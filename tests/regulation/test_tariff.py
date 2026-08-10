from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest
import yaml

from core.contracts.assumptions import AssumptionProvider, AssumptionValue
from core.contracts.units import Money
from core.regulation.tariff import (
    DirectTradeTariffTable,
    MeterPoint,
    ResidentialBlock,
    ResidentialTariffTable,
    TariffCatalog,
    TariffEngine,
    TaxAndFundScheme,
    TouDiscountRule,
    TouPeriod,
    TouTariffTable,
    TouUsage,
)

VAT_RATE_KEY = "tax.vat_rate"
POWER_FUND_RATE_KEY = "tariff.power_fund_rate"
DIRECT_TRADE_SUPPORT_KEY = "fee.direct_trade_support"
POLICY_RATE_KEYS = (VAT_RATE_KEY, POWER_FUND_RATE_KEY, DIRECT_TRADE_SUPPORT_KEY)


def _ledger_values() -> dict[str, float | int | str]:
    path = Path(__file__).resolve().parents[2] / "docs" / "assumptions.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    values: dict[str, float | int | str] = {}
    for item in doc["assumptions"]:
        key = item.get("key")
        if key in POLICY_RATE_KEYS:
            values[key] = item["value"]
    missing = set(POLICY_RATE_KEYS) - set(values)
    if missing:
        raise AssertionError(f"대장에 필요한 정책 요율이 없습니다: {sorted(missing)}")
    return values


def _ledger_decimal(key: str) -> Decimal:
    value = _ledger_values()[key]
    if isinstance(value, str):
        raise AssertionError(f"대장값 {key} 가 문자열입니다: {value!r}")
    return Decimal(str(value))


def _won(value: Decimal | int) -> Money:
    amount = Decimal(value) if isinstance(value, int) else value
    return Money(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _rate_amount(subtotal: int | Decimal, key: str) -> Money:
    return _won(Decimal(subtotal) * _ledger_decimal(key))


def _tax_and_fund(subtotal: int | Decimal) -> tuple[Money, Money]:
    return _rate_amount(subtotal, VAT_RATE_KEY), _rate_amount(subtotal, POWER_FUND_RATE_KEY)


def _value(key: str, value: float | int | str) -> AssumptionValue:
    return AssumptionValue(
        key=key,
        value=value,
        value_unit="테스트",
        base_year="2026",
        applicable_scope="WP-3 테스트 스텁",
        derivation_method="테스트 케이스 손계산",
        source="tests/regulation",
        verified_at=date(2026, 8, 9),
        confidence="확정",
        set_name="regulation-test",
        set_version="1",
    )


class _Assumptions(AssumptionProvider):
    def __init__(self, items: Mapping[str, float | int | str]) -> None:
        self._items = dict(items)

    @property
    def set_name(self) -> str:
        return "regulation-test"

    @property
    def set_version(self) -> str:
        return "1"

    def get(self, key: str) -> AssumptionValue | None:
        if key not in self._items:
            return None
        return _value(key, self._items[key])


def _residential_table() -> ResidentialTariffTable:
    return ResidentialTariffTable(
        name="residential-2026",
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        blocks=(
            ResidentialBlock(upper_kwh=200.0, energy_rate_key="r.energy.1",
                             basic_charge_key="r.basic.1"),
            ResidentialBlock(upper_kwh=400.0, energy_rate_key="r.energy.2",
                             basic_charge_key="r.basic.2"),
            ResidentialBlock(upper_kwh=None, energy_rate_key="r.energy.3",
                             basic_charge_key="r.basic.3"),
        ),
        climate_rate_key="tariff.climate",
        fuel_adjustment_rate_key="tariff.fuel",
        essential_discount_key="tariff.essential_discount",
        essential_discount_max_kwh=200.0,
        tax_and_fund=TaxAndFundScheme(
            vat_rate_key=VAT_RATE_KEY,
            power_fund_rate_key=POWER_FUND_RATE_KEY,
        ),
    )


def _assumptions() -> _Assumptions:
    items: dict[str, float | int | str] = {
        "r.energy.1": 100,
        "r.energy.2": 200,
        "r.energy.3": 300,
        "r.basic.1": 900,
        "r.basic.2": 1600,
        "r.basic.3": 7300,
        "tariff.climate": 10,
        "tariff.fuel": -5,
        "tariff.essential_discount": 4000,
        "tou.summer.peak": 200,
        "tou.spring.weekend": 100,
        "tou.weekday": 120,
        "tou.spring_weekend_discount": 0.20,
        "direct.energy": 80,
    }
    items.update(_ledger_values())
    return _Assumptions(items)


def _engine() -> TariffEngine:
    return TariffEngine(
        assumptions=_assumptions(),
        catalog=TariffCatalog(
            residential=(_residential_table(),),
            tou=(_tou_table(),),
            direct_trade=(_direct_table(),),
        ),
    )


@pytest.mark.req("NFR-202-M1")
def test_policy_rates_in_tariff_stub_are_read_from_assumption_ledger() -> None:
    """Oracle rank 1: direct key equality against the assumption ledger.

    This catches the exact failure mode from the inspection: changing
    `docs/assumptions.yaml` must change the test stub for
    `tax.vat_rate`, `tariff.power_fund_rate`, and
    `fee.direct_trade_support`.
    """
    assumptions = _assumptions()
    for key in POLICY_RATE_KEYS:
        assert assumptions.require(key).value == _ledger_values()[key]


@pytest.mark.req("FR-501-AC1")
@pytest.mark.parametrize(
    ("kwh", "basic", "energy", "discount"),
    [
        (199.0, 900, 19_900, -4_000),
        (200.0, 900, 20_000, -4_000),
        (201.0, 1_600, 20_200, 0),
        (400.0, 1_600, 60_000, 0),
        (401.0, 7_300, 60_300, 0),
    ],
)
def test_residential_progressive_boundaries_are_inclusive(
    kwh: float, basic: int, energy: int, discount: int
) -> None:
    """Oracle rank 1: closed-form tranche calculation, exact won amounts.

    Formula:
    - 199 kWh: 199 * 100 = 19,900.
    - 200 kWh boundary: 200 * 100 = 20,000, discount still -4,000.
    - 201 kWh: 200 * 100 + 1 * 200 = 20,200, no discount.
    - 400 kWh boundary: 200 * 100 + 200 * 200 = 60,000.
    - 401 kWh: prior 60,000 + 1 * 300 = 60,300.
    """
    bill = _engine().bill_residential(kwh, when=date(2026, 6, 30))

    assert bill.amount("basic") == Money(basic)
    assert bill.amount("energy") == Money(energy)
    assert bill.amount("essential_discount") == Money(discount)


@pytest.mark.req("FR-501-AC7")
@pytest.mark.req("FR-501-AC8")
def test_bill_breakdown_contains_vat_power_fund_and_traceable_lines() -> None:
    """Oracle rank 1: bill-line closed form, exact won amounts.

    Formula:
    basic 900 + energy 200*100 + climate 200*10 + fuel 200*(-5)
    + essential discount -4,000 = subtotal 17,900.
    VAT = round-half-up(17,900 * ledger(tax.vat_rate)).
    Fund = round-half-up(17,900 * ledger(tariff.power_fund_rate)).
    """
    bill = _engine().bill_residential(200.0, when=date(2026, 6, 30))
    vat, fund = _tax_and_fund(17_900)

    assert bill.amount("basic") == Money(900)
    assert bill.amount("energy") == Money(20_000)
    assert bill.amount("climate_environment") == Money(2_000)
    assert bill.amount("fuel_adjustment") == Money(-1_000)
    assert bill.amount("essential_discount") == Money(-4_000)
    assert bill.amount("vat") == vat
    assert bill.amount("power_industry_fund") == fund
    assert bill.total == Money(Decimal(17_900) + vat + fund)
    assert bill.line("vat").assumption_key == VAT_RATE_KEY
    assert bill.line("power_industry_fund").assumption_key == POWER_FUND_RATE_KEY


@pytest.mark.req("FR-501-AC5")
def test_tariff_catalog_selects_table_by_inclusive_valid_period() -> None:
    """Oracle rank 1: same 10 kWh load under two effective data tables.

    Formula:
    2026-12-31 uses old table: basic 100 + 10*10 = 200.
    2027-01-01 uses new table: basic 300 + 10*30 = 600.
    Effective-period endpoints are inclusive.
    """
    assumptions = _Assumptions({
        "old.energy": 10,
        "old.basic": 100,
        "new.energy": 30,
        "new.basic": 300,
    })
    old = ResidentialTariffTable(
        name="old",
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        blocks=(ResidentialBlock(100.0, "old.energy", "old.basic"),),
    )
    new = ResidentialTariffTable(
        name="new",
        valid_from=date(2027, 1, 1),
        valid_to=None,
        blocks=(ResidentialBlock(100.0, "new.energy", "new.basic"),),
    )
    engine = TariffEngine(
        assumptions=assumptions,
        catalog=TariffCatalog(residential=(old, new), tou=(), direct_trade=()),
    )

    assert engine.bill_residential(10.0, when=date(2026, 12, 31)).total == Money(200)
    assert engine.bill_residential(10.0, when=date(2027, 1, 1)).total == Money(600)


def _tou_table() -> TouTariffTable:
    return TouTariffTable(
        name="tou-2026",
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        periods=(
            TouPeriod(
                key="summer_peak",
                months=(6, 7, 8),
                weekdays=(0, 1, 2, 3, 4),
                start_hour=16,
                end_hour=22,
                energy_rate_key="tou.summer.peak",
            ),
            TouPeriod(
                key="spring_weekend",
                months=(3, 4, 5, 9, 10),
                weekdays=(5, 6),
                start_hour=10,
                end_hour=16,
                energy_rate_key="tou.spring.weekend",
            ),
            TouPeriod(
                key="weekday",
                months=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12),
                weekdays=(0, 1, 2, 3, 4),
                start_hour=0,
                end_hour=24,
                energy_rate_key="tou.weekday",
            ),
        ),
        discounts=(
            TouDiscountRule(
                key="spring_weekend_discount",
                months=(3, 4, 5, 9, 10),
                weekdays=(5, 6),
                discount_rate_key="tou.spring_weekend_discount",
            ),
        ),
        tax_and_fund=TaxAndFundScheme(
            vat_rate_key=VAT_RATE_KEY,
            power_fund_rate_key=POWER_FUND_RATE_KEY,
        ),
    )


@pytest.mark.req("FR-501-AC2")
@pytest.mark.req("FR-501-AC3")
def test_tou_uses_season_weekday_hour_matrix_and_special_discount() -> None:
    """Oracle rank 1: period-by-period tariff multiplication.

    Formula:
    summer peak = 10*200 = 2,000.
    spring weekend = 10*100 = 1,000.
    spring weekend discount = -(1,000*0.20) = -200.
    Subtotal 2,800 then VAT/fund are ledger-rate round-half-up charges
    under FR-501-AC7.
    """
    bill = _engine().bill_tou(
        (
            TouUsage(datetime(2026, 7, 15, 17), 10.0),
            TouUsage(datetime(2026, 4, 11, 11), 10.0),
        ),
        when=date(2026, 7, 1),
    )
    vat, fund = _tax_and_fund(2_800)

    assert bill.amount("energy.summer_peak") == Money(2_000)
    assert bill.amount("energy.spring_weekend") == Money(1_000)
    assert bill.amount("discount.spring_weekend_discount") == Money(-200)
    assert bill.amount("vat") == vat
    assert bill.amount("power_industry_fund") == fund
    assert bill.total == Money(Decimal(2_800) + vat + fund)


def _direct_table() -> DirectTradeTariffTable:
    return DirectTradeTariffTable(
        name="direct-2026",
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        energy_rate_key="direct.energy",
        support_fee_key=DIRECT_TRADE_SUPPORT_KEY,
        tax_and_fund=TaxAndFundScheme(
            vat_rate_key=VAT_RATE_KEY,
            power_fund_rate_key=POWER_FUND_RATE_KEY,
        ),
    )


@pytest.mark.req("FR-501-AC6")
def test_scenario_combines_independent_meter_points_without_mixing_tariffs() -> None:
    """Oracle rank 1: sum of independent meter-point bills.

    Formula:
    household 200 kWh = residential subtotal 17,900 plus ledger VAT/fund.
    common TOU summer peak = 10*200 plus ledger VAT/fund.
    direct trade = 50*80 + 50*ledger(fee.direct_trade_support), then
    ledger VAT/fund. Scenario total is the exact sum of those three bills.
    """
    bill = _engine().bill_scenario(
        (
            MeterPoint.residential("household-1", 200.0),
            MeterPoint.tou("common", (TouUsage(datetime(2026, 7, 15, 17), 10.0),)),
            MeterPoint.direct_trade("trade", 50.0),
        ),
        when=date(2026, 7, 1),
    )

    household_vat, household_fund = _tax_and_fund(17_900)
    common_vat, common_fund = _tax_and_fund(2_000)
    direct_support = _won(Decimal(50) * _ledger_decimal(DIRECT_TRADE_SUPPORT_KEY))
    direct_subtotal = Decimal(4_000) + direct_support
    direct_vat, direct_fund = _tax_and_fund(direct_subtotal)

    assert bill.meter_bill("household-1").amount("energy") == Money(20_000)
    assert bill.meter_bill("common").amount("energy.summer_peak") == Money(2_000)
    assert bill.meter_bill("common").amount("vat") == common_vat
    assert bill.meter_bill("common").amount("power_industry_fund") == common_fund
    assert bill.meter_bill("trade").amount("direct_trade_support_fee") == direct_support
    assert bill.meter_bill("trade").amount("vat") == direct_vat
    assert bill.meter_bill("trade").amount("power_industry_fund") == direct_fund
    assert bill.total == Money(
        Decimal(17_900) + household_vat + household_fund
        + Decimal(2_000) + common_vat + common_fund
        + direct_subtotal + direct_vat + direct_fund
    )
