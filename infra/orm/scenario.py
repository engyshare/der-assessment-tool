"""시나리오·자원 인스턴스 — §7.2 · §7.1 O-1.

**이 파일의 `Scenario` 가 §7.1 O-1 / DV-11 의 검사 대상이다.** Scenario 는
`assumption_set_id` 로만 전제에 닿는다 — `regulation_profile_id`·
`tariff_table_id`·`discount_rate`·`analysis_years` 같은 필드를 절대 가져서는
안 된다. (test_scenario_ownership.py 가 기계 검사한다.)
"""
from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from infra.database import Base
from infra.orm.base import PkMixin, TimestampMixin


class Scenario(Base, PkMixin, TimestampMixin):
    """단일 분석 정의 — §7.2.

    **주의 — 이 클래스에 필드를 추가하기 전에 test_scenario_ownership 의
    FORBIDDEN_FIELDS 와 forbidden_patterns 를 먼저 보십시오.** discount_rate·
    analysis_years 같은 이름이 여기 들어가면 DV-11 위반이다.
    전제 분류(FR-601-AC2.*)에 해당 값은 AssumptionSet 에 넣고 여기서는
    `assumption_set_id` 만 들고 있다.
    """

    __tablename__ = "scenarios"

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # §7.1 O-1 — Scenario 가 전제에 닿는 유일한 경로.
    # 이 컬럼 외에 discount_rate·analysis_years·regulation_profile_id·
    # tariff_table_id 등을 두면 안 된다 (DV-11).
    assumption_set_id: Mapped[int] = mapped_column(
        ForeignKey("assumption_sets.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="1")
    definition_json: Mapped[str | None] = mapped_column(Text)


class ScenarioOverride(Base, PkMixin, TimestampMixin):
    """전제 오버라이드 — §7.2 O-2.

    시나리오가 전제와 다른 값을 써야 하면 **필드를 복제하지 않고** 이 테이블에
    명시적 레코드를 남긴다 (O-2). 오버라이드는 리포트에 자동 표기된다 (FR-602).
    """

    __tablename__ = "scenario_overrides"

    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    assumption_key: Mapped[str] = mapped_column(String(128), nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)


class DERInstance(Base, PkMixin):
    """시나리오 내 자원 인스턴스 — §7.2. FR-103."""

    __tablename__ = "der_instances"

    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    tag: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    params_json: Mapped[str | None] = mapped_column(Text)
    # FR-105 — 운전 방법은 자원 클래스가 선언한 목록에 속해야 한다 (DV-14).
    # 자원 클래스와의 정합은 core.der 가 검사한다. 영속성은 문자열로 담는다.
    operating_mode: Mapped[str | None] = mapped_column(String(64))
    # §7.2 — incentive_scheme_id 는 자원 단위. Scenario 가 아닌 자원이
    # 들고 있어야 서로 다른 자원에 다른 지원 조건을 걸 수 있다.
    incentive_scheme_id: Mapped[int | None] = mapped_column(
        ForeignKey("incentive_schemes.id", ondelete="SET NULL")
    )


class DERDatasetBinding(Base, PkMixin):
    """자원↔시계열 바인딩 — §7.2 O-3.

    시계열 데이터셋은 Scenario 가 아니라 **DERInstance 단위로** 바인딩된다.
    가구부·공용부 부하가 서로 다른 시계열을 가져야 하기 때문이다 (FR-905).
    """

    __tablename__ = "der_dataset_bindings"
    __table_args__ = (
        CheckConstraint("role IN ('load', 'generation', 'temp')", name="role_enum"),
    )

    der_instance_id: Mapped[int] = mapped_column(
        ForeignKey("der_instances.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("time_series_datasets.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)


class CaseGrid(Base, PkMixin, TimestampMixin):
    """탐색 변수 정의 — §7.2. FR-802.

    결합 변수(coupled_sets)는 변수 그룹별로 값 목록 길이가 같아야 한다 (DV-9).
    스키마는 두 JSON 을 분리해 담고 정합 검사는 core.casegrid 가 한다.
    """

    __tablename__ = "case_grids"

    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    variables_json: Mapped[str] = mapped_column(Text, nullable=False)
    coupled_sets_json: Mapped[str | None] = mapped_column(Text)
    # 기본 임계치 500 (DV-10). 0 은 sentinel 로 쓰지 않는다 — 0 건이 곧
    # 무한대 케이스가 되므로 0 은 사실상 오류고, nullable 로 구분한다.
    expected_case_count: Mapped[int | None] = mapped_column(Integer)
