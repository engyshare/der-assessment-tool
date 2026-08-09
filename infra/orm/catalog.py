"""카탈로그·요금·지원조건·공통설비 — §7.2.

v0.5 가 이 영역에 세 가지 변경을 넣었다:
    · TechCatalog      — applicable_scope·derivation_method·verified_at 3컬럼 추가
    · IncentiveScheme  — subsidy_fixed_amount·funding_program·is_prefunded·
                         prefunded_status (FR-611 타 사업 기지원 설비)
    · CommonAsset      — 신설 엔티티 자체 (FR-106)

이 변경이 스키마에 누락되면 v0.4 까지의 단일 보조율 모델로 데이터가 들어가고,
그 상태에서 FR-611 검증을 통과한 것처럼 보인다. 테스트(test_catalog_v05_fields)
가 각 컬럼을 컬럼명으로 찍어 확인한다.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from infra.database import Base
from infra.orm.base import PkMixin, TimestampMixin, money


class TechCatalog(Base, PkMixin, TimestampMixin):
    """기술 기본값 카탈로그 — §7.2.

    같은 단가를 다른 규격에 적용하는 오류를 잡으려면 **적용 범위** 가 값과 함께
    저장되어야 한다 (v0.5 근거). 그래서 applicable_scope·derivation_method 가
    필수 컬럼이다 — JSON 안에 숨기지 않고 컬럼으로 올려 CHECK·검색이 가능하게.
    """

    __tablename__ = "tech_catalog"

    tag: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    spec: Mapped[str | None] = mapped_column(Text)
    base_year: Mapped[int | None] = mapped_column(Integer)
    # 단가(원/kW 등) — 금액성이지만 money() 가 아닌 일반 Numeric. 단가는
    # 원/W = 0.001 원/W 처럼 소수점 단위가 자연스럽고, money() 의 scale=0
    # (원 단위 정수) 정합에 맞지 않는다. 산출 시 to_won() 이 정수 원으로
    # 반올림하므로 저장은 정밀하게, 합산은 정수 원에서.
    capex_unit: Mapped[float | None] = mapped_column(Numeric(asdecimal=True))
    opex_unit: Mapped[float | None] = mapped_column(Numeric(asdecimal=True))
    lifetime: Mapped[int | None] = mapped_column(Integer)
    # v0.5 신규 3컬럼 — 같은 값이라도 적용 범위가 다르면 다른 자원이다.
    applicable_scope: Mapped[str | None] = mapped_column(Text)
    derivation_method: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[str | None] = mapped_column(String(16))


class TariffTable(Base, PkMixin, TimestampMixin):
    """요금표 — §7.2. INT-3 (배전사업자 요금표 YAML 시드)."""

    __tablename__ = "tariff_tables"
    __table_args__ = (
        CheckConstraint(
            "type IN ('누진', 'TOU', '직접거래')", name="tariff_type_enum"
        ),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_from: Mapped[str | None] = mapped_column(String(32))
    valid_to: Mapped[str | None] = mapped_column(String(32))
    structure_json: Mapped[str | None] = mapped_column(Text)
    # 부가세·펀드 비율 — COMMON.md §6 의 내부 비율 소수(0~1) 규약을 따른다.
    # 0.10 = 10%. % 단위(0~100) 로 저장하지 않는다 — v1.0 의 inflation_pct
    # 함정(같은 «2%» 가 0.02 와 100배 어긋남) 과 같은 결함이 생긴다.
    vat_rate: Mapped[float | None] = mapped_column(Numeric(asdecimal=True))
    fund_rate: Mapped[float | None] = mapped_column(Numeric(asdecimal=True))
    source: Mapped[str | None] = mapped_column(Text)


class IncentiveScheme(Base, PkMixin, TimestampMixin):
    """지원 조건 — §7.2.

    v0.5 (FR-611) 신규 필드: `subsidy_fixed_amount`·`funding_program`·
    `is_prefunded`·`prefunded_status`. **이 네 컬럼이 빠지면 타 사업 기지원
    설비 시나리오가 입력 단계에서 거부된다** — 단일 비율 보조만으로는
    "이미 보조받은 설비에 또 보조를 주는가" 를 표현할 수 없다.
    """

    __tablename__ = "incentive_schemes"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # subsidy_rate·loan_rate·interest_rate·tax_credit_rate 는 비율(소수 0~1).
    # 0.20 = 20%. % 단위로 저장하지 않는다 (COMMON.md §6, vat_rate 참조).
    subsidy_rate: Mapped[float | None] = mapped_column(Numeric(asdecimal=True))
    # v0.5 — 정액 보조. 정률·정액이 같이 있을 수 있다 (DV-1).
    # 금액성 컬럼 — money() (Decimal 원 단위 정수, NFR-103). Mapped[Decimal]
    # 로 선언해 money() 의 Numeric[Decimal] 반환과 일치시킨다. float 로
    # 선언하면 합산 시 미세 오차가 화면상 정상으로 보이는 결함이 생긴다.
    subsidy_fixed_amount: Mapped[Decimal | None] = mapped_column(money())
    subsidy_cap: Mapped[Decimal | None] = mapped_column(money())
    loan_rate: Mapped[float | None] = mapped_column(Numeric(asdecimal=True))
    interest_rate: Mapped[float | None] = mapped_column(Numeric(asdecimal=True))
    grace_years: Mapped[int | None] = mapped_column(Integer)
    repay_years: Mapped[int | None] = mapped_column(Integer)
    repay_method: Mapped[str | None] = mapped_column(String(32))
    tax_credit_rate: Mapped[float | None] = mapped_column(Numeric(asdecimal=True))
    funder: Mapped[str | None] = mapped_column(String(200))
    # v0.5 — FR-611 타 사업 기지원 설비 3필드.
    funding_program: Mapped[str | None] = mapped_column(String(200))
    is_prefunded: Mapped[bool | None] = mapped_column(Boolean)
    prefunded_status: Mapped[str | None] = mapped_column(String(64))


class CommonAsset(Base, PkMixin, TimestampMixin):
    """비에너지 공통설비 — §7.2. v0.5 신설 (FR-106).

    CEMS·HEMS·계량통신 설비는 발전·축열과 무관한 자본 비용이다. 자원 인스턴스
    (DERInstance) 와 분리된 이 테이블에 둬, 비용 배분(allocation_rule) 이 자원
    수가 바뀌어도 일관되게 적용되게 한다.
    """

    __tablename__ = "common_assets"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('CEMS', 'HEMS', '계량통신')", name="common_asset_kind"
        ),
        CheckConstraint(
            "allocation_rule IN ('균등', '용량비례', '미안분')",
            name="allocation_rule_enum",
        ),
    )

    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 금액성 컬럼 — money() (Decimal 원 단위 정수, NFR-103). capex·O&M 은
    # 20년 합산되므로 float 미세 오차가 누적된다. Decimal 로 통일.
    capex_hw: Mapped[Decimal | None] = mapped_column(money())
    capex_sw: Mapped[Decimal | None] = mapped_column(money())
    fixed_om_annual: Mapped[Decimal | None] = mapped_column(money())
    lifetime_hw: Mapped[int | None] = mapped_column(Integer)
    lifetime_sw: Mapped[int | None] = mapped_column(Integer)
    allocation_rule: Mapped[str | None] = mapped_column(String(32))
    incentive_scheme_id: Mapped[int | None] = mapped_column(
        ForeignKey("incentive_schemes.id", ondelete="SET NULL")
    )
