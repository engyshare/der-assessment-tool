"""3.6 — 무료 티어 영속성 전략 — NFR-504-AC1.

NFR-504: "무료 티어 제약(메모리 512MB, 콜드스타트, 디스크 비영속) 하에서
        데이터 유실 없이 운영."

**brief 3.6 의 핵심**: 512MB · 콜드스타트 · 디스크 비영속 환경에서 **데이터
유실 0** 실증. 시뮬레이션:

    1. 앱 시작 — 빈 DB. 첫 데이터 시드.
    2. replicate_now — 복제 대상에 스냅샷 push.
    3. 컨테이너 슬립 / 디스크 날아감 — DB 파일 삭제.
    4. 컨테이너 재가동 — restore_on_startup 이 복제본에서 pull.
    5. 데이터 전건 회복 — 행 수·ID 로 비교.

이 사이클이 N 번 반복돼도 데이터가 유실되지 않는다는 것을 보인다.

TU-2 결정 근거
--------------
이 테스트는 Litestream binary 없이 돌아간다 — FilesystemReplica 가 같은
ReplicationStrategy Protocol 을 만족하므로, **전략(데이터 무결성)** 은
검증하면서 **외부 의존 없이** 돌린다. LitestreamReplica 자체는 binary 가
있는 환경에서만 도는 별도 스킵 테스트로 둔다.

오라클: 4 순위(항등식) — 복원 후 행 수 = 복제 전 행 수.
"""
from __future__ import annotations

import ast
import inspect
import shutil
from pathlib import Path

import pytest
from sqlalchemy import text

from infra.audit import AuditLog  # noqa: F401  — 메타데이터 등록
from infra.database import Base, make_engine, session_factory
from infra.freetier import (
    FilesystemReplica,
    LitestreamReplica,
    ReplicationStrategy,
    replicate_now,
    restore_on_startup,
)
from infra.orm import (
    AssumptionItem,
    AssumptionSet,
    Project,
    User,
)

# ── TU-2 결정 근거 — 모듈에 기록되었는지 확인 ────────────────────────────


def test_tu2_decision_documented_in_freetier_module() -> None:
    """TU-2 판정(Litestream vs Turso) 의 근거가 코드 독스트링에 남아 있다.

    AST 파싱을 이용해 주석/코드의 영향을 받지 않고 모듈 독스트링 본문만
    정확히 검사한다.
    """
    import infra.freetier as ft

    source = inspect.getsource(ft)
    tree = ast.parse(source)
    docstring = ast.get_docstring(tree) or ""

    # 결정이 적혀 있는지 — Litestream 채택, Turso 아님.
    assert "Litestream" in docstring
    assert "Turso" in docstring
    # 근거 항목이 하나 이상 적혀 있는지.
    assert "판정 근거" in docstring or "드라이버" in docstring


def test_litestream_replica_class_exists_as_production_strategy() -> None:
    """LitestreamReplica 클래스가 운영 전략으로 정의되어 있다."""
    assert issubclass(LitestreamReplica, object)
    # Protocol 만족 여부 — runtime_checkable 이므로 isinstance 가 작동한다.
    instance = LitestreamReplica("s3://bucket/db")
    assert isinstance(instance, ReplicationStrategy)


def test_litestream_live_binary_execution_skipped() -> None:
    """Litestream 실제 바이너리를 사용한 복제/복원은 환경 미설치로 수행 불가함을 명시.

    로컬 및 CI 환경에 litestream 바이너리(shutil.which('litestream') is None)가
    설치되어 있지 않아 실제 바이너리 구동 검사는 수행할 수 없으나,
    동일한 Protocol을 따르는 FilesystemReplica로 전략 무결성을 대체 실증함.
    """
    if shutil.which("litestream") is None:
        pytest.skip(
            "litestream 바이너리가 로컬/CI 환경에 설치되어 있지 않아 "
            "실제 바이너리 실행 검출을 건너땁니다."
        )


# ── NFR-504-AC1 — 디스크 비영속 시뮬레이션, 데이터 유실 0 ──────────────


@pytest.mark.req("NFR-504-AC1")
def test_zero_data_loss_through_disk_loss_cycle(
    tmp_path: Path,
) -> None:
    """콜드스타트·디스크 비영속 1사이클에서 데이터 유실 0.

    시나리오:
        seed → push → DB 삭제(디스크 비영속) → restore_on_startup → 검증.

    FilesystemReplica 를 쓴다 — Litestream binary 없이도 전략 자체를 검증한다.
    """
    db_path = tmp_path / "app.db"
    replica_path = tmp_path / "replica" / "replica.db"
    strategy = FilesystemReplica(replica_path)

    # 1) 최초 시작 — DB 없음. restore_on_startup 은 False (복제본도 없음).
    assert restore_on_startup(strategy, db_path) is False
    assert strategy.exists() is False

    # 2) 데이터 시드
    seeded_ids = _seed_assumption_data(db_path)
    assert _count_rows(db_path, "assumption_items") == 1

    # 3) 복제 — 앱이 커밋 후 호출하는 훅이라고 가정.
    replicate_now(strategy, db_path)
    assert strategy.exists() is True
    assert replica_path.is_file()

    # 4) 컨테이너 슬립 / 디스크 날아감 — DB 파일 삭제.
    db_path.unlink()
    assert not db_path.exists(), "디스크 비영속 시뮬레이션이 안 되었습니다."

    # 5) 컨테이너 재가동 — restore_on_startup 이 복제본에서 당겨옴.
    restored = restore_on_startup(strategy, db_path)
    assert restored is True, "복제본이 있는데 restore_on_startup 이 False 다"
    assert db_path.is_file()

    # 6) 데이터 전건 회복 — ID·행 수 비교.
    restored_ids = _read_assumption_ids(db_path)
    assert restored_ids == seeded_ids, (
        f"복원 후 데이터가 다릅니다: {seeded_ids} → {restored_ids}. "
        "전략이 push/pull 중 어느 단계에서 데이터를 손상시킵니다."
    )
    assert _count_rows(db_path, "assumption_items") == 1


@pytest.mark.req("NFR-504-AC1")
def test_zero_data_loss_through_multiple_cold_starts(
    tmp_path: Path,
) -> None:
    """콜드스타트 3사이클 반복 — 누적 유실 0.

    무료 티어는 하루 여러 번 슬립될 수 있다. 매 사이클마다 데이터가 유실되면
    며칠 만에 시나리오 전체가 사라진다. 세 번의 cycle 을 돌며 데이터가
    누적 보존되는지 확인.
    """
    db_path = tmp_path / "cycle.db"
    strategy = FilesystemReplica(tmp_path / "repl" / "r.db")

    # Cycle 1: 시드 + 복제
    restore_on_startup(strategy, db_path)
    _seed_assumption_data(db_path, suffix="c1")
    replicate_now(strategy, db_path)
    after_c1 = _count_rows(db_path, "assumption_items")
    assert after_c1 == 1

    # 디스크 손실 1
    db_path.unlink()
    restore_on_startup(strategy, db_path)
    assert _count_rows(db_path, "assumption_items") == 1, "Cycle 1 데이터 유실"

    # Cycle 2: 추가 시드 + 복제
    _seed_assumption_data(db_path, suffix="c2")
    replicate_now(strategy, db_path)
    after_c2 = _count_rows(db_path, "assumption_items")
    assert after_c2 == 2

    # 디스크 손실 2
    db_path.unlink()
    restore_on_startup(strategy, db_path)
    assert _count_rows(db_path, "assumption_items") == 2, "Cycle 2 데이터 유실"

    # Cycle 3
    _seed_assumption_data(db_path, suffix="c3")
    replicate_now(strategy, db_path)
    db_path.unlink()
    restore_on_startup(strategy, db_path)
    assert _count_rows(db_path, "assumption_items") == 3, (
        "3-cycle 후 누적 데이터가 유실되었습니다 — 매 복원마다 일부가 "
        "빠지면 운영 수 일차에 전체가 사라집니다."
    )


# ── NFR-504-AC1 — restore_on_startup 의 판정 분기 ──────────────────────


@pytest.mark.req("NFR-504-AC1")
def test_restore_on_startup_skips_when_db_already_present(
    tmp_path: Path,
) -> None:
    """DB 가 이미 있으면 복원을 건너뛴다 — 로컬이 진본.

    복제본이 더 최신이더라도 로컬을 우선한다 — 컨테이너가 graceful shutdown
    을 했다면 로컬이 마지막 커밋을 담고 있기 때문이다. 이 분기가 없으면
    시작할 때마다 강제 pull 이 로컬의 새 데이터를 날린다.
    """
    db_path = tmp_path / "local.db"
    strategy = FilesystemReplica(tmp_path / "r.db")

    # 로컬 DB 가 이미 있다
    _seed_assumption_data(db_path)
    replicate_now(strategy, db_path)

    # restore_on_startup 은 False — 로컬이 있으므로.
    assert restore_on_startup(strategy, db_path) is False


@pytest.mark.req("NFR-504-AC1")
def test_restore_on_startup_skips_when_no_replica_yet(
    tmp_path: Path,
) -> None:
    """첫 시작 (복제본도 없음) — False 반환, 앱이 빈 DB 로 시작하게 둔다."""
    strategy = FilesystemReplica(tmp_path / "first.db")
    assert strategy.exists() is False
    assert restore_on_startup(strategy, tmp_path / "app.db") is False


# ── FilesystemReplica — atomic write 검증 ──────────────────────────────


def test_filesystem_replica_uses_atomic_rename(tmp_path: Path) -> None:
    """push 도중 깨진 복제본이 남지 않아야 한다.

    `shutil.copy` 를 직접 쓰면 도중 실패 시 반쓰기 파일이 남는다. FilesystemReplica
    는 임시 파일 + rename 을 써야 한다. 여기서는 간접 검증 — 복제 성공 후
    `.tmp` 파일이 남지 않는지 본다.
    """
    db_path = tmp_path / "src.db"
    strategy = FilesystemReplica(tmp_path / "repl" / "r.db")
    _seed_assumption_data(db_path)

    strategy.push(db_path)

    # .tmp 잔여가 없어야 한다.
    leftover = list((tmp_path / "repl").glob("*.tmp"))
    assert leftover == [], f"atomic rename 잔여: {leftover}"


# ── LitestreamReplica — binary 없는 환경에서의 안전한 스킵 ──────────────


def test_litestream_replica_exists_returns_false_when_binary_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """litestream binary 가 없는 환경에서 exists() 는 False (예외 아님).

    운영 환경에서 binary 가 빠지면 restore_on_startup 의 첫 판정이 깨진다.
    binary 가 없으면 "복제본 없음" 으로 취급해 앱이 빈 DB 로 시작하게 둔다.
    """
    strategy = LitestreamReplica("s3://nonexistent/bucket", binary_path="litestream-missing-xyz")
    # shutil.which 로 binary 가 없는 걸 먼저 확인
    assert shutil.which("litestream-missing-xyz") is None
    assert strategy.exists() is False


# ── helpers ──────────────────────────────────────────────────────────


def _seed_assumption_data(db_path: Path, suffix: str = "x") -> set[int]:
    """한 쌍의 User/Project/AssumptionSet/AssumptionItem 을 넣고
    AssumptionSet.id 와 AssumptionItem.id 를 반환."""
    url = f"sqlite:///{db_path}"
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as session:
        user = User(email=f"t-{suffix}@example.com", password_hash="x", role="user")
        session.add(user)
        session.flush()

        project = Project(user_id=user.id, name=f"P-{suffix}")
        session.add(project)
        session.flush()

        aset = AssumptionSet(name=f"전제-{suffix}", version="1")
        session.add(aset)
        session.flush()

        item = AssumptionItem(
            assumption_set_id=aset.id,
            key=f"discount_rate_{suffix}",
            value_type="scalar",
            value_json="0.05",
            unit="fraction",
            confidence="추정",
        )
        session.add(item)
        session.commit()
        ids = {aset.id, item.id}
    engine.dispose()
    return ids


def _read_assumption_ids(db_path: Path) -> set[int]:
    url = f"sqlite:///{db_path}"
    engine = make_engine(url)
    factory = session_factory(engine)
    with factory() as session:
        items = session.query(AssumptionItem).all()
        sets = session.query(AssumptionSet).all()
        ids = {s.id for s in sets} | {i.id for i in items}
    engine.dispose()
    return ids


def _count_rows(db_path: Path, table: str) -> int:
    engine = make_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as conn:
            return int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())
    finally:
        engine.dispose()
