"""**PV 잉여의 배분 순서는 `PVAllocationPriority` 축이 고른다** — 그 갈래별
동작을 붙든다 (R50/WP-3 · R51/WP-1).

## 무엇을 붙드는가

러너가 짓는 `surplus_profile_kwh` 는 **PV 출력의 배분 순서를 정한다.** 정본
선언은 `e2e_runner._resolve_ess_dispatch_inputs` 독스트링에 있고 여기는 그
선언이 **동작과 같은지** 재는 자리다. 축은 셋이다 — `HOUSEHOLD_FIRST`(**지금
배포 기본값** · 사용자 판정 `docs/decisions-2026-09-01-R51.md` §1 이 `MC-1`
기본값으로 정했고 R51/WP-6 이 뒤집었다) · `BATTERY_FIRST`(그 전의 배포
기본값이며 지워지지 않았다 — 명시로 고를 수 있다) · `PRICE_BASED`(자리만 있고
거부됨, `tests/der/test_pv.py` 가 붙든다).

⚠ **아래 검사 전부가 갈래를 명시로 지정해 돌린다** — 그래서 배포 기본값이
어느 쪽이든 단언이 그대로 성립한다. 기본값 자체를 붙드는 것은 이 파일 맨
아래 `test_deployment_default_is_household_first` 하나이며, 그것만이 뒤집기에
반응한다.

`ESS._pv_surplus_charge_kwh_by_hour` 는 가구 부하를 보지 않는다 — 러너가 그
부하를 충전 계획에 넘기지 않기 때문이다(피크 저감에는 `_site_load_kw` 로
넘긴다). `BATTERY_FIRST` 에서는 그래서 **부하를 아무리 키워도 ② 의 몫은 줄지
않는다.** `HOUSEHOLD_FIRST` 는 정반대다 — 스텝별 실제 부하를 먼저 뺀 나머지만
ESS 로 가므로 부하가 크면 ESS 충전이 준다.

## ⚠ 왜 「잉여 합이 `pv.surplus_kwh()` 와 같은가」로 재지 않았는가

그것은 **같은 함수를 두 번 부른 것**이고, 이 저장소가 반복해 밟은 동어반복이다
(`status.md` 「함정」 절 — *「이 단언에 등장하는 값 중 몇 개를 검사 대상이 스스로
정하는가? 전부라면 동어반복이다」*). 대신 **입력 하나(가구 부하 총량)만 바꾼 두
실행을 견준다** — 단언에 쓰는 값은 두 실행이 각각 따로 내놓은 운전 결과이고,
어느 쪽도 다른 쪽을 정하지 않는다.

## ⚠ 단언이 **둘**인 이유 (갈래마다)

「부하를 키우면 ESS 충전이 달라진다(또는 안 달라진다)」만으로는 **「부하가
아예 반영되지 않는다」와 구별되지 않는다.** 그래서 같은 두 실행에서 **계통
수전도 함께** 잰다 — `BATTERY_FIRST` 는 수전이 늘어야 하고, `HOUSEHOLD_FIRST`
는 그 증가분이 `BATTERY_FIRST` 보다 작아야 한다(가구가 PV 로 스스로 채운
몫만큼 계통에서 덜 산다).

## `req("FR-302-AC1")` 마커는 「집 우선」에만 단다 (R51 갱신)

`FR-302-AC1` 의 7단계 우선순위 ① 은 *「즉시」* 자가소비(그 스텝의 실제 부하)다.
`HOUSEHOLD_FIRST` 는 정확히 그 뜻으로 구현했으므로 마커를 단다.
`BATTERY_FIRST` 는 여전히 **연간 고정 비율**이라 ① 의 뜻이 조항과 어긋난다 —
그 어긋남은 `_resolve_ess_dispatch_inputs` 독스트링이 적어 둔다. 마커를 달면
매핑표가 그 조항을 「검증됨」으로 세는데, `BATTERY_FIRST` 검사가 재는 것은
조항의 ① 이 아니라 **그 갈래가 실제로 하는 순서**이므로 달지 않는다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.casegrid.e2e_runner import DAYS_PER_YEAR, run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.models import CaseOutcome
from core.casegrid.profiles import load_daily_shapes
from core.der.pv import PVAllocationPriority
from core.report.dispatch_notes import build_hourly_profile
from core.report.unreflected import _measured_quantities

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_ESS = "e2e-ess"
_LOAD = "e2e-load"

#: 부하 0 인 케이스도 **부하 자원을 세운다** — 총량만 0 이다. 자원 구성을 같게
#: 두어야 두 실행의 차이가 「부하의 크기」 하나로 좁혀진다(자원이 하나 없어지면
#: 「없어서 달라졌다」와 「앞서서 달라졌다」를 가를 수 없다).
_NO_LOAD_KWH = 0.0
#: 가구 10호분(3,600kWh/호·년 · 대장 `load.household.annual` 의 가정값). PV 연간
#: 발전량을 넘도록 크게 잡는다 — 넘지 않으면 「잉여가 넉넉해서 부하와 다투지
#: 않았다」로도 통과한다. ⚠ **`BATTERY_FIRST` 전용이다** — 이 갈래는 household
#: 를 전혀 보지 않으므로(연간 고정 비율) 이 값이 아무리 커도 안전하다.
_HEAVY_LOAD_KWH = 36_000.0
#: **갈래를 견주는(집 우선을 포함하는) 검사 전용** — `_HEAVY_LOAD_KWH` 를 쓸 수
#: 없다(실측). 그만큼 부하가 크면 「집 우선」에서 대표일 24시간 내내 PV 출력을
#: 가구가 다 가져가 잉여가 통째로 0 이 되고, `ESS`(충전원 기본값 `PV_SURPLUS`)
#: 가 「충전원이 태양광 잉여인데 잉여 시계열이 전부 0」이라며 그 조합을
#: 거부한다 — 실행이 아예 서지 못한다. 대표일에 잉여가 일부라도 남는 한도
#: 안에서 고른 값이다(가구 2호분 · §7 오케스트레이터가 볼 것).
_CROSS_PRIORITY_LOAD_KWH = 7_200.0


def _run(
    annual_load_kwh: float | None, *, priority: PVAllocationPriority | None
) -> CaseOutcome:
    """`priority=None` 은 **아무것도 지정하지 않은 실행** — 배포 기본값이 쓰인다."""
    return run_single_case_e2e(
        {},
        level_map=build_level_map(_ASSUMPTIONS),
        horizon_years=20,
        daily_shapes=load_daily_shapes(),
        annual_load_kwh=annual_load_kwh,
        pv_allocation_priority=priority,
    )


def _annual_ess_charge_kwh(outcome: CaseOutcome) -> float:
    """ESS 의 **연간 충전량**(kWh) — 대표일 운전 결과의 음수분(= 충전)을 연간화한다.

    ⚠ `ESS.annual_charge_kwh()` 를 부르지 않는다. 그것은 자원이 스스로 내놓는
    **계획**이고, 여기서 재려는 것은 러너가 실제로 실은 **운전 결과**다.
    """
    electric = outcome.dispatch.per_resource[_ESS].electric
    return -sum(v for v in electric if v < 0.0) * DAYS_PER_YEAR


def _annual_grid_import_kwh(outcome: CaseOutcome) -> float:
    return sum(outcome.dispatch.grid_import) * DAYS_PER_YEAR


def _annual_grid_export_kwh(outcome: CaseOutcome) -> float:
    return sum(outcome.dispatch.grid_export) * DAYS_PER_YEAR


def _pv_resource_line(outcome: CaseOutcome):
    """리포트 0절이 실제로 실은 PV 행 — 실물 문면을 붙드는 검사가 여기서 읽는다."""
    return next(line for line in outcome.basis.resources if line.name == "e2e-pv")


def _self_consumption_ratio_pct(outcome: CaseOutcome) -> int:
    """PV 행의 `capacity` 문면에서 「자가소비율 N%」 를 그대로 읽는다.

    ⚠ **재계산하지 않는다** — 검사 대상은 *리포트가 인쇄한 문자열*이지 별도
    계산이 아니다. 재계산하면 이 검사와 배포 코드가 같은 도우미를 불러 같은
    답을 내는 동어반복이 된다(`status.md` 「함정」 절).
    """
    match = re.search(r"자가소비율 (\d+)% \(본 실행 실측\)", _pv_resource_line(outcome).capacity)
    assert match is not None, (
        f"PV 행 capacity 에 「자가소비율 N% (본 실행 실측)」 문면이 없다: "
        f"{_pv_resource_line(outcome).capacity!r}"
    )
    return int(match.group(1))


def test_both_priorities_stand_the_load_resource() -> None:
    """★ 성립 조건 — 부하를 준 실행은 갈래·부하 크기와 무관하게 부하 자원을 세운다.

    이것이 거짓이면 아래 검사들은 「부하가 있는 실행 vs 없는 실행」을 견주는
    것이 되고, 그때 「충전량이 같다/다르다」는 우선순위가 아니라 **자원 구성**을
    잰 것이 된다.
    """
    for priority in (PVAllocationPriority.BATTERY_FIRST, PVAllocationPriority.HOUSEHOLD_FIRST):
        for load_kwh in (_NO_LOAD_KWH, _CROSS_PRIORITY_LOAD_KWH):
            outcome = _run(load_kwh, priority=priority)
            assert _LOAD in outcome.dispatch.per_resource, (
                f"{priority.value}·부하 {load_kwh}kWh 인데 부하 자원이 서지 않았다"
            )


def test_battery_first_ess_charge_does_not_yield_to_household_demand() -> None:
    """★★ 배터리 우선 — ② 가 가구의 추가 수요보다 **앞선다**.

    가구 부하를 0 에서 10호분으로 올려도 ESS 가 받아 가는 연간 kWh 는 **한
    kWh 도 줄지 않는다.** 충전 계획(`ESS._pv_surplus_charge_kwh_by_hour`)이
    보는 것은 PV 잉여뿐이고, 그 잉여는 가구가 무엇을 쓰든 그대로이기 때문이다.

    ⚠ **이 단언은 「그래야 한다」가 아니라 「지금 그렇다」다.** R51/WP-6 이
    배포 기본값을 `HOUSEHOLD_FIRST` 로 뒤집었으므로 **이 검사가 지금 붙드는
    것은 「명시로 고르면 여전히 이 동작이 나오는가」**다 — 그 좁혀짐은 WP-1 이
    이 자리에 미리 적어 둔 것이며, 갈래가 지워지지 않았다는 증인이기도 하다.
    """
    quiet = _annual_ess_charge_kwh(
        _run(_NO_LOAD_KWH, priority=PVAllocationPriority.BATTERY_FIRST)
    )
    heavy = _annual_ess_charge_kwh(
        _run(_HEAVY_LOAD_KWH, priority=PVAllocationPriority.BATTERY_FIRST)
    )
    assert quiet > 0.0, f"부하 0 인 실행에서 ESS 충전이 {quiet}kWh 다 — 견줄 것이 없다"
    assert heavy == pytest.approx(quiet), (
        f"배터리 우선에서 가구 부하를 {_HEAVY_LOAD_KWH:,.0f}kWh 로 올리자 ESS 연간 충전이 "
        f"{quiet:,.4f} → {heavy:,.4f}kWh 로 움직였다. 우선순위가 바뀌었다면 "
        "`_resolve_ess_dispatch_inputs` 독스트링의 선언을 함께 고쳐야 한다 — "
        "선언과 동작이 갈리면 다음 사람이 문면을 믿는다"
    )


def test_battery_first_household_demand_lands_on_grid_import_instead() -> None:
    """★★ 배터리 우선 — 밀려난 수요는 **계통 수전**으로 간다.

    앞 검사만으로는 *「부하를 아예 계산에 넣지 않았다」* 도 통과한다. 같은 두
    실행에서 **계통 수전이 실제로 늘어나는지**를 함께 재어 그 갈래를 막는다.
    """
    quiet = _run(_NO_LOAD_KWH, priority=PVAllocationPriority.BATTERY_FIRST)
    heavy = _run(_HEAVY_LOAD_KWH, priority=PVAllocationPriority.BATTERY_FIRST)
    quiet_import = _annual_grid_import_kwh(quiet)
    heavy_import = _annual_grid_import_kwh(heavy)
    assert heavy_import > quiet_import, (
        f"배터리 우선에서 가구 부하를 {_HEAVY_LOAD_KWH:,.0f}kWh 로 올렸는데 계통 수전이 "
        f"{quiet_import:,.4f} → {heavy_import:,.4f}kWh 로 늘지 않았다 — 부하가 "
        "운전에 반영되지 않았을 수 있다"
    )
    assert _annual_grid_export_kwh(heavy) < _annual_grid_export_kwh(quiet), (
        "부하가 늘었는데 계통 역송이 줄지 않았다 — ③ 이 잔여분이 아니게 됐다"
    )


@pytest.mark.req("FR-302-AC1")
def test_household_first_ess_charge_yields_to_household_demand() -> None:
    """★★ 집 우선 — ESS 충전이 가구의 추가 수요에 **밀린다**(판정 §1·④, 거울 단언).

    배터리 우선과 정반대다: 가구 부하가 커지면 그 스텝의 실제 부하를 먼저 채우고
    남는 잉여만 ESS 로 가므로, ESS 연간 충전이 **줄어야** 한다(같으면 안 된다 —
    같으면 배터리 우선과 구별되지 않는다).
    """
    quiet = _annual_ess_charge_kwh(
        _run(_NO_LOAD_KWH, priority=PVAllocationPriority.HOUSEHOLD_FIRST)
    )
    heavy = _annual_ess_charge_kwh(
        _run(_CROSS_PRIORITY_LOAD_KWH, priority=PVAllocationPriority.HOUSEHOLD_FIRST)
    )
    assert quiet > 0.0, f"부하 0 인 실행에서 ESS 충전이 {quiet}kWh 다 — 견줄 것이 없다"
    assert heavy < quiet, (
        f"집 우선에서 가구 부하를 {_CROSS_PRIORITY_LOAD_KWH:,.0f}kWh 로 올렸는데 ESS 연간 "
        f"충전이 {quiet:,.4f} → {heavy:,.4f}kWh 로 줄지 않았다 — 배터리 우선과 구별되지 않는다"
    )


@pytest.mark.req("FR-302-AC1")
def test_household_first_grid_import_increases_less_than_battery_first() -> None:
    """★★ 집 우선의 계통 수전 증가분이 배터리 우선보다 **작다**(판정 §1·④, 거울 단언).

    집 우선은 가구가 늘어난 부하 중 일부를 자기 PV 로 스스로 채우므로, 부하를
    0 → 10호분으로 올렸을 때의 **계통 수전 증가분**이 배터리 우선보다 작아야
    한다. 두 갈래의 증가분을 직접 견주어 「부하가 커져도 배터리 우선과 똑같이
    전량 계통에서 산다」를 가른다.
    """
    battery_quiet = _run(_NO_LOAD_KWH, priority=PVAllocationPriority.BATTERY_FIRST)
    battery_heavy = _run(_CROSS_PRIORITY_LOAD_KWH, priority=PVAllocationPriority.BATTERY_FIRST)
    household_quiet = _run(_NO_LOAD_KWH, priority=PVAllocationPriority.HOUSEHOLD_FIRST)
    household_heavy = _run(_CROSS_PRIORITY_LOAD_KWH, priority=PVAllocationPriority.HOUSEHOLD_FIRST)

    battery_increase = _annual_grid_import_kwh(battery_heavy) - _annual_grid_import_kwh(
        battery_quiet
    )
    household_increase = _annual_grid_import_kwh(household_heavy) - _annual_grid_import_kwh(
        household_quiet
    )
    assert household_increase < battery_increase, (
        f"집 우선의 계통 수전 증가분({household_increase:,.4f}kWh)이 배터리 우선"
        f"({battery_increase:,.4f}kWh)보다 작지 않다 — 가구가 자기 PV 로 채운 몫이 없다"
    )


def test_household_none_priority_is_irrelevant() -> None:
    """★ `household` 가 없으면(`annual_load_kwh` 를 아예 안 준 실행) 두 갈래가
    **완전히 같다**(판정 §1·④) — 채울 집이 없으니 우선순위가 있으나 마나다.
    """
    battery = _run(None, priority=PVAllocationPriority.BATTERY_FIRST)
    household = _run(None, priority=PVAllocationPriority.HOUSEHOLD_FIRST)
    assert _LOAD not in battery.dispatch.per_resource, "부하를 안 줬는데 부하 자원이 섰다"
    assert _annual_ess_charge_kwh(household) == pytest.approx(_annual_ess_charge_kwh(battery)), (
        "household=None 인데 ESS 연간 충전이 갈래별로 다르다"
    )
    assert _annual_grid_import_kwh(household) == pytest.approx(
        _annual_grid_import_kwh(battery)
    ), "household=None 인데 계통 수전이 갈래별로 다르다"
    assert _annual_grid_export_kwh(household) == pytest.approx(
        _annual_grid_export_kwh(battery)
    ), "household=None 인데 계통 역송이 갈래별로 다르다"


@pytest.mark.req("FR-302-AC1")
def test_deployment_default_is_household_first() -> None:
    """★★★ **배포 기본값이 「집 우선」이다** (사용자 판정 §1 · R51/WP-6).

    ## 왜 상수를 읽어 견주지 않는가

    `PV_ALLOCATION_PRIORITY_DEFAULT is PVAllocationPriority.HOUSEHOLD_FIRST`
    는 **선언이 선언과 같은지**를 물을 뿐이다 — 러너가 그 상수를 읽지 않게
    되는 날에도 초록불이다(이 저장소가 「선언은 있는데 읽는 쪽이 없다」로
    네 번 만난 형태다). 그래서 **아무것도 지정하지 않은 실행**을 두 갈래를
    명시로 지정한 실행과 각각 견준다 — 기본값과 같은 갈래의 운전이 나오고,
    다른 갈래와는 실제로 갈리는지를 함께 본다.

    ## ⚠ 갈래가 갈리는 것도 함께 단언하는 이유

    「기본 실행 == 집 우선」만 재면 **두 갈래가 우연히 같은 수를 내는 케이스**
    에서도 통과한다(부하가 없거나 잉여가 넉넉하면 실제로 같다 — 같은 파일의
    `test_household_none_priority_is_irrelevant` 가 그 경우를 잰다). 그러면
    누가 기본값을 되돌려도 이 검사가 아무 말을 하지 않는다.
    """
    default_run = _run(_CROSS_PRIORITY_LOAD_KWH, priority=None)
    household = _run(_CROSS_PRIORITY_LOAD_KWH, priority=PVAllocationPriority.HOUSEHOLD_FIRST)
    battery = _run(_CROSS_PRIORITY_LOAD_KWH, priority=PVAllocationPriority.BATTERY_FIRST)

    assert _annual_ess_charge_kwh(battery) != pytest.approx(
        _annual_ess_charge_kwh(household)
    ), (
        "이 부하에서 두 갈래가 같은 운전을 낸다 — 그러면 아래 단언이 기본값을 "
        "붙들지 못한다. `_CROSS_PRIORITY_LOAD_KWH` 를 갈래가 갈리는 값으로 고쳐라"
    )
    assert _annual_ess_charge_kwh(default_run) == pytest.approx(
        _annual_ess_charge_kwh(household)
    ), (
        "갈래를 지정하지 않은 실행이 「집 우선」과 다른 ESS 충전을 냈다 — 배포 "
        "기본값(`core/casegrid/pv_allocation.py::PV_ALLOCATION_PRIORITY_DEFAULT`)이 "
        "사용자 판정 §1(「지산지소 모델은 집에서 우선 사용」)과 어긋난다"
    )
    assert _annual_grid_import_kwh(default_run) == pytest.approx(
        _annual_grid_import_kwh(household)
    ), "갈래를 지정하지 않은 실행이 「집 우선」과 다른 계통 수전을 냈다"


# ── 판정 §4 — 「자가소비율」은 본 실행 실측치이지 모듈 상수가 아니다 ──────────
#
# 여기서 재는 것은 ⓑ(**실제 배분** — 이 실행에서 집이 실제로 얼마를 썼나)다.
# ⓐ(**반사실** — 「자가소비했다면 얼마였을까」, `core/report/unreflected.py::
# _measured_quantities`)와는 값이 다르고 공존한다 — `pv_allocation.
# measured_self_consumption_ratio` 독스트링 참조.


@pytest.mark.req("FR-703-AC1.self-consumption")
def test_household_first_self_consumption_ratio_is_measured_and_nonzero() -> None:
    """★★★ 「집 우선」 — 리포트 0절의 자가소비율이 0% 가 아니다.

    R51 이 「집 우선」을 기본값으로 만든 뒤에도 이 칸은 계속 `PV_SELF_
    CONSUMPTION_RATIO`(모듈 상수, = 0)를 인쇄해 왔다 — 가구가 그 스텝의
    태양광을 실제로 먼저 쓰는데도 표시는 0% 였다(판정 §4). 그 결함이 남아
    있으면 이 단언이 실패한다.
    """
    outcome = _run(_CROSS_PRIORITY_LOAD_KWH, priority=PVAllocationPriority.HOUSEHOLD_FIRST)
    ratio_pct = _self_consumption_ratio_pct(outcome)
    assert ratio_pct > 0, (
        f"집 우선인데 자가소비율이 {ratio_pct}% 다 — 모듈 상수를 계속 읽고 "
        "있을 수 있다(판정 §4)"
    )


@pytest.mark.req("FR-703-AC1.self-consumption")
def test_battery_first_self_consumption_ratio_is_exactly_zero() -> None:
    """★★★ 「배터리 우선」 — 자가소비율이 **정확히 0%** 다(판정 §4 ⚠).

    갈래마다 값이 갈리는 것이 옳은 동작이다 — 판정 문면이 못 박았다:
    *「「배터리 우선」 갈래에서도 참이어야 한다 — 그 갈래의 실제 자가소비는
    0 이므로 0% 가 맞다」*. `_measured_quantities`(ⓐ, 반사실)로 재면 이
    갈래에서도 0 이 아닌 값이 나온다 — 그것과 혼동하면 거짓 표시가 된다.
    """
    outcome = _run(_CROSS_PRIORITY_LOAD_KWH, priority=PVAllocationPriority.BATTERY_FIRST)
    ratio_pct = _self_consumption_ratio_pct(outcome)
    assert ratio_pct == 0, (
        f"배터리 우선인데 자가소비율이 {ratio_pct}% 다 — 그 갈래는 가구가 PV 를 "
        "한 kWh 도 못 쓰고 전부 계통 수전으로 메워진다(`pv_allocation` 독스트링)"
    )


@pytest.mark.req("FR-703-AC1.self-consumption")
def test_household_first_self_consumption_ratio_matches_unreflected_layer() -> None:
    """★★ 층을 건너 대조한다 — 붙임 8 의 자가소비 수량(ⓐ 자료 원천)과 리포트
    0절의 자가소비율 × PV 발전량(ⓑ)이 **같아야 한다** (`HOUSEHOLD_FIRST` 한정).

    ⚠ 이 갈래에서는 ⓐ(`min(발전,부하)` 반사실)와 ⓑ(발전 − 잉여, 실제 배분)가
    **수치로 같다** — 가구가 그 스텝에 쓸 수 있는 만큼 실제로 쓰기 때문이다
    (`_resolve_ess_dispatch_inputs` 독스트링의 `HOUSEHOLD_FIRST` 절 참조).
    `BATTERY_FIRST` 에서는 둘이 다르므로(ⓐ ≠ 0, ⓑ = 0) 여기서 견주지 않는다.

    ⚠⚠ **동어반복이 아니다** — 두 값을 각각 다른 자리에서 읽는다: ⓐ 는
    `core/report/unreflected.py::_measured_quantities`(대표일 시간대별 운전
    결과에서 `min(발전,부하)` 를 스텝마다 합산)로, ⓑ 는 리포트 0절이 실제로
    인쇄한 퍼센트 문자열(`_self_consumption_ratio_pct`)에 **실제 PV 운전
    결과**(`outcome.dispatch.per_resource["e2e-pv"]`)의 발전량을 곱해 얻는다 —
    어느 쪽도 `pv_allocation.measured_self_consumption_ratio` 를 다시 부르지
    않는다.
    """
    outcome = _run(_CROSS_PRIORITY_LOAD_KWH, priority=PVAllocationPriority.HOUSEHOLD_FIRST)
    hours = build_hourly_profile(outcome.dispatch)
    measured = _measured_quantities(hours)
    assert measured is not None, "부하 자원이 서지 않아 ⓐ 를 잴 수 없다"

    generation_kwh = sum(outcome.dispatch.per_resource["e2e-pv"].electric)
    ratio_pct = _self_consumption_ratio_pct(outcome)
    implied_self_consumption_kwh = generation_kwh * ratio_pct / 100

    # 표시가 정수 %로 반올림되므로 최대 오차는 발전량의 0.5%다 — 여유를 두어
    # 판정한다(실제 어긋남을 가리지 않을 만큼 좁게).
    tolerance_kwh = 0.006 * generation_kwh + 1e-6
    assert implied_self_consumption_kwh == pytest.approx(
        measured.self_consumption, abs=tolerance_kwh
    ), (
        f"붙임 8 자가소비(ⓐ) {measured.self_consumption:,.4f}kWh/일 과 "
        # RUF001: 「×」는 사람이 읽는 산식 문면이다 — `x` 로 바꾸면 곱셈이 변수
        # 이름으로 읽힌다(`core/casegrid/operating_lines.py` 가 세운 규약).
        f"리포트 0절 자가소비율({ratio_pct}%) × PV 발전량({generation_kwh:,.4f}kWh/일) = "  # noqa: RUF001
        f"{implied_self_consumption_kwh:,.4f}kWh/일 이 다르다"
    )


def test_pv_operating_mode_shows_declaration_and_actual_allocation() -> None:
    """★★ 「운전 방식」 칸 — 선언(`전량 판매`)과 본 실행 배분 순서를 함께 적는다
    (판정 §4 나-4). 두 값이 달라 보이는 것은 결함이 아니라 같은 뿌리다.
    """
    for priority in (PVAllocationPriority.HOUSEHOLD_FIRST, PVAllocationPriority.BATTERY_FIRST):
        outcome = _run(_CROSS_PRIORITY_LOAD_KWH, priority=priority)
        operating_mode = _pv_resource_line(outcome).operating_mode
        assert "전량 판매" in operating_mode and "(선언)" in operating_mode, (
            f"{priority.value}: 선언값(전량 판매)이 「운전 방식」 칸에서 사라졌다: "
            f"{operating_mode!r}"
        )
        assert f"본 실행 배분: {priority.value}" in operating_mode, (
            f"{priority.value} 로 돌렸는데 「운전 방식」 칸이 그 배분을 보이지 "
            f"않는다: {operating_mode!r}"
        )
