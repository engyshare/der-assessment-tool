"""계절마다 대표일을 **각각 돌려 계절일수로 가중 합산**하는 운전 (R64/WP-4 · 착수 36ⓐ).

## 왜 `e2e_runner.py` 에서 갈라냈나

`core/casegrid/e2e_runner.py` 는 `NFR-206` 코드 줄 상한(500)에 **499/500** 으로
닿아 있었고(`check_file_size.py --code-strict` 실측), `run_single_case_e2e` 의
`PLR0915` 문장 상한(50)도 이미 꽉 차 있었다. 계절 루프를 그 자리에 그대로 넣으면
둘 다 넘긴다. **상한을 올려 푸는 것은 spec 개정(§16.5)이므로 하지 않는다** —
이 저장소가 이미 두 번 쓴 방법(`core/casegrid/pv_allocation.py` R60/WP-2 ·
`core/casegrid/ess_build.py` R57/WP-5)을 따라 새 모듈로 뽑는다.

**가르는 선은 「자원 조립 + 운전」이다.** 러너에 남는 것은 대장 조회(`_resolve`)·
편익 조립·프로포마·지표이며, 이 모듈이 갖는 것은 *「무슨 자원을 세워 어떤 하루를
몇 번 돌리는가」* 하나다.

## 무엇이 달라졌나 — 종전과 지금

    종전   연간 결과 = 몫 가중 평균 대표일 1일의 운전 × 365
    지금   연간 결과 = Σ_계절 ( 그 계절 대표일 1일의 운전 × 그 계절 일수 )

종전에는 계절이 여럿인 자산도 `DailyShape.representative_day()` 가 내는 **하루 한
벌**로 접혀 들어갔고, 그래서 겨울 하루와 여름 하루가 같아 **ESS 도 PV 잉여도 계절을
몰랐다.** 지금은 계절마다 자원을 세워 각각 돌린다.

## ★★★ 합산을 **어느 자리에서** 하는가 — 「일수 가중 평균 하루」

계절별 운전 결과를 합치는 자리는 **`SystemDispatch` 하나**다:

    연간등가 하루[j] = Σ_계절 ( 그 계절 하루[j] × 계절일수 / 365 )

그렇게 접은 하루를 러너의 종전 연간화 규약(`operating_lines.annualise` 의 ×365)에
그대로 먹이면 **`연간등가 하루 × 365 == Σ_계절 (계절 하루 × 계절일수)`** 이므로,
곧 위 산식의 오른쪽과 같다. 창을 읽는 편익(`scales_with_dispatch_window`)은 전부
창의 **합**에 선형이고(`SurplusSale`·`REC`·`NWAs` 의 `sum(max(0, e))` 는 계통 송전
계열이 이미 음수를 갖지 않으므로 선형이다), 계통 수전 비용도 `sum × 365` 다.

⚠⚠ **이 자리를 「편익 금액」으로 옮기면 안 된다.** 금액에서 합치면 **월 단위로 이미
연간값인 편익**(`PeakShaving`·`CP` — `scales_with_dispatch_window = False`)이 계절
수만큼 곱해진다. 이 모듈은 금액을 만들지 않으므로 그 사고가 구조적으로 불가능하다.

⚠ **그 대신 첨두 절감은 계절을 모른다.** `PeakShaving` 은 사업장 최대부하가 정하는
월 단위 편익이고, 이 모듈이 내는 연간등가 하루의 부하 계열은 **종전 대표일과 원소
하나까지 같다**(아래 「무엇이 안 움직이는가」). 계절별 월 피크를 따로 모형화하는
것은 이 WP 의 몫이 아니다 — `ESS.reducible_peak_kw` 독스트링의 「한계」 절이 그
자리를 이미 적어 두었다.

## 왜 「일수 가중 평균 하루」가 종전 하루와 **입력에서는** 같은가

`DailyShape.representative_day()` 는 몫 가중 평균이고
`representative_day_by_season()` 은 접기 전 해상도이며, 둘 사이에 항등식이 있다
(R64/WP-3 이 시험으로 붙들었다 — `test_the_day_weighted_mean_of_the_seasons_is_the_folded_day`):

    Σ_계절 ( 계절 대표일[j] × 계절일수 / 365 ) == representative_day()[j]

그러므로 **자원에 들어가는 발전·부하는 접기 전과 접은 뒤가 같다** — 연간 총량이
움직일 수 없다(성질 「가」). 움직이는 것은 **운전이 비선형**이기 때문이다:
계통 송·수전은 `max(0, 순합)` 으로 갈리고 ESS 충전은 SOC·출력 상한에 걸린다.
평균 하루를 돌린 결과와 계절마다 돌려 평균한 결과가 그 자리에서 갈린다.

## 차례에 무감하다 (성질 「다」 · 착수 36번의 위험)

계절을 적는 차례를 바꿔도 연간 결과가 같아야 한다. 이 모듈이 그것을 지키는 방법은
둘이다 — ① 계절을 **이어 붙이지 않는다**(`spread()` 가 아니라
`representative_day_by_season()` 을 부른다) ② 합산을 **`math.fsum`** 으로 한다
(순차 `+` 는 더하는 차례가 마지막 자리에 남는다). R60/WP-4 가 실측한
*「차례만 바꿔도 연간 발전이 +281kWh 생기고 부하가 −315kWh 사라진다」* 가 ① 을
어겼을 때 나는 증상이다.

## 자산은 하나다 — **총량은 자산이 정하고 운전만 계절을 안다** (판정 ①)

취득비·수명·고정 O&M·교체비는 **계절과 무관한 사실**이므로 여기서 계절마다 다른
값을 만들지 않는다. 자원 객체를 계절마다 세우는 것은 **그 계절의 하루를 돌리기
위해서**이고, 러너가 돈을 매기는 자원(`CaseDispatch.pv`·`ess_fleet`·`ess_whole`)은
**연간등가 하루 위에 선 한 벌**이다. 계절이 하나면 그 한 벌이 계절 한 벌과
같은 값을 갖는다.

⚠ **ESS 의 PV 잉여 충전 계획만은 계절을 지난다.** `CaseDispatch.pv_surplus_profile_kwh`
는 계절별 잉여(`max(0, 그 계절 발전 − 그 계절 부하)`)를 일수로 가중 평균한 것이며,
종전의 *「평균 하루의 잉여」* 와 다르다(클램프가 비선형이다). 배터리가 한 해 동안
실제로 받는 잉여의 연간 평균이 그쪽이므로 이 값을 쓴다.

## ★★★ 「AI 가전」이 **계절마다** 부하를 옮긴다 (R64/WP-7 · 사용자 요구 2)

`dr_shiftable_share_pct` 가 *「가전 부하 중 하루 안에서 옮길 수 있는 몫」* 이고,
그 몫은 **그 계절 하루의 태양광 잉여가 있는 시각으로** 간다
(`core/casegrid/load_shift.py::shift_into_pv_surplus`).

⚠⚠ **계절마다 따로 옮긴다.** 계절마다 잉여가 나는 시각과 크기가 다르므로 —
겨울에는 하루 종일 잉여가 없을 수 있다 — 연간등가 하루에서 옮기고 계절에 나눠
주면 이 모듈이 푼 상쇄가 **부하 쪽에서 다시 접힌다.** 충전 쪽 PV 잉여를 계절별로
넘기면서 부하 이동만 접는 것은 같은 하루를 두 해상도로 읽는 것이다
(`_setup_one_season` 의 ★★ 절이 방전 쪽에서 같은 판단을 적었다).

⚠ **총량은 한 kWh 도 움직이지 않는다** — 옮기는 것이지 더하는 것이 아니다.
그래서 성질 「가」(자원에 들어가는 발전·부하의 연간 총량 불변)는 **그대로**다.

⚠ **연간등가 부하 하루는 옮긴 계절 하루들의 일수 가중 평균으로 다시 세운다**
(`_shifted_household`). 접힌 하루를 따로 옮기면 그 하루가 리포트가 인쇄하는
하루(계절별 하루의 가중 평균)와 갈리고, 그때 「부하 추종」 방전이 인쇄된 하루와
다른 하루를 따라간다. **옮긴 몫이 하나도 없으면 종전 객체를 그대로 쓴다** —
그 실행은 이 배선이 생기기 전과 원소 하나까지 같다.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from core.casegrid.appliance_load import ApplianceSeasonShares
from core.casegrid.ess_build import build_case_ess_fleet
from core.casegrid.ess_share import ESSShare, ESSSharePlan
from core.casegrid.household_scale import household_scale
from core.casegrid.load_shift import shift_into_pv_surplus
from core.casegrid.models import SeasonRun
from core.casegrid.operating_lines import DAYS_PER_YEAR
from core.casegrid.profiles import DailyShapes
from core.casegrid.pv_allocation import (
    _dispatch_inputs_under_baseline,
    resolve_ess_discharge_inputs,
)
from core.casegrid.season_blend import blend_dispatch, blend_series
from core.cba.baseline import BaselineArrangement, PoolMeteringDeclaration
from core.cba.proforma import check_analysis_period
from core.contracts.der import DER, DispatchContext, DispatchResult
from core.contracts.engine import DispatchEngine, SystemDispatch
from core.contracts.units import Year
from core.der.ess import ESS, ESSChargeSource, ESSOperatingMode
from core.der.ess_schedule import ESSDischargeAllocation
from core.der.load import Load
from core.der.pv import PV, OperatingMode, PVAllocationPriority

__all__ = (
    "CaseDispatch",
    "build_and_dispatch_case",
    "dispatch_note",
)


def dispatch_note(seasons: Sequence[SeasonRun], *, steps_per_day: int) -> str:
    """붙임 7 머리의 **시간 해상도 문면** — *실제로 하는 일*을 적는다 (판정 ④).

    ## ⚠⚠⚠ 종전 문면은 이 WP 가 도는 순간 **거짓**이 됐다

    옛 문면은 *「대표일 1일을 24스텝으로 모의하고 365일로 연간화한다. **계절·요일
    변동을 반영하지 않으므로** 잉여 판매량은 대표일의 365배다」* 였다. 계절을
    반영하게 됐으므로 그 앞 절이 거짓이다 — 문면을 안 고치면 산출물이 **자기가
    한 일을 부정하면서** 그 결과를 싣는다.

    ## ⚠ 「요일까지 반영했다」로 적지 않는다 — 안 했다

    주중·주말 대표일은 여전히 가르지 않는다. 그 결손은 붙임 8 의
    「계절·요일 변동」 항목이 계속 신고한다(`core/report/unreflected.py`).

    ## 갈래가 둘인 이유

    계절이 여럿인 자산에서만 계절 합산이 실제로 일어난다. 계절이 하나(`연중`)
    이거나 형상 자산이 없는 실행에서는 **하루 한 벌**이며, 그 실행에 계절 문면을
    적으면 하지 않은 일을 적는 것이 된다.
    """
    tail = (
        "첨두 절감은 월 단위 12회로 이미 연간값이라 곱하지 않는다"
    )
    if len(seasons) < 2:
        return (
            f"대표일 1일을 {steps_per_day}스텝(1시간 간격)으로 모의하고 "
            f"{DAYS_PER_YEAR}일로 연간화한다. 자산이 계절을 선언하지 않아 "
            "계절 간 하루 차이가 없고 요일 변동도 반영하지 않으므로 잉여 "
            f"판매량은 대표일의 {DAYS_PER_YEAR}배다. {tail}"
        )
    calendar = " · ".join(f"{s.name} {s.days}일" for s in seasons)
    return (
        f"계절 {len(seasons)}개({calendar} · 합 {sum(s.days for s in seasons)}일)의 "
        f"대표일을 **각각** {steps_per_day}스텝(1시간 간격)으로 모의하고 그 계절 "
        "일수로 가중 합산해 연간화한다. 이 표가 싣는 하루는 계절별 하루를 "
        "일수로 가중 평균한 **연간등가 하루**이며, 잉여 판매량은 그 하루의 "
        # RUF001: 「×」는 검토자가 읽는 산식 문면이다 — `operating_lines.py` 의
        # `benefit_line()` 이 같은 이유로 같은 면제를 쓴다(대상을 좁히는 면제이지
        # 규칙을 넓히는 것이 아니다).
        f"{DAYS_PER_YEAR}배 = Σ(계절 하루 × 그 계절 일수) 다. **요일 변동은 "  # noqa: RUF001
        f"반영하지 않는다** — 주중·주말 대표일을 가르지 않는다. {tail}"
    )


@dataclass(frozen=True)
class CaseDispatch:
    """자원 조립 + 계절 운전의 산출 — 러너가 받는 한 묶음.

    ⚠ **묶음 하나로 돌려주는 이유는 러너의 `PLR0915` 다.** 값마다 따로 돌려주면
    러너에서 대입 문장이 그만큼 늘고, 그 함수는 문장 상한에 이미 닿아 있다.
    """

    #: 운전 창 — 24스텝 대표일 하나. 계절마다 **같은 창**이다.
    ctx: DispatchContext
    #: 돈을 매기는 태양광 한 벌 — **연간등가 하루** 위에 선다(모듈 머리말).
    pv: PV
    #: 가구 부하. 총량을 주지 않은 실행에서는 `None` 이다.
    household: Load | None
    #: 디스패치·수명·비용·자원 표에 실을 저장장치 **전건**(몫 분기 포함).
    ess_fleet: tuple[ESS, ...]
    #: 몫 계획 전건. 몫이 없으면 빈 튜플이다.
    ess_plans: tuple[ESSSharePlan, ...]
    #: 가르기 전의 **물리 배터리 한 대** — 교체비·잔존가치가 그 사건이다.
    ess_whole: ESS
    #: 엔진에 실은 자원 전건 — 러너가 `CaseOutcome.resources` 로 나른다.
    resources: tuple[DER, ...]
    #: **연간등가 하루**의 운전 — 계절별 하루를 일수로 가중 평균한 것이다.
    #: 러너는 이 하루에 종전 그대로 `DAYS_PER_YEAR` 를 곱한다.
    dispatch: SystemDispatch
    #: 계절별 결과 전건. **자산이 계절을 세우지 않은 실행에서는 비어 있다** —
    #: 형상 자산을 주지 않은 실행(케이스 그리드·성능 측정)이 그렇다.
    seasons: tuple[SeasonRun, ...]
    #: 연간등가 PV 잉여 시계열 — 자가소비율·ⓒ 대칭 항이 읽는다(머리말 ⚠).
    pv_surplus_profile_kwh: list[float]
    #: 이 실행이 실제로 고른 PV 배분 순서(승격·거부까지 끝난 값).
    pv_allocation_priority: PVAllocationPriority


def build_and_dispatch_case(
    *,
    engine: DispatchEngine,
    daily_shapes: DailyShapes | None,
    case_values: Mapping[str, object],
    horizon_years: int,
    steps_per_day: int,
    seconds_per_hour: int,
    pv_capacity_kw: float,
    pv_capacity_factor: float,
    pv_capex: float,
    pv_inverter_share: float,
    pv_fixed_om: float,
    pv_self_consumption_ratio: float,
    price_escalation_rate: float,
    replacement_escalation_rate: float,
    annual_load_kwh: float | None,
    extra_appliance_load_kwh: float,
    household_count: int | None,
    # ★★ **냉난방(추가 기기) 부하의 계절별 몫** (R64/WP-3b-1 · 사용자 요구 3).
    # `None` 이 미지정이며 그때 아래 두 호출이 **종전 식을 그대로** 지난다 —
    # `core/casegrid/appliance_load.py::ApplianceSeasonShares` 머리말 ⛔ 절.
    appliance_shares: ApplianceSeasonShares | None = None,
    dr_shiftable_share_pct: float,
    ess_shares: Sequence[ESSShare] | None,
    ess_capacity_kwh: float,
    ess_capex: float,
    ess_fixed_om: float,
    ess_replacement_price: float,
    ess_operating_mode: ESSOperatingMode | str | None,
    ess_charge_source: ESSChargeSource | str | None,
    ess_discharge_allocation: ESSDischargeAllocation | str | None,
    pv_allocation_priority: PVAllocationPriority | str | None,
    baseline_arrangement: BaselineArrangement | str | None,
    pool_metering: PoolMeteringDeclaration | None,
) -> CaseDispatch:
    """자원을 세우고 **계절마다 돌려** 연간등가 하루로 접는다.

    ## ⚠ 제원 상수 다섯을 인자로 받는 이유

    `STEPS_PER_DAY`·`SECONDS_PER_HOUR`·`PV_CAPACITY_FACTOR`·
    `PRICE_ESCALATION_RATE`·`PV_SELF_CONSUMPTION_RATIO` 는 **`e2e_runner.py` 의
    모듈 상수**이고, 리포트 문면이 그 소유자를 *「`core/casegrid/e2e_runner.py`
    모듈 상수」* 라고 **이름으로 지목한다**(`core/casegrid/operating_lines.py`
    머리말의 ⚠ 절이 그 함정을 적어 두었다 — 옮기면 그 문면이 거짓이 되고 리포트
    매니페스트 해시가 움직인다). 그래서 **옮기지 않고 받는다.**

    ## 도는 차례

    ① 계절 목록을 자산에서 받는다(`_season_inputs`) — 없으면 계절 하나짜리 실행
    ①ⓑ **계절마다 가전 부하를 그 계절의 PV 잉여 시각으로 옮긴다**(`_shift_seasons` ·
       R64/WP-7). 총량은 그대로이고 하루의 모양만 바뀐다
    ② 계절마다 PV·부하를 세우고 **그 계절의 PV 잉여**를 만든다(저장장치는 아직)
    ③ 잉여를 일수로 가중 평균해 **연간등가 자원 한 벌**을 세운다 — 저장장치의
       설정 판정(`충전원=태양광 잉여인데 한 해에 잉여가 없다`)이 여기서 난다
    ④ 계절마다 **하루를 돌린다** — 잉여가 0 인 계절에서는 배터리가 쉰다
    ⑤ `DV-5`(분석기간 상한)를 **디스패치 결과를 쓰기 전에** 잰다
    ⑥ 계절별 하루를 일수로 가중 평균해 연간등가 하루를 만든다

    ⚠ **⑤ 의 자리** — 종전에는 *「자원이 서자마자」* 였고 디스패치보다 앞이었다.
    지금은 계절 운전이 자원 조립과 얽혀 있어 그보다 이르게 둘 수 없다. 대신
    **어떤 편익·프로포마·CBA 도 돌기 전에** 거부한다는 성질은 그대로다 — 이
    함수는 금액을 하나도 만들지 않는다. ⚠ `pool_metering` 의 `DV-15` 거부는
    여전히 **저장장치 조립보다 이르다**(② 안에서 첫 계절이 그 자리를 지난다).
    """
    ctx = DispatchContext(steps=steps_per_day, dt=seconds_per_hour, year=Year(1))
    generation_total_kwh = pv_capacity_kw * pv_capacity_factor * steps_per_day * DAYS_PER_YEAR
    # ⚠ **부하를 여기서 먼저 세운다** — 「총량은 주고 형상은 잊었다」를 거부하는
    # 자리가 이 생성자 하나이기 때문이다(`tests/casegrid/test_household_load_gate.py`).
    # 계절 목록을 먼저 만들면 형상 없는 실행에서 계절이 하나로 떨어지면서 그
    # 실수가 **조용히** 「부하 없는 실행」이 된다.
    # ★★ **냉난방 몫에 「총부하 안의 비중」을 채워 둔다** (R64/WP-3b-1). 아래
    # 두 자리가 같은 분해를 써야 **인쇄하는 하루와 배터리가 따라가는 하루**가
    # 갈리지 않는다(`ApplianceSeasonShares.folded_year` 독스트링).
    shares = ApplianceSeasonShares.of(appliance_shares, annual_load_kwh, extra_appliance_load_kwh)
    household = _household_load_if_total_given(
        daily_shapes, annual_load_kwh, extra_appliance_load_kwh, household_count,
        escalation_rate=price_escalation_rate, appliance_shares=shares,
    )
    load_total_kwh = _load_total_kwh(
        annual_load_kwh, extra_appliance_load_kwh, household_count
    )
    pv_spec = _PVSpec(
        capacity_kw=pv_capacity_kw, capacity_factor=pv_capacity_factor, capex=pv_capex,
        inverter_share=pv_inverter_share, fixed_om=pv_fixed_om,
        escalation_rate=price_escalation_rate,
        replacement_escalation=replacement_escalation_rate,
        self_consumption_ratio=pv_self_consumption_ratio,
    )
    ess_spec = _ESSSpec(
        shares=ess_shares, capacity_kwh=ess_capacity_kwh, capex=ess_capex,
        fixed_om=ess_fixed_om, replacement_price=ess_replacement_price,
        escalation_rate=price_escalation_rate,
        replacement_escalation=replacement_escalation_rate,
    )
    inputs = _season_inputs(daily_shapes, generation_total_kwh, load_total_kwh, shares)
    weights = tuple(season.days / DAYS_PER_YEAR for season in inputs)
    # ★★★ **「AI 가전」이 계절마다 부하를 옮긴다** (R64/WP-7 · 사용자 요구 2).
    # 모듈 머리말의 ★★★ 절이 정본이다. 총량은 그대로이고 옮겨 가는 곳은 **그
    # 계절 하루의 태양광 잉여가 있는 시각**이며, 잉여가 없는 계절에서는 하루가
    # 원소 하나까지 그대로다.
    inputs = _shift_seasons(
        inputs, share_pct=dr_shiftable_share_pct,
        appliance_ratio=_appliance_ratio(annual_load_kwh, extra_appliance_load_kwh),
    )
    household = _shifted_household(
        household, inputs, weights, escalation_rate=price_escalation_rate
    )
    # ★★ **방전 배분 축은 계절이 갈리기 전에 한 번만 고른다** (R64/WP-6b).
    # *「이 실행에 따라갈 수요가 있는가」* 는 연간 수준의 사실이라 계절마다 다시
    # 내리면 부하가 어느 계절에만 0 인 자산에서 갈래가 계절마다 갈리고,
    # `_resolved_once` 가 그것을 거부한다. 여기서 고른 갈래를 계절마다 **인자로
    # 되먹이고**, 계절이 새로 짓는 것은 **그 계절의 부하 시계열 하나**다.
    # 짝으로 나오는 `load_whole` 은 연간등가 배터리가 설 하루다 — 아래 ★★ 참조.
    # ⚠ **부하를 옮긴 뒤에 부른다** (R64/WP-7) — 이 호출이 짓는 `load_whole` 이
    # 연간등가 배터리가 따라갈 하루이고, 그 하루는 리포트가 인쇄하는 하루와
    # 같아야 한다(모듈 머리말 마지막 ⚠). 옮기기 전에 부르면 그 배터리가 **옮기기
    # 전 저녁 봉우리**를 따라가고, 그 어긋남은 아무 예외도 내지 않는다.
    discharge_allocation, load_whole = resolve_ess_discharge_inputs(
        ess_discharge_allocation, case_values, ctx, household=household,
    )
    setups = [
        _setup_one_season(
            ctx, season=season, pv_spec=pv_spec,
            escalation_rate=price_escalation_rate, case_values=case_values,
            ess_operating_mode=ess_operating_mode, ess_charge_source=ess_charge_source,
            pv_allocation_priority=pv_allocation_priority,
            ess_discharge_allocation=discharge_allocation,
            baseline_arrangement=baseline_arrangement, pool_metering=pool_metering,
        )
        for season in inputs
    ]
    # ★★ **연간등가 자원 한 벌** — 판정 ① (총량은 자산이 정하고 운전만 계절을
    # 안다). PV 는 계절 대표일의 일수 가중 평균이 곧 `representative_day()`
    # 이므로(모듈 머리말의 항등식) 종전과 **원소 하나까지 같은** 하루 위에 선다.
    # ESS 만은 계절별 잉여의 가중 평균 위에 서며, 그 이유는 머리말 마지막 ⚠ 다.
    # ⚠ **부하는 옮긴 하루 위에 선다** (R64/WP-7) — 위 `_shifted_household` 가
    # 계절별 옮긴 하루의 일수 가중 평균으로 다시 세웠고, **옮긴 몫이 없으면**
    # 그 항등식이 그대로여서 종전과 원소 하나까지 같다.
    #
    # ⚠⚠ **배터리는 계절 운전보다 **먼저** 선다** — 「충전원이 태양광 잉여인데
    # 한 해에 잉여가 하나도 없다」를 거부하는 자리가 여기 하나여야 하기 때문이다.
    # 계절마다 세우면서 그 판정을 걸면 겨울 한 계절이 비었다고 한 해가 거부된다
    # (`_dispatch_one_season` 의 ★★★ 절이 실측과 함께 적는다).
    pv = pv_spec.build(
        None if daily_shapes is None
        else daily_shapes.generation.spread_over_representative_day(
            generation_total_kwh, days=DAYS_PER_YEAR
        )
    )
    surplus = blend_series([s.surplus for s in setups], weights)
    mode, source, priority, allocation = _resolved_once(setups)
    # ★★★ **연간등가 배터리의 설정 판정은 「옮기기 전」 잉여로 한다** (R64/WP-7).
    # 근거 전문은 `_setup_one_season` 의 ★★★ 절이 갖는다 — 그 거부는 **설비
    # 구성**의 물음이고 부하 이동은 **운전**이며, 그 비율은 우리가 세운 가정값이다.
    # ⚠ 옮기지 않은 실행에서는 두 목록이 같으므로 이 줄은 종전과 같은 값을 낸다.
    # ⚠ **`CaseDispatch.pv_surplus_profile_kwh` 는 옮긴 뒤 잉여 그대로다**(위
    # `surplus`) — 자가소비율·ⓒ 대칭 항이 읽는 것은 **실제로 남은 잉여**여야 한다.
    surplus_for_setting = blend_series(
        [s.surplus_before_shift for s in setups], weights
    )
    # ★★ **연간등가 배터리에는 연간등가 하루의 부하를 넘긴다** (R64/WP-6b).
    # 이 한 대는 **설정 오류를 잡는 자리**이고(위 ⚠⚠ 절) 리포트 0절이 「운전
    # 방식」 칸에 그 대의 `discharge_allocation` 을 인쇄한다 — 그러므로 그 대가
    # 서는 하루도 리포트가 인쇄하는 하루(`CaseDispatch.dispatch` 의 연간등가
    # 하루)와 같아야 한다. 계절 하나의 부하를 여기 넣으면 **어느 계절의 것인지**
    # 말할 수 없고, 그 대가 받는 설정 판정도 그 계절의 것이 된다.
    ess_fleet, ess_plans, ess_whole = ess_spec.build(
        operating_mode=mode, charge_source=source,
        pv_surplus_profile_kwh=surplus_for_setting,
        discharge_allocation=allocation, load_profile_kwh=load_whole,
    )
    runs = [
        _dispatch_one_season(
            engine, ctx, setup=setup, ess_spec=ess_spec,
            idle_names=tuple(e.name for e in ess_fleet),
        )
        for setup in setups
    ]
    # ★ **분석기간 상한 (DV-5)** — 위 독스트링 ④ 절 참조. 몫 전건의 수명을 넣는다
    # (하나만 넣으면 나머지 몫이 상한 판정에서 사라진다).
    check_analysis_period(
        analysis_years=horizon_years,
        asset_lifetimes_years=[pv.lifetime, *(e.lifetime for e in ess_fleet)],
    )
    return CaseDispatch(
        ctx=ctx, pv=pv, household=household, ess_fleet=ess_fleet, ess_plans=ess_plans,
        ess_whole=ess_whole,
        resources=(
            (pv, *ess_fleet) if household is None else (pv, *ess_fleet, household)
        ),
        dispatch=blend_dispatch([run.dispatch for run in runs], weights),
        seasons=(
            () if daily_shapes is None
            # ★ **옮긴 몫을 계절 결과에 함께 싣는다** (R64/WP-7) — 표시 층이
            # 그것을 자산에서 다시 세면 인쇄된 이동량과 결론이 선 이동량이
            # 갈릴 수 있다(`SeasonRun` 독스트링의 같은 판단).
            else tuple(
                _season_run(run, load_shift_kwh=season.load_shift_kwh)
                for run, season in zip(runs, inputs, strict=True)
            )
        ),
        pv_surplus_profile_kwh=surplus,
        pv_allocation_priority=priority,
    )


# ── 계절 목록과 계절별 하루 ────────────────────────────────────────────────


@dataclass(frozen=True)
class _SeasonInput:
    """계절 하나에 들어가는 것 — 이름 · 일수 · 그 계절의 발전 하루 · 부하 하루."""

    name: str
    days: int
    generation_day: tuple[float, ...] | None
    #: 자산이 낸 **옮기기 전** 부하 하루. ⚠ 옮긴 뒤에도 이 칸은 그대로다 —
    #: 「설비 구성에 잉여가 있는가」를 묻는 자리가 이 하루를 쓴다
    #: (`_setup_one_season` 의 ★★★ 절).
    load_day: tuple[float, ...] | None
    #: 「AI 가전」이 **옮긴 뒤**의 부하 하루. `None` 이면 옮기지 않았다는 뜻이며
    #: 그때 운전도 `load_day` 로 돈다 (`_operating_day`).
    shifted_load_day: tuple[float, ...] | None = None
    #: 그 계절 하루에서 **옮긴 가전 부하**(kWh/일) — `_shift_seasons` 가 채운다.
    #:
    #: ⚠ 기본값 `0.0` 은 *「아직 옮기지 않았다」*이며, `_season_inputs` 가 내는
    #: 값이 그것이다 — 옮기는 것은 그 다음 단계이고 두 단계를 한 함수에 넣지
    #: 않는다(형상을 읽는 일과 형상을 옮기는 일은 다른 판정이다).
    load_shift_kwh: float = 0.0

    @property
    def operating_day(self) -> tuple[float, ...] | None:
        """운전이 도는 하루 — 옮겼으면 옮긴 하루, 아니면 자산이 낸 하루."""
        return self.load_day if self.shifted_load_day is None else self.shifted_load_day


def _season_inputs(
    daily_shapes: DailyShapes | None,
    generation_total_kwh: float,
    load_total_kwh: float | None,
    appliance_shares: ApplianceSeasonShares | None = None,
) -> tuple[_SeasonInput, ...]:
    """계절마다 (이름 · 일수 · 발전 하루 · 부하 하루). **일수를 여기서 세지 않는다.**

    정본은 자산이고 그것을 읽는 것은 `DailyShape._calendar_days()` 하나다
    (`representative_day_by_season()` 이 그 함수에서 받는다) — 두 곳에서 따로
    세면 한쪽만 고쳐진다. 여기서는 발전과 부하가 **같은 달력 위에 섰는지**만
    다시 확인한다.

    ⚠ **형상 자산이 없는 실행은 계절 하나짜리다.** 그때 PV 는 이용률 하나로
    균등 배분하고 부하는 서지 않으므로 계절이 가를 것이 없다 — 종전 실행과
    원소 하나까지 같아야 한다(성질 「라」).

    ★★ **`appliance_shares` 가 냉난방을 기본 부하에서 떼어 낸다** (R64/WP-3b-1 ·
    사용자 요구 3). 종전에는 둘이 합쳐진 뒤 **기본 부하의 계절 몫 하나**로
    나뉘어 냉난방 몫이 기본 몫과 강제로 같았다. `None` 이면 그 종전 식을
    그대로 지난다 — 새 식으로 다시 계산하지 않는다(`ApplianceSeasonShares`
    머리말 ⛔ 절).
    """
    if daily_shapes is None:
        return (_SeasonInput("연중", DAYS_PER_YEAR, None, None),)
    generation = daily_shapes.generation.representative_day_by_season(
        generation_total_kwh, days=DAYS_PER_YEAR
    )
    if load_total_kwh is None:
        return tuple(
            _SeasonInput(season.name, days, day, None)
            for season, day, days in generation
        )
    load = ApplianceSeasonShares.load_days(
        daily_shapes.load, load_total_kwh, appliance_shares, days=DAYS_PER_YEAR
    )
    if [(s.name, d) for s, _w, d in generation] != [(s.name, d) for s, _w, d in load]:
        raise ValueError(
            f"발전 형상의 계절 달력 {[(s.name, d) for s, _w, d in generation]} 과 "
            f"부하 형상의 계절 달력 {[(s.name, d) for s, _w, d in load]} 이 "
            "다릅니다 — 계절마다 돌려 합산하려면 두 자원이 같은 달력 위에 "
            "서야 합니다"
        )
    return tuple(
        _SeasonInput(season.name, days, day, load_day)
        for (season, day, days), (_ls, load_day, _ld) in zip(generation, load, strict=True)
    )


def _year_of(day: tuple[float, ...]) -> list[float]:
    """계절 대표일 한 벌을 **연간 스텝 수만큼** 되풀이한다.

    ⚠ **`계절일수` 가 아니라 `DAYS_PER_YEAR` 만큼 되풀이한다.** 자원은 받은
    시계열의 앞 하루만 잘라 쓰지만(`core/der/pv.py`·`core/der/load.py` 의
    `[: ctx.steps]`) **길이는 `DV-4`(연간 스텝 수)가 본다** — 계절일수로 줄이면
    그 검증이 거부한다. `spread_over_representative_day()` 가 접힌 하루에 대해
    하는 일과 같으며, 다른 것은 되풀이하는 하루가 **그 계절의 것**이라는 점뿐이다.
    """
    return [value for _day in range(DAYS_PER_YEAR) for value in day]


# ── 「AI 가전」 — 계절마다 부하를 옮긴다 (R64/WP-7) ─────────────────────────


def _appliance_ratio(
    annual_load_kwh: float | None, extra_appliance_load_kwh: float
) -> float:
    """그 하루 부하 중 **가전의 몫** — 옮길 수 있는 비율의 분모를 좁힌다.

    사용자 문면이 *「집 전체 **가전** 부하 중 비율」* 이므로 히트펌프·전기차는
    분모에서 빠진다(`core/casegrid/load_shift.py` 머리말 마지막 ⚠ 절이 정본).

    ⚠ **가구 수는 약분된다** — 총량과 증분에 같은 배수가 곱해지므로 이 비율은
    가구 수에 무관하다. 그래서 여기서 `household_scale` 을 부르지 않는다.

    ⚠ 부하를 세우지 않은 실행과 총량이 0 인 실행에서는 `1.0` 이다 — 그때
    옮길 부하 자체가 없어 이 수가 어떤 값이어도 옮긴 몫이 0 이다.
    """
    total = (annual_load_kwh or 0.0) + extra_appliance_load_kwh
    return annual_load_kwh / total if annual_load_kwh and total > 0.0 else 1.0


def _shift_seasons(
    inputs: tuple[_SeasonInput, ...], *, share_pct: float, appliance_ratio: float
) -> tuple[_SeasonInput, ...]:
    """계절마다 **그 계절의 잉여로** 부하를 옮긴다 (사용자 판정 §4·§5).

    ⚠ **비율이 0 이면 받은 것을 그대로 돌려준다** — 새 객체를 짓지 않으므로
    그 실행은 이 배선이 생기기 전과 **원소 하나까지** 같다. 골든 회귀가 그
    동일성을 재는 자리이며(`tests/golden/test_regression_scenarios.py`), 러너
    인자의 기본값이 0 인 이유도 그것이다.

    ⚠ **발전 하루가 없는 실행은 옮기지 않는다.** 형상 자산 없이 도는 실행
    (케이스 그리드·성능 측정)에서는 PV 가 이용률 하나로 균등 배분되어 「잉여가
    있는 시각」이라는 개념이 서지 않는다 — 그때 옮기면 **하루 종일 조금씩
    잉여가 있는 가짜 하루**로 옮기는 것이 되고, 그 이동은 실물 근거가 없다.
    """
    if share_pct <= 0.0:
        return inputs
    return tuple(
        _shifted_season(season, share_pct=share_pct, appliance_ratio=appliance_ratio)
        for season in inputs
    )


def _shifted_season(
    season: _SeasonInput, *, share_pct: float, appliance_ratio: float
) -> _SeasonInput:
    """계절 하나를 옮긴다 — **두 칸을 함께** 바꿔 든다.

    ⚠ 하루만 옮기고 이동량을 두지 않으면 산출물이 *「옮길 곳이 없어 그대로다」*
    와 *「비율이 0 이라 그대로다」* 를 가릴 수 없다.
    """
    if season.load_day is None or season.generation_day is None:
        return season
    shift = shift_into_pv_surplus(
        season.load_day, season.generation_day,
        share_pct=share_pct, appliance_ratio=appliance_ratio,
    )
    if shift.moved_kwh <= 0.0:
        # ★ **옮긴 것이 없으면 새 하루를 달지 않는다** — `shifted_load_day` 가
        # `None` 이어야 아래 `_setup_one_season` 이 잉여를 **한 번만** 짓는다.
        return season
    return replace(
        season, shifted_load_day=shift.day, load_shift_kwh=shift.moved_kwh
    )


def _shifted_household(
    household: Load | None,
    inputs: tuple[_SeasonInput, ...],
    weights: Sequence[float],
    *,
    escalation_rate: float,
) -> Load | None:
    """연간등가 부하를 **옮긴 계절 하루들의 일수 가중 평균**으로 다시 세운다.

    ## 왜 접힌 하루를 따로 옮기지 않는가

    옮기는 연산은 `max(0, 발전 − 부하)` 를 지나므로 **비선형**이다. 그래서
    「접은 뒤에 옮긴 하루」와 「옮긴 뒤에 접은 하루」가 다르고, 리포트가
    인쇄하는 하루(`core/casegrid/season_blend.py::blend_dispatch` 가 낸 연간등가
    하루)는 **뒤쪽**이다. 앞쪽을
    세우면 연간등가 배터리가 인쇄되지 않은 하루를 따라간다.

    ⚠ **옮긴 몫이 하나도 없으면 받은 객체를 그대로 돌려준다.** 그때 계절별
    하루의 일수 가중 평균은 `representative_day()` 와 항등이지만(모듈 머리말)
    **연산 차례가 달라 마지막 자리가 어긋날 수 있다** — 그 어긋남이 골든의
    수를 움직이면 「무엇이 축을 옮겼나」가 흐려진다. 그래서 여기서 동일성을
    성질에 맡기지 않고 **객체를 그대로 두는 것으로** 지킨다.
    """
    if household is None or not any(s.load_shift_kwh > 0.0 for s in inputs):
        return household
    day = blend_series(
        [s.operating_day for s in inputs if s.operating_day is not None], weights
    )
    return _build_load(_year_of(tuple(day)), escalation_rate)


# ── 자원 조립 — **한 자리에서만 세운다** ───────────────────────────────────


@dataclass(frozen=True)
class _PVSpec:
    """계절과 무관한 PV 제원. 계절마다 바뀌는 것은 **발전 시계열 하나**다.

    ⚠ 계절마다 `PV(...)` 를 다시 적으면 사본이 되고, 제원 하나를 고칠 때 계절
    하나만 고쳐지는 날이 온다 — 그 어긋남은 아무 예외도 내지 않는다.
    """

    capacity_kw: float
    capacity_factor: float
    capex: float
    inverter_share: float
    fixed_om: float
    escalation_rate: float
    #: ⚠ **칸 이름이 생성자 인자 이름(`replacement_escalation_rate`)과 일부러
    #: 다르다.** `scripts/check_unread_extension_points.py` 는 **속성 접근 이름**
    #: 으로 「계약이 내놓은 것을 배포 코드가 읽는가」를 세는데, 이 칸을 그 이름으로
    #: 두면 `self.replacement_escalation_rate` 가 **`DER` 의 그 필드를 읽은 것으로
    #: 잘못 세어진다** — 이 값은 생성자에 넘겨질 뿐 아무도 자원에서 되읽지 않는다.
    #: 부채 목록이 거짓으로 줄어드는 것이 이 저장소가 반복해 잡아 온 형태다.
    replacement_escalation: float
    self_consumption_ratio: float

    def build(self, generation_profile: Sequence[float] | None) -> PV:
        """★ **형상이 오면 이용률 대신 시계열을 준다** (둘 다 주면 자원이 거부한다).

        연간 발전량은 **그대로**이며 시간대만 옮겨간다 — 형상은 배분이지 값이
        아니다. 형상 없는 실행(케이스 그리드·성능 측정)은 정당한 상태이고,
        그때 이용률 하나로 균등 배분한다.
        """
        return PV(
            name="e2e-pv",
            capacity_kw=self.capacity_kw,
            capacity_factor=None if generation_profile is not None else self.capacity_factor,
            generation_profile_kwh=generation_profile,
            unit_capex_won_per_kw=self.capex,
            inverter_unit_capex_won_per_kw=self.capex * self.inverter_share,
            # ★ **인버터 교체 단가** (사용자 판정 §7 · R52/WP-6). 조사가 크기 근거를
            # 찾지 못해(WP-5 §7) **취득 단가와 같은 값**을 쓴다 — 위 줄과 같은
            # 표현식이며 지어낸 차이가 아니다. `pv.py::inverter_replacement_unit_
            # won_per_kw` 가 그 통로다.
            inverter_replacement_unit_won_per_kw=self.capex * self.inverter_share,
            fixed_om_won_per_year=self.fixed_om,
            escalation_rate=self.escalation_rate,
            replacement_escalation_rate=self.replacement_escalation,
            self_consumption_ratio=self.self_consumption_ratio,
            operating_mode=OperatingMode.FULL_EXPORT,
        )


def _build_load(hourly_kwh: Sequence[float], escalation_rate: float) -> Load:
    """가구 부하 자원을 세우는 **유일한 자리** — 계절별 하루도 연간등가 하루도 여기로 온다.

    ⚠ 계절마다 `Load(...)` 를 따로 적으면 사본이 되고, 인자 하나를 고칠 때 한쪽만
    고쳐지는 날이 온다 — 그 어긋남은 아무 예외도 내지 않는다.

    ★ **부하는 편익을 만들지 않는다** (`RC-LD-B0` · `Load.value_streams()` 는
    비어 있다). 그래서 이 자원을 더해도 편익 갈래는 늘지 않고 **운전만**
    달라진다 — 계통 수전이 실제 수량으로 나온다. 화폐화(자가소비 절감·구매
    비용)는 요금 엔진의 몫이며, 한쪽만 계상하면 사업에 불리한 쪽으로 틀린다
    (NSPM 대칭성).

    ⚠ **`escalation_rate` 는 지금 어떤 수도 움직이지 않는다** — 이 `Load` 에는
    비용 인자가 하나도 없어(단가·O&M·부속설비 전부 미지정) 곱할 것이 없다.
    그런데도 넘기는 이유는 `tests/contract/test_escalation_debt.py` 래칫이
    R42 에 **처음으로 이 자리를 보았기** 때문이며 — 곧 부채가 는 것이 아니라
    사각이 드러난 것이고 — 비용 인자가 들어오는 날 조용히 실질 기준이 되지
    않도록 지금 닫아 둔다 (`DV-7`).
    """
    return Load(name="e2e-load", hourly_kwh=hourly_kwh, escalation_rate=escalation_rate)


def _household_load_if_total_given(
    daily_shapes: DailyShapes | None,
    annual_load_kwh: float | None,
    extra_appliance_load_kwh: float = 0.0,
    household_count: int | None = None,
    *,
    escalation_rate: float,
    appliance_shares: ApplianceSeasonShares | None = None,
) -> Load | None:
    """가구 부하 자원 — **부하 총량(`annual_load_kwh`)이 왔을 때만** 세운다.

    ⚠ **R64/WP-4 가 `core/casegrid/e2e_runner.py` 에서 여기로 옮겼다.** 계절마다
    부하를 세워야 하는데 `Load(...)` 를 두 곳에 적으면 사본이 되기 때문이다 —
    러너는 이 이름을 **재수출**하므로 `e2e_runner._household_load_if_total_given`
    를 가리키는 문면들은 그대로 참이다(`ess_build.py`·`pv_allocation.py` 가 쓴
    것과 같은 재수출 규약 · `scripts/check_docstring_references.py`). ⚠
    **`escalation_rate` 가 인자가 됐다** — 그 상수(`PRICE_ESCALATION_RATE`)의
    소유자는 여전히 `e2e_runner.py` 이고 이 모듈은 받기만 한다(이 파일이 그
    상수를 옮기지 않는 이유는 `build_and_dispatch_case` 독스트링에 있다).

    `extra_appliance_load_kwh` (판정 §5·B-2)는 히트펌프 등 추가 전력사용기기의
    **연간 소비전력량**이며 총량에 더해진다 — `annual_load_kwh` 가 `None`
    이면(부하를 세우지 않는 실행) 더할 기저가 없으므로 **무시된다**.

    ⚠⚠ **`extra_appliance_load_kwh` 는 「호당」이다** (R64/WP-1 이 판정해 여기
    적는다 — 여태 어느 문서도 이것을 적지 않았다). 근거는 대장이다:
    `docs/assumptions.yaml::load.household.annual` 의 `applicable_scope` 가
    *「이 총량은 추가 전력사용기기(히트펌프 등)가 없는 가구 기준이다 … 그
    기기의 **연간 소비전력량을 이 값에 더해** 총량이 비례 증가하는 형태여야
    한다」* 라고 적고, 그 「이 값」이 **kWh/호·년** 이다. 그러므로 증분도 한
    호의 것이고 **더한 뒤에 가구 수를 곱한다** — 곱한 뒤에 더하면 추가 기기가
    단지에 딱 한 대 있는 사업이 된다.

    ★★ **`household_count` 는 「총량」에만 곱한다** (R64/WP-1 · 착수 47ⓐ).
    대표일 24스텝 **형상은 건드리지 않는다** — 형상은 합이 1 인 배분 벡터라
    가구 수와 무관하고, 형상을 만지면 계절 축(착수 36번)과 충돌한다.
    `None` 이 **「적지 않았다」**이며 그때 배수가 1 이라 이 배선이 생기기 전과
    원소 하나까지 같다(`core/casegrid/household_scale.py` 머리말 ⚠⚠⚠).

    ## 왜 함수 이름이 조건을 말하는가 (R37)

    종전에는 「형상과 총량이 함께 와야 한다」였고, 형상만 오면 **오류로 막았다**.
    그 막음이 잡으려던 실수는 *「부하를 넣을 생각이었는데 총량을 잊었다」* 다.

    R37 이 일사 곡선을 기본 경로에 배선하면서 `daily_shapes` 는 **발전 형상의
    자산이 되었다** — 이제 형상은 모든 실행에 온다. 그러므로 *형상이 왔다* 를
    *부하를 원한다* 로 읽을 수 없다. 부하를 원한다는 뜻은 **총량만이** 말한다.

    ⚠ **그래서 조건을 그냥 풀지 않고 이름으로 갈랐다.** 조건만 완화하면 옛
    실수(총량을 잊었다)가 조용히 통과하고 호출부는 그것을 알 수 없다. 이름이
    `…_if_total_given` 이면 호출 자리에서 *「총량을 주지 않으면 부하가 서지
    않는다」* 가 읽히므로, 통과가 조용하지 않다. 반대 방향의 실수는 **여전히
    오류다** — 총량은 왔는데 형상이 없으면 부하가 하루 안에서 균등 배분되어
    지금 PV 가 겪던 것과 같은 형태가 되고(붙임 8 「일중 발전 프로파일」),
    *「부하를 반영했다」* 는 진술이 성립하는데 **그 부하는 실제로 아무 시간대도
    갖지 않는다.**

    ★★ **`appliance_shares` 는 위 `_season_inputs` 와 같은 분해를 쓴다**
    (R64/WP-3b-1). 두 자리가 다른 식으로 서면 리포트가 인쇄하는 하루와
    연간등가 배터리가 따라가는 하루가 갈린다 —
    `ApplianceSeasonShares.folded_year` 독스트링이 그 판단을 갖는다.

    ## ★★ 이것이 내는 하루는 **연간등가 하루**다

    `spread_over_representative_day()` 는 `representative_day()`(몫 가중 평균
    하루)를 365일 되풀이한다. **계절이 여럿이어도 그 하루는 계절별 대표일의
    일수 가중 평균과 같으므로**(모듈 머리말의 항등식) 연간 총량이 대장값
    그대로다. 계절 간 차이를 담는 것은 이 자원이 아니라 계절마다 따로 세우는
    자원들이다(`_run_one_season`).
    """
    if annual_load_kwh is None:
        return None
    if daily_shapes is None:
        raise ValueError(
            "연간 부하(annual_load_kwh)를 주면 대표일 형상(daily_shapes)도 "
            "함께 주어야 합니다 — 총량만 주면 부하가 시간대를 갖지 못한 채 "
            "「반영했다」가 성립합니다"
        )
    total = _load_total_kwh(annual_load_kwh, extra_appliance_load_kwh, household_count)
    assert total is not None  # 위 분기가 보장한다 (타입 좁히기)
    return _build_load(
        ApplianceSeasonShares.folded_year(
            daily_shapes.load, total, appliance_shares, days=DAYS_PER_YEAR
        ),
        escalation_rate,
    )


def _load_total_kwh(
    annual_load_kwh: float | None,
    extra_appliance_load_kwh: float,
    household_count: int | None,
) -> float | None:
    """단지 총부하 (kWh/년) — 총량을 주지 않았으면 `None`(부하를 세우지 않는다).

    산식과 그 판정 근거는 위 `_household_load_if_total_given` 독스트링이 갖는다
    (증분은 「호당」이므로 **더한 뒤에** 가구 수를 곱한다).
    """
    if annual_load_kwh is None:
        return None
    return (annual_load_kwh + extra_appliance_load_kwh) * household_scale(household_count)


@dataclass(frozen=True)
class _ESSSpec:
    """계절과 무관한 ESS 제원. 계절마다 바뀌는 것은 **PV 잉여 시계열 하나**다.

    ⚠ 조립 전문(제원 상수 여덟과 몫 분기)은 `core/casegrid/ess_build.py` 가
    갖는다 — 여기서 넘기는 것은 이미 해석된 값들과 대장에서 온 값들뿐이다.
    """

    shares: Sequence[ESSShare] | None
    capacity_kwh: float
    capex: float
    fixed_om: float
    replacement_price: float
    escalation_rate: float
    #: ⚠ 이름이 생성자 인자와 다른 이유는 위 `_PVSpec` 의 같은 칸 주석에 있다.
    replacement_escalation: float

    def build(
        self,
        *,
        operating_mode: ESSOperatingMode | str,
        charge_source: ESSChargeSource | str,
        pv_surplus_profile_kwh: Sequence[float] | None,
        discharge_allocation: ESSDischargeAllocation | str,
        load_profile_kwh: Sequence[float] | None,
    ) -> tuple[tuple[ESS, ...], tuple[ESSSharePlan, ...], ESS]:
        """★ **계절마다 바뀌는 시계열이 이제 둘이다** (R64/WP-6b · 사용자 요구 5).

        충전 쪽 `pv_surplus_profile_kwh` 옆에 방전 쪽 `load_profile_kwh` 가
        섰다. 둘 다 **제원이 아니라 그 하루의 사실**이므로 이 데이터클래스의
        칸이 아니라 인자로 받는다 — 칸으로 두면 계절마다 `_ESSSpec` 을 다시
        세워야 하고, 그러면 제원이 계절마다 갈릴 수 있다.
        """
        return build_case_ess_fleet(
            shares=self.shares,
            capacity_kwh=self.capacity_kwh,
            operating_mode=operating_mode,
            charge_source=charge_source,
            pv_surplus_profile_kwh=pv_surplus_profile_kwh,
            discharge_allocation=discharge_allocation,
            load_profile_kwh=load_profile_kwh,
            capex_unit_won_per_kwh=self.capex,
            fixed_om_won_per_year=self.fixed_om,
            replacement_unit_won_per_kwh=self.replacement_price,
            escalation_rate=self.escalation_rate,
            replacement_escalation_rate=self.replacement_escalation,
        )


# ── 계절 하나를 돌린다 ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class _SeasonSetup:
    """계절 하나의 **자원과 그 계절이 고른 것들** — 저장장치는 아직 없다.

    ⚠ **저장장치를 여기서 세우지 않는 이유**는 그 배터리가 **한 해에 한 대**이고
    그 판정(충전원이 태양광 잉여인데 한 해에 잉여가 하나도 없는가)이 **연간
    수준의 사실**이기 때문이다 — 계절마다 세우면서 그 판정을 계절에 걸면,
    겨울처럼 잉여가 0 인 계절 하나 때문에 **한 해 전체가 거부된다**(⑩·실측).
    """

    name: str
    days: int
    pv: PV
    household: Load | None
    #: 그 계절의 PV 잉여 — **부하를 옮긴 뒤**의 하루에서 난다. 운전이 이것으로
    #: 돈다(그 계절의 배터리가 실제로 받는 몫).
    surplus: list[float]
    #: 같은 계절의 PV 잉여 — **부하를 옮기기 전**의 하루에서 난다. 이것을 쓰는
    #: 자리는 **연간등가 배터리의 설정 판정 하나**다(`_setup_one_season` 의
    #: ★★★ 절이 근거를 갖는다). 옮기지 않은 실행에서는 위 칸과 같은 목록이다.
    surplus_before_shift: list[float]
    operating_mode: ESSOperatingMode | str
    charge_source: ESSChargeSource | str
    priority: PVAllocationPriority
    #: 이 계절이 고른 방전 배분과 **그 계절의** 부하 시계열 (R64/WP-6b · 요구 5).
    #: ⚠ 짝으로 든다 — 「고정 창」이면 부하가 `None` 이고 그 조합만 `ESS` 가
    #: 받는다(`pv_allocation.resolve_ess_discharge_inputs`).
    discharge_allocation: ESSDischargeAllocation | str
    load_profile: list[float] | None

    @property
    def has_pv_surplus(self) -> bool:
        """그 계절에 **채울 잉여가 하루 중 한 시각이라도 있는가.**

        `ESS` 가 `충전원=태양광 잉여` 인데 잉여가 전부 0 인 시계열을 거부하는
        기준과 **같은 식**이다(`core/der/ess_schedule.py::check_pv_surplus_profile`).
        여기서 다른 식을 쓰면 「거부되는가」와 「비었다고 보는가」가 갈린다.
        """
        return any(v > 0.0 for v in self.surplus)


@dataclass(frozen=True)
class _OneSeason:
    """계절 하나의 운전 — 모듈 안에서만 산다."""

    name: str
    days: int
    dispatch: SystemDispatch


def _setup_one_season(
    ctx: DispatchContext,
    *,
    season: _SeasonInput,
    pv_spec: _PVSpec,
    escalation_rate: float,
    case_values: Mapping[str, object],
    ess_operating_mode: ESSOperatingMode | str | None,
    ess_charge_source: ESSChargeSource | str | None,
    pv_allocation_priority: PVAllocationPriority | str | None,
    ess_discharge_allocation: ESSDischargeAllocation | str | None,
    baseline_arrangement: BaselineArrangement | str | None,
    pool_metering: PoolMeteringDeclaration | None,
) -> _SeasonSetup:
    """그 계절의 **태양광·부하를 세우고 그 계절의 PV 잉여를 만든다.**

    ★★★ **기준선 갈래가 이 자리를 지난다** (`FR-705-AC2`) — `_dispatch_inputs_
    under_baseline` 이 ⓐ(자가용 없음)에서 가구로 가는 몫을 0 으로 만들고,
    ⓒ(집합자원화)의 계측 선언이 없으면 `DV-15` 로 **거부한다.** 그 거부는
    저장장치 조립·디스패치보다 이르다.

    ⚠ **운전 방법·충전원·배분 순서는 계절과 무관하다** — 셋 다 인자·`case_values`·
    모듈 상수에서 오며 형상을 보지 않는다. 계절마다 다시 고르는 것은 그 사실을
    이 자리에서 확인하기 위해서이고(갈리면 `_resolved_once` 가 거부한다),
    실제로 갈리는 것은 **시계열 둘**이다.

    ## ★★ 시계열이 둘이 됐다 — **그 계절의 부하를 그 계절의 ESS 에 넘긴다**

    R64/WP-6b(사용자 요구 5)가 방전 쪽 시계열을 세웠다. 방전 배분 **갈래**는
    위 셋과 같이 계절과 무관하지만(`_resolved_once` 가 넷째로 함께 잰다),
    **그 갈래가 따라갈 부하는 계절마다 다르다** — 겨울 저녁의 봉우리와 여름
    저녁의 봉우리는 같은 하루가 아니다.

    ⛔ **연간등가 하루의 부하 한 벌을 네 계절에 돌려쓰지 않는다.** 그러면
    「부하 추종」이 계절을 안 보는 추종이 되고, R64/WP-4 가 푼 계절 상쇄가
    **방전 쪽에서 다시 접힌다** — 충전 쪽 PV 잉여를 계절별로 넘기면서 방전
    쪽만 접는 것은 같은 하루를 두 해상도로 읽는 것이다.
    """
    pv = pv_spec.build(
        None if season.generation_day is None else _year_of(season.generation_day)
    )
    operating = season.operating_day
    household = (
        None if operating is None
        else _build_load(_year_of(operating), escalation_rate)
    )
    mode, source, surplus, priority = _dispatch_inputs_under_baseline(
        ess_operating_mode, ess_charge_source, dict(case_values), pv, ctx,
        pv_allocation_priority=pv_allocation_priority, household=household,
        baseline_arrangement=baseline_arrangement,
        pool_metering=pool_metering,
    )
    # ★★★ **옮기기 전 잉여를 함께 짓는다 — 설정 판정만 이것으로 한다** (R64/WP-7)
    #
    # 왜 둘이 필요한가. `ESS(충전원=태양광 잉여)` 는 잉여 시계열이 전부 0 이면
    # **거부한다**(`core/der/ess_schedule.py::check_pv_surplus_profile`). 그
    # 거부가 묻는 것은 *「이 **설비 구성**(태양광 용량 · 부하 총량 · 배터리)에
    # 한 해 동안 태양광 잉여가 있는가」* 이며, 그래서 그 문면이 조치로 적는 것도
    # **설비·규모의 손잡이 둘**이다 — *「부하를 줄이거나(가구 수·히트펌프·전기차)
    # 태양광 용량을 키우십시오」*.
    #
    # 「가전 부하를 하루 안에서 옮긴다」는 그 구성을 **하나도 바꾸지 않는 운전
    # 선택**이고, 게다가 그 비율은 **우리가 대장에 세운 가정값**이다. 그것이
    # 설비 구성의 성립 여부를 뒤집으면 **우리 가정 때문에 사용자의 실행이
    # 거부된다** — 실측(2026-09-06): 골든 시나리오에 가구 수 2호를 적으면
    # 비율 5%까지는 서고 **10%에서 `DV` 거부**가 난다(옮긴 부하가 그 구성의
    # 얇은 잉여를 전부 채운다). 가구 수 축(R64/WP-1)이 화면에서 답하던 값이
    # 가정값 하나로 사라지는 것이므로 그렇게 두지 않는다.
    #
    # ⇒ **설정 판정은 옮기기 전 잉여로, 운전은 옮긴 뒤 잉여로** 한다.
    # ⛔ 그 대신 **운전을 옮기기 전 잉여로 돌리지 않는다** — 그러면 배터리가
    #    가구가 이미 쓴 전기로 충전해 같은 kWh 가 두 번 쓰인다.
    # ✅ 옮긴 뒤 잉여가 0 인 계절에서는 **그 계절의 배터리가 쉰다** — 아래
    #    `_dispatch_one_season` 이 이미 갖고 있는 갈래이며(잉여 없는 계절),
    #    그 사실은 붙임 7 의 계절 표에서 **0 으로 보인다.**
    before = (
        surplus if season.shifted_load_day is None
        else _dispatch_inputs_under_baseline(
            ess_operating_mode, ess_charge_source, dict(case_values), pv, ctx,
            pv_allocation_priority=pv_allocation_priority,
            household=_build_load(_year_of(season.load_day), escalation_rate)
            if season.load_day is not None else None,
            baseline_arrangement=baseline_arrangement,
            pool_metering=pool_metering,
        )[2]
    )
    allocation, load_profile = resolve_ess_discharge_inputs(
        ess_discharge_allocation, case_values, ctx, household=household,
    )
    return _SeasonSetup(
        name=season.name, days=season.days, pv=pv, household=household,
        surplus=surplus, surplus_before_shift=before,
        operating_mode=mode, charge_source=source, priority=priority,
        discharge_allocation=allocation, load_profile=load_profile,
    )


def _dispatch_one_season(
    engine: DispatchEngine,
    ctx: DispatchContext,
    *,
    setup: _SeasonSetup,
    ess_spec: _ESSSpec,
    idle_names: tuple[str, ...],
) -> _OneSeason:
    """그 계절의 **하루를 돌린다** — 잉여가 없는 계절에서는 배터리가 쉰다.

    ## ★★★ 잉여가 하루 종일 0 인 계절 (R64/WP-4 · ⑩ 의 (나) 하나)

    가구 수가 늘거나 겨울처럼 발전이 적은 계절에서는 `max(0, 발전 − 부하)` 가
    **하루 스물넷 전부 0** 이 될 수 있다. 그것은 결함이 아니라 사실이다 —
    태양광 잉여로만 충전하는 배터리는 그 계절에 **한 번도 충전하지 못하고,
    따라서 방전도 하지 못한다.**

    그런데 `ESS` 는 그런 시계열을 **거부한다**
    (`core/der/ess_schedule.py::check_pv_surplus_profile` — *「충전원이 태양광
    잉여인데 잉여 시계열이 없거나 전부 0입니다」*). 그 거부는 **연간 수준의
    설정 오류**(잉여로 충전한다고 해 놓고 한 해에 잉여가 없다)를 잡으라고 선
    것이며 지금도 그 자리에서 그대로 선다 — **연간등가 배터리 한 대**가 그
    판정을 받는다(`build_and_dispatch_case`). 계절 하나가 비었다고 한 해를
    거부하면 *「겨울에 잉여가 없는 단지는 평가할 수 없다」* 가 된다.

    ⛔ **그 계절만 계통 충전으로 바꾸지 않는다** — 리포트의 「충전원: 태양광
    잉여」가 거짓이 된다.
    ⛔ **연간 평균 잉여로 대신 세우지 않는다** — 없는 잉여로 충전하게 되고 그
    몫이 조용히 **겨울 계통 수전**으로 나타난다.
    ✅ **배터리를 그 계절 운전에서 빼고, 그 자리에 0 을 싣는다.** 값을 지어내는
    것이 아니라 *모형이 낼 값 그 자체*이며(`pv_surplus_charge_kwh_by_hour` 가
    빈 계획을 낸다), 실제로 그런지 **수지 검사로 확인한다**(아래 마지막 줄).
    """
    if setup.has_pv_surplus or setup.charge_source != ESSChargeSource.PV_SURPLUS:
        fleet, _plans, _whole = ess_spec.build(
            operating_mode=setup.operating_mode, charge_source=setup.charge_source,
            pv_surplus_profile_kwh=setup.surplus,
            # ★ **그 계절의 부하다** (R64/WP-6b). 연간등가 하루의 부하를 여기
            # 넣으면 네 계절이 같은 저녁 봉우리를 따라가고, WP-4 가 푼 상쇄가
            # 방전 쪽에서 다시 접힌다(`_setup_one_season` 의 ★★ 절).
            discharge_allocation=setup.discharge_allocation,
            load_profile_kwh=setup.load_profile,
        )
    else:
        fleet = ()
    resources: list[DER] = [setup.pv, *fleet]
    if setup.household is not None:
        resources.append(setup.household)
    dispatch = engine.run(resources, ctx)
    if not fleet:
        dispatch = SystemDispatch(
            per_resource={
                **dispatch.per_resource,
                **{name: DispatchResult.zeros(ctx.steps) for name in idle_names},
            },
            grid_import=dispatch.grid_import,
            grid_export=dispatch.grid_export,
        )
        DispatchEngine.verify_balance(dispatch)
    return _OneSeason(name=setup.name, days=setup.days, dispatch=dispatch)


def _resolved_once(
    setups: Sequence[_SeasonSetup],
) -> tuple[
    ESSOperatingMode | str, ESSChargeSource | str, PVAllocationPriority,
    ESSDischargeAllocation | str,
]:
    """운전 방법·충전원·배분 순서·**방전 배분** — 계절마다 같아야 한다. 다르면 거부한다.

    넷은 인자·`case_values`·모듈 상수에서 오며 **형상을 보지 않으므로** 계절이
    갈라도 같은 값이 나온다. 그 사실 위에서 호출부가 「한 벌」의 ESS 를 세우고
    산출물에 배분 순서 하나를 적는데, 만약 갈리면 **어느 계절의 것이 실렸는지
    말할 수 없는 채로** 그 하나가 인쇄된다.

    ⚠ **방전 배분의 짝인 부하 시계열은 여기서 재지 않는다** — 그것은 계절마다
    **달라야 하는** 값이다(`_setup_one_season` 의 ★★ 절). 갈래만 같으면 된다.

    ⚠ **첫 계절 것을 조용히 쓰지 않는다.** 조용히 쓰면 계절 차례가 산출물을
    정하게 되고, 그것이 성질 「다」(차례 무감)를 깨는 자리가 된다 — 이 함수가
    없으면 그 깨짐은 아무 예외도 내지 않는다.
    """
    picked = {
        (s.operating_mode, s.charge_source, s.priority, s.discharge_allocation)
        for s in setups
    }
    if len(picked) != 1:
        raise ValueError(
            "계절마다 ESS 운전 방법·충전원·PV 배분 순서·방전 배분이 다르게 "
            f"해석됐습니다: {sorted(str(item) for item in picked)} — 이 넷은 "
            "형상이 아니라 입력이 정하므로 계절이 갈라도 같아야 합니다"
        )
    first = setups[0]
    return (
        first.operating_mode, first.charge_source, first.priority,
        first.discharge_allocation,
    )


def _season_run(run: _OneSeason, *, load_shift_kwh: float) -> SeasonRun:
    """계절 하나의 운전을 **다음 WP 가 읽을 모양**으로 옮긴다 (판정 ⑤).

    「그 계절 연간 기여」는 **하루 합 × 그 계절 일수**다 — 계절마다 다른 일수를
    곱하는 것이 이 WP 가 여는 것 그 자체이므로, 여기서 `DAYS_PER_YEAR` 를 곱하면
    표가 종전(계절을 모르는 연간화)으로 되돌아간다.

    ⚠ **옮긴 부하도 같은 규약으로 연간화한다** (R64/WP-7) — 하루 옮긴 몫 ×
    그 계절 일수다. `DAYS_PER_YEAR` 를 곱하면 겨울에 옮기지 못한 몫이 봄의
    이동량으로 메워진 것처럼 보인다.
    """
    return SeasonRun(
        name=run.name,
        days=run.days,
        dispatch=run.dispatch,
        per_resource_annual_kwh={
            resource: math.fsum(result.electric) * run.days
            for resource, result in run.dispatch.per_resource.items()
        },
        grid_export_annual_kwh=math.fsum(run.dispatch.grid_export) * run.days,
        grid_import_annual_kwh=math.fsum(run.dispatch.grid_import) * run.days,
        load_shift_annual_kwh=load_shift_kwh * run.days,
    )
