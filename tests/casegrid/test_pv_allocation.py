"""**기준선 갈래가 잉여 시계열을 가르고, 배분 순서 축은 건드리지 않는다**
— `core/casegrid/pv_allocation.py::_dispatch_inputs_under_baseline` (FR-705-AC2 · R60/WP-2).

## 무엇을 붙드는가 — **감싸기의 성질**

R60/WP-2 가 기준선 갈래(`FR-705-AC2`)를 실행 경로에 배선하면서, 갈래가 계산을
가르는 지점을 **한 자리**로 모았다: `_resolve_ess_dispatch_inputs` 를 감싸
그것이 낸 **PV 잉여 시계열**을 갈래에 맞추는 함수다. 이 파일은 그 **감싸기**를
직접 잰다.

    F1  ⓐ(`NONE` · 자가용 없음)면 잉여가 **PV 출력 전량**이다   ← 자가소비가 0
    F2  ⓑ(`MAINTAIN` · 자가용 유지)면 **감싸기 전과 같다**      ← 손대지 않는다
    F3  ★ 갈래가 **배분 순서 축을 덮어쓰지 않는다**             ← 두 축은 뿌리가 다르다

★★ **F3 가 요점이다.** ⓐ 의 잉여는 `BATTERY_FIRST`(자가소비율 0 이므로 잉여
비율 1.0)로 갈아 끼워도 **우연히 같은 수가 된다.** 그렇게 구현하면 F1·F2 는
초록불인데 리포트가 *이 실행이 고르지 않은* 배분 순서를 인쇄한다 — 「자가소비
처리」와 「낮 전기를 누가 먼저 가져가는가」는 뿌리가 다른 축이고(하나는 **사업
구조**, 하나는 **배분 규칙**), 그 혼동은 아무 예외도 내지 않는다. 그 위험을
`_dispatch_inputs_under_baseline` 독스트링이 적어 두었으며 여기가 그것을 잰다.

## ⚠ 왜 비공개 이름을 시험이 **직접** 부르는가

이 저장소의 `tests/casegrid/` 는 배분 순서 축을 **진입점으로** 잰다
(`test_pv_surplus_allocation_priority.py` — `run_single_case_e2e` 를 돌려
ESS 충전량·계통 수전을 견준다). 그 관례가 옳은 이유는 그 파일이 재는 것이
*축의 동작*이고 동작은 진입점에서 관측되기 때문이다.

**여기서 재는 것은 동작이 아니라 감싸기다.** F2(*「감싸기가 ⓑ 를 손대지
않는다」*)와 F3(*「넷째 반환값이 그대로다」*)는 **그 함수가 돌려주는 튜플의
성질**이며 진입점에서는 관측되지 않는다 — ⓑ 의 동작 불변은 이미 골든 3건이
잡고(무보조 `npv` −11,537,129원 불변), 진입점에서 다시 재면 같은 것을 두 곳에서
재게 된다.

그래서 **비공개 이름을 직접 부른다.** 이 저장소에 이미 있는 관례이며 같은
이유로 쓰인다 — `tests/report/test_unreflected.py` 계열이
`core.report.unreflected._measured_quantities` 를,
`tests/report/test_case_influences.py` 가 `case_influences._Sweeper` 를,
`tests/report/test_case_report.py` 가 `_overrides`·`_scheme_for` 를 직접
부른다(**바로 그 함수의 성질**을 재는 자리들이다).

## ⚠ 왜 `test_pv_surplus_allocation_priority.py` 에 얹지 않았나

그 파일의 머리말이 자기 대상을 *「러너가 짓는 `surplus_profile_kwh` 의 배분
순서 갈래별 **동작**」* 으로 못 박고, 모든 검사가 `run_single_case_e2e` 를
돌린다. 감싸기를 직접 부르는 검사를 그 안에 넣으면 그 머리말이 거짓이 되고
층이 둘 섞인다. 파일 이름도 게이트 ②(`NFR-105-M2`)가 인정하는 규약
(`tests/<구획>/test_<stem>.py`)에 맞는 쪽이 `test_pv_allocation.py` 다.

⚠ **ⓒ(`FORFEIT` · 자가용 집합자원화) 거부는 여기서 재지 않는다** — 리포트·러너
두 진입점에서 `tests/report/test_baseline_arrangement_wiring.py` 의 T3 이
이미 잰다. 같은 것을 두 곳에서 재면 한쪽만 고쳐진다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.casegrid.e2e_runner import (
    DAYS_PER_YEAR,
    HOURS_PER_YEAR,
    PRICE_ESCALATION_RATE,
    PV_CAPACITY_FACTOR,
    PV_SELF_CONSUMPTION_RATIO,
    SECONDS_PER_HOUR,
    STEPS_PER_DAY,
    _household_load_if_total_given,
)
from core.casegrid.profiles import load_daily_shapes
from core.casegrid.pv_allocation import (
    _dispatch_inputs_under_baseline,
    _resolve_ess_dispatch_inputs,
)
from core.cba.baseline import BaselineArrangement
from core.contracts.der import DispatchContext
from core.contracts.units import Year
from core.der.load import Load
from core.der.pv import PV, OperatingMode, PVAllocationPriority

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: 탐침 용량(kW). **대장을 읽지 않는다** — 이 파일이 재는 것은 금액이 아니라
#: 감싸기이고, 대장값을 베끼면 대장이 바뀔 때 여기가 따라오지 않아도 아무 일이
#: 없다(`test_e2e_analysis_period_wiring.py` 머리의 「탐침값」 규약 그대로).
_PROBE_PV_KW = 3.0

#: 가구 연간 사용량(kWh) — **0 이 아닌 것이 이 파일의 전제다.**
#:
#: ⚠⚠ `household` 가 `None` 이거나 부하가 0 이면 `HOUSEHOLD_FIRST` 가 뺄 것이
#: 없어 잉여가 **PV 출력 전량**이 되고, 그러면 ⓐ 와 ⓑ 가 같은 수를 내
#: **F1 이 항등적으로 통과한다**(아무것도 붙들지 않는다). 그래서 아래 F1 이
#: 두 갈래가 실제로 갈리는지를 **먼저** 단언한다.
#:
#: 크기는 대표일에 잉여가 **일부라도 남는** 한도에서 골랐다 — 잉여가 통째로 0
#: 이면 이번에는 ⓑ 쪽이 「전부 0」이 되어 대조가 다시 죽는다.
_PROBE_LOAD_KWH = 3_600.0


def _probe_pv() -> PV:
    """탐침 PV — **배포 경로와 같은 방식**으로 세운다(대표일 발전 형상 + 이용률).

    형상을 주는 이유는 `run_single_case_e2e` 가 그렇게 세우기 때문이다 — 형상
    없이 이용률만 주면 24스텝 균등 배분이 되어 **심야에도 발전**하고, 그 구성
    위에서 「집 우선이 낮 부하를 먼저 뺀다」를 재면 실물과 다른 사업을 재게 된다
    (붙임 8 「일중 발전 프로파일」이 같은 어긋남을 적어 두었다).
    """
    shapes = load_daily_shapes()
    return PV(
        name="probe-pv",
        capacity_kw=_PROBE_PV_KW,
        capacity_factor=None,
        generation_profile_kwh=shapes.generation.spread(
            _PROBE_PV_KW * PV_CAPACITY_FACTOR * HOURS_PER_YEAR, days=DAYS_PER_YEAR
        ),
        unit_capex_won_per_kw=1,
        fixed_om_won_per_year=0,
        escalation_rate=PRICE_ESCALATION_RATE,
        # ★ **러너와 같은 값(0.0)이다** — 이 상수가 0 인 채로도 갈래가 갈려야
        # 한다는 것이 이 파일의 요점이다. 「자가소비 비율을 0 으로 만든다」로는
        # ⓐ 가 서지 않고(이미 0 이다) 잉여 시계열 자체를 갈래에 맞춰야 한다.
        self_consumption_ratio=PV_SELF_CONSUMPTION_RATIO,
        operating_mode=OperatingMode.FULL_EXPORT,
    )


def _probe_household() -> Load:
    """탐침 가구 부하 — **러너와 같은 생성자**로 만든다.

    손으로 `Load(...)` 를 짓지 않는 이유는 그것이 러너의 사본이 되기 때문이다
    (형상·물가 계수 인자가 갈리면 이 파일이 다른 부하를 재게 된다).
    """
    household = _household_load_if_total_given(
        load_daily_shapes(), _PROBE_LOAD_KWH
    )
    assert household is not None, "총량을 주었는데 부하가 서지 않았다"
    return household


def _ctx() -> DispatchContext:
    return DispatchContext(steps=STEPS_PER_DAY, dt=SECONDS_PER_HOUR, year=Year(1))


def _surplus(
    arrangement: BaselineArrangement,
    *,
    priority: PVAllocationPriority,
) -> tuple[list[float], PVAllocationPriority]:
    """그 갈래·그 배분 순서로 감싸기를 부르고 (잉여 시계열, 넷째 반환값)을 낸다."""
    _mode, _source, surplus, resolved = _dispatch_inputs_under_baseline(
        None,
        None,
        {},
        _probe_pv(),
        _ctx(),
        pv_allocation_priority=priority,
        household=_probe_household(),
        baseline_arrangement=arrangement,
    )
    return surplus, resolved


@pytest.mark.req("FR-705-AC2")
def test_the_no_own_plant_branch_makes_the_whole_pv_output_surplus() -> None:
    """**F1** — ⓐ(`NONE` · 자가용 없음)면 잉여가 **PV 출력 전량**이다.

    전기사용자에게 자가용 설비가 없으므로 낮 전기 중 **가구가 먼저 가져가는
    몫이 없다.** 가구가 쓰는 전력은 자가소비가 아니라 분산e사업자로부터의
    **구매**이며 그 화폐화는 요금 엔진의 몫이다.

    ⚠⚠ **두 갈래가 실제로 갈리는지를 먼저 단언한다.** 부하가 0 이거나
    `household` 가 `None` 이면 `HOUSEHOLD_FIRST` 도 뺄 것이 없어 잉여가 전량이
    되고, 그때 이 검사는 **항등적으로 통과**한다 — 「같다」를 재는 검사는 비교
    대상이 원래 같으면 아무것도 붙들지 못한다(`_PROBE_LOAD_KWH` 주석).
    """
    pv = _probe_pv()
    full_output = list(pv.dispatch(_ctx()).electric)

    none_surplus, _ = _surplus(
        BaselineArrangement.NONE, priority=PVAllocationPriority.HOUSEHOLD_FIRST
    )
    maintain_surplus, _ = _surplus(
        BaselineArrangement.MAINTAIN, priority=PVAllocationPriority.HOUSEHOLD_FIRST
    )

    assert none_surplus != maintain_surplus, (
        "ⓐ 와 ⓑ 의 잉여 시계열이 같다 — 탐침 부하가 잉여를 깎지 못했다는 뜻이고, "
        "그러면 아래 단언이 항등적으로 통과해 아무것도 붙들지 못한다"
    )
    assert none_surplus == pytest.approx(full_output), (
        "ⓐ 인데 잉여가 PV 출력 전량이 아니다 — 자가용이 없으므로 가구가 먼저 "
        f"가져가는 몫이 0 이어야 한다. 잉여합 {sum(none_surplus):.3f}kWh · "
        f"발전합 {sum(full_output):.3f}kWh"
    )


@pytest.mark.req("FR-705-AC2")
def test_the_maintain_branch_leaves_the_surplus_untouched() -> None:
    """**F2** — ⓑ(`MAINTAIN` · 자가용 유지)면 **감싸기 전과 같다.**

    ⓑ 는 자가소비가 Without·With **양쪽에 똑같이** 있어 차액에서 소거된다
    (판정 정본 `docs/decisions-2026-09-03-R57.md` §1 둘째). 그러므로 손댈 것이
    없고, 그 「손대지 않음」이 **골든 3건이 한 원도 안 움직인 이유**다
    (무보조 `npv` −11,537,129원 불변).

    오라클은 **감싸는 함수와 감싸이는 함수를 같은 인자로 나란히 부른 결과**다 —
    수를 손으로 적지 않는다(적으면 그 수가 배분 계산의 사본이 되고, 계산이
    바뀔 때 이 검사만 조용히 낡는다).
    """
    priority = PVAllocationPriority.HOUSEHOLD_FIRST
    _mode, _source, unwrapped, _resolved = _resolve_ess_dispatch_inputs(
        None,
        None,
        {},
        _probe_pv(),
        _ctx(),
        pv_allocation_priority=priority,
        household=_probe_household(),
    )

    wrapped, _ = _surplus(BaselineArrangement.MAINTAIN, priority=priority)

    assert wrapped == pytest.approx(unwrapped), (
        "ⓑ 인데 감싸기가 잉여 시계열을 바꿨다 — ⓑ 의 자가소비는 양쪽에 있어 "
        "소거되므로 손댈 것이 없다. 이 어긋남은 골든 3건을 움직인다"
    )


@pytest.mark.req("FR-705-AC2")
def test_the_branch_never_overwrites_the_allocation_priority() -> None:
    """**F3** ★ — 갈래가 **배분 순서 축을 덮어쓰지 않는다.**

    ⓐ 의 잉여는 `BATTERY_FIRST` 로 갈아 끼워도 **우연히 같은 수**가 된다
    (러너의 자가소비율이 0 이라 그 갈래의 잉여 비율이 1.0 이다 —
    `_resolve_ess_dispatch_inputs` 독스트링의 `BATTERY_FIRST` 절). 그렇게
    구현하면 F1·F2 는 초록불인데 **리포트가 이 실행이 고르지 않은 배분 순서를
    인쇄한다**(넷째 반환값이 리포트 2.1 「운전 방식」 칸으로 간다).

    두 축은 뿌리가 다르다 — 갈래는 **사업 구조**(자가용 설비를 어떻게 처리하나),
    배분 순서는 **낮 전기의 배분 규칙**(집이 먼저냐 배터리가 먼저냐)이다.
    한쪽이 다른 쪽을 덮으면 그 혼동은 아무 예외도 내지 않는다.

    ⚠ **두 값 모두 본다.** 한쪽만 보면 「항상 그 값을 돌려준다」는 구현이
    통과한다.
    """
    for priority in (
        PVAllocationPriority.HOUSEHOLD_FIRST,
        PVAllocationPriority.BATTERY_FIRST,
    ):
        for arrangement in (BaselineArrangement.NONE, BaselineArrangement.MAINTAIN):
            _surplus_kwh, resolved = _surplus(arrangement, priority=priority)
            assert resolved is priority, (
                f"갈래 {arrangement.value!r} 로 부르니 배분 순서가 "
                f"{priority!r} → {resolved!r} 로 바뀌었다 — 갈래가 배분 순서 "
                "축을 덮어썼다. 리포트가 고르지 않은 순서를 인쇄하게 된다"
            )
