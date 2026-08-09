"""Tariff engine for WP-3.

Tariff structure is data. This module owns interpretation and arithmetic, while
rates and effective periods are supplied through tariff tables and
`AssumptionProvider`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, TypeVar

from core.contracts.assumptions import AssumptionProvider
from core.contracts.units import Money, to_won

_TariffTable = TypeVar(
    "_TariffTable",
    "ResidentialTariffTable",
    "TouTariffTable",
    "DirectTradeTariffTable",
)


def _decimal(value: float | int | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _valid_on(valid_from: date | None, valid_to: date | None, when: date) -> bool:
    if valid_from is not None and when < valid_from:
        return False
    return not (valid_to is not None and when > valid_to)


@dataclass(frozen=True)
class BillLine:
    key: str
    label: str
    amount: Money
    assumption_key: str | None = None
    kwh: float | None = None
    unit_rate_won_per_kwh: float | None = None


@dataclass(frozen=True)
class BillBreakdown:
    lines: tuple[BillLine, ...]

    @property
    def total(self) -> Money:
        total = sum((Decimal(line.amount) for line in self.lines), Decimal(0))
        return Money(total)

    def amount(self, key: str) -> Money:
        total = sum(
            (Decimal(line.amount) for line in self.lines if line.key == key),
            Decimal(0),
        )
        return Money(total)

    def line(self, key: str) -> BillLine:
        for line in self.lines:
            if line.key == key:
                return line
        raise KeyError(key)


@dataclass(frozen=True)
class ScenarioMeterBill:
    meter_id: str
    bill: BillBreakdown


@dataclass(frozen=True)
class ScenarioBill:
    meter_bills: tuple[ScenarioMeterBill, ...]

    @property
    def total(self) -> Money:
        total = sum((Decimal(item.bill.total) for item in self.meter_bills), Decimal(0))
        return Money(total)

    def meter_bill(self, meter_id: str) -> BillBreakdown:
        for item in self.meter_bills:
            if item.meter_id == meter_id:
                return item.bill
        raise KeyError(meter_id)


@dataclass(frozen=True)
class TaxAndFundScheme:
    vat_rate_key: str
    power_fund_rate_key: str


@dataclass(frozen=True)
class ResidentialBlock:
    upper_kwh: float | None
    energy_rate_key: str
    basic_charge_key: str


@dataclass(frozen=True)
class ResidentialTariffTable:
    name: str
    valid_from: date | None
    valid_to: date | None
    blocks: tuple[ResidentialBlock, ...]
    climate_rate_key: str | None = None
    fuel_adjustment_rate_key: str | None = None
    essential_discount_key: str | None = None
    essential_discount_max_kwh: float | None = None
    tax_and_fund: TaxAndFundScheme | None = None

    def __post_init__(self) -> None:
        if not self.blocks:
            raise ValueError("residential tariff needs at least one block")


@dataclass(frozen=True)
class TouPeriod:
    key: str
    months: tuple[int, ...]
    weekdays: tuple[int, ...]
    start_hour: int
    end_hour: int
    energy_rate_key: str

    def matches(self, timestamp: datetime) -> bool:
        if timestamp.month not in self.months or timestamp.weekday() not in self.weekdays:
            return False
        hour = timestamp.hour
        if self.start_hour <= self.end_hour:
            return self.start_hour <= hour < self.end_hour
        return hour >= self.start_hour or hour < self.end_hour


@dataclass(frozen=True)
class TouDiscountRule:
    key: str
    months: tuple[int, ...]
    weekdays: tuple[int, ...]
    discount_rate_key: str
    period_keys: tuple[str, ...] = ()

    def applies(self, timestamp: datetime, period_key: str) -> bool:
        if self.period_keys and period_key not in self.period_keys:
            return False
        return timestamp.month in self.months and timestamp.weekday() in self.weekdays


@dataclass(frozen=True)
class TouTariffTable:
    name: str
    valid_from: date | None
    valid_to: date | None
    periods: tuple[TouPeriod, ...]
    discounts: tuple[TouDiscountRule, ...] = ()
    tax_and_fund: TaxAndFundScheme | None = None

    def __post_init__(self) -> None:
        if not self.periods:
            raise ValueError("TOU tariff needs at least one period")


@dataclass(frozen=True)
class TouUsage:
    timestamp: datetime
    kwh: float


@dataclass(frozen=True)
class DirectTradeTariffTable:
    name: str
    valid_from: date | None
    valid_to: date | None
    energy_rate_key: str
    support_fee_key: str
    tax_and_fund: TaxAndFundScheme | None = None


@dataclass(frozen=True)
class TariffCatalog:
    residential: tuple[ResidentialTariffTable, ...]
    tou: tuple[TouTariffTable, ...]
    direct_trade: tuple[DirectTradeTariffTable, ...]

    def select_residential(self, when: date) -> ResidentialTariffTable:
        return _select_effective(self.residential, when, "residential")

    def select_tou(self, when: date) -> TouTariffTable:
        return _select_effective(self.tou, when, "tou")

    def select_direct_trade(self, when: date) -> DirectTradeTariffTable:
        return _select_effective(self.direct_trade, when, "direct_trade")


def _select_effective(
    tables: tuple[_TariffTable, ...],
    when: date,
    kind: str,
) -> _TariffTable:
    matched = [
        table for table in tables
        if _valid_on(table.valid_from, table.valid_to, when)
    ]
    if not matched:
        raise KeyError(f"effective {kind} tariff table is missing for {when.isoformat()}")
    return max(matched, key=lambda table: table.valid_from or date.min)


@dataclass(frozen=True)
class MeterPoint:
    meter_id: str
    kind: Literal["residential", "tou", "direct_trade"]
    kwh: float = 0.0
    tou_usages: tuple[TouUsage, ...] = ()

    @classmethod
    def residential(cls, meter_id: str, kwh: float) -> MeterPoint:
        return cls(meter_id=meter_id, kind="residential", kwh=kwh)

    @classmethod
    def tou(cls, meter_id: str, usages: Iterable[TouUsage]) -> MeterPoint:
        return cls(meter_id=meter_id, kind="tou", tou_usages=tuple(usages))

    @classmethod
    def direct_trade(cls, meter_id: str, kwh: float) -> MeterPoint:
        return cls(meter_id=meter_id, kind="direct_trade", kwh=kwh)


class TariffEngine:
    def __init__(self, *, assumptions: AssumptionProvider,
                 catalog: TariffCatalog) -> None:
        self._assumptions = assumptions
        self._catalog = catalog

    def bill_residential(self, kwh: float, *, when: date) -> BillBreakdown:
        if kwh < 0:
            raise ValueError("kWh must be non-negative")
        table = self._catalog.select_residential(when)
        assert isinstance(table, ResidentialTariffTable)

        lines: list[BillLine] = []
        basic_block = self._basic_block(table, kwh)
        basic = to_won(self._rate(basic_block.basic_charge_key))
        lines.append(BillLine("basic", "기본요금", basic, basic_block.basic_charge_key))

        energy = self._residential_energy_charge(table, kwh)
        lines.append(BillLine("energy", "전력량요금", energy, kwh=kwh))
        self._append_usage_rate_line(
            lines, "climate_environment", "기후환경요금", kwh, table.climate_rate_key
        )
        self._append_usage_rate_line(
            lines, "fuel_adjustment", "연료비조정", kwh,
            table.fuel_adjustment_rate_key
        )
        if (
            table.essential_discount_key is not None
            and table.essential_discount_max_kwh is not None
            and kwh <= table.essential_discount_max_kwh
        ):
            discount = to_won(self._rate(table.essential_discount_key))
            lines.append(BillLine(
                "essential_discount",
                "필수사용량 공제",
                Money(-discount),
                table.essential_discount_key,
            ))
        self._append_tax_and_fund(lines, table.tax_and_fund)
        return BillBreakdown(tuple(lines))

    def bill_tou(self, usages: Iterable[TouUsage], *, when: date) -> BillBreakdown:
        table = self._catalog.select_tou(when)
        assert isinstance(table, TouTariffTable)
        energy_raw: dict[str, Decimal] = {}
        rate_keys: dict[str, str] = {}
        discount_raw: dict[str, Decimal] = {}
        discount_keys: dict[str, str] = {}

        for usage in usages:
            if usage.kwh < 0:
                raise ValueError("kWh must be non-negative")
            period = self._period_for(table, usage.timestamp)
            rate = self._rate(period.energy_rate_key)
            charge = _decimal(usage.kwh) * _decimal(rate)
            energy_raw[period.key] = energy_raw.get(period.key, Decimal(0)) + charge
            rate_keys[period.key] = period.energy_rate_key
            for rule in table.discounts:
                if rule.applies(usage.timestamp, period.key):
                    discount = charge * _decimal(self._rate(rule.discount_rate_key))
                    discount_raw[rule.key] = discount_raw.get(rule.key, Decimal(0)) + discount
                    discount_keys[rule.key] = rule.discount_rate_key

        lines = [
            BillLine(
                f"energy.{key}",
                f"TOU 전력량요금 {key}",
                to_won(amount),
                rate_keys[key],
            )
            for key, amount in energy_raw.items()
        ]
        lines.extend(
            BillLine(
                f"discount.{key}",
                f"특례할인 {key}",
                Money(-to_won(amount)),
                discount_keys[key],
            )
            for key, amount in discount_raw.items()
        )
        self._append_tax_and_fund(lines, table.tax_and_fund)
        return BillBreakdown(tuple(lines))

    def bill_direct_trade(self, kwh: float, *, when: date) -> BillBreakdown:
        if kwh < 0:
            raise ValueError("kWh must be non-negative")
        table = self._catalog.select_direct_trade(when)
        assert isinstance(table, DirectTradeTariffTable)
        lines = [
            self._usage_rate_line(
                "direct_trade_energy",
                "직접거래 전력량요금",
                kwh,
                table.energy_rate_key,
            ),
            self._usage_rate_line(
                "direct_trade_support_fee",
                "거래지원수수료",
                kwh,
                table.support_fee_key,
            ),
        ]
        self._append_tax_and_fund(lines, table.tax_and_fund)
        return BillBreakdown(tuple(lines))

    def bill_scenario(self, meters: Iterable[MeterPoint], *, when: date) -> ScenarioBill:
        bills: list[ScenarioMeterBill] = []
        for meter in meters:
            if meter.kind == "residential":
                bill = self.bill_residential(meter.kwh, when=when)
            elif meter.kind == "tou":
                bill = self.bill_tou(meter.tou_usages, when=when)
            else:
                bill = self.bill_direct_trade(meter.kwh, when=when)
            bills.append(ScenarioMeterBill(meter.meter_id, bill))
        return ScenarioBill(tuple(bills))

    def price_signal_for_tou(self, timestamp: datetime, *, when: date) -> float:
        table = self._catalog.select_tou(when)
        assert isinstance(table, TouTariffTable)
        return self._rate(self._period_for(table, timestamp).energy_rate_key)

    def _rate(self, key: str) -> float:
        return self._assumptions.require_float(key)

    def _basic_block(self, table: ResidentialTariffTable,
                     kwh: float) -> ResidentialBlock:
        for block in table.blocks:
            if block.upper_kwh is None or kwh <= block.upper_kwh:
                return block
        return table.blocks[-1]

    def _residential_energy_charge(self, table: ResidentialTariffTable,
                                   kwh: float) -> Money:
        previous = Decimal(0)
        total = Decimal(0)
        target = _decimal(kwh)
        for block in table.blocks:
            upper = target if block.upper_kwh is None else _decimal(block.upper_kwh)
            tranche = max(Decimal(0), min(target, upper) - previous)
            if tranche:
                total += tranche * _decimal(self._rate(block.energy_rate_key))
            previous = upper
            if target <= upper:
                break
        return to_won(total)

    def _period_for(self, table: TouTariffTable, timestamp: datetime) -> TouPeriod:
        for period in table.periods:
            if period.matches(timestamp):
                return period
        raise KeyError(f"TOU period is missing for {timestamp.isoformat()}")

    def _usage_rate_line(self, key: str, label: str, kwh: float,
                         rate_key: str) -> BillLine:
        rate = self._rate(rate_key)
        amount = to_won(_decimal(kwh) * _decimal(rate))
        return BillLine(
            key,
            label,
            amount,
            assumption_key=rate_key,
            kwh=kwh,
            unit_rate_won_per_kwh=rate,
        )

    def _append_usage_rate_line(self, lines: list[BillLine], key: str, label: str,
                                kwh: float, rate_key: str | None) -> None:
        if rate_key is not None:
            lines.append(self._usage_rate_line(key, label, kwh, rate_key))

    def _append_tax_and_fund(self, lines: list[BillLine],
                             scheme: TaxAndFundScheme | None) -> None:
        if scheme is None:
            return
        subtotal = sum((Decimal(line.amount) for line in lines), Decimal(0))
        vat_rate = _decimal(self._rate(scheme.vat_rate_key))
        fund_rate = _decimal(self._rate(scheme.power_fund_rate_key))
        lines.append(BillLine(
            "vat",
            "부가가치세",
            to_won(subtotal * vat_rate),
            scheme.vat_rate_key,
        ))
        lines.append(BillLine(
            "power_industry_fund",
            "전력산업기반기금",
            to_won(subtotal * fund_rate),
            scheme.power_fund_rate_key,
        ))
