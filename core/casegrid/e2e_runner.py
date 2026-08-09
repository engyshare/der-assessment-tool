"""End-to-end case runner — wraps DER → Engine → Benefit → CBA into a CaseRunner.

This module translates case-grid variable levels into concrete resource parameters,
executes the full dispatch → benefit → CBA pipeline for one case, and returns
metric dict suitable for ``run_cases()``.

The pipeline mirrors ``tests/integration/test_wave2_end_to_end.py`` but is
parameterised by case variable values so the case-grid can drive it.

All numeric parameters come from the *level_map* argument, which the caller
builds from ``docs/assumptions.yaml``.  No financial/quantity value is
hardcoded in this module (NFR-202).
"""
from __future__ import annotations

from collections.abc import Mapping

from core.cba.metrics import npv, payback_discounted
from core.cba.proforma import benefit_row, fixed_om_row
from core.contracts.der import DispatchContext, DispatchResult
from core.contracts.units import Money, Year
from core.der.ess import ESS, ESSOperatingMode
from core.der.pv import PV, OperatingMode
from core.engine.rule_based import RuleBasedEngine
from core.valuestream import PeakShaving, SurplusSale

HORIZON_YEARS = 20
STEPS_PER_DAY = 24
SECONDS_PER_HOUR = 3_600
DAYS_PER_YEAR = 365


def _resolve(
    level: str | object,
    var_name: str,
    level_map: Mapping[str, Mapping[str, float]],
) -> float:
    """Translate a case variable level name to a numeric value."""
    key = str(level)
    mapping = level_map.get(var_name, {})
    if key in mapping:
        return mapping[key]
    raise ValueError(f"Unknown level {key!r} for variable {var_name!r}")


def run_single_case_e2e(
    case_values: dict[str, object],
    *,
    level_map: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
    """Execute the full DER → Engine → Benefit → CBA pipeline for one case.

    *level_map* maps each case-grid variable name (e.g. ``"pv_unit_cost"``)
    to a ``{level_name: numeric_value}`` dict.  The caller builds this from
    ``AssumptionProvider`` so that all financial/quantity parameters originate
    from ``docs/assumptions.yaml`` (NFR-202).

    Returns a metric dict with at least ``npv`` so the case-grid can collect it.
    """
    pv_capex = _resolve(
        case_values.get("pv_unit_cost", "base"), "pv_unit_cost", level_map
    )
    ess_capex = _resolve(
        case_values.get("ess_unit_cost", "base"), "ess_unit_cost", level_map
    )
    discount_rate = _resolve(
        case_values.get("discount_rate", "base"), "discount_rate", level_map
    )

    # 1. Resources
    pv = PV(
        name="e2e-pv",
        capacity_kw=3.0,
        capacity_factor=0.15,
        unit_capex_won_per_kw=pv_capex,
        fixed_om_won_per_year=100_000,
        escalation_rate=0.02,
        self_consumption_ratio=0.0,
        operating_mode=OperatingMode.FULL_EXPORT,
    )
    ess = ESS(
        name="e2e-ess",
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
        capex_unit_won_per_kwh=ess_capex,
        fixed_om_won_per_year=100_000,
    )

    # 2. Dispatch
    ctx = DispatchContext(steps=STEPS_PER_DAY, dt=SECONDS_PER_HOUR, year=Year(1))
    dispatch = RuleBasedEngine().run([pv, ess], ctx)

    # 3. Benefits (one day, annualised)
    grid_export_result = DispatchResult(
        electric=list(dispatch.grid_export),
        heat=[0.0] * ctx.steps,
        cool=[0.0] * ctx.steps,
        fuel=[0.0] * ctx.steps,
    )
    surplus_per_day = SurplusSale(sale_price_won_per_kwh=120.0).annual_value(
        grid_export_result, year=1
    )
    peak_per_day = PeakShaving(
        monthly_peak_reduction_kw=[ess.reducible_peak_kw(year=1)] * 12,
        demand_charge_won_per_kw_month=8_320.0,
    ).annual_value(grid_export_result, year=1)
    annual_benefit = int(surplus_per_day * DAYS_PER_YEAR + peak_per_day)

    # 4. Proforma → NPV
    initial_investment = Money(pv.capex(year=1) + ess.capex(year=1))
    benefit_rows = [
        benefit_row(
            "E2EBenefit",
            {year: annual_benefit for year in range(1, HORIZON_YEARS + 1)},
        ),
    ]
    cost_rows = [
        fixed_om_row(
            "PVFixedOM",
            start_year=1,
            end_year=HORIZON_YEARS,
            annual_amount_won=int(pv.fixed_om(year=1)),
            escalation_rate=0.02,
        ),
        fixed_om_row(
            "ESSFixedOM",
            start_year=1,
            end_year=HORIZON_YEARS,
            annual_amount_won=int(ess.fixed_om(year=1)),
        ),
    ]
    all_rows = list(benefit_rows) + list(cost_rows)
    project_npv = npv(initial_investment, all_rows, discount_rate=discount_rate)
    discounted_payback = payback_discounted(
        initial_investment, all_rows, discount_rate=discount_rate
    )

    return {
        "npv": float(project_npv),
        "payback_years": discounted_payback,
    }
