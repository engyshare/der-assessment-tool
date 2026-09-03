"""`EV_V2G` — 전기차 + 양방향 충전기 (작업 6.3 / WP-1c).

spec FR-102-AC1.EV_V2G · FR-104 · FR-105-AC1 · FR-404 · §13.2.2 · §13.2.3.

**기본 상태는 「비용만 있고 편익은 0」이다.** §15.1 Q-8이 V2G 방전 전력의
계량·정산 제도 존부를 **미확인**으로 판정했고, `docs/assumptions.yaml` 의
`benefit.v2g_discharge` 는 `track: default0 / value: 0` 이다. 제도가 없으면
편익은 작은 것이 아니라 **0**이며, 정산단가를 추정해 넣으면 존재하지 않는 제도
위에 편익을 쌓아 필요 지원액을 과소 산정하게 된다 (가정 A-11). 충전기 비용은
그대로 계상되므로 기본 상태의 V2G는 순수 비용으로 나타난다 — **오류가 아니라
제도 미비의 정직한 반영**이다.

**차량은 사업 자산이 아니다.** 사업이 사는 것은 충전기이고, 차주 배터리가 닳는
몫은 열화 보상단가로 비용측에 계상한다 (`RC-EV-C6`) — 상계하면 "얼마를 벌고
얼마를 물어 주는가"가 사라진다.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Callable
from typing import ClassVar

from core.contracts.der import DER, EOL_REPLACE, DispatchContext, DispatchResult
from core.contracts.units import (
    ENERGY_TOLERANCE_KWH,
    SECONDS_PER_HOUR,
    ZERO,
    Money,
    Year,
    to_won,
    won_sum,
)
from core.contracts.validation import ValidationError

# 대표 1개년 반복 전제(가정 A-4)에서 8760 = 365일 × 24시간이다.
DAYS_PER_YEAR, SECONDS_PER_DAY, HOURS_PER_DAY = 365, 86_400, 24

POLICY_WARNING = (  # 활성화 시 리포트 상단에 뜨는 문구 (FR-404-AC1과 같은 형식)
    "V2G 방전 편익을 활성화했습니다 — 제도 미확인 상태의 정책 가정 편익입니다 "
    "(spec §15.1 Q-8 · assumptions benefit.v2g_discharge track=default0). "
    "본편익과 분리해 표시하고, 회수기간은 V2G 편익 포함/제외 두 값으로 병기해야 합니다"
)


# 클래스명은 파스칼케이스 관례를 따르지 않는다. spec 조항 ID `FR-102-AC1.EV_V2G`
# 와 **같은 리터럴**이어야 하며, `EvV2g` 로 다듬으면 NFR-106 순회 검사가 헛돈다.
class EV_V2G(DER):
    """전기차 + 양방향 충전기. 파라미터는 spec FR-102-AC1.EV_V2G 원문 그대로 —
    대수, 배터리(kWh), 최대 충방전(kW), 접속가능시간대, 참여율, 열화 보상단가."""

    tag: ClassVar[str] = "EV_V2G"

    #: FR-101-AC3 — 자원이 **자기 디스패치 규칙을 선언**한다. 값은 엔진 어휘
    #: `DispatchRule.V2G_CHARGE` 의 값 문자열이다. 열거형을 import 하지 않는
    #: 이유(NFR-208-AC1 역방향 import 금지)는 `DER.DISPATCH_RULE` 독스트링에
    #: 있다.
    DISPATCH_RULE: ClassVar[str] = "v2g_charge"

    # 값은 spec FR-105-AC1 의 EV_V2G 행 원문이다 — 다듬으면 spec과 갈린다.
    MODE_UNIDIRECTIONAL: ClassVar[str] = "단방향 충전만"
    MODE_BIDIRECTIONAL: ClassVar[str] = "양방향(최소 SOC 보장)"
    MODE_WINDOW_LIMITED: ClassVar[str] = "접속시간대 제한 운전"
    OPERATING_MODES: ClassVar[tuple[str, ...]] = (
        MODE_UNIDIRECTIONAL, MODE_BIDIRECTIONAL, MODE_WINDOW_LIMITED)

    def __init__(
        self,
        *,
        name: str,
        vehicle_count: int,
        battery_kwh: float,
        max_charge_kw: float,
        max_discharge_kw: float,
        connect_start_hour: int,
        connect_end_hour: int,
        participation: float,
        available_dod: float,
        arrival_soc: float = 0.8,
        min_departure_soc: float = 0.8,
        discharge_efficiency: float = 0.92,
        charge_efficiency: float = 0.92,
        lifetime: int = 10,
        degradation_rate: float = 0.0,
        escalation_rate: float = 0.0,
        replacement_escalation_rate: float | None = None,
        charger_count: int | None = None,
        charger_unit_cost_won: float = 0.0,
        ancillary_cost_won: float = 0.0,
        vat_rate: float = 0.0,
        fixed_om_won_per_year: float = 0.0,
        variable_om_won_per_kwh: float = 0.0,
        degradation_compensation_won_per_kwh: float = 0.0,
        replacement_cost_won: float | None = None,
        daily_charge_kwh: float = 0.0,
        operating_mode: str = MODE_BIDIRECTIONAL,
        discharge_benefit_enabled: bool = False,
        avoided_price_won_per_kwh: float = 0.0,
        dt: int = SECONDS_PER_HOUR,
        end_of_life_action: str = EOL_REPLACE,
    ) -> None:
        super().__init__(name=name, dt=dt, lifetime=lifetime,
                         degradation_rate=degradation_rate, carries_electric=True,
                         operating_mode=operating_mode,
                         escalation_rate=escalation_rate,
                         replacement_escalation_rate=replacement_escalation_rate,
                         end_of_life_action=end_of_life_action)
        self.vehicle_count = int(vehicle_count)
        self.battery_kwh = float(battery_kwh)
        self.max_charge_kw = float(max_charge_kw)
        self.max_discharge_kw = float(max_discharge_kw)
        self.connect_start_hour = int(connect_start_hour)
        self.connect_end_hour = int(connect_end_hour)
        self.participation = float(participation)
        self.available_dod = float(available_dod)
        self.arrival_soc = float(arrival_soc)
        self.min_departure_soc = float(min_departure_soc)
        self.discharge_efficiency = float(discharge_efficiency)
        self.charge_efficiency = float(charge_efficiency)
        self.charger_count = int(vehicle_count if charger_count is None else charger_count)
        self.charger_unit_cost_won = float(charger_unit_cost_won)
        self.ancillary_cost_won = float(ancillary_cost_won)
        self.vat_rate = float(vat_rate)
        self.fixed_om_won_per_year = float(fixed_om_won_per_year)
        self.variable_om_won_per_kwh = float(variable_om_won_per_kwh)
        self.degradation_compensation_won_per_kwh = float(degradation_compensation_won_per_kwh)
        self.replacement_cost_won = replacement_cost_won
        self.daily_charge_kwh = float(daily_charge_kwh)
        self.discharge_benefit_enabled = bool(discharge_benefit_enabled)
        self.avoided_price_won_per_kwh = float(avoided_price_won_per_kwh)

        self._validate_domain()
        self._connected_hours = _connected_hours(self.connect_start_hour, self.connect_end_hour)
        self._is_full_day = len(self._connected_hours) == HOURS_PER_DAY
        arrival = 0 if self._is_full_day else self.connect_start_hour
        self._cycle_offsets = _cycle_offsets(self._connected_hours, arrival, self.dt)
        self._connected_offsets = frozenset(self._cycle_offsets)
        self._validate_operation()

        if self.discharge_benefit_enabled:
            # 켜는 시점에 한 번만 남긴다 — 매 호출 경고는 로그를 잠기게 한다.
            warnings.warn(POLICY_WARNING, UserWarning, stacklevel=2)

    # ── 검증 ─────────────────────────────────────────────────────────

    def _validate_domain(self) -> None:
        """정의역 검사를 대입 뒤 한자리로 모은다 — 대입문 27줄 사이에 흩어 두면
        새 파라미터를 넣는 사람이 검사를 빠뜨린다 (§7.5 비율 규약 포함)."""
        # 운전 방법 소속과 물가상승률 척도는 **계약이 이미 검사했다**
        # (v1.1 개정 ④⑤). 여기서 다시 보면 규칙이 두 곳에 생기고 한쪽만 고쳐진다.
        n = self.name
        _check(n, "0보다 커야 합니다", lambda v: v > 0,
               vehicle_count=self.vehicle_count, battery_kwh=self.battery_kwh,
               max_charge_kw=self.max_charge_kw, max_discharge_kw=self.max_discharge_kw)
        _check(n, "0~23시입니다", lambda v: 0 <= v <= 23,
               connect_start_hour=self.connect_start_hour, connect_end_hour=self.connect_end_hour)
        _check(n, "0~1 소수입니다 (50%는 0.5)", lambda v: 0.0 <= v <= 1.0,
               participation=self.participation, arrival_soc=self.arrival_soc,
               min_departure_soc=self.min_departure_soc)
        _check(n, "0 초과 1 이하 소수입니다", lambda v: 0.0 < v <= 1.0,
               available_dod=self.available_dod, charge_efficiency=self.charge_efficiency,
               discharge_efficiency=self.discharge_efficiency)
        _check(n, "음수일 수 없습니다", lambda v: v >= 0,
               daily_charge_kwh=self.daily_charge_kwh, vat_rate=self.vat_rate,
               charger_unit_cost_won=self.charger_unit_cost_won,
               ancillary_cost_won=self.ancillary_cost_won,
               fixed_om_won_per_year=self.fixed_om_won_per_year,
               variable_om_won_per_kwh=self.variable_om_won_per_kwh,
               replacement_cost_won=self.replacement_cost_won or 0.0,
               avoided_price_won_per_kwh=self.avoided_price_won_per_kwh,
               degradation_compensation_won_per_kwh=self.degradation_compensation_won_per_kwh)

    def _validate_operation(self) -> None:
        """SOC 보장·운전 방법·시간대 수용력이 성립하는지 본다. 조용히 클램프하면
        리포트는 "보장 충족"으로 나오고 실제로는 차주가 출근을 못 한다."""
        n = self.name
        if self.arrival_soc - self.available_dod < -1e-12:
            raise ValidationError(
                field="ev_v2g.available_dod",
                reason=(
                    f"{n}: 가용 DOD {self.available_dod} 가 도착 SOC {self.arrival_soc} "
                    "보다 깊습니다 — SOC가 음수가 됩니다"
                ),
                action=f"available_dod 를 도착 SOC({self.arrival_soc}) 이하로 낮추십시오",
            )
        if (self.operating_mode != self.MODE_UNIDIRECTIONAL
                and self.arrival_soc + 1e-12 < self.min_departure_soc):
            raise ValidationError(
                field="ev_v2g.min_departure_soc",
                reason=(
                    f"{n}: 도착 SOC {self.arrival_soc} 로는 출발 보장 SOC "
                    f"{self.min_departure_soc} 를 지킬 수 없습니다 — 방전을 아예 하지 "
                    "않아도 미달입니다"
                ),
                action=f"min_departure_soc 를 {self.arrival_soc} 이하로 낮추십시오",
            )
        if self.operating_mode == self.MODE_WINDOW_LIMITED and self._is_full_day:
            raise ValidationError(
                field="ev_v2g.operating_mode",
                reason=(
                    f"{n}: 운전 방법이 {self.MODE_WINDOW_LIMITED} 인데 접속가능시간대가 "
                    "24시간입니다 — 제한 없는 제한 운전은 운전 방법 선택을 리포트 문구로만 "
                    "남깁니다"
                ),
                action=(
                    "connect_start_hour/connect_end_hour 로 24시간보다 짧은 접속 시간대를 "
                    "지정하거나 operating_mode 를 다른 값으로 바꾸십시오"
                ),
            )
        avail = len(self._cycle_offsets)
        dt_h = self.dt / SECONDS_PER_HOUR
        need_d = _steps_needed(self._daily_grid_discharge_kwh(1),
                               self._fleet_discharge_kw() * dt_h)
        need_c = _steps_needed(self._daily_grid_charge_kwh(1),
                               self._fleet_charge_kw() * dt_h)
        if need_d + need_c > avail:
            raise ValidationError(
                field="ev_v2g.max_discharge_kw",
                reason=(
                    f"{n}: 접속 시간대({avail}스텝) 안에 방전 {need_d}스텝 + 재충전 "
                    f"{need_c}스텝이 들어가지 않습니다. 조용히 재충전을 덜 하면 출발 SOC "
                    "보장이 깨지고, 조용히 방전을 줄이면 편익이 소리 없이 작아집니다"
                ),
                action=(
                    "max_charge_kw/max_discharge_kw 를 높이거나 connect_start_hour/"
                    "connect_end_hour 로 접속 시간대를 늘리십시오"
                ),
            )

    # ── 선언 (FR-105-AC1 · FR-404-AC1) ──────────────────────────────

    @classmethod
    def supported_operating_modes(cls) -> tuple[str, ...]:
        """지원 운전 방법 목록. 엔진 수정 없이 여기서만 늘어난다 (FR-105-AC2)."""
        return cls.OPERATING_MODES

    def policy_warnings(self) -> list[str]:
        """리포트 상단에 표시할 정책 가정 경고 (FR-404-AC1).

        **`DER` 계약의 기본 구현(빈 목록)을 덮어쓴다** (R48 §7 · spec §16.2).
        문면은 `POLICY_WARNING` 이 소유한다 — 계약은 형식만 고정한다.
        """
        return [POLICY_WARNING] if self.discharge_benefit_enabled else []

    def value_streams(self) -> tuple[str, ...]:
        """편익 tag — **기본은 없음이다** (§15.1 Q-8 제도 미확인 → 비활성).

        비활성 상태에서 값 0인 편익을 선언하면 리포트에 행이 서는데, 그 0은
        「제도가 없어서 0」과 「계산이 0을 냈다」를 구분하지 못한다. 단방향
        충전에도 편익이 없다 — 충전기 비용은 계상되므로 보수적이다.
        """
        if (not self.discharge_benefit_enabled
                or self.operating_mode == self.MODE_UNIDIRECTIONAL):
            return ()
        return ("DemandResponse",)

    # ── 물리 (RC-EV-P1~P3) ───────────────────────────────────────────

    def _fleet_capacity_kwh(self, year: int) -> float:
        """참여 차량의 합산 배터리 용량 (kWh). 연차별 열화를 반영한다 (FR-104)."""
        base = self.vehicle_count * self.battery_kwh * self.participation
        return base * (1.0 - self.degradation_rate) ** (int(Year(year)) - 1)

    def _fleet_discharge_kw(self) -> float:
        return self.vehicle_count * self.max_discharge_kw * self.participation

    def _fleet_charge_kw(self) -> float:
        return self.vehicle_count * self.max_charge_kw * self.participation

    def daily_available_discharge_kwh(self, *, year: int = 1) -> float:
        """일 가용 방전량 (kWh, **배터리 방출 기준**) — `RC-EV-P1`.
        `대수 × 배터리 × 참여율 × 가용 DOD`. 계통에 나가는 양은 여기에 방전효율을
        곱한 값이고(`RC-EV-B1`) 배터리가 닳는 양은 이 값이다(`RC-EV-C6`) — 둘을
        한 이름으로 부르면 편익과 보상비의 기준이 갈린다."""
        if self.operating_mode == self.MODE_UNIDIRECTIONAL:
            return 0.0
        return self._fleet_capacity_kwh(year) * self.available_dod

    def annual_available_discharge_kwh(self, *, year: int = 1) -> float:
        return self.daily_available_discharge_kwh(year=year) * DAYS_PER_YEAR

    def _daily_grid_discharge_kwh(self, year: int) -> float:
        return self.daily_available_discharge_kwh(year=year) * self.discharge_efficiency

    def _daily_grid_charge_kwh(self, year: int) -> float:
        if self.operating_mode == self.MODE_UNIDIRECTIONAL:
            return self.daily_charge_kwh
        return self.daily_available_discharge_kwh(year=year) / self.charge_efficiency

    def dispatch(self, ctx: DispatchContext) -> DispatchResult:
        """한 해 운전 — 접속 시간대 안에서 방전하고 출발 전까지 재충전한다.

        부호 규약은 계약과 같다: **양수 = 방전(계통에 내보냄), 음수 = 충전**.
        스텝 배치는 「접속 사이클 순서」다 — 도착(예 18시)부터 출발(예 08시)까지를
        한 사이클로 보고 앞에 방전을, 뒤에 재충전을 채운다. 달력일 배열 순서로
        채우면 자정을 넘는 블록이 잘려 재충전이 방전보다 먼저 오는 하루가 된다.

        **부분 창은 연초부터의 연속 구간이다.** 사이클 오프셋은 하루 안의 인덱스
        이므로 온전한 하루의 값은 창 길이와 무관하다. 창이 하루 중간에서 끝나면
        남은 스텝은 **관측되지 않은 것**이며, 창 안으로 압축하지 않는다.

        **`retire` 면 수명(충전기) 다음 해부터 전 매체가 0이다** (`FR-104-AC3`).
        충전기 없는 V2G는 계통에 못 싣는다 — 비용(교체비)만 끊고 편익(방전)은
        남기면 회수기간이 실제보다 좋게 나온다.
        """
        self.check_context(ctx)
        year, steps = int(ctx.year), ctx.steps
        if self.retires_at_end_of_life() and year > self.lifetime:
            return DispatchResult.zeros(steps)
        elec = [0.0] * steps
        grid_dis = self._daily_grid_discharge_kwh(year)
        grid_chg = self._daily_grid_charge_kwh(year)
        if grid_dis <= 0.0 and grid_chg <= 0.0:
            return DispatchResult.zeros(steps)

        dt_h = self.dt / SECONDS_PER_HOUR
        per_day = SECONDS_PER_DAY // self.dt
        for day in range(math.ceil(steps / per_day)):
            base = day * per_day
            idxs = [base + j for j in self._cycle_offsets if base + j < steps]
            pos, _ = _fill(elec, idxs, 0, total_kwh=grid_dis,
                           power_kw=self._fleet_discharge_kw(), dt_hours=dt_h,
                           limit_kw=ctx.grid_limit_kw, sign=+1)
            delivered = sum(elec[i] for i in idxs if elec[i] > 0.0)
            _, left = _fill(elec, idxs, pos, total_kwh=self._recharge_need_kwh(delivered),
                            power_kw=self._fleet_charge_kw(), dt_hours=dt_h,
                            limit_kw=ctx.grid_limit_kw, sign=-1)
            if left > ENERGY_TOLERANCE_KWH and len(idxs) == len(self._cycle_offsets):
                raise ValueError(
                    f"{self.name}: {day}일차에 재충전 {left:.3f} kWh 를 접속 시간대 안에 "
                    "넣지 못했습니다 (계통 연계 상한일 수 있습니다). 그대로 진행하면 "
                    "출발 SOC 보장이 조용히 깨집니다")

        zeros = [0.0] * steps
        return DispatchResult(elec, zeros, list(zeros), list(zeros))

    def _recharge_need_kwh(self, delivered_kwh: float) -> float:
        """계통에서 끌어와야 할 재충전량 (kWh). **실제 인도량 기준**이다 — 계획량으로
        계산하면 상한 때문에 방전이 덜 나간 날에도 그만큼 충전해 SOC가 계획을 넘는다."""
        if self.operating_mode == self.MODE_UNIDIRECTIONAL:
            return self.daily_charge_kwh
        return delivered_kwh / self.discharge_efficiency / self.charge_efficiency

    def departure_steps(self, ctx: DispatchContext) -> list[int]:
        """일자별 출발 직전 스텝 인덱스 — `RC-EV-P3` 의 검사 지점."""
        per_day = SECONDS_PER_DAY // self.dt
        last = self._cycle_offsets[-1]
        return [d * per_day + last for d in range(math.ceil(ctx.steps / per_day))
                if d * per_day + last < ctx.steps]

    def soc_profile(self, ctx: DispatchContext) -> list[float]:
        """스텝 종료 시점 SOC (0~1 분율) — `RC-EV-P3`. 비접속 스텝은 사이클 종료
        SOC를 유지한다. 주행 소모는 모형화하지 않는다 — 주행 부하는 `Load` 자원의
        몫이고 여기서 함께 빼면 두 번 계상된다."""
        cap = self._fleet_capacity_kwh(int(ctx.year))
        if cap <= 0.0:
            # 참여 차량이 0이면 SOC는 정의되지 않는다. 0으로 나누지 않고 도착
            # SOC를 그대로 둔다 (`RC-EV-X1`).
            return [self.arrival_soc] * ctx.steps

        elec = self.dispatch(ctx).electric
        per_day = SECONDS_PER_DAY // self.dt
        start_kwh = self.arrival_soc * cap - self._planned_daily_net_kwh()
        soc = [0.0] * ctx.steps
        for day in range(math.ceil(ctx.steps / per_day)):
            base = day * per_day
            level = start_kwh
            for j in self._cycle_offsets:
                i = base + j
                if i >= ctx.steps:
                    continue
                if elec[i] > 0.0:
                    level -= elec[i] / self.discharge_efficiency
                elif elec[i] < 0.0:
                    level += -elec[i] * self.charge_efficiency
                soc[i] = level / cap
            for j in range(per_day):
                i = base + j
                if i < ctx.steps and j not in self._connected_offsets:
                    soc[i] = level / cap
        return soc

    def _planned_daily_net_kwh(self) -> float:
        """사이클 1회의 **계획** 순증 배터리 에너지 (kWh). 양방향은 되채우므로 0이다.
        실측으로 역산하지 않는 이유: 역산하면 재충전이 모자란 날에도 출발 SOC가
        저절로 맞아 `RC-EV-P3` 이 자기충족 검사가 된다."""
        if self.operating_mode == self.MODE_UNIDIRECTIONAL:
            return self.daily_charge_kwh * self.charge_efficiency
        return 0.0

    # ── 편익 (RC-EV-B1) — 기본 비활성 ────────────────────────────────

    def v2g_discharge_benefit(self, *, year: int) -> Money:
        """V2G 방전 편익 (원/년) — **기본 0**.

        오라클: `방전 kWh × 방전효율 × 회피단가` (spec §13.2.3 `RC-EV-B1`).
        회피단가가 입력되어 있어도 `discharge_benefit_enabled` 가 거짓이면 0이다 —
        단가만으로 자동 활성화하면 참고삼아 값을 넣은 사용자가 존재하지 않는 제도의
        편익을 받게 된다 (§15.1 Q-8 · A-11). 회피단가에 물가상승률도 곱하지 않는다
        (전기요금 인상률은 Q-5b 소관이며, 섞으면 두 가정이 뒤엉킨다).
        """
        y = int(Year(year))
        if not self.discharge_benefit_enabled:
            return ZERO
        delivered = self.annual_available_discharge_kwh(year=y) * self.discharge_efficiency
        return to_won(delivered * self.avoided_price_won_per_kwh)

    # ── 비용 (RC-ALL-C1~C5 · RC-EV-C6) ───────────────────────────────

    def _initial_cost_won(self) -> float:
        """세전 취득가 = 충전기 단가 × 대수 + 부대비 (§13.2.2 C-1)."""
        return self.charger_unit_cost_won * self.charger_count + self.ancillary_cost_won

    def _replacement_cost_won(self) -> float:
        """교체비 기준가. 부대비(전기 인입·설치 공사)를 빼는 이유는 교체 시
        재발생하지 않기 때문이다 — 넣으면 20년 분석에서 인입공사비를 두 번 낸다."""
        if self.replacement_cost_won is not None:
            return self.replacement_cost_won
        return self.charger_unit_cost_won * self.charger_count

    def capex(self, *, year: int) -> Money:
        """CAPEX (원). **부가세 제외** — 세액은 `capex_vat()` 로 분리한다."""
        return to_won(self._initial_cost_won()) if int(Year(year)) == 1 else ZERO

    def capex_vat(self, *, year: int) -> Money:
        """CAPEX 부가세 (원). 프로포마에서 본체와 분리 표시한다 (§13.2.2 C-1)."""
        vat = self._initial_cost_won() * self.vat_rate
        return to_won(vat) if int(Year(year)) == 1 else ZERO

    def fixed_om(self, *, year: int) -> Money:
        """고정 O&M (원/년). 명목 기준이므로 물가로 에스컬레이션한다 (가정 A-2).
        20년 누계는 `A × ((1+i)^n − 1)/i` 와 원 단위로 일치한다 (§13.2.2 C-2)."""
        return to_won(self.fixed_om_won_per_year * self.escalation_factor(year=year))

    def throughput_kwh(self, *, year: int) -> float:
        """변동 O&M의 처리량 정의 = **연간 배터리 방전 kWh** (§13.2.2 C-3). 충전량을
        함께 세지 않는다 — 재충전은 방전에 종속된 되채움이라 같은 사건을 두 번 센다."""
        return self.annual_available_discharge_kwh(year=year)

    def cost_breakdown(self, *, year: int) -> dict[str, Money]:
        """변동 비용의 **분리 표시** 행 (`RC-EV-C6`). 열화 보상을 편익에서 빼지
        않고 여기에 따로 세운다 — 상계하면 순편익은 같아 보이지만 차주에게 얼마를
        물어 주는지가 사라진다."""
        y = int(Year(year))
        throughput = self.throughput_kwh(year=y)
        esc = self.escalation_factor(year=y)
        return {"충전기 변동 O&M": to_won(throughput * self.variable_om_won_per_kwh * esc),
                "V2G 배터리 열화 보상": to_won(
                    throughput * self.degradation_compensation_won_per_kwh * esc)}

    def variable_om(self, *, year: int) -> Money:
        """변동 O&M 합계 (원/년) — 열화 보상을 **포함**한다. 분리 표시는
        `cost_breakdown()` 이 맡되, 계약 6종만 보는 호출자에게도 열화 보상이
        전달되어야 한다. 별도 행에만 두면 그 비용은 조용히 사라진다."""
        return won_sum(self.cost_breakdown(year=year).values())

    def replacement_schedule(self, *, horizon: int) -> dict[int, Money]:
        """교체 스케줄 — 수명 도달 **다음 연도 초**에 계상 (§13.2.2 C-4).

        `lifetime` 은 **충전기**의 수명이다. 차량은 사업 자산이 아니어서 이
        모델에 수명이 없고, 그래서 이 자원에는 **본체·부속설비로 나눌 두
        수명이 없다** — `FR-104-AC4`(부속설비의 독립 수명을 본체와 분리 관리)를
        인용하지 않는 이유다 (R38-B. 종전 문면은 *「충전기는 차량과 별개의
        수명을 갖는 부속설비다 (FR-104-AC4)」* 였으나 차량 수명이 없으므로
        분리할 것이 없다).

        **`retire` 면 빈다** (`FR-104-AC3`) — 아무것도 다시 사지 않는다."""
        if horizon < 1:
            raise ValidationError(
                field="ev_v2g.horizon",
                reason=f"분석기간은 1년 이상입니다: {horizon}",
                action="분석기간(horizon)에 1 이상의 정수를 지정하십시오",
            )
        schedule: dict[int, Money] = {}
        if self.retires_at_end_of_life():
            return schedule
        year = self.lifetime + 1
        while year <= horizon:
            schedule[year] = to_won(
                self._replacement_cost_won() * self.replacement_escalation_factor(year=year))
            year += self.lifetime
        return schedule

    def salvage_value(self, *, year: int) -> Money:
        """잔존가치 (원) = `취득가 × 잔존수명 / 총수명` (§13.2.2 C-5 · FR-104-AC5).
        `year` 는 **평가 시점(보통 분석기간 최종연도)** 이다 — 계약이 분석기간을
        넘겨 주지 않으므로 호출자가 최종연도를 넣는다. 할인율은 재무 조건이지 자원
        속성이 아니므로 여기서 할인하지 않는다."""
        y = int(Year(year))
        n = self.lifetime
        install_year = ((y - 1) // n) * n + 1
        remaining = n - (y - install_year + 1)
        if remaining <= 0:
            return ZERO
        base = (
            self._initial_cost_won() if install_year == 1
            else self._replacement_cost_won()
            * self.replacement_escalation_factor(year=install_year)
        )
        return to_won(base * remaining / n)

    def discounted_salvage_value(self, *, year: int, discount_rate: float) -> Money:
        """최종연도 잔존가치를 현재가치로 할인한 값 (§13.2.2 C-5 예시)."""
        if discount_rate <= -1.0:
            raise ValidationError(
                field="ev_v2g.discount_rate",
                reason=f"할인율은 -100%보다 커야 합니다: {discount_rate}",
                action="할인율을 -1(-100%)보다 큰 값으로 지정하십시오",
            )
        y = int(Year(year))
        return to_won(float(self.salvage_value(year=y)) / (1.0 + discount_rate) ** y)


# ── 모듈 보조 함수 — 자원 상태를 읽지 않는 순수 계산 ─────────────────


def _check(owner: str, constraint: str, ok: Callable[[float], bool], **values: float) -> None:
    """정의역 위반을 **파라미터 이름과 함께** 알린다 — 이름 없이 거부하면
    파라미터가 25개인 생성자에서 어느 값이 문제인지 찾을 수 없다."""
    for label, value in values.items():
        if not ok(value):
            raise ValidationError(
                field=f"ev_v2g.{label}",
                reason=f"{owner}: {label} 은 {constraint}: {value}",
                action=f"{label} 값을 {constraint} 조건에 맞게 지정하십시오",
            )


def _connected_hours(start: int, end: int) -> list[int]:
    """접속가능시간대의 시각 목록. `start == end` 는 24시간 접속으로 읽는다."""
    if start == end:
        return list(range(HOURS_PER_DAY))
    if start < end:
        return list(range(start, end))
    return list(range(start, HOURS_PER_DAY)) + list(range(end))


def _cycle_offsets(hours: list[int], arrival_hour: int, dt: int) -> list[int]:
    """접속 스텝을 **도착 시각 기준 사이클 순서**로 늘어놓는다 (18~08시 접속이면
    [18, 19, …, 23, 00, …, 07])."""
    connected = set(hours)
    keyed: list[tuple[int, int]] = []
    for j in range(SECONDS_PER_DAY // dt):
        sec = j * dt
        hour = sec // SECONDS_PER_HOUR
        if hour in connected:
            offset = ((hour - arrival_hour) % HOURS_PER_DAY) * SECONDS_PER_HOUR
            keyed.append((offset + sec % SECONDS_PER_HOUR, j))
    keyed.sort()
    return [j for _, j in keyed]


def _steps_needed(total_kwh: float, step_capacity_kwh: float) -> float:
    """`total_kwh` 를 소화하는 데 필요한 최소 스텝 수. 용량 0이면 무한대다 —
    유한 대형 상수를 sentinel로 쓰지 않는다 (FR-403-AC4와 같은 규약)."""
    if total_kwh <= 0.0:
        return 0
    if step_capacity_kwh <= 0.0:
        return math.inf
    return math.ceil(total_kwh / step_capacity_kwh)


def _fill(
    series: list[float],
    idxs: list[int],
    start: int,
    *,
    total_kwh: float,
    power_kw: float,
    dt_hours: float,
    limit_kw: list[float] | None,
    sign: int,
) -> tuple[int, float]:
    """`idxs[start:]` 를 순서대로 채우고 `(다음 위치, 미충족량)` 을 돌려준다. 스텝
    상한은 충전기 출력과 계통 연계 상한 중 **작은 쪽**이다 — 연계 상한을 무시하면
    물리적으로 불가능한 편익이 계상된다."""
    remaining = total_kwh
    pos = start
    while pos < len(idxs) and remaining > ENERGY_TOLERANCE_KWH:
        i = idxs[pos]
        cap_kw = power_kw if limit_kw is None else min(power_kw, limit_kw[i])
        amount = min(remaining, max(cap_kw, 0.0) * dt_hours)
        if amount > 0.0:
            series[i] = sign * amount
            remaining -= amount
        pos += 1
    return pos, max(remaining, 0.0)
