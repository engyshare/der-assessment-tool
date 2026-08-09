"""3.3 — Alembic 초기 마이그레이션 검증.

세 가지를 확인한다:
    1. upgrade 가 깨끗이 돈다 (에러 없이 head 도달).
    2. §7.2 엔티티 전건 + audit_logs 총 23개 테이블이 실제로 만들어진다.
    3. upgrade 후 Base.metadata 와 DB 스키마가 일치한다 (drift 없음).
    4. downgrade base 가 깨끗이 돈다 — 복원 가능성.

**COMMON.md §8 함정**: drift 검사는 자기검사 구조다. Alembic autogenerate
diff 가 빈 리스트를 반환하면 "통과" 지만, **diff 가 작동하지 않아서 빈 것일
수도 있다.** 그래서 심어 둔 위반(임의 컬럼 추가)을 drift checker 가 실제로
잡는지 별도 검증한다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from infra.database import Base, make_engine

#: WP-13 소유의 마이그레이션 디렉터리. tests/infra 에서 두 단계 위.
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "infra" / "migrations"
_INI = _MIGRATIONS_DIR / "alembic.ini"


def _alembic_config(db_url: str) -> Config:
    """alembic.ini 를 읽어 DB URL 을 주입한 Config 반환.

    `script_location = .` (alembic.ini 자신의 디렉터리) 로 설정했으므로, Config
    가 alembic.ini 를 로드하면 자동으로 migrations 디렉터리가 스크립트 루트가 된다.
    """
    cfg = Config(str(_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _table_names(db_url: str) -> set[str]:
    engine = make_engine(db_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_alembic_ini_lives_in_infra_migrations() -> None:
    """alembic.ini 는 infra/migrations/ 안에 있다 (WP-13 소유 경로).

    루트에 두면 WP-15(pyproject.toml 소유) 와 충돌한다 — COMMON.md §1.
    """
    assert _INI.is_file(), f"alembic.ini 가 예상 위치에 없습니다: {_INI}"
    # migrations 디렉터리가 WP-13 단독 소유인지 확인.
    parts = _INI.parts
    assert "infra" in parts and "migrations" in parts


def test_upgrade_creates_all_tables(tmp_db_url: str) -> None:
    """upgrade head 가 23개 테이블을 만든다 — §7.2 22엔티티 + audit_logs."""
    cfg = _alembic_config(tmp_db_url)
    command.upgrade(cfg, "head")

    tables = _table_names(tmp_db_url)
    # alembic_version 테이블이 추가로 있지만, 우리가 만든 것은 아래 23개.
    expected = {
        "users", "projects",
        "assumption_sets", "assumption_items",
        "scenarios", "scenario_overrides",
        "der_instances", "der_dataset_bindings",
        "case_grids",
        "tech_catalog", "tariff_tables",
        "incentive_schemes", "common_assets",
        "regulation_profiles", "regulation_items",
        "benefit_exclusion_rules", "time_series_datasets",
        "runs", "case_results", "proforma_lines",
        "result_metrics", "influence_ranks",
        "audit_logs",
    }
    missing = expected - tables
    assert not missing, (
        f"마이그레이션이 테이블을 놓쳤습니다: {sorted(missing)}. "
        "infra.orm.__init__.py 의 __all__ 과 0001_initial.py 를 대조하십시오."
    )


def test_no_drift_between_migration_and_models(tmp_db_url: str) -> None:
    """upgrade 후 Base.metadata 와 DB 스키마가 일치한다.

    drift 가 있으면 모델을 고쳤는데 마이그레이션을 안 고친 것이다 (또는 그 반대).
    autogenerate diff 가 빈 리스트를 반환해야 한다.
    """
    cfg = _alembic_config(tmp_db_url)
    command.upgrade(cfg, "head")

    engine = make_engine(tmp_db_url)
    try:
        with engine.connect() as conn:
            mc = MigrationContext.configure(conn)
            diffs = compare_metadata(mc, Base.metadata)
    finally:
        engine.dispose()

    # Alembic 가 제안하는 diff 항목 중 SQLite 한계로 잡지 못하는 것들이 있다.
    # 우리가 잡고 싶은 것은 「컬럼이나 테이블이 한 쪽에만 있다」 는 종류의 drift.
    structural = [
        d for d in diffs
        if _is_structural_diff(d)
    ]
    assert structural == [], (
        f"스키마 drift 발견: {structural}. 모델(infra.orm) 과 마이그레이션"
        "(0001_initial.py) 이 어긋나 있습니다. 어느 쪽이 정본인지 확인하십시오."
    )


def _is_structural_diff(diff: tuple[Any, ...]) -> bool:
    """autogenerate diff 중 구조적(테이블·컬럼·FK) 변경만 거른다.

    Alembic 은 인덱스·CHECK 제약의 이름 차이를 자주 diff 로 보고한다 — 특히
    SQLite batch mode 에서. 이런 것은 노이즈다. 우리가 잡고 싶은 것은
    "테이블/컬럼이 한 쪽에만 있다" 이다.
    """
    # diff tuple 의 첫 원소가 문자열 카테고리 ("add_table", "remove_table",
    # "add_column", "remove_column", "add_fk", "remove_fk" 등) 다.
    if not diff:
        return False
    head = diff[0]
    if isinstance(head, str):
        return head in {
            "add_table", "remove_table",
            "add_column", "remove_column",
            "add_fk", "remove_fk",
        }
    return False


def test_downgrade_to_base_drops_all_tables(tmp_db_url: str) -> None:
    """downgrade base 가 테이블을 전부 지운다 — 복원 가능성.

    downgrade 가 안 되면 rollback 경로가 없다. 운영 중 잘못 올린 마이그레이션을
    되돌릴 수 없게 된다.
    """
    cfg = _alembic_config(tmp_db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    tables = _table_names(tmp_db_url)
    # alembic_version 은 downgrade base 후에도 남을 수 있다 — 빈 리비전 표시용.
    leftover_business_tables = tables - {"alembic_version"}
    assert not leftover_business_tables, (
        f"downgrade 후 테이블이 남습니다: {leftover_business_tables}. "
        "0001_initial.downgrade 가 drop_all 에 모든 테이블을 넘기는지 확인."
    )


# ── COMMON.md §8 — drift checker 가 진짜 잡는가 ──────────────────────────


def test_drift_checker_catches_added_column(tmp_db_url: str) -> None:
    """drift checker 가 의도로 넣은 위반(컬럼 추가)을 실제로 잡는지 확인.

    이 단언이 없으면 `test_no_drift_between_migration_and_models` 의 빈 diff 가
    "checker 가 작동해서 빈 것" 인지 "checker 가 망가져서 빈 것" 인지 알 수 없다.
    임의 컬럼을 DB 에 직접 추가하고 checker 가 그것을 잡는지 본다.
    """
    cfg = _alembic_config(tmp_db_url)
    command.upgrade(cfg, "head")

    # 사용자 테이블에 마이그레이션에 없는 컬럼을 직접 추가 — drift 심기.
    engine = make_engine(tmp_db_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN planted_extra TEXT"))
    finally:
        engine.dispose()

    # Base.metadata 에는 planted_extra 가 없으므로 diff 가 잡아야 한다.
    engine = make_engine(tmp_db_url)
    try:
        with engine.connect() as conn:
            mc = MigrationContext.configure(conn)
            diffs = compare_metadata(mc, Base.metadata)
    finally:
        engine.dispose()

    structural = [d for d in diffs if _is_structural_diff(d)]
    assert structural, (
        "drift checker 가 심어 둔 위반(planted_extra 컬럼)을 잡지 못했습니다. "
        "_is_structural_diff 필터가 너무 좁거나 compare_metadata 가 작동하지 "
        "않습니다 — 이 경우 test_no_drift_between_migration_and_models 의 통과는 "
        "「검사가 통과했다」일 뿐 「검사가 검사했다」가 아닙니다."
    )


def test_drift_checker_does_not_flag_in_sync_schema(tmp_db_url: str) -> None:
    """drift checker 가 정상 스키마에서 거짓 경고를 내지 않는지 확인.

    앞선 테스트의 역방향. 심어 둔 위반이 없으면 structural diff 도 비어야 한다.
    거짓 경고가 나면 실제 drift 가 묻힌다.
    """
    cfg = _alembic_config(tmp_db_url)
    command.upgrade(cfg, "head")

    engine = make_engine(tmp_db_url)
    try:
        with engine.connect() as conn:
            mc = MigrationContext.configure(conn)
            diffs = compare_metadata(mc, Base.metadata)
    finally:
        engine.dispose()

    structural = [d for d in diffs if _is_structural_diff(d)]
    assert structural == [], (
        f"drift checker 가 정상 스키마에서 거짓 경고를 냅니다: {structural}. "
        "_is_structural_diff 가 너무 넓거나 naming convention 이 어긋난 것."
    )


def test_drift_checker_catches_model_column_addition(tmp_db_url: str) -> None:
    """**핵심 검증** — 모델에 컬럼을 심으면 마이그레이션 drift 가 잡히는가.

    이전 판의 자기충족 검증(§13.0.2 차단) 을 직접 점검한다. 0001_initial 이
    ``Base.metadata.create_all`` 을 썼을 때는, 모델에 컬럼을 추가하면
    ``create_all`` 이 같은 메타데이터를 써서 DB 가 같이 바뀌므로 drift 가 절대
    잡히지 않았다. 명시적 ``op.create_table`` 로 바꾼 뒤에는 모델과 마이그레이션이
    독립이므로 잡혀야 한다 — 잡히지 않으면 자기충족 검증이 해결되지 않은 것이다.

    오라클: 순위 4 (교차 구현 대조 — §13.0.1 ④). «검사가 통과했다» 와
    «검사가 무언가를 검사했다» 를 가른다.
    """
    from sqlalchemy import Column, String

    from infra.orm.identity import User

    cfg = _alembic_config(tmp_db_url)
    command.upgrade(cfg, "head")

    # 모델 메타데이터에만 임시 컬럼 추가 — 마이그레이션 0001_initial 에는 없다.
    planted = Column("planted_for_drift_test", String(32), nullable=True)
    User.__table__.append_column(planted)  # type: ignore[attr-defined]
    try:
        engine = make_engine(tmp_db_url)
        try:
            with engine.connect() as conn:
                mc = MigrationContext.configure(conn)
                diffs = compare_metadata(mc, Base.metadata)
        finally:
            engine.dispose()

        structural = [d for d in diffs if _is_structural_diff(d)]
        assert structural, (
            "모델에 컬럼을 심었는데 drift 가 잡히지 않았다. 명시적 op.create_table "
            "로 전환했음에도 잡히지 않는다면, 마이그레이션이 아직 모델 메타데이터에 "
            "의존하고 있는 것이다 — 자기충족 검증이 해결되지 않았다 (§13.0.2)."
        )
    finally:
        # 임시 컬럼 제거 — 다른 테스트에 영향을 주지 않게.
        User.__table__._columns.remove(planted)
