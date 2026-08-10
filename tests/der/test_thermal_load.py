"""`ThermalLoad` 열부하 자원 테스트 — WP-1e / spec FR-102-AC1.ThermalLoad.

**`RC-TL-P2` 를 HeatPump 없이 검증하는 이유** (§16.1 W-5 구획 격리):
열 수지 균형은 「부하 = 공급 합」이라는 *산술*이지 히트펌프의 성질이 아니다.
여기서 `core.der.heat_pump` 를 import 하면 WP-1d 가 아직 없을 때 이 테스트가
깨지고, 있으면 두 구획이 한 테스트로 묶여 어느 쪽 결함인지 판정할 수 없다.
그래서 공급량을 **인자로 받아** 균형만 본다.
"""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

from core.contracts.der import DER, EOL_REPLACE, EOL_RETIRE, DispatchContext
from core.contracts.units import ENERGY_TOLERANCE_KWH, HOURS_PER_YEAR, Money, to_won, won_sum
from core.der.thermal_load import ThermalLoad
from tests.contract.test_der_contract import DERContractTests

# §13.2.3 RC-TL-P1 오라클: HDD 2,500 × 0.8 kWh/HDD = 2,000.0 kWh
HDD = 2_500.0
KWH_PER_HDD = 0.8
ANNUAL_HEAT_KWH = 2_000.0

# §13.2.2 C-2 오라클
OM_A = 100_000.0
OM_I = 0.02
OM_N = 20
OM_20Y_TOTAL = Money(2_429_737)


def make_thermal_load(**overrides) -> ThermalLoad:
    params: dict = {
        "name": "난방급탕부하",
        "heating_degree_days": HDD,
        "kwh_per_hdd": KWH_PER_HDD,
    }
    params.update(overrides)
    return ThermalLoad(**params)


# ── 계약 테스트 상속 (§13.0.3 L3) ────────────────────────────────────

class TestThermalLoadContract(DERContractTests):
    def make(self) -> DER:
        return make_thermal_load(
            capacity_kw=5.0,
            unit_cost_won_per_kw=200_000.0,
            fixed_om_won_per_year=OM_A,
            variable_om_won_per_kwh=3.0,
            escalation_rate=OM_I,
            subcomponents=[("순환펌프", 12, 400_000.0)],
        )


# ── RC-TL-P1 난방도일 기반 추정 ──────────────────────────────────────

@pytest.mark.req("FR-102-AC1.ThermalLoad")
def test_hdd_based_estimate() -> None:
    """HDD 2,500 × 0.8 kWh/HDD = **2,000.0 kWh**."""
    tl = make_thermal_load()
    assert tl.annual_energy_kwh(year=1) == pytest.approx(ANNUAL_HEAT_KWH, abs=1e-9)

    series = tl.step_series_kwh(year=1)
    assert len(series) == HOURS_PER_YEAR
    assert math.fsum(series) == pytest.approx(ANNUAL_HEAT_KWH, abs=1e-9)


@pytest.mark.req("FR-102-AC1.ThermalLoad")
def test_monthly_weights_shape_the_year_without_changing_the_total() -> None:
    """월 가중치는 **모양만** 바꾼다 — 연간 추정치는 HDD 산식이 정한다.

    가중치가 총량까지 바꾸면 난방도일 오라클(2,000 kWh)이 프로파일에 따라
    흔들리고, 그 순간 §13.2.3 의 기준값은 검증 정박점이 아니게 된다.
    """
    weights = [3.0, 3.0, 2.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 2.0, 3.0]
    tl = make_thermal_load(monthly_weights=weights)

    monthly = tl.monthly_energy_kwh(year=1)
    assert math.fsum(monthly) == pytest.approx(ANNUAL_HEAT_KWH, abs=1e-9)
    assert monthly[6] == pytest.approx(0.0, abs=1e-12), "가중치 0인 달은 열부하 0"
    assert monthly[0] == pytest.approx(ANNUAL_HEAT_KWH * 3.0 / 15.0, abs=1e-9)


@pytest.mark.req("FR-102-AC1.ThermalLoad")
def test_hourly_series_input_path() -> None:
    """8760 열부하 시계열 직접 입력 경로."""
    tl = make_thermal_load(
        heating_degree_days=None, kwh_per_hdd=None, hourly_kwh=[0.25] * HOURS_PER_YEAR
    )
    assert tl.annual_energy_kwh(year=1) == pytest.approx(2_190.0, abs=1e-9)


@pytest.mark.req("FR-102-AC1.ThermalLoad")
def test_media_flags_only_heat_and_sign_is_negative() -> None:
    """열부하는 열 수지에서 **음수**로 잡힌다 (DispatchResult 부호 규약)."""
    tl = make_thermal_load()
    assert tl.tag == "ThermalLoad"
    assert tl.carries_heat is True
    assert tl.carries_electric is False
    assert tl.carries_cool is False
    assert tl.consumes_fuel is False

    ctx = DispatchContext(steps=HOURS_PER_YEAR, dt=tl.dt, year=1)
    result = tl.dispatch(ctx)
    assert all(v <= 0.0 for v in result.heat)
    assert math.fsum(result.heat) == pytest.approx(-ANNUAL_HEAT_KWH, abs=1e-9)
    assert not any(result.electric), "히트펌프 소비전력은 히트펌프가 싣는다 — 부하가 아니다"
    assert not any(result.cool)
    assert not any(result.fuel)


@pytest.mark.req("FR-102-AC1.ThermalLoad")
def test_annual_growth_compounds_from_year_one() -> None:
    g = 0.015
    tl = make_thermal_load(annual_growth_rate=g)
    assert tl.degradation_rate == 0.0
    for n in (1, 2, 10):
        assert tl.annual_energy_kwh(year=n) == pytest.approx(
            ANNUAL_HEAT_KWH * (1.0 + g) ** (n - 1), rel=1e-12
        )


# ── RC-TL-P2 열 수지 (FR-301-AC2) ────────────────────────────────────

@pytest.mark.req("FR-301-AC2")
def test_heat_balance_across_heatpump_and_backup_source() -> None:
    """열부하 = 히트펌프 공급 + 보조열원 공급, **전 스텝** 균형.

    연 합계만 맞추면 여름에 남고 겨울에 모자라는 공급도 통과한다. 균형은
    스텝별로 성립해야 하며 허용 오차는 NFR-102 의 1e-6 kWh 다.
    """
    tl = make_thermal_load()
    ctx = DispatchContext(steps=HOURS_PER_YEAR, dt=tl.dt, year=1)
    demand = tl.step_series_kwh(year=1)

    heat_pump = [d * 0.7 for d in demand]
    backup = [d - hp for d, hp in zip(demand, heat_pump, strict=True)]

    residual = tl.heat_balance_residual(ctx, supplied_kwh=[heat_pump, backup])
    assert len(residual) == HOURS_PER_YEAR
    assert all(abs(r) < ENERGY_TOLERANCE_KWH for r in residual)
    assert tl.is_heat_balanced(ctx, supplied_kwh=[heat_pump, backup]) is True


@pytest.mark.req("FR-301-AC2")
def test_unmet_heat_is_reported_not_silently_absorbed() -> None:
    """공급이 모자라면 **미충족으로 드러난다** (`RC-HP-X1` 과 짝).

    잔차를 0으로 눌러 버리면 정격이 모자란 히트펌프도 전 부하를 감당한 것으로
    보이고, 보조열원 연료비가 통째로 사라진다.
    """
    tl = make_thermal_load()
    ctx = DispatchContext(steps=HOURS_PER_YEAR, dt=tl.dt, year=1)
    demand = tl.step_series_kwh(year=1)
    partial = [d * 0.7 for d in demand]

    residual = tl.heat_balance_residual(ctx, supplied_kwh=[partial])
    assert all(r <= 0.0 for r in residual), "공급 부족은 음수 잔차다"
    assert math.fsum(residual) == pytest.approx(-ANNUAL_HEAT_KWH * 0.3, rel=1e-9)
    assert tl.is_heat_balanced(ctx, supplied_kwh=[partial]) is False


@pytest.mark.req("FR-301-AC3")
def test_heat_balance_rejects_row_count_mismatch() -> None:
    """공급 시계열 행수가 다르면 명확한 오류 (FR-301-AC3)."""
    tl = make_thermal_load()
    ctx = DispatchContext(steps=24, dt=tl.dt, year=1)
    with pytest.raises(ValueError, match="스텝"):
        tl.heat_balance_residual(ctx, supplied_kwh=[[1.0] * 23])


# ── RC-LD-B0 과 같은 규칙: 부하는 편익을 만들지 않는다 ───────────────

@pytest.mark.req("FR-102-AC1.ThermalLoad")
def test_thermal_load_produces_no_value_streams() -> None:
    """열부하도 편익을 생성하지 않는다.

    「히트펌프로 바꿔서 아낀 열비용」은 히트펌프의 편익(`RC-HP-B1`·`B2`)이며,
    열부하에도 붙이면 같은 절감이 두 번 계상된다 (FR-402-AC2.C).
    """
    tl = make_thermal_load()
    assert tl.value_streams() == ()
    baseline = tl.baseline_energy_cost(year=1, tariff_won_per_kwh=120.0)
    assert baseline == to_won(ANNUAL_HEAT_KWH * 120.0)


# ── 경계·위반 ────────────────────────────────────────────────────────

@pytest.mark.req("FR-102-AC1.ThermalLoad")
def test_rejects_negative_hdd_and_intensity() -> None:
    with pytest.raises(ValueError, match="음수"):
        make_thermal_load(heating_degree_days=-1.0)
    with pytest.raises(ValueError, match="음수"):
        make_thermal_load(kwh_per_hdd=-0.1)
    with pytest.raises(ValueError, match="음수"):
        make_thermal_load(
            heating_degree_days=None,
            kwh_per_hdd=None,
            hourly_kwh=[0.1] * (HOURS_PER_YEAR - 1) + [-0.1],
        )


@pytest.mark.req("FR-102-AC1.ThermalLoad")
def test_rejects_ambiguous_or_missing_input_path() -> None:
    with pytest.raises(ValueError, match="하나"):
        make_thermal_load(hourly_kwh=[0.25] * HOURS_PER_YEAR)
    with pytest.raises(ValueError, match="하나"):
        make_thermal_load(heating_degree_days=None, kwh_per_hdd=None)
    with pytest.raises(ValueError, match="함께"):
        make_thermal_load(kwh_per_hdd=None)


@pytest.mark.req("FR-102-AC1.ThermalLoad")
def test_rejects_bad_series_and_weights() -> None:
    with pytest.raises(ValueError, match="행"):
        make_thermal_load(
            heating_degree_days=None, kwh_per_hdd=None, hourly_kwh=[0.25] * 8759
        )
    with pytest.raises(ValueError, match="12"):
        make_thermal_load(monthly_weights=[1.0] * 11)
    with pytest.raises(ValueError, match="음수"):
        make_thermal_load(monthly_weights=[-1.0] + [1.0] * 11)
    with pytest.raises(ValueError, match="0"):
        make_thermal_load(monthly_weights=[0.0] * 12)


@pytest.mark.req("FR-102-AC1.ThermalLoad")
def test_rejects_growth_rate_out_of_range() -> None:
    with pytest.raises(ValueError, match="증가율"):
        make_thermal_load(annual_growth_rate=1.5)


# ── RC-ALL-C1 CAPEX ──────────────────────────────────────────────────

@pytest.mark.req("FR-101-AC2")
def test_rc_all_c1_capex_and_vat_are_separated_for_thermal_load() -> None:
    """`RC-ALL-C1` 산식 원문 (§13.2.2): `단가 × 용량 + 부대비`, 부가세는 별도 항목.

        ThermalLoad 파라미터화: 1,000,000 × 5 + 300,000 = **5,300,000원**
        부가세               : 5,300,000 × 10% = **530,000원**

    경계 짝: 초기 투자와 세액은 **1년차에만** 있다. 이후 연도에 남으면 없는 설비에
    다시 세금이 붙는 셈이다.
    """
    tl = make_thermal_load(
        capacity_kw=5.0,
        unit_cost_won_per_kw=1_000_000.0,
        incidental_cost_won=300_000.0,
        vat_rate=0.1,
    )
    assert tl.capex(year=1) == Money(5_300_000)
    assert tl.capex_vat(year=1) == Money(530_000)
    assert tl.capex(year=2) == Money(0)
    assert tl.capex_vat(year=2) == Money(0)


# ── RC-ALL-C2 고정 O&M ───────────────────────────────────────────────

@pytest.mark.req("FR-101-AC2")
def test_rc_all_c2_fixed_om_20y_total_matches_geometric_series_for_thermal_load() -> None:
    """`RC-ALL-C2` 산식 원문 (§13.2.2): 등비수열 합 `A × ((1+i)^n − 1) / i`.

        ThermalLoad 파라미터화: A=100,000원, i=0.02, n=20
        20년 누계 = 100,000 × ((1.02^20 − 1) / 0.02) = **2,429,737원**

    경계 짝: A=0이면 물가계수만으로 비용이 생기면 안 된다.
    """
    tl = make_thermal_load(fixed_om_won_per_year=OM_A, escalation_rate=OM_I)
    closed_form = OM_A * ((1.0 + OM_I) ** OM_N - 1.0) / OM_I

    assert tl.fixed_om(year=1) == Money(100_000)
    assert tl.fixed_om(year=2) == Money(102_000)
    assert to_won(closed_form) == OM_20Y_TOTAL
    assert won_sum(tl.fixed_om(year=y) for y in range(1, OM_N + 1)) == OM_20Y_TOTAL
    assert make_thermal_load(escalation_rate=OM_I).fixed_om(year=7) == Money(0)


# ── RC-ALL-C3 변동 O&M ───────────────────────────────────────────────

@pytest.mark.req("FR-101-AC2")
def test_rc_all_c3_variable_om_uses_thermal_throughput_not_capacity() -> None:
    """`RC-ALL-C3` 산식 원문 (§13.2.2): `처리량 × 단가`.

        ThermalLoad 처리량 = 연간 열소비 **2,000 kWh_th**
        1년차 O&M          = 2,000 × 3 = **6,000원**
        2년차 O&M          = 2,000 × 1.015 × 3 × 1.02 = 6,211.8 → **6,212원**

    경계 짝: 단가가 0이면 성장률·물가가 있어도 0원이어야 한다.
    """
    tl = make_thermal_load(
        annual_growth_rate=0.015,
        escalation_rate=0.02,
        variable_om_won_per_kwh=3.0,
    )
    assert tl.variable_om(year=1) == Money(6_000)
    assert tl.variable_om(year=2) == Money(6_212)
    assert make_thermal_load(
        annual_growth_rate=0.015,
        escalation_rate=0.02,
        variable_om_won_per_kwh=0.0,
    ).variable_om(year=7) == Money(0)


# ── RC-ALL-C4 교체비 ─────────────────────────────────────────────────

@pytest.mark.req("FR-104-AC3")
@pytest.mark.req("FR-104-AC4")
def test_rc_all_c4_replacement_is_booked_the_year_after_life_and_not_before() -> None:
    """`RC-ALL-C4` 산식 원문 (§13.2.2): 수명 도달 **다음 연도 초**에 계상한다.

        순환펌프 12년 수명 400,000원 → **13년차 400,000원**
        본체 5kW × 1,000,000원/kW   → **26년차 5,000,000원**

    경계 짝: 12년차까지는 순환펌프 교체비가 아직 0원이어야 한다.
    """
    tl = make_thermal_load(
        lifetime=25,
        capacity_kw=5.0,
        unit_cost_won_per_kw=1_000_000.0,
        subcomponents=[("순환펌프", 12, 400_000.0)],
    )
    assert tl.replacement_schedule(horizon=12) == {}
    assert tl.replacement_schedule(horizon=20) == {13: Money(400_000)}

    longer = tl.replacement_schedule(horizon=30)
    assert sorted(longer) == [13, 25, 26]
    assert longer[25] == Money(400_000)
    assert longer[26] == Money(5_000_000)


# ── RC-ALL-C5 잔존가치 ───────────────────────────────────────────────

@pytest.mark.req("FR-104-AC5")
def test_rc_all_c5_salvage_value_is_prorated_and_zero_at_eol() -> None:
    """`RC-ALL-C5` 산식 원문 (§13.2.2): `취득가 × 잔존수명 / 총수명`을 최종연도에 계상 후 할인.

        ThermalLoad 파라미터화: 1,000,000 × 5 = **5,000,000원**
        20년 종료 시 잔존수명      = 25 − 20 = **5년**
        명목 잔존가치             = 5,000,000 × 5/25 = **1,000,000원**
        20년 할인(4.5%)          = 1,000,000 / 1.045^20 = **414,643원**

    경계 짝: 수명을 다 쓴 25년차 잔존가치는 0원이다.
    """
    tl = make_thermal_load(
        lifetime=25, capacity_kw=5.0, unit_cost_won_per_kw=1_000_000.0
    )

    assert tl.salvage_value(year=20) == Money(1_000_000)
    assert to_won(Decimal("1000000") / Decimal("1.045") ** 20) == Money(414_643)
    assert tl.salvage_value(year=25) == Money(0)


# ── NFR-206 파일 규모 ────────────────────────────────────────────────

@pytest.mark.req("NFR-206-M1")
def test_module_stays_within_size_budget() -> None:
    import inspect

    import core.der.thermal_load as module

    lines = inspect.getsource(module).splitlines()
    assert len(lines) <= 500, f"thermal_load.py 가 {len(lines)}줄입니다 (NFR-206: 500)"


@pytest.mark.req("NFR-208-AC2")
def test_does_not_import_sibling_resources() -> None:
    """자원끼리 import 하지 않는다 (NFR-208-AC1 · §16.1 W-5).

    `ThermalLoad` 가 `HeatPump` 를 알면 두 구획이 한 몸이 되어 병렬 작업이
    깨지고, 열부하를 히트펌프 없이 쓰는 모델(보일러만 있는 기준선)이 성립하지
    않는다.
    """
    import inspect

    import core.der.thermal_load as module

    source = inspect.getsource(module)
    for forbidden in ("core.der.heat_pump", "core.der.load", "core.der.boiler"):
        assert forbidden not in source, f"형제 자원 {forbidden} 을 참조합니다"


# ── FR-104-AC3 retire 기능 (WP-24) ────────────────────────────────────


@pytest.mark.req("FR-104-AC3")
def test_default_is_replace_behavior_unchanged() -> None:
    """기본값은 replace - 아무것도 안 넘기면 지금까지와 결과가 똑같다.

    ThermalLoad(기본 생성)은 end_of_life_action이 "replace"이므로 기존과 동일하게 작동한다.
    """
    tl = make_thermal_load(
        lifetime=25,
        capacity_kw=5.0,
        unit_cost_won_per_kw=1_000_000.0,
        subcomponents=[("순환펌프", 12, 400_000.0)],
    )
    assert tl.end_of_life_action == EOL_REPLACE
    assert tl.retires_at_end_of_life() is False

    # 기존과 동일한 교체 스케줄: 12년 수명 순환펌프 → 13년차 교체
    schedule = tl.replacement_schedule(horizon=20)
    assert schedule == {13: Money(400_000)}


@pytest.mark.req("FR-104-AC3")
def test_retire_returns_empty_replacement_schedule() -> None:
    """retire면 본체도 부속설비도 아무것도 교체하지 않는다.

    수명 25년 + 순환펌프 12년이어도, retire 선택 시 빈 스케줄을 돌려준다.
    """
    tl = make_thermal_load(
        end_of_life_action=EOL_RETIRE,
        lifetime=25,
        capacity_kw=5.0,
        unit_cost_won_per_kw=1_000_000.0,
        subcomponents=[("순환펌프", 12, 400_000.0)],
    )
    assert tl.end_of_life_action == EOL_RETIRE
    assert tl.retires_at_end_of_life() is True

    # retire 선택 시 교체비가 전혀 없다
    schedule = tl.replacement_schedule(horizon=20)
    assert schedule == {}

    longer = tl.replacement_schedule(horizon=30)
    assert longer == {}


@pytest.mark.req("FR-104-AC3")
def test_retire_keeps_thermal_load_unchanged_dispatch() -> None:
    """retire 여도 열부하는 그대로다 - 수요는 계속 발생한다.

    Load/ThermalLoad는 순수 부하 자원으로서, retire해도 가구는 계속 살고
    수요는 계속 발생한다. dispatch()는 수정하지 않는다.
    """
    tl_replace = make_thermal_load(lifetime=25, annual_growth_rate=0.0)
    tl_retire = make_thermal_load(
        lifetime=25, end_of_life_action=EOL_RETIRE, annual_growth_rate=0.0
    )

    ctx_early = DispatchContext(steps=HOURS_PER_YEAR, dt=tl_replace.dt, year=1)
    result_replace_early = tl_replace.dispatch(ctx_early)
    result_retire_early = tl_retire.dispatch(ctx_early)

    # 수명 도달 전(1년차): 둘 다 동일한 열부하를 소비
    assert result_replace_early.heat == result_retire_early.heat
    assert math.fsum(result_replace_early.heat) == pytest.approx(-ANNUAL_HEAT_KWH, abs=1e-9)

    # 수명 도달 후(30년차): 둘 다 여전히 동일한 열부하를 소비 (부하 자원 특성)
    ctx_late = DispatchContext(steps=HOURS_PER_YEAR, dt=tl_replace.dt, year=30)
    result_replace_late = tl_replace.dispatch(ctx_late)
    result_retire_late = tl_retire.dispatch(ctx_late)

    assert result_replace_late.heat == result_retire_late.heat


@pytest.mark.req("FR-104-AC3")
def test_retire_keeps_thermal_load_unchanged_annual_energy() -> None:
    """retire 선택 시 연간 열부하가 replace와 같다.

    수명 25년 기준:
    - 1~25년차: replace와 retire 동일
    - 26년차 이후: 둘 다 여전히 성장률 적용하여 계산 (부하 자원 특성)
    """
    g = 0.015
    tl_replace = make_thermal_load(lifetime=25, annual_growth_rate=g)
    tl_retire = make_thermal_load(
        lifetime=25, end_of_life_action=EOL_RETIRE, annual_growth_rate=g
    )

    for year in [1, 10, 25, 30]:
        expected = ANNUAL_HEAT_KWH * (1.0 + g) ** (year - 1)
        assert tl_replace.annual_energy_kwh(year=year) == pytest.approx(expected, rel=1e-12)
        assert tl_retire.annual_energy_kwh(year=year) == pytest.approx(expected, rel=1e-12)
        assert tl_replace.annual_energy_kwh(year=year) == tl_retire.annual_energy_kwh(year=year)


@pytest.mark.req("FR-104-AC3")
def test_retire_does_not_affect_other_cost_methods() -> None:
    """retire가 capex, O&M, 잔존가치에 영향을 주지 않는다.

    교체비(schedule)만 다르고, 다른 비용 메서드는 수명에 따라 동일하게 작동한다.
    """
    tl_replace = make_thermal_load(
        lifetime=25,
        capacity_kw=5.0,
        unit_cost_won_per_kw=1_000_000.0,
        fixed_om_won_per_year=OM_A,
        variable_om_won_per_kwh=3.0,
        escalation_rate=OM_I,
    )
    tl_retire = make_thermal_load(
        lifetime=25,
        end_of_life_action=EOL_RETIRE,
        capacity_kw=5.0,
        unit_cost_won_per_kw=1_000_000.0,
        fixed_om_won_per_year=OM_A,
        variable_om_won_per_kwh=3.0,
        escalation_rate=OM_I,
    )

    # capex: 둘 다 1년차에만 발생
    assert tl_replace.capex(year=1) == tl_retire.capex(year=1)
    assert tl_replace.capex(year=2) == tl_retire.capex(year=2) == Money(0)

    # fixed_om: 물가상승 동일
    for year in [1, 10, 25]:
        assert tl_replace.fixed_om(year=year) == tl_retire.fixed_om(year=year)

    # variable_om: 소비량 동일
    for year in [1, 10, 25]:
        assert tl_replace.variable_om(year=year) == tl_retire.variable_om(year=year)

    # salvage_value: 수명에 따른 잔존가치 동일
    for year in [10, 25]:
        assert tl_replace.salvage_value(year=year) == tl_retire.salvage_value(year=year)
