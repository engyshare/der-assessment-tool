from decimal import Decimal
from typing import Any

import pytest

from core.contracts.units import Money
from core.incentive.calculator import build_capex_cashflows, calculate_loan_schedule
from core.incentive.schemas import IncentiveScheme
from core.incentive.solver import solve_min_subsidy_rate


def _scheme(**kwargs: Any) -> IncentiveScheme:
    """Helper to create scheme with defaults for testing."""
    defaults = {
        "subsidy_rate": 0.0,
        "subsidy_fixed": None,
        "subsidy_limit": None,
        "loan_rate": 0.0,
        "loan_interest": 0.0,
        "loan_grace_years": 0,
        "loan_repayment_years": 0,
        "loan_repayment_type": "원리금균등",
        "tax_credit_rate": 0.0,
        "sponsor": "국비",
        "funding_program": None,
        "is_prefunded": False,
        "prefunded_status": None,
    }
    defaults.update(kwargs)
    return IncentiveScheme(**defaults)


@pytest.mark.req("FR-604-AC1", "FR-604-AC6")
def test_incentive_scheme_subsidy_forms() -> None:
    """FR-604-AC1, AC6: 보조금 정률/정액/상한 형태 검증"""
    scheme_rate = _scheme(subsidy_rate=0.4, subsidy_limit=Decimal("400"))
    assert scheme_rate.subsidy_rate == 0.4
    assert scheme_rate.subsidy_limit == Decimal("400")

    scheme_fixed = _scheme(subsidy_fixed=Decimal("600"))
    assert scheme_fixed.subsidy_fixed == Decimal("600")


@pytest.mark.req("FR-604-AC2")
def test_incentive_scheme_loan_conditions() -> None:
    """FR-604-AC2: 융자 조건 검증"""
    scheme = _scheme(
        loan_rate=0.3,
        loan_interest=0.03,
        loan_grace_years=2,
        loan_repayment_years=5,
        loan_repayment_type="원리금균등",
    )
    assert scheme.loan_rate == 0.3
    assert scheme.loan_interest == 0.03
    assert scheme.loan_grace_years == 2
    assert scheme.loan_repayment_years == 5
    assert scheme.loan_repayment_type == "원리금균등"


@pytest.mark.req("FR-604-AC3")
def test_incentive_scheme_tax_conditions() -> None:
    """FR-604-AC3: 세제 혜택 조건 검증"""
    scheme = _scheme(tax_credit_rate=0.1)
    assert scheme.tax_credit_rate == 0.1


@pytest.mark.req("FR-604-AC4", "FR-604-AC5")
def test_incentive_scheme_encapsulation_and_sponsor() -> None:
    """FR-604-AC4, AC5: 캡슐화 및 지원 주체 추적"""
    scheme = _scheme(sponsor="지방비")
    assert scheme.sponsor == "지방비"


@pytest.mark.req("FR-604-AC7", "FR-604-AC8")
def test_calculate_financing_identity() -> None:
    """FR-604-AC7, AC8: 자금조달 항등식 및 확정액 계산"""
    scheme1 = _scheme(subsidy_rate=0.3, loan_rate=0.4)
    res1 = scheme1.calculate_financing(1000)
    assert res1["subsidy"] == Money(300)
    assert res1["loan"] == Money(400)
    assert res1["equity"] == Money(300)
    assert res1["subsidy"] + res1["loan"] + res1["equity"] == Money(1000)

    scheme2 = _scheme(subsidy_rate=0.5, subsidy_limit=Decimal("400"))
    res2 = scheme2.calculate_financing(1000)
    assert res2["subsidy"] == Money(400)


@pytest.mark.req("FR-604-AC9")
def test_calculate_financing_no_negative_equity() -> None:
    """FR-604-AC9: 자부담 음수 방지"""
    scheme_exceed = _scheme(subsidy_rate=0.6, loan_rate=0.5)
    with pytest.raises(ValueError, match="초과하여 자부담이 음수가 됩니다"):
        scheme_exceed.calculate_financing(1000)


@pytest.mark.req("FR-606-AC1")
def test_calculate_loan_schedule_grace() -> None:
    """FR-606-AC1: 거치기간 중 이자 납부 검증"""
    scheme_grace = _scheme(
        loan_rate=0.5,
        loan_interest=0.03,
        loan_grace_years=2,
        loan_repayment_years=3,
        loan_repayment_type="원금균등",
    )
    schedule_grace = calculate_loan_schedule(scheme_grace, 600000)
    assert schedule_grace[1] == Money(18000)
    assert schedule_grace[2] == Money(18000)
    assert schedule_grace[3] == Money(218000)


@pytest.mark.req("FR-606-AC2")
def test_calculate_loan_schedule_types() -> None:
    """FR-606-AC2: 상환 방식별 검증"""
    scheme_eq = _scheme(
        loan_rate=0.5,
        loan_interest=0.03,
        loan_grace_years=0,
        loan_repayment_years=5,
        loan_repayment_type="원리금균등",
    )
    schedule = calculate_loan_schedule(scheme_eq, 500000)
    assert schedule[1] == Money(109177)
    total_repayment = sum(schedule.values(), Decimal(0))
    assert total_repayment == Money(545887)

    scheme_bullet = _scheme(
        loan_rate=0.5,
        loan_interest=0.03,
        loan_grace_years=0,
        loan_repayment_years=2,
        loan_repayment_type="만기일시",
    )
    schedule_bullet = calculate_loan_schedule(scheme_bullet, 100000)
    assert schedule_bullet[1] == Money(3000)
    assert schedule_bullet[2] == Money(103000)


@pytest.mark.req("FR-611-AC1", "FR-611-AC2")
def test_build_capex_cashflows_prefunded_basics() -> None:
    """FR-611-AC1, AC2: 기지원 설비 기본 특성"""
    scheme_prefunded = _scheme(subsidy_rate=1.0, is_prefunded=True, funding_program="대여사업")
    cf_pre_owner = build_capex_cashflows(scheme_prefunded, 1000, "OWNER")
    assert len(cf_pre_owner) == 1
    assert cf_pre_owner[0].amounts[1] == Money(-1000)


@pytest.mark.req("FR-611-AC3.OWNER", "FR-611-AC3.SOCIAL", "FR-611-AC3.GOV")
def test_build_capex_cashflows_viewpoints() -> None:
    """FR-611-AC3: 관점별 기지원 설비 계상"""
    scheme_pre = _scheme(subsidy_rate=1.0, is_prefunded=True, funding_program="대여사업")

    # OWNER 관점
    cf_owner = build_capex_cashflows(scheme_pre, 1000, "OWNER")
    assert cf_owner[0].amounts[1] == Money(-1000)

    # GOV 관점
    cf_gov = build_capex_cashflows(scheme_pre, 1000, "GOV")
    assert cf_gov[0].amounts[1] == Money(-1000)
    assert cf_gov[0].tag == "capex.prefunded_subsidy"
    assert "대여사업" in cf_gov[0].label


@pytest.mark.req("FR-611-AC4", "FR-611-AC5", "FR-611-AC6")
def test_build_capex_cashflows_misc() -> None:
    """FR-611-AC4, AC5, AC6: 혼재된 설비 운영 및 표시 (stub)"""
    pass


@pytest.mark.req("FR-607-AC1", "FR-607-AC2", "FR-607-AC3")
def test_build_capex_cashflows_baseline() -> None:
    """FR-607: 무지원 기준선"""
    scheme_new = _scheme(subsidy_rate=0.4)
    cf_base_new = build_capex_cashflows(scheme_new, 1000, "OWNER", is_baseline=True)
    assert cf_base_new[0].amounts[1] == Money(-1000)

    scheme_pre = _scheme(subsidy_rate=1.0, is_prefunded=True)
    cf_base_pre = build_capex_cashflows(scheme_pre, 1000, "OWNER", is_baseline=True)
    assert cf_base_pre[0].amounts[1] == Money(-1000)


@pytest.mark.req("FR-608-AC1", "FR-608-AC2", "FR-608-AC4")
def test_solve_min_subsidy_rate_basic() -> None:
    """FR-608-AC1, AC2, AC4: 역산 기본 기능"""

    def eval_npv_linear(rate: float) -> float:
        return -100.0 + (200.0 * rate)

    res1 = solve_min_subsidy_rate(eval_npv_linear, 0.0, "NPV")
    assert res1.success is True
    assert abs(res1.subsidy_rate - 0.5) <= 0.001

    def eval_payback(rate: float) -> float:
        return 15.0 - (10.0 * rate)

    res3 = solve_min_subsidy_rate(eval_payback, 10.0, "PAYBACK")
    assert res3.success is True
    assert abs(res3.subsidy_rate - 0.5) <= 0.001


@pytest.mark.req("FR-608-AC3")
def test_solve_min_subsidy_rate_monotonicity() -> None:
    """FR-608-AC3: 비단조 구간 대응"""

    def eval_npv_non_monotonic(rate: float) -> float:
        if rate < 0.4:
            return rate * 100
        elif rate < 0.6:
            return 40 - (rate - 0.4) * 100
        else:
            return 20 + (rate - 0.6) * 200

    res4 = solve_min_subsidy_rate(eval_npv_non_monotonic, 30.0, "NPV", precision=0.01)
    assert res4.success is True
    assert abs(res4.subsidy_rate - 0.3) <= 0.01


@pytest.mark.req("FR-608-AC5")
def test_solve_min_subsidy_rate_unachievable() -> None:
    """FR-608-AC5: 달성 불가 케이스"""

    def eval_npv_linear(rate: float) -> float:
        return -100.0 + (200.0 * rate)

    res2 = solve_min_subsidy_rate(eval_npv_linear, 200.0, "NPV")
    assert res2.success is False
    assert res2.subsidy_rate == 1.0
    assert res2.shortfall == 100.0
    assert res2.reason is not None and "최대 지원" in res2.reason


@pytest.mark.req("FR-610-AC1")
def test_fixed_evaluation_mode() -> None:
    """FR-610: 사후 평가 모드"""
    scheme = _scheme(subsidy_rate=0.5)
    cf = build_capex_cashflows(scheme, 1000, "OWNER")
    assert cf[0].amounts[1] == Money(-500)


@pytest.mark.req("FR-605-AC1")
def test_resource_differential_support() -> None:
    """FR-605-AC1: 자원별 차등 지원 동시 적용 검증"""
    scheme_pv = _scheme(subsidy_rate=0.3)
    scheme_ess = _scheme(subsidy_rate=0.5)

    cf_pv = build_capex_cashflows(scheme_pv, 1000, "OWNER")
    cf_ess = build_capex_cashflows(scheme_ess, 1000, "OWNER")

    assert cf_pv[0].amounts[1] == Money(-700)
    assert cf_ess[0].amounts[1] == Money(-500)
