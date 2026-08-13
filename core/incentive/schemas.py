from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.contracts.units import Money, to_won
from core.contracts.validation import ValidationError


class IncentiveScheme(BaseModel):
    """자원 인스턴스별 지원(보조금, 융자, 세제) 조건 (FR-604)"""

    model_config = ConfigDict(frozen=True)

    @classmethod
    def create_baseline(cls) -> IncentiveScheme:
        return cls(
            subsidy_rate=0.0,
            subsidy_fixed=None,
            subsidy_limit=None,
            loan_rate=0.0,
            loan_interest=0.0,
            loan_grace_years=0,
            loan_repayment_years=0,
            loan_repayment_type="원리금균등",
            tax_credit_rate=0.0,
            sponsor="국비",
            funding_program=None,
            is_prefunded=False,
            prefunded_status=None,
        )

    # 보조금 (FR-604-AC1, AC2, AC8)
    subsidy_rate: float = Field(ge=0.0, le=1.0)
    subsidy_fixed: Decimal | None = None
    subsidy_limit: Decimal | None = None

    # 융자 (FR-604-AC3)
    loan_rate: float = Field(ge=0.0, le=1.0)
    loan_interest: float = Field(ge=0.0)
    loan_grace_years: int = Field(ge=0)
    loan_repayment_years: int = Field(ge=0)
    loan_repayment_type: Literal["원리금균등", "원금균등", "만기일시"]

    # 세제 (FR-604-AC5)
    tax_credit_rate: float = Field(ge=0.0, le=1.0)
    depreciation_method: str = "정액법"
    depreciation_years: int = 20

    # 지원 주체 및 기지원 (FR-604-AC6, FR-611-AC1)
    sponsor: Literal["국비", "지방비", "민간"]
    funding_program: str | None = None
    is_prefunded: bool = False
    prefunded_status: str | None = None

    @model_validator(mode="after")
    def _validate_subsidy(self) -> IncentiveScheme:
        if self.subsidy_fixed is not None and self.subsidy_rate > 0:
            raise ValidationError(
                field="incentivescheme.subsidy_fixed_and_subsidy_rate",
                reason=(
                    "정액 보조금(subsidy_fixed)과 정률 보조금(subsidy_rate)은 "
                    "동시에 설정할 수 없습니다"
                ),
                action=(
                    "둘 중 하나만 사용하십시오 — 정액 보조금을 쓰려면 subsidy_rate를 0으로, "
                    "정률 보조금을 쓰려면 subsidy_fixed를 None으로 하십시오"
                ),
            )
        return self

    @model_validator(mode="after")
    def _validate_prefunding_status(self) -> IncentiveScheme:
        if self.is_prefunded:
            if self.prefunded_status not in ("확정 지원", "지원 예정"):
                raise ValidationError(
                    field="incentivescheme.prefunded_status",
                    reason=(
                        f"기지원 설비는 prefunded_status 를 '확정 지원' 또는 '지원 예정'으로 "
                        f"명시해야 합니다 — 현재 값: {self.prefunded_status!r}"
                    ),
                    action="prefunded_status를 '확정 지원' 또는 '지원 예정' 중 하나로 고치십시오",
                )
            return self
        if self.prefunded_status is not None:
            raise ValidationError(
                field="incentivescheme.prefunded_status",
                reason="prefunded_status 는 is_prefunded=True 인 설비에만 지정합니다",
                action="is_prefunded=True로 설정하거나 prefunded_status를 None으로 하십시오",
            )
        return self

    def calculate_financing(self, total_capex: float | Decimal) -> dict[str, Money]:
        """자금조달 항등식 산출 (FR-604-AC4, AC7, AC8, AC9)"""
        capex_won = to_won(total_capex)

        # 보조금 확정액 산출
        if self.subsidy_fixed is not None:
            subsidy = to_won(self.subsidy_fixed)
        else:
            calc_subsidy = to_won(float(capex_won) * self.subsidy_rate)
            if self.subsidy_limit is not None:
                subsidy = min(calc_subsidy, to_won(self.subsidy_limit))
            else:
                subsidy = calc_subsidy

        # 융자 확정액 산출
        loan = to_won(float(capex_won) * self.loan_rate)

        # 보조금 + 융자금이 총사업비를 초과하는지 검사 (자부담 음수 불가)
        # DV-1: 보조 확정액 + 융자 확정액 + 자부담액 = 대상 총사업비 (오차 1원 이내)
        if subsidy + loan > capex_won:
            raise ValidationError(
                field="incentivescheme.subsidy_rate_or_loan_rate",
                reason=(
                    f"보조금({subsidy})과 융자({loan})의 합이 총사업비({capex_won})를 "
                    "초과하여 자부담이 음수가 됩니다"
                ),
                action="보조금율 또는 융자율을 낮추어 자부담이 0 이상이 되도록 고치십시오",
                rule="DV-1",
            )

        # 자부담 잔여 자동 계산
        equity = to_won(capex_won - subsidy - loan)

        # 자금조달 항등식 검증 (오차 1원 이내)
        assert abs((subsidy + loan + equity) - capex_won) <= 1, (
            "자금조달 항등식 오차 범위를 벗어났습니다."
        )

        return {
            "subsidy": subsidy,
            "loan": loan,
            "equity": equity,
        }
