"""`ESS` 배터리 자원 — 구획 WP-1b / spec FR-102-AC1.ESS.

검증 케이스: §13.2.3 `RC-ESS-P1~P4` · `B1~B2` · `X1` + §13.2.2 공통 비용 5종.
테스트가 먼저 있다 (NFR-105) — `tests/der/test_ess.py`. 의존은 `core.contracts`
뿐이다 (NFR-208-AC1).

**스스로 지키는 것 셋.** ① 가용량·정격출력·계통 한도를 넘는 계획은 잘라내지 않고
**거부하고 원인을 보고**한다 — 잘라내면 남은 값으로 수지가 닫혀 NFR-102 검사도
통과하고 사라진 편익은 아무데도 안 남는다. ② **반올림은 `to_won()` 에서만**
(NFR-103) — `RC-ESS-B1` 은 3,244.4 가 아니라 3,244.4444… 를 요구한다.
③ **열화는 보수적인 쪽** (FR-104-AC2) — 나은 쪽이면 교체가 밀려 회수기간이 짧다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import ClassVar

from core.contracts.der import DER, DispatchContext, DispatchResult
from core.contracts.units import (
    ENERGY_TOLERANCE_KWH,
    SECONDS_PER_HOUR,
    Money,
    to_won,
    won_sum,
)

HOURS_PER_DAY = 24
#: 1년 = 365일. `RC-ESS-P1` 의 연 방전 2,920 kWh = 8 kWh × 365 가 여기서 나온다
DAYS_PER_YEAR = 365.0
MONTHS_PER_YEAR = 12
#: 부동소수 비교 여유. kW 비교이므로 에너지 허용오차(kWh)와 구분해 둔다
_KW_TOLERANCE = 1e-9


class ESSOperatingMode(StrEnum):
    """ESS 운전 방법 (FR-105-AC1).

    **값은 spec 원문 그대로다** — 다듬으면 리포트의 운전 방법명이 조항과 갈려
    FR-105-AC4 가 가리키는 대상을 판정할 수 없다. 자원 클래스에 함께 두는 것은
    FR-105-AC2 요구다(새 운전 방법 추가 시 코어 엔진 수정 0줄).
    """

    SELF_CONSUMPTION = "자가소비 우선"
    TOU_ARBITRAGE = "TOU 차익거래"
    PEAK_SHAVING = "피크 저감"
    BACKUP_RESERVE = "백업 예비 확보"
    HYBRID = "혼합(가중치)"


#: 운전 방법별 (충전 시간대, 방전 시간대) — 하루 중 시각(0~23).
#:
#: 자원이 시간대를 드는 이유는 FR-105-AC2 다 — 엔진이 표를 들면 운전 방법
#: 하나 늘릴 때마다 엔진을 고쳐야 한다. 요금제 연동 최적화는 WP-6 의 몫이고,
#: 여기 값은 자원 단독 검증(§13.2.1 결정성)용 손계산 가능한 기본 프로파일이다.
#:
#: **`MappingProxyType` 인 이유 (NFR-205).** 평범한 `dict` 로 두면 모듈 수준
#: 가변 상태다. 지금은 아무도 고치지 않지만 그것이 다음 사람도 고치지 않는다는
#: 보장은 아니고, **케이스 그리드 병렬 실행(FR-805)에서 한 번의 변형은 다른
#: 케이스의 결과를 조용히 바꾼다** — 조항의 근거인 DER-VET `Params.py` 가 정확히
#: 그 형태였다. 읽기 전용으로 만들면 그 가능성 자체가 사라진다.
_MODE_WINDOWS: Mapping[ESSOperatingMode, tuple[tuple[int, ...], tuple[int, ...]]] = (
    MappingProxyType({
        ESSOperatingMode.SELF_CONSUMPTION: ((10, 11, 12, 13, 14, 15), (18, 19, 20, 21)),
        ESSOperatingMode.TOU_ARBITRAGE: ((1, 2, 3, 4, 5, 6), (18, 19, 20, 21)),
        ESSOperatingMode.PEAK_SHAVING: ((1, 2, 3, 4, 5, 6), (13, 14, 15, 16)),
        ESSOperatingMode.BACKUP_RESERVE: ((1, 2, 3, 4, 5, 6), (18, 19, 20, 21)),
    })
)


class ESS(DER):
    """배터리 에너지저장장치 (FR-102-AC1.ESS).

    파라미터는 spec 조항이 열거한 그대로다 — 정격용량(kWh), 정격출력(kW),
    RTE(%), SOC 상하한, 사이클수명, 달력수명, EOL 잔존율, 신품/사용후 구분.
    """

    #: spec 조항 ID `FR-102-AC1.ESS` 와 **같은 리터럴**. 슬러그화·소문자화
    #: 금지 — NFR-106 레지스트리 순회가 자원을 못 찾고도 초록불로 남는다.
    tag: ClassVar[str] = "ESS"

    #: FR-105-AC1 이 ESS 에 대해 열거한 운전 방법 전체
    OPERATING_MODES: ClassVar[tuple[ESSOperatingMode, ...]] = tuple(ESSOperatingMode)

    #: 사용후배터리의 초기 SOH (FR-102-AC1.ESS 「신품/사용후배터리」)
    SECOND_LIFE_INITIAL_SOH: ClassVar[float] = 0.80

    def __init__(
        self,
        *,
        name: str,
        capacity_kwh: float,
        power_kw: float,
        rte_pct: float = 90.0,
        soc_min_pct: float = 10.0,
        soc_max_pct: float = 90.0,
        cycle_life: int = 6000,
        calendar_life: int = 15,
        eol_soh_pct: float = 80.0,
        second_life: bool = False,
        cycles_per_year: float = 365.0,
        operating_mode: ESSOperatingMode = ESSOperatingMode.TOU_ARBITRAGE,
        mode_weights: dict[ESSOperatingMode, float] | None = None,
        backup_reserve_pct: float = 0.0,
        dt: int = SECONDS_PER_HOUR,
        capex_unit_won_per_kwh: float = 0.0,
        capex_extra_won: float = 0.0,
        vat_rate: float = 0.0,
        fixed_om_won_per_year: float = 0.0,
        escalation_rate: float = 0.0,
        variable_om_won_per_kwh: float = 0.0,
        replacement_unit_won_per_kwh: float | None = None,
        pcs_lifetime: int | None = None,
        pcs_cost_won: float = 0.0,
    ) -> None:
        for label, value in (("정격용량(kWh)", capacity_kwh), ("정격출력(kW)", power_kw),
                             ("연간 사이클 수", cycles_per_year)):
            if value <= 0:
                raise ValueError(f"{label}은 0보다 커야 합니다: {value}")
        for label, value in (("사이클수명", cycle_life), ("달력수명", calendar_life)):
            if value <= 0:
                raise ValueError(f"{label}은 1 이상입니다: {value}")
        if not 0.0 < rte_pct <= 100.0:
            raise ValueError(
                f"RTE(왕복효율)는 0 초과 100 이하 %입니다: {rte_pct}. 0.9 를 그대로 "
                "넘기고 있지 않은지 확인하십시오 (§7.5 비율)"
            )
        if not 0.0 <= soc_min_pct < soc_max_pct <= 100.0:
            raise ValueError(
                f"SOC 상하한이 성립하지 않습니다: 하한 {soc_min_pct}% / 상한 "
                f"{soc_max_pct}%. 0 ≤ 하한 < 상한 ≤ 100 이어야 가용량이 양수가 됩니다"
            )
        if not 0.0 <= backup_reserve_pct < 100.0:
            raise ValueError(f"백업 예비율은 0 이상 100 미만 %입니다: {backup_reserve_pct}")
        if pcs_lifetime is not None and pcs_lifetime <= 0:
            raise ValueError(f"PCS 수명은 1년 이상입니다: {pcs_lifetime}")

        self.capacity_kwh = float(capacity_kwh)
        self.power_kw = float(power_kw)
        self.rte = rte_pct / 100.0
        self.soc_min = soc_min_pct / 100.0
        self.soc_max = soc_max_pct / 100.0
        self.cycle_life = int(cycle_life)
        self.calendar_life = int(calendar_life)
        self.eol_soh = eol_soh_pct / 100.0
        self.second_life = bool(second_life)
        self.cycles_per_year = float(cycles_per_year)
        self.backup_reserve = backup_reserve_pct / 100.0
        self.initial_soh = self.SECOND_LIFE_INITIAL_SOH if self.second_life else 1.0

        if not 0.0 < self.eol_soh < self.initial_soh:
            # 사용후배터리(초기 80%)에 EOL 80%를 주면 **취득 즉시 EOL** 이 된다.
            # 교체비가 매년 잡히는 형태라 "보수적으로 나왔나 보다"로 읽힌다.
            raise ValueError(
                f"EOL 잔존율({eol_soh_pct}%)은 초기 SOH"
                f"({self.initial_soh * 100:.0f}%)보다 낮아야 합니다. 사용후배터리는 "
                "이미 80%에서 시작하므로 EOL 을 그보다 낮게(예: 60%) 지정하십시오"
            )

        self.mode_weights = self._normalize_weights(operating_mode, mode_weights)

        self._capex_unit = float(capex_unit_won_per_kwh)
        self._capex_extra = float(capex_extra_won)
        if not 0.0 <= vat_rate <= 1.0:
            raise ValueError(f"부가세율은 0~1 소수입니다: {vat_rate} (§7.5)")
        self._vat_rate = float(vat_rate)
        self._fixed_om = float(fixed_om_won_per_year)
        self._variable_om_unit = float(variable_om_won_per_kwh)
        self._replacement_unit = (
            self._capex_unit
            if replacement_unit_won_per_kwh is None
            else float(replacement_unit_won_per_kwh)
        )
        self._pcs_lifetime = pcs_lifetime
        self._pcs_cost = float(pcs_cost_won)

        super().__init__(
            name=name,
            dt=dt,
            lifetime=self.eol_year(),
            degradation_rate=self._annual_fade(),
            carries_electric=True,
            operating_mode=operating_mode,
            escalation_rate=escalation_rate,
        )

    # ── 운전 방법 (FR-105) ──────────────────────────────────────────

    @staticmethod
    def _normalize_weights(
        mode: ESSOperatingMode, weights: dict[ESSOperatingMode, float] | None
    ) -> dict[ESSOperatingMode, float]:
        """운전 방법 가중치를 항상 「합 1」로 정규화한다. 단일 모드도
        `{mode: 1.0}` 으로 만들면 이후 계산에 분기가 없다 — 분기가 남으면 혼합
        모드에만 걸리는 규칙이 생기고 단일 모드에서 빠져도 보이지 않는다."""
        if mode is not ESSOperatingMode.HYBRID:
            if weights:
                raise ValueError(
                    f"가중치는 {ESSOperatingMode.HYBRID.value} 모드에서만 지정합니다 "
                    f"(현재 {mode.value})"
                )
            return {mode: 1.0}

        if not weights:
            raise ValueError(
                f"{ESSOperatingMode.HYBRID.value} 모드는 가중치가 필요합니다. 무엇을 "
                "어떤 비율로 섞는지 없이는 예비 확보량도 운전창도 판정할 수 없습니다"
            )
        if any(w < 0 for w in weights.values()):
            raise ValueError("운전 방법 가중치는 음수가 될 수 없습니다")
        total = math.fsum(weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"운전 방법 가중치의 합이 1이 아닙니다: {total}. 합이 1이 아니면 "
                "가용량이 비율만큼 늘거나 줄어 편익이 왜곡됩니다"
            )
        return dict(weights)

    @property
    def dominant_mode(self) -> ESSOperatingMode:
        """운전창을 정하는 대표 모드 — 혼합이면 가중치 최대인 것. 가중치대로
        시간대를 쪼개 섞는 것은 **디스패치 엔진(WP-6)** 의 몫이다. 자원이 임의
        배분을 하면 결과가 두 벌이 되어 어느 쪽이 실렸는지 구분할 수 없다."""
        return max(
            self.mode_weights,
            key=lambda m: (self.mode_weights[m], -self.OPERATING_MODES.index(m)),
        )

    @property
    def charge_hours(self) -> tuple[int, ...]:
        return _MODE_WINDOWS[self.dominant_mode][0]

    @property
    def discharge_hours(self) -> tuple[int, ...]:
        return _MODE_WINDOWS[self.dominant_mode][1]

    @property
    def reserved_fraction(self) -> float:
        """백업 예비로 묶여 운전에 쓰이지 않는 비율 — **가중치만큼만** 묶는다."""
        weight = self.mode_weights.get(ESSOperatingMode.BACKUP_RESERVE, 0.0)
        return self.backup_reserve * weight

    # ── 열화 (FR-104-AC2) ───────────────────────────────────────────

    def _fade_span(self) -> float:
        """초기 SOH → EOL 낙폭. `1 − EOL` 이 아닌 이유는 사용후배터리다 —
        이미 0.8 에서 시작하므로 입력 수명은 **남은 수명**이며, `1 − EOL` 을
        쓰면 EOL 도달이 늦어져 보수적일 자리에서 낙관적이 된다."""
        return self.initial_soh - self.eol_soh

    def soh_cycle(self, *, year: int) -> float:
        """사이클 누적에 의한 SOH — 연 `cycles_per_year` 사이클 가정."""
        used = self.cycles_per_year * year / self.cycle_life
        return max(0.0, self.initial_soh - self._fade_span() * used)

    def soh_calendar(self, *, year: int) -> float:
        """달력 경과에 의한 SOH."""
        return max(0.0, self.initial_soh - self._fade_span() * year / self.calendar_life)

    def state_of_health(self, *, year: int) -> float:
        """`year` 년 말 SOH — 사이클/달력 중 **보수적(낮은) 값** (FR-104-AC2)."""
        if year < 0:
            raise ValueError(f"연도는 0 이상입니다: {year}")
        return min(self.soh_cycle(year=year), self.soh_calendar(year=year))

    def _annual_fade(self) -> float:
        """연간 열화율(소수) — `DER.degradation_rate` 에 싣는 보수적 연 환산값."""
        rate = self._fade_span() * max(
            1.0 / self.calendar_life, self.cycles_per_year / self.cycle_life
        )
        if rate >= 1.0:
            raise ValueError(
                f"연간 열화율이 {rate:.3f} 로 100%를 넘습니다. 사이클수명"
                f"({self.cycle_life}회)·달력수명({self.calendar_life}년)·연간 사이클"
                f"({self.cycles_per_year}회) 입력을 확인하십시오"
            )
        return rate

    def eol_year(self) -> int:
        """EOL 도달 해 (1-base, 올림). 사이클과 달력 중 **먼저 닿는 쪽**이
        수명이다. 연 단위 올림은 프로포마가 연 단위 문서이기 때문이며, 교체비는
        `RC-ALL-C4` 대로 **그 다음 연도 초**에 잡힌다."""
        by_cycle = self.cycle_life / self.cycles_per_year
        return max(1, math.ceil(min(float(self.calendar_life), by_cycle)))

    # ── 가용량·SOC (FR-102-AC1.ESS) ────────────────────────────────

    def _soh_at_start_of(self, year: int) -> float:
        """`year` 년 **초** SOH = 전년도 말 SOH. 그 해의 운전 가능량은 그 해가
        시작될 때 정해진다 — 연말 값을 쓰면 1년차부터 열화된 용량이 되어
        `RC-ESS-P1` 의 2,920 kWh 를 못 낸다."""
        return self.state_of_health(year=max(0, year - 1))

    def usable_capacity_kwh(self, *, year: int) -> float:
        """1사이클 가용 전력량 (kWh).

        `정격용량 × (SOC상한 − SOC하한) × SOH × (1 − 백업예비)`
        """
        window = self.capacity_kwh * (self.soc_max - self.soc_min)
        return window * self._soh_at_start_of(year) * (1.0 - self.reserved_fraction)

    def soc_bounds_kwh(self, *, year: int) -> tuple[float, float]:
        """그 해의 SOC 하한·상한 (kWh). 열화한 용량 위에서 다시 잡힌다."""
        effective = self.capacity_kwh * self._soh_at_start_of(year)
        return effective * self.soc_min, effective * self.soc_max

    def plan_discharge(self, *, soc_kwh: float, energy_kwh: float, year: int = 1) -> float:
        """방전 지시를 검증하고 실제 방전량(kWh)을 돌려준다 (`RC-ESS-X1`).

        **하한 침범은 잘라내지 않고 거부한다.** 조용히 잘라내면 가용량이 늘어난
        것과 같아 편익이 과대 계상되고, 잘라낸 값으로 수지가 닫혀 NFR-102 검사도
        통과한다."""
        if energy_kwh < 0:
            raise ValueError(f"{self.name}: 방전량은 음수가 될 수 없습니다: {energy_kwh}")
        low, _ = self.soc_bounds_kwh(year=year)
        available = soc_kwh - low
        if energy_kwh > available + ENERGY_TOLERANCE_KWH:
            raise ValueError(
                f"{self.name}: SOC 하한 침범 — 요구 방전량 {energy_kwh:.6g} kWh 가 "
                f"가용량 {available:.6g} kWh 를 초과합니다 "
                f"(현재 SOC {soc_kwh:.6g} kWh, 하한 {low:.6g} kWh, {year}년차)"
            )
        return energy_kwh

    # ── 연간 물리량 (`RC-ESS-P1` · `P2`) ────────────────────────────

    def annual_discharge_kwh(self, *, year: int) -> float:
        """연 방전량 = 가용량 × 연간 사이클 수."""
        return self.usable_capacity_kwh(year=year) * self.cycles_per_year

    def annual_charge_kwh(self, *, year: int) -> float:
        """연 충전량 = 방전량 / RTE. 왕복 손실을 충전 측에 싣는 관례다."""
        return self.annual_discharge_kwh(year=year) / self.rte

    def annual_loss_kwh(self, *, year: int) -> float:
        """연 손실 = 충전 − 방전. `충전 = 방전 + 손실` 이 항등식이다."""
        return self.annual_charge_kwh(year=year) - self.annual_discharge_kwh(year=year)

    def reducible_peak_kw(self, *, year: int = 1) -> float:
        """피크 저감 가능 출력 (kW) = 가용량 / 방전창 시간. **정격출력이 상한**
        이다 — 없으면 없는 출력으로 기본요금 편익이 난다 (`RC-ESS-B2`)."""
        window_hours = len(self.discharge_hours)
        return min(self.power_kw, self.usable_capacity_kwh(year=year) / window_hours)

    # ── 편익 (`RC-ESS-B1` · `B2`) ──────────────────────────────────

    def tou_arbitrage_benefit(
        self, *, peak_price_won: float, offpeak_price_won: float, year: int = 1
    ) -> Money:
        """TOU 차익거래 편익 (원/년) — `RC-ESS-B1`.

        `방전 kWh × 피크단가 − 충전 kWh × 경부하단가`. `won_sum` 은 NFR-103-M1
        — 항별로 반올림한 뒤 더해야 프로포마의 행별 값과 총계가 일치한다.
        """
        return won_sum(
            (
                self.annual_discharge_kwh(year=year) * peak_price_won,
                -self.annual_charge_kwh(year=year) * offpeak_price_won,
            )
        )

    def peak_shaving_benefit(
        self,
        *,
        demand_charge_won_per_kw: float,
        reduced_kw: float | None = None,
        months: int = MONTHS_PER_YEAR,
        year: int = 1,
    ) -> Money:
        """기본요금(피크) 절감 (원/년) — `RC-ESS-B2` / FR-401-AC2.PeakShaving.

        `저감 kW × 기본요금 단가 × 12개월`
        """
        kw = self.reducible_peak_kw(year=year) if reduced_kw is None else reduced_kw
        if kw > self.power_kw + _KW_TOLERANCE:
            raise ValueError(
                f"{self.name}: 저감 지시 {kw} kW 가 정격출력 {self.power_kw} kW 를 "
                "넘습니다. 없는 출력으로 기본요금 편익이 계상됩니다"
            )
        return to_won(kw * demand_charge_won_per_kw * months)

    # ── 비용 (§13.2.2 `RC-ALL-C1~C5`) ──────────────────────────────

    def _gross_capex_won(self) -> float:
        """CAPEX 본체 — `단가 × 용량 + 부대비`. **부가세 제외** (§13.2.2 C-1)."""
        return self._capex_unit * self.capacity_kwh + self._capex_extra

    def capex(self, *, year: int) -> Money:
        """`RC-ALL-C1` — `단가 × 용량 + 부대비`. 초기 투자는 1년차에만."""
        if year != 1:
            return to_won(0)
        return to_won(self._gross_capex_won())

    def capex_vat(self, *, year: int) -> Money:
        """`RC-ALL-C1` 부가세액 — 본체와 **분리** 계상 (§13.2.2 C-1).

        v1.0 계약에 자리가 없어 **이 자원만 세액 자체가 없었다.** 프로포마
        부가세 행의 ESS 열이 0이 되고, 그 0은 「면세」로도 「누락」으로도 읽힌다.
        """
        if year != 1:
            return to_won(0)
        return to_won(self._gross_capex_won() * self._vat_rate)

    def fixed_om(self, *, year: int) -> Money:
        """`RC-ALL-C2` — `A × (1+i)^(y−1)`. 20년 누계는 등비수열 합이 된다.
        합을 미리 내지 않는 것은 프로포마가 **연도별 행**을 요구하기 때문이며
        (FR-701-AC3), 누계는 재무 계층이 `won_sum` 으로 더한다.

        물가 계수는 계약의 `escalation_factor()` 다 — v1.0 에서는 이 자원만
        `inflation_pct`(**%**) 로 받아, 같은 「2%」가 다른 자원의 `0.02` 와 100배
        어긋난 채 어느 쪽도 오류가 아니었다 (v1.1 개정 ⑤)."""
        return to_won(self._fixed_om * self.escalation_factor(year=year))

    def variable_om(self, *, year: int) -> Money:
        """`RC-ALL-C3` — `처리량 × 단가`. **ESS 의 처리량은 방전 kWh** 다.
        열화로 처리량이 줄면 변동 O&M 도 함께 준다 — 1년차 값을 20년 내내
        쓰면 후반 O&M 이 과대 계상된다.

        단가에도 물가 계수를 걸어 **고정 O&M 과 같은 명목 기준**으로 맞춘다.
        한쪽만 실질이면 20년 누계에서 두 항목의 비율이 실제와 달라지고, 어느
        쪽이 기준인지 프로포마에 표시가 남지 않는다."""
        return to_won(
            self.annual_discharge_kwh(year=year)
            * self._variable_om_unit
            * self.escalation_factor(year=year)
        )

    def _battery_cost(self) -> Money:
        """배터리 교체 단가 × 용량. 부대비(설치·계통연계)는 재취득하지 않는다."""
        return to_won(self._replacement_unit * self.capacity_kwh)

    def _acquisitions(self, *, horizon: int) -> dict[int, Money]:
        """{취득 연도: 취득가} — 최초 취득(1년차)과 배터리 교체분. 잔존가치를
        **마지막 취득 시점**부터 세기 위한 것이다 — 최초 취득만 보면 교체
        직후에도 잔존가치가 0으로 잡혀 새 배터리가 통째로 사라진다."""
        acquired: dict[int, Money] = {1: self.capex(year=1)}
        year = self.lifetime + 1
        while year <= horizon:
            acquired[year] = self._battery_cost()
            year += self.lifetime
        return acquired

    def replacement_schedule(self, *, horizon: int) -> dict[int, Money]:
        """`RC-ALL-C4` — 수명 도달 **다음 연도 초**에 계상. 배터리와 PCS 수명은
        **독립**이다 (FR-104-AC4) — 본체 수명만 보면 PCS 교체비가 통째로 빠진다.
        같은 해에 겹치면 합산한다."""
        # 1년차 최초 취득은 CAPEX 이지 교체비가 아니므로 제외한다
        schedule: dict[int, Money] = {
            y: cost for y, cost in self._acquisitions(horizon=horizon).items() if y != 1
        }

        if self._pcs_lifetime is not None and self._pcs_cost > 0:
            cost = to_won(self._pcs_cost)
            year = self._pcs_lifetime + 1
            while year <= horizon:
                schedule[year] = Money(schedule.get(year, to_won(0)) + cost)
                year += self._pcs_lifetime

        return schedule

    def salvage_value(self, *, year: int) -> Money:
        """`RC-ALL-C5` — `취득가 × 잔존수명 / 총수명`. `year` 년에 분석이 끝난다고
        볼 때의 값이며 **할인은 하지 않는다** — 할인은 CBA 계층(WP-7)의 몫이고,
        여기서 함께 하면 두 번 할인되어 "보수적으로 보여서" 검출되지 않는다."""
        acquired = self._acquisitions(horizon=year)
        last_year = max(y for y in acquired if y <= year)
        used = year - last_year + 1  # 취득 연도부터 센다 (1-base)
        remaining = max(0, self.lifetime - used)
        return to_won(int(acquired[last_year]) * remaining / self.lifetime)

    # ── 디스패치 (FR-301) ──────────────────────────────────────────

    def value_streams(self) -> tuple[str, ...]:
        """ESS 가 만드는 편익 (`FR-401-AC2.<키>`) — **운전 방법이 정한다.**

        백업 예비 확보의 정전 회피 편익(`Resilience`)은 Phase 3이므로 선언하지
        않는다 — 값 0인 행은 「편익 없음」과 「미구현」을 구분하지 못한다.
        혼합 모드는 가중치 0보다 큰 **모든** 모드의 편익을 갖는다. 대표 모드만
        보면 30% 섞인 피크 저감 편익이 통째로 사라진다.
        """
        active = {m for m, w in self.mode_weights.items() if w > 0.0}
        streams: list[str] = []
        if active & {ESSOperatingMode.SELF_CONSUMPTION, ESSOperatingMode.TOU_ARBITRAGE}:
            streams.append("SelfConsumption")
        if ESSOperatingMode.PEAK_SHAVING in active:
            streams.append("PeakShaving")
        return tuple(streams)

    def dispatch(self, ctx: DispatchContext) -> DispatchResult:
        """하루 1주기 충·방전 프로파일을 스텝별로 전개한다.

        부호 규약: **양수 = 방전, 음수 = 충전**. 열·냉·연료는 0으로 남긴다 —
        플래그가 거짓인 매체의 값은 사라진다 (FR-101-AC4).

        **부분 창은 연초부터의 연속 구간이다.** 하루치 에너지를 시각별로 펼치고
        창 길이만큼 잘라 내므로, 24스텝은 48스텝의 앞 24스텝과 정확히 같다 —
        하루 에너지를 창 길이에 재배분하면 그 성질이 깨진다.
        """
        self.check_context(ctx)
        steps_per_hour = SECONDS_PER_HOUR // ctx.dt
        hours_per_step = ctx.dt / SECONDS_PER_HOUR

        daily = (
            self.usable_capacity_kwh(year=int(ctx.year))
            * self.cycles_per_year
            / DAYS_PER_YEAR
        )
        out_step = daily / (len(self.discharge_hours) * steps_per_hour)
        in_step = daily / self.rte / (len(self.charge_hours) * steps_per_hour)

        self._check_power(out_step, hours_per_step, "방전")
        self._check_power(in_step, hours_per_step, "충전")

        electric = [0.0] * ctx.steps
        for i in range(ctx.steps):
            hour = (i // steps_per_hour) % HOURS_PER_DAY
            if hour in self.discharge_hours:
                electric[i] = out_step
            elif hour in self.charge_hours:
                electric[i] = -in_step

        self._check_grid_limit(electric, ctx, hours_per_step)

        zeros = [0.0] * ctx.steps
        return DispatchResult(
            electric=electric, heat=zeros, cool=list(zeros), fuel=list(zeros)
        )

    def _check_power(self, step_kwh: float, hours_per_step: float, label: str) -> None:
        """정격출력 초과를 **거부**한다. 잘라내면 없는 출력으로 편익이 난다."""
        kw = step_kwh / hours_per_step
        if kw > self.power_kw + _KW_TOLERANCE:
            raise ValueError(
                f"{self.name}: {label} 계획 {kw:.6g} kW 가 정격출력 "
                f"{self.power_kw:.6g} kW 를 넘습니다. 운전창이나 정격출력을 키우십시오 "
                "— 자동으로 잘라내면 그만큼의 편익이 조용히 사라집니다"
            )

    def _check_grid_limit(
        self, electric: list[float], ctx: DispatchContext, hours_per_step: float
    ) -> None:
        """계통 연계 한도 초과를 **실행 전에 검출하고 원인을 보고**한다 (FR-403)."""
        if ctx.grid_limit_kw is None:
            return
        for i, value in enumerate(electric):
            kw = abs(value) / hours_per_step
            if kw > ctx.grid_limit_kw[i] + _KW_TOLERANCE:
                raise ValueError(
                    f"{self.name}: {i}번 스텝의 계통 연계 한도 초과 — "
                    f"계획 {kw:.6g} kW / 한도 {ctx.grid_limit_kw[i]:.6g} kW"
                )
