"""**ESS 가 가구 수요를 보고 방전한다** — 배선 (R64/WP-6b · 사용자 요구 5).

R64/WP-6a 가 `core/der/ess_schedule.py` 에 방전 배분 갈래(고정 창 · 부하 추종)를
세웠으나 **러너가 그것을 한 번도 부르지 않았다** — 부하 시계열을 `ESS` 에 넘기는
통로가 없어 배포 실행은 종전대로 방전창 안에 균등 분배했다. 이 파일이 그 배선을
붙든다.

## 무엇을 재는가 — 다섯

    ① 배포 기본값이 「부하 추종」이다              사용자 요구 5 · 판정 ①
    ② 따라갈 수요가 없으면 「고정 창」으로 선다     판정 ①의 예외 · 조용하지 않다
    ③ **그 계절의** 부하를 그 계절 ESS 가 본다     판정 ②
    ④ 하루 방전 총량은 보존되고 배분만 바뀐다      결론축이 움직인 사유
    ⑤ 리포트가 *실행이 고른* 값을 인쇄한다         판정 ③

⚠ **결론축의 수를 여기서 못 박지 않는다.** 그 자리는
`fixtures/golden/scenario_*.yaml` 이며 두 곳에 적으면 한쪽만 갱신되는 날이 온다.
"""
from __future__ import annotations

import math
from itertools import pairwise
from pathlib import Path

import pytest

from core.casegrid.e2e_runner import (
    ESS_DISCHARGE_ALLOCATION_DEFAULT,
    run_single_case_e2e,
)
from core.casegrid.ess_build import build_case_ess
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.models import CaseOutcome
from core.casegrid.operating_lines import DAYS_PER_YEAR
from core.casegrid.profiles import load_daily_shapes
from core.casegrid.pv_allocation import resolve_ess_discharge_inputs
from core.casegrid.seasonal_dispatch import build_and_dispatch_case
from core.contracts.der import DispatchContext
from core.contracts.units import Year
from core.contracts.validation import ValidationError
from core.der.ess import ESSChargeSource, ESSOperatingMode
from core.der.ess_schedule import ESSDischargeAllocation
from core.der.load import Load

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_ESS = "e2e-ess"
_LOAD = "e2e-load"

#: 가구 한 호분(대장 `load.household.annual` 의 가정값). 골든이 도는 값이다.
_ONE_HOUSEHOLD_KWH = 3_600.0
#: 부하 자원은 서지만 **수요가 0** 인 실행 — 배분 순서 축의 대조군이 그렇게 돈다
#: (`tests/casegrid/test_pv_surplus_allocation_priority.py` 의 `_NO_LOAD_KWH`).
_ZERO_LOAD_KWH = 0.0

_CTX = DispatchContext(steps=24, dt=3_600, year=Year(1))


def _run(
    annual_load_kwh: float | None,
    *,
    allocation: ESSDischargeAllocation | str | None = None,
    case_values: dict[str, object] | None = None,
) -> CaseOutcome:
    """`allocation=None` 은 **아무것도 지정하지 않은 실행** — 사슬이 정한다."""
    return run_single_case_e2e(
        case_values or {},
        level_map=build_level_map(_ASSUMPTIONS),
        horizon_years=20,
        daily_shapes=load_daily_shapes(),
        annual_load_kwh=annual_load_kwh,
        ess_discharge_allocation=allocation,
    )


def _ess_resource(outcome: CaseOutcome):
    return next(r for r in outcome.resources if r.name == _ESS)


def _ess_line(outcome: CaseOutcome):
    return next(line for line in outcome.basis.resources if line.name == _ESS)


def _discharge_by_step(outcome: CaseOutcome) -> list[float]:
    """대표일 스텝별 **방전분**(양수만) — 충전은 음수라 0 으로 접는다."""
    return [max(0.0, v) for v in outcome.dispatch.per_resource[_ESS].electric]


def _load_by_step(outcome: CaseOutcome) -> list[float]:
    return [-v for v in outcome.dispatch.per_resource[_LOAD].electric]


# ── ① 배포 기본값 ────────────────────────────────────────────────────────


def test_the_deployed_default_is_load_following() -> None:
    """★★ **기본 실행이 사용자 요구 5 를 만족한다** (판정 ①).

    ⛔ *「갈래로만 두고 기본값은 그대로」* 로 피하지 않았다는 것을 재는 자리다 —
    아무것도 지정하지 않은 실행이 「부하 추종」으로 서야 한다. 상수 하나만 보면
    *「상수는 바뀌었는데 러너가 안 읽는다」* 를 통과시키므로 **실행이 세운
    자원**에서 함께 읽는다(그 상태가 정확히 R64/WP-6a 가 남긴 상태였다).
    """
    assert ESS_DISCHARGE_ALLOCATION_DEFAULT is ESSDischargeAllocation.LOAD_FOLLOWING

    ess = _ess_resource(_run(_ONE_HOUSEHOLD_KWH))
    assert ess.discharge_allocation is ESSDischargeAllocation.LOAD_FOLLOWING
    assert ess.load_profile_kwh is not None, (
        "부하 추종으로 섰는데 부하 시계열이 자원에 실리지 않았다 — 배선이 끊겼다"
    )


def test_the_axis_follows_the_same_chain_as_the_other_three() -> None:
    """우선순위 사슬 — 호출 인자 → `case_values` → 모듈 상수.

    ⚠ **문자열도 받는다** (`FR-105-AC5` 관례). 케이스 그리드가 축을 문자열로
    건네므로 그 경로가 서지 않으면 화면·시나리오에서 이 축을 고를 수 없다.
    """
    by_argument = _ess_resource(_run(_ONE_HOUSEHOLD_KWH, allocation="고정 창"))
    assert by_argument.discharge_allocation is ESSDischargeAllocation.FIXED_WINDOW

    by_case_values = _ess_resource(
        _run(_ONE_HOUSEHOLD_KWH, case_values={"ess_discharge_allocation": "고정 창"})
    )
    assert by_case_values.discharge_allocation is ESSDischargeAllocation.FIXED_WINDOW

    # 인자가 `case_values` 를 이긴다.
    argument_wins = _ess_resource(
        _run(
            _ONE_HOUSEHOLD_KWH,
            allocation=ESSDischargeAllocation.LOAD_FOLLOWING,
            case_values={"ess_discharge_allocation": "고정 창"},
        )
    )
    assert argument_wins.discharge_allocation is ESSDischargeAllocation.LOAD_FOLLOWING


# ── ② 따라갈 수요가 없는 실행 ────────────────────────────────────────────


@pytest.mark.parametrize("annual_load_kwh", [None, _ZERO_LOAD_KWH])
def test_a_run_with_no_demand_to_follow_stands_on_the_fixed_window(
    annual_load_kwh: float | None,
) -> None:
    """부하 자원이 없거나 수요가 0 이면 **모듈 상수가 「고정 창」으로 떨어진다.**

    ⛔ 이것이 없으면 부하를 세우지 않는 실행(케이스 그리드·성능 측정)이 **전부
    거부된다** — *「가구 부하를 적지 않으면 사업을 평가할 수 없다」* 가 되고,
    그것은 요구 5 가 시킨 것보다 넓다.
    """
    ess = _ess_resource(_run(annual_load_kwh))
    assert ess.discharge_allocation is ESSDischargeAllocation.FIXED_WINDOW
    assert ess.load_profile_kwh is None


@pytest.mark.parametrize("annual_load_kwh", [None, _ZERO_LOAD_KWH])
def test_an_explicit_load_following_with_no_demand_is_rejected_not_downgraded(
    annual_load_kwh: float | None,
) -> None:
    """⛔ **명시로 고른 「부하 추종」은 떨어뜨리지 않는다.**

    수요가 없는데 부하 추종을 명시한 것은 설정 오류다. 조용히 고정 창으로
    되돌리면 리포트의 *「부하 추종으로 돌았다」* 가 거짓이 되고, 그 거짓은
    결과 어디에도 남지 않는다.
    """
    with pytest.raises(ValidationError) as caught:
        _run(annual_load_kwh, allocation=ESSDischargeAllocation.LOAD_FOLLOWING)
    assert caught.value.field == "ess.load_profile_kwh"
    # 조치가 **화면에서 할 수 있는 일**이어야 한다.
    assert "가구 전기부하" in caught.value.action


def test_the_report_prints_what_the_run_chose_not_what_the_constant_says() -> None:
    """★★ 「운전 방식」 칸은 **세운 자원이 실제로 든 값**을 싣는다.

    모듈 상수를 다시 읽어 재현하면 위 ② 의 실행에서도 「부하 추종」이 인쇄되고,
    그 거짓은 아무 예외도 내지 않는다 — `_resource_lines` 의
    `self_consumption_ratio`·`pv_allocation_priority` 가 같은 함정을 이미 적었다.
    """
    following = _ess_line(_run(_ONE_HOUSEHOLD_KWH)).operating_mode
    fixed = _ess_line(_run(None)).operating_mode

    assert ESSDischargeAllocation.LOAD_FOLLOWING.value in following
    assert ESSDischargeAllocation.FIXED_WINDOW.value in fixed
    # ⚠⚠ **방전창을 함께 적는다** — 「부하 추종」만 적으면 하루 종일 수요를
    # 따라간다로 읽힌다. 창 밖은 대응하지 못한다(붙임 8 이 그 크기를 잰다).
    assert "18~21시" in following, following
    assert "방전창" in fixed, fixed


# ── ③ 계절 ───────────────────────────────────────────────────────────────


def test_each_season_follows_its_own_load_not_the_annual_equivalent_day() -> None:
    """★★★ **그 계절의 부하를 그 계절의 ESS 가 본다** (판정 ②).

    계절 넷의 저녁 봉우리는 서로 다르다. 연간등가 하루의 부하 한 벌을 네 계절에
    돌려쓰면 「부하 추종」이 계절을 안 보는 추종이 되고, R64/WP-4 가 푼 계절
    상쇄가 **방전 쪽에서 다시 접힌다.**

    재는 방법: 계절별 하루의 **방전 형상**(하루 방전량으로 정규화)이 계절마다
    같지 않아야 한다. 같으면 한 벌을 돌려쓴 것이다.
    """
    outcome = _run(_ONE_HOUSEHOLD_KWH)
    assert len(outcome.seasons) >= 2, "계절이 하나면 이 성질을 잴 수 없다"

    shapes = []
    for season in outcome.seasons:
        electric = season.dispatch.per_resource[_ESS].electric
        total = math.fsum(v for v in electric if v > 0.0)
        assert total > 0.0, f"{season.name} 에 방전이 없다 — 잴 형상이 없다"
        shapes.append(tuple(max(0.0, v) / total for v in electric))

    assert len(set(shapes)) > 1, (
        "계절마다 방전 형상이 같다 — 연간등가 하루의 부하 한 벌을 돌려쓴 것이다"
    )


def test_the_annual_equivalent_battery_stands_on_the_annual_equivalent_day() -> None:
    """연간등가 배터리 한 대는 **리포트가 인쇄하는 하루** 위에 선다.

    그 대는 설정 오류를 잡고 비용을 무는 자리이며(`seasonal_dispatch` 머리말),
    리포트 0절이 그 대의 방전 배분을 인쇄한다. 계절 하나의 부하를 그 대에
    넣으면 **어느 계절의 것인지** 말할 수 없다.
    """
    outcome = _run(_ONE_HOUSEHOLD_KWH)
    ess = _ess_resource(outcome)
    assert ess.load_profile_kwh is not None
    assert list(ess.load_profile_kwh) == pytest.approx(_load_by_step(outcome))


# ── ④ 총량 보존 · 배분만 바뀐다 ──────────────────────────────────────────


def test_only_the_split_moves_the_daily_discharge_total_is_preserved() -> None:
    """★★ 하루 방전 **총량**은 그대로이고 **시각별 배분**만 달라진다.

    이것이 결론축이 움직인 사유를 좁힌다 — 총량이 함께 움직였다면 그 이동은
    「수요를 보고 방전한다」가 아니라 **다른 무엇**이다.
    """
    following = _discharge_by_step(_run(_ONE_HOUSEHOLD_KWH))
    fixed = _discharge_by_step(
        _run(_ONE_HOUSEHOLD_KWH, allocation=ESSDischargeAllocation.FIXED_WINDOW)
    )

    assert math.fsum(following) == pytest.approx(math.fsum(fixed))
    assert following != pytest.approx(fixed), (
        "배분이 하나도 안 바뀌었다 — 부하 시계열이 자원에 닿지 않은 것이다"
    )


def test_more_load_in_an_hour_means_more_discharge_in_that_hour() -> None:
    """「대응」의 뜻 — **수요가 큰 시각이 더 많이 낸다** (요구 5).

    방전창 안의 시각들끼리 견준다(창 밖은 어느 배분에서도 0 이다).
    """
    outcome = _run(_ONE_HOUSEHOLD_KWH)
    discharge = _discharge_by_step(outcome)
    load = _load_by_step(outcome)
    window = [step for step, kwh in enumerate(discharge) if kwh > 0.0]
    assert len(window) >= 2, "방전 시각이 하나면 견줄 것이 없다"

    ordered = sorted(window, key=lambda step: load[step])
    for lower, higher in pairwise(ordered):
        assert discharge[lower] <= discharge[higher] + 1e-9, (
            f"{lower}시(부하 {load[lower]:.4f}kWh)가 {higher}시(부하 "
            f"{load[higher]:.4f}kWh)보다 많이 냈다 — 부하 추종이 아니다"
        )


# ── ⑤ 조립·해석 함수가 짝을 다룬다 ──────────────────────────────────────


def test_the_builder_takes_the_pair_and_hands_it_to_the_resource() -> None:
    """`build_case_ess` 가 방전 배분과 부하를 **짝으로** 받아 자원에 싣는다.

    ⚠ 두 인자는 **기본값이 없다.** 기본값을 주면 배선이 끊겨도 조용히 「고정
    창」으로 서고, 그 상태가 정확히 이 WP 착수 시점의 상태였다.
    """
    day = [0.0] * 18 + [1.0, 2.0, 3.0, 1.0] + [0.0] * 2
    ess = build_case_ess(
        capacity_kwh=8.0,
        operating_mode=ESSOperatingMode.SELF_CONSUMPTION,
        charge_source=ESSChargeSource.GRID,
        pv_surplus_profile_kwh=None,
        discharge_allocation=ESSDischargeAllocation.LOAD_FOLLOWING,
        load_profile_kwh=day,
        capex_unit_won_per_kwh=380_000.0,
        fixed_om_won_per_year=90_000.0,
        replacement_unit_won_per_kwh=340_000.0,
        escalation_rate=0.0,
        replacement_escalation_rate=0.0,
    )
    assert ess.discharge_allocation is ESSDischargeAllocation.LOAD_FOLLOWING
    assert ess.load_profile_kwh == tuple(day)


def test_the_resolver_pairs_the_allocation_with_the_load_it_will_follow() -> None:
    """`resolve_ess_discharge_inputs` — 「고정 창」이면 부하가 `None` 이다.

    ⚠ 그 짝이 어긋나면 `ESS` 가 *「고정 창인데 부하 시계열을 받음」* 으로
    거부한다. 두 값을 따로 고르면 그 조합이 조용히 갈리므로 한 함수가 낸다.
    """
    household = Load(
        name="probe-load",
        hourly_kwh=([0.0] * 18 + [1.0, 2.0, 3.0, 1.0] + [0.0] * 2) * DAYS_PER_YEAR,
    )

    following, profile = resolve_ess_discharge_inputs(
        None, {}, _CTX, household=household
    )
    assert following is ESSDischargeAllocation.LOAD_FOLLOWING
    assert profile is not None
    assert profile[20] == pytest.approx(3.0)

    fixed, empty = resolve_ess_discharge_inputs(
        ESSDischargeAllocation.FIXED_WINDOW, {}, _CTX, household=household
    )
    assert fixed is ESSDischargeAllocation.FIXED_WINDOW
    assert empty is None

    absent, nothing = resolve_ess_discharge_inputs(None, {}, _CTX, household=None)
    assert absent is ESSDischargeAllocation.FIXED_WINDOW
    assert nothing is None


def test_the_runner_module_still_exports_the_default_for_the_docstrings() -> None:
    """`e2e_runner` 가 상수를 **재수출**한다 — 문면들이 그 경로를 가리킨다.

    `ESS_OPERATING_MODE_DEFAULT`·`ESS_CHARGE_SOURCE_DEFAULT`·
    `PV_ALLOCATION_PRIORITY_DEFAULT` 와 같은 자리다
    (`core/casegrid/pv_allocation.py` 머리말의 재수출 규약).
    """
    from core.casegrid import pv_allocation

    assert (
        ESS_DISCHARGE_ALLOCATION_DEFAULT
        is pv_allocation.ESS_DISCHARGE_ALLOCATION_DEFAULT
    )


def test_the_seasonal_entry_point_requires_the_axis_to_be_named() -> None:
    """`build_and_dispatch_case` 가 이 축을 **필수 인자**로 받는다.

    기본값을 주면 러너가 넘기는 것을 잊어도 조용히 돌고, 그 상태가 이 WP 가
    고친 상태다 — 잊은 것이 예외로 드러나야 한다.
    """
    with pytest.raises(TypeError, match="ess_discharge_allocation"):
        build_and_dispatch_case()  # type: ignore[call-arg]
