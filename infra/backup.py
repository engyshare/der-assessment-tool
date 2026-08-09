"""SQLite 백업·복원 — 작업 3.5 / NFR-502.

NFR-502: "SQLite 파일 일 1회 이상 자동 백업, 분기 1회 복원 리허설."

**이 모듈이 제공하는 것**
    `take_backup(src, dst)`               — SQLite 파일 복제 (바이트 동일).
    `restore_from_backup(backup, target)` — 백업 파일을 DB 경로로 되돌림.
    `should_backup(now, last_backup_at)`  — 24시간 주기 도달 여부 (순수 함수).

**이 모듈이 제공하지 않는 것**
    스케줄러. 언제 백업을 돌릴지는 app/인프라가 결정한다 — 영속성 계층은
    "지금 백업해야 하는가" 와 "어떻게 백업·복원하는가" 만 안다.

왜 단순 파일 복제인가
---------------------
SQLite 공식 백업 방법은 두 가지다:
    1. `sqlite3_backup_*` API — DB 가 열려 있을 때 online 으로 복제.
    2. 파일 단순 복제 — 엔진이 닫혀 있을 때.

Phase 1 은 단일 컨테이너·단일 프로세스(NFR-503) 다. 앱이 백업 타이밍을
잡으면 엔진을 잠깐 멈추고 파일을 복제하는 것이 단순하고 빠르다. 바이트가
정확히 같으므로 비트 동일 복원이 보장된다.

`sqlite3_backup_*` API 가 필요해지는 시점은 다중 프로세스가 같은 DB 를
열어놓고 24시간 운영할 때다 — Phase 2 MILP 도입·다중 워커 이후 검토.

WAL 모드 주의
-------------
SQLite 가 WAL 모드일 때 파일 복제는 `-wal`·`-shm` 파일도 같이 복제해야
한다. 그렇지 않으면 커밋됐지만 파일에만 있고 -wal 에 있는 트랜잭션이
누락된다. 이 모듈은 WAL 모드를 가정하고 세 파일을 함께 다룬다.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path

#: NFR-502 — 일 1회 이상. 24시간을 기준으로 잡는다.
BACKUP_INTERVAL: timedelta = timedelta(hours=24)


class BackupCorruptError(RuntimeError):
    """백업 파일이 SQLite 포맷이 아니다 — 복원을 거부한다."""


_SQLITE_MAGIC: bytes = b"SQLite format 3\x00"


def take_backup(src: Path, dst: Path) -> None:
    """SQLite DB 파일을 백업 경로로 복제한다.

    바이트를 그대로 옮긴다 — SQLite 의 페이지 구조·인덱스·트랜잭션 상태까지
    전부 보존된다. WAL 모드일 경우 `-wal`·`-shm` 도 함께 복사한다 (커밋된
    트랜잭션이 -wal 에만 있을 수 있으므로).

    src 가 존재하지 않으면 빈 DB 에 대한 백업 시도로 보고 FileNotFoundError 를
    올린다 — 조용히 빈 파일을 만들면 "백업했다" 가 "DB 가 비어 있었다" 와
    구분이 안 된다.
    """
    src = Path(src)
    dst = Path(dst)
    if not src.is_file():
        raise FileNotFoundError(f"백업 원본 DB 파일이 없습니다: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

    # WAL 모드 동반 파일 — 있으면 같이 복사.
    for suffix in ("-wal", "-shm"):
        side = src.with_name(src.name + suffix)
        if side.is_file():
            shutil.copy2(side, dst.with_name(dst.name + suffix))


def restore_from_backup(backup: Path, target: Path) -> None:
    """백업 파일을 DB 경로로 되돌린다.

    **brief 3.5 의 핵심**: 「복원이 된다」를 검증하는 단계. 두 가지 안전장치:

        1. 백업 파일이 SQLite 포맷인지 확인 (magic byte). 아니면 거부.
        2. target 의 기존 파일을 덮어쓰기 전에 백업 파일을 먼저 검증.

    거부하지 않고 조용히 빈 DB 로 복원되면, 운영자는 「복원 절차를 거쳤다」만
    보고 데이터 유실을 눈치채지 못한다.
    """
    backup = Path(backup)
    target = Path(target)
    if not backup.is_file():
        raise FileNotFoundError(f"복원할 백업 파일이 없습니다: {backup}")

    _assert_sqlite_format(backup)

    target.parent.mkdir(parents=True, exist_ok=True)
    # target 이 이미 있으면 덮어쓴다 — 복원 시나리오는 「깨진 DB 를 되돌린다」다.
    shutil.copy2(backup, target)

    # WAL 동반 파일이 백업에 있으면 같이 복원.
    for suffix in ("-wal", "-shm"):
        side = backup.with_name(backup.name + suffix)
        if side.is_file():
            shutil.copy2(side, target.with_name(target.name + suffix))


def _assert_sqlite_format(path: Path) -> None:
    """SQLite magic byte (처음 16바이트) 가 맞는지 본다.

    SQLite 헤더는 항상 `b"SQLite format 3\\x00"` 로 시작한다. 다르면 백업이
    잘렸거나 다른 파일이 잘못 들어온 것이다.
    """
    with Path(path).open("rb") as f:
        head = f.read(len(_SQLITE_MAGIC))
    if head != _SQLITE_MAGIC:
        raise BackupCorruptError(
            f"백업 파일이 SQLite 포맷이 아닙니다: {path}\n"
            f"  magic bytes = {head!r}\n"
            f"  expected    = {_SQLITE_MAGIC!r}\n"
            "잘린 파일·다른 포맷·디스크 손상이 의심됩니다. 다른 백업을 "
            "사용하거나 새 백업을 시도하십시오."
        )


def should_backup(now: datetime, last_backup_at: datetime | None) -> bool:
    """24시간 주기 도달 여부. 순수 함수 — 시간은 호출부가注入.

    왜 함수 하나로 뺐는가 — 스케줄러가 영속성 계층 밖에 있기 때문이다.
    영속성은 「언제 돌릴지」모르지만 「지금 돌려야 하는가」는 안다. 이 판정을
    순수 함수로 빼면 테스트에서 24시간을 기다리지 않고 시간을注入해 검증한다.

    `last_backup_at=None` 이면 첫 백업 — 언제든 해야 한다.
    """
    if last_backup_at is None:
        return True
    return now - last_backup_at >= BACKUP_INTERVAL
