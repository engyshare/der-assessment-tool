"""8.1 — 편익 6종 산식 케이스. 이 파일이 편익 산식의 소유자다.

각 편익의 산식(FR-401-AC2.*)을 닫힌 형태(해석해)로 손계산해 기대값을 만들고,
그것과 구현을 비교한다.

**오라클 순위 1 (해석해)** — 모든 산식이 곱셈·뺄셈 한두 번이므로 손계산으로
완전 재현 가능하다. 금액은 원 단위 완전 일치로 판정한다.
"""
from __future__ import annotations

import pytest

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.valuestream import Payer, ValueStream
from core.valuestream import (
    REC,
    DirectTrade,
    DistributedBenefit,
    DistributedSubItems,
    HeatCostSaving,
    PeakShaving,
    SelfConsumption,
    SurplusSale,
)


def _dispatch_electric(values: list[float]) -> DispatchResult:
    """electric 계열만 채운 DispatchResult. 다른 매체는 0."""
    zeros = [0.0] * len(values)
    return DispatchResult(
        electric=list(values),
        heat=list(zeros),
        cool=list(zeros),
        fuel=list(zeros),
    )


# ── SelfConsumption ──────────────────────────────────────────────────────

@pytest.mark.req("FR-401-AC1", "FR-401-AC2.SelfConsumption")
def test_self_consumption_baseline_minus_new() -> None:
    """자가소비 절감 = 기존요금 − 신규요금.

    오라클: 순위 1 (해석해). 기존 300만 − 신규 120만 = 180만 원.
    """
    vs = SelfConsumption(baseline_annual_bill_won=3_000_000, new_annual_bill_won=1_200_000)
    val = vs.annual_value(_dispatch_electric([0.0] * 8760), year=1)
    assert val == to_won(1_800_000)
    assert isinstance(val, Money)


def test_self_consumption_negative_means_cost_increase() -> None:
    """신규 요금이 더 크면 음수(비용 증가) — 0으로 가두지 않는다.

    오라클: 순위 1. 음수를 0으로 클램프하면 역방향 케이스가 숨는다.
    """
    vs = SelfConsumption(baseline_annual_bill_won=1_000_000, new_annual_bill_won=1_500_000)
    assert vs.annual_value(_dispatch_electric([0.0] * 8760), year=1) == to_won(-500_000)


# ── SurplusSale ──────────────────────────────────────────────────────────

@pytest.mark.req("FR-401-AC2.SurplusSale")
def test_surplus_sale_volume_times_price() -> None:
    """잉여판매 = 잉여량 × 판매단가. 음수(소비)는 잉여가 아니다.

    오라클: 순위 1. [10, -5, 20] → 양수 합 30 kWh × 100원 = 3,000 원.
    """
    vs = SurplusSale(sale_price_won_per_kwh=100.0)
    # electric: 10(잉여), -5(소비→잉여 아님), 20(잉여)
    val = vs.annual_value(_dispatch_electric([10.0, -5.0, 20.0]), year=1)
    assert val == to_won(30 * 100)


def test_surplus_sale_rejects_negative_price() -> None:
    """판매단가 음수는 입력 부호가 바뀐 것 — 거부."""
    with pytest.raises(ValueError, match="음수"):
        SurplusSale(sale_price_won_per_kwh=-50.0)


# ── REC ──────────────────────────────────────────────────────────────────

@pytest.mark.req("FR-401-AC2.REC")
def test_rec_generation_times_weight_times_price() -> None:
    """REC = 발전량 × 가중치 × 단가. 충전(음수)은 REC 대상이 아니다.

    오라클: 순위 1. 1000 kWh × 1.0 × 50,000원 = 50,000,000 원.
    """
    vs = REC(weight=1.0, rec_price_won_per_unit=50_000)
    val = vs.annual_value(_dispatch_electric([1000.0, -100.0, 0.0]), year=1)
    assert val == to_won(1000 * 1.0 * 50_000)


# ── DirectTrade ──────────────────────────────────────────────────────────

@pytest.mark.req("FR-401-AC2.DirectTrade")
def test_direct_trade_spread_times_volume_minus_fee() -> None:
    """직접거래 = (약관 − 직접거래단가) × 거래량 − 수수료.

    오라클: 순위 1. (200 − 150) × 1000 − 5000 = 45,000 원.
    """
    vs = DirectTrade(
        tariff_won_per_kwh=200.0,
        trade_price_won_per_kwh=150.0,
        trade_volume_kwh=1000.0,
        support_fee_won=5000.0,
    )
    val = vs.annual_value(_dispatch_electric([0.0]), year=1)
    assert val == to_won((200 - 150) * 1000 - 5000)


def test_direct_trade_negative_spread_is_loss() -> None:
    """약관 < 직접거래단가면 손실(음수) — 역방향 케이스를 숨기지 않는다.

    오라클: 순위 1.
    """
    vs = DirectTrade(
        tariff_won_per_kwh=100.0,
        trade_price_won_per_kwh=150.0,
        trade_volume_kwh=1000.0,
        support_fee_won=0.0,
    )
    assert vs.annual_value(_dispatch_electric([0.0]), year=1) == to_won(-50_000)


# ── PeakShaving ──────────────────────────────────────────────────────────

@pytest.mark.req("FR-401-AC2.PeakShaving")
def test_peak_shaving_sum_of_monthly_times_charge() -> None:
    """피크절감 = sum(월별 저감 kW) × 기본요금 단가.

    오라클: 순위 1. 12개월 각 1 kW × 5000원 = 60,000 원.
    물리량(kW)이 SelfConsumption(kWh)과 다르므로 동시 계상은 중복 아니다
    (FR-402-AC1, 도메인 원칙 §2 «동시 발생은 중복이 아님»).
    """
    vs = PeakShaving(
        monthly_peak_reduction_kw=[1.0] * 12,
        demand_charge_won_per_kw_month=5000.0,
    )
    assert vs.annual_value(_dispatch_electric([0.0] * 8760), year=1) == to_won(60_000)


def test_peak_shaving_rejects_wrong_month_count() -> None:
    """월별 저감량은 12개월 치 — 다르면 거부."""
    with pytest.raises(ValueError, match="12개월"):
        PeakShaving(
            monthly_peak_reduction_kw=[1.0] * 11,  # 11개
            demand_charge_won_per_kw_month=5000.0,
        )


# ── HeatCostSaving ───────────────────────────────────────────────────────

@pytest.mark.req("FR-401-AC2.HeatCostSaving")
def test_heat_cost_baseline_fuel_minus_hp_electricity() -> None:
    """열비용절감 = 기존 열원 연료비 − 히트펌프 전력비.

    오라클: 순위 1. 200만 − 80만 = 120만 원.
    기준선은 «난방 안 함»이 아니라 «기존 보일러 유지» (도메인 원칙 1-3).
    """
    vs = HeatCostSaving(
        baseline_fuel_cost_won_per_year=2_000_000,
        hp_electricity_cost_won_per_year=800_000,
    )
    assert vs.annual_value(_dispatch_electric([0.0] * 8760), year=1) == to_won(1_200_000)


# ── DistributedBenefit (기본 0) ──────────────────────────────────────────

@pytest.mark.req("FR-401-AC2.DistributedBenefit")
def test_distributed_benefit_default_is_zero() -> None:
    """분산편익 기본 0 — 제도 근거 미확인이면 크기를 추정하지 않는다.

    오라클: 순위 1. 기본값이 0임을 단정. FR-404-AC1~AC3.
    """
    vs = DistributedBenefit()  # sub_items 생략 → 전부 0
    assert vs.annual_value(_dispatch_electric([0.0]), year=1) == to_won(0)


def test_distributed_benefit_sums_sub_items() -> None:
    """하위 항목을 주면 그 합 — 각 항목은 제도 근거가 확인된 값이어야 한다.

    오라클: 순위 1. 100 + 200 + 0 + 0 + 0 = 300 원.
    """
    items = DistributedSubItems(
        transmission_avoidance_won=100.0,
        loss_reduction_won=200.0,
    )
    vs = DistributedBenefit(sub_items=items)
    assert vs.annual_value(_dispatch_electric([0.0]), year=1) == to_won(300)


def test_distributed_benefit_policy_warning_only_when_value() -> None:
    """활성화됐고 값이 있어야 «정책 가정 편익» 경고 대상 (FR-404-AC1).

    오라클: 순위 4 (정책 가정 상태의 정합).
    """
    zero = DistributedBenefit()  # 활성화됐지만 0
    assert not zero.is_policy_assumed()
    valued = DistributedBenefit(sub_items=DistributedSubItems(ghg_reduction_won=10.0))
    assert valued.is_policy_assumed()


# ── Payer 게이트 (FR-402-AC5) ────────────────────────────────────────────

class _UnspecifiedBenefit(ValueStream):
    """테스트용 — 지불 주체가 UNSPECIFIED. 활성화 게이트 검증."""

    tag = "_TestUnspecified"
    #: 검사용 편익 — 창을 읽지 않으므로 연간화 대상이 아니다 (R34 계약).
    scales_with_dispatch_window = False
    payer = Payer.UNSPECIFIED

    def __init__(self, *, enabled: bool = True) -> None:
        super().__init__(name="테스트용 미특정 편익", enabled=enabled)

    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        return to_won(0)

    def formula(self, dispatch: DispatchResult, *, year: int) -> str:
        return "검사용 스텁 0원"


def test_unspecified_payer_rejected_at_activation() -> None:
    """지불 주체 미특정 + 활성화 → 생성 단계에서 ValueError — FR-402-AC5.

    오라클: 순위 4 (계약 정합). 계약 ValueStream.__init__ 이 Q1 을 먼저 잡는다.
    payer_gate.assert_activation_allowed 는 이미 생성된 객체에 대한 4문항
    맥락 노출용이지만, UNSPECIFIED+enabled 는 생성 자체가 거부된다.
    """
    with pytest.raises(ValueError, match="지불 주체"):
        _UnspecifiedBenefit(enabled=True)


def test_disabled_unspecified_constructs_without_error() -> None:
    """비활성 편익은 생성 허용 — 활성화하지 않았으므로 Q1 검사 대상 아니다.

    오라클: 순위 4 (계약 정합). enabled=False 면 UNSPECIFIED 라도 생성된다.
    """
    # 예외 없이 생성되어야 한다
    _UnspecifiedBenefit(enabled=False)
