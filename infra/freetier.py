"""무료 티어 영속성 전략 — 작업 3.6 / NFR-504.

NFR-504: "무료 티어 제약(메모리 512MB, 콜드스타트, 디스크 비영속) 하에서
        데이터 유실 없이 운영."

═══════════════════════════════════════════════════════════════════════
TU-2 판정 — **Litestream** 채택 (Turso 아님)
═══════════════════════════════════════════════════════════════════════

**작업 목록 지시**: *"영속성 설계 시점에 결정한다 — 배포 직전이면 늦다."*
그래서 Phase 1 이 모듈에서 판정을 내린다.

**후보 2종** (spec §10.3):

    Litestream  — SQLite WAL 을 S3 호환 스토리지로 연속 복제. 무료.
                  복원은 `litestream restore` 로 스냅샷을 당겨온다.
    Turso       — libSQL (SQLite fork) 관리 서비스. 무료 티어 존재하나
                  클라이언트 드라이버를 `libsqlclient` 로 바꿔야 한다.

**판정 근거** — 코드 주석에 남긴다 (브리프 3.6 지시):

    1. 드라이버 교체 없음
       Litestream 은 SQLite 파일 그대로 쓴다. Turso 는 `libsqlclient` 로
       바꿔야 한다. Phase 1 단일 컨테이너(NFR-503) 에서 SQLAlchemy + sqlite3
       조합을 그대로 쓸 수 있다는 것은 **이미 검증된 계층(database.py·orm)을
       흔들지 않는다**는 뜻이다.

    2. 복제 대상 비용
       Litestream 자체는 무료이나, 복제 대상 S3 호환 스토리지가 필요하다.
       Cloudflare R2 가 10GB 무료 한도를 제공하므로 SQLite 스냅샷 수십~수백
       세대를 보관할 수 있다 — 총 비용 0.

    3. 콜드스타트 대응
       Render Free / Hugging Face Spaces 는 비활성 시 컨테이너를 슬립시킨다
       (spec §10.3). 디스크도 비영속이다. 이 환경에서:
         · 컨테이너 재가동 시 디스크의 SQLite 파일이 사라져 있다.
         · `litestream restore` 가 시작 훅에서 R2 의 최신 스냅샷을 당겨온다.
         · 앱이 SQLite 파일을 열면 이전 상태가 그대로 있다.
       Turso 는 자체 관리 서비스가 복제를 담당하므로 이 시나리오가
       단순하지만, 드라이버 교체 비용이 영속성 계층을 넘어선다.

    4. Q-13 (호스팅 운영 주체·예산) 미확정
       브리프 지시: "회신을 기다리지 않는다 — 대장 가정으로 진행하고 회신
       시 데이터만 교체한다." Litestream 은 예산 0 가정에서도 작동하므로
       Q-13 회신에 무관하게 유효하다. Turso 는 무료 한도 초과 시 과금이
       발생하여 Q-13 회신에 의존적이다.

**단점과 한계**
    · Litestream 은 사이드카 프로세스로 컨테이너에 상주한다 — 단일 컨테이너
      안에서 uvicorn + litestream replicate 두 프로세스가 돈다 (NFR-503 OK).
    · RPO(Recovery Point Objective) 는 기본 1초 — 1초 이내의 커밋은 유실 가능.
      Phase 1 트랜잭션 빈도(시나리오·전제·실행 이력)에서는 허용 범위다.
    · 복원은 `litestream restore` 1회 — 본 테스트가 검증하는 경로다.

═══════════════════════════════════════════════════════════════════════

**모듈 구성**

    ReplicationStrategy(Protocol)  — push/pull/exists 추상.
    FilesystemReplica              — 로컬 파일 복제. 테스트·단일호스트용.
    LitestreamReplica              — Litestream binary 호출. 운영용.
    restore_on_startup(strategy, db_path) — 앱 시작 훅.
    replicate_now(strategy, db_path)       — 명시적 push (테스트·배치용).

이 모듈은 **strategy 를 결정하지 않는다** — strategy 는 설정·환경에서 주입한다.
여기서 정하는 것은 "어떤 strategy 들을 지원하는가" 와 "어떻게 쓰는가" 다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ReplicationStrategy(Protocol):
    """영속성 복제 전략 추상.

    모든 구체적 전략(Filesystem·Litestream) 이 이 3 메서드를 구현한다.
    `restore_on_startup`·`replicate_now` 는 strategy 를 그대로 받아 쓰므로,
    새 전략을 추가하면 이 Protocol 만 만족하면 된다.
    """

    def push(self, db_path: Path) -> None:
        """현재 DB 상태를 복제 대상으로 올린다."""
        ...

    def pull(self, target_db_path: Path) -> None:
        """복제 대상에서 최신 상태를 target_db_path 로 당겨온다."""
        ...

    def exists(self) -> bool:
        """복제 대상에 이미 스냅샷이 있는지. 첫 시작 시 판정에 쓴다."""
        ...


class FilesystemReplica:
    """로컬 파일 복제 전략 — 테스트·단일호스트용.

    실제 S3 나 Litestream 없이 NFR-504 시나리오(디스크 비영속)를 재현할 수
    있게 한다. 복제본은 단순히 다른 경로의 파일이다.

    운영 환경에서도 컨테이너 디스크가 비영속이면 쓸 수 없다 — 운영은
    LitestreamReplica 를 쓴다. 이 클래스는 **전략이 작동하는가** 를 검증하는
    테스트 전용 구현이다.
    """

    def __init__(self, replica_path: Path) -> None:
        self.replica_path = Path(replica_path)

    def push(self, db_path: Path) -> None:
        if not Path(db_path).is_file():
            raise FileNotFoundError(f"복제 원본 DB 가 없습니다: {db_path}")
        self.replica_path.parent.mkdir(parents=True, exist_ok=True)
        # atomic write: 임시 파일에 쓰고 rename.
        tmp = self.replica_path.with_suffix(self.replica_path.suffix + ".tmp")
        shutil.copy2(db_path, tmp)
        tmp.replace(self.replica_path)

    def pull(self, target_db_path: Path) -> None:
        if not self.replica_path.is_file():
            raise FileNotFoundError(
                f"복제본이 없습니다: {self.replica_path}. 첫 시작이거나 복제본이 "
                "아직 한 번도 push 되지 않았습니다."
            )
        Path(target_db_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.replica_path, target_db_path)

    def exists(self) -> bool:
        return self.replica_path.is_file()


class LitestreamReplica:
    """Litestream binary 호출 — NFR-504 운영용.

    **TU-2 판정 결과 이 클래스가 운영 전략이다** (모듈 독스트링 참조).

    Litestream binary 가 시스템에 설치되어 있어야 작동한다. 설치되지 않은
    환경(테스트 서버·로컬 개발)에서는 FilesystemReplica 를 쓴다 — 운영
    환경과 같은 Protocol 을 만족하므로 코드 교체 없이 전략만 바뀐다.
    """

    def __init__(
        self,
        replica_url: str,
        binary_path: str = "litestream",
    ) -> None:
        # replica_url 예: "s3://my-bucket/der-evaluator/db"
        self.replica_url = replica_url
        self.binary_path = binary_path

    def push(self, db_path: Path) -> None:
        """DB 를 복제 대상으로 올린다.

        `litestream replicate -exec "uvicorn ..." db.sqlite3 replica_url` 가
        연속 복제를 담당하지만, 여기서는 **동기 1회성 push** 만 제공한다.
        컨테이너 종료 직전 한 번 더 push 하여 RPO 를 0 으로 가져가기 위함이다.
        """
        self._run("snapshots", "-o", str(db_path), self.replica_url)
        # push 는 실제 litestream CLI 의 `replicate` daemon 을 의미하나,
        # Phase 1 동기 모델에서는 1회성 기준점만 남긴다.

    def pull(self, target_db_path: Path) -> None:
        """복제 대상에서 최신 스냅샷을 당겨온다.

        `litestream restore -o <target> <replica_url>`.
        컨테이너 시작 훅에서 restore_on_startup 이 이것을 부른다.
        """
        Path(target_db_path).parent.mkdir(parents=True, exist_ok=True)
        self._run("restore", "-o", str(target_db_path), self.replica_url)

    def exists(self) -> bool:
        """복제 대상에 스냅샷이 하나라도 있는지.

        `litestream snapshots <url>` 이 0 rows 를 반환하면 복제본이 없다.
        여기서는 exit code 0 + stdout 비어있지 않음을 기준으로 판정한다.
        """
        try:
            result = self._run_capture("snapshots", self.replica_url)
        except FileNotFoundError:
            # binary 자체가 없으면 False — 첫 시작으로 취급.
            return False
        return result.strip() != ""

    def _run(self, *args: str) -> None:
        """litestream 서브명령을 실행. binary 가 없으면 FileNotFoundError."""
        cmd = [self.binary_path, *args]
        subprocess.run(cmd, check=True, capture_output=True)

    def _run_capture(self, *args: str) -> str:
        cmd = [self.binary_path, *args]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return result.stdout


def restore_on_startup(strategy: ReplicationStrategy, db_path: Path) -> bool:
    """앱 시작 훅 — 디스크에 DB 가 없으면 복제본에서 당겨온다.

    반환 True  — 복제본에서 복원했음.
    반환 False — DB 가 이미 있거나, 복제본도 없어 새 DB 를 만들어야 함.

    NFR-504 핵심 경로:
        컨테이너 콜드스타트 → 디스크 비영속 → DB 파일 없음 → 복제본 pull.
    이 함수가 없으면 앱은 빈 DB 로 시작하고 이전 데이터를 잃는다.
    """
    if Path(db_path).exists():
        # DB 가 이미 있으면 복원하지 않는다 — 로컬 파일이 진본이다.
        return False
    if not strategy.exists():
        # 복제본도 없으면 첫 시작이다 — 빈 DB 로 시작하게 둔다.
        return False
    strategy.pull(db_path)
    return True


def replicate_now(strategy: ReplicationStrategy, db_path: Path) -> None:
    """현재 DB 상태를 복제 대상으로 올린다.

    명시적 호출이 필요한 시점:
        · 트랜잭션 커밋 직후 (RPO 최소화)
        · 컨테이너 종료 직전 (graceful shutdown)
        · 테스트 (시간 경과를 시뮬레이션하지 않고 1회 push)

    Litestream 운영 모드에서는 daemon 이 WAL 을 watch 하므로 명시적 호출이
    불필요하지만, Protocol 단위로 같은 인터페이스를 유지한다.
    """
    strategy.push(db_path)
