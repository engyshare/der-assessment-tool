"""Regulation compliance calculations for WP-3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from core.contracts.regulation import RegulationProfile
from core.contracts.units import to_won
from core.regulation.tariff import BillBreakdown, BillLine

SUPPLY_DUTY_REQUIRED_RATIO = "supply_duty.required_ratio"
SUPPLY_DUTY_EXEMPTION_YEARS = "supply_duty.exemption_years"
SUPPLY_DUTY_ALLOWED_EXTERNAL_RATE = "supply_duty.allowed_external_rate"
SUPPLY_DUTY_EXCESS_EXTERNAL_RATE = "supply_duty.excess_external_rate"
SELF_SUFFICIENCY_REQUIRED_RATIO = "self_sufficiency.required_ratio"


def _profile_float(profile: RegulationProfile, key: str, *, when: date) -> float:
    value = profile.get(key, when=when).value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"regulation item {key!r} must be numeric")
    return float(value)


def _profile_int(profile: RegulationProfile, key: str, *, when: date) -> int:
    value = profile.get(key, when=when).value
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"regulation item {key!r} must be an integer")
    return value


def _ratio(profile: RegulationProfile, key: str, *, when: date) -> float:
    value = _profile_float(profile, key, when=when)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"regulation ratio {key!r} must be between 0 and 1")
    return value


def _money_line(key: str, label: str, kwh: float, rate: float) -> BillLine:
    amount = to_won(Decimal(str(kwh)) * Decimal(str(rate)))
    return BillLine(key, label, amount, kwh=kwh, unit_rate_won_per_kwh=rate)


@dataclass(frozen=True)
class SupplyDutyResult:
    fulfillment_ratio: float
    required_procurement_kwh: float
    allowed_external_kwh: float
    excess_external_kwh: float
    shortfall_kwh: float
    exempt: bool
    warning: bool
    charge: BillBreakdown


def assess_supply_duty(
    *,
    total_consumption_kwh: float,
    in_zone_procurement_kwh: float,
    operation_year: int,
    when: date,
    profile: RegulationProfile,
) -> SupplyDutyResult:
    if total_consumption_kwh <= 0:
        raise ValueError("total consumption must be positive")
    if in_zone_procurement_kwh < 0:
        raise ValueError("in-zone procurement must be non-negative")
    if operation_year < 1:
        raise ValueError("operation year is one-based")

    required_ratio = _ratio(profile, SUPPLY_DUTY_REQUIRED_RATIO, when=when)
    exemption_years = _profile_int(profile, SUPPLY_DUTY_EXEMPTION_YEARS, when=when)
    required = total_consumption_kwh * required_ratio
    external = max(total_consumption_kwh - in_zone_procurement_kwh, 0.0)
    allowed_external = total_consumption_kwh * (1.0 - required_ratio)
    excess_external = max(external - allowed_external, 0.0)
    shortfall = max(required - in_zone_procurement_kwh, 0.0)
    fulfillment = in_zone_procurement_kwh / total_consumption_kwh
    exempt = operation_year <= exemption_years

    if exempt:
        charge = BillBreakdown(())
        warning = False
    else:
        allowed_rate = _profile_float(
            profile, SUPPLY_DUTY_ALLOWED_EXTERNAL_RATE, when=when
        )
        excess_rate = _profile_float(
            profile, SUPPLY_DUTY_EXCESS_EXTERNAL_RATE, when=when
        )
        charge = BillBreakdown((
            _money_line(
                "allowed_external_energy",
                "의무 허용 외부조달",
                min(external, allowed_external),
                allowed_rate,
            ),
            _money_line(
                "excess_external_energy",
                "의무 초과 외부조달",
                excess_external,
                excess_rate,
            ),
        ))
        warning = excess_external > 0.0

    return SupplyDutyResult(
        fulfillment_ratio=fulfillment,
        required_procurement_kwh=required,
        allowed_external_kwh=allowed_external,
        excess_external_kwh=excess_external,
        shortfall_kwh=shortfall,
        exempt=exempt,
        warning=warning,
        charge=charge,
    )


SelfSufficiencyBasis = Literal["self_supply", "grid_burden"]


@dataclass(frozen=True)
class SelfSufficiencyInput:
    total_consumption_kwh: float
    self_supplied_kwh: float
    grid_import_kwh: float
    basis: SelfSufficiencyBasis


@dataclass(frozen=True)
class SelfSufficiencyResult:
    ratio: float
    required_ratio: float
    warning: bool
    formula: str


def assess_self_sufficiency(
    data: SelfSufficiencyInput,
    *,
    when: date,
    profile: RegulationProfile,
) -> SelfSufficiencyResult:
    if data.total_consumption_kwh <= 0:
        raise ValueError("total consumption must be positive")
    required = _ratio(profile, SELF_SUFFICIENCY_REQUIRED_RATIO, when=when)

    if data.basis == "self_supply":
        ratio = data.self_supplied_kwh / data.total_consumption_kwh
        formula = "self_supplied_kwh / total_consumption_kwh"
    else:
        ratio = 1.0 - data.grid_import_kwh / data.total_consumption_kwh
        formula = "1 - grid_import_kwh / total_consumption_kwh"

    return SelfSufficiencyResult(
        ratio=ratio,
        required_ratio=required,
        warning=ratio < required,
        formula=formula,
    )
