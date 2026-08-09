from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from core.cba.metrics import npv, payback_simple
from core.cba.proforma import benefit_row
from core.contracts.der import DispatchContext, DispatchResult
from core.contracts.units import Money
from core.der.ess import ESS, ESSOperatingMode
from core.der.pv import PV, OperatingMode
from core.engine.rule_based import RuleBasedEngine
from core.incentive.schemas import IncentiveScheme
from core.valuestream import PeakShaving, SurplusSale

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "fixtures" / "golden"
DISCOUNT_RATE = 0.045
HORIZON_YEARS = 20
HOURS_PER_DAY = 24
DAYS_PER_YEAR = 365


def _load_case(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"{path.name} is not a mapping"
    return loaded


def _expected_values(case: dict[str, Any]) -> dict[str, float]:
    expected = case.get("expected_values")
    if not isinstance(expected, dict):
        return {}
    return {
        key: float(value)
        for key, value in expected.items()
        if isinstance(value, (int, float))
    }


def _reference_metrics() -> dict[str, float]:
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
    grid_export_result = DispatchResult(
        electric=list(dispatch.grid_export),
        heat=[0.0] * ctx.steps,
        cool=[0.0] * ctx.steps,
        fuel=[0.0] * ctx.steps,
    )

    surplus = SurplusSale(sale_price_won_per_kwh=120.0).annual_value(
        grid_export_result, year=1
    )
    peak = PeakShaving(
        monthly_peak_reduction_kw=[ess.reducible_peak_kw(year=1)] * 12,
        demand_charge_won_per_kw_month=8_320.0,
    ).annual_value(grid_export_result, year=1)
    annual_benefit = Money(surplus * DAYS_PER_YEAR + peak)

    base_capex = Money(int(pv.capex(year=1) + ess.capex(year=1)))
    rows = [
        benefit_row(
            "annual_benefit",
            {year: int(annual_benefit) for year in range(1, HORIZON_YEARS + 1)},
        )
    ]

    return {
        "annual_benefit_won": float(int(annual_benefit)),
        "base_capex_won": float(int(base_capex)),
        "npv_won": float(int(npv(base_capex, rows, DISCOUNT_RATE))),
        "payback_period_years": float(payback_simple(base_capex, rows)),
    }


def _scenario_metrics(subsidy_rate: float) -> dict[str, float]:
    metrics = _reference_metrics()
    base_capex = int(metrics["base_capex_won"])
    annual_benefit = int(metrics["annual_benefit_won"])

    scheme = IncentiveScheme(
        subsidy_rate=subsidy_rate,
        loan_rate=0.0,
        loan_interest=0.0,
        loan_grace_years=0,
        loan_repayment_years=0,
        loan_repayment_type="\uc6d0\ub9ac\uae08\uade0\ub4f1",
        tax_credit_rate=0.0,
        sponsor="\uad6d\ube44",
    )
    equity = scheme.calculate_financing(base_capex)["equity"]
    initial_investment = Money(int(equity))
    rows = [
        benefit_row(
            "annual_benefit",
            {year: annual_benefit for year in range(1, HORIZON_YEARS + 1)},
        )
    ]

    return {
        "npv_won": float(int(npv(initial_investment, rows, DISCOUNT_RATE))),
        "payback_period_years": float(payback_simple(initial_investment, rows)),
    }


def _compare(path: Path, expected: dict[str, float], actual: dict[str, float]) -> None:
    for key, expected_value in expected.items():
        assert key in actual, f"{path.name}: missing actual value for {key}"
        if key == "npv_won":
            assert actual[key] == expected_value, (
                f"{path.name}: {key} expected {expected_value}, actual {actual[key]}"
            )
        else:
            assert actual[key] == pytest.approx(expected_value, rel=1e-3, abs=1e-3), (
                f"{path.name}: {key} expected {expected_value}, actual {actual[key]}"
            )


@pytest.mark.req("NFR-104-M1")
@pytest.mark.parametrize("path", sorted(GOLDEN_DIR.glob("scenario_*.yaml")))
def test_golden_scenarios_match_current_regression_snapshot(path: Path) -> None:
    case = _load_case(path)
    expected = _expected_values(case)
    if not expected:
        print(f"SKIP {path.name}: expected_values are all null")
        pytest.skip(f"{path.name}: expected_values are all null")

    actual = _scenario_metrics(float(case["subsidy_rate"]))
    _compare(path, expected, actual)
