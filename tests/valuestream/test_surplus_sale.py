"""잉여전력 판매 수량의 **충전원 차감** — FR-401-AC2.SurplusSale (R51/WP-5 · 판정 §4).

`SurplusSale` 의 수량은 종전에 **시스템 총 역송량**이라 누가 내보냈는지를
몰랐다. 사용자 판정 §4(`docs/decisions-2026-09-01-R51.md`)는 충전원이
`GRID` 인 ESS 방전분을 그 수량에서 빼라고 답한다 — `PV_SURPLUS` 충전분은
태양광 전력이 ESS 를 경유한 것이라 빼지 않는다.

이 파일은 **편익 클래스 하나만** 본다(수량 계산 · 거부 · 산식 문면). 그
차감량을 러너가 어떻게 계산해 넘기는지는
`tests/casegrid/test_surplus_sale_charge_source_deduction.py` 가 잰다.
"""
from __future__ import annotations

import pytest

from core.contracts.der import DispatchResult
from core.contracts.units import to_won
from core.contracts.validation import ValidationError
from core.valuestream import SurplusSale


def _dispatch(*electric: float) -> DispatchResult:
    zeros = [0.0] * len(electric)
    return DispatchResult(
        electric=list(electric), heat=list(zeros), cool=list(zeros), fuel=list(zeros)
    )


@pytest.mark.req("FR-401-AC2.SurplusSale")
def test_default_deduction_is_zero_and_behaves_like_before() -> None:
    """★ 기본값 0.0 — 기존 호출자 전부가 그대로 동작한다(판정 ①).

    인자를 아예 안 주면 수량은 종전 그대로 **총 역송량**이다.
    """
    stream = SurplusSale(sale_price_won_per_kwh=100.0)
    dispatch = _dispatch(10.0, 20.0, -5.0)  # 음수(소비)는 0으로 클램프

    assert stream.annual_value(dispatch, year=1) == to_won(30.0 * 100.0)
    assert "비PV" not in stream.formula(dispatch, year=1), (
        "차감이 0인데 산식에 차감 문구가 실렸다 — 기존 리포트 문면을 조용히 바꾼다"
    )


@pytest.mark.req("FR-401-AC2.SurplusSale")
def test_non_pv_discharge_is_subtracted_from_the_quantity() -> None:
    """★★ 충전원이 계통인 ESS 방전분만큼 수량이 준다(판정 §4의 핵심).

    같은 실행(같은 `dispatch`)을 차감 0 인 것과 차감 30 인 것 둘로 돌려
    **금액 차이가 정확히 그 30kWh × 단가**인지 본다 — 값을 손으로 다시
    적지 않고 두 결과를 직접 견준다(동어반복을 피한다).
    """
    dispatch = _dispatch(50.0, 50.0)  # 총 역송 100kWh
    price = 90.0
    undeducted = SurplusSale(sale_price_won_per_kwh=price)
    deducted = SurplusSale(sale_price_won_per_kwh=price, non_pv_ess_discharge_kwh=30.0)

    diff = float(undeducted.annual_value(dispatch, year=1)) - float(
        deducted.annual_value(dispatch, year=1)
    )
    assert diff == pytest.approx(30.0 * price)


@pytest.mark.req("FR-401-AC2.SurplusSale")
def test_pv_surplus_source_keeps_the_full_quantity() -> None:
    """★ `PV_SURPLUS` 충전분은 빼지 않는다 — 태양광 전력이 ESS 를 경유한 것이다.

    러너는 충전원이 `PV_SURPLUS` 이면 차감 인자에 0.0 을 넘긴다(수량이 그대로
    유지된다는 것을 그 값 자체로 확인한다).
    """
    dispatch = _dispatch(40.0, 40.0)
    stream = SurplusSale(sale_price_won_per_kwh=110.0, non_pv_ess_discharge_kwh=0.0)
    assert stream.annual_value(dispatch, year=1) == to_won(80.0 * 110.0)


@pytest.mark.req("FR-401-AC2.SurplusSale")
def test_negative_deduction_argument_is_refused_at_construction() -> None:
    """음수 차감량은 물리적으로 뜻이 없다 — 생성 시점에 거부한다."""
    with pytest.raises(ValueError, match="음수"):
        SurplusSale(sale_price_won_per_kwh=100.0, non_pv_ess_discharge_kwh=-1.0)


@pytest.mark.req("FR-401-AC2.SurplusSale")
def test_deduction_exceeding_the_quantity_is_refused_not_clamped() -> None:
    """★★ 차감 뒤 수량이 음수가 되면 **거부**한다 — 0 으로 자르지 않는다(판정 ①).

    조용히 0 으로 자르면 「차감량이 실제 역송량을 초과했다」는 사실이 사라진다
    — 이 저장소의 거부 관례(`ValidationError` 3요소)를 따른다.
    """
    dispatch = _dispatch(10.0)  # 총 역송 10kWh
    stream = SurplusSale(sale_price_won_per_kwh=100.0, non_pv_ess_discharge_kwh=15.0)

    with pytest.raises(ValidationError) as caught:
        stream.annual_value(dispatch, year=1)

    err = caught.value
    assert err.field == "valuestream.SurplusSale.non_pv_ess_discharge_kwh"
    assert "10" in err.reason and "15" in err.reason
    assert err.action.strip()


@pytest.mark.req("FR-401-AC2.SurplusSale")
def test_formula_shows_the_deduction_when_present() -> None:
    """★ 검토자가 「총 역송량 × 단가」로만 손계산해도 맞지 않게 만들지 않는다
    — 차감을 산식 문면에 함께 싣는다(판정 ①)."""
    dispatch = _dispatch(50.0, 50.0)
    stream = SurplusSale(sale_price_won_per_kwh=90.0, non_pv_ess_discharge_kwh=30.0)
    formula = stream.formula(dispatch, year=1)

    assert "100.00kWh" in formula, f"총 역송량이 산식에 없다: {formula!r}"
    assert "30.00kWh" in formula, f"차감량이 산식에 없다: {formula!r}"
    assert "70.00kWh" in formula, f"차감 후 수량이 산식에 없다: {formula!r}"
