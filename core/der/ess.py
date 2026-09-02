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
from collections.abc import Mapping, Sequence
from enum import StrEnum
from types import MappingProxyType
from typing import ClassVar, NoReturn

from core.contracts.der import DER, EOL_REPLACE, DispatchContext, DispatchResult
from core.contracts.units import (
    ENERGY_TOLERANCE_KWH,
    SECONDS_PER_HOUR,
    Money,
    to_won,
    won_sum,
)
from core.contracts.validation import ValidationError

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
    #: R51/WP-3 신설 — 한전(계통운영자)에 도움을 주는 두 용도. 값은 사용자
    #: 문면 그대로다(`docs/decisions-2026-09-01-R51.md` §3) — 다듬으면 위 규칙이
    #: 경고하는 대상이 된다.
    GRID_DISCHARGE = "계통 방전"
    SEMI_CENTRAL_DISPATCH = "준중앙급전 등록"


class ESSChargeSource(StrEnum):
    """충전원 (`docs/decisions-2026-08-31-R48.md` §1). **운전 방법과 직교하는
    별도 축이다** — `_MODE_WINDOWS` 는 언제 충전하는지만 정하고 어디서
    충전하는지는 정하지 않았고, 그 빈자리가 심야 계통충전을 「태양광 연계」로
    착각하게 만들었다(같은 문서 「⚠⚠ 그런데」절).

    `core.contracts.der.DER` 에 올리지 않는다 — 충전원은 저장장치에만 있는
    개념이라 `DER` 계약에 올리면 `PV`·`Load`·`HeatPump` 전부가 뜻 없는 물음에
    답해야 한다(판정 A-1).
    """

    PV_SURPLUS = "태양광 잉여"
    GRID = "계통"


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
        # R51/WP-3 신설 — 방전 시각을 **계통운영자가 정하는** 두 모드다. 사업자가
        # 고른 창이 아니라 손계산 가능한 대표 프로파일이며, 계통 전체 수요 피크와
        # 겹치는 저녁(18~21시)을 그대로 쓴다 — 실제 지시 시각은 제도가 서면 배선한다.
        ESSOperatingMode.GRID_DISCHARGE: ((1, 2, 3, 4, 5, 6), (18, 19, 20, 21)),
        ESSOperatingMode.SEMI_CENTRAL_DISPATCH: ((1, 2, 3, 4, 5, 6), (18, 19, 20, 21)),
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

    #: 이 자원이 받는 충전원 선언 목록 (판정 A-2) — `OPERATING_MODES` 와 같은
    #: 관례다. 목록 밖 값은 `_coerce_charge_source()` 가 거부한다.
    CHARGE_SOURCES: ClassVar[tuple[ESSChargeSource, ...]] = tuple(ESSChargeSource)

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
        # **기본값이 `GRID` 인 이유**: 종전 동작이 그것이고, 기본값을 바꾸면
        # 이 인자를 모르는 기존 호출자 전부의 수가 조용히 움직인다. 이 사업의
        # 값은 러너가 명시로 준다(`docs/decisions-2026-08-31-R48.md` §1 ·
        # `e2e_runner.py::ESS_CHARGE_SOURCE_DEFAULT`).
        charge_source: ESSChargeSource | str = ESSChargeSource.GRID,
        #: 시각별(0~23) PV 잉여 kWh — `charge_source=PV_SURPLUS` 일 때만 쓴다
        #: (판정 A-3). `ESS` 는 형제 구획을 import 할 수 없으므로(`NFR-208-AC2`)
        #: PV 를 참조하지 않고 시계열로 받는다.
        pv_surplus_profile_kwh: Sequence[float] | None = None,
        backup_reserve_pct: float = 0.0,
        dt: int = SECONDS_PER_HOUR,
        capex_unit_won_per_kwh: float = 0.0,
        capex_extra_won: float = 0.0,
        vat_rate: float = 0.0,
        fixed_om_won_per_year: float = 0.0,
        escalation_rate: float = 0.0,
        replacement_escalation_rate: float | None = None,
        variable_om_won_per_kwh: float = 0.0,
        replacement_unit_won_per_kwh: float | None = None,
        pcs_lifetime: int | None = None,
        pcs_cost_won: float = 0.0,
        end_of_life_action: str = EOL_REPLACE,
    ) -> None:
        for label, field_name, value in (
            ("정격용량(kWh)", "ess.capacity_kwh", capacity_kwh),
            ("정격출력(kW)", "ess.power_kw", power_kw),
            ("연간 사이클 수", "ess.cycles_per_year", cycles_per_year),
            ("사이클수명", "ess.cycle_life", cycle_life),
            ("달력수명", "ess.calendar_life", calendar_life),
        ):
            _positive(value, field=field_name, label=label, name=name)
        if not 0.0 < rte_pct <= 100.0:
            # ⚠ **`_in_range()` 로 접지 않는다.** `rule="DV-3"` 이 `ValidationError(...)`
            # 호출에 **리터럴**로 있어야 `tests/contract/test_dv_rule_enforcement.py`
            # 의 AST 스캐너가 「실제로 던지는 코드」로 센다 — 변수로 넘기면(`_in_range`
            # 처럼) 스캐너가 **의도적으로** 세지 않는다(그 파일 독스트링이 그렇게
            # 적는다). R51/WP-3 이 이 자리에서 그 함정을 실측으로 밟았다.
            raise ValidationError(
                field="ess.rte",
                reason=f"{name}: RTE(왕복효율)는 0 초과 100 이하 %입니다 (받은 값 {rte_pct})",
                action="RTE 를 0 초과 100 이하 %값으로 지정하십시오(0.9 를 그대로 넘기지 않도록)",
                rule="DV-3",
            )
        _in_range(
            soc_min_pct, 0.0, 100.0, field="ess.soc_min", label="SOC 하한(%)", name=name,
            rule="DV-2",
        )
        _in_range(
            soc_max_pct, 0.0, 100.0, field="ess.soc_max", label="SOC 상한(%)", name=name,
            rule="DV-2",
        )
        if soc_min_pct >= soc_max_pct:
            raise ValidationError(
                field="ess.soc_min",
                reason=f"{name}: SOC 하한({soc_min_pct}%)이 상한({soc_max_pct}%) 이상입니다",
                action="SOC 하한을 상한보다 작은 값으로 고치십시오 — 가용량이 양수가 됩니다",
                rule="DV-2",
            )
        _in_range(backup_reserve_pct, 0.0, 100.0, field="ess.backup_reserve", label="백업 예비율",
            name=name, high_exclusive=True)
        if pcs_lifetime is not None:
            _positive(pcs_lifetime, field="ess.pcs_lifetime", label="PCS 수명", name=name)

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

        # 사용후배터리(초기 80%)에 EOL 80%를 주면 **취득 즉시 EOL** 이 된다.
        # 교체비가 매년 잡히는 형태라 "보수적으로 나왔나 보다"로 읽힌다.
        _in_range(eol_soh_pct, 0.0, self.initial_soh * 100.0, field="ess.eol_soh", label="EOL(%)",
            name=name, low_exclusive=True, high_exclusive=True)

        self.mode_weights = self._normalize_weights(operating_mode, mode_weights, name=name)
        self.charge_source = self._coerce_charge_source(charge_source, name=name)
        self.pv_surplus_profile_kwh = self._check_pv_surplus(pv_surplus_profile_kwh, name)

        self._capex_unit = float(capex_unit_won_per_kwh)
        self._capex_extra = float(capex_extra_won)
        self._vat_rate = _in_range(
            vat_rate, 0.0, 1.0, field="ess.vat_rate", label="부가세율", name=name
        )
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
            degradation_rate=self._annual_fade(name=name),
            carries_electric=True,
            operating_mode=operating_mode,
            escalation_rate=escalation_rate,
            replacement_escalation_rate=replacement_escalation_rate,
            end_of_life_action=end_of_life_action,
        )

    # ── 운전 방법 (FR-105) ──────────────────────────────────────────

    @staticmethod
    def _normalize_weights(
        mode: ESSOperatingMode, weights: dict[ESSOperatingMode, float] | None, *, name: str
    ) -> dict[ESSOperatingMode, float]:
        """운전 방법 가중치를 항상 「합 1」로 정규화한다. 단일 모드도
        `{mode: 1.0}` 으로 만들면 이후 계산에 분기가 없다 — 분기가 남으면 혼합
        모드에만 걸리는 규칙이 생기고 단일 모드에서 빠져도 보이지 않는다."""
        def reject(reason: str, action: str) -> NoReturn:
            raise ValidationError(field="ess.mode_weights", reason=reason, action=action)

        if mode is not ESSOperatingMode.HYBRID:
            if weights:
                reject(
                    f"{name}: 가중치는 {ESSOperatingMode.HYBRID.value} 모드에서만 "
                    f"지정합니다 (현재 {mode.value})",
                    "mode_weights 인자를 빼거나 운전 방법을 "
                    f"{ESSOperatingMode.HYBRID.value} 로 바꾸십시오",
                )
            return {mode: 1.0}

        if not weights:
            reject(
                f"{name}: {ESSOperatingMode.HYBRID.value} 모드는 가중치가 필요합니다",
                "무엇을 어떤 비율로 섞는지 mode_weights 로 지정하십시오 — 없으면 예비 "
                "확보량도 운전창도 판정할 수 없습니다",
            )
        if any(w < 0 for w in weights.values()):
            reject(
                f"{name}: 운전 방법 가중치는 음수가 될 수 없습니다",
                "mode_weights 의 모든 값을 0 이상으로 지정하십시오",
            )
        total = math.fsum(weights.values())
        if abs(total - 1.0) > 1e-9:
            reject(
                f"{name}: 운전 방법 가중치의 합이 1이 아닙니다 (합 {total})",
                "mode_weights 의 합이 1이 되도록 지정하십시오 — 합이 1이 아니면 가용량이 "
                "비율만큼 늘거나 줄어 편익이 왜곡됩니다",
            )
        return dict(weights)

    # ── 충전원 (판정 A-1~A-3) ───────────────────────────────────────

    @classmethod
    def _coerce_charge_source(cls, source: ESSChargeSource | str, *, name: str) -> ESSChargeSource:
        """문자열을 충전원 열거값으로 승격하고 목록 소속을 검사한다 (판정 A-2).

        `PV._coerce_mode()` 와 같은 모양이다 — 케이스 그리드가 문자열로 값을
        건넬 수 있어야 한다(`FR-105-AC5` 가 운전 방법에 대해 이미 세운 관례).

        ⚠ **규칙 ID 를 비운다.** `DER._check_operating_mode` 의 `DV-14` 는
        「운전 방법이 선언 목록에 속함」이고, 충전원은 그 규칙이 아니다 — 계약을
        건드리지 않고 신설한 축이라 `DV-14` 를 재사용하면 그 규칙이 실제로
        지키는 것과 어긋난다.
        """
        try:
            return ESSChargeSource(source)
        except ValueError as e:
            allowed = ", ".join(s.value for s in cls.CHARGE_SOURCES)
            reason = f"{name}: 선언되지 않은 충전원입니다: {source!r}"
            action = f"ESS 가 지원하는 충전원 중 하나를 지정하십시오 — [{allowed}]"
            raise ValidationError(field="ess.charge_source", reason=reason, action=action) from e

    def _reject_pv_surplus_profile(self, reason: str, action: str) -> NoReturn:
        """`_check_pv_surplus()` 전용 — 필드 하나에 걸린 거부 셋을
        한 곳으로 모은다(코드 스프롤 방지, NFR-206)."""
        raise ValidationError(field="ess.pv_surplus_profile_kwh", reason=reason, action=action)

    def _check_pv_surplus(
        self, profile: Sequence[float] | None, name: str) -> tuple[float, ...] | None:
        """`charge_source` 와 `pv_surplus_profile_kwh` 의 조합·형태만 검사한다
        (판정 §1 · A-8-d).

        ⚠⚠ **「시각별 충전량이 잉여를 넘으면 거부」는 판정 A-8-b 로 없어졌다** —
        모자라면 거부가 아니라 「가능한 만큼」 충전한다(`_pv_surplus_charge_kwh_by_hour`
        가 그 계획을 짓는다). 여기 남는 것은 판정 §1 이 요구하는 **형태 검사 넷**뿐이다.
        """
        if self.charge_source is ESSChargeSource.GRID:
            if profile is not None:
                self._reject_pv_surplus_profile(f"{name}: 충전원=계통인데 PV잉여 시계열을 받음",
                    "charge_source 를 PV_SURPLUS 로 바꾸거나 인자를 빼십시오")
            return None

        # charge_source == PV_SURPLUS
        if profile is None or not any(v > 0.0 for v in profile):
            self._reject_pv_surplus_profile(
                f"{name}: 충전원이 태양광 잉여인데 잉여 시계열이 없거나 전부 0입니다",
                "pv_surplus_profile_kwh 에 시각별(0~23) PV 잉여 kWh 를 지정하십시오",
            )
        if len(profile) != HOURS_PER_DAY:
            self._reject_pv_surplus_profile(
                f"{name}: PV 잉여 시계열은 {HOURS_PER_DAY}행이어야 합니다(받은 값 "
                f"{len(profile)}행)",
                f"pv_surplus_profile_kwh 를 {HOURS_PER_DAY}행 시계열로 맞추십시오",
            )
        return tuple(float(v) for v in profile)

    def _pv_surplus_charge_kwh_by_hour(self, *, year: int) -> dict[int, float]:
        """대표일 시각별 **실제** 충전량(kWh) — `PV_SURPLUS` 전용 (판정 A-8-a·b).

        시각(0~23)을 차례로 훑어 **방전창을 뺀, 잉여가 있는 모든 시각**에서
        `min(그 시각 잉여, 정격출력 1시간분, 남은 저장 여유)` 만큼 채운다.
        여유가 다 차거나 잉여가 없는 시각은 건너뛴다 — **거부하지 않는다**
        (A-8-b). 남는 여유의 상한은 `cycles_per_year` 다(A-8-c — 잉여가
        넘치도록 많아도 사이클 상한은 지킨다).

        ⚠ **이 충전이 가구 부하보다 앞선다** — 그 우선순위의 정본 선언은
        `e2e_runner._resolve_ess_dispatch_inputs` 독스트링에 있다(사본을 두지
        않는다).
        """
        profile = self.pv_surplus_profile_kwh
        assert profile is not None  # charge_source==PV_SURPLUS 면 생성자가 보장한다
        daily_cap = self.usable_capacity_kwh(year=year) * self.cycles_per_year / DAYS_PER_YEAR
        room_kwh = daily_cap / self.rte
        charged: dict[int, float] = {}
        for hour in range(HOURS_PER_DAY):
            if hour in self.discharge_hours or room_kwh <= 0.0 or profile[hour] <= 0.0:
                continue
            amount = min(profile[hour], self.power_kw, room_kwh)  # 셋 다 양수라 amount>0
            charged[hour] = amount
            room_kwh -= amount
        return charged

    def realized_cycles_per_year(self, *, year: int) -> float:
        """실제 연 사이클 수 — `PV_SURPLUS` 에서는 잉여가 모자라면
        `cycles_per_year`(상한)보다 **작을 수 있다**(판정 A-8-c). `GRID` 에서는
        언제나 `cycles_per_year` 와 같다. 「365 사이클로 샀는데 실제로는
        얼마나 돌았는가」를 밖에서 읽는 자리다."""
        capacity = self.usable_capacity_kwh(year=year)
        return self.annual_discharge_kwh(year=year) / capacity if capacity > 0.0 else 0.0

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

    def _annual_fade(self, *, name: str) -> float:
        """연간 열화율(소수) — `DER.degradation_rate` 에 싣는 보수적 연 환산값.

        **경계는 [0,100%) 이며 DV-3([0,10%])보다 넓다** — 대장 경계로 좁히는 것은
        동작 변경이라 이 구획의 일이 아니다(브리프 판정). 그래서 `rule` 을 비운다.
        """
        rate = self._fade_span() * max(
            1.0 / self.calendar_life, self.cycles_per_year / self.cycle_life
        )
        if rate >= 1.0:
            raise ValidationError(
                field="ess.degradation_rate",
                reason=f"{name}: 연간 열화율 {rate:.3f} 가 100% 초과 (사이클·달력·연사이클 조합)",
                action="사이클수명·달력수명·연간 사이클 수를 조정해 100% 미만이 되도록 하십시오",
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
                f"{self.name}: SOC 하한 침범 — 요구 방전량 {energy_kwh:.6g} kWh 가 가용량 "
                f"{available:.6g} kWh 를 초과합니다 (현재 SOC {soc_kwh:.6g} kWh, 하한 "
                f"{low:.6g} kWh, {year}년차)")
        return energy_kwh

    # ── 연간 물리량 (`RC-ESS-P1` · `P2`) ────────────────────────────

    def annual_discharge_kwh(self, *, year: int) -> float:
        """연 방전량. `GRID` = 가용량 × 연간 사이클 수(종전 그대로). `PV_SURPLUS` 는
        **실제로 채운 잉여**가 정한다(판정 A-8-c) — `cycles_per_year` 는 상한일 뿐이라
        잉여가 모자라면 이 값이 그보다 작을 수 있다(`realized_cycles_per_year` 참조).
        """
        if self.charge_source is ESSChargeSource.PV_SURPLUS:
            daily_charge = math.fsum(self._pv_surplus_charge_kwh_by_hour(year=year).values())
            return daily_charge * self.rte * DAYS_PER_YEAR
        return self.usable_capacity_kwh(year=year) * self.cycles_per_year

    def annual_charge_kwh(self, *, year: int) -> float:
        """연 충전량 = 방전량 / RTE. 왕복 손실을 충전 측에 싣는 관례다."""
        return self.annual_discharge_kwh(year=year) / self.rte

    def annual_loss_kwh(self, *, year: int) -> float:
        """연 손실 = 충전 − 방전. `충전 = 방전 + 손실` 이 항등식이다."""
        return self.annual_charge_kwh(year=year) - self.annual_discharge_kwh(year=year)

    def reducible_peak_kw(
        self, *, year: int = 1, site_load_kw: Sequence[float] | None = None) -> float:
        """피크 저감 가능 출력 (kW) — **자가 부하와 겹치는 방전분에서만** 난다
        (판정 §4). `site_load_kw` 는 시각별(0~23) 사업장 부하다.

        `site_load_kw` 가 없으면 **0** 이다 — 이 자원 혼자서는 「무엇의 피크를
        낮췄는가」에 답할 수 없다. 기본요금은 사업장 **최대부하**로 매겨지므로,
        그 최대부하 시각이 방전창 밖이면 창 안에서 아무리 방전해도 그 피크는
        내려가지 않는다(보수적인 쪽, 모듈 독스트링 「스스로 지키는 것 셋」③).

        ⚠ **한계** — 시간 해상도가 하루 24스텝 대표일이고 월별 피크를 모형화
        하지 않는다. 실제 월별 최대부하 시각이 대표일과 다르면 이 값은 그 달의
        기본요금 절감을 과소·과대 계상할 수 있다.
        """
        if site_load_kw is None:
            return 0.0
        peak_hour = max(range(len(site_load_kw)), key=lambda h: site_load_kw[h])
        if peak_hour not in self.discharge_hours:
            return 0.0
        window_hours = len(self.discharge_hours)
        return min(
            self.power_kw,
            self.usable_capacity_kwh(year=year) / window_hours,
            site_load_kw[peak_hour],
        )

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
        self, *, demand_charge_won_per_kw: float, reduced_kw: float | None = None,
        months: int = MONTHS_PER_YEAR, year: int = 1, site_load_kw: Sequence[float] | None = None,
    ) -> Money:
        """기본요금(피크) 절감 (원/년) — `RC-ESS-B2` / FR-401-AC2.PeakShaving.

        `저감 kW × 기본요금 단가 × 12개월`. `reduced_kw` 를 주지 않으면
        `reducible_peak_kw(site_load_kw=site_load_kw)` 로 산정한다 — `site_load_kw`
        없이는 0 이다(판정 §4, `reducible_peak_kw` 독스트링 참조).
        """
        kw = (
            self.reducible_peak_kw(year=year, site_load_kw=site_load_kw)
            if reduced_kw is None
            else reduced_kw
        )
        if kw > self.power_kw + _KW_TOLERANCE:
            raise ValueError(
                f"{self.name}: 저감 {kw}kW 가 정격출력 {self.power_kw}kW 초과 — 없는 편익 계상"
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
        """배터리 교체 단가 × 용량. 부대비(설치·계통연계)는 재취득하지 않는다.

        **1년차 기준(실질) 가격이다** — 물가 계수는 부르는 쪽(`_acquisitions()`)이
        교체 연도를 알고 곱한다. 여기서 곱하려면 이 함수가 연도를 받아야 하고,
        그러면 「단가」와 「그 해의 지출」이 한 이름에 겹친다.
        """
        return to_won(self._replacement_unit * self.capacity_kwh)

    def _acquisitions(
        self, *, horizon: int
    ) -> tuple[tuple[int, dict[int, float]], ...]:
        """부품별 `(수명, {취득 연도: 취득가})` — 배터리와 PCS 를 **갈라** 담는다.
        잔존가치를 **마지막 취득 시점**부터 세기 위한 것이다 — 최초 취득만 보면
        교체 직후에도 잔존가치가 0으로 잡혀 새 배터리가 통째로 사라진다.

        ## 왜 부품별로 갈랐는가 (R42 · R40 ② 가 남긴 비대칭)

        R40 이 PCS **교체비**를 `replacement_schedule()` 에 배선하면서 이 함수는
        건드리지 않아, **교체비는 계상되는데 그 잔존가치는 없는** 상태가 됐다 —
        `tests/casegrid/test_lifecycle_wiring.py` ⓒ 가 *「스케줄에만 있다 → 교체비는
        냈는데 그 설비의 잔존가치가 사라진다」* 로 경고한 바로 그 방향이고, 결론을
        **한 방향으로만** 나쁘게 만들어 「보수적이라 안전하다」로 읽히는 형태다.

        접어서 담을 수는 없다 — 배터리와 PCS 는 **수명이 다르다.** 사전 하나로
        접으면 20년차에 「마지막 취득 = 15년차 PCS」가 되고 그 잔존가치를 **배터리
        수명**으로 재게 되어, PCS 가 배터리만큼 버티는 설비가 된다. `PV` 가 본체·
        인버터에 대해 같은 이유로 갈라 담았고 **그쪽이 정본이다**
        (`pv.py::_acquisitions` 독스트링).

        ⚠ **최초 PCS 를 취득분으로 세지 않는다.** 대장의 설비 단가
        (`capex.ess.new`)는 설치 완료 기준이므로 최초 PCS 값은 이미
        `_gross_capex_won()` 안에 있고, 여기서 또 세면 **초기투자에 없는 지출**의
        잔존가치를 세게 된다. 반대로 본체 취득가에서 PCS 몫을 떼어내지도 않았다 —
        떼려면 「설비 단가의 몇 %가 PCS 인가」를 새로 정해야 하고 **그 값이 대장에
        없다**(`Q-2` 회신에 묶여 있다 · `status-human.md`). **모르는 값을 채우지
        않는다.** 그 결과 최초 PCS 몫이 배터리 몫의 잔존가치에 남아 있으나, 그것은
        배터리를 아직 교체하지 않은 해까지만이다 — 교체하는 순간 「마지막 취득
        시점부터」 규약이 리셋한다. `PV` 의 인버터가 같은 자리에 있다.

        ⚠ **`replacement_schedule()` 이 이 함수에서 파생된다** — 두 곳이 갈리면
        위 비대칭이 조용히 다시 생기므로 **같은 조건을 두 곳에 적지 않는다.**

        ⚠⚠ **`retire` 면 재취득이 없다** (`FR-104-AC3` · R39-E2 가 고쳤다).
        `replacement_schedule()` 은 `retire` 에서 **빈 사전**을 내는데 이 함수가
        그것을 보지 않아 **사지도 않은 배터리의 잔존가치**를 `retire` 자원에
        붙이고 있었다. `PV._acquisitions()` 가 같은 결함을 가졌고 그쪽을 고칠
        때 세운 그물(`tests/casegrid/test_lifecycle_wiring.py` ⓒ)이 **이쪽을
        곧바로 잡았다** — 같은 형태가 자원마다 따로 있었다는 뜻이다.

        ⚠ **위 `retire` 갈래는 실행 경로의 수를 움직이지 않는다** — 러너의 `ESS` 는
        `replace` 이므로 그 갈래를 타지 않는다(아래 물가 계수는 **움직인다**).
        ★ **PCS 갈래도 마찬가지다** — 러너의 `ESS` 에는 PCS 가 없어 결론축이
        움직이지 않는다. 그래서 급하지 않았고, PCS 를 쓰는 케이스가 들어오는 날
        조용히 틀리는 것을 막으려고 지금 닫는다.

        ## 재취득분에 **물가 계수를 곱한다** (R40 · `DV-7`)

        대장이 `price_basis: "명목"` 을 **한 번** 선언하므로 18년차 지출을 오늘의
        원으로 적으면 **그 지출만 실질이 되어** 선언과 어긋난다. R39 까지 이 함수는
        계수를 받고도 쓰지 않았고, 러너의 주석(`e2e_runner.py` ⓑ)은 *「배터리
        교체비에 굴린다」* 고 이미 **선언하고 있었다** — 이 저장소가 거듭 만나 온
        「선언과 구현이 갈린」 형태다.

        **`salvage_value()` 가 같은 사전을 읽으므로 잔존가치도 함께 움직인다** —
        그래야 「명목으로 산 것을 실질로 되판다」가 되지 않는다.

        ⚠ **단가가 0인 부품은 재취득하지 않는다.** `HeatPump` 와 같이 `unit_cost > 0.0`
        가드를 적용해 0원 교체행을 만들지 않는다. 0원 행을 프로포마에 내면 단가가 0일 뿐인데도
        「교체가 있었다」로 표시되는 결함이 되기 때문이다. 종전에는 PCS 갈래만 우연히 그 조건
        (`initial is None and unit_cost <= 0.0`)에 걸러졌고 배터리 갈래는 단가 0이어도
        `{16: 0원}` 교체행을 내었다 (실측 결과는 3절 기록 참고).
        """
        if self.retires_at_end_of_life():
            # 다시 사지 않으므로 취득분은 **최초 본체 하나**다. PCS 를 여기 두면
            # `replacement_schedule()` 이 비어 있는데 잔존가치만 생긴다.
            return ((self.lifetime, {1: float(self.capex(year=1))}),)

        parts: list[tuple[int, dict[int, float]]] = []
        for life, unit_cost, initial in (
            # 배터리 — 최초 취득(1년차)은 `_gross_capex_won()`(부대비·PCS 포함)이고
            # 재취득분은 배터리 교체 단가만 쓴다(부대비는 재취득하지 않는다).
            (self.lifetime, float(self._battery_cost()), float(self.capex(year=1))),
            # PCS — 최초 취득분을 두지 않는다(위 ⚠ 참조).
            (self._pcs_lifetime, self._pcs_cost, None),
        ):
            if life is None:
                continue
            acquired: dict[int, float] = {} if initial is None else {1: initial}
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

    def _first_eol_year(self) -> int:
        """본체·PCS 중 **먼저** 수명이 끝나는 해 (`retire` 의 의미 ⑤).

        `retire` 는 「이 설비 계통을 더는 갱신하지 않는다」이므로, PCS 없는
        배터리(또는 배터리 없는 PCS)를 계통에 실을 수 없다 — 둘 중 짧은 쪽이
        전체 출력을 멈추는 기준이다.
        """
        if self._pcs_lifetime is None:
            return self.lifetime
        return min(self.lifetime, self._pcs_lifetime)

    def replacement_schedule(self, *, horizon: int) -> dict[int, Money]:
        """`RC-ALL-C4` — 수명 도달 **다음 연도 초**에 계상. 배터리와 PCS 수명은
        **독립**이다 (FR-104-AC4) — 본체 수명만 보면 PCS 교체비가 통째로 빠진다.
        같은 해에 겹치면 합산한다.

        **`retire` 면 아무것도 사지 않는다** (FR-104-AC3) — 본체도 PCS도.
        그 갈래를 **여기 다시 적지 않는다** — `_acquisitions()` 가 `retire` 에서
        1년차 하나만 내고 그것은 아래에서 걸러지므로 이 함수는 저절로 빈다.
        같은 조건을 두 곳에 적으면 한쪽만 고쳐진다.

        ⚠ **이 스케줄은 `_acquisitions()` 에서 파생된다** (R42). 종전에는 PCS 항을
        여기서 따로 굴렸고, 그래서 **교체비는 계상되는데 그 잔존가치는 없는**
        비대칭이 조용히 생겼다(R40 ②). 두 곳이 같은 `(수명, 단가)` 짝을 돌게
        두는 것보다, **한 곳이 내고 다른 곳이 읽는** 편이 그 어긋남을 구조적으로
        막는다 — `tests/casegrid/test_lifecycle_wiring.py` ⓒ 가 대조하는 두 경로가
        이제 **같은 출처**를 본다.

        ⚠ **두 항 다 물가 계수를 굴린다** (R40 · `DV-7`) — 한쪽만 굴리면 같은
        해의 지출 두 개가 **서로 다른 가격 기준**으로 한 칸에 합산되고, 그
        합계는 어느 기준으로도 읽을 수 없다. 그리고 ⓓ 래칫(스케줄 전체를
        견준다)은 **한쪽만 반응해도 통과하므로** 그 어긋남을 잡지 못한다 —
        그래서 PCS 를 준 자원을 그 래칫의 탐침에 함께 세웠다.
        """
        schedule: dict[int, Money] = {}
        for _life, acquired in self._acquisitions(horizon=horizon):
            for year, cost in acquired.items():
                # 1년차 최초 취득은 CAPEX 이지 교체비가 아니므로 제외한다
                if year == 1:
                    continue
                # 같은 해에 배터리와 PCS 가 겹치면 더한다 — 덮어쓰면 한쪽이
                # 조용히 사라진다
                schedule[year] = Money(schedule.get(year, to_won(0)) + to_won(cost))
        return schedule

    def salvage_value(self, *, year: int) -> Money:
        """`RC-ALL-C5` — `취득가 × 잔존수명 / 총수명`. `year` 년에 분석이 끝난다고
        볼 때의 값이며 **할인은 하지 않는다** — 할인은 CBA 계층(WP-7)의 몫이고,
        여기서 함께 하면 두 번 할인되어 "보수적으로 보여서" 검출되지 않는다.

        **부품마다 마지막 취득 시점부터 센다** (R42) — 근거는 `_acquisitions()`
        독스트링. PCS 는 배터리와 수명이 다르므로 각자의 수명으로 재야 하고,
        접어서 하나로 보면 15년차에 새로 산 PCS 의 잔존수명을 **배터리 수명**으로
        재게 된다. `PV.salvage_value()` 와 같은 셈이다.
        """
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

    # ── 디스패치 (FR-301) ──────────────────────────────────────────

    def value_streams(self) -> tuple[str, ...]:
        """ESS 가 만드는 편익 (`FR-401-AC2.<키>`) — **운전 방법이 정한다**
        (판정 §4 산정식 표).

        백업 예비 확보의 정전 회피 편익(`Resilience`)은 Phase 3이므로 선언하지
        않는다 — 값 0인 행은 「편익 없음」과 「미구현」을 구분하지 못한다.
        혼합 모드는 가중치 0보다 큰 **모든** 모드의 편익을 갖는다. 대표 모드만
        보면 30% 섞인 피크 저감 편익이 통째로 사라진다.

        ⚠⚠ **`TOU_ARBITRAGE` 는 `TouArbitrage` 를 낸다 (R50 · 비어 있던 자리를
        채웠다).** 종전에는 이 모드가 `SelfConsumption` 을 냈는데, **계통에 파는
        운전인데 자가소비 편익이 붙는** 오매핑이었다(판정 §4 ⚠⚠). R48 이 그
        오매핑을 떼면서 **자리를 비워 두었고**, 그동안 이 메서드는 그 모드에서
        빈 튜플을 돌려주었으며 `tou_arbitrage_benefit()`(`RC-ESS-B1`)은
        **호출자가 단위시험 하나뿐**이었다. R50 이 `FR-401-AC2.TouArbitrage`
        (`core/valuestream/tou_arbitrage.py`)를 세워 그 자리를 채운다 —
        **같은 산식이며 시험이 두 값을 대조한다.**

        ⚠ **`TouArbitrage` 는 `SelfConsumption`·`PeakShaving` 과 배타가 아니다.**
        셋 다 운전 주체가 사업자이고 이 메서드가 이미 혼합 모드를 그렇게 다룬다 —
        `NWAs`·`CP` 와의 유형 `E` 배타가 갈라내는 축은 **방전 시점을 누가
        정하는가**이며 그 축에서 셋은 같은 쪽이다 (`docs/exclusion-rules.yaml`
        「R48 신설 — 운전 주체 축」).

        ⚠ **`GRID_DISCHARGE` → `NWAs` · `SEMI_CENTRAL_DISPATCH` → `CP` (R51/WP-3
        · 예언대로 표에 한 줄씩만 붙었다).** 이 둘은 방전 시점을 **계통운영자가**
        정하는 쪽이라 위 셋(사업자 운전)과 유형 `E` 로 갈린다 — 혼합 모드로
        함께 켜면 이 메서드는 두 태그를 **함께** 낸다. 그것이 결함이 아니라
        옳은 동작이다(판정 §3 · 「고를 수 있다」 ≠ 「동시에 성립한다」).

        ✔ **R52/WP-3 이 이 갈림을 닫았다.** R51/WP-3~WP-7 은 이 자리에
        *「배타는 실행 경로(`assert_no_exclusions`/`build_report`)가 건다」*
        고 적었는데 실측은 **둘 다 유형 `E` 를 걸지 않는 것**이었다 — 「계통
        방전」을 골라 `NWAs` 단가를 준 실행이 거부 없이 서고 `NWAs` 와 사업자
        운전 편익이 함께 계상됐다. 사용자 판정 §3 앞 문장(*「배터리는 한 번에
        하나의 역할만 수행하는 것으로 설계해야 함」*, `docs/decisions-2026-09-
        02-R52.md` §3)이 그 갈림을 「거부한다」로 풀었다 — `assert_no_
        exclusions()` 가 이제 유형 `A` 와 함께 `E` 도 거부한다(DV-12). 이
        메서드가 혼합 모드에서 두 태그를 **함께 내는 것 자체는 여전히 옳다**
        (「고를 수 있다」 ≠ 「동시에 성립한다」) — 그 조합이 실행 경로에서
        거부되는 것이 배타 규칙의 일이지, 이 메서드가 태그를 감추는 것이
        아니다.

        ⚠ **R54/WP-1 뒤에는 위 문단이 반쪽만 참이다.** 위 거부가 늘 일어난
        것은 사실 `e2e_runner.py` 가 **운전 방법과 무관하게 항상**
        `PeakShaving` 을 만들었기 때문이었다 — 「계통 방전」·「준중앙급전
        등록」단독 선택에서도 단가 0원인 `PeakShaving` 이 함께 서서 유형 `E`
        로 매번 거부됐다. 사용자 판정 §1(`docs/decisions-2026-09-02-R54.md`
        §1)은 「한 번에 하나」를 *둘이 있으면 막는다*가 아니라 *한 가지만
        한다*로 풀었다 — R54/WP-1 이 `grid_support.py::peak_shaving_enabled()`
        술어를 세워 방식 「나」(`GRID_DISCHARGE`·`SEMI_CENTRAL_DISPATCH`)
        단독일 때는 `PeakShaving` 을 **애초에 만들지 않는다**(`HYBRID` 는
        켠 채 둔다). `assert_no_exclusions()` 의 유형 `E` 거부 규칙 자체는
        지워지지 않았다 — 다만 이제는 이 메서드가 혼합 모드에서 두 태그를
        **함께 냈을 때만**(즉 조합이 실제로 조립됐을 때만) 발동한다. 방식
        「나」를 단독으로 고르면 애초에 거부할 쌍이 서지 않는다.
        """
        # ⚠ **`if` 갈래 대신 표로 둔다.** 갈래로 짜면 편익이 늘 때마다 이 메서드가
        # 자라고, 이 파일은 이미 `NFR-206` 코드 줄 수 상한(500)에 **정확히 걸려
        # 있었다** — R50 이 편익 한 종을 더하며 그 상한을 실제로 넘겼고, 표로
        # 바꿔 되돌렸다. **다음에 한 종이 더 늘면 표에 한 줄만 붙는다.**
        active = {m for m, w in self.mode_weights.items() if w > 0.0}
        by_mode = {
            ESSOperatingMode.SELF_CONSUMPTION: "SelfConsumption",
            ESSOperatingMode.TOU_ARBITRAGE: "TouArbitrage",
            ESSOperatingMode.PEAK_SHAVING: "PeakShaving",
            ESSOperatingMode.GRID_DISCHARGE: "NWAs",
            ESSOperatingMode.SEMI_CENTRAL_DISPATCH: "CP",
        }
        return tuple(tag for mode, tag in by_mode.items() if mode in active)

    def dispatch(self, ctx: DispatchContext) -> DispatchResult:
        """하루 1주기 충·방전 프로파일을 스텝별로 전개한다.

        부호 규약: **양수 = 방전, 음수 = 충전**. 열·냉·연료는 0으로 남긴다 —
        플래그가 거짓인 매체의 값은 사라진다 (FR-101-AC4).

        **부분 창은 연초부터의 연속 구간이다.** 하루치 에너지를 시각별로 펼치고
        창 길이만큼 잘라 내므로, 24스텝은 48스텝의 앞 24스텝과 정확히 같다 —
        하루 에너지를 창 길이에 재배분하면 그 성질이 깨진다.

        **`retire` 면 첫 수명종료 다음 해부터 출력이 0이다** (FR-104-AC3).
        교체비를 끊고 편익은 그대로 두면 회수기간이 실제보다 좋아지므로, 두
        쪽을 함께 끊는다 — 배터리에는 «채우지 못한 수요»가 없으므로
        `unmet_*` 는 건드리지 않는다(기본값 0이 그대로 남는다).

        **`PV_SURPLUS` 는 충전창이 고정이 아니다** (판정 A-8-a). 방전은 두 충전원
        모두 방전창에 균등 배분하지만(종전 그대로), 충전은 `GRID` 만 고정창을
        쓰고 `PV_SURPLUS` 는 시각별 실충전량(`_pv_surplus_charge_kwh_by_hour`)을
        그대로 싣는다 — 시각마다 다른 값이라 균등 배분할 수 없다.
        """
        self.check_context(ctx)
        if self.retires_at_end_of_life() and int(ctx.year) > self._first_eol_year():
            zeros = [0.0] * ctx.steps
            return DispatchResult(electric=zeros, heat=zeros, cool=list(zeros), fuel=list(zeros))

        steps_per_hour = SECONDS_PER_HOUR // ctx.dt
        hours_per_step = ctx.dt / SECONDS_PER_HOUR
        year = int(ctx.year)
        discharge_window = len(self.discharge_hours) * steps_per_hour
        out_step = self.annual_discharge_kwh(year=year) / DAYS_PER_YEAR / discharge_window
        self._check_power(out_step, hours_per_step, "방전")

        electric = [0.0] * ctx.steps
        if self.charge_source is ESSChargeSource.PV_SURPLUS:
            charged_by_hour = self._pv_surplus_charge_kwh_by_hour(year=year)
            for i in range(ctx.steps):
                hour = (i // steps_per_hour) % HOURS_PER_DAY
                if hour in self.discharge_hours:
                    electric[i] = out_step
                elif hour in charged_by_hour:
                    electric[i] = -(charged_by_hour[hour] / steps_per_hour)
        else:
            charge_window = len(self.charge_hours) * steps_per_hour
            in_step = self.annual_charge_kwh(year=year) / DAYS_PER_YEAR / charge_window
            self._check_power(in_step, hours_per_step, "충전")
            for i in range(ctx.steps):
                hour = (i // steps_per_hour) % HOURS_PER_DAY
                if hour in self.discharge_hours:
                    electric[i] = out_step
                elif hour in self.charge_hours:
                    electric[i] = -in_step

        self._check_grid_limit(electric, ctx, hours_per_step)
        zeros = [0.0] * ctx.steps
        return DispatchResult(electric=electric, heat=zeros, cool=list(zeros), fuel=list(zeros))

    def _check_power(self, step_kwh: float, hours_per_step: float, label: str) -> None:
        """정격출력 초과를 **거부**한다. 잘라내면 없는 출력으로 편익이 난다."""
        kw = step_kwh / hours_per_step
        if kw > self.power_kw + _KW_TOLERANCE:
            raise ValidationError(
                field="ess.power_kw",
                reason=f"{self.name}: {label} {kw:.6g}kW 가 정격출력 {self.power_kw:.6g}kW 초과",
                action="정격출력(power_kw)을 키우거나 운전창(운전 방법)을 조정해 계획이 "
                "정격출력 이내가 되도록 하십시오 — 자동으로 잘라내면 그만큼의 편익이 "
                "조용히 사라집니다",
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
                raise ValidationError(
                    field="ess.power_kw",
                    reason=f"{self.name}: {i} 계통 연계 초과 {kw:.6g}/{ctx.grid_limit_kw[i]:.6g}kW",
                    action="정격출력(power_kw)이나 용량(capacity_kwh)을 낮추거나, 시나리오의 "
                    "계통 연계 한도(grid_limit_kw)를 이 자원의 계획에 맞게 올리십시오",
                )


# ── 입력 검증 도우미 ────────────────────────────────────────────────
# 오류 메시지에 **자원 이름과 받은 값**을 반드시 넣는다 — 자원 수십 개짜리
# 시나리오에서 «값이 범위 밖»만 나오면 어느 자원인지 찾지 못한다.


def _positive(value: float, *, field: str, label: str, name: str) -> float:
    if not value > 0:
        raise ValidationError(
            field=field,
            reason=f"{name}: {label}은 0보다 커야 합니다 (받은 값 {value})",
            action=f"{label}에 0보다 큰 값을 지정하십시오",
        )
    return float(value)


def _in_range(
    value: float, low: float, high: float, *, field: str, label: str, name: str,
    rule: str | None = None, low_exclusive: bool = False, high_exclusive: bool = False,
) -> float:
    """닫힌 구간이 기본이다 — `low_exclusive`·`high_exclusive` 로 경계를 배타로
    바꾼다 (R51/WP-3 · `rte_pct`·`backup_reserve_pct`·`eol_soh` 흡수).

    ⚠ **경계가 하나라도 배타면 문면이 「N 초과/이상 M 이하/미만」으로 바뀐다** —
    닫힌 구간의 `{low}~{high} 범위` 문면(기존 호출자 전부)은 그대로 둔다. 값을
    두 번 쓰지 않으려고 여기서 만들지만, 어느 쪽이든 개폐를 **말로** 남긴다.
    """
    ok = (low < value if low_exclusive else low <= value) and (
        value < high if high_exclusive else value <= high
    )
    if ok:
        return float(value)
    if low_exclusive or high_exclusive:
        lo, hi = ("초과" if low_exclusive else "이상"), ("미만" if high_exclusive else "이하")
        desc = f"{low:g} {lo} {high:g} {hi}"
    else:
        desc = f"{low}~{high} 범위"
    raise ValidationError(
        field=field, reason=f"{name}: {label}은 {desc}입니다 (받은 값 {value})",
        action=f"{label}을(를) {desc}(으)로 지정하십시오", rule=rule,
    )
