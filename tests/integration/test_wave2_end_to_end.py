from __future__ import annotations

from decimal import Decimal

import pytest

from core.cba.metrics import npv
from core.cba.proforma import (
    aggregate,
    assert_proforma_identity,
    benefit_row,
    total_row,
)
from core.contracts.der import DispatchContext, DispatchResult
from core.contracts.schemas import CashFlowRow
from core.contracts.units import ENERGY_TOLERANCE_KWH, Money, to_won
from core.der.ess import ESS, ESSOperatingMode
from core.der.pv import PV, OperatingMode
from core.engine.rule_based import RuleBasedEngine
from core.valuestream import PeakShaving, SurplusSale

HORIZON_YEARS = 20
HOURS_PER_DAY = 24
DAYS_PER_YEAR = 365


def test_wave2_single_case_runs_from_der_to_cba() -> None:
    """PV 3 kW at 15% gives 0.45 kWh/h; ESS uses 8 kWh/day at 90% RTE."""
    pv = PV(
        name="integration-pv",
        capacity_kw=3.0,
        capacity_factor=0.15,
        unit_capex_won_per_kw=1_500_000,
        fixed_om_won_per_year=100_000,
        escalation_rate=0.02,
        self_consumption_ratio=0.0,
        operating_mode=OperatingMode.FULL_EXPORT,
    )
    ess = ESS(
        name="integration-ess",
        capacity_kwh=10.0,
        power_kw=5.0,
        rte_pct=90.0,
        soc_min_pct=10.0,
        soc_max_pct=90.0,
        cycle_life=6_000,
        calendar_life=20,
        eol_soh_pct=80.0,
        cycles_per_year=365.0,
        operating_mode=ESSOperatingMode.PEAK_SHAVING,
        capex_unit_won_per_kwh=500_000,
        fixed_om_won_per_year=100_000,
    )

    ctx = DispatchContext(steps=HOURS_PER_DAY, dt=3_600, year=1)
    dispatch = RuleBasedEngine().run([pv, ess], ctx)

    assert set(dispatch.per_resource) == {"integration-pv", "integration-ess"}
    assert max(abs(error) for error in dispatch.electric_balance_error()) < ENERGY_TOLERANCE_KWH

    pv_series = dispatch.per_resource["integration-pv"].electric
    assert pv_series == pytest.approx([0.45] * HOURS_PER_DAY)

    ess_series = dispatch.per_resource["integration-ess"].electric
    assert _active_steps(ess_series, sign=-1) == [1, 2, 3, 4, 5, 6]
    assert _active_steps(ess_series, sign=1) == [13, 14, 15, 16]

    grid_export_result = DispatchResult(
        electric=list(dispatch.grid_export),
        heat=[0.0] * ctx.steps,
        cool=[0.0] * ctx.steps,
        fuel=[0.0] * ctx.steps,
    )
    surplus = SurplusSale(sale_price_won_per_kwh=120.0).annual_value(
        grid_export_result,
        year=1,
    )
    # Manual path check: the value stream consumes exported kWh, so positives only.
    assert surplus == to_won(sum(dispatch.grid_export) * 120.0)

    peak = PeakShaving(
        monthly_peak_reduction_kw=[ess.reducible_peak_kw(year=1)] * 12,
        demand_charge_won_per_kw_month=8_320.0,
    ).annual_value(grid_export_result, year=1)
    assert peak == ess.peak_shaving_benefit(demand_charge_won_per_kw=8_320.0, year=1)

    annual_benefit = Money(surplus * DAYS_PER_YEAR + peak)
    rows = [
        benefit_row(
            "IntegrationBenefit",
            {year: int(annual_benefit) for year in range(1, HORIZON_YEARS + 1)},
        ),
        _money_row("PVFixedOM", {year: -pv.fixed_om(year=year) for year in range(1, 21)}),
        _money_row(
            "ESSFixedOM",
            {year: -ess.fixed_om(year=year) for year in range(1, 21)},
        ),
    ]
    assert_proforma_identity(rows)

    grand_total = total_row(rows)
    assert aggregate(rows) == grand_total.total()
    assert sum(grand_total.amounts.values(), Decimal(0)) == sum(row.total() for row in rows)
    for row in [*rows, grand_total]:
        for amount in row.amounts.values():
            assert amount == amount.to_integral_value()

    initial_investment = Money(pv.capex(year=1) + ess.capex(year=1))
    project_npv = npv(initial_investment, [grand_total], discount_rate=0.045)
    assert isinstance(project_npv, Money)
    assert project_npv == Money(int(project_npv))


def _active_steps(series: list[float], *, sign: int) -> list[int]:
    if sign > 0:
        return [index for index, value in enumerate(series) if value > ENERGY_TOLERANCE_KWH]
    return [index for index, value in enumerate(series) if value < -ENERGY_TOLERANCE_KWH]


def _money_row(tag: str, schedule: dict[int, Money]) -> CashFlowRow:
    return CashFlowRow(
        label=tag,
        tag=tag,
        amounts={year: Decimal(amount) for year, amount in schedule.items()},
    )
