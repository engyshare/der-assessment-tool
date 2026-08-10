"""`ThermalLoad` 열부하 — WP-1e / spec FR-102-AC1.ThermalLoad.

난방·급탕 열부하. 입력은 두 갈래다 — **8760 열부하 시계열** 또는
**난방도일(HDD) 기반 추정** (`RC-TL-P1`: HDD × kWh/HDD).

**전기부하(`Load`)와 코드가 닮았지만 서로 import 하지 않는다.**
둘은 독립 자원이며(§16.3 파일 1개 = 자원 1종), 한쪽이 다른 쪽을 알면 구획이
한 몸이 되어 병렬 작업이 깨진다. 더 실질적으로는, 열부하만 있고 전기부하가
없는 모델(지역난방 기준선 등)이 성립하지 않게 된다. 중복은 그 대가다.

**히트펌프도 import 하지 않는다.** `RC-TL-P2` 열 수지는 「부하 = 공급 합」이라는
*산술*이지 히트펌프의 성질이 아니므로, 공급량을 **인자로 받아** 잔차만
계산한다 (`heat_balance_residual`). 자원이 다른 자원을 직접 참조하기 시작하면
디스패치 순서가 코어가 아니라 자원 안에 숨는다 (FR-302 는 그것을 엔진의
설정 가능한 우선순위로 두라고 요구한다).

부호 규약: 열부하는 **받아들이므로 음수**로 열 계열에 실린다. 히트펌프가 열을
+3,000 kWh 로 싣고 열부하가 −3,000 kWh 로 실려야 열 수지가 독립적으로 균형을
이룬다 (`RC-HP-P3` · 도메인 원칙 5-3).

`core.contracts` 밖의 `core` 하위 모듈을 import 하지 않는다 (NFR-208-AC1).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import ClassVar, Final

from core.contracts.der import DER, EOL_REPLACE, DispatchContext, DispatchResult
from core.contracts.units import (
    ENERGY_TOLERANCE_KWH,
    SECONDS_PER_HOUR,
    Money,
    Year,
    steps_per_year,
    to_won,
)

_DAYS_IN_MONTH: Final[tuple[int, ...]] = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MONTHS: Final[int] = 12
_DAYS_IN_YEAR: Final[int] = 365

#: 부속설비 1건 = (이름, 수명 년, 교체·취득비 원)
Subcomponent = tuple[str, int, float]


# ── 입력 정규화 도우미 ───────────────────────────────────────────────

def _month_bounds(total_steps: int) -> list[tuple[int, int]]:
    steps_per_day = total_steps // _DAYS_IN_YEAR
    bounds: list[tuple[int, int]] = []
    start = 0
    for days in _DAYS_IN_MONTH:
        end = start + days * steps_per_day
        bounds.append((start, end))
        start = end
    return bounds


def _check_non_negative(values: Sequence[float], *, label: str) -> None:
    for i, v in enumerate(values):
        if v < 0.0:
            raise ValueError(
                f"{label} 에 음수가 있습니다 (index {i}: {v}). 열부하는 소비량이며 "
                "부호는 `dispatch()` 가 붙입니다 — 입력에 음수를 넣으면 부호가 "
                "두 번 뒤집혀 열 공급으로 잡힙니다"
            )


def _check_amount(value: float, *, label: str) -> float:
    if value < 0.0:
        raise ValueError(f"{label}는 음수일 수 없습니다: {value}")
    return float(value)


def _check_rate(value: float, *, label: str, low: float, high: float) -> float:
    """비율은 코드 내부에서 0~1 소수다 (§7.5).

    상한을 두는 이유는 %를 정규화하지 않고 넘긴 입력을 잡기 위해서다.
    """
    if not low < value <= high:
        raise ValueError(
            f"{label}는 {low} 초과 {high} 이하 소수입니다: {value}. "
            "1.5%는 0.015 입니다 (§7.5 비율 — 코드 내부는 소수로 정규화)"
        )
    return float(value)


def _normalize_weights(weights: Sequence[float] | None) -> list[float] | None:
    """월별 배분 가중치 검증. **총량은 바꾸지 않고 모양만 정한다.**

    가중치가 연 총량까지 바꾸면 `RC-TL-P1` 의 2,000 kWh 오라클이 프로파일에
    따라 흔들리고, 그 순간 §13.2.3 기준값은 검증의 정박점이 아니게 된다.
    """
    if weights is None:
        return None
    values = [float(w) for w in weights]
    if len(values) != _MONTHS:
        raise ValueError(
            f"월 가중치는 12개월치입니다: {len(values)}개. 일부 달만 주면 "
            "나머지 달의 난방부하가 0이 되는데, 연 총량은 그대로라 눈에 띄지 않습니다"
        )
    _check_non_negative(values, label="월 가중치")
    if math.fsum(values) <= 0.0:
        raise ValueError(
            "월 가중치 합이 0 이하입니다. 연간 열부하를 배분할 곳이 없어 "
            "부하가 통째로 사라집니다"
        )
    return values


def _resolve_hdd_path(
    heating_degree_days: float | None, kwh_per_hdd: float | None
) -> float:
    """`RC-TL-P1`: 연간 열부하 = HDD × kWh/HDD."""
    if (heating_degree_days is None) != (kwh_per_hdd is None):
        raise ValueError(
            "난방도일 추정은 `heating_degree_days` 와 `kwh_per_hdd` 를 **함께** "
            "지정합니다. 한쪽만 주면 나머지를 기본값으로 채우게 되고, 그 기본값이 "
            "결과를 좌우하면서도 입력 어디에도 남지 않습니다"
        )
    hdd = _check_amount(float(heating_degree_days or 0.0), label="난방도일(HDD)")
    intensity = _check_amount(float(kwh_per_hdd or 0.0), label="HDD 원단위(kWh/HDD)")
    return hdd * intensity


def _expand(
    monthly: Sequence[float], total_steps: int
) -> list[float]:
    """월별 열부하 → 스텝별 시계열 (월 안에서는 균등).

    월 안의 시간대 분포까지 재현하려면 8760 시계열 경로를 쓴다 — 여기서
    임의의 일간 곡선을 지어내면 근거 없는 수치가 코드에 박힌다 (§15.1 방침).
    """
    series = [0.0] * total_steps
    for (start, end), energy in zip(_month_bounds(total_steps), monthly, strict=True):
        step_value = energy / (end - start)
        for i in range(start, end):
            series[i] = step_value
    return series


def _resolve_series(
    *,
    hourly_kwh: Sequence[float] | None,
    heating_degree_days: float | None,
    kwh_per_hdd: float | None,
    monthly_weights: Sequence[float] | None,
    total_steps: int,
) -> tuple[list[float], list[float]]:
    """두 입력 경로 중 **정확히 하나**를 골라 (스텝 시계열, 월별 합계)를 만든다."""
    hdd_given = heating_degree_days is not None or kwh_per_hdd is not None
    given = [hourly_kwh is not None, hdd_given]
    if sum(given) != 1:
        raise ValueError(
            "열부하 입력은 `hourly_kwh`(8760 시계열) 또는 난방도일 추정 "
            f"(`heating_degree_days`+`kwh_per_hdd`) 중 **하나**만 지정합니다 "
            f"(현재 {sum(given)}개). spec FR-102-AC1.ThermalLoad 의 두 경로입니다"
        )

    weights = _normalize_weights(monthly_weights)

    if hourly_kwh is not None:
        series = [float(v) for v in hourly_kwh]
        if len(series) != total_steps:
            raise ValueError(
                f"열부하 시계열 행수가 맞지 않습니다: {len(series)}행, "
                f"기대 {total_steps}행 (FR-301-AC3)"
            )
        _check_non_negative(series, label="열부하 시계열")
        monthly = [math.fsum(series[s:e]) for s, e in _month_bounds(total_steps)]
        return series, monthly

    annual = _resolve_hdd_path(heating_degree_days, kwh_per_hdd)
    if weights is None:
        # 균등 분포는 **자리 표시자**다. 연 총량 오라클(RC-TL-P1)은 맞지만
        # 계절성이 없으므로, 시간대별 계산을 하는 하류에는 반드시 가중치를 준다.
        weights = [float(d) for d in _DAYS_IN_MONTH]
    weight_sum = math.fsum(weights)
    monthly = [annual * w / weight_sum for w in weights]
    return _expand(monthly, total_steps), monthly


def _validate_subcomponents(items: Sequence[Subcomponent]) -> list[Subcomponent]:
    """부속설비의 독립 수명 (FR-104-AC4) — 순환펌프·열교환기 등."""
    validated: list[Subcomponent] = []
    for label, life, cost in items:
        if life < 1:
            raise ValueError(f"부속설비 `{label}` 수명은 1년 이상입니다: {life}")
        validated.append((str(label), int(life), _check_amount(cost, label=f"`{label}` 교체비")))
    return validated


class ThermalLoad(DER):
    """열부하 (FR-102-AC1.ThermalLoad).

    `tag` 는 spec 조항 ID `FR-102-AC1.ThermalLoad` 와 **같은 리터럴**이다.
    """

    tag: ClassVar[str] = "ThermalLoad"

    def __init__(
        self,
        *,
        name: str,
        dt: int = SECONDS_PER_HOUR,
        lifetime: int = 20,
        hourly_kwh: Sequence[float] | None = None,
        heating_degree_days: float | None = None,
        kwh_per_hdd: float | None = None,
        monthly_weights: Sequence[float] | None = None,
        annual_growth_rate: float = 0.0,
        capacity_kw: float = 0.0,
        unit_cost_won_per_kw: float = 0.0,
        incidental_cost_won: float = 0.0,
        vat_rate: float = 0.0,
        fixed_om_won_per_year: float = 0.0,
        variable_om_won_per_kwh: float = 0.0,
        escalation_rate: float = 0.0,
        subcomponents: Sequence[Subcomponent] = (),
        end_of_life_action: str = EOL_REPLACE,
    ) -> None:
        # 열부하도 열화하지 않는다 — 단열 성능 저하는 부하 *증가*이므로
        # `degradation_rate`(감소)로 표현할 수 없다. 증가율로 따로 둔다.
        super().__init__(
            name=name,
            dt=dt,
            lifetime=lifetime,
            degradation_rate=0.0,
            carries_heat=True,
            escalation_rate=escalation_rate,
            end_of_life_action=end_of_life_action,
        )
        self._steps = steps_per_year(dt)
        self._base_series, self._base_monthly = _resolve_series(
            hourly_kwh=hourly_kwh,
            heating_degree_days=heating_degree_days,
            kwh_per_hdd=kwh_per_hdd,
            monthly_weights=monthly_weights,
            total_steps=self._steps,
        )
        self._base_annual = math.fsum(self._base_monthly)

        self.annual_growth_rate = _check_rate(
            annual_growth_rate, label="연간 증가율", low=-1.0, high=1.0
        )
        self._capacity_kw = _check_amount(capacity_kw, label="정격 열용량")
        self._acquisition_won = (
            _check_amount(unit_cost_won_per_kw, label="단가") * self._capacity_kw
            + _check_amount(incidental_cost_won, label="부대비")
        )
        self._vat_rate = _check_rate(vat_rate, label="부가세율", low=-1.0, high=1.0)
        self._fixed_om_won = _check_amount(fixed_om_won_per_year, label="고정 O&M")
        self._variable_om_won_per_kwh = _check_amount(
            variable_om_won_per_kwh, label="변동 O&M 단가"
        )
        self._subcomponents = _validate_subcomponents(subcomponents)

    # ── 물리 (RC-TL-P1) ─────────────────────────────────────────────

    def growth_factor(self, *, year: int) -> float:
        """n년차 배율 `(1+g)^(n−1)`. 1년차 지수는 0이다."""
        return (1.0 + self.annual_growth_rate) ** (int(Year(year)) - 1)

    def annual_energy_kwh(self, *, year: int) -> float:
        """해당 연도 연간 열부하 (kWh_th, 양수 크기)."""
        return self._base_annual * self.growth_factor(year=year)

    def monthly_energy_kwh(self, *, year: int) -> list[float]:
        factor = self.growth_factor(year=year)
        return [v * factor for v in self._base_monthly]

    def step_series_kwh(self, *, year: int) -> list[float]:
        """스텝별 열부하 (kWh_th, **양수 크기**). 부호는 `dispatch()` 가 붙인다."""
        factor = self.growth_factor(year=year)
        return [v * factor for v in self._base_series]

    def dispatch(self, ctx: DispatchContext) -> DispatchResult:
        """한 해(또는 그 앞부분) 운전. 열 계열에 **음수**로 싣는다.

        전기 계열은 건드리지 않는다 — 히트펌프의 소비전력은 히트펌프가 싣는다.
        여기서 함께 실으면 같은 전력이 두 자원에서 계상된다.
        """
        series = self._window(ctx)
        zeros = DispatchResult.zeros(ctx.steps)
        return DispatchResult(
            electric=zeros.electric,
            heat=[-v for v in series],
            cool=zeros.cool,
            fuel=zeros.fuel,
        )

    # ── RC-TL-P2 열 수지 (FR-301-AC2) ───────────────────────────────

    def heat_balance_residual(
        self, ctx: DispatchContext, *, supplied_kwh: Sequence[Sequence[float]]
    ) -> list[float]:
        """스텝별 `공급 합 − 열부하` 잔차 (kWh).

        양수는 초과 공급, **음수는 미충족**이다. 잔차를 0으로 눌러 버리면
        정격이 모자란 히트펌프도 전 부하를 감당한 것으로 보이고, 그만큼의
        보조열원 연료비가 통째로 사라진다 (`RC-HP-X1` 과 짝).

        공급 시계열은 인자로 받는다 — 히트펌프·보일러를 import 하지 않기 위해
        서다(§16.1 W-5). 행수는 컨텍스트가 검사하므로(FR-301-AC3) 어긋난
        시각끼리 더해지는 일이 없다.
        """
        demand = self._window(ctx)
        for i, series in enumerate(supplied_kwh, start=1):
            ctx.check_series(series, name=f"열공급 시계열 #{i}")
        return [
            math.fsum(source[step] for source in supplied_kwh) - demand[step]
            for step in range(ctx.steps)
        ]

    def is_heat_balanced(
        self,
        ctx: DispatchContext,
        *,
        supplied_kwh: Sequence[Sequence[float]],
        tolerance: float = ENERGY_TOLERANCE_KWH,
    ) -> bool:
        """**전 스텝** 균형 여부 (NFR-102 · 1e-6 kWh).

        연 합계로 보면 여름에 남고 겨울에 모자란 공급도 통과한다.
        """
        return all(
            abs(r) < tolerance
            for r in self.heat_balance_residual(ctx, supplied_kwh=supplied_kwh)
        )

    # ── 편익 없음 (`RC-LD-B0` 과 같은 규칙) ─────────────────────────

    def value_streams(self) -> tuple[str, ...]:
        """**항상 빈 목록.** 열부하는 편익을 생성하지 않는다.

        「히트펌프로 바꿔 아낀 열비용」은 히트펌프의 편익(`RC-HP-B1`·`B2`)이며,
        열부하에도 붙이면 같은 절감이 두 번 계상된다 (FR-402-AC2.C).

        v1.1 계약이 기본 구현(빈 튜플)을 두었으므로 이제 **상속만으로 강제된다**.
        """
        return ()

    def baseline_energy_cost(self, *, year: int, tariff_won_per_kwh: float) -> Money:
        """무지원 기준선 열비용 (원/년) — FR-607 · FR-705.

        **편익이 아니라 비교의 바닥이다.** `RC-HP-B2` 가 요구하는 「기준선을
        명시적으로 산출·표시」의 그 기준선이며, 프로포마에서 편익 행이 아니라
        기준선 행으로 간다.
        """
        return to_won(
            self.annual_energy_kwh(year=year)
            * _check_amount(tariff_won_per_kwh, label="열 단가")
        )

    # ── 비용 5종 (RC-ALL-C1~C5 / §13.2.2) ───────────────────────────

    def capex(self, *, year: int) -> Money:
        """C-1: `단가 × 용량 + 부대비`. 부가세는 `capex_vat()` 로 분리한다."""
        return to_won(self._acquisition_won) if int(Year(year)) == 1 else Money(0)

    def capex_vat(self, *, year: int) -> Money:
        """부가세는 본체와 분리한다 — 관점별 취급이 다르다 (FR-704)."""
        if int(Year(year)) != 1:
            return Money(0)
        return to_won(self._acquisition_won * self._vat_rate)

    def fixed_om(self, *, year: int) -> Money:
        """C-2: `A × (1+i)^(n−1)`. 20년 누계는 등비수열 합이 된다."""
        return to_won(self._fixed_om_won * self.escalation_factor(year=year))

    def variable_om(self, *, year: int) -> Money:
        """C-3: `처리량 × 단가`. 열부하의 처리량은 **연간 열 소비 kWh_th** 다."""
        return to_won(
            self.annual_energy_kwh(year=year)
            * self._variable_om_won_per_kwh
            * self.escalation_factor(year=year)
        )

    def replacement_schedule(self, *, horizon: int) -> dict[int, Money]:
        """C-4: 수명 도달 **다음 연도 초**. 부속설비는 독립 스케줄 (FR-104-AC4).

        **FR-104-AC3**: `retire` 선택 시 빈 스케줄을 돌려준다.
        """
        if horizon < 1:
            raise ValueError(f"분석기간은 1년 이상입니다: {horizon}")

        # retire 선택 시 본체도 부속설비도 아무것도 교체하지 않는다
        if self.retires_at_end_of_life():
            return {}

        schedule: dict[int, Money] = {}
        for _label, life, cost in self._components():
            if cost <= 0.0:
                continue
            year = life + 1
            while year <= horizon:
                amount = to_won(cost * self.escalation_factor(year=year))
                schedule[year] = Money(schedule.get(year, Money(0)) + amount)
                year += life
        return schedule

    def salvage_value(self, *, year: int) -> Money:
        """C-5: `취득가 × 잔존수명/총수명` (FR-104-AC5). **할인하지 않는다.**

        자원은 할인율을 모른다(FR-101-AC3). 자원과 재무 계층 두 곳에서 할인하면
        어느 쪽이 이미 했는지 판정할 수 없다.
        """
        n = int(Year(year))
        total = 0.0
        for _label, life, cost in self._components():
            remaining = life - ((n - 1) % life) - 1
            total += cost * remaining / life
        return to_won(total)

    # ── 내부 ────────────────────────────────────────────────────────

    def _window(self, ctx: DispatchContext) -> list[float]:
        """컨텍스트가 요구한 스텝 수만큼 연초부터 잘라 돌려준다.

        해상도가 다르면 같은 인덱스가 서로 다른 시각을 가리키므로 거부한다.
        """
        if ctx.dt != self.dt:
            raise ValueError(
                f"{self.name}: 컨텍스트 해상도({ctx.dt}초)가 자원 해상도"
                f"({self.dt}초)와 다릅니다 (FR-301-AC3)"
            )
        if ctx.steps > self._steps:
            raise ValueError(
                f"{self.name}: 요청 스텝 수 {ctx.steps} 가 연간 스텝 수 "
                f"{self._steps} 를 넘습니다. 열부하 시계열은 1년치입니다"
            )
        return self.step_series_kwh(year=int(ctx.year))[: ctx.steps]

    def _components(self) -> list[Subcomponent]:
        return [("본체", self.lifetime, self._acquisition_won), *self._subcomponents]
