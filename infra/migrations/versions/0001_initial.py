"""initial schema — §7.2 엔티티 전건 + 감구로그 테이블.

**명시적 op.create_table 선언** (create_all 위임이 아님). 각 테이블의 컬럼·
FK·CHECK 제약을 이 파일에 손으로 적었다. 모델(infra.orm.*) 과 마이그레이션
(이 파일) 이 **독립 산출물** 이어야, 한 쪽을 고치고 다른 쪽을 안 고쳤을 때
``test_no_drift_between_migration_and_models`` 가 실제로 빨간불이 된다.

왜 create_all 위임을 버렸는가
-----------------------------
이전 판은 ``Base.metadata.create_all`` 로 현재 ORM 메타데이터를 가져와 DB 를
만들었다. 그 구조에서 ``compare_metadata(mc, Base.metadata)`` 는 **모델을
모델과 비교** 하는 자기충족 검증이었다 (§13.0.2 금지). 모델을 바꾸면
create_all 이 같은 메타데이터를 쓰므로 DB 가 같이 바뀌어 drift 가 절대
잡히지 않는다 — 42건 통과라는 초록불이 이 결함을 가리고 있었다.

명시적 DDL 은 두 산출물을 분리한다. 모델 컬럼을 하나 지우거나名字 바꾸면
마이그레이션 파일은 그대로고 모델만 바뀌어, diff 가 실제로 위반을 보고한다.
이 사실을 ``test_drift_checker_catches_model_column_addition`` 가 직접
검증한다 — 모델에 컬럼을 심어 마이그레이션과 어긋나게 만들고 테스트가
빨간불이 되는지 본다.

FK 의존성 순서
--------------
부모 테이블이 자식보다 먼저. SQLite 가 foreign_key_constraint 를 걸려면
참조 대상이 이미 있어야 한다. 아래 순서는 위상 정렬 결과이며, downgrade 는
역순으로 drop 한다.

금액 컬럼 타입
--------------
``money()`` ≡ ``Numeric(precision=None, scale=0, asdecimal=True)`` — Decimal
원 단위 정수 (NFR-103). 금액성 컬럼(value_krw·subsidy_fixed_amount·
subsidy_cap·capex_hw·capex_sw·fixed_om_annual) 은 이 타입을 직접 적는다.
비율(vat_rate·fund_rate·subsidy_rate 등) 은 ``Numeric(asdecimal=True)``
(소수 0~1, COMMON §6). 단가(capex_unit·opex_unit) 도 ``Numeric(asdecimal=True)``
(소수점 단위 허용). 지표값(ResultMetric.value·InfluenceRank.delta_*) 은 ``Float``
(비율·금액·물리량 혼합).

Revision ID: 0001_initial
Revises:
Create Date: 2025-08-09
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """23개 테이블을 명시적 DDL 로 생성 (FK 의존성 순서)."""
    # ── money 타입 — money() 와 동일. 반복을 피해 로컬 별칭. ──────────
    money_type = sa.Numeric(precision=None, scale=0, asdecimal=True)
    ratio_type = sa.Numeric(asdecimal=True)

    # ── identity ────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(320), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id", sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("tags", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    # ── assumption ──────────────────────────────────────────────────
    op.create_table(
        "assumption_sets",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column(
            "parent_version_id", sa.Integer,
            sa.ForeignKey("assumption_sets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "assumption_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "assumption_set_id", sa.Integer,
            sa.ForeignKey("assumption_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value_type", sa.String(16), nullable=False),
        sa.Column("value_json", sa.Text, nullable=True),
        sa.Column("ref_entity", sa.String(64), nullable=True),
        sa.Column("ref_id", sa.Integer, nullable=True),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("base_year", sa.Integer, nullable=True),
        sa.Column("applicable_scope", sa.Text, nullable=True),
        sa.Column("derivation_method", sa.Text, nullable=True),
        sa.Column("source", sa.Text, nullable=True),
        sa.Column("verified_at", sa.String(32), nullable=True),
        sa.Column("confidence", sa.String(16), nullable=True),
        sa.CheckConstraint("value_type IN ('scalar', 'ref')", name="value_type_enum"),
        sa.CheckConstraint(
            "confidence IN ('확정', '추정', '가정')", name="confidence_axis2"
        ),
    )

    # ── catalog (시나리오보다 먼저 — der_instances/common_assets FK) ─
    op.create_table(
        "tech_catalog",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tag", sa.String(64), nullable=False, unique=True),
        sa.Column("spec", sa.Text, nullable=True),
        sa.Column("base_year", sa.Integer, nullable=True),
        sa.Column("capex_unit", ratio_type, nullable=True),
        sa.Column("opex_unit", ratio_type, nullable=True),
        sa.Column("lifetime", sa.Integer, nullable=True),
        sa.Column("applicable_scope", sa.Text, nullable=True),
        sa.Column("derivation_method", sa.Text, nullable=True),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("verified_at", sa.String(32), nullable=True),
        sa.Column("confidence", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "tariff_tables",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.String(32), nullable=True),
        sa.Column("valid_to", sa.String(32), nullable=True),
        sa.Column("structure_json", sa.Text, nullable=True),
        sa.Column("vat_rate", ratio_type, nullable=True),
        sa.Column("fund_rate", ratio_type, nullable=True),
        sa.Column("source", sa.Text, nullable=True),
        sa.CheckConstraint(
            "type IN ('누진', 'TOU', '직접거래')", name="tariff_type_enum"
        ),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "incentive_schemes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("subsidy_rate", ratio_type, nullable=True),
        sa.Column("subsidy_fixed_amount", money_type, nullable=True),
        sa.Column("subsidy_cap", money_type, nullable=True),
        sa.Column("loan_rate", ratio_type, nullable=True),
        sa.Column("interest_rate", ratio_type, nullable=True),
        sa.Column("grace_years", sa.Integer, nullable=True),
        sa.Column("repay_years", sa.Integer, nullable=True),
        sa.Column("repay_method", sa.String(32), nullable=True),
        sa.Column("tax_credit_rate", ratio_type, nullable=True),
        sa.Column("funder", sa.String(200), nullable=True),
        sa.Column("funding_program", sa.String(200), nullable=True),
        sa.Column("is_prefunded", sa.Boolean, nullable=True),
        sa.Column("prefunded_status", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    # ── regulation (time_series_datasets 가 der_bindings 보다 먼저) ──
    op.create_table(
        "regulation_profiles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column(
            "parent_version_id", sa.Integer,
            sa.ForeignKey("regulation_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("valid_from", sa.String(32), nullable=True),
        sa.Column("valid_to", sa.String(32), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "regulation_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "regulation_profile_id", sa.Integer,
            sa.ForeignKey("regulation_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value_json", sa.Text, nullable=True),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("scope", sa.String(64), nullable=True),
        sa.Column("valid_from", sa.String(32), nullable=True),
        sa.Column("valid_to", sa.String(32), nullable=True),
        sa.Column("reference_url", sa.Text, nullable=True),
        sa.Column("verified_at", sa.String(32), nullable=True),
    )
    op.create_table(
        "benefit_exclusion_rules",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("benefit_a", sa.String(64), nullable=False),
        sa.Column("benefit_b", sa.String(64), nullable=False),
        sa.Column("exclusion_type", sa.String(8), nullable=False),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column(
            "regulation_profile_id", sa.Integer,
            sa.ForeignKey("regulation_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "exclusion_type IN ('A', 'B', 'C', 'D')", name="exclusion_type_enum"
        ),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "time_series_datasets",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id", sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("resolution", sa.Integer, nullable=True),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("storage_path", sa.Text, nullable=True),
        sa.Column("checksum", sa.String(128), nullable=True),
        sa.Column("stats_json", sa.Text, nullable=True),
        sa.Column("source", sa.Text, nullable=True),
        sa.Column("confidence", sa.String(16), nullable=True),
        sa.CheckConstraint(
            "kind IN ('load', 'pv', 'smp', 'temp')", name="ts_kind_enum"
        ),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    # ── scenario ────────────────────────────────────────────────────
    op.create_table(
        "scenarios",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "project_id", sa.Integer,
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assumption_set_id", sa.Integer,
            sa.ForeignKey("assumption_sets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("definition_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "scenario_overrides",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "scenario_id", sa.Integer,
            sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("assumption_key", sa.String(128), nullable=False),
        sa.Column("value_json", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "der_instances",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "scenario_id", sa.Integer,
            sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tag", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("params_json", sa.Text, nullable=True),
        sa.Column("operating_mode", sa.String(64), nullable=True),
        sa.Column(
            "incentive_scheme_id", sa.Integer,
            sa.ForeignKey("incentive_schemes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_table(
        "der_dataset_bindings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "der_instance_id", sa.Integer,
            sa.ForeignKey("der_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dataset_id", sa.Integer,
            sa.ForeignKey("time_series_datasets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.CheckConstraint("role IN ('load', 'generation', 'temp')", name="role_enum"),
    )
    op.create_table(
        "case_grids",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "scenario_id", sa.Integer,
            sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("variables_json", sa.Text, nullable=False),
        sa.Column("coupled_sets_json", sa.Text, nullable=True),
        sa.Column("expected_case_count", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "common_assets",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "scenario_id", sa.Integer,
            sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("capex_hw", money_type, nullable=True),
        sa.Column("capex_sw", money_type, nullable=True),
        sa.Column("fixed_om_annual", money_type, nullable=True),
        sa.Column("lifetime_hw", sa.Integer, nullable=True),
        sa.Column("lifetime_sw", sa.Integer, nullable=True),
        sa.Column("allocation_rule", sa.String(32), nullable=True),
        sa.Column(
            "incentive_scheme_id", sa.Integer,
            sa.ForeignKey("incentive_schemes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "kind IN ('CEMS', 'HEMS', '계량통신')", name="common_asset_kind"
        ),
        sa.CheckConstraint(
            "allocation_rule IN ('균등', '용량비례', '미안분')",
            name="allocation_rule_enum",
        ),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    # ── run ─────────────────────────────────────────────────────────
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "scenario_id", sa.Integer,
            sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_grid_id", sa.Integer,
            sa.ForeignKey("case_grids.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("engine", sa.String(32), nullable=True),
        sa.Column("started_at", sa.String(32), nullable=True),
        sa.Column("finished_at", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=True),
        sa.Column("manifest_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "case_results",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "run_id", sa.Integer,
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("case_index", sa.Integer, nullable=False),
        sa.Column("case_values_json", sa.Text, nullable=True),
        sa.Column("metrics_json", sa.Text, nullable=True),
    )
    op.create_table(
        "proforma_lines",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "run_id", sa.Integer,
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("case_index", sa.Integer, nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column(
            "der_instance_id", sa.Integer,
            sa.ForeignKey("der_instances.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("value_krw", money_type, nullable=True),
    )
    op.create_table(
        "result_metrics",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "run_id", sa.Integer,
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("case_index", sa.Integer, nullable=False),
        sa.Column("perspective", sa.String(32), nullable=False),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("value", sa.Float, nullable=True),
        sa.Column("unit", sa.String(32), nullable=True),
    )
    op.create_table(
        "influence_ranks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "run_id", sa.Integer,
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("assumption_key", sa.String(128), nullable=False),
        sa.Column("delta_low", sa.Float, nullable=True),
        sa.Column("delta_high", sa.Float, nullable=True),
        sa.Column("rank", sa.Integer, nullable=True),
        sa.Column("flips_conclusion", sa.Boolean, nullable=True),
    )

    # ── audit ───────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "actor_user_id", sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=True),
        sa.Column("entity_id", sa.Integer, nullable=True),
        sa.Column("before_json", sa.Text, nullable=True),
        sa.Column("after_json", sa.Text, nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    """23개 테이블을 FK 의존성 역순으로 삭제."""
    for table in (
        "audit_logs",
        "influence_ranks",
        "result_metrics",
        "proforma_lines",
        "case_results",
        "runs",
        "common_assets",
        "case_grids",
        "der_dataset_bindings",
        "der_instances",
        "scenario_overrides",
        "scenarios",
        "time_series_datasets",
        "benefit_exclusion_rules",
        "regulation_items",
        "regulation_profiles",
        "incentive_schemes",
        "tariff_tables",
        "tech_catalog",
        "assumption_items",
        "assumption_sets",
        "projects",
        "users",
    ):
        op.drop_table(table)
