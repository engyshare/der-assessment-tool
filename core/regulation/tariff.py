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
from core.contracts.validation import ValidationError

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
class TariffFallbackNotice:
    """요청 시점에 유효한 요금표가 없어 **최근접 표로 대체했다** — `DV-6`.

    `DV-6` 원문: *「요금표 유효기간이 분석연도를 포함 **(미포함 시 경고 후 최근접
    표)**」*. R24 가 이 규칙을 「거부」로 읽었던 것은 `DV_RULES` 사본이 괄호를
    잘라 먹었기 때문이고, 원문은 **거부의 반대**를 요구한다.

    `direction` 을 함께 싣는 이유: 「과거 표로 계산했다」와 「미래 표로 계산했다」는
    **읽는 사람에게 뜻이 다르다.** 과거 표는 그 뒤의 요금 개정을 반영하지 않은
    것이고, 미래 표는 **아직 시행되지 않은 요금으로 과거를 계산한 것**이다.
    """

    kind: str
    requested: date
    used_table: str
    used_from: date | None
    used_to: date | None
    direction: Literal["과거", "미래"]

    @property
    def message(self) -> str:
        """사용자에게 보이는 한 줄. 리포트·화면이 그대로 싣는다."""
        window = (
            f"{self.used_from.isoformat() if self.used_from else '(무제한)'}"
            f" ~ {self.used_to.isoformat() if self.used_to else '(무제한)'}"
        )
        return (
            f"{self.requested.isoformat()} 에 유효한 {self.kind} 요금표가 없어 "
            f"{self.direction} 방향 최근접 표 «{self.used_table}»({window})로 "
            "계산했습니다"
        )


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
    #: 요금표 대체 경고 — `DV-6` 의 「경고 후 최근접 표」의 「경고」다.
    #:
    #: **왜 예외도 로그도 아니라 결과에 실리는가.** 규칙이 요구하는 것은 거부가
    #: 아니라 **폴백**이므로 계산은 계속되어야 하고, 그러면 사용자에게 「이 청구서는
    #: 요청한 연도의 표로 계산된 것이 아니다」를 전할 통로가 필요하다. 로그로
    #: 흘리면 리포트가 그것을 그릴 수 없고, 그리지 못하는 경고는 없는 것과 같다.
    #:
    #: 선례가 셋 있다 — `DispatchResult.notes` · UI `compliance_alert` ·
    #: `benefit.v2g_discharge` 의 `UserWarning`. 결과에 담으면 **새 경고 종류가 늘 때
    #: 채널을 새로 만들 필요가 없다.**
    notices: tuple[TariffFallbackNotice, ...] = ()

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
class BillLineSaving:
    key: str
    label: str
    baseline_amount: Money
    reduced_amount: Money

    @property
    def saved(self) -> Money:
        return Money(Decimal(self.baseline_amount) - Decimal(self.reduced_amount))


def trace_benefit_by_line(
    baseline: BillBreakdown, reduced: BillBreakdown
) -> tuple[BillLineSaving, ...]:
    """FR-501-AC8 「편익 → 항목 추적」: 편익 적용 전후 청구서를 항목별로 비교한다.

    항목 자체는 이미 6종으로 분해되어 있다(basic·energy·climate_environment·
    fuel_adjustment·vat·power_industry_fund). 남는 것은 편익 산식이 그
    항목들 중 어디를 얼마나 줄였는지 짝짓는 것뿐이다.
    """
    labels: dict[str, str] = {}
    for line in (*baseline.lines, *reduced.lines):
        labels.setdefault(line.key, line.label)
    return tuple(
        BillLineSaving(
            key=key,
            label=labels[key],
            baseline_amount=baseline.amount(key),
            reduced_amount=reduced.amount(key),
        )
        for key in sorted(labels)
    )


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

    @property
    def notices(self) -> tuple[TariffFallbackNotice, ...]:
        """계량점 전부의 요금표 대체 경고를 **한자리에** 모은다 — `DV-6`.

        모아 주지 않으면 읽는 사람이 계량점을 하나씩 뒤져야 하고, `TU-6` 판단대로
        한 단지의 계량점은 여럿이다(가구부 N개 + 공용부 + 거래분). 뒤져야 하는
        경고는 곧 읽히지 않는 경고다.
        """
        return tuple(
            notice for item in self.meter_bills for notice in item.bill.notices
        )

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
            raise ValidationError(
                field="tariff.residential_blocks",
                reason=f"누진 요금표 `{self.name}` 에 구간(block)이 하나도 없습니다",
                action="누진 구간을 최소 1개 이상 정의하십시오",
            )


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
            raise ValidationError(
                field="tariff.tou_periods",
                reason=f"TOU 요금표 `{self.name}` 에 시간대(period)가 하나도 없습니다",
                action="TOU 시간대를 최소 1개 이상 정의하십시오",
            )


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

    def select_residential(
        self, when: date
    ) -> tuple[ResidentialTariffTable, TariffFallbackNotice | None]:
        return _select_effective(self.residential, when, "주택용")

    def select_tou(
        self, when: date
    ) -> tuple[TouTariffTable, TariffFallbackNotice | None]:
        return _select_effective(self.tou, when, "TOU")

    def select_direct_trade(
        self, when: date
    ) -> tuple[DirectTradeTariffTable, TariffFallbackNotice | None]:
        return _select_effective(self.direct_trade, when, "직접거래")


def _select_effective(
    tables: tuple[_TariffTable, ...],
    when: date,
    kind: str,
) -> tuple[_TariffTable, TariffFallbackNotice | None]:
    """유효한 표를 고르고, 없으면 **최근접 표로 대체하며 경고를 낸다** — `DV-6`.

    ★ **거부가 아니라 폴백이다.** 종전에는 `KeyError` 를 던졌는데, `DV-6` 원문은
    *「미포함 시 **경고 후 최근접 표**」* 이며 그것은 거부의 반대다. R24 가 이
    규칙을 「거부」로 읽은 것은 `DV_RULES` 사본이 그 괄호를 잘라 먹었기 때문이다.

    ★★ **「최근접」을 과거 방향 우선으로 정했다 (R31 결정 §3).** 미래 개정본이
    날짜상 더 가까워도 쓰지 않는다 — 미래 요금표로 과거를 정산하면 **실제로
    청구되지 않은 요금**이 결과에 들어간다. 과거 방향에 아무것도 없을 때만 미래
    최근접으로 내려가고, 그때도 경고의 `direction` 이 그 사실을 나른다.

    ⚠ **표가 하나도 없으면 거부한다.** 대체할 대상이 없으므로 폴백이 성립하지
    않고, 그때 빈 표로 계산하면 요금이 0 원으로 나온다 — 「요금표가 없다」가
    「요금이 없다」와 구별되지 않는다.
    """
    matched = [
        table for table in tables
        if _valid_on(table.valid_from, table.valid_to, when)
    ]
    if matched:
        return max(matched, key=lambda table: table.valid_from or date.min), None

    if not tables:
        raise ValidationError(
            field=f"tariff.{kind}",
            reason=(
                f"{kind} 요금표가 하나도 없습니다 — {when.isoformat()} 에 대해 "
                "대체할 표가 없습니다"
            ),
            action=(
                "요금표를 최소 하나 등재하십시오. 빈 표로 계산하면 요금이 0 원으로 "
                "나오고, 「요금표가 없다」가 「요금이 없다」와 구별되지 않습니다"
            ),
            rule="DV-6",
        )

    past = [t for t in tables if t.valid_to is not None and t.valid_to < when]
    if past:
        chosen = max(past, key=lambda t: t.valid_to or date.min)
        direction: Literal["과거", "미래"] = "과거"
    else:
        future = [t for t in tables if t.valid_from is not None and t.valid_from > when]
        if not future:
            # 유효하지도, 과거도, 미래도 아닌 표만 있는 경우는 `_valid_on` 의
            # 정의상 존재할 수 없다 — 그래도 조용히 아무 표를 고르지 않는다.
            raise ValidationError(
                field=f"tariff.{kind}",
                reason=(
                    f"{kind} 요금표 {len(tables)}건 중 {when.isoformat()} 의 최근접을 "
                    "정할 수 없습니다 — 유효기간이 비어 있는 표만 있습니다"
                ),
                action="요금표의 `valid_from`·`valid_to` 를 확인하십시오",
                rule="DV-6",
            )
        chosen = min(future, key=lambda t: t.valid_from or date.max)
        direction = "미래"

    return chosen, TariffFallbackNotice(
        kind=kind,
        requested=when,
        used_table=chosen.name,
        used_from=chosen.valid_from,
        used_to=chosen.valid_to,
        direction=direction,
    )


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
            raise ValidationError(
                field="tariff.residential_kwh",
                reason=f"사용량이 음수입니다: {kwh!r}",
                action="사용량(kWh)을 0 이상 값으로 입력하십시오",
            )
        table, notice = self._catalog.select_residential(when)
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
        return BillBreakdown(tuple(lines), notices=() if notice is None else (notice,))

    def bill_tou(self, usages: Iterable[TouUsage], *, when: date) -> BillBreakdown:
        table, notice = self._catalog.select_tou(when)
        assert isinstance(table, TouTariffTable)
        energy_raw: dict[str, Decimal] = {}
        rate_keys: dict[str, str] = {}
        discount_raw: dict[str, Decimal] = {}
        discount_keys: dict[str, str] = {}

        for usage in usages:
            if usage.kwh < 0:
                raise ValidationError(
                    field="tariff.tou_kwh",
                    reason=f"사용량이 음수입니다: {usage.kwh!r}",
                    action="사용량(kWh)을 0 이상 값으로 입력하십시오",
                )
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
        return BillBreakdown(tuple(lines), notices=() if notice is None else (notice,))

    def bill_direct_trade(self, kwh: float, *, when: date) -> BillBreakdown:
        if kwh < 0:
            raise ValidationError(
                field="tariff.direct_trade_kwh",
                reason=f"사용량이 음수입니다: {kwh!r}",
                action="사용량(kWh)을 0 이상 값으로 입력하십시오",
            )
        table, notice = self._catalog.select_direct_trade(when)
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
        return BillBreakdown(tuple(lines), notices=() if notice is None else (notice,))

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
        """스텝별 단가 신호 — 경고를 **의도적으로 버린다**.

        이 함수는 `DispatchContext` 의 가격 신호를 만드는 자리이고 스텝마다
        불린다(8760회). 경고를 실으면 같은 경고가 8760번 쌓이고, 그것은
        정보가 아니라 소음이다 — 같은 요금표 대체 사실은 청구서
        (`bill_tou`)가 한 번 나른다.
        """
        table, _ = self._catalog.select_tou(when)
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
