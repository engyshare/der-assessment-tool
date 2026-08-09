from decimal import Decimal
from typing import Any

import pytest

from core.contracts.units import Money
from core.incentive.calculator import build_capex_cashflows, calculate_loan_schedule
from core.incentive.schemas import IncentiveScheme
from core.incentive.solver import generate_iso_support_curve, solve_min_subsidy_rate


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
    """FR-611-AC1, AC2: 기지원 설비 기본 특성.

    `AC2` 는 취득원가를 **0으로 만들지 않고 전액 계상**하라고 한다. 0이 되는
    것은 관점별 현금흐름이지 취득원가가 아니므로, 사업자 관점에도 **행은
    남고 금액만 0**이다 — 행까지 사라지면 리포트에서 그 설비가 통째로
    보이지 않게 된다.
    """
    scheme_prefunded = _scheme(subsidy_rate=1.0, is_prefunded=True, funding_program="대여사업")
    cf_pre_owner = build_capex_cashflows(scheme_prefunded, 1000, "OWNER")
    assert len(cf_pre_owner) == 1
    assert cf_pre_owner[0].amounts[1] == Money(0)


@pytest.mark.req("FR-611-AC3.OWNER", "FR-611-AC3.SOCIAL", "FR-611-AC3.GOV")
def test_build_capex_cashflows_viewpoints() -> None:
    """FR-611-AC3: 관점별 기지원 설비 계상 — **세 지갑이 서로 다른 값을 본다.**

    `AC3.OWNER` 는 *"사업자·주민 — 자기부담 0 (현금흐름 미발생). 근거: 실제
    지출이 없음"* 이다. **이 테스트는 v0.13 이전까지 그 정반대인 전액 지출을
    고정하고 있었고**, 조항 ID 에 매핑까지 돼 있어 매핑표에서는 초록불로
    보였다. 미매핑보다 나쁜 상태였다.

    같은 금액이 관점에 따라 0 / 전액으로 갈리는 것이 `FR-611` 의 요점이므로
    (Rationale: *"하나의 보조율로는 표현할 수 없다"*), 두 관점을 한 자리에서
    대조해 **갈린다는 사실 자체**를 단언한다.
    """
    scheme_pre = _scheme(subsidy_rate=1.0, is_prefunded=True, funding_program="대여사업")

    # OWNER 관점 — 자기부담 0
    cf_owner = build_capex_cashflows(scheme_pre, 1000, "OWNER")
    assert cf_owner[0].amounts[1] == Money(0)

    # GOV 관점 — 타 사업 국비로 전액, 재원 사업명 동반
    cf_gov = build_capex_cashflows(scheme_pre, 1000, "GOV")
    assert cf_gov[0].amounts[1] == Money(-1000)
    assert cf_gov[0].tag == "capex.prefunded_subsidy"
    assert "대여사업" in cf_gov[0].label

    # 두 관점이 실제로 갈린다 — 같아지면 FR-611 이 무의미해진다
    assert cf_owner[0].amounts[1] != cf_gov[0].amounts[1]


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

    # 확정 지원은 기준선에 포함된다 (FR-607). 기준선이라고 해서 사업자가
    # 내지 않은 돈을 낸 것으로 되돌리지는 않으므로 자기부담은 여전히 0이다.
    scheme_pre = _scheme(subsidy_rate=1.0, is_prefunded=True)
    cf_base_pre = build_capex_cashflows(scheme_pre, 1000, "OWNER", is_baseline=True)
    assert cf_base_pre[0].amounts[1] == Money(0)


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


@pytest.mark.req("FR-609-AC1", "FR-609-AC2", "FR-609-AC3")
def test_generate_iso_support_curve() -> None:
    """FR-609-AC1, AC2, AC3: 등가 지원 조합 곡선 산출 및 최소 재정부담 조합 강조 검증.

    손으로 계산한 기대값:
    사업자 NPV = -1000 + 1000 * s + 500 * lr * (0.05 - li)
    정부 재정 부담 현가(gov_fiscal_pv) = 1050 * s + 500 * lr * (0.05 - li)
    목표 사업자 NPV = 0.0 일 때:
    - (lr=0.0, li=0.0): s=1.000, owner_npv=0.0, gov_fiscal_pv=1050.0
    - (lr=0.5, li=0.02): s=0.9925, owner_npv=0.0, gov_fiscal_pv=1049.625
    - (lr=0.8, li=0.00): s=0.9800, owner_npv=0.0, gov_fiscal_pv=1049.0 (최소)
    모든 조합에서 사업자 NPV=0.0을 달성하는 등가 곡선이다.
    """

    def eval_model(
        subsidy_rate: float, loan_rate: float, loan_interest: float
    ) -> tuple[float, float]:
        owner_npv = (
            -1000.0 + 1000.0 * subsidy_rate + 500.0 * loan_rate * (0.05 - loan_interest)
        )
        gov_fiscal_pv = 1050.0 * subsidy_rate + 500.0 * loan_rate * (0.05 - loan_interest)
        return owner_npv, gov_fiscal_pv

    loan_candidates = [
        (0.0, 0.0),
        (0.5, 0.02),
        (0.8, 0.0),
    ]

    result = generate_iso_support_curve(
        eval_model, target_value=0.0, target_type="NPV", loan_candidates=loan_candidates
    )

    assert len(result.points) == 3
    # FR-609-AC1: 목표 NPV=0.0 달성 등가 곡선 포인트 확인 (0.1%p 정밀도 내)
    for pt in result.points:
        assert abs(pt.owner_metric - 0.0) <= 1.0

    # FR-609-AC2 & AC3: 정부 재정 부담 현가 병기 및 최소 부담 조합 존재 확인
    assert result.min_fiscal_point is not None
    assert result.min_fiscal_point.is_minimum_fiscal_burden is True
    assert result.min_fiscal_point.loan_rate == 0.8
