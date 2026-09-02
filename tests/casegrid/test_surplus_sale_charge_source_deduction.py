"""잉여판매 수량의 충전원 차감이 **실행 경로에서** 지켜지는가 — R51/WP-5 · 판정 §4.

`tests/valuestream/test_surplus_sale.py` 는 `SurplusSale` 클래스 하나만 본다.
이 파일은 그 차감량을 **러너가 계산해 실제로 넘기는지**(`core/casegrid/
e2e_runner.py`)와, 그 결과로 `TouArbitrage` 와 `SurplusSale` 이 **더는 배타가
아니라 동시에 켤 수 있는지**를 실행 경로에서 잰다(`status.md` 「함정」 절 —
*「값을 손으로 적으면 동어반복이다」*를 피하려고 값은 항상 러너가 돌려준
운전 결과에서 읽는다).
"""
from __future__ import annotations

from types import MappingProxyType

import pytest

from core.casegrid.e2e_runner import DAYS_PER_YEAR, run_single_case_e2e
from core.casegrid.ledger_levels import design_levels
from core.casegrid.models import CaseOutcome
from core.contracts.units import to_won
from core.der.ess import ESSChargeSource
from core.valuestream import TouArbitrage

_ESS = "e2e-ess"
_SURPLUS_TAG = "SurplusSale"

#: 분석기간 탐침값 — 이 파일의 관심이 아니다(소유자는 `AssumptionSet`).
_PROBE_HORIZON = 18


def _level_map(surplus_sale_price: float) -> dict[str, MappingProxyType[str, float]]:
    """`tests/casegrid/test_surplus_sale_price_wiring.py` 와 같은 최소 수준표다
    — 구매 단가와 판매 단가를 **다른 수**로 고정해 R35 가 없앤 우연한 일치를
    되살리지 않는다."""
    return {
        "pv_unit_cost": MappingProxyType({"base": 1_600_000.0}),
        "ess_unit_cost": MappingProxyType({"base": 400_000.0}),
        "discount_rate": MappingProxyType({"base": 0.045}),
        "grid_purchase_price": MappingProxyType({"base": 100.0}),
        "surplus_sale_price": MappingProxyType({"base": surplus_sale_price}),
        "replacement_real_trend": MappingProxyType({"base": 0.0}),
        "pv_inverter_share": MappingProxyType({"base": 0.11}),
        "demand_charge": MappingProxyType({"base": 7_700.0}),
        "pv_fixed_om": MappingProxyType({"base": 70_000.0}),
        "ess_fixed_om": MappingProxyType({"base": 65_000.0}),
        # ESS 교체 단가 — 러너가 요구한다(R52/WP-6 에 스윕 축으로 올렸다).
        # **대장과 다른 수를 일부러 쓴다.**
        "ess_replacement": MappingProxyType({"base": 350_000.0}),
        **design_levels(),
    }


def _surplus_line_won(outcome: CaseOutcome) -> int:
    lines = [line for line in outcome.basis.benefits if line.tag == _SURPLUS_TAG]
    assert len(lines) == 1, f"잉여판매 편익 항목이 {len(lines)}개다"
    return lines[0].annual_won


def _annualised_won(daily_net_kwh: float, price: float) -> int:
    return int(float(to_won(daily_net_kwh * price)) * DAYS_PER_YEAR)


@pytest.mark.req("FR-401-AC2.SurplusSale")
def test_grid_charge_source_deducts_the_ess_discharge_from_the_surplus_quantity() -> None:
    """★★ 충전원이 `GRID` 이면 잉여판매 수량에서 **그 ESS 의 방전분**이 빠진다.

    ⚠ **같은 실행을 두 충전원으로 돌려 견준다.** 기대 차감량은 이 실행이
    돌려준 운전 결과(`outcome.dispatch.per_resource["e2e-ess"]`)에서 직접
    읽는다 — 리터럴로 적으면 디스패치 규칙이 바뀔 때 이 시험이 조용히
    사본을 검산하게 된다.
    """
    price = 90.0
    level_map = _level_map(price)

    grid_outcome = run_single_case_e2e(
        {}, level_map=level_map, horizon_years=_PROBE_HORIZON,
        ess_charge_source=ESSChargeSource.GRID,
    )
    pv_surplus_outcome = run_single_case_e2e(
        {}, level_map=level_map, horizon_years=_PROBE_HORIZON,
        ess_charge_source=ESSChargeSource.PV_SURPLUS,
    )

    grid_gross_kwh = sum(max(0.0, e) for e in grid_outcome.dispatch.grid_export)
    grid_ess_discharge_kwh = sum(
        v for v in grid_outcome.dispatch.per_resource[_ESS].electric if v > 0.0
    )
    assert grid_ess_discharge_kwh > 0.0, (
        "GRID 충전원인데 ESS 가 방전하지 않았다 — 차감량이 0이라 이 검사가 "
        "무엇을 재는지 알 수 없다"
    )
    expected_grid_net_kwh = grid_gross_kwh - grid_ess_discharge_kwh
    assert expected_grid_net_kwh > 0.0, (
        "차감 후 수량이 0 이하다 — 이 케이스로는 차감이 성립함을 재지 못한다"
    )

    assert _surplus_line_won(grid_outcome) == _annualised_won(expected_grid_net_kwh, price), (
        f"GRID 충전원인데 잉여판매 금액이 (총 역송 {grid_gross_kwh:,.2f} − ESS 방전 "  # noqa: RUF001
        f"{grid_ess_discharge_kwh:,.2f})kWh × 단가로 나오지 않는다"  # noqa: RUF001
    )

    pv_gross_kwh = sum(max(0.0, e) for e in pv_surplus_outcome.dispatch.grid_export)
    assert _surplus_line_won(pv_surplus_outcome) == _annualised_won(pv_gross_kwh, price), (
        "PV_SURPLUS 충전원인데 잉여판매 수량이 총 역송량과 다르다 — 태양광 전력이 "
        "ESS 를 경유한 몫까지 빠졌을 수 있다(판정 §4는 그 몫을 빼지 말라고 한다)"
    )


@pytest.mark.req("FR-402-AC2.E", "FR-401-AC2.TouArbitrage")
def test_tou_arbitrage_and_surplus_sale_can_run_together() -> None:
    """★ `TouArbitrage` 와 `SurplusSale` 을 **동시에 켤 수 있다** — 배타가 아니다.

    R50 은 이 쌍을 유형 A 로 막았다. 판정 §4 는 그것을 「배타로 막으면 정당한
    동시 운전을 지운다」고 답한다 — 그 동시 운전이 실행 경로
    (`assert_no_exclusions`, `run_single_case_e2e` 안)에서 실제로 거부되지
    않음을 잰다(`extra_value_streams` 가 그 진입점이다 — 그 함수 자신의
    독스트링이 배타 검사 전용 인자라고 적는다).
    """
    tou = TouArbitrage(
        discharge_kwh=1_000.0, charge_kwh=1_100.0,
        peak_price_won_per_kwh=180.0, offpeak_price_won_per_kwh=60.0,
    )
    outcome = run_single_case_e2e(
        {},
        level_map=_level_map(90.0),
        horizon_years=_PROBE_HORIZON,
        extra_value_streams=[tou],
    )
    assert "npv" in outcome.metrics
