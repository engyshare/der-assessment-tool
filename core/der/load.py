"""`Load` 전기부하 — WP-1e / spec FR-102-AC1.Load.

가구·공용부·상업 전기부하. 입력은 두 갈래다 — **8760 부하 시계열** 또는
**월사용량 + 표준 프로파일** (Q-3 이 실측 확보 전까지 후자를 쓰기로 한 그 경로).

**부하 자원이 다른 자원과 다른 세 가지.**

1. **부호가 음수다.** `DispatchResult` 규약은 양수=내보냄, 음수=받아들임이다.
   부하를 양수로 실으면 발전과 더해져 조용히 상쇄된다 — 4,200 kWh 부하를
   양수로 두면 4,200 kWh PV 와 합쳐져 순 8,400 kWh 발전으로 보인다.

2. **편익을 만들지 않는다** (`RC-LD-B0`). 부하가 산출하는 것은 *기준선 요금*
   이지 편익이 아니다. 「부하가 줄어 생긴 절감」은 그 절감을 일으킨 자원(PV
   자가소비·히트펌프)의 편익이며, 부하에도 붙이면 같은 화폐 흐름이 두 번
   계상된다 (FR-402-AC2.C 동일 효과의 이중 화폐화). 그래서 `value_streams()`
   는 **비어 있는 것이 정답**이며, 그 사실을 테스트가 고정한다.

3. **열화하지 않고 성장한다.** 계약의 `degradation_rate` 는 0~1 소수이고
   *감소*를 뜻하므로(FR-101-AC1 · §7.5), 반대 방향인 연간 증가율을 거기에
   실을 수 없다. `degradation_rate=0.0` 으로 고정하고 `annual_growth_rate`
   를 따로 둔다.

`core.contracts` 밖의 `core` 하위 모듈을 import 하지 않는다 (NFR-208-AC1).
형제 자원(`core.der.thermal_load` 등)도 마찬가지다 — 자원끼리 알면 구획이
한 몸이 되어 병렬 작업과 부분 모델 구성이 함께 깨진다.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import ClassVar, Final

from core.contracts.der import DER, DispatchContext, DispatchResult
from core.contracts.units import (
    SECONDS_PER_HOUR,
    Money,
    Year,
    steps_per_year,
    to_won,
)

#: 평년 기준. 윤년을 쓰지 않는 이유는 8760/35040 이라는 스텝 수 규약 자체가
#: 평년 전제이기 때문이다 — 여기서만 366일을 쓰면 마지막 하루가 갈 곳을 잃는다.
_DAYS_IN_MONTH: Final[tuple[int, ...]] = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MONTHS: Final[int] = 12
_DAYS_IN_YEAR: Final[int] = 365

#: 부속설비 1건 = (이름, 수명 년, 교체·취득비 원)
Subcomponent = tuple[str, int, float]


# ── 입력 정규화 도우미 ───────────────────────────────────────────────

def _month_bounds(total_steps: int) -> list[tuple[int, int]]:
    """월별 [시작, 끝) 스텝 인덱스."""
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
                f"{label} 에 음수가 있습니다 (index {i}: {v}). 부하는 소비량이며 "
                "부호는 `dispatch()` 가 붙입니다 — 입력에 음수를 넣으면 부호가 "
                "두 번 뒤집혀 발전으로 잡힙니다"
            )


def _check_length(values: Sequence[float], expected: int, *, label: str) -> None:
    if len(values) != expected:
        raise ValueError(
            f"{label} 행수가 맞지 않습니다: {len(values)}행, 기대 {expected}행. "
            "조용히 자르거나 채우면 어느 시각이 어긋났는지 영영 모릅니다 (FR-301-AC3)"
        )


def _normalize_monthly(monthly_kwh: float | Sequence[float]) -> list[float]:
    """스칼라(매월 동일) 또는 12개월 목록 → 12개 값."""
    if isinstance(monthly_kwh, (int, float)):
        values = [float(monthly_kwh)] * _MONTHS
    else:
        values = [float(v) for v in monthly_kwh]
        if len(values) != _MONTHS:
            raise ValueError(
                f"월사용량은 12개월치입니다: {len(values)}개. "
                "계절성이 있는 부하를 일부 달만 주면 나머지 달이 0이 됩니다"
            )
    _check_non_negative(values, label="월사용량")
    return values


def _expand_monthly(
    monthly: Sequence[float], shape: Sequence[float] | None, total_steps: int
) -> list[float]:
    """월사용량 → 스텝별 시계열. **월 총량을 각각 보존한다.**

    프로파일 가중치를 연 전체로 한 번에 정규화하지 않는 이유: 가중치가 큰 달이
    다른 달의 사용량을 빨아들여도 **연 합계는 그대로**라 눈에 띄지 않는다.
    월별로 정규화하면 그 경로가 막힌다.
    """
    series = [0.0] * total_steps
    for (start, end), energy in zip(_month_bounds(total_steps), monthly, strict=True):
        if shape is None:
            step_value = energy / (end - start)
            for i in range(start, end):
                series[i] = step_value
            continue
        weights = shape[start:end]
        weight_sum = math.fsum(weights)
        if weight_sum <= 0.0:
            raise ValueError(
                f"표준 프로파일의 {start}~{end} 구간 가중치 합이 0 이하입니다. "
                "그 달의 사용량을 배분할 곳이 없어 통째로 사라집니다"
            )
        for offset, w in enumerate(weights):
            series[start + offset] = energy * w / weight_sum
    return series


def _resolve_series(
    *,
    hourly_kwh: Sequence[float] | None,
    monthly_kwh: float | Sequence[float] | None,
    shape: Sequence[float] | None,
    total_steps: int,
) -> tuple[list[float], list[float]]:
    """두 입력 경로 중 **정확히 하나**를 골라 (스텝 시계열, 월별 합계)를 만든다.

    둘 다 주면 어느 쪽이 채택됐는지 결과만 보고는 알 수 없고, 둘 다 없으면
    0 kWh 부하가 조용히 성립해 기준선 요금이 통째로 사라진다.
    """
    given = [hourly_kwh is not None, monthly_kwh is not None]
    if sum(given) != 1:
        raise ValueError(
            "부하 입력은 `hourly_kwh`(8760 시계열) 또는 `monthly_kwh`(월사용량) "
            f"중 **하나**만 지정합니다 (현재 {sum(given)}개). "
            "spec FR-102-AC1.Load 가 허용하는 두 경로입니다"
        )

    if shape is not None:
        _check_length(shape, total_steps, label="표준 프로파일")
        _check_non_negative(shape, label="표준 프로파일")

    if hourly_kwh is not None:
        series = [float(v) for v in hourly_kwh]
        _check_length(series, total_steps, label="부하 시계열")
        _check_non_negative(series, label="부하 시계열")
        bounds = _month_bounds(total_steps)
        monthly = [math.fsum(series[s:e]) for s, e in bounds]
        return series, monthly

    monthly = _normalize_monthly(monthly_kwh)  # type: ignore[arg-type]
    return _expand_monthly(monthly, shape, total_steps), monthly


def _check_rate(value: float, *, label: str, low: float, high: float) -> float:
    """비율은 코드 내부에서 0~1 소수다 (§7.5).

    상한을 두는 이유는 %를 정규화하지 않고 넘긴 입력을 잡기 위해서다 —
    연 2%를 `2.0` 으로 주면 20년 뒤 부하가 3.5억 배가 되는데, 중간 어디에도
    오류가 나지 않는다.
    """
    if not low < value <= high:
        raise ValueError(
            f"{label}는 {low} 초과 {high} 이하 소수입니다: {value}. "
            "2%는 0.02 입니다 (§7.5 비율 — 코드 내부는 소수로 정규화)"
        )
    return float(value)


def _check_amount(value: float, *, label: str) -> float:
    if value < 0.0:
        raise ValueError(f"{label}는 음수일 수 없습니다: {value}")
    return float(value)


class Load(DER):
    """전기부하 (FR-102-AC1.Load).

    `tag` 는 spec 조항 ID `FR-102-AC1.Load` 와 **같은 리터럴**이다. 여기서
    슬러그화하거나 대소문자를 바꾸면 NFR-106 레지스트리 순회 검사가 헛돈다.
    """

    tag: ClassVar[str] = "Load"

    def __init__(
        self,
        *,
        name: str,
        dt: int = SECONDS_PER_HOUR,
        lifetime: int = 20,
        hourly_kwh: Sequence[float] | None = None,
        monthly_kwh: float | Sequence[float] | None = None,
        shape: Sequence[float] | None = None,
        annual_growth_rate: float = 0.0,
        capacity_kw: float = 0.0,
        unit_cost_won_per_kw: float = 0.0,
        incidental_cost_won: float = 0.0,
        vat_rate: float = 0.0,
        fixed_om_won_per_year: float = 0.0,
        variable_om_won_per_kwh: float = 0.0,
        escalation_rate: float = 0.0,
        subcomponents: Sequence[Subcomponent] = (),
    ) -> None:
        # 부하는 열화하지 않는다 — `degradation_rate` 는 감소를 뜻하므로 성장을
        # 실을 수 없다. 생성자 인자로도 열어 두지 않는다(열면 반드시 쓰인다).
        super().__init__(
            name=name,
            dt=dt,
            lifetime=lifetime,
            degradation_rate=0.0,
            carries_electric=True,
            escalation_rate=escalation_rate,
        )
        self._steps = steps_per_year(dt)
        self._base_series, self._base_monthly = _resolve_series(
            hourly_kwh=hourly_kwh,
            monthly_kwh=monthly_kwh,
            shape=shape,
            total_steps=self._steps,
        )
        self._base_annual = math.fsum(self._base_monthly)

        self.annual_growth_rate = _check_rate(
            annual_growth_rate, label="연간 증가율", low=-1.0, high=1.0
        )
        self._capacity_kw = _check_amount(capacity_kw, label="계약전력")
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

    # ── 물리 (RC-LD-P1 · P2) ────────────────────────────────────────

    def growth_factor(self, *, year: int) -> float:
        """n년차 배율 `(1+g)^(n−1)`. **1년차 지수는 0** 이다.

        `Year` 로 검증하는 이유: 0-base 인덱스를 그대로 넘기면 배율이 한 해분
        어긋나는데, 연 2%에서 20년 뒤 2% 차이는 눈으로 잡히지 않는다.
        """
        return (1.0 + self.annual_growth_rate) ** (int(Year(year)) - 1)

    def annual_energy_kwh(self, *, year: int) -> float:
        """해당 연도 연간 소비 (kWh, 양수 크기)."""
        return self._base_annual * self.growth_factor(year=year)

    def monthly_energy_kwh(self, *, year: int) -> list[float]:
        factor = self.growth_factor(year=year)
        return [v * factor for v in self._base_monthly]

    def step_series_kwh(self, *, year: int) -> list[float]:
        """스텝별 소비량 (kWh, **양수 크기**). 부호는 `dispatch()` 가 붙인다."""
        factor = self.growth_factor(year=year)
        return [v * factor for v in self._base_series]

    def dispatch(self, ctx: DispatchContext) -> DispatchResult:
        """한 해(또는 그 앞부분) 운전. 전기 계열에 **음수**로 싣는다."""
        self.check_context(ctx)
        if ctx.steps > self._steps:
            raise ValueError(
                f"{self.name}: 요청 스텝 수 {ctx.steps} 가 연간 스텝 수 "
                f"{self._steps} 를 넘습니다. 부하 시계열은 1년치이므로 그 너머는 "
                "채울 근거가 없습니다"
            )
        series = self.step_series_kwh(year=int(ctx.year))
        result = DispatchResult.zeros(ctx.steps)
        # 부호 규약: 음수 = 받아들임(소비). 여기서 뒤집으면 합산에서 상쇄된다
        return DispatchResult(
            electric=[-v for v in series[: ctx.steps]],
            heat=result.heat,
            cool=result.cool,
            fuel=result.fuel,
        )

    # ── 편익 (RC-LD-B0) ─────────────────────────────────────────────

    def value_streams(self) -> tuple[str, ...]:
        """**항상 빈 목록.** 부하는 편익을 생성하지 않는다 (`RC-LD-B0`).

        여기에 무엇이든 넣는 순간 다른 자원의 편익을 이중 계상하게 된다.
        **v1.1 개정으로 이 메서드는 계약이 요구하는 것이 되었다.** v1.0 계약에는
        훅이 없어 이 선언이 자원의 성실성에 달려 있었다 — 다른 누군가가 부하에
        편익을 붙이는 것을 아무 장치도 막지 않았다. 이제 기본 구현이 빈 튜플이므로
        **상속만으로 강제된다**.
        """
        return ()

    def baseline_energy_cost(
        self, *, year: int, tariff_won_per_kwh: float
    ) -> Money:
        """무지원 기준선 요금 (원/년) — FR-607.

        **편익이 아니다.** 이 값은 비교의 바닥이며, 프로포마에서 편익 행이
        아니라 기준선 행으로 간다. 요금단가를 인자로 받는 이유는 연도별 인상
        전망(Q-5b)이 자원이 아니라 가정집합의 소관이기 때문이다.
        """
        return to_won(
            self.annual_energy_kwh(year=year)
            * _check_amount(tariff_won_per_kwh, label="요금단가")
        )

    # ── 비용 5종 (RC-ALL-C1~C5 / §13.2.2) ───────────────────────────

    def capex(self, *, year: int) -> Money:
        """C-1: `단가 × 용량 + 부대비`. 부가세는 `capex_vat()` 로 분리한다."""
        return to_won(self._acquisition_won) if int(Year(year)) == 1 else Money(0)

    def capex_vat(self, *, year: int) -> Money:
        """부가세를 본체와 **분리**한다.

        섞으면 관점별 계상(FR-704)에서 떼어낼 수 없다 — 사업자에게는 매입세액
        공제 대상이고 사회 관점에서는 이전지출이므로 취급이 다르다.
        """
        if int(Year(year)) != 1:
            return Money(0)
        return to_won(self._acquisition_won * self._vat_rate)

    def fixed_om(self, *, year: int) -> Money:
        """C-2: `A × (1+i)^(n−1)`. 20년 누계는 등비수열 합이 된다."""
        return to_won(self._fixed_om_won * self.escalation_factor(year=year))

    def variable_om(self, *, year: int) -> Money:
        """C-3: `처리량 × 단가`. 부하의 처리량은 **연간 소비 kWh** 다."""
        return to_won(
            self.annual_energy_kwh(year=year)
            * self._variable_om_won_per_kwh
            * self.escalation_factor(year=year)
        )

    def replacement_schedule(self, *, horizon: int) -> dict[int, Money]:
        """C-4: 수명 도달 **다음 연도 초**에 계상. 부속설비는 독립 스케줄.

        한 해 밀리면 할인 계수가 한 해분 달라진다 — 교체비 300만원이면 4.5%
        할인율에서 13만원가량이 조용히 이동한다 (도메인 원칙 4-3).
        """
        if horizon < 1:
            raise ValueError(f"분석기간은 1년 이상입니다: {horizon}")
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
        """C-5: `취득가 × 잔존수명/총수명` 을 최종연도에 계상 (FR-104-AC5).

        **할인하지 않는다.** 자원은 할인율을 모르며(FR-101-AC3), 할인을 자원과
        재무 계층 두 곳에서 하면 어느 쪽이 이미 했는지 판정할 수 없다.

        나이를 `(year−1) % life` 로 세는 이유: 교체가 있었다면 잔존가치는
        **새로 설치된 개체**의 것이다. 최초 취득 시점만 보면 교체분의 잔존가치가
        통째로 사라진다.
        """
        n = int(Year(year))
        total = 0.0
        for _label, life, cost in self._components():
            remaining = life - ((n - 1) % life) - 1
            total += cost * remaining / life
        return to_won(total)

    # ── 내부 ────────────────────────────────────────────────────────

    def _components(self) -> list[Subcomponent]:
        """본체 + 부속설비. 본체를 같은 목록에 넣어 수명 계산을 한 곳에 모은다."""
        return [("본체", self.lifetime, self._acquisition_won), *self._subcomponents]


def _validate_subcomponents(items: Sequence[Subcomponent]) -> list[Subcomponent]:
    """부속설비의 독립 수명 (FR-104-AC4).

    본체 수명만 보면 20년 분석에서 12년짜리 부속설비 교체비가 통째로 빠진다.
    """
    validated: list[Subcomponent] = []
    for item in items:
        label, life, cost = item
        if life < 1:
            raise ValueError(f"부속설비 `{label}` 수명은 1년 이상입니다: {life}")
        validated.append((str(label), int(life), _check_amount(cost, label=f"`{label}` 교체비")))
    return validated
