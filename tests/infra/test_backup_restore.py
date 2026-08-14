"""3.5 — 백업·복원 리허설 테스트 — NFR-502-AC1.

NFR-502: "SQLite 파일 일 1회 이상 자동 백업, 분기 1회 복원 리허설."

**brief 3.5 의 핵심**: 「백업이 돈다」가 아니라 「복원이 된다」를 검증한다.
복원해 본 적 없는 백업은 백업이 아니다. 그래서 이 테스트는:

    1. 데이터를 쓴다.
    2. 백업한다.
    3. DB 를 잃는다 (디스크 비영속 시뮬레이션 — 파일 삭제).
    4. 백업에서 복원한다.
    5. 데이터가 전부 돌아왔는지 건수로 비교한다.

추가 — COMMON.md §8: 깨진 백업(잘린 파일)을 복원하려 하면 **에러가 나야** 한다.
조용히 빈 DB 로 복원되면 「복원 절차가 있다」는 것이 「복원이 된다」를
보장하지 않는다.

일 1회 자동 백업 (NFR-502-AC1 의 「자동」 부분)
-----------------------------------------------
스케줄러는 영속성 계층 밖이다 — app·인프라가 결정한다. 영속성은
`should_backup(now, last_backup_at)` 하나로 「백업 주기 도달 여부」를
판정하는 순수 함수만 제공한다. 시간이注入되어야 테스트에서 시간을 조작할
수 있다 (실제로 24시간 안 기다릴 수 없으므로).

오라클: 4 순위(항등식) — 복원 후 행 수 = 백업 전 행 수.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from infra.audit import AuditLog  # noqa: F401  — 메타데이터 등록
from infra.backup import (
    BackupCorruptError,
    restore_from_backup,
    should_backup,
    take_backup,
)
from infra.database import Base, make_engine, session_factory
from infra.orm import (
    AssumptionItem,
    AssumptionSet,
    Project,
    User,
)


def _seed_one_assumption_set(session: Session) -> int:
    """한 쌍의 User/Project/AssumptionSet/AssumptionItem 을 디비에 넣고
    AssumptionSet.id 를 반환. 복원 후 같은 데이터가 돌아왔는지 비교하는 기준."""
    user = User(email="t@example.com", password_hash="x", role="user")
    session.add(user)
    session.flush()

    project = Project(user_id=user.id, name="P1")
    session.add(project)
    session.flush()

    aset = AssumptionSet(name="전제 v1", version="1", price_basis="명목")
    session.add(aset)
    session.flush()

    item = AssumptionItem(
        assumption_set_id=aset.id,
        key="discount_rate",
        value_type="scalar",
        value_json="0.05",
        unit="fraction",
        confidence="추정",
    )
    session.add(item)
    session.commit()
    return aset.id


def _count_assumption_items(engine: Engine) -> int:
    """독립 엔진으로 행 수를 센다 — 세션 캐시가 아니라 디비 상태를 본다."""
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT COUNT(*) FROM assumption_items")).scalar_one())


# ── NFR-502-AC1 — 복원 리허설 (이 테스트의 본체) ────────────────────────


@pytest.mark.req("NFR-502-AC1")
def test_restore_recovers_all_data_after_db_loss(
    tmp_db_url: str, tmp_path: Path
) -> None:
    """백업 → DB 손실 → 복원 → 데이터 전건 회복.

    이 테스트가 통과하면 NFR-502 의 「복원 리허설」 을 거친 것이다. 실패하면
    백업 파일 형식이 잘못되었거나 restore_from_backup 이 손실을 일으킨다.
    """
    db_path = Path(tmp_db_url.replace("sqlite:///", ""))
    backup_path = tmp_path / "backup.sqlite3"

    # 1) 데이터 시드
    engine = make_engine(tmp_db_url)
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as session:
        original_id = _seed_one_assumption_set(session)
    original_count = _count_assumption_items(engine)
    assert original_count >= 1
    engine.dispose()

    # 2) 백업
    take_backup(db_path, backup_path)
    assert backup_path.is_file(), "백업 파일이 생성되지 않았습니다"
    assert backup_path.stat().st_size > 0

    # 3) DB 손실 (디스크 비영속 / 컨테이너 슬립 / 디스크 교체 시뮬레이션)
    db_path.unlink()
    assert not db_path.exists(), "DB 파일 삭제가 안 되었습니다 — 복원 시나리오 깨짐"

    # 4) 복원
    restore_from_backup(backup_path, db_path)
    assert db_path.is_file(), "복원이 DB 파일을 만들지 않았습니다"

    # 5) 데이터 전건 회복 — 행 수가 같고, ID 가 같다
    engine2 = make_engine(tmp_db_url)
    restored_count = _count_assumption_items(engine2)
    factory2 = session_factory(engine2)
    with factory2() as session:
        restored_set = session.get(AssumptionSet, original_id)
        items = session.query(AssumptionItem).filter_by(assumption_set_id=original_id).all()
    engine2.dispose()

    assert restored_count == original_count, (
        f"복원 후 행 수가 다릅니다: {original_count} → {restored_count}. "
        "백업이 일부 행을 잃었거나 복원 절차가 truncate 를 수반합니다."
    )
    assert restored_set is not None, "복원 후 AssumptionSet 이 없습니다"
    assert restored_set.name == "전제 v1"
    assert len(items) == 1
    assert items[0].key == "discount_rate"


# ── COMMON.md §8 — 깨진 백업을 잡는가 ──────────────────────────────────


@pytest.mark.req("NFR-502-AC1")
def test_restore_rejects_corrupt_backup(
    tmp_db_url: str, tmp_path: Path
) -> None:
    """잘린 백업 파일을 복원하려 하면 에러가 나야 한다.

    조용히 빈 DB 로 복원되면 NFR-502 가 「복원 가능」이 아니라 「복원 절차가
    있다」만 보장하게 된다. 깨진 백업을 명시적으로 거부한다.
    """
    db_path = Path(tmp_db_url.replace("sqlite:///", ""))
    backup_path = tmp_path / "broken.sqlite3"
    backup_path.write_bytes(b"NOT A SQLITE DATABASE FILE")

    with pytest.raises(BackupCorruptError, match="백업"):
        restore_from_backup(backup_path, db_path)


# ── NFR-502-AC1 — 일 1회 자동 백업 판정 ───────────────────────────────


@pytest.mark.req("NFR-502-AC1")
def test_should_backup_returns_true_when_no_prior_backup() -> None:
    """첫 백업은 언제든 해야 한다 — last_backup_at=None 이면 True."""
    assert should_backup(now=datetime(2024, 1, 1), last_backup_at=None) is True


@pytest.mark.req("NFR-502-AC1")
def test_should_backup_returns_true_after_24h() -> None:
    """24시간이 지됀으면 다시 백업한다 — NFR-502 「일 1회 이상」."""
    last = datetime(2024, 1, 1, 0, 0, 0)
    now = last + timedelta(hours=24, seconds=1)
    assert should_backup(now=now, last_backup_at=last) is True


@pytest.mark.req("NFR-502-AC1")
def test_should_backup_returns_false_within_24h() -> None:
    """24시간 이내면 중복 백업을 피한다 — 무료 티어 디스크 낭비."""
    last = datetime(2024, 1, 1, 0, 0, 0)
    now = last + timedelta(hours=23, minutes=59)
    assert should_backup(now=now, last_backup_at=last) is False


# ── 보조 — take_backup 은 동일한 바이트를 복제하는가 ──────────────────


@pytest.mark.req("NFR-502-AC1")
def test_take_backup_produces_byte_identical_copy(
    tmp_db_url: str, tmp_path: Path
) -> None:
    """백업 파일은 원본과 바이트가 같아야 한다 — SQLite 파일 단순 복제.

    바이트가 다르면 WAL·페이지 정렬·압축 어딘가에서 손상이 생겼고, 복원 후
    데이터가 달라질 수 있다. NFR-502 의 「복원」이 「비트 동일 복원」인지
    확인한다.
    """
    db_path = Path(tmp_db_url.replace("sqlite:///", ""))
    backup_path = tmp_path / "byte_copy.sqlite3"

    engine = make_engine(tmp_db_url)
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory() as session:
        _seed_one_assumption_set(session)
    engine.dispose()

    take_backup(db_path, backup_path)
    original = db_path.read_bytes()
    copy = backup_path.read_bytes()
    assert original == copy, (
        "백업 파일이 원본과 바이트가 다릅니다 — SQLite VACUUM/압축/정렬 차이가 "
        "아닌 take_backup 의 손상일 수 있습니다."
    )
