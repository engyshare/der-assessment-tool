"""낮 전기의 배분 순서 — ESS 운전 방법·충전원과 함께 결정한다.

`core/casegrid/e2e_runner.py` 에서 R51/WP-5 가 옮겼다. 그 파일이 `NFR-206`
코드 줄 상한(500)에 **정확히 걸려 있었고**(WP-1·WP-2 실측), 이 WP 가 `SurplusSale`
차감 계산을 그 자리에 더해야 했으므로 분리 없이는 상한을 넘겼다 — WP-1 이
이 자리를 예고해 두었다(`e2e_runner.py::PV_ALLOCATION_PRIORITY_DEFAULT` 옆 주석).

**행동은 한 줄도 바뀌지 않았다.** `_resolve_ess_dispatch_inputs` 와 그 기본값
상수 셋을 독스트링·주석째로 옮겼을 뿐이다 — `e2e_runner.py` 가 이 모듈에서
import 해 그대로 쓴다. 이름을 그대로 둔 이유는 `core/der/ess.py`·`core/der/pv.py`
독스트링과 `tests/casegrid/test_pv_surplus_allocation_priority.py` 가 **정본
선언 자리**로 `e2e_runner._resolve_ess_dispatch_inputs`·`e2e_runner.py::
ESS_CHARGE_SOURCE_DEFAULT` 를 이름으로 가리키기 때문이다 — `e2e_runner.py` 가
이 이름들을 import 로 받아 자기 이름공간에 두면(재수출), 그 문면들은 여전히
참이다(`scripts/check_docstring_references.py` 의 「재수출을 참으로 인정한다」
규약, R43 · WP-F3).

⚠ **기본값 상수 셋(`ESS_OPERATING_MODE_DEFAULT`·`ESS_CHARGE_SOURCE_DEFAULT`·
`PV_ALLOCATION_PRIORITY_DEFAULT`)도 함께 옮겼다.** 함수만 옮기고 상수를
`e2e_runner.py` 에 남기면 이 모듈이 그 상수를 읽으려고 `e2e_runner.py` 를
import 해야 하고, `e2e_runner.py` 는 이 모듈의 함수를 쓰려고 다시 이 모듈을
import 한다 — **순환 import**가 되어 `lint-imports` 의 계층 계약이 깨진다.
이 모듈은 `core.der`·`core.contracts` 아래 계층만 보고 `e2e_runner.py` 를
전혀 모른다.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from core.cba.metrics import self_consumption_rate
from core.contracts.der import DispatchContext
from core.der.ess import ESSChargeSource, ESSOperatingMode
from core.der.load import Load
from core.der.pv import PV, PVAllocationPriority, resolve_pv_allocation_priority

#: 이 사업의 ESS 운전 방법·충전원 기본값 (판정 근거: `docs/decisions-
#: 2026-08-31-R48.md` §1·§4 — 「이 사업의 ESS 는 태양광 연계다. PV 잉여로
#: 충전하고 저녁에 방전한다」·산정식 표 1행). 케이스 그리드나 호출자가 값을
#: 주지 않을 때만 쓰인다 — `run_single_case_e2e()` 의 `ess_operating_mode`·
#: `ess_charge_source` 인자, `case_values["ess_operating_mode"/"ess_charge_source"]`
#: 를 이 순서로 먼저 본다.
ESS_OPERATING_MODE_DEFAULT = ESSOperatingMode.SELF_CONSUMPTION
ESS_CHARGE_SOURCE_DEFAULT = ESSChargeSource.PV_SURPLUS

#: PV 낮 전기 배분 우선순위 **배포 기본값** — 「집 우선」.
#:
#: ★★ **근거는 사용자 판정이다** (`docs/decisions-2026-09-01-R51.md` §1 —
#: *「낮에 만든 전기를 집에서 사용할 수도 있고, 배터리에 충전할 수도 있음. …
#: 지산지소 모델의 경우에는 집에서 우선 사용하는 것이 취지에 맞음」*).
#: `MC-1` 이 재는 것이 그 지산지소 모델이므로 **그 모델의 기본값이 「집
#: 우선」이어야 한다** — 판정 문면의 *「취지에 맞음」* 이 이 한 줄의 전부다.
#:
#: ⚠ 조항 쪽 근거도 같은 방향이다 — `FR-302-AC1` 의 *「① PV 발전 → **즉시**
#: 자가소비」* 에서 「즉시」는 **그 스텝의 실제 가구 부하**를 뜻하며,
#: `BATTERY_FIRST` 의 연간 고정 비율(`PV_SELF_CONSUMPTION_RATIO`)은 그것과
#: 어긋난다(아래 `_resolve_ess_dispatch_inputs` 독스트링이 그 어긋남을 잰다).
#:
#: ⚠⚠ **「배터리 우선」은 지워지지 않았다** — 여전히 고를 수 있는 갈래이며
#: (시나리오·모델 파라미터·호출 인자 셋 다), `PV_SELF_CONSUMPTION_RATIO` 는
#: 그 갈래가 계속 읽으므로 **지우지 마라.** 판정 §1 이 답한 것은 *「하나를
#: 골라라」* 가 아니라 *「고를 수 있게 하고 지산지소의 기본값은 집 우선으로
#: 두라」* 다.
#:
#: ★ **이 한 줄이 R51 의 결론축을 움직였다** — 세 골든 시나리오의 `npv` 가
#: 각각 **+365,018원** 올랐다(`payback_period_years` 는 셋 다 `.inf` 그대로 —
#: 「집 우선」이 사업을 흑자로 돌리지는 않는다). 경위는 세 골든 파일 머리말
#: 주석의 R51 블록이 갖는다. 되돌리려면 이 줄 하나를 `BATTERY_FIRST` 로
#: 되돌리고 골든 셋을 다시 뽑는다.
PV_ALLOCATION_PRIORITY_DEFAULT = PVAllocationPriority.HOUSEHOLD_FIRST


def _resolve_ess_dispatch_inputs(
    ess_operating_mode: ESSOperatingMode | str | None,
    ess_charge_source: ESSChargeSource | str | None,
    case_values: dict[str, object],
    pv: PV,
    ctx: DispatchContext,
    *,
    pv_allocation_priority: PVAllocationPriority | str | None,
    household: Load | None,
) -> tuple[ESSOperatingMode | str, ESSChargeSource | str, list[float], PVAllocationPriority]:
    """운전 방법·충전원·PV 잉여 배분 순서를 고른다 (판정 §1·§3·A-3·A-6,
    `docs/decisions-2026-09-01-R51.md` §1).

    ★ **넷째 반환값(`priority`)은 판정 §4 나-4 의 재료다** — 리포트가 「운전
    방식」 칸에 *이 실행이 실제로 고른* 배분 순서를 적으려면 승격·거부까지
    끝난 값이 필요하고, 그 승격은 이 함수 안에서만 일어난다. 호출부가
    `case_values`·인자를 다시 따라가며 같은 우선순위 사슬을 재현하면 이 함수의
    사슬과 갈릴 수 있다(둘이 따로 바뀌면 조용히 어긋난다) — 그래서 여기서
    돌려준다.

    우선순위(운전 방법·충전원·배분 순서 셋 모두 같은 모양): 호출 인자 →
    `case_values`(문자열로 와도 받는다 — `FR-105-AC5` 가 이미 그 관례다) →
    모듈 상수(`ESS_OPERATING_MODE_DEFAULT`·`ESS_CHARGE_SOURCE_DEFAULT`·
    `PV_ALLOCATION_PRIORITY_DEFAULT`, 근거는 각 상수 옆 주석).

    ⚠ `ESS(...)` 자신이 문자열을 승격·검증한다(`ESS._coerce_charge_source` ·
    `DER._check_operating_mode`) — 여기서 미리 승격하지 않는다, 잘못된 값의
    오류 메시지는 그 자원이 내는 것이 맞다. **`pv_allocation_priority` 는
    다르다** — 이 축은 어느 자원 계약에도 속하지 않으므로(별개 축,
    `PVAllocationPriority` 독스트링 참조) 여기서 직접
    `resolve_pv_allocation_priority()` 로 승격·거부한다(판정 §1 ⑤).

    **PV 잉여 시계열은 PV 를 먼저 디스패치해** 시각별 전기 출력을 얻는다.
    ⚠ **모듈 상수를 읽어 대신하지 않는다** — 읽으면 이 케이스의 실제 PV
    용량·형상이 아니라 기준값을 쓰게 되어 `pv_capacity_kw` 축이 도는 동안에도
    잉여가 그대로다(`pv_inverter_share`·`demand_charge` 주석이 같은 함정을
    적어 두었다).

    ## ★★ PV 출력을 **누가 먼저 가져가는가** — 그 순서를 만드는 자리가 여기다

    `pv_allocation_priority` 가 **어느 계산으로 잉여를 만들지**를 고른다.

    ### `BATTERY_FIRST`(R51/WP-6 이전의 배포 기본값) — 연간 고정 비율

        ① PV 출력 중 「자가소비 비율」분    → 가구 자가소비 (PV 가 비율로 정한다)
        ② 그 나머지(= 잉여) 중 ESS 가 받을 수 있는 만큼 → ESS 충전 (PV_SURPLUS)
        ③ 그래도 남은 몫                   → 계통 역송 (잉여판매)
           가구가 ① 을 넘어 쓰는 수요       → 계통 수전

    ★★ **핵심은 ② 가 가구의 추가 수요보다 앞선다는 것이다.** ① 의 몫을 정하는
    `PV.self_consumption_kwh()` 는 **연간발전량 × 고정 비율**이며 **가구 부하를
    보지 않는다.** 그러므로 가구가 그 비율분을 넘어 쓰는 몫은 ② 를 밀어내지
    못하고 **계통 수전**으로 메워진다 — 부하는 별개 자원(`_household_load_if_total_given`)
    이고, 스텝마다 자원별 시계열을 상계해 남는 부족분을 계통 수전으로 세는 것은
    `RuleBasedEngine._grid_exchange` 다.

    ⚠ **이 갈래를 고르면 ① 은 항등적으로 0 이다.** 러너가 `PV` 를
    `self_consumption_ratio=PV_SELF_CONSUMPTION_RATIO`(= 0.0) 로 세우고 운전
    방법도 전량 판매라 `PV._self_consumption_ratio_effective()` 가 한 번 더 0 으로
    덮는다. 그래서 `surplus_ratio` 는 1.0 이고 **PV 출력 전량이 ② 의 몫으로
    간다** — 가구 부하는 한 kWh 도 ① 로 가지 못하고 전부 계통 수전이 된다.
    ★ **그것이 R51/WP-6 이 배포 기본값을 뒤집은 이유다** — 「집 우선」이 기본이
    아니면 지산지소 모델의 가구가 자기 PV 를 한 kWh 도 못 쓴다.
    **`PV_SELF_CONSUMPTION_RATIO` 는 이 갈래에서만 읽힌다** — `HOUSEHOLD_FIRST`
    는 아래에서 보듯 이 상수를 쓰지 않는다. ⚠ **그러므로 기본값이 바뀌어도
    그 상수를 지우면 안 된다** — 이 갈래가 계속 읽는다.

    **물리적으로 부정확하지는 않다** — 넘치는 몫은 계통 수전으로 메워지므로
    에너지 수지는 맞는다(`RuleBasedEngine.verify_media_balance` 와 그 위의 수지
    검사가 그것을 잰다).

    ### `HOUSEHOLD_FIRST`(**지금 배포 기본값**) — 그 스텝의 실제 가구 부하 (판정 §1·④)

    스텝별 잉여 = `max(0, PV 스텝 출력 − 그 스텝 가구 부하)`. **`household` 가
    `None`(부하를 아예 세우지 않는 실행)이면 뺄 것이 없으므로 `BATTERY_FIRST`
    와 완전히 같은 결과**다 — 채울 집이 없다(아래 분기가 그것을 그대로
    구현한다: `household is None` 이면 이 갈래를 골라도 아래로 떨어진다).

    이것이 `FR-302-AC1` 의 *「① PV 발전 → 즉시 자가소비」* 다 — 「즉시」는 그
    스텝의 실제 부하를 뜻하며, `BATTERY_FIRST` 의 연간 고정 비율과 다르다.
    사용자 판정(`docs/decisions-2026-09-01-R51.md` §1)은 `MC-1`(지산지소
    모델)의 **기본값을 이 갈래로 정했고, R51/WP-6 이 `PV_ALLOCATION_PRIORITY_
    DEFAULT` 를 이 갈래로 뒤집었다** — 그 상수 옆 주석이 근거와 움직인 수를
    갖는다(세 골든 `npv` 각 **+365,018원**).

    ### `PRICE_BASED` — 자리만 있다

    선택하면 `resolve_pv_allocation_priority()` 가 **`ValidationError` 로
    거부한다**(구현 없음) — 조용히 다른 갈래로 떨어뜨리지 않는다.

    ⚠ **자원에게 부하를 넘길 통로가 없어서가 아니다.** `_site_load_kw` 가 이미
    같은 부하를 `ESS.reducible_peak_kw()` 로 넘긴다 — 즉 **피크 저감 편익에는
    부하를 주고 `BATTERY_FIRST` 의 충전 계획
    (`ESS._pv_surplus_charge_kwh_by_hour`)에는 주지 않기로 되어 있는 것**이며,
    `HOUSEHOLD_FIRST` 는 그 부하를 충전 계획에도 준다 — 그것이 이 축이 만드는
    유일한 차이다.

    ⚠ **조항은 순서를 이미 말한다** — `FR-302-AC1` 의 7단계 우선순위가 ①②③
    과 계통 수전을 그대로 적는다. `DEFAULT_RULE_ORDER` 가 같은 일곱을 이름으로
    든다. **`BATTERY_FIRST` 에서 어긋나는 것은 순서가 아니라 ① 의 뜻이다** —
    조항의 ① 은 *「즉시」* 자가소비이고 `BATTERY_FIRST` 의 ① 은 연간 고정
    비율이다. `HOUSEHOLD_FIRST` 는 그 어긋남이 없다.

    ★ **어느 갈래가 최선인가는 판정이며 이 자리가 답하지 않는다.** *「가구
    부하가 ESS 충전보다 먼저여야 하는 것 아닌가」* 는 결론축을 움직이는
    물음이었고 사용자가 §1 에서 「축을 만들고 지산지소의 기본값은 집 우선으로
    두라」로 답했다 — **가정이 아니라 사용자 판정이 이 기본값을 정한다.**
    `tests/casegrid/test_pv_surplus_allocation_priority.py` 가 두 갈래를 각각
    붙든다.
    """
    # `case_values` 는 `dict[str, object]` 다(케이스 그리드가 변수 종류를 섞어
    # 담는 자리라 값 타입을 하나로 좁힐 수 없다) — 그래서 아래 `cast` 셋은
    # **런타임 변환이 아니라 타입 단정**이다. 실제 검증은 `ESS` 와
    # `resolve_pv_allocation_priority()` 가 한다.
    mode = cast(
        "ESSOperatingMode | str",
        ess_operating_mode
        if ess_operating_mode is not None
        else case_values.get("ess_operating_mode", ESS_OPERATING_MODE_DEFAULT),
    )
    source = cast(
        "ESSChargeSource | str",
        ess_charge_source
        if ess_charge_source is not None
        else case_values.get("ess_charge_source", ESS_CHARGE_SOURCE_DEFAULT),
    )
    raw_priority = (
        pv_allocation_priority
        if pv_allocation_priority is not None
        else case_values.get("pv_allocation_priority", PV_ALLOCATION_PRIORITY_DEFAULT)
    )
    priority = resolve_pv_allocation_priority(cast("PVAllocationPriority | str", raw_priority))
    pv_dispatch = pv.dispatch(ctx)
    if priority is PVAllocationPriority.HOUSEHOLD_FIRST and household is not None:
        household_kwh = [-v for v in household.dispatch(ctx).electric]
        surplus_profile_kwh = [
            max(0.0, gen - load)
            for gen, load in zip(pv_dispatch.electric, household_kwh, strict=True)
        ]
    else:
        annual_generation_kwh = pv.annual_generation_kwh(year=1)
        surplus_ratio = (
            pv.surplus_kwh(year=1) / annual_generation_kwh if annual_generation_kwh > 0.0 else 0.0
        )
        surplus_profile_kwh = [v * surplus_ratio for v in pv_dispatch.electric]
    return mode, source, surplus_profile_kwh, priority


def measured_self_consumption_ratio(
    pv: PV, ctx: DispatchContext, surplus_profile_kwh: Sequence[float]
) -> float:
    """대표일 자가소비율 — 판정 §4 ⓑ(**실제 배분**). 리포트 0절 「자가소비율」
    칸의 실측치다.

    ⚠⚠ **이것은 `core/report/unreflected.py::_measured_quantities` 의
    ⓐ(**반사실** — 「자가소비했다면 얼마였을까」, `min(발전,부하)` 스텝합)와
    다른 값을 낸다.** 갈래가 `BATTERY_FIRST` 면 ⓑ 는 항등적으로 0 이고 ⓐ 는
    0 이 아니다 — 판정 §4 가 요구하는 것은 ⓑ 다(*「배터리 우선」 갈래에서도
    참이어야 한다 — 그 갈래의 실제 자가소비는 0 이므로 0% 가 맞다*). 두 값은
    공존하며 어느 쪽도 다른 쪽을 대신하지 않는다.

    자가소비 kWh = Σ(PV 스텝 발전) − Σ(그 실행의 PV 잉여 시계열). `surplus_
    profile_kwh` 는 `_resolve_ess_dispatch_inputs()` 의 셋째 반환값이며 **여기서
    다시 계산하지 않는다** — 새로 지으면 이 함수가 부른 갈래와 잉여를 만든
    갈래가 갈릴 수 있다.

    분자·분모 나눗셈은 `core.cba.metrics.self_consumption_rate`
    (`FR-703-AC1.self-consumption`)에 위임한다 — 그 함수가 이미 「발전 0 이면
    0」 규약과 오차 범위를 검사로 붙들고 있다(`tests/cba/test_indicators.py`).
    이 저장소가 그 함수를 배포 경로에서 부르는 첫 자리다.
    """
    generation_kwh = sum(pv.dispatch(ctx).electric)
    self_consumed_kwh = generation_kwh - sum(surplus_profile_kwh)
    return self_consumption_rate(self_consumed_kwh, generation_kwh)
