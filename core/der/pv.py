"""`PV` 태양광 — WP-1a / spec FR-102-AC1.PV · FR-104 · FR-105.

`core.contracts` **만** import한다 (FR-101-AC3 · NFR-208-AC1). 자원이 엔진을
알면 «신규 자원 추가 시 코어 수정 없음»(NFR-201)이 성립하지 않는다.

검증 케이스는 `tests/der/test_pv.py` — §13.2.2 `RC-ALL-C1~C5`, §13.2.3
`RC-PV-P1~P3 · B1~B3 · X1`. 산식을 고칠 때는 그 오라클이 왜 바뀌어야 하는지를
먼저 말할 수 있어야 한다.

**금액은 전부 `Money`(정수 원)로 나간다** (NFR-103). 반올림은 `to_won()` 한
곳에서만 일어난다 — `round()`·`int()` 를 직접 쓰면 사사오입 규칙이 갈리고,
엑셀 대조군(§13.3)과 개별 셀이 1원씩 어긋나 원인 추적이 불가능해진다.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import ClassVar

from core.contracts.der import DER, EOL_REPLACE, DispatchContext, DispatchResult
from core.contracts.units import (
    HOURS_PER_YEAR,
    SECONDS_PER_HOUR,
    Money,
    steps_per_year,
    to_won,
)
from core.contracts.validation import ValidationError

#: 인버터 교체비 기본값 — 초기 설비비 대비 비율. 통상 10~20% 구간의 중앙을 쓴다.
#: **기본값이지 오라클이 아니다** — 견적이 있으면 `inverter_unit_capex_won_per_kw` 로 준다.
#:
#: ⚠ **결론을 내는 경로는 이 상수를 읽지 않는다** (R43). 정본은 대장의
#: `capex.pv.inverter_share`(`Q-18`)이고, `core/casegrid/e2e_runner.py` 가
#: 그 값으로 단가를 지어 위 인자로 넘긴다 — 그래야 5.1 영향도 표에 서고
#: *「0.15 를 골랐다」가 결론에 얼마를 넣었는지* 가 재어진다. 여기 남긴 것은
#: **자원을 단독으로 세울 때의 기본값**이며, 지우면 인자를 생략한 호출이
#: 인버터 교체를 통째로 잃는다(0원이 되어 아무 예외도 나지 않는다).
DEFAULT_INVERTER_CAPEX_RATIO = 0.15

#: kWh → MWh (REC 정산 단위). 1000을 산식에 흩어 두면 단위 환산인지 계수인지 모른다.
KWH_PER_MWH = 1000.0


class OperatingMode(StrEnum):
    """PV가 지원하는 운전 방법 (FR-105-AC1).

    **운전 방법은 자원 클래스에 함께 정의한다** (FR-105-AC2) — 엔진 쪽에 두면 운전
    방법 하나를 늘릴 때마다 코어를 고쳐야 한다. PV는 비제어 자원이라 발전량 자체는
    운전 방법과 무관하므로, 여기서 정하는 것은 **① 발전량의 용도 배분**(자가소비/
    판매)과 **② 계통 상한 초과 시의 처리**다. 둘 중 어느 것도 바꾸지 않는 운전
    방법은 결과에 영향이 없는 선언으로 남는다.
    """

    #: 자가소비율만큼 부하에 먼저 쓰고 나머지를 잉여로 둔다
    SELF_CONSUMPTION_FIRST = "자가소비 우선"
    #: 자가소비를 하지 않는다 (발전사업용)
    FULL_EXPORT = "전량 판매"
    #: 계통 연계 상한을 넘는 발전을 버린다
    CURTAILMENT = "출력제어 수용"


class PV(DER):
    """태양광 발전 자원 (옥상·벽면 BIPV 공통).

    FR-102-AC1.PV 입력: 용량(kW), 이용률(%) **또는** 8760 발전 시계열,
    방위·경사, 연간 열화율, 인버터 수명.

    **비용 파라미터의 기본값이 0인 이유.** §13.2.1 「단독성」은 검증 케이스가 대상
    효과만 켜고 나머지를 전부 끌 것을 요구한다. 물리 케이스(`RC-PV-P1`)를 돌리려고
    비용 6종을 다 채워야 하면 그 값들이 물리 결과에 영향을 주지 않는다는 사실을
    매번 다시 확인해야 한다. 0은 «미지정»이 아니라 «이 케이스에서 계상하지 않음»
    이며, 실제 시나리오의 비용 누락 방어는 입력 검증 계층(FR-901·FR-1002)의 몫이다.
    """

    tag = "PV"

    #: FR-105-AC1 — 자원 클래스가 자신이 지원하는 운전 방법 목록을 선언한다
    OPERATING_MODES: ClassVar[tuple[OperatingMode, ...]] = tuple(OperatingMode)

    def __init__(
        self,
        *,
        name: str,
        capacity_kw: float,
        capacity_factor: float | None = None,
        generation_profile_kwh: Sequence[float] | None = None,
        azimuth_deg: float = 180.0,
        tilt_deg: float = 30.0,
        degradation_rate: float = 0.005,
        lifetime: int = 25,
        inverter_lifetime: int = 12,
        unit_capex_won_per_kw: float = 0.0,
        bos_capex_won: float = 0.0,
        vat_rate: float = 0.0,
        inverter_unit_capex_won_per_kw: float | None = None,
        fixed_om_won_per_year: float = 0.0,
        variable_om_won_per_kwh: float = 0.0,
        escalation_rate: float = 0.0,
        replacement_escalation_rate: float | None = None,
        self_consumption_ratio: float = 1.0,
        operating_mode: OperatingMode | str = OperatingMode.SELF_CONSUMPTION_FIRST,
        end_of_life_action: str = EOL_REPLACE,
        dt: int = SECONDS_PER_HOUR,
    ) -> None:
        # 이름·수명·열화율·매체 플래그·운전 방법·물가상승률 검증은 계약이 이미
        # 한다. 여기서 다시 검사하면 같은 규칙이 두 곳에 생기고, 언젠가 한쪽만
        # 고쳐진다.
        super().__init__(
            name=name,
            dt=dt,
            lifetime=lifetime,
            degradation_rate=float(degradation_rate),
            carries_electric=True,   # PV는 전기만 낸다 (FR-101-AC4)
            carries_heat=False,
            carries_cool=False,
            consumes_fuel=False,
            operating_mode=self._coerce_mode(mode=operating_mode, name=name),
            escalation_rate=escalation_rate,
            replacement_escalation_rate=replacement_escalation_rate,
            end_of_life_action=end_of_life_action,
        )

        self.capacity_kw = _positive(
            capacity_kw, field="pv.capacity_kw", label="용량(kW)", name=name
        )
        self.capacity_factor, self.generation_profile_kwh = self._resolve_generation(
            capacity_factor=capacity_factor, profile=generation_profile_kwh, name=name
        )
        self.azimuth_deg = _in_range(
            azimuth_deg, 0.0, 360.0, field="pv.azimuth_deg", label="방위각(도)", name=name
        )
        self.tilt_deg = _in_range(
            tilt_deg, 0.0, 90.0, field="pv.tilt_deg", label="경사각(도)", name=name
        )
        self.inverter_lifetime = int(
            _positive(
                inverter_lifetime, field="pv.inverter_lifetime", label="인버터 수명", name=name
            )
        )
        self.unit_capex_won_per_kw = _non_negative(
            unit_capex_won_per_kw,
            field="pv.unit_capex_won_per_kw",
            label="설비 단가(원/kW)",
            name=name,
        )
        self.bos_capex_won = _non_negative(
            bos_capex_won, field="pv.bos_capex_won", label="부가세 제외 부대비(원)", name=name
        )
        self.vat_rate = _in_range(
            vat_rate, 0.0, 1.0, field="pv.vat_rate", label="부가세율", name=name
        )
        self.inverter_unit_capex_won_per_kw = _non_negative(
            self.unit_capex_won_per_kw * DEFAULT_INVERTER_CAPEX_RATIO
            if inverter_unit_capex_won_per_kw is None
            else inverter_unit_capex_won_per_kw,
            field="pv.inverter_unit_capex_won_per_kw",
            label="인버터 단가(원/kW)",
            name=name,
        )
        self.fixed_om_won_per_year = _non_negative(
            fixed_om_won_per_year,
            field="pv.fixed_om_won_per_year",
            label="고정 O&M(원/년)",
            name=name,
        )
        self.variable_om_won_per_kwh = _non_negative(
            variable_om_won_per_kwh,
            field="pv.variable_om_won_per_kwh",
            label="변동 O&M 단가(원/kWh)",
            name=name,
        )
        self.self_consumption_ratio = _in_range(
            self_consumption_ratio, 0.0, 1.0, field="pv.self_consumption_ratio",
            label="자가소비율", name=name
        )

    # ── 입력 해석 ───────────────────────────────────────────────────

    @classmethod
    def _coerce_mode(cls, *, mode: OperatingMode | str, name: str) -> OperatingMode:
        """문자열을 열거 멤버로 승격시킨다 — **목록 소속 검사는 계약이 한다.**

        문자열을 받는 이유는 운전 방법이 케이스 그리드의 탐색 변수이고
        (FR-105-AC5) 그 값이 YAML·DB를 거쳐 문자열로 들어오기 때문이다. 승격하지
        않으면 `operating_mode is OperatingMode.CURTAILMENT` 가 조용히 거짓이 되어
        출력제어 수용이 무시된다 — 계약은 `str` 소속만 본다 (DV-14).
        """
        try:
            return OperatingMode(mode)
        except ValueError as e:
            allowed = ", ".join(m.value for m in cls.OPERATING_MODES)
            raise ValidationError(
                field="pv.operating_mode",
                reason=f"{name}: 선언되지 않은 운전 방법입니다: {mode!r}",
                action=f"PV가 지원하는 운전 방법 중 하나를 지정하십시오 — [{allowed}]",
                rule="DV-14",
            ) from e

    def _resolve_generation(
        self, *, capacity_factor: float | None, profile: Sequence[float] | None, name: str
    ) -> tuple[float | None, tuple[float, ...] | None]:
        """이용률과 8760 시계열 중 **정확히 하나**를 고른다 (FR-102-AC1.PV).

        둘 다 주면 어느 쪽이 이겼는지 입력만 보고 알 수 없다. 둘 다 없으면
        발전량 0인 PV가 조용히 만들어지고, 비용만 있는 사업이 된다.
        """
        if (capacity_factor is None) == (profile is None):
            both = "둘 다 주었습니다" if capacity_factor is not None else "둘 다 주지 않았습니다"
            raise ValidationError(
                field="pv.capacity_factor",
                reason=(
                    f"{name}: 이용률(capacity_factor)과 8760 발전 시계열을 {both}"
                    f" (받은 값 — 이용률 {capacity_factor!r}, 시계열 "
                    f"{'없음' if profile is None else f'{len(profile)}행'})"
                ),
                action=(
                    "이용률(capacity_factor) 또는 발전 시계열(generation_profile_kwh) "
                    "중 정확히 하나만 지정하십시오"
                ),
            )

        if capacity_factor is not None:
            return (
                _in_range(
                    capacity_factor, 0.0, 1.0, field="pv.capacity_factor", label="이용률", name=name
                ),
                None,
            )

        assert profile is not None  # 위 분기가 보장한다 (타입 좁히기)
        expected = steps_per_year(self.dt)
        if len(profile) != expected:
            raise ValidationError(
                field="pv.generation_profile_kwh",
                reason=(
                    f"{name}: 발전 시계열 행수가 맞지 않습니다: {len(profile)}행, "
                    f"기대 {expected}행"
                ),
                action=(
                    f"발전 시계열을 정확히 {expected}행으로 맞춰 지정하십시오 "
                    f"(dt={self.dt}초 기준)"
                ),
                rule="DV-4",
            )
        for i, v in enumerate(profile):
            if v < 0.0:
                raise ValidationError(
                    field="pv.generation_profile_kwh",
                    reason=f"{name}: 발전 시계열 {i}번째 스텝이 음수입니다: {v}",
                    action=(
                        "발전 시계열의 모든 값을 0 이상으로 지정하십시오 — 부호 규약상 음수는 "
                        "«계통에서 받아들임(소비)»을 의미합니다"
                    ),
                )
        return None, tuple(float(v) for v in profile)

    # ── 물리 (RC-PV-P1~P3) ──────────────────────────────────────────

    def derate(self, *, year: int) -> float:
        """`year` 년차 성능 잔존율 = `(1 − 열화율)^(year−1)` (FR-104-AC1).

        지수가 `year`가 아니라 `year−1`인 이유: 1년차는 준공 첫 해라 아직 열화가
        걸리지 않았다. 0-base로 쓰면 20년 누계가 한 해분 적게 나오는데, 값이
        그럴듯해서 눈으로는 잡히지 않는다.
        """
        return (1.0 - self.degradation_rate) ** (int(year) - 1)

    def _first_end_of_life_year(self) -> int:
        """본체·인버터 중 **먼저** 수명이 끝나는 해 — `retire` 출력 중단 기준
        (`FR-104-AC3`, `core/contracts/der.py` 「retire의 의미」⑤)."""
        return min(self.lifetime, self.inverter_lifetime)

    def annual_generation_kwh(self, *, year: int) -> float:
        """`year` 년차 연간 발전량 (kWh).

        오라클 `RC-PV-P1`: `용량 × 8760h × 이용률` — 1kW × 8760 × 0.15 = 1,314.0
        """
        if self.generation_profile_kwh is not None:
            base = sum(self.generation_profile_kwh)
        else:
            assert self.capacity_factor is not None  # 생성자가 보장한다
            base = self.capacity_kw * HOURS_PER_YEAR * self.capacity_factor
        return base * self.derate(year=year)

    def cumulative_generation_kwh(self, *, horizon: int) -> float:
        """분석기간 누계 발전량 (kWh) — 오라클 `RC-PV-P2` 25,068.4 kWh.

        폐형식 `1,314 × (1 − 0.995²⁰)/0.005` 대신 연도별 합으로 쓰는 이유는
        열화율 0일 때의 분모 0을 분기로 피하지 않기 위해서다 — 분기가 있으면
        그 분기만 검증에서 빠진다.
        """
        return sum(self.annual_generation_kwh(year=y) for y in range(1, horizon + 1))

    def _self_consumption_ratio_effective(self) -> float:
        """전량 판매는 자가소비율을 0으로 덮는다 (FR-105-AC1).

        입력값 자체를 지우지 않는 이유는 운전 방법을 되돌렸을 때 원래 값이
        살아나야 하기 때문이다 (FR-801이 운전 방법을 탐색 변수로 돌린다).
        """
        if self.operating_mode is OperatingMode.FULL_EXPORT:
            return 0.0
        return self.self_consumption_ratio

    def self_consumption_kwh(self, *, year: int) -> float:
        return self.annual_generation_kwh(year=year) * self._self_consumption_ratio_effective()

    def surplus_kwh(self, *, year: int) -> float:
        """잉여 = 총발전량 − 자가소비.

        총량에서 빼는 것은 **자가소비 + 잉여 = 총발전량** 항등식(§13.2.3
        `RC-PV-B2`)을 산식 자체로 보장하기 위해서다. `총량 × (1 − 비율)` 로
        따로 계산하면 두 식이 각각 반올림되어 항등식이 미세하게 깨지고, 깨진
        만큼의 kWh는 어느 편익에도 잡히지 않는다.

        ⚠ **여기서 나온 잉여를 가구 부하보다 ESS 충전이 먼저 가져간다** — 그
        우선순위의 정본 선언은 `e2e_runner._resolve_ess_dispatch_inputs`
        독스트링에 있다(사본을 두지 않는다).
        """
        return self.annual_generation_kwh(year=year) - self.self_consumption_kwh(year=year)

    def check_allocation(
        self, *, year: int, self_consumption_kwh: float, surplus_kwh: float
    ) -> None:
        """배분이 총발전량을 넘지 않는지 확인한다 — `RC-PV-X1` (FR-402-AC2.A).

        동일 kWh를 자가소비 절감과 잉여판매에 이중 계상하는 조합은 **실행
        거부**다(차단 100%). 중복 계상은 경제성을 실제보다 좋게 보이게 하여 필요
        지원 규모를 과소 산정하게 만든다.
        """
        if self_consumption_kwh < 0.0 or surplus_kwh < 0.0:
            raise ValueError(
                f"{self.name}: 배분량은 음수가 될 수 없습니다 "
                f"(자가소비 {self_consumption_kwh}, 잉여 {surplus_kwh})"
            )
        total = self.annual_generation_kwh(year=year)
        allocated = self_consumption_kwh + surplus_kwh
        # NFR-102 에너지 수지 허용 오차(1e-6 kWh)만큼은 float 누산 오차로 본다
        if allocated - total > 1e-6:
            raise ValidationError(
                field="pv.allocation",
                reason=(
                    f"{self.name}: 동일 발전량의 이중 계상입니다 — "
                    f"{year}년차 발전 {total:.6f} kWh 에 대해 자가소비 "
                    f"{self_consumption_kwh:.6f} + 잉여 {surplus_kwh:.6f} = "
                    f"{allocated:.6f} kWh 를 배분했습니다"
                ),
                action=(
                    "자가소비 배분량과 잉여판매 배분량의 합이 해당 연도 총발전량을 "
                    "넘지 않도록 편익 활성화 조합을 조정하십시오"
                ),
                rule="DV-12",
            )

    def value_streams(self) -> tuple[str, ...]:
        """편익 tag (`FR-401-AC2.<키>`) — **운전 방법과 자가소비율이 정한다.**

        3종을 늘 선언하면 전량 판매인데 자가소비 절감이, 자가소비율 100%인데
        판매 수익이 계상된다 (FR-402-AC2.A 동일 물리량 이중 판매).
        """
        ratio = self._self_consumption_ratio_effective()
        return tuple(
            (["SelfConsumption"] if ratio > 0.0 else [])
            + (["SurplusSale"] if ratio < 1.0 else [])
            + ["REC"]        # REC는 발전량 기준이므로 용도 배분과 무관하다
        )

    def dispatch(self, ctx: DispatchContext) -> DispatchResult:
        """운전 — 전기 계열에만 값을 싣는다 (FR-101-AC4).

        스텝당 kWh = `발전 kW × 스텝 길이(h)`. 해상도가 바뀌어도 연간 합계가 같아야
        하므로 스텝 길이를 곱한다 — 빼먹으면 15분 해상도에서 발전량이 4배가 된다.

        `ctx.steps` 가 한 해보다 짧으면 **연초부터 그만큼**이다 (부분 창 규약) —
        시계열을 앞에서 자르는 것이 그 이행이다.

        **`retire` 면 첫 수명 종료(본체·인버터 중 먼저 끝나는 쪽) 다음 해부터
        전량 0이다** (`FR-104-AC3`). 인버터를 다시 사지 않으면서 발전은 계속
        나온다면 교체비만 사라지고 편익은 남아 필요 지원액이 과소 산정된다 —
        인버터 없는 PV 는 계통에 못 싣는다.
        """
        self.check_context(ctx)   # 해상도 불일치를 계약이 거부한다
        if self.retires_at_end_of_life() and int(ctx.year) > self._first_end_of_life_year():
            zeros = [0.0] * ctx.steps
            return DispatchResult(
                electric=list(zeros), heat=list(zeros), cool=list(zeros), fuel=list(zeros)
            )

        hours_per_step = ctx.hours_per_step
        derate = self.derate(year=int(ctx.year))

        if self.generation_profile_kwh is not None:
            if ctx.steps > len(self.generation_profile_kwh):
                raise ValueError(
                    f"{self.name}: 발전 시계열이 요청 스텝보다 짧습니다 — "
                    f"{len(self.generation_profile_kwh)}행, 요청 {ctx.steps}행 "
                    "(FR-301-AC3)"
                )
            electric = [v * derate for v in self.generation_profile_kwh[: ctx.steps]]
        else:
            assert self.capacity_factor is not None  # 생성자가 보장한다
            per_step = self.capacity_kw * self.capacity_factor * derate * hours_per_step
            electric = [per_step] * ctx.steps

        electric = self._apply_grid_limit(electric, ctx=ctx, hours_per_step=hours_per_step)

        return DispatchResult(
            electric=electric,
            heat=[0.0] * ctx.steps,
            cool=[0.0] * ctx.steps,
            fuel=[0.0] * ctx.steps,
        )

    def _apply_grid_limit(
        self, electric: list[float], *, ctx: DispatchContext, hours_per_step: float
    ) -> list[float]:
        """계통 연계 상한 처리 — 운전 방법에 따라 **깎거나 거부한다**.

        초과분을 조용히 깎으면 «출력제어 수용»과 «미수용»이 같은 결과를 내어
        FR-105 선택이 결과에 영향을 주지 못한다. 깎지 않고 통과시키면 계통에
        실릴 수 없는 kWh가 편익이 된다. 어느 쪽도 화면에 표시가 남지 않는다.
        """
        if ctx.grid_limit_kw is None:
            return electric

        limits = [lim * hours_per_step for lim in ctx.grid_limit_kw]
        if self.operating_mode is OperatingMode.CURTAILMENT:
            return [min(gen, lim) for gen, lim in zip(electric, limits, strict=True)]

        for step, (gen, lim) in enumerate(zip(electric, limits, strict=True)):
            if gen - lim > 1e-9:
                raise ValidationError(
                    field="pv.operating_mode",
                    reason=(
                        f"{self.name}: {step}번째 스텝 발전 {gen:.6f} kWh 가 계통 "
                        f"연계 용량 상한 {lim:.6f} kWh 를 넘습니다"
                    ),
                    action=(
                        f"운전 방법을 «{OperatingMode.CURTAILMENT.value}» 로 지정해 출력제어를 "
                        "수용하거나, 용량(capacity_kw)을 계통 한도 이하로 낮추십시오"
                    ),
                )
        return electric

    # ── 편익 (RC-PV-B1~B3) ──────────────────────────────────────────

    def self_consumption_benefit(self, *, year: int, avoided_tariff_won_per_kwh: float) -> Money:
        """`RC-PV-B1` 자가소비 절감 = `자가소비 kWh × 회피 요금단가`.

        회피 단가를 인자로 받는 이유: 실제 단가는 누진·TOU 구조에서 나오며
        (FR-401-AC2.SelfConsumption) 그 계산은 요금 엔진의 몫이다. 자원이 요금
        구조를 알면 요금제 개정이 자원 코드 수정이 된다.
        """
        return to_won(self.self_consumption_kwh(year=year) * avoided_tariff_won_per_kwh)

    def surplus_sale_revenue(self, *, year: int, sale_price_won_per_kwh: float) -> Money:
        """`RC-PV-B2` 잉여 판매 = `잉여 kWh × 판매단가` (직거래/상계/SMP)."""
        return to_won(self.surplus_kwh(year=year) * sale_price_won_per_kwh)

    def rec_revenue(self, *, year: int, rec_price_won_per_mwh: float, rec_weight: float) -> Money:
        """`RC-PV-B3` REC 수익 = `발전 MWh × 가중치 × REC 단가`.

        가중치는 설치 유형(건물·수상·영농형)과 제도에 종속되므로 규제
        프로파일(FR-504)에서 온다. 자원이 들고 있으면 제도 개정 때 자원
        코드를 고치게 된다.
        """
        if rec_weight < 0.0:
            raise ValidationError(
                field="pv.rec_weight",
                reason=f"{self.name}: REC 가중치는 음수가 될 수 없습니다 (받은 값 {rec_weight})",
                action="REC 가중치를 0 이상의 값으로 지정하십시오",
            )
        if rec_price_won_per_mwh < 0.0:
            raise ValidationError(
                field="pv.rec_price_won_per_mwh",
                reason=(
                    f"{self.name}: REC 단가는 음수가 될 수 없습니다 "
                    f"(받은 값 {rec_price_won_per_mwh})"
                ),
                action="REC 단가(원/MWh)를 0 이상의 값으로 지정하십시오",
            )
        mwh = self.annual_generation_kwh(year=year) / KWH_PER_MWH
        return to_won(mwh * rec_weight * rec_price_won_per_mwh)

    # ── 비용 5종 (RC-ALL-C1~C5) ─────────────────────────────────────

    def _gross_capex_won(self) -> float:
        """CAPEX 본체 = `단가 × 용량 + 부대비` (§13.2.2 C-1). 부가세는 제외."""
        return self.capacity_kw * self.unit_capex_won_per_kw + self.bos_capex_won

    # 물가 계수는 계약의 `escalation_factor(year=...)` 다 (v1.1 개정 ⑤) — 자원이
    # 각자 지수를 쓰면 기준연도가 갈려 한 해씩 어긋난 비용이 나온다.
    #
    # ⚠ **`escalation_rate` 슬롯은 자원당 하나다** — 비용 항목별로 나뉘어 있지
    # 않다. 그래서 이 인자로 들어오는 값 하나가 `fixed_om()`(아래)·
    # `variable_om()`·`replacement_schedule()` **셋**을 함께 굴린다. 호출자가
    # 「O&M 물가만」과 「교체비 물가」를 다른 값으로 두고 싶어도 이 클래스는 그
    # 구분을 갖지 않는다 — 다른 값이 필요하면 계약을 바꿔야 한다(지금은 바꾸지
    # 않았다). 운영 배선(`core/casegrid/e2e_runner.py`)에서 이 인자에 실제로
    # 무엇을 넘기는지, 그리고 다른 자원(`ESS`)이 이 인자를 받는지는 이 파일이
    # 모른다 — `tests/contract/test_escalation_debt.py` 가 그 사실을 붙든다
    # (R38-D2).

    def capex(self, *, year: int) -> Money:
        """`RC-ALL-C1` CAPEX — 1년차에만 계상. 오라클 1,500,000 × 3 = 4,500,000원.

        이후 연도에 다시 계상하면 20년 동안 25번 지은 사업이 된다 (§13.2.2).
        """
        return to_won(self._gross_capex_won()) if int(year) == 1 else Money(0)

    def capex_vat(self, *, year: int) -> Money:
        """CAPEX 부가세 — **본체와 분리된 항목** (§13.2.2 C-1).

        본체에 섞으면 프로포마에서 세액을 따로 표시할 수 없고, 환급·면세
        시나리오에서 본체 단가를 역산해야 한다.
        """
        return to_won(self._gross_capex_won() * self.vat_rate) if int(year) == 1 else Money(0)

    def fixed_om(self, *, year: int) -> Money:
        """`RC-ALL-C2` 고정 O&M — 설비 보유에 비례하며 발전량과 무관하다."""
        return to_won(self.fixed_om_won_per_year * self.escalation_factor(year=year))

    def fixed_om_cumulative(self, *, horizon: int) -> Money:
        """`RC-ALL-C2` 고정 O&M 분석기간 누계 — 등비수열 합.

        오라클(§13.2.2): `A × ((1+i)^n − 1) / i`, A=100,000 i=0.02 n=20
        → 2,429,737원. 폐형식과 연도별 합이 **원 단위까지 일치**해야 한다
        (NFR-103-M1) — 갈리면 프로포마 총계와 행별 합이 어긋나고, 그 어긋남은
        화면상 정상으로 보인다. 테스트가 두 경로를 대조한다.
        """
        if horizon <= 0:
            raise ValidationError(
                field="pv.horizon",
                reason=f"{self.name}: 분석기간은 1년 이상입니다: {horizon}",
                action="분석기간(horizon)에 1 이상의 정수를 지정하십시오",
            )
        i = self.escalation_rate
        if i == 0.0:
            total = self.fixed_om_won_per_year * horizon
        else:
            total = self.fixed_om_won_per_year * ((1.0 + i) ** horizon - 1.0) / i
        return to_won(total)

    def variable_om(self, *, year: int) -> Money:
        """`RC-ALL-C3` 변동 O&M = `처리량 × 단가`. PV의 처리량은 **발전 kWh**.

        오라클(§13.2.2): 발전 1,314 kWh × 5원 = 6,570원/년. 열화된 발전량을 쓴다 —
        1년차 값으로 20년을 고정하면 발전량과 변동비가 서로 다른 물리를 말한다.
        """
        return to_won(
            self.annual_generation_kwh(year=year)
            * self.variable_om_won_per_kwh
            * self.escalation_factor(year=year)
        )

    def replacement_schedule(self, *, horizon: int) -> dict[int, Money]:
        """`RC-ALL-C4` 교체비 — 수명 도달 **다음 연도 초**에 계상 (§13.2.2).

        오라클: 인버터 12년 → **13년차**. 본체 25년은 20년 분석기간 내 없음.

        **부속설비의 독립 수명이 이 메서드의 존재 이유다** (FR-104-AC4). 본체
        수명만 보면 20년 분석에서 인버터 교체비가 통째로 빠지고, 회수기간이
        짧게 나와 필요 지원액이 과소 산정된다. 12년차가 아닌 이유는 12년차가
        **아직 쓰고 있는 해**이고, 한 해 차이가 할인 때문에 회수기간을 바꾸기 때문.

        ⚠ **이 스케줄은 `_acquisitions()` 에서 파생된다** (R44 · WP-13). 종전에는
        여기와 `_acquisitions()` 가 **각자** `(수명, 단가)` 짝을 돌았다. 두 곳이
        갈리면 *교체비는 계상되는데 그 취득분의 잔존가치는 안 세어지는* 상태가
        조용히 생기고, 그것은 결론을 **한 방향으로만** 나쁘게 만들어 「보수적이라
        안전하다」로 읽힌다. `ESS`(R42)·`HeatPump`(R43 · WP-D2)가 같은 자리에서
        같은 답을 냈다 — **한 곳이 내고 다른 곳이 읽는다.** 부품을 왜 접지 않는지,
        최초 인버터를 왜 취득분으로 세지 않는지는 전부 `_acquisitions()`
        독스트링에 있다. **같은 조건을 두 곳에 적지 않는다.**

        **`retire` 면 빈다** (`FR-104-AC3`) — 그 조건을 **여기 다시 적지 않는다.**
        `_acquisitions()` 가 `retire` 에서 1년차 본체 하나만 내고 그것은 아래에서
        걸러지므로 이 함수는 저절로 빈다.

        ⚠ **단가가 0인 부품은 재취득하지 않는다.** `HeatPump._acquisitions()` 에
        있던 `unit_cost > 0.0` 가드를 이식해, 이제 단가 0인 부품은 미래 교체 연도에 0원 행을
        내지 않고 건너뛴다. 종전에는 이 가드가 없어 단가 0이어도 `{13: 0원}`(인버터 기준)을 내어
        프로포마에 「교체가 있었다」로 읽혔으며, 그 어긋남의 크기와 변경 전 동작 기록은
        `.orch/R44/result_13.md` 에 남겼다.

        `horizon` 검증은 **여기가 진다** — `_acquisitions()` 에는 그 검증이 없고
        `salvage_value()` 는 그것을 검증 없이 부른다(`HeatPump` 와 같은 배치).
        """
        if horizon <= 0:
            raise ValidationError(
                field="pv.horizon",
                reason=f"{self.name}: 분석기간은 1년 이상입니다: {horizon}",
                action="분석기간(horizon)에 1 이상의 정수를 지정하십시오",
            )

        schedule: dict[int, Money] = {}
        for _life, acquired in self._acquisitions(horizon=horizon):
            for year, cost in acquired.items():
                # 1년차 최초 취득은 CAPEX 이지 교체비가 아니므로 제외한다
                if year == 1:
                    continue
                # 같은 해에 본체와 인버터가 겹치면 더한다 — 덮어쓰면 한쪽이
                # 조용히 사라진다
                schedule[year] = to_won(to_won(cost) + schedule.get(year, Money(0)))
        return {year: schedule[year] for year in sorted(schedule)}

    def _acquisitions(self, *, horizon: int) -> tuple[tuple[int, dict[int, float]], ...]:
        """부품별 `(수명, {취득 연도: 취득가})` — 본체와 인버터를 **갈라** 담는다.

        ## 왜 부품별로 갈라야 하는가 (R39-E · 갈래 ④)

        `ESS._acquisitions()` 가 이미 세운 규약이 *「잔존가치를 **마지막 취득
        시점**부터 센다」* 다 — 최초 취득만 보면 교체 직후에도 잔존가치가 0으로
        잡혀 **새로 산 설비가 통째로 사라진다.** `PV` 는 그 규약을 따르지 않고
        있었고(`salvage_value()` 가 `_gross_capex_won()` 만 봤다), 그래서 13년차에
        새로 산 인버터가 20년차 잔존가치에서 사라졌다.

        ⚠ **`ESS` 를 그대로 베낄 수는 없다.** `ESS` 는 취득분을 **연도 하나의
        사전**으로 접고 마지막 것 하나만 쓰는데(배터리 한 부품만 재취득하므로
        그것으로 충분하다), `PV` 는 **수명이 다른 부품 둘**을 갖는다 — 인버터
        12년·본체 25년. 접어 버리면 20년차에 「마지막 취득 = 13년차 인버터」가
        되고 그 잔존가치를 **본체 수명 25년**으로 재게 되어, 인버터가 25년
        버티는 설비가 된다. 그래서 접지 않고 부품별로 남긴다.

        ⚠ **최초 인버터를 취득분으로 세지 않는다.** 대장의 설비 단가
        (`capex.pv.rooftop`)는 *「원/kW (설치 완료 기준)」* 이므로 최초 인버터
        값은 이미 `_gross_capex_won()` 안에 있고, 여기서 또 세면 **초기투자에
        없는 지출**의 잔존가치를 세게 된다. 반대로 본체 취득가에서 인버터 몫을
        떼어내지도 않았다 — 떼려면 「설비 단가의 몇 %가 인버터인가」를 새로
        정해야 하고 그 값은 대장에 없다(`DEFAULT_INVERTER_CAPEX_RATIO` 는
        *교체비* 비율로 선언된 상수이며 취득가의 구성비가 아니다). **모르는 값을
        채우지 않는다** — 그 결과 최초 인버터 몫이 본체 잔존가치에 남아 있다는
        어긋남은 `.orch/R39/result_replacement_wiring.md` 에 크기와 함께 올렸다.

        ⚠ **`replacement_schedule()` 이 여기서 파생된다** (R44 · WP-13). 종전에는
        두 함수가 **각자** 같은 `(수명, 단가)` 짝을 돌았고, 갈리면 *교체비는
        계상되는데 그 취득분의 잔존가치는 안 세어지는* 상태가 조용히 생겼다.
        `tests/casegrid/test_lifecycle_wiring.py` ⓒ 가 여전히 둘을 대조하지만,
        이제 그 대조는 **1년차를 거르는 규약**만 재는 동어반복에 가깝다 — 갈림을
        막는 것은 시험이 아니라 **출처가 하나뿐이라는 사실**이다.
        **`retire` 갈래가 그 대조의 첫 실물이었다** — 아래 참조.

        ⚠⚠ **`retire` 면 재취득이 없다** (`FR-104-AC3` · R39-E2 가 고쳤다).
        `replacement_schedule()` 은 `retire` 에서 **빈 사전**을 내는데 이 함수는
        그것을 보지 않아 **사지도 않은 인버터의 잔존가치**를 `retire` 자원에
        붙이고 있었다(20년차 900,000 → 1,185,354원). 두 곳이 갈리면 *교체비는
        없는데 그 취득분의 잔존가치는 있는* 상태가 되며, 그것은 위 ⚠ 가 경고한
        어긋남의 **반대 방향**이다. 그래서 같은 조건을 **두 곳에 적지 않고**
        `retires_at_end_of_life()` 하나를 양쪽이 함께 본다.
        """
        if self.retires_at_end_of_life():
            # 다시 사지 않으므로 취득분은 **최초 본체 하나**다. 인버터를 여기
            # 두면 `replacement_schedule()` 이 비어 있는데 잔존가치만 생긴다.
            return ((self.lifetime, {1: self._gross_capex_won()}),)

        parts: list[tuple[int, dict[int, float]]] = []
        for life, unit_cost, initial in (
            # 본체 — 최초 취득(1년차)은 `_gross_capex_won()`(부대비 포함)이고
            # 재취득분은 `replacement_schedule()` 과 같은 단가를 쓴다.
            (self.lifetime, self.unit_capex_won_per_kw, self._gross_capex_won()),
            # 인버터 — 최초 취득분을 두지 않는다(위 ⚠ 참조).
            (self.inverter_lifetime, self.inverter_unit_capex_won_per_kw, None),
        ):
            acquired: dict[int, float] = {} if initial is None else {1: initial}
            if unit_cost > 0.0:
                year = life + 1
                while year <= horizon:
                    cost = self.capacity_kw * unit_cost * self.replacement_escalation_factor(
                        year=year
                    )
                    acquired[year] = float(to_won(cost))
                    year += life
            if not acquired:
                continue
            parts.append((life, acquired))
        return tuple(parts)

    def salvage_value(self, *, year: int) -> Money:
        """`RC-ALL-C5` 잔존가치 = `취득가 × 잔존수명 / 총수명` (§13.2.2).

        **부품마다 마지막 취득 시점부터 센다** (R39-E) — 근거는
        `_acquisitions()` 독스트링. 20년 분석에서 13년차에 새로 산 인버터는
        4년치 잔존수명을 갖는데, 종전 구현은 최초 취득(`_gross_capex_won()`)만
        보아 그것을 **0으로** 두었다.

        ⚠ **오라클이 움직였다.** §13.2.2 C-5 의 `4,500,000 × 5/25 = 900,000원`
        은 취득분이 **하나**라는 전제의 수다. 인버터 재취득분을 세면 같은 제원에서
        `900,000 + 225,000 = 1,125,000원` 이 된다. 조항 문면(§1918 C-5)은
        *「어느 취득가」* 를 **말하지 않으며**(침묵), `ESS` 는 그 침묵을 「취득
        시점 리셋」으로 메우고 사유를 적어 두었다 — 정본이 이미 있고 `PV` 가
        따르지 않았던 것이다. **조항의 오라클과 이 구현이 갈린 상태**이며 조항에
        「어느 취득가」를 명문화하는 것은 사람 몫이다(§16.5). 그 어긋남은
        `.orch/R39/result_replacement_wiring.md` 가 크기와 함께 올렸다.

        **할인은 여기서 하지 않는다.** 할인율은 사업 단위 전제(FR-701)이지 자원의
        속성이 아니다. 자원이 할인율을 들고 있으면 같은 설비가 시나리오마다 다른
        잔존가치를 갖고, 관점별(FR-704) 할인율 차이도 적용할 수 없다. 할인 후
        값은 `discounted_salvage_value()` 가 준다.
        """
        horizon = int(year)
        total = 0.0
        for life, acquired in self._acquisitions(horizon=horizon):
            within = [y for y in acquired if y <= horizon]
            if not within:
                continue
            last_year = max(within)
            used = horizon - last_year + 1  # 취득 연도부터 센다 (1-base, ESS 와 같다)
            remaining = max(0, life - used)
            total += acquired[last_year] * remaining / life
        return to_won(total)

    def discounted_salvage_value(self, *, year: int, discount_rate: float) -> Money:
        """최종연도 잔존가치의 현재가치 — 오라클 `900,000 / 1.045^20` = 373,179원."""
        if discount_rate <= -1.0:
            raise ValidationError(
                field="pv.discount_rate",
                reason=f"{self.name}: 할인율이 -100% 이하입니다: {discount_rate}",
                action="할인율을 -1(-100%)보다 큰 값으로 지정하십시오",
            )
        nominal = float(self.salvage_value(year=year))
        return to_won(nominal / (1.0 + discount_rate) ** int(year))


# ── 입력 검증 도우미 ────────────────────────────────────────────────
# 오류 메시지에 **자원 이름과 받은 값**을 반드시 넣는다 — 자원 수십 개짜리
# 시나리오에서 «값이 범위 밖»만 나오면 어느 자원인지 찾지 못한다.


def _in_range(value: float, low: float, high: float, *, field: str, label: str, name: str) -> float:
    if not low <= value <= high:
        raise ValidationError(
            field=field,
            reason=f"{name}: {label} 은(는) {low}~{high} 범위입니다 (받은 값 {value})",
            action=(
                f"{label}을(를) {low}~{high} 범위의 값으로 지정하십시오 "
                "(비율은 코드 내부에서 0~1 소수로 정규화합니다, §7.5)"
            ),
        )
    return float(value)


def _positive(value: float, *, field: str, label: str, name: str) -> float:
    if not value > 0:
        raise ValidationError(
            field=field,
            reason=f"{name}: {label} 은(는) 0보다 커야 합니다 (받은 값 {value})",
            action=f"{label}에 0보다 큰 값을 지정하십시오",
        )
    return float(value)


def _non_negative(value: float, *, field: str, label: str, name: str) -> float:
    if value < 0:
        raise ValidationError(
            field=field,
            reason=f"{name}: {label} 은(는) 음수가 될 수 없습니다 (받은 값 {value})",
            action=f"{label}에 0 이상의 값을 지정하십시오",
        )
    return float(value)
