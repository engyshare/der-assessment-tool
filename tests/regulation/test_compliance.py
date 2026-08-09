from __future__ import annotations

from datetime import date

import pytest

from core.contracts.regulation import RegulationItem
from core.contracts.units import Money
from core.regulation.compliance import (
    SelfSufficiencyInput,
    assess_self_sufficiency,
    assess_supply_duty,
)
from core.regulation.profile import DataRegulationProfile


def _profile(
    *,
    supply_ratio: float = 0.70,
    self_sufficiency_ratio: float = 0.60,
) -> DataRegulationProfile:
    return DataRegulationProfile(
        name="current",
        version="2026",
        entries=(
            RegulationItem(
                key="supply_duty.required_ratio",
                value=supply_ratio,
                unit="소수",
                source="테스트 고시",
                valid_from=date(2026, 1, 1),
            ),
            RegulationItem(
                key="supply_duty.exemption_years",
                value=3,
                unit="년",
                source="테스트 고시",
                valid_from=date(2026, 1, 1),
            ),
            RegulationItem(
                key="supply_duty.allowed_external_rate",
                value=100,
                unit="원/kWh",
                source="테스트 고시",
                valid_from=date(2026, 1, 1),
            ),
            RegulationItem(
                key="supply_duty.excess_external_rate",
                value=300,
                unit="원/kWh",
                source="테스트 고시",
                valid_from=date(2026, 1, 1),
            ),
            RegulationItem(
                key="self_sufficiency.required_ratio",
                value=self_sufficiency_ratio,
                unit="소수",
                source="테스트 고시",
                valid_from=date(2026, 1, 1),
            ),
        ),
    )


@pytest.mark.req("FR-502-AC1")
@pytest.mark.req("FR-502-AC2")
@pytest.mark.req("FR-502-AC4")
def test_supply_duty_separates_allowed_and_excess_external_energy() -> None:
    """Oracle rank 1: closed-form supply-duty split.

    Formula:
    required = 1,000*0.70 = 700.
    external = 1,000 - 650 = 350.
    allowed external = 1,000*(1 - 0.70) = 300.
    excess external = 350 - 300 = 50.
    charges = 300*100 and 50*300, exact won amounts.
    """
    result = assess_supply_duty(
        total_consumption_kwh=1000.0,
        in_zone_procurement_kwh=650.0,
        operation_year=4,
        when=date(2026, 6, 30),
        profile=_profile(),
    )

    assert result.fulfillment_ratio == pytest.approx(0.65)
    assert result.required_procurement_kwh == pytest.approx(700.0)
    assert result.allowed_external_kwh == pytest.approx(300.0)
    assert result.excess_external_kwh == pytest.approx(50.0)
    assert result.shortfall_kwh == pytest.approx(50.0)
    assert result.warning is True
    assert result.charge.amount("allowed_external_energy") == Money(30_000)
    assert result.charge.amount("excess_external_energy") == Money(15_000)


@pytest.mark.req("FR-502-AC3")
def test_supply_duty_exemption_period_is_profile_data() -> None:
    """Oracle rank 1: operation year 3 is inside profile exemption years 3."""
    result = assess_supply_duty(
        total_consumption_kwh=1000.0,
        in_zone_procurement_kwh=650.0,
        operation_year=3,
        when=date(2026, 6, 30),
        profile=_profile(),
    )

    assert result.exempt is True
    assert result.warning is False
    assert result.charge.total == Money(0)


@pytest.mark.req("FR-503-AC1")
def test_self_sufficiency_supports_both_formula_bases_and_warns_on_shortfall() -> None:
    """Oracle rank 1: two explicit self-sufficiency formula bases.

    Formula:
    self-supply basis = 610 / 1,000 = 0.61, above required 0.60.
    grid-burden basis = 1 - 450 / 1,000 = 0.55, below required 0.60.
    """
    profile = _profile()

    met = assess_self_sufficiency(
        SelfSufficiencyInput(
            total_consumption_kwh=1000.0,
            self_supplied_kwh=610.0,
            grid_import_kwh=390.0,
            basis="self_supply",
        ),
        when=date(2026, 6, 30),
        profile=profile,
    )
    missed = assess_self_sufficiency(
        SelfSufficiencyInput(
            total_consumption_kwh=1000.0,
            self_supplied_kwh=550.0,
            grid_import_kwh=450.0,
            basis="grid_burden",
        ),
        when=date(2026, 6, 30),
        profile=profile,
    )

    assert met.ratio == pytest.approx(0.61)
    assert met.warning is False
    assert met.formula == "self_supplied_kwh / total_consumption_kwh"
    assert missed.ratio == pytest.approx(0.55)
    assert missed.warning is True
    assert missed.formula == "1 - grid_import_kwh / total_consumption_kwh"


@pytest.mark.req("FR-502-AC1")
@pytest.mark.parametrize("bad_ratio", [-0.01, 1.01])
def test_supply_duty_rejects_profile_ratio_outside_fraction_range(
    bad_ratio: float,
) -> None:
    """Oracle rank 1 negative test: ratio domain is the closed interval 0..1.

    This plants invalid regulation-profile values so the `_ratio()` guard is
    proven to inspect something, rather than merely passing 0 invalid cases.
    """
    with pytest.raises(ValueError, match="between 0 and 1"):
        assess_supply_duty(
            total_consumption_kwh=1000.0,
            in_zone_procurement_kwh=650.0,
            operation_year=4,
            when=date(2026, 6, 30),
            profile=_profile(supply_ratio=bad_ratio),
        )


@pytest.mark.req("FR-503-AC1")
@pytest.mark.parametrize("bad_ratio", [-0.01, 1.01])
def test_self_sufficiency_rejects_profile_ratio_outside_fraction_range(
    bad_ratio: float,
) -> None:
    """Oracle rank 1 negative test: self-sufficiency threshold is 0..1."""
    with pytest.raises(ValueError, match="between 0 and 1"):
        assess_self_sufficiency(
            SelfSufficiencyInput(
                total_consumption_kwh=1000.0,
                self_supplied_kwh=610.0,
                grid_import_kwh=390.0,
                basis="self_supply",
            ),
            when=date(2026, 6, 30),
            profile=_profile(self_sufficiency_ratio=bad_ratio),
        )
