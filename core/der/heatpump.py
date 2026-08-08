"""`HeatPump` 히트펌프 (난방/급탕) — 작업 WP-1d / spec FR-102-AC1.HeatPump.

**이 자원이 다른 자원과 다른 점은 매체를 둘 걸친다는 것이다.** 전기를
받아들여 열을 내보내므로 `carries_electric` 과 `carries_heat` 가 **둘 다
참**이고, 한 번의 `dispatch()` 가 두 수지에 동시에 값을 싣는다 — RC-HP-P3 은
COP 3.0·열부하 3,000 kWh 에서 전기 −1,000 kWh, 열 +3,000 kWh 를 요구한다.
두 값을 한 계열에 섞으면 합(2,000 kWh)은 남지만 "전기를 얼마 썼고 열을 얼마
냈는가"가 사라지며, 그 상태로도 NFR-102 균형 검사는 통과한다 — 총량은 맞기
때문이다. 그래서 계열을 절대 섞지 않고, 부호 규약(양수=내보냄, 음수=받아들임)에
따라 **전기는 음수, 열은 양수**로 싣는다.

설계상의 선택 셋: ① 정의역 밖 COP는 클램프한다 — 외삽하면 −30 ℃에서 COP가 0
이하가 되어 소비전력이 발산한다. ② 못 채운 열부하는 미충족으로 남긴다
(RC-HP-X1) — 열 수지에 실으면 열비용 절감 편익이 부풀려지는데 화면상으로는
정상으로 보인다. ③ 기준선을 결과에 남긴다 (FR-705-AC1) — 차액만 돌려주면
"무엇에 대비한 절감인가"가 사라진다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise
from typing import ClassVar

from core.contracts.der import DER, DispatchContext, DispatchResult
from core.contracts.units import (
    ENERGY_TOLERANCE_KWH,
    SECONDS_PER_HOUR,
    Money,
    steps_per_year,
    to_won,
    won_sum,
)

# spec FR-105-AC1 이 HeatPump 예시로 열거한 세 가지를 **리터럴 그대로** 둔다.
# 여기서 이름을 다시 지으면 spec 조항과 코드가 갈리고, 갈린 것은 아무도 모른다.
MODE_LOAD_FOLLOWING = "열부하 추종"
MODE_NIGHT_STORAGE = "축열조 활용 심야 운전"
MODE_PRICE_LINKED = "전력요금 연동"

#: 축열조 심야 운전의 기본 운전 시간대(시). 23시~익일 7시.
DEFAULT_NIGHT_HOURS: tuple[int, ...] = (23, 0, 1, 2, 3, 4, 5, 6, 7)
#: 보조 전기 히터는 저항가열이므로 COP 1.0이다.
AUX_HEATER_COP = 1.0

_SECONDS_PER_DAY = 86_400
CopCurve = float | int | Mapping[float, float] | Sequence[tuple[float, float]]


@dataclass(frozen=True)
class HeatBaseline:
    """설비 미설치 시의 기존 열원 — FR-705-AC1 비교 대조군.

    자료구조로 받는 이유: 같은 히트펌프라도 전기보일러 대비냐 가스보일러 대비냐에
    따라 절감액이 두 배 이상 갈린다 (RC-HP-B1 300,000원 vs B2 132,353원).
    """

    label: str
    #: 열효율 (전기보일러 1.0, 가스보일러 0.85 등)
    efficiency: float
    #: 연료(또는 전력) 단가 — 원/kWh **연료 기준**. 열 기준이 아니다
    fuel_price_won_per_kwh: float

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("기준선에는 이름이 필요합니다 — '무엇 대비 절감인가'를 "
                             "표시하지 못하면 증분 분석의 전제가 사라집니다 (FR-705-AC1)")
        if self.efficiency <= 0.0:
            raise ValueError(f"{self.label}: 열효율은 0보다 커야 합니다: {self.efficiency}")
        if self.fuel_price_won_per_kwh < 0.0:
            raise ValueError(f"{self.label}: 연료단가가 음수입니다")

    def cost_for_heat(self, heat_kwh: float) -> Money:
        """같은 열량을 기존 열원으로 공급했을 때의 연료비."""
        return to_won(heat_kwh / self.efficiency * self.fuel_price_won_per_kwh)


@dataclass(frozen=True)
class HeatCostSaving:
    """열비용 절감 편익 (FR-401-AC2.HeatCostSaving). **차액만 담지 않는다** —
    기준선 비용과 신규 전기요금을 함께 남겨야 증분의 근거를 되짚을 수 있다.
    """

    baseline_label: str
    baseline_heat_kwh: float
    baseline_cost: Money
    hp_electricity_kwh: float
    hp_electricity_cost: Money
    saving: Money


@dataclass(frozen=True)
class HeatPumpOperation:
    """한 해 운전 결과 — 디스패치 시계열과 **집계·진단값**을 함께 담는다.

    `dispatch()` 는 계약상 `DispatchResult` 만 돌려주므로 미충족 열량을 실을 자리가
    없다. 남기지 않으면 정격 초과 요구가 조용히 사라진다 (RC-HP-X1).
    """

    result: DispatchResult
    heat_demand_kwh: float
    hp_heat_kwh: float
    aux_heat_kwh: float
    electricity_kwh: float
    unmet_heat_kwh: float

    @property
    def heat_supplied_kwh(self) -> float:
        return self.hp_heat_kwh + self.aux_heat_kwh

    @property
    def unmet(self) -> bool:
        """열부하 미충족 플래그. NFR-102 허용 오차를 넘는 부족분만 참이다."""
        return self.unmet_heat_kwh > ENERGY_TOLERANCE_KWH


def _normalize_cop_curve(curve: CopCurve) -> tuple[tuple[float, float], ...]:
    """COP 곡선을 외기온 오름차순 격자점으로 정규화한다. 스칼라를 허용하는 이유는
    RC-HP-P1(COP 고정값) 때문이다 — 격자점 1개는 클램프되어 전 구간 상수가 된다.
    """
    if isinstance(curve, bool):
        raise TypeError("COP 곡선에 bool 을 넣을 수 없습니다")
    if isinstance(curve, (int, float)):
        points = [(0.0, float(curve))]
    elif isinstance(curve, Mapping):
        points = [(float(t), float(c)) for t, c in curve.items()]
    else:
        points = [(float(t), float(c)) for t, c in curve]

    if not points:
        raise ValueError("COP 곡선이 비어 있습니다 — 소비전력을 계산할 수 없습니다")
    points.sort()

    temps = [t for t, _ in points]
    if len(set(temps)) != len(temps):
        raise ValueError(f"COP 곡선에 같은 외기온이 두 번 나옵니다: {temps}")
    for temp, cop in points:
        if cop <= 0.0:
            raise ValueError(f"COP 가 0 이하입니다 ({temp}℃ → {cop}). 소비전력은 열량을 "
                             "COP로 나눈 값이므로 발산하거나 음수가 됩니다")
    return tuple(points)


def _annual_tuple(
    series: Sequence[float] | None, *, dt: int, name: str
) -> tuple[float, ...] | None:
    """비용 산정용 시계열이 **1년치**임을 확인한 뒤 고정한다. 연간 합계를 내는
    자리에 24행짜리가 들어오면 변동 O&M과 편익이 365분의 1로 조용히 줄어든다.
    """
    if series is None:
        return None
    expected = steps_per_year(dt)
    if len(series) != expected:
        raise ValueError(f"{name} 는 1년치 시계열이어야 합니다: {len(series)}행, "
                         f"기대 {expected}행")
    return tuple(float(v) for v in series)


class HeatPump(DER):
    """히트펌프 — 전기를 받아들여 열을 공급한다 (FR-102-AC1.HeatPump). 파라미터 축은
    spec 조항이 열거한 셋이다: **정격 열출력(kW)**, **COP 곡선(외기온 함수)**,
    **열부하 대응 방식**(= 운전 방법 + 보조 열원).
    """

    #: spec 조항 ID `FR-102-AC1.HeatPump` 의 키와 **같은 리터럴**이다. 대소문자를
    #: 바꾸면 NFR-106 레지스트리 순회 검사가 다른 키를 찾게 된다.
    tag: ClassVar[str] = "HeatPump"

    #: FR-105-AC1 — 자원 클래스가 자신이 지원하는 운전 방법을 선언한다.
    operating_modes: ClassVar[tuple[str, ...]] = (
        MODE_LOAD_FOLLOWING, MODE_NIGHT_STORAGE, MODE_PRICE_LINKED,
    )

    def __init__(
        self,
        *,
        # ── 물리 (FR-102-AC1.HeatPump) ──
        name: str,
        rated_heat_kw: float,
        cop_curve: CopCurve,
        heat_load_kwh: float | Sequence[float],
        # ── 열부하 대응 방식 (FR-105-AC1) ──
        mode: str = MODE_LOAD_FOLLOWING,
        aux_heater_kw: float = 0.0,
        night_hours: Sequence[int] = DEFAULT_NIGHT_HOURS,
        price_profile_won_per_kwh: Sequence[float] | None = None,
        price_linked_hours: int = 8,
        annual_ambient_temp_c: Sequence[float] | None = None,
        default_ambient_temp_c: float = 7.0,
        # ── 재무 (§13.2.2 RC-ALL-C1~C5) ──
        elec_price_won_per_kwh: float = 0.0,
        capex_unit_won_per_kw: float = 0.0, capex_extra_won: float = 0.0, vat_rate: float = 0.1,
        fixed_om_won: float = 0.0, om_escalation: float = 0.0,
        variable_om_won_per_kwh: float = 0.0,
        replacement_cost_won: float | None = None,
        pump_lifetime: int | None = None, pump_replacement_cost_won: float = 0.0,
        dt: int = SECONDS_PER_HOUR, lifetime: int = 15, degradation_rate: float = 0.0,
    ) -> None:
        # 전기·열 **둘 다** 참이다. 하나만 켜면 나머지 매체의 값이 어느 수지에도
        # 잡히지 않고 사라진다 (FR-101-AC4).
        super().__init__(name=name, dt=dt, lifetime=lifetime,
                         degradation_rate=degradation_rate,
                         carries_electric=True, carries_heat=True)

        if rated_heat_kw <= 0.0:
            raise ValueError(f"{name}: 정격 열출력은 0보다 커야 합니다: {rated_heat_kw}")
        if aux_heater_kw < 0.0:
            raise ValueError(f"{name}: 보조 열원 정격이 음수입니다: {aux_heater_kw}")
        if mode not in self.operating_modes:
            raise ValueError(f"{name}: 지원하지 않는 운전 방법입니다: {mode!r}. "
                             f"지원 목록: {list(self.operating_modes)} (FR-105-AC1)")
        if mode == MODE_PRICE_LINKED and price_profile_won_per_kwh is None:
            # 조용히 열부하 추종으로 되돌리면 사용자는 요금 연동으로 돌았다고 믿는다
            raise ValueError(f"{name}: 전력요금 연동 운전에는 요금 시계열이 필요합니다")
        if price_linked_hours <= 0:
            raise ValueError(f"{name}: 요금 연동 운전 시간은 1시간 이상입니다")

        self.rated_heat_kw = float(rated_heat_kw)
        self.cop_curve = _normalize_cop_curve(cop_curve)
        self.mode = mode
        self.aux_heater_kw = float(aux_heater_kw)
        self.night_hours = frozenset(int(h) for h in night_hours)
        self.price_linked_hours = int(price_linked_hours)
        self.default_ambient_temp_c = float(default_ambient_temp_c)
        self.price_profile_won_per_kwh = _annual_tuple(
            price_profile_won_per_kwh, dt=dt, name="price_profile_won_per_kwh")
        self.annual_ambient_temp_c = _annual_tuple(
            annual_ambient_temp_c, dt=dt, name="annual_ambient_temp_c")
        self._load_profile, self._annual_load_kwh = self._normalize_heat_load(heat_load_kwh)

        self.elec_price_won_per_kwh = float(elec_price_won_per_kwh)
        self.capex_unit_won_per_kw = float(capex_unit_won_per_kw)
        self.capex_extra_won = float(capex_extra_won)
        self.vat_rate = float(vat_rate)
        self.fixed_om_won = float(fixed_om_won)
        self.om_escalation = float(om_escalation)
        self.variable_om_won_per_kwh = float(variable_om_won_per_kwh)
        self.pump_lifetime = int(pump_lifetime) if pump_lifetime else None
        self.pump_replacement_cost_won = float(pump_replacement_cost_won)

        # 교체비를 따로 주지 않으면 본체 취득원가로 본다 — 부대비(설계·인허가)는
        # 교체 시 다시 들지 않는 것이 통례다.
        self._body_won = self.capex_unit_won_per_kw * self.rated_heat_kw
        self._acquisition_won = self._body_won + self.capex_extra_won
        self.replacement_cost_won = (
            float(replacement_cost_won) if replacement_cost_won is not None else self._body_won)

        # 연간 운전은 비용·편익 산정에서 반복 호출되므로 연도별로 한 번만 푼다.
        self._annual_ops: dict[int, HeatPumpOperation] = {}

    def _normalize_heat_load(
        self, heat_load_kwh: float | Sequence[float]
    ) -> tuple[tuple[float, ...] | None, float]:
        """열부하를 (스텝별 프로파일, 연간 총량)으로 정규화한다. 스칼라는 연간
        총량이라 **균등 배분**하고, 프로파일은 1년치로 보아 그대로 쓴다.
        """
        if isinstance(heat_load_kwh, (int, float)) and not isinstance(heat_load_kwh, bool):
            if heat_load_kwh < 0.0:
                raise ValueError(f"{self.name}: 연간 열부하가 음수입니다: {heat_load_kwh}")
            return None, float(heat_load_kwh)

        profile = tuple(float(v) for v in heat_load_kwh)
        _annual_tuple(profile, dt=self.dt, name="heat_load_kwh")
        if any(v < 0.0 for v in profile):
            raise ValueError(f"{self.name}: 열부하 시계열에 음수가 있습니다")
        return profile, float(sum(profile))

    def cop_at(self, temp_c: float, *, year: int = 1) -> float:
        """외기온 → COP (RC-HP-P2). 격자점 일치·격자 사이 선형보간·정의역 밖 클램프.
        `year` 를 받는 이유는 성능 저하(FR-104-AC1)가 연도별로 걸리기 때문이다 —
        열화된 COP는 같은 열을 내는 데 더 많은 전력을 요구한다.
        """
        if year < 1:
            raise ValueError(f"분석 연도는 1부터 셉니다: {year}")

        points = self.cop_curve
        if temp_c <= points[0][0]:
            base = points[0][1]
        elif temp_c >= points[-1][0]:
            base = points[-1][1]
        else:
            base = points[-1][1]
            for (t0, c0), (t1, c1) in pairwise(points):
                if t0 <= temp_c <= t1:
                    base = c0 + (c1 - c0) * (temp_c - t0) / (t1 - t0)
                    break
        return base * (1.0 - self.degradation_rate) ** (year - 1)

    def dispatch(self, ctx: DispatchContext) -> DispatchResult:
        return self.simulate(ctx).result

    def simulate(self, ctx: DispatchContext) -> HeatPumpOperation:
        """한 해 운전 — 시계열과 미충족 진단을 함께 돌려준다."""
        if ctx.dt != self.dt:
            raise ValueError(f"{self.name}: 컨텍스트의 시간 해상도({ctx.dt}초)가 자원의 "
                             f"해상도({self.dt}초)와 다릅니다 — 연간 스텝 수가 달라지면 "
                             "열부하 균등 배분이 통째로 어긋납니다")

        hours = ctx.dt / SECONDS_PER_HOUR
        cap_hp = self.rated_heat_kw * hours
        cap_aux = self.aux_heater_kw * hours

        load = self._load_series(ctx)
        target = self._production_target(ctx, load, cap_hp + cap_aux)
        temps = self._temperature_series(ctx)

        electric = [0.0] * ctx.steps
        heat = [0.0] * ctx.steps
        hp_total = aux_total = elec_total = 0.0

        for i in range(ctx.steps):
            hp_heat = min(target[i], cap_hp)
            aux_heat = min(target[i] - hp_heat, cap_aux)
            consumed = hp_heat / self.cop_at(temps[i], year=ctx.year) + aux_heat / AUX_HEATER_COP

            # 부호 규약: 열은 내보내므로 양수, 전기는 받아들이므로 음수.
            heat[i] = hp_heat + aux_heat
            electric[i] = -consumed
            hp_total += hp_heat
            aux_total += aux_heat
            elec_total += consumed

        demand = sum(load)
        zeros = [0.0] * ctx.steps
        return HeatPumpOperation(
            result=DispatchResult(electric=electric, heat=heat, cool=zeros, fuel=list(zeros)),
            heat_demand_kwh=demand,
            hp_heat_kwh=hp_total,
            aux_heat_kwh=aux_total,
            electricity_kwh=elec_total,
            unmet_heat_kwh=max(0.0, demand - hp_total - aux_total),
        )

    def _load_series(self, ctx: DispatchContext) -> list[float]:
        if self._load_profile is not None:
            ctx.check_series(self._load_profile, name="heat_load_kwh")
            return list(self._load_profile)
        return [self._annual_load_kwh / steps_per_year(ctx.dt)] * ctx.steps

    def _temperature_series(self, ctx: DispatchContext) -> list[float]:
        if ctx.ambient_temp_c is not None:
            return list(ctx.ambient_temp_c)
        return [self.default_ambient_temp_c] * ctx.steps

    def _production_target(
        self, ctx: DispatchContext, load: list[float], capacity: float
    ) -> list[float]:
        """열부하 대응 방식에 따른 스텝별 생산 목표량 (kWh). 축열조·요금연동 운전은
        **하루 단위로만** 부하를 옮긴다 — 며칠치를 몰아 생산하면 알지도 못하는
        축열 용량을 가정하게 된다.
        """
        if self.mode == MODE_LOAD_FOLLOWING:
            return load

        allowed = self._allowed_steps(ctx)
        per_day = max(1, _SECONDS_PER_DAY // ctx.dt)
        target = [0.0] * ctx.steps
        for start in range(0, ctx.steps, per_day):
            end = min(start + per_day, ctx.steps)
            window = [i for i in range(start, end) if allowed[i]]
            if not window:
                continue  # 운전 가능 시간이 없는 날은 전량 미충족으로 남는다
            level = sum(load[start:end]) / len(window)
            for i in window:
                target[i] = min(level, capacity)
        return target

    def _allowed_steps(self, ctx: DispatchContext) -> list[bool]:
        """운전 가능 시간대 마스크. 심야는 시계로, 요금 연동은 요금 순위로 고른다."""
        if self.mode == MODE_NIGHT_STORAGE:
            return [(i * ctx.dt // SECONDS_PER_HOUR) % 24 in self.night_hours
                    for i in range(ctx.steps)]

        prices = self.price_profile_won_per_kwh
        if prices is None:  # 생성자가 이미 막지만 -O 로 assert 가 사라져도 남아야 한다
            raise ValueError(f"{self.name}: 전력요금 연동 운전에 요금 시계열이 없습니다")
        ctx.check_series(prices, name="price_profile_won_per_kwh")

        per_day = max(1, _SECONDS_PER_DAY // ctx.dt)
        cheapest = max(1, self.price_linked_hours * SECONDS_PER_HOUR // ctx.dt)
        allowed = [False] * ctx.steps
        for start in range(0, ctx.steps, per_day):
            ranked = sorted(range(start, min(start + per_day, ctx.steps)),
                            key=lambda i: (prices[i], i))
            for i in ranked[:cheapest]:
                allowed[i] = True
        return allowed

    def annual_operation(self, year: int = 1) -> HeatPumpOperation:
        """비용·편익 산정용 1년치 운전. 연도별로 한 번만 풀고 재사용한다."""
        key = int(year)
        if key not in self._annual_ops:
            ambient = self.annual_ambient_temp_c
            ctx = DispatchContext(steps=steps_per_year(self.dt), dt=self.dt, year=key,
                                  ambient_temp_c=list(ambient) if ambient else None)
            self._annual_ops[key] = self.simulate(ctx)
        return self._annual_ops[key]

    def annual_heat_supplied_kwh(self, year: int = 1) -> float:
        """연간 공급 열량 (히트펌프 + 보조 열원)."""
        return self.annual_operation(year).heat_supplied_kwh

    def annual_electricity_kwh(self, year: int = 1) -> float:
        """연간 소비 전력량 — **양수 크기**다. 부호 규약은 시계열에만 적용된다."""
        return self.annual_operation(year).electricity_kwh

    def heat_cost_saving(self, *, baseline: HeatBaseline, year: int = 1) -> HeatCostSaving:
        """열비용 절감 = **기존 열원 연료비 − 히트펌프 전력비**. 수요가 아니라
        *공급한 열*을 기준선 열량으로 쓴다 — 두 대안이 같은 서비스를 냈을 때만
        비교가 성립하므로 미충족분은 양쪽에서 함께 뺀다.
        """
        op = self.annual_operation(year)
        supplied = op.heat_supplied_kwh
        baseline_cost = baseline.cost_for_heat(supplied)
        hp_cost = to_won(op.electricity_kwh * self.elec_price_won_per_kwh)
        return HeatCostSaving(
            baseline_label=baseline.label,
            baseline_heat_kwh=supplied,
            baseline_cost=baseline_cost,
            hp_electricity_kwh=op.electricity_kwh,
            hp_electricity_cost=hp_cost,
            saving=Money(baseline_cost - hp_cost),
        )

    def capex(self, *, year: int) -> Money:
        """C-1 (§13.2.2) `단가 × 용량 + 부대비`. 초기 투자는 1년차에만 발생한다."""
        return to_won(self._acquisition_won) if year == 1 else Money(0)

    def capex_vat(self, *, year: int) -> Money:
        """C-1 부가세 — **본체와 분리 표시**한다. 합쳐 두면 프로포마에서 환급·불환급을
        나눌 수 없고, 관점별(사업자·사회·정부) 계상이 갈리는 지점을 잃는다.
        """
        return to_won(self._acquisition_won * self.vat_rate) if year == 1 else Money(0)

    def fixed_om(self, *, year: int) -> Money:
        """C-2 고정 O&M `A × (1+i)^(n−1)`. 20년 누계는 등비수열 합과 일치한다."""
        if year < 1:
            raise ValueError(f"분석 연도는 1부터 셉니다: {year}")
        return to_won(self.fixed_om_won * (1.0 + self.om_escalation) ** (year - 1))

    def variable_om(self, *, year: int) -> Money:
        """C-3 변동 O&M = `처리량 × 단가`. HeatPump의 처리량은 **열공급 kWh**다 —
        전력량(1,000)이 아니라 열량(3,000) 기준이며, COP배 차이라 잘못 걸면 COP분의
        1로 과소 계상된다. 보조 열원분은 본체 마모가 아니므로 뺀다.
        """
        return to_won(self.annual_operation(year).hp_heat_kwh * self.variable_om_won_per_kwh)

    def replacement_schedule(self, *, horizon: int) -> dict[int, Money]:
        """C-4 교체비 — 수명 도달 **다음 연도 초**에 계상. 순환펌프 등 부속설비는
        본체와 **독립 수명**을 갖는다 (FR-104-AC4) — 본체 수명만 보면 15년
        히트펌프의 10년짜리 부속 교체비가 통째로 빠진다.
        """
        if horizon < 1:
            raise ValueError(f"분석기간은 1년 이상입니다: {horizon}")

        schedule: dict[int, Decimal] = {}
        for life, cost in ((self.lifetime, self.replacement_cost_won),
                           (self.pump_lifetime, self.pump_replacement_cost_won)):
            if not life or cost <= 0.0:
                continue
            year = life + 1
            while year <= horizon:
                schedule[year] = schedule.get(year, Decimal(0)) + to_won(cost)
                year += life
        return {y: Money(v) for y, v in sorted(schedule.items())}

    def salvage_value(self, *, year: int) -> Money:
        """C-5 잔존가치 = `취득가 × 잔존수명 / 총수명`, 최종연도 계상.

        **할인은 하지 않는다** — 명목액을 돌려주고 할인은 재무 계층의 몫이다
        (NFR-103 계층 경계). 교체가 있었으면 교체 취득가와 교체 이후 경과년수로 다시
        센다 — 무시하면 16년차에 새로 산 설비가 20년차에 0으로 잡혀 회수기간이 실제보다
        길게 나온다 (원칙 4-3).
        """
        if year < 1:
            raise ValueError(f"분석 연도는 1부터 셉니다: {year}")
        pump = self.pump_replacement_cost_won
        return won_sum([
            self._component_salvage(self.lifetime, self._acquisition_won,
                                    self.replacement_cost_won, year),
            self._component_salvage(self.pump_lifetime, pump, pump, year),
        ])

    @staticmethod
    def _component_salvage(
        life: int | None, initial_won: float, replacement_won: float, year: int
    ) -> Decimal:
        if not life or initial_won <= 0.0:
            return Decimal(0)

        acquired_year, acquired_won = 1, initial_won
        replaced = life + 1
        while replaced <= year:
            acquired_year, acquired_won = replaced, replacement_won
            replaced += life

        remaining = max(0, life - (year - acquired_year + 1))
        return Decimal(str(acquired_won)) * remaining / life
