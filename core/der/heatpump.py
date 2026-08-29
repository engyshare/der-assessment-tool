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

from core.contracts.der import DER, EOL_REPLACE, DispatchContext, DispatchResult
from core.contracts.units import (
    ENERGY_TOLERANCE_KWH,
    SECONDS_PER_HOUR,
    Money,
    Year,
    steps_per_year,
    to_won,
)
from core.contracts.validation import ValidationError

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
            raise ValidationError(
                field="heatpump.baseline_label",
                reason="기준선 이름이 비어 있습니다 — '무엇 대비 절감인가'를 "
                       "표시하지 못하면 증분 분석의 전제가 사라집니다 (FR-705-AC1)",
                action="기준 열원을 가리키는 이름을 지정하십시오 (예: 전기보일러, 가스보일러)",
            )
        if self.efficiency <= 0.0:
            raise ValidationError(
                field="heatpump.baseline_efficiency",
                reason=f"{self.label}: 열효율은 0보다 커야 합니다 (받은 값 {self.efficiency})",
                action="열효율을 0보다 큰 값으로 지정하십시오",
            )
        if self.fuel_price_won_per_kwh < 0.0:
            raise ValidationError(
                field="heatpump.baseline_fuel_price_won_per_kwh",
                reason=f"{self.label}: 연료단가가 음수입니다 (받은 값 "
                       f"{self.fuel_price_won_per_kwh})",
                action="연료단가(원/kWh)를 0 이상의 값으로 지정하십시오",
            )

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
        raise ValidationError(
            field="heatpump.cop_curve",
            reason="COP 곡선이 비어 있습니다 — 소비전력을 계산할 수 없습니다",
            action="스칼라 COP 값 하나 또는 (외기온, COP) 격자점 목록을 지정하십시오",
        )
    points.sort()

    temps = [t for t, _ in points]
    if len(set(temps)) != len(temps):
        raise ValidationError(
            field="heatpump.cop_curve",
            reason=f"COP 곡선에 같은 외기온이 두 번 나옵니다: {temps}",
            action="외기온 격자점이 서로 겹치지 않도록 COP 곡선을 다시 지정하십시오",
        )
    for temp, cop in points:
        if cop <= 0.0:
            raise ValidationError(
                field="heatpump.cop_curve",
                reason=f"COP 가 0 이하입니다 ({temp}℃ → {cop}). 소비전력은 열량을 "
                       "COP로 나눈 값이므로 발산하거나 음수가 됩니다",
                action="해당 격자점의 COP를 0보다 큰 값으로 고치십시오",
            )
    return tuple(points)


def _annual_tuple(
    series: Sequence[float] | None, *, dt: int, name: str, field: str
) -> tuple[float, ...] | None:
    """비용 산정용 시계열이 **1년치**임을 확인한 뒤 고정한다. 연간 합계를 내는
    자리에 24행짜리가 들어오면 변동 O&M과 편익이 365분의 1로 조용히 줄어든다.

    `field` 를 인자로 받는 이유: 이 헬퍼는 세 필드(요금 시계열·외기온
    시계열·열부하 프로파일)가 공유한다. 고정 키를 쓰면 어느 칸이 틀렸는지
    사라지므로 호출부마다 다른 `field` 를 넘긴다.
    """
    if series is None:
        return None
    expected = steps_per_year(dt)
    if len(series) != expected:
        raise ValidationError(
            field=field,
            reason=f"{name} 는 1년치 시계열이어야 합니다: {len(series)}행, "
                   f"기대 {expected}행",
            action=f"{name} 을(를) {expected}행 시계열로 맞추십시오 (8760 또는 35040)",
            rule="DV-4",
        )
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
    #: 이름은 계약이 고정한다 (v1.1 개정 ④) — v1.0 에서는 이 자원만 소문자
    #: `operating_modes` 였고 나머지는 `OPERATING_MODES` 였다. 케이스 그리드가
    #: 운전 방법을 탐색 변수로 순회할 때(FR-105-AC5) 자원별 분기가 생긴다.
    OPERATING_MODES: ClassVar[tuple[str, ...]] = (
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
        operating_mode: str = MODE_LOAD_FOLLOWING,
        aux_heater_kw: float = 0.0,
        night_hours: Sequence[int] = DEFAULT_NIGHT_HOURS,
        price_profile_won_per_kwh: Sequence[float] | None = None,
        price_linked_hours: int = 8,
        annual_ambient_temp_c: Sequence[float] | None = None,
        default_ambient_temp_c: float = 7.0,
        # ── 재무 (§13.2.2 RC-ALL-C1~C5) ──
        elec_price_won_per_kwh: float = 0.0,
        # `vat_rate` 기본값은 **0.0 이며 「세율 0%」가 아니라 「주입되지 않음」**
        # 이다. 법정 세율 10%는 `docs/assumptions.yaml` 의 `tax.vat_rate` 가
        # 정본이고, 자원은 그것을 소유하지 않는다 (NFR-202).
        #
        # v1.1 계약 개정 직후 이 자리만 `0.1` 이었고 나머지 일곱(자원 6종 +
        # 공통설비)은 `0.0` 이었다. **같은 프로포마에서 히트펌프만 세액이 잡히고
        # 나머지는 0원이 되는데 어느 쪽도 오류가 아니었다** — v1.1이 메운
        # 「`capex_vat()` 가 없다」와 같은 구조가 기본값에 남아 있었던 것이다.
        capex_unit_won_per_kw: float = 0.0, capex_extra_won: float = 0.0, vat_rate: float = 0.0,
        fixed_om_won: float = 0.0, escalation_rate: float = 0.0,
        variable_om_won_per_kwh: float = 0.0,
        replacement_cost_won: float | None = None,
        pump_lifetime: int | None = None, pump_replacement_cost_won: float = 0.0,
        dt: int = SECONDS_PER_HOUR, lifetime: int = 15, degradation_rate: float = 0.0,
        end_of_life_action: str = EOL_REPLACE,
    ) -> None:
        # 전기·열 **둘 다** 참이다. 하나만 켜면 나머지 매체의 값이 어느 수지에도
        # 잡히지 않고 사라진다 (FR-101-AC4).
        super().__init__(name=name, dt=dt, lifetime=lifetime,
                         degradation_rate=degradation_rate,
                         carries_electric=True, carries_heat=True,
                         operating_mode=operating_mode,
                         escalation_rate=escalation_rate,
                         end_of_life_action=end_of_life_action)

        if rated_heat_kw <= 0.0:
            raise ValidationError(
                field="heatpump.rated_heat_kw",
                reason=f"{name}: 정격 열출력은 0보다 커야 합니다 (받은 값 {rated_heat_kw})",
                action="정격 열출력(kW)을 0보다 큰 값으로 지정하십시오",
            )
        if aux_heater_kw < 0.0:
            raise ValidationError(
                field="heatpump.aux_heater_kw",
                reason=f"{name}: 보조 열원 정격이 음수입니다 (받은 값 {aux_heater_kw})",
                action="보조 열원 정격(kW)을 0 이상의 값으로 지정하십시오",
            )
        # 운전 방법 소속 검사는 계약이 이미 했다 (super() 안에서). 여기서는
        # **그 방법이 필요한 입력을 갖췄는지**만 본다 — 성질이 다른 검사다.
        if operating_mode == MODE_PRICE_LINKED and price_profile_won_per_kwh is None:
            # 조용히 열부하 추종으로 되돌리면 사용자는 요금 연동으로 돌았다고 믿는다
            raise ValidationError(
                field="heatpump.price_profile_won_per_kwh",
                reason=f"{name}: 전력요금 연동 운전에는 요금 시계열이 필요합니다",
                action="price_profile_won_per_kwh 에 1년치 요금 시계열을 지정하십시오",
            )
        if price_linked_hours <= 0:
            raise ValidationError(
                field="heatpump.price_linked_hours",
                reason=f"{name}: 요금 연동 운전 시간은 1시간 이상입니다 "
                       f"(받은 값 {price_linked_hours})",
                action="price_linked_hours 를 1 이상의 정수로 지정하십시오",
            )

        self.rated_heat_kw = float(rated_heat_kw)
        self.cop_curve = _normalize_cop_curve(cop_curve)
        self.aux_heater_kw = float(aux_heater_kw)
        self.night_hours = frozenset(int(h) for h in night_hours)
        self.price_linked_hours = int(price_linked_hours)
        self.default_ambient_temp_c = float(default_ambient_temp_c)
        self.price_profile_won_per_kwh = _annual_tuple(
            price_profile_won_per_kwh, dt=dt, name="price_profile_won_per_kwh",
            field="heatpump.price_profile_won_per_kwh")
        self.annual_ambient_temp_c = _annual_tuple(
            annual_ambient_temp_c, dt=dt, name="annual_ambient_temp_c",
            field="heatpump.annual_ambient_temp_c")
        self._load_profile, self._annual_load_kwh = self._normalize_heat_load(heat_load_kwh)

        self.elec_price_won_per_kwh = float(elec_price_won_per_kwh)
        self.capex_unit_won_per_kw = float(capex_unit_won_per_kw)
        self.capex_extra_won = float(capex_extra_won)
        self.vat_rate = float(vat_rate)
        self.fixed_om_won = float(fixed_om_won)
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
        # `bool` 을 **먼저** 거른다. `bool` 은 `int` 의 하위 클래스라 스칼라
        # 분기로 들어오면 조용히 0·1 kWh 가 되고, 아래 프로파일 분기로 가면
        # *"'bool' object is not iterable"* 이라는 무관해 보이는 메시지가 뜬다.
        # `to_won()` 이 금액 자리의 `bool` 을 거부하는 것과 같은 이유다.
        if isinstance(heat_load_kwh, bool):
            raise TypeError(
                f"{self.name}: 열부하 자리에 bool 이 들어왔습니다. "
                "연간 총량(스칼라) 또는 스텝별 프로파일이어야 합니다"
            )
        if isinstance(heat_load_kwh, (int, float)):
            if heat_load_kwh < 0.0:
                raise ValidationError(
                    field="heatpump.heat_load_kwh",
                    reason=f"{self.name}: 연간 열부하가 음수입니다 (받은 값 {heat_load_kwh})",
                    action="연간 열부하(kWh)를 0 이상의 값으로 지정하십시오",
                )
            return None, float(heat_load_kwh)

        profile = tuple(float(v) for v in heat_load_kwh)
        _annual_tuple(profile, dt=self.dt, name="heat_load_kwh", field="heatpump.heat_load_kwh")
        if any(v < 0.0 for v in profile):
            raise ValidationError(
                field="heatpump.heat_load_kwh",
                reason=f"{self.name}: 열부하 시계열에 음수가 있습니다",
                action="열부하 시계열의 모든 값을 0 이상으로 지정하십시오",
            )
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

    def value_streams(self) -> tuple[str, ...]:
        """히트펌프가 만드는 편익 — 열 비용 절감 1종 (`RC-HP-B1~B2`).

        전기를 **받아들이는** 자원이므로 전력 판매·REC 편익은 없다. 열 비용
        절감은 기존 열원(전기보일러·가스보일러) 대비 차액이며, 그 기준선을
        전제로 갖는다 (FR-401-AC2.HeatCostSaving).
        """
        return ("HeatCostSaving",)

    def dispatch(self, ctx: DispatchContext) -> DispatchResult:
        return self.simulate(ctx).result

    def simulate(self, ctx: DispatchContext) -> HeatPumpOperation:
        """운전 — 시계열과 미충족 진단을 함께 돌려준다.

        해상도 불일치 거부는 계약의 `check_context()` 로 옮겼다 (v1.1 개정 ①) —
        v1.0 에서는 이 자원과 부하 자원만 거부하고 나머지 넷은 조용히 한쪽
        해상도를 채택했다.
        """
        self.check_context(ctx)

        first_eol = min(
            self.lifetime,
            self.pump_lifetime if self.pump_lifetime is not None else self.lifetime,
        )
        if self.retires_at_end_of_life() and ctx.year > first_eol:
            zeros = [0.0] * ctx.steps
            load = self._load_series(ctx)
            demand = sum(load)
            eol_notes: tuple[str, ...] = ()
            if demand > ENERGY_TOLERANCE_KWH:
                eol_notes = (
                    f"{self.name}: 수명 종료(retire)로 인하여 열부하 {demand:.3f} kWh 전량 미충족.",
                )
            return HeatPumpOperation(
                result=DispatchResult(
                    electric=zeros,
                    heat=zeros,
                    cool=zeros,
                    fuel=list(zeros),
                    unmet_heat=load,
                    notes=eol_notes,
                ),
                heat_demand_kwh=demand,
                hp_heat_kwh=0.0,
                aux_heat_kwh=0.0,
                electricity_kwh=0.0,
                unmet_heat_kwh=demand,
            )

        hours = ctx.hours_per_step
        cap_hp = self.rated_heat_kw * hours
        cap_aux = self.aux_heater_kw * hours

        load = self._load_series(ctx)
        target, unmet_basis = self._production_plan(ctx, load)
        temps = self._temperature_series(ctx)

        electric = [0.0] * ctx.steps
        heat = [0.0] * ctx.steps
        unmet = [0.0] * ctx.steps
        hp_total = aux_total = elec_total = 0.0

        for i in range(ctx.steps):
            hp_heat = min(target[i], cap_hp)
            aux_heat = min(target[i] - hp_heat, cap_aux)
            consumed = hp_heat / self.cop_at(temps[i], year=ctx.year) + aux_heat / AUX_HEATER_COP

            # 부호 규약: 열은 내보내므로 양수, 전기는 받아들이므로 음수.
            heat[i] = hp_heat + aux_heat
            electric[i] = -consumed
            # 계획 대비 부족분. **스텝별로 남긴다** — 연 총량만 남기면
            # «한겨울 며칠 전량 미충족»과 «1년 내내 조금씩 부족»이 같은 값이 되고,
            # 보조 열원 증설 판단이 성립하지 않는다 (`RC-HP-X1`).
            unmet[i] = max(0.0, unmet_basis[i] - heat[i])
            hp_total += hp_heat
            aux_total += aux_heat
            elec_total += consumed

        demand = sum(load)
        unmet_total = max(0.0, demand - hp_total - aux_total)
        zeros = [0.0] * ctx.steps
        notes: tuple[str, ...] = ()
        if unmet_total > ENERGY_TOLERANCE_KWH:
            notes = (
                f"{self.name}: 열부하 {unmet_total:.3f} kWh 미충족 "
                f"(정격 {self.rated_heat_kw} kWth · 보조 {self.aux_heater_kw} kWth). "
                "보조 열원 증설 또는 정격 상향을 검토하십시오 (RC-HP-X1)",
            )
        return HeatPumpOperation(
            result=DispatchResult(
                electric=electric, heat=heat, cool=zeros, fuel=list(zeros),
                # **미충족을 결과에 싣는다** (v1.1 개정). v1.0 은 이 값을
                # `HeatPumpOperation` 에만 두었고, 엔진은 `dispatch()` 만 보므로
                # 미충족 사실이 그 자리에서 사라졌다 — 남는 것은 「열이 조금 덜
                # 나온 정상 결과」뿐이었다.
                unmet_heat=unmet,
                notes=notes,
            ),
            heat_demand_kwh=demand,
            hp_heat_kwh=hp_total,
            aux_heat_kwh=aux_total,
            electricity_kwh=elec_total,
            unmet_heat_kwh=unmet_total,
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

    def _production_plan(
        self, ctx: DispatchContext, load: list[float]
    ) -> tuple[list[float], list[float]]:
        """`(생산 목표, 미충족 계상 기준)` 을 스텝별로 돌려준다 (kWh).

        축열조·요금연동 운전은 **하루 단위로만** 부하를 옮긴다 — 며칠치를 몰아
        생산하면 알지도 못하는 축열 용량을 가정하게 된다.

        **두 배열을 나눠 돌려주는 이유** (v1.1). 미충족을 `부하 − 공급` 으로 스텝
        마다 재면, 심야 운전은 주간 스텝 전부가 미충족으로 잡힌다 — 그 하루의 열이
        실제로는 전량 공급되었는데도 그렇다. 미충족은 **계획 대비 부족분**이어야
        하고, 계획은 부하를 옮긴 뒤의 것이다.

        목표에 용량 상한을 걸지 않는 것도 그래서다. 상한은 호출부가 `min()` 으로
        걸며(기기별로 다르다), 여기서 미리 깎으면 **깎인 만큼이 미충족 계상 기준에서
        함께 사라진다** — 정격 부족이 미충족으로 드러나지 않는 상태가 된다.
        """
        if self.operating_mode == MODE_LOAD_FOLLOWING:
            return load, load

        allowed = self._allowed_steps(ctx)
        per_day = max(1, _SECONDS_PER_DAY // ctx.dt)
        target = [0.0] * ctx.steps
        basis = [0.0] * ctx.steps
        for start in range(0, ctx.steps, per_day):
            end = min(start + per_day, ctx.steps)
            window = [i for i in range(start, end) if allowed[i]]
            if not window:
                # 운전 가능 시간이 없는 날은 전량 미충족이다. 목표는 0으로 두되
                # **계상 기준에는 부하를 남긴다** — 기준에서도 지우면 그 하루가
                # 「부하가 없던 날」과 구분되지 않는다.
                basis[start:end] = load[start:end]
                continue
            level = sum(load[start:end]) / len(window)
            for i in window:
                target[i] = level
                basis[i] = level
        return target, basis

    def _allowed_steps(self, ctx: DispatchContext) -> list[bool]:
        """운전 가능 시간대 마스크. 심야는 시계로, 요금 연동은 요금 순위로 고른다."""
        if self.operating_mode == MODE_NIGHT_STORAGE:
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
        """비용·편익 산정용 1년치 운전. 연도별로 한 번만 풀고 재사용한다.

        `int(year)` 가 아니라 `Year(year)` 로 만든다. `DispatchContext` 가
        `__post_init__` 에서 다시 `Year` 로 감싸므로 **동작은 전과 같지만**,
        1-base 규약을 지닌 타입을 벗겨 낸 뒤 넘기면 그 규약이 계약 경계에서만
        살아 있고 여기서는 사라진 것처럼 보인다. `Year` 는 `int` 의 하위
        클래스라 캐시 키로도 그대로 쓰인다 (`Year(1) == 1`).
        """
        key = Year(year)
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
        return to_won(self.fixed_om_won * self.escalation_factor(year=year))

    def variable_om(self, *, year: int) -> Money:
        """C-3 변동 O&M = `처리량 × 단가`. HeatPump의 처리량은 **열공급 kWh**다 —
        전력량(1,000)이 아니라 열량(3,000) 기준이며, COP배 차이라 잘못 걸면 COP분의
        1로 과소 계상된다. 보조 열원분은 본체 마모가 아니므로 뺀다.
        """
        return to_won(self.annual_operation(year).hp_heat_kwh * self.variable_om_won_per_kwh)

    def _acquisitions(self, *, horizon: int) -> tuple[tuple[int, dict[int, float]], ...]:
        """부품별 `(수명, {취득 연도: 취득가})` — 본체와 순환펌프를 **갈라** 담는다.
        `replacement_schedule()` 과 `salvage_value()` 가 **둘 다 여기서** 나온다.

        ## 왜 한 출처여야 하는가 (R43 · WP-D2)

        R43 이 교체비에 `replacement_escalation_factor` 를 태운 뒤(`59530fc`),
        `salvage_value()` 는 `replacement_cost_won` 을 **계수 없이** 읽고 있었다.
        그 결과가 *「명목으로 산 것을 실질로 되판다」* 다 — 본체 16년·교체단가
        1억·`escalation_rate=0.02` 에서 17년차 교체비는 **137,278,571원(명목)**
        인데 20년차 잔존가치는 `100,000,000 × 12/16 = 75,000,000원`(**1년차
        실질**)이었다. 명목이면 **102,958,928원**이다.

        어긋남의 방향이 **한쪽뿐**이라 위험하다 — 잔존가치가 과소 계상되어
        「보수적이라 안전하다」로 읽힌다. `ess.py::_acquisitions` 가 경계한 바로
        그 형태이며, 두 함수가 각자 `(수명, 단가)` 짝을 돌던 **갈라짐**이 그것을
        만들었다. `ESS`(R42)·`PV`(R39-E) 가 같은 자리에서 같은 답을 냈다:
        **한 곳이 내고 다른 곳이 읽는다.**

        ## `ESS` 가 아니라 `PV` 의 모양을 골랐다 — 그러나 파생은 `ESS` 를 따른다

        `HeatPump` 는 **본체 + 순환펌프** 두 부품이고 `PV`(본체 + 인버터)와 같은
        꼴이다 — 둘 다 *「본체 취득가 하나 + 수명이 다른 부속 하나」* 이고 부속의
        최초 취득분이 본체 단가 안에 잠겨 있다. `ESS` 는 배터리가 **자기 단가를
        따로 갖는**(`_battery_cost()`) 구조라 그쪽이 아니다. 다만 *`PV` 는
        `replacement_schedule()` 을 아직 여기서 파생시키지 않으므로* 파생 방식은
        `ESS`(R42)를 따랐다 — `PV` 는 그래서 두 곳이 여전히 갈려 있다.

        ⚠ **접지 않는다.** 부품별로 남기지 않으면 (본체 16년·펌프 10년을 25년
        분석할 때) 「마지막 취득 = 21년차 순환펌프」 하나만 남고 그 잔존수명을
        **본체 수명 16년**으로 재게 되어, 순환펌프가 본체만큼 버티는 설비가
        된다 (R42 가 `ESS` 에서 경고한 함정).

        ⚠ **최초 순환펌프를 취득분으로 세지 않는다.** 대장의 설비 단가
        (`capex_unit_won_per_kw`)는 *설치 완료 기준*이므로 최초 순환펌프 값은
        이미 `_acquisition_won` 안에 있고, 여기서 또 세면 **초기투자에 없는
        지출**의 잔존가치를 세게 된다. 반대로 본체 취득가에서 순환펌프 몫을
        떼어내지도 않았다 — 떼려면 「단가의 몇 %가 순환펌프인가」를 새로 정해야
        하고 **그 값이 대장에 없다**(`Q-2` 회신에 묶여 있다). **모르는 값을
        채우지 않는다.** `ESS` 의 PCS · `PV` 의 인버터가 같은 자리다.

        ⚠⚠ **`retire` 면 재취득이 없다** (`FR-104-AC3`). 종전 `salvage_value()`
        는 그 갈래를 보지 않아 **사지도 않은 설비의 잔존가치**를 `retire` 자원에
        붙이고 있었다(위 탐침 제원에서 20년차 **75,000,000원**). `replacement_schedule()`
        은 이미 비어 있었으므로 두 곳이 **반대 방향으로** 갈려 있었던 것이다 —
        `PV`(R39-E2)·`ESS`(R42)가 고친 것과 같은 결함이다. `retire` 조건을
        **여기 한 곳에만** 두어 양쪽이 함께 본다.

        ⚠ **단가가 0인 부품은 재취득하지 않는다** — 0원짜리 교체행을 프로포마에
        내보내면 「교체가 있었다」로 읽힌다. 종전 `replacement_schedule()` 의
        `cost <= 0.0` 갈래를 그대로 옮긴 것이다.
        """
        if self.retires_at_end_of_life():
            # 다시 사지 않으므로 취득분은 **최초 본체 하나**다. 순환펌프를 여기
            # 두면 `replacement_schedule()` 이 비어 있는데 잔존가치만 생긴다.
            return ((self.lifetime, {1: self._acquisition_won}),)

        parts: list[tuple[int, dict[int, float]]] = []
        for life, unit_cost, initial in (
            # 본체 — 최초 취득(1년차)은 `_acquisition_won`(부대비 포함)이고
            # 재취득분은 `replacement_cost_won`(부대비 제외)을 쓴다.
            (self.lifetime, self.replacement_cost_won, self._acquisition_won),
            # 순환펌프 — 최초 취득분을 두지 않는다 (위 ⚠ 참조).
            (self.pump_lifetime, self.pump_replacement_cost_won, None),
        ):
            if not life:
                continue
            acquired: dict[int, float] = {} if initial is None else {1: float(initial)}
            if unit_cost > 0.0:
                year = life + 1
                while year <= horizon:
                    acquired[year] = float(
                        to_won(unit_cost * self.replacement_escalation_factor(year=year))
                    )
                    year += life
            if not acquired:
                continue
            parts.append((life, acquired))
        return tuple(parts)

    def replacement_schedule(self, *, horizon: int) -> dict[int, Money]:
        """C-4 교체비 — 수명 도달 **다음 연도 초**에 계상. 순환펌프 등 부속설비는
        본체와 **독립 수명**을 갖는다 (FR-104-AC4) — 본체 수명만 보면 15년
        히트펌프의 10년짜리 부속 교체비가 통째로 빠진다.

        ⚠ **이 스케줄은 `_acquisitions()` 에서 파생된다** (R43 · WP-D2). 종전에는
        여기와 `salvage_value()` 가 **각자** `(수명, 단가)` 짝을 돌았고, 그래서
        *교체비는 명목인데 그 잔존가치는 실질*인 비대칭이 조용히 생겼다.
        사유·선례·`retire` 갈래는 전부 `_acquisitions()` 독스트링에 있다 —
        **같은 조건을 두 곳에 적지 않는다.**

        `retire` 면 빈 dict 다 (FR-104-AC3) — 그 조건을 **여기 다시 적지 않는다.**
        `_acquisitions()` 가 `retire` 에서 1년차 하나만 내고 그것은 아래에서
        걸러지므로 이 함수는 저절로 빈다.

        ⚠ **두 항 다 `replacement_escalation_factor` 를 굴린다** (R43 · `DV-7`).
        대장이 `price_basis: "명목"` 을 **최상위에서 한 번** 선언하므로
        (`docs/assumptions.yaml:76`) 17년차 지출을 오늘의 원으로 적으면 **그
        지출만 실질이 되어** 선언과 어긋난다 — `ESS` 에서 R40 이 같은 자리에 서서
        같은 근거로 정한 것을 그대로 따른다(`ess.py::_acquisitions`). 선언이 자원별이
        아니라 대장 최상위 1회이므로 그 사유는 `HeatPump` 에도 그대로 성립한다.

        ⚠ **O&M 계수(`escalation_factor`)로 되돌리지 않는다** — 대장의
        `capex.replacement_real_trend`(`Q-17`)는 적용범위를 **재취득 단가로만**
        좁혀 두었고 O&M 을 명시적으로 뺐다(`contracts/der.py`
        `replacement_escalation_factor` 독스트링). 되돌리면
        `test_replacement_follows_the_replacement_rate_and_om_does_not` 이 잡는다.

        ⚠ **연차는 「그 부품의 교체가 일어나는 해」다.** 본체(16년)와 부속(10·20년)이
        서로 다른 해에 걸리므로 각 항이 **자기 연차**로 계수를 받는다. 한 해에 둘이
        겹치면 **각각 곱한 뒤** 더한다 — 합산 후 한 번 곱하면 같은 해에서는 우연히
        맞지만, 단가가 다른 두 부품을 한 계수로 접는 셈이라 수명이 갈리는 순간
        틀린다.
        """
        if horizon < 1:
            raise ValidationError(
                field="heatpump.horizon",
                reason=f"분석기간은 1년 이상입니다 (받은 값 {horizon})",
                action="분석기간(horizon)에 1 이상의 정수를 지정하십시오",
            )
        schedule: dict[int, Decimal] = {}
        for _life, acquired in self._acquisitions(horizon=horizon):
            for year, cost in acquired.items():
                # 1년차 최초 취득은 CAPEX 이지 교체비가 아니므로 제외한다
                if year == 1:
                    continue
                # 같은 해에 본체와 순환펌프가 겹치면 더한다 — 덮어쓰면 한쪽이
                # 조용히 사라진다
                schedule[year] = schedule.get(year, Decimal(0)) + to_won(cost)
        return {y: Money(v) for y, v in sorted(schedule.items())}

    def salvage_value(self, *, year: int) -> Money:
        """C-5 잔존가치 = `취득가 × 잔존수명 / 총수명`, 최종연도 계상.

        **할인은 하지 않는다** — 명목액을 돌려주고 할인은 재무 계층의 몫이다
        (NFR-103 계층 경계). 교체가 있었으면 교체 취득가와 교체 이후 경과년수로 다시
        센다 — 무시하면 16년차에 새로 산 설비가 20년차에 0으로 잡혀 회수기간이 실제보다
        길게 나온다 (원칙 4-3).

        **부품마다 마지막 취득 시점부터 센다** (R43 · WP-D2) — 취득분은
        `_acquisitions()` 하나가 낸다. 그래서 **교체비가 명목이면 잔존가치도
        명목**이고, 종전처럼 *명목으로 산 것을 실질로 되파는* 상태가 될 수 없다.
        `PV.salvage_value()`·`ESS.salvage_value()` 와 같은 셈이다.
        """
        if year < 1:
            raise ValueError(f"분석 연도는 1부터 셉니다: {year}")
        total = 0.0
        for life, acquired in self._acquisitions(horizon=year):
            within = [y for y in acquired if y <= year]
            if not within:
                continue
            last_year = max(within)
            used = year - last_year + 1  # 취득 연도부터 센다 (1-base)
            remaining = max(0, life - used)
            total += acquired[last_year] * remaining / life
        return to_won(total)
