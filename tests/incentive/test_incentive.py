from decimal import Decimal
from typing import Any

import pytest

from core.contracts.units import Money
from core.incentive.calculator import (
    build_baseline_capex_cashflows,
    build_capex_cashflows,
    build_prefunding_risk_cases,
    calculate_loan_schedule,
)
from core.incentive.schemas import IncentiveScheme
from core.incentive.solver import (
    Goal,
    generate_iso_support_curve,
    solve_min_subsidy_rate,
    solve_min_subsidy_rate_for_goals,
    solve_min_support_variable,
)


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


@pytest.mark.req("FR-604-AC1", "FR-604-AC2")
def test_incentive_scheme_subsidy_forms() -> None:
    """FR-604-AC1, FR-604-AC2: 보조 — 보조율(%)/정액(원)/상한 형태 검증.

    ⚠ 조항 ID 를 **약식(`AC2`)이 아니라 전체**로 적는다 — ③-2 그물은 문면에
    적힌 조항 ID 를 세므로, 약식으로 적으면 `FR-604-AC2` 는 「자기를 안 적고
    이웃(`FR-604-AC1`)만 적는 인용」으로 잡힌다(오탐 ②).
    """
    scheme_rate = _scheme(subsidy_rate=0.4, subsidy_limit=Decimal("400"))
    assert scheme_rate.subsidy_rate == 0.4
    assert scheme_rate.subsidy_limit == Decimal("400")

    scheme_fixed = _scheme(subsidy_fixed=Decimal("600"))
    assert scheme_fixed.subsidy_fixed == Decimal("600")


@pytest.mark.req("FR-604-AC3")
def test_incentive_scheme_loan_conditions() -> None:
    """FR-604-AC3: 융자 — 융자율·연이자율·거치기간·상환기간·상환방식 검증"""
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


@pytest.mark.req("FR-604-AC4")
def test_incentive_scheme_equity_share_is_automatic_residual() -> None:
    """FR-604-AC4: 자부담 — 잔여 비율 자동 계산.

    조항 문면은 *「자부담: 잔여 비율 자동 계산」* 이다. 형제 조항이 재는 것과
    겹치지 않는 몫이 무엇인지부터 못박는다 — AC7 은 **합이 총사업비와 같은가**,
    AC8 은 **보조 확정액 산식**, AC9 는 **음수 불가**를 잰다. AC4 가 요구하는
    것은 그 셋 중 어느 것도 아닌 **「자부담은 사람이 주는 값이 아니라 남는
    몫으로 저절로 나온다」** 이다. 그래서 셋을 잰다.

    ① **자부담은 입력이 아니다** — `IncentiveScheme` 에 자부담을 선언할 필드가
       없다. 있으면 「자동 계산」이 아니라 사람이 적어 넣는 값이 된다.

    ② **잔여 「비율」이다 — 규모에 불변이다.**
       손계산: 잔여 비율 = 1 − 보조율 − 융자율 = 1 − 0.30 − 0.40 = **0.30**
               1,000,000 × 0.30 = 300,000 원
               2,500,000 × 0.30 = 750,000 원
       총사업비가 2.5배가 되어도 **같은 비율**이 나오는 것이 「비율」의 실물이다.

    ③ **「자동」의 실물 — 선언한 비율이 아니라 확정액을 따라간다.**
       보조 상한이 걸리면 잔여 비율은 선언한 보조율로 계산되지 않는다.
       손계산: 보조 확정액 = min(1,000,000 × 0.50, 400,000) = **400,000**
               융자 확정액 = 1,000,000 × 0.40 = 400,000
               자부담     = 1,000,000 − 400,000 − 400,000 = **200,000**
               잔여 비율  = 200,000 / 1,000,000 = **0.20**
       선언한 비율로 셈하면 1 − 0.50 − 0.40 = 0.10 (100,000원)이 되어 **틀린다.**
       spec 이 *「검증은 비율이 아니라 금액 기준으로 수행한다 … 정액 보조·보조
       상한이 있으면 비율 합계가 100%가 되지 않기 때문이다 (DV-1)」* 로 적은
       그 갈래이며, 이 갈래를 눌러야 자부담이 **확정액에서 자동으로** 나오는
       것이 보인다.

    부르는 구현: `IncentiveScheme.calculate_financing()`
    (`core/incentive/schemas.py` — `equity = capex − subsidy − loan`)
    """
    # ① 자부담은 선언할 수 있는 필드가 아니다 — 남는 몫으로만 나온다
    declarable = set(IncentiveScheme.model_fields)
    assert not [f for f in declarable if "equity" in f or "self_burden" in f], (
        f"자부담이 선언 가능한 필드로 있으면 「자동 계산」이 아니다: {sorted(declarable)}"
    )

    # ② 잔여 비율 = 1 − 0.30 − 0.40 = 0.30 — 총사업비 규모가 달라져도 같다
    scheme = _scheme(subsidy_rate=0.3, loan_rate=0.4)
    small = scheme.calculate_financing(1_000_000)
    large = scheme.calculate_financing(2_500_000)
    assert small["equity"] == Money(300_000)
    assert large["equity"] == Money(750_000)
    assert small["equity"] / Decimal(1_000_000) == Decimal("0.30")
    assert large["equity"] / Decimal(2_500_000) == Decimal("0.30")

    # ③ 상한이 걸리면 잔여는 선언한 보조율(0.50)이 아니라 확정액(400,000)을 따른다
    capped = _scheme(subsidy_rate=0.5, subsidy_limit=Decimal("400000"), loan_rate=0.4)
    res = capped.calculate_financing(1_000_000)
    assert res["subsidy"] == Money(400_000)
    assert res["equity"] == Money(200_000), (
        "선언한 비율(1 - 0.50 - 0.40 = 0.10 -> 100,000원)이 아니라 "
        "확정액에서 자동으로 나온 잔여(200,000원)여야 한다"
    )
    assert res["equity"] / Decimal(1_000_000) == Decimal("0.20")


@pytest.mark.req("FR-604-AC5")
def test_incentive_scheme_tax_conditions() -> None:
    """FR-604-AC5: 세제 — 세액공제율 검증"""
    scheme = _scheme(tax_credit_rate=0.1)
    assert scheme.tax_credit_rate == 0.1


@pytest.mark.req("FR-604-AC6")
def test_incentive_scheme_encapsulation_and_sponsor() -> None:
    """FR-604-AC6: 지원 주체 — 국비/지방비/민간 추적"""
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
    scheme_prefunded = _scheme(
        subsidy_rate=1.0,
        is_prefunded=True,
        funding_program="대여사업",
        prefunded_status="확정 지원",
    )
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
    scheme_pre = _scheme(
        subsidy_rate=1.0,
        is_prefunded=True,
        funding_program="대여사업",
        prefunded_status="확정 지원",
    )

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


@pytest.mark.req("FR-611-AC3.SOCIAL")
def test_build_capex_cashflows_social_viewpoint_differs_from_owner_and_gov_when_prefunded() -> None:
    """FR-611-AC3.SOCIAL: 기지원 설비 — 사회 관점은 **전액**을 비용으로 본다.

    조항 원문: *"사회 — 전액 비용. 근거: 재원이 어디서 왔든 자원은 소모됨"*
    (분산자원 경제성 평가 원칙 2-3 관점 분리).

    손계산 오라클(취득가 1,000원, 기지원 확정):
    - SOCIAL = **-1,000원** (AC2 「전액 계상」과 같은 금액 — 관점이 취득가
      자체를 바꾸지 않는다)
    - OWNER = 0원 (자기부담 없음) → SOCIAL 과 **다르다**
    - GOV = -1,000원(「타 사업 국비」 메모 행) — 이 경우 금액은 SOCIAL 과
      같지만(둘 다 취득가 전액을 가리키므로), **의미가 다른 별개 행**이다
      (GOV 는 본 사업 재정부담에서 제외된 타 사업 지출의 메모이고, SOCIAL 은
      사회 전체가 실제로 소모한 자원의 총비용이다). `tag` 로 구분한다.
    """
    scheme_pre = _scheme(
        subsidy_rate=1.0,
        is_prefunded=True,
        funding_program="대여사업",
        prefunded_status="확정 지원",
    )

    cf_social = build_capex_cashflows(scheme_pre, 1000, "SOCIAL")
    cf_owner = build_capex_cashflows(scheme_pre, 1000, "OWNER")
    cf_gov = build_capex_cashflows(scheme_pre, 1000, "GOV")

    assert cf_social[0].amounts[1] == Money(-1000)
    assert cf_owner[0].amounts[1] == Money(0)
    assert cf_social[0].amounts[1] != cf_owner[0].amounts[1]

    assert cf_social[0].tag != cf_gov[0].tag, (
        "SOCIAL과 GOV의 금액이 같더라도(둘 다 취득가 전액) 서로 다른 관점의 "
        "행이므로 태그가 같으면 리포트에서 두 관점이 뒤섞인다"
    )


@pytest.mark.req("FR-611-AC3.SOCIAL")
def test_build_capex_cashflows_social_viewpoint_books_full_cost_even_without_prefunding() -> None:
    """FR-611-AC3.SOCIAL: **비**기지원 설비에서도 사회 관점은 재원 구성과 무관하게
    취득가 전액을 비용으로 본다.

    손계산 오라클(취득가 1,000원, 보조율 30%, 융자 0%):
    - 자금조달 항등식(FR-604-AC7): 보조금 300원 + 융자 0원 + 자부담 700원 = 1,000원
    - SOCIAL = **-1,000원** — 재원이 보조금·자부담 어느 쪽이든 자원 자체가
      소모된 값은 변하지 않는다 (원칙 2-3)
    - OWNER = -700원 (자부담만) → SOCIAL 과 **다르다**
    - GOV = -300원 (본 사업 보조금만) → SOCIAL 과 **다르다**

    기지원 케이스만 보면 「SOCIAL=전액」이 우연히 다른 계상과 일치하는 특수
    사례로 보일 수 있다 — 재원 구성이 섞인 이 케이스가 그것이 아님을 보인다.
    """
    scheme_new = _scheme(subsidy_rate=0.3)

    cf_social = build_capex_cashflows(scheme_new, 1000, "SOCIAL")
    cf_owner = build_capex_cashflows(scheme_new, 1000, "OWNER")
    cf_gov = build_capex_cashflows(scheme_new, 1000, "GOV")

    assert cf_social[0].amounts[1] == Money(-1000)
    assert cf_owner[0].amounts[1] == Money(-700)
    assert cf_gov[0].amounts[1] == Money(-300)
    assert cf_social[0].amounts[1] != cf_owner[0].amounts[1]
    assert cf_social[0].amounts[1] != cf_gov[0].amounts[1]


@pytest.mark.req("FR-611-AC4")
def test_build_prefunding_risk_cases_add_support_failure_variant_for_planned_support() -> None:
    """FR-611-AC4: `지원 예정`은 미확정 리스크이므로 **병기 케이스**를 함께 만든다.

    손계산 오라클:
    - 본 케이스(지원 도착 가정): 사업자 초기투자비 = **0원**
    - 병기 케이스(지원 무산): **해당 설비 제외** 이므로 CAPEX 행 자체가 **없다**

    0원이 아니라 **행 없음**이어야 하는 이유:
    0원 행을 남기면 설비는 있는 것으로 보이는데 비용만 0원이어서, AC4가 요구한
    "해당 설비를 제외한 케이스"가 아니다.
    """
    scheme_planned = _scheme(
        subsidy_rate=1.0,
        is_prefunded=True,
        funding_program="대여사업",
        prefunded_status="지원 예정",
    )

    cases = build_prefunding_risk_cases(scheme_planned, 1000, "OWNER")

    assert len(cases.current_rows) == 1
    assert cases.current_rows[0].amounts[1] == Money(0)
    assert cases.support_failure_rows == ()
    assert cases.support_failure_note == "지원 무산 시 회수기간은 해당 설비 제외 케이스로 병기"


@pytest.mark.req("FR-607-AC1", "FR-607-AC2", "FR-607-AC3")
def test_build_capex_cashflows_baseline() -> None:
    """FR-607: 무지원 기준선 — 확정 기지원은 포함, 지원 예정은 제외.

    손계산 오라클:
    - 신규 설비: 본 사업 지원 0 → 사업자 CAPEX **-1,000원**
    - 확정 기지원: 기준선 포함된 소여 → 사업자 현금흐름 **0원**
    - 지원 예정: 기준선 제외 → **행 없음**

    `is_baseline` 깃발은 사라졌다 — 기준선 판정은 `build_baseline_
    capex_cashflows()` 라는 별개 함수의 책임이다 (R21 WP-31B).
    """
    scheme_new = _scheme(subsidy_rate=0.4)
    cf_base_new = build_baseline_capex_cashflows(scheme_new, 1000, "OWNER")
    assert cf_base_new[0].amounts[1] == Money(-1000)

    # 확정 지원은 기준선에 포함된다 (FR-607). 기준선이라고 해서 사업자가
    # 내지 않은 돈을 낸 것으로 되돌리지는 않으므로 자기부담은 여전히 0이다.
    scheme_pre = _scheme(subsidy_rate=1.0, is_prefunded=True, prefunded_status="확정 지원")
    cf_base_pre = build_baseline_capex_cashflows(scheme_pre, 1000, "OWNER")
    assert cf_base_pre[0].amounts[1] == Money(0)

    scheme_planned = _scheme(subsidy_rate=1.0, is_prefunded=True, prefunded_status="지원 예정")
    cf_base_planned = build_baseline_capex_cashflows(scheme_planned, 1000, "OWNER")
    assert cf_base_planned == []


# ⚠ **마커 오기를 R26 에 고쳤다.** 이 테스트는 `FR-608-AC4`(「해가 없으면 그
# 사실과 부족분을 명시」)를 인용하고 있었으나 **AC4 를 검사하지 않는다** — 해가
# 있는 경우만 본다. AC4 를 검사하는 것은 아래 `..._unachievable` 이고, 그쪽은
# 반대로 `FR-608-AC5`(역산 대상 변수 확장)를 인용하고 있었다. 둘이 서로 남의
# 조항을 달고 있었고, `core/incentive/solver.py` 의 주석도 같은 오기였다.
@pytest.mark.req("FR-608-AC1", "FR-608-AC2")
def test_solve_min_subsidy_rate_basic() -> None:
    """FR-608-AC1(택일)·AC2: 목표 3종을 각각 역산한다.

    ★ **`IRR` 갈래는 R26 까지 한 번도 실행되지 않았다.** 조항이 열거한 목표는
    셋(`NPV`·`IRR`·`PAYBACK`)인데 검사는 둘만 지났고, 그동안 `is_met` 의 IRR
    분기가 부등호를 뒤집어도 아무것도 빨간불이 되지 않았다.
    """

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

    # ★ IRR — 조항 예시가 「IRR ≥ 5%」다. 손계산: 지원율 r 에서 IRR = 10r 이면
    # 5% 를 넘기는 최소 r 은 0.5 다. NPV 와 **같은 방향**(클수록 좋다)이므로
    # `is_met` 이 PAYBACK 쪽 부등호를 쓰면 답이 0.0 으로 나온다.
    def eval_irr(rate: float) -> float:
        return 10.0 * rate

    res_irr = solve_min_subsidy_rate(eval_irr, 5.0, "IRR")
    assert res_irr.success is True
    assert abs(res_irr.subsidy_rate - 0.5) <= 0.001, (
        f"IRR 목표의 최소 지원율이 0.5 여야 합니다: {res_irr.subsidy_rate}"
    )


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


@pytest.mark.req("FR-608-AC4")
def test_solve_min_subsidy_rate_unachievable() -> None:
    """FR-608-**AC4**: 해가 없으면 그 사실과 **부족분**을 명시한다.

    (마커가 `AC5` 로 적혀 있었다 — R26 정정. AC5 는 역산 대상 변수 확장이며
    이 테스트와 무관하다. `..._basic` 과 서로 남의 조항을 달고 있었다.)
    """

    def eval_npv_linear(rate: float) -> float:
        return -100.0 + (200.0 * rate)

    res2 = solve_min_subsidy_rate(eval_npv_linear, 200.0, "NPV")
    assert res2.success is False
    assert res2.subsidy_rate == 1.0
    assert res2.shortfall == 100.0
    assert res2.reason is not None and "최대 지원" in res2.reason


# ── FR-608-AC1 후반부 — 목표 「복수」 ────────────────────────────────────


@pytest.mark.req("FR-608-AC1")
def test_multiple_goals_take_the_binding_one() -> None:
    """★ 복수 목표의 답은 **각 목표 최소 해의 최댓값**이고, 무엇이 구속했는지 말한다.

    손계산 오라클:
        NPV ≥ 0       NPV = -100 + 200r  →  200r ≥ 100  →  최소 r = 0.50
        회수기간 ≤ 8  PB  = 15 - 10r     →  10r  ≥ 7    →  최소 r = 0.70
    둘 다 만족하는 최소 지원율은 **0.70** 이고 구속하는 것은 회수기간이다.

    **최댓값이 아니라 최솟값·평균을 쓰면 답이 0.50 이나 0.60 이 되고, 그 값에서
    회수기간 목표는 충족되지 않는다** — 그래도 「해를 찾았다」로 보인다.
    """
    goals = [
        Goal(lambda r: -100.0 + 200.0 * r, 0.0, "NPV", label="NPV≥0"),
        Goal(lambda r: 15.0 - 10.0 * r, 8.0, "PAYBACK", label="회수기간≤8년"),
    ]

    result = solve_min_subsidy_rate_for_goals(goals)

    assert result.success is True
    assert abs(result.subsidy_rate - 0.7) <= 0.001
    assert result.binding_label == "회수기간≤8년", (
        "어느 목표가 답을 결정했는지 말해야 한다 — 그것이 없으면 지원율을 "
        f"낮출 때 무엇을 완화해야 할지 알 수 없다: {result.binding_label!r}"
    )

    # 구속하지 않는 목표만 남기면 답이 내려간다 — 위 0.70 이 「둘 다」에서 온
    # 값이지 목표 하나에서 온 우연이 아님을 보인다
    only_npv = solve_min_subsidy_rate_for_goals([goals[0]])
    assert abs(only_npv.subsidy_rate - 0.5) <= 0.001


@pytest.mark.req("FR-608-AC1")
@pytest.mark.req("FR-608-AC4")
def test_multiple_goals_name_the_unreachable_one() -> None:
    """하나라도 100%로 달성 불가하면 전체 실패이고 **그 목표를 지목한다.**

    「어딘가 안 된다」로는 무엇을 고쳐야 할지 알 수 없다.
    """
    goals = [
        Goal(lambda r: -100.0 + 200.0 * r, 0.0, "NPV", label="NPV≥0"),
        Goal(lambda r: 15.0 - 10.0 * r, 1.0, "PAYBACK", label="회수기간≤1년"),
    ]

    result = solve_min_subsidy_rate_for_goals(goals)

    assert result.success is False
    assert result.binding_label == "회수기간≤1년"
    assert result.shortfall is not None
    assert "회수기간≤1년" in (result.reason or "")


# ── FR-608-AC5 — 역산 대상 변수를 보조율 외로도 지정 ──────────────────────
#
# ⚠ **이 조항은 R27 까지 붙드는 테스트가 없었다.** 있던 것은
# `..._unachievable` 의 `FR-608-AC5` 마커뿐이고 그 테스트는 AC4(해 없음)를
# 검사한다 — 즉 **유일한 매핑이 거짓이었다.** 마커를 바로잡자
# `test_dod9_phase_1_musthave_unmapped_zero` 가 빨간불이 되어 그 사실이
# 드러났다. R20 이 「마커를 지우면 DoD 9 가 빨간불」이라 적어 둔 자리와 같은
# 형태이며, 그때와 달리 이번에는 조항을 **구현해서** 닫는다.


@pytest.mark.req("FR-608-AC5")
def test_other_support_variables_can_be_solved_and_are_named() -> None:
    """보조율 외 변수도 역산하고, **어느 변수였는지 결과가 말한다.**

    손계산 오라클: 융자금리를 x 로 두었을 때 NPV = -100 + 200x 이면 NPV ≥ 0 인
    최소 x 는 0.5 다(보조율 예시와 같은 식 — 탐색은 변수에 무관하다는 것이
    요점이므로 식을 일부러 같게 둔다).

    ★ **변수 이름이 결과에 남아야 한다.** `SolverResult` 의 필드는
    `subsidy_rate` 라서, 거기에 융자금리를 담으면 표시 층이 그것을 보조율로
    읽는다 — 값은 맞는데 뜻이 틀린 상태가 되고 아무 예외도 나지 않는다.
    """
    def eval_npv(x: float) -> float:
        return -100.0 + 200.0 * x

    result = solve_min_support_variable(
        eval_npv, 0.0, "NPV", variable="loan_interest_rate"
    )

    assert result.success is True
    assert abs(result.value - 0.5) <= 0.001
    assert result.variable == "loan_interest_rate", (
        "어느 변수를 역산했는지 결과에 없다 — 표시 층이 보조율로 읽게 된다"
    )


@pytest.mark.req("FR-608-AC5")
def test_the_four_named_variables_are_all_accepted() -> None:
    """조항이 **이름으로 세운 넷**이 전부 받아들여진다.

    하나만 확인하면 나머지 셋이 빠져 있어도 통과한다 — 조항은 넷을 열거한다
    (융자금리·거치기간·직접거래단가·REC단가).
    """
    def eval_npv(x: float) -> float:
        return -100.0 + 200.0 * x

    for variable in (
        "loan_interest_rate",
        "grace_period_years",
        "direct_trade_price",
        "rec_price",
    ):
        result = solve_min_support_variable(
            eval_npv, 0.0, "NPV", variable=variable
        )
        assert result.success is True, variable
        assert result.variable == variable


@pytest.mark.req("FR-608-AC5")
def test_an_unknown_variable_is_refused() -> None:
    """★ 목록 밖 이름은 거부한다 — 열어 두면 오타가 조용히 통과한다.

    `loan_rat` 같은 오타를 받아 답을 돌려주면 그 답은 **아무 변수의 것도
    아니다.** 그런데 값은 그럴듯하고 예외도 나지 않는다.
    """
    with pytest.raises(ValueError, match="역산 대상 변수가 아닙니다"):
        solve_min_support_variable(
            lambda x: x, 0.0, "NPV", variable="loan_rat"
        )


@pytest.mark.req("FR-608-AC1")
def test_no_goals_is_refused() -> None:
    """목표가 비면 역산할 대상이 없다 — 조용히 0.0 을 돌려주지 않는다."""
    with pytest.raises(ValueError, match="목표가 하나도 없습니다"):
        solve_min_subsidy_rate_for_goals([])


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


# ⚠ **`req` 마커에 `DV-N` 을 쓰지 않는다** — R24 인수 정정. `DV-1` 은 §7.3 검증
# 규칙 대장의 ID 이지 **수용기준 ID 가 아니다.** `gen_traceability.py` 가 이 넷을
# *「해당 수용기준이 spec에 없음」* 으로 잡았다(매달린 참조). 이 자리가 인용해야
# 하는 것은 **같은 규칙을 붙드는 기존 테스트가 인용하던 조항**(`FR-604-AC9` —
# 자부담 음수 불가, `test_calculate_financing_no_negative_equity` 와 동일)과
# **구조화 요구**(`NFR-303-M1`)다. 규칙 ID 는 코드의 `rule="DV-1"` 과 그것을
# 붙드는 `tests/contract/test_dv_rule_enforcement.py` 가 나른다.
@pytest.mark.req("FR-604-AC9")
@pytest.mark.req("NFR-303-M1")
def test_dv1_subsidy_plus_loan_exceeds_capex_raises_validation_error() -> None:
    """DV-1: 보조금+융자 합이 총사업비를 초과하면 ValidationError 구조로 던진다.

    NFR-303: 오류 메시지는 «어떤 필드가 / 왜 / 어떻게 고쳐야 하는지»를 제시해야 한다.
    세 금액(보조·융자·총사업비)이 전부 사유에 실려야 하며, 규칙 ID가 있어야 한다.

    기대값 계산: capex=1000, subsidy_rate=0.6 → subsidy=600, loan_rate=0.5 → loan=500
    subsidy+loan=1100 > capex=1000 → 자부담 음수(-100) → 위반
    """
    from core.contracts.validation import ValidationError

    scheme = _scheme(subsidy_rate=0.6, loan_rate=0.5)
    capex = 1000

    with pytest.raises(ValidationError) as caught:
        scheme.calculate_financing(capex)

    parts = caught.value.as_dict()
    assert parts["field"] == "incentivescheme.subsidy_rate_or_loan_rate", (
        "관례에 맞는 키여야 한다"
    )
    assert parts["rule"] == "DV-1", "대장 규칙 ID 가 있어야 한다"

    # 세 금액이 전부 사유에 실려야 한다
    reason = parts["reason"] or ""
    assert "600" in reason or "500" in reason, "보조·융자 금액 중 하나는 사유에 있어야 한다"
    assert "1000" in reason, "총사업비 금액이 사유에 있어야 한다"
    assert "초과" in reason or "자부담" in reason, "어떤 위반인지 명시되어야 한다"

    # 조치가 구체적이어야 한다
    assert (parts["action"] or "").strip(), "조치가 비어 있으면 안 된다"


@pytest.mark.req("FR-604-AC9")
def test_dv1_boundary_case_subsidy_plus_loan_equals_capex_passes() -> None:
    """DV-1: 보조금+융자 합이 총사업비와 같으면 통과한다 (자부담 0).

    대장은 「오차 1원 이내」이므로, 따로 같을 때는 통과해야 한다.
    기대값: capex=1000, subsidy_rate=0.4 → subsidy=400, loan_rate=0.6 → loan=600
    subsidy+loan=1000 == capex=1000 → equity=0 → 통과
    """
    scheme = _scheme(subsidy_rate=0.4, loan_rate=0.6)
    result = scheme.calculate_financing(1000)

    assert result["subsidy"] == 400
    assert result["loan"] == 600
    assert result["equity"] == 0


@pytest.mark.req("FR-604-AC9")
@pytest.mark.req("NFR-303-M1")
def test_dv1_fixed_subsidy_plus_loan_exceeds_capex_raises_validation_error() -> None:
    """DV-1: 정액 보조금 + 융자 초과도 ValidationError 구조로 던진다.

    정액 보조금 케이스에서도 같은 규칙이 적용되어야 한다.
    기대값: capex=1000, subsidy_fixed=700, loan_rate=0.4 → loan=400
    subsidy+loan=1100 > capex=1000 → 위반
    """
    from core.contracts.validation import ValidationError

    scheme = _scheme(subsidy_fixed=Decimal("700"), loan_rate=0.4)

    with pytest.raises(ValidationError) as caught:
        scheme.calculate_financing(1000)

    parts = caught.value.as_dict()
    assert parts["rule"] == "DV-1"
    reason = parts["reason"] or ""
    assert "700" in reason or "1000" in reason, "정액 보조금·총사업비 금액이 사유에 있어야 한다"


@pytest.mark.req("NFR-303-M1")
def test_dv1_validation_error_is_catchable_as_valueerror() -> None:
    """DV-1: ValidationError는 ValueError를 상속하므로 기존 코드가 그대로 받는다.

    tests/incentive/test_incentive.py::test_calculate_financing_no_negative_equity
    가 `pytest.raises(ValueError, match="...")` 로 물려 있고, 그대로 통과해야 한다.
    """
    scheme = _scheme(subsidy_rate=0.6, loan_rate=0.5)

    with pytest.raises(ValueError, match="초과하여 자부담이 음수가 됩니다"):
        scheme.calculate_financing(1000)
