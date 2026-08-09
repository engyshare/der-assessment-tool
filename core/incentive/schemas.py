from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.contracts.units import Money, to_won


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
            raise ValueError(
                "정액 보조금(subsidy_fixed)과 정률 보조금(subsidy_rate)은 동시에 설정할 수 없습니다."  # noqa: E501
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
        if subsidy + loan > capex_won:
            raise ValueError(
                f"보조금({subsidy})과 융자({loan})의 합이 총사업비({capex_won})를 초과하여 자부담이 음수가 됩니다."  # noqa: E501
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
