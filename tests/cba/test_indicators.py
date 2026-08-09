"""10.4 — 13종 지표 중 metrics 대조(10.3) 가 담당하지 않는 종류.

여기서 다루는 것:
- ``lcoe-resource`` (순위 1, 자원별)
- ``lcoe-mixed`` **음성 케이스** — 값이 나오면 실패 (FR-703-AC1.lcoe-mixed)
- ``mirr-order`` **조건부 표시 규칙** — 값이 아니다 (FR-703-AC1.mirr-order)
- ``payback-simple``, ``household-saving``, ``self-consumption``,
  ``supply-duty``, ``fiscal-pv``

음성 케이스와 표시 규칙이 «나머지 11종» 과 검증 형태가 다르다 (브리프 10.4).
"""
from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest

from core.cba import (
    fiscal_pv,
    household_saving,
    lcoe_mixed,
    lcoe_resource,
    mirr_preferred_over_irr,
    payback_simple,
    self_consumption_rate,
    supply_duty_rate,
)
from core.cba.proforma import benefit_row
from core.contracts.units import Money

# ── lcoe-resource — 자원별 LCOE (순위 1) ──────────────────────────────────

@pytest.mark.req("FR-703-AC1.lcoe-resource")
def test_lcoe_resource_total_cost_over_generation() -> None:
    """LCOE(자원별) = 총비용 현가 / 총발전량. **발전 자원만**.

    오라클: 순위 1 (단순 나눗셈). 10M 원 / 100,000 kWh = 100 원/kWh.
    """
    val = lcoe_resource(Money(10_000_000), 100_000.0)
    assert val == Decimal("100")


def test_lcoe_resource_zero_generation_returns_none() -> None:
    """발전량 0 → None (정의 불가)."""
    assert lcoe_resource(Money(1_000_000), 0.0) is None


# ── lcoe-mixed — 음성 케이스 (값이 나오면 실패) ──────────────────────────

@pytest.mark.req("FR-703-AC1.lcoe-mixed")
def test_lcoe_mixed_never_returns_a_value() -> None:
    """혼합 모델 전체 LCOE — **산출하지 않는다** (음성 케이스).

    오라클: 순위 4 (§13.0.1 ④ — 검사가 무언가를 검사했는가). 값이 나오면 실패다.
    분모 정의가 성립하지 않으므로 (v0.3 정정) None 만 정상.
    «분모를 명시하면 낼 수 있다» 는 우회로는 v1.6 에서 닫혔다.
    """
    lcoe: Callable[[], object | None] = lcoe_mixed
    result = lcoe()
    assert result is None, (
        "lcoe_mixed 가 값을 반환했다 — 혼합 모델 LCOE 는 산출하지 않는다 (v0.3 정정). "
        "«분모를 명시하면 낼 수 있다» 는 우회로는 닫혔다"
    )


# ── mirr-order — 조건부 표시 규칙 (값이 아니다) ──────────────────────────

@pytest.mark.req("FR-703-AC1.mirr-order")
def test_mirr_order_preferred_when_multiple_sign_changes() -> None:
    """현금흐름 부호변경이 2회 이상 → MIRR 을 IRR 보다 우선 표시.

    오라클: 순위 4 (정의 항등식). 부호변경 2회 → True. IRR 은 복수해 가질 수 있다.
    """
    # - + - + → 부호변경 3회 → True
    assert mirr_preferred_over_irr([-100.0, 50.0, -30.0, 80.0]) is True


def test_mirr_order_not_preferred_for_simple_cash_flow() -> None:
    """부호변경 1회(표준 - initial + benefits) → MIRR 우선 아니다.

    오라클: 순위 4. [-100, +30, +30, +30] → 부호변경 1회 → False.
    """
    assert mirr_preferred_over_irr([-100.0, 30.0, 30.0, 30.0]) is False


# ── payback-simple — 단순 회수기간 ─────────────────────────────────────────

@pytest.mark.req("FR-703-AC1.payback-simple")
def test_payback_simple_no_discount() -> None:
    """단순 회수기간 — 할인 없이 누적 0 도달.

    오라클: 순위 1. initial=1,000,000, 매년 300,000 → 3.333 년.
    """
    flow = benefit_row(tag="B", schedule={y: 300_000 for y in range(1, 6)})
    val = payback_simple(Money(1_000_000), [flow])
    # Y3 누적 -100, Y4 누적 +200 → 3 + 100/300 = 3.333
    expected = 3 + 100_000 / 300_000
    assert val == pytest.approx(expected, rel=1e-4)


# ── household-saving — 가구당 월 절감액 (순위 1) ──────────────────────────

@pytest.mark.req("FR-703-AC1.household-saving")
def test_household_saving_annual_over_12_months_over_households() -> None:
    """가구당 월 절감액 = 연간 절감 / 12 / 가구 수.

    오라클: 순위 1. 1,200,000 원/년 / 12 / 10 가구 = 10,000 원/호·월.
    """
    val = household_saving(Money(1_200_000), household_count=10)
    assert int(val) == 10_000


def test_household_saving_rejects_zero_households() -> None:
    """가구 수 0 → 정의 불가 — 거부."""
    with pytest.raises(ValueError, match="가구 수는 1 이상"):
        household_saving(Money(1_200_000), household_count=0)


# ── self-consumption — 자가소비율 (순위 1) ─────────────────────────────────

@pytest.mark.req("FR-703-AC1.self-consumption")
def test_self_consumption_rate_ratio() -> None:
    """자가소비율 = 자가소비 / 총발전. 0~1 소수.

    오라클: 순위 1. 600/1000 = 0.6.
    """
    assert self_consumption_rate(600.0, 1000.0) == pytest.approx(0.6)


def test_self_consumption_zero_generation_is_zero() -> None:
    """발전량 0 → 자가소비율 0 (정의 불가)."""
    assert self_consumption_rate(0.0, 0.0) == 0.0


# ── supply-duty — 우선공급 의무 충족률 ─────────────────────────────────────

@pytest.mark.req("FR-703-AC1.supply-duty")
def test_supply_duty_rate_clamped_to_01() -> None:
    """충족률 = 초과발전 / 의무량. 0~1 로 클램프.

    오라클: 순위 1. 700/1000 = 0.7. **현행 기준값 70% 는 규제 프로파일 소관**.
    """
    assert supply_duty_rate(700.0, 1000.0) == pytest.approx(0.7)
    assert supply_duty_rate(1500.0, 1000.0) == 1.0  # 초과 → 1.0
    assert supply_duty_rate(-100.0, 1000.0) == 0.0  # 음수 → 0.0


# ── fiscal-pv — 정부 재정 부담 현가 ────────────────────────────────────────

@pytest.mark.req("FR-703-AC1.fiscal-pv")
def test_fiscal_pv_sums_components() -> None:
    """정부 재정 부담 = 직접 보조금 + 이차보전 현가 + 기타.

    오라클: 순위 1. 1,000,000 + 200,000 + 50,000 = 1,250,000.
    **타 사업 국비는 제외** (FR-704-AC6 — 본 사업 국비만).
    """
    val = fiscal_pv(
        direct_subsidy_won=Money(1_000_000),
        loan_interest_subsidy_pv_won=Money(200_000),
        other_fiscal_cost_pv_won=Money(50_000),
    )
    assert int(val) == 1_250_000
