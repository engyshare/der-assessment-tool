"""ESS 방전 배분 — 고정 창 · 부하 추종 (R64/WP-6a · 사용자 요구 5).

사용자 요구 5 는 *「ESS는 가구의 전력 수요를 **최우선적으로 대응**할 수 있도록
운전되야 함」* 이다. 종전 방전은 방전창 안의 모든 시각에 **같은 양**을 실었으므로
그 요구를 만족하지 않았다 — 이 파일이 새 갈래(`부하 추종`)를 붙들고, 동시에
**기본값(고정 창)이 한 원소도 움직이지 않았음**을 붙든다.

성질 여섯을 판정문(`.orch/R64/WP-6a.md` §4)의 이름 그대로 붙든다.

    가  기본값(고정 창)일 때 지금과 **원소 하나까지** 같다
    나  부하 추종일 때 하루 방전 총량이 고정 창과 같다 (에너지 보존)
    다  부하 추종일 때 부하가 큰 시각에 더 많이 낸다 (실제로 추종하는가)
    라  부하 시계열이 없거나 전부 0이면 **3요소로 거부**한다 (조용한 폴백 없음)
    마  정격출력을 넘지 않는다
    바  기존 갈래(운전 방법 · 충전원 · 배분 우선순위)가 그대로 선다

⚠ **오라클을 구현에서 읽어오지 않는다.** 성질 가의 기댓값은 이 파일이 종전
산식을 **손으로 옮겨 적어** 만든다(`_legacy_electric`) — 구현을 불러 비교하면
둘이 함께 틀려도 초록불이다.
"""

from __future__ import annotations

import math

import pytest

from core.contracts.der import DispatchContext
from core.contracts.units import ENERGY_TOLERANCE_KWH, SECONDS_PER_HOUR
from core.contracts.validation import ValidationError
from core.der.ess import DAYS_PER_YEAR, ESS, ESSChargeSource, ESSOperatingMode
from core.der.ess_schedule import (
    ESSDischargeAllocation,
    check_load_profile,
    load_following_kwh_by_hour,
)
from core.der.pv import PVAllocationPriority, resolve_pv_allocation_priority

#: `RC-ESS-P1` 제원. 가용량 10×(0.9−0.1)=8kWh · 연 365사이클 → **하루 방전 8kWh**,
#: 기본 운전 방법(TOU 차익거래)의 방전창은 18~21시 **네 시각**이다.
_P1 = {
    "name": "배분시험ESS", "capacity_kwh": 10.0, "power_kw": 5.0, "rte_pct": 90.0,
    "soc_min_pct": 10.0, "soc_max_pct": 90.0, "cycle_life": 6000,
    "calendar_life": 20, "eol_soh_pct": 80.0, "cycles_per_year": 365.0,
}


def _ess(**overrides) -> ESS:
    params = dict(_P1)
    params.update(overrides)
    return ESS(**params)


def _ctx(*, steps: int = 24, dt: int = SECONDS_PER_HOUR, year: int = 1) -> DispatchContext:
    return DispatchContext(steps=steps, dt=dt, year=year)


def _evening_load(**by_hour: float) -> list[float]:
    """시각→부하 kWh 를 24행 시계열로. 적지 않은 시각은 0이다."""
    profile = [0.0] * 24
    for hour, kwh in by_hour.items():
        profile[int(hour.lstrip("h"))] = kwh
    return profile


def _legacy_electric(ess: ESS, ctx: DispatchContext) -> list[float]:
    """**종전 산식을 손으로 옮겨 적은 것** — R64/WP-6a 이전 `ESS.dispatch()`.

    `core/der/ess.py:895~918`(착수 시점) 의 방전·충전 배분 그대로다. 부동소수의
    마지막 자리까지 같아야 하므로 나눗셈의 **순서와 묶음**을 바꾸지 않았다.
    """
    steps_per_hour = SECONDS_PER_HOUR // ctx.dt
    year = int(ctx.year)
    discharge_window = len(ess.discharge_hours) * steps_per_hour
    out_step = ess.annual_discharge_kwh(year=year) / DAYS_PER_YEAR / discharge_window
    electric = [0.0] * ctx.steps
    if ess.charge_source is ESSChargeSource.PV_SURPLUS:
        charged_by_hour = ess._pv_surplus_charge_kwh_by_hour(year=year)
        for i in range(ctx.steps):
            hour = (i // steps_per_hour) % 24
            if hour in ess.discharge_hours:
                electric[i] = out_step
            elif hour in charged_by_hour:
                electric[i] = -(charged_by_hour[hour] / steps_per_hour)
    else:
        charge_window = len(ess.charge_hours) * steps_per_hour
        in_step = ess.annual_charge_kwh(year=year) / DAYS_PER_YEAR / charge_window
        for i in range(ctx.steps):
            hour = (i // steps_per_hour) % 24
            if hour in ess.discharge_hours:
                electric[i] = out_step
            elif hour in ess.charge_hours:
                electric[i] = -in_step
    return electric


# ── 성질 가 — 기본값은 한 원소도 움직이지 않았다 ─────────────────────

def test_default_discharge_allocation_is_the_fixed_window() -> None:
    """성질 가 — **기본값을 바꾸지 않았다.** 이 한 줄이 무너지면 이 축을 모르는
    기존 호출자 전부의 수가 조용히 움직인다."""
    assert _ess().discharge_allocation is ESSDischargeAllocation.FIXED_WINDOW
    assert _ess().load_profile_kwh is None


@pytest.mark.parametrize("dt", [SECONDS_PER_HOUR, SECONDS_PER_HOUR // 4])
@pytest.mark.parametrize("mode", list(ESSOperatingMode))
def test_fixed_window_dispatch_is_element_identical_to_the_legacy_formula(
    dt: int, mode: ESSOperatingMode
) -> None:
    """성질 가 — 기본값일 때 **원소 하나까지** 종전과 같다.

    `pytest.approx` 를 쓰지 않는다 — 허용오차로 비교하면 마지막 자리가 움직인
    것을 통과시키고, 골든 회귀는 그 자리에서 빨개진다.
    """
    if mode is ESSOperatingMode.HYBRID:
        pytest.skip("혼합 모드는 가중치를 요구한다 — 운전창 자체는 대표 모드의 것이다")
    steps = 24 * (SECONDS_PER_HOUR // dt)
    ess = _ess(operating_mode=mode, dt=dt)
    ctx = _ctx(steps=steps, dt=dt)
    assert ess.dispatch(ctx).electric == _legacy_electric(ess, ctx)


def test_fixed_window_dispatch_is_element_identical_under_pv_surplus_charging() -> None:
    """성질 가 — 충전원이 `PV_SURPLUS` 인 갈래도 원소 하나까지 같다."""
    ess = _ess(
        operating_mode=ESSOperatingMode.SELF_CONSUMPTION,
        charge_source=ESSChargeSource.PV_SURPLUS,
        pv_surplus_profile_kwh=[3.0] * 24,
    )
    ctx = _ctx()
    assert ess.dispatch(ctx).electric == _legacy_electric(ess, ctx)


# ── 성질 나·다 — 총량은 보존되고, 배분만 부하를 따라간다 ──────────────

def test_load_following_preserves_the_daily_discharge_total() -> None:
    """성질 나 — **에너지 보존.** 바뀌는 것은 배분뿐이며, 하루 방전 총량은
    고정 창과 같다. 총량이 움직이면 편익이 생기거나 사라진다."""
    profile = _evening_load(h18=1.0, h19=2.0, h20=3.0, h21=4.0)
    fixed = _ess().dispatch(_ctx()).electric
    following = _ess(
        discharge_allocation=ESSDischargeAllocation.LOAD_FOLLOWING,
        load_profile_kwh=profile,
    ).dispatch(_ctx()).electric
    fixed_out = math.fsum(v for v in fixed if v > 0.0)
    following_out = math.fsum(v for v in following if v > 0.0)
    assert following_out == pytest.approx(fixed_out, abs=ENERGY_TOLERANCE_KWH)
    assert following_out == pytest.approx(8.0, abs=ENERGY_TOLERANCE_KWH)


def test_load_following_gives_more_to_the_hours_with_more_load() -> None:
    """성질 다 — **실제로 추종하는가.** 부하 1:2:3:4 이면 방전도 1:2:3:4 다."""
    profile = _evening_load(h18=1.0, h19=2.0, h20=3.0, h21=4.0)
    electric = _ess(
        discharge_allocation=ESSDischargeAllocation.LOAD_FOLLOWING,
        load_profile_kwh=profile,
    ).dispatch(_ctx()).electric
    out = [electric[hour] for hour in (18, 19, 20, 21)]
    assert out == sorted(out), "부하가 커지는 순서로 방전도 커져야 한다"
    assert out == pytest.approx([0.8, 1.6, 2.4, 3.2], abs=ENERGY_TOLERANCE_KWH)
    # 고정 창이었다면 넷 다 2.0 이다 — 그것이 「수요를 보지 않는다」의 모습이다
    assert _ess().dispatch(_ctx()).electric[18] == pytest.approx(2.0, abs=ENERGY_TOLERANCE_KWH)


def test_load_following_leaves_zero_load_hours_empty() -> None:
    """성질 다 — 부하가 0인 시각에는 내지 않는다. 「대응」은 수요가 있는 곳에
    낸다는 뜻이고, 수요 없는 시각에 싣는 것은 추종이 아니다."""
    profile = _evening_load(h19=1.0, h21=1.5)
    electric = _ess(
        discharge_allocation=ESSDischargeAllocation.LOAD_FOLLOWING,
        load_profile_kwh=profile,
    ).dispatch(_ctx()).electric
    assert electric[18] == 0.0
    assert electric[20] == 0.0
    # 하루 8kWh 를 1 : 1.5 로 — 3.2 와 4.8. 둘 다 정격(5kWh/h) 아래다
    assert electric[19] == pytest.approx(3.2, abs=ENERGY_TOLERANCE_KWH)
    assert electric[21] == pytest.approx(4.8, abs=ENERGY_TOLERANCE_KWH)


def test_load_following_splits_each_hour_evenly_across_its_steps() -> None:
    """부분 창 규약(`ESS.dispatch` 독스트링)은 그대로다 — 15분 스텝이면 한 시각의
    몫이 네 스텝에 넷으로 나뉘어 실린다. 시각 단위 계획이라 스텝을 잘게 해도
    **그 시각의 총량**은 움직이지 않는다."""
    profile = _evening_load(h18=1.0, h19=1.5)
    dt = SECONDS_PER_HOUR // 4
    electric = _ess(
        dt=dt,
        discharge_allocation=ESSDischargeAllocation.LOAD_FOLLOWING,
        load_profile_kwh=profile,
    ).dispatch(_ctx(steps=96, dt=dt)).electric
    # 18시의 몫 3.2kWh 가 네 스텝에 0.8 씩, 19시의 몫 4.8kWh 는 1.2 씩
    assert electric[72:76] == pytest.approx([0.8] * 4, abs=ENERGY_TOLERANCE_KWH)
    assert electric[76:80] == pytest.approx([1.2] * 4, abs=ENERGY_TOLERANCE_KWH)
    assert math.fsum(v for v in electric if v > 0.0) == pytest.approx(8.0, abs=1e-9)


# ── 성질 라 — 조용한 폴백이 없다 ────────────────────────────────────

@pytest.mark.parametrize(
    ("profile", "needle"),
    [
        (None, "없거나 전부 0"),
        ([0.0] * 24, "없거나 전부 0"),
        ([1.0] * 23, "24행이어야"),
        ([1.0] * 25, "24행이어야"),
    ],
)
def test_load_following_rejects_a_missing_or_malformed_load_profile(
    profile: list[float] | None, needle: str
) -> None:
    """성질 라 — 3요소(`field`·`reason`·`action`)로 거부한다. ⛔ 조용히 고정 창으로
    되돌아가면 리포트의 「부하 추종으로 돌았다」가 거짓이 된다."""
    with pytest.raises(ValidationError) as excinfo:
        _ess(
            discharge_allocation=ESSDischargeAllocation.LOAD_FOLLOWING,
            load_profile_kwh=profile,
        )
    parts = excinfo.value.as_dict()
    assert parts["field"] == "ess.load_profile_kwh"
    assert needle in parts["reason"]
    assert parts["action"]
    assert parts["rule"] is None


def test_load_following_rejects_a_load_that_is_zero_throughout_the_discharge_window() -> None:
    """성질 라 — 부하는 있는데 **방전 시간대 안이 전부 0**이면 무엇에 맞춰 낼지가
    없다. 이때 균등 배분으로 돌아가면 「추종했다」가 거짓이 된다."""
    with pytest.raises(ValidationError) as excinfo:
        _ess(
            discharge_allocation=ESSDischargeAllocation.LOAD_FOLLOWING,
            load_profile_kwh=_evening_load(h10=5.0),
        )
    parts = excinfo.value.as_dict()
    assert parts["field"] == "ess.load_profile_kwh"
    assert "방전 시간대" in parts["reason"]


def test_fixed_window_rejects_a_load_profile_it_would_never_read() -> None:
    """성질 라의 반대 방향 — 고정 창인데 부하 시계열을 받으면 거부한다. 받아
    두고 안 쓰면 「부하를 줬는데 결과가 그대로다」가 된다
    (`ESS._check_pv_surplus` 가 충전원에 대해 세운 것과 같은 관례)."""
    with pytest.raises(ValidationError) as excinfo:
        _ess(load_profile_kwh=[1.0] * 24)
    assert excinfo.value.as_dict()["field"] == "ess.load_profile_kwh"


def test_the_rejection_tells_the_user_something_they_can_actually_do() -> None:
    """`action` 은 **화면 사용자가 할 수 있는 말**이어야 한다.

    실측된 결함이 하나 있다 — `pv_surplus_profile_kwh` 거부의 `action` 이
    *「`pv_surplus_profile_kwh` 에 … 지정하십시오」* 라 파이썬 인자 이름을 시킨다.
    같은 잘못을 하지 않았음을 붙든다: 부하 시계열 거부의 `action` 에는 파이썬
    인자 이름이 없고, **고르는 것**과 **넣는 것**이 적혀 있다.
    """
    with pytest.raises(ValidationError) as excinfo:
        _ess(discharge_allocation=ESSDischargeAllocation.LOAD_FOLLOWING)
    action = excinfo.value.as_dict()["action"]
    assert "load_profile_kwh" not in action
    assert ESSDischargeAllocation.FIXED_WINDOW.value in action
    assert "가구" in action


def test_an_unknown_discharge_allocation_is_rejected_with_the_allowed_list() -> None:
    """선언 목록 밖의 값은 거부하고 **고를 수 있는 것을 알려준다**
    (`ESS._coerce_charge_source` 와 같은 관례)."""
    with pytest.raises(ValidationError) as excinfo:
        _ess(discharge_allocation="적당히")
    parts = excinfo.value.as_dict()
    assert parts["field"] == "ess.discharge_allocation"
    assert ESSDischargeAllocation.LOAD_FOLLOWING.value in parts["action"]


def test_the_allocation_axis_accepts_the_plain_string_a_case_grid_would_pass() -> None:
    """양성 짝 — 케이스 그리드가 문자열로 축을 건넬 수 있어야 한다."""
    ess = _ess(
        discharge_allocation="부하 추종",
        load_profile_kwh=_evening_load(h18=1.0, h19=1.0, h20=1.0, h21=1.0),
    )
    assert ess.discharge_allocation is ESSDischargeAllocation.LOAD_FOLLOWING


# ── 성질 마 — 정격출력을 넘지 않는다 (판정 ⑤) ────────────────────────

def test_load_following_caps_at_the_rated_power_and_redistributes_the_rest() -> None:
    """성질 마 · 판정 ⑤ — 부하가 한 시각에 몰려도 **정격출력을 넘지 않고**,
    넘칠 몫은 **사라지지 않고** 나머지 시각으로 간다.

    손계산: 하루 8kWh · 정격 5kW · 방전창 18~21시. 부하가 21시에 100, 나머지
    셋에 0.1 이면 비례 배분은 21시에 7.976kWh 로 정격(5kWh/h)을 넘는다 →
    21시를 5 에 묶고 남은 3kWh 를 세 시각에 부하 비례(같은 값)로 나눠 1.0 씩.
    """
    ess = _ess(
        discharge_allocation=ESSDischargeAllocation.LOAD_FOLLOWING,
        load_profile_kwh=_evening_load(h18=0.1, h19=0.1, h20=0.1, h21=100.0),
    )
    electric = ess.dispatch(_ctx()).electric
    assert max(electric) <= ess.power_kw
    assert electric[21] == pytest.approx(5.0, abs=1e-9)
    assert [electric[h] for h in (18, 19, 20)] == pytest.approx([1.0, 1.0, 1.0], abs=1e-9)
    assert math.fsum(v for v in electric if v > 0.0) == pytest.approx(8.0, abs=1e-9)


def test_load_following_rejects_when_the_rated_power_cannot_hold_the_daily_energy() -> None:
    """판정 ⑤ 의 남은 구석 — 부하가 있는 시각을 전부 정격까지 채우고도 남으면
    **거부한다.** ⛔ 잘라내면 방전이 줄어드는데 편익은 그대로 남고, 부하가 0인
    시각에 몰래 실으면 「수요에 대응했다」가 거짓이 된다."""
    ess = _ess(
        discharge_allocation=ESSDischargeAllocation.LOAD_FOLLOWING,
        load_profile_kwh=_evening_load(h21=10.0),
    )
    with pytest.raises(ValidationError) as excinfo:
        ess.dispatch(_ctx())
    parts = excinfo.value.as_dict()
    assert parts["field"] == "ess.power_kw"
    assert "남습니다" in parts["reason"]
    assert parts["action"]


def test_the_allocator_never_exceeds_the_cap_for_any_load_shape() -> None:
    """성질 마 — 모양을 바꿔 가며 **정격 초과가 한 시각도 없음**과 **총량 보존**을
    함께 잰다. 한쪽만 재면 「잘라내서 정격을 지켰다」가 통과한다."""
    shapes = ([4.0, 1.0, 1.0, 1.0], [1.0, 0.0, 0.0, 9.0], [1.0, 1.0, 1.0, 1.0],
              [0.5, 40.0, 40.0, 0.5])
    for shape in shapes:
        planned = load_following_kwh_by_hour(
            daily_kwh=8.0,
            discharge_hours=(18, 19, 20, 21),
            load_profile_kwh=_evening_load(h18=shape[0], h19=shape[1], h20=shape[2],
                                           h21=shape[3]),
            power_kw=5.0,
            name="모양시험",
        )
        assert max(planned.values()) <= 5.0 + 1e-9, shape
        assert math.fsum(planned.values()) == pytest.approx(8.0, abs=1e-9), shape


# ── 성질 바 — 기존 갈래가 그대로 선다 ────────────────────────────────

@pytest.mark.parametrize("mode", list(ESSOperatingMode))
def test_every_operating_mode_still_stands(mode: ESSOperatingMode) -> None:
    """성질 바 — 이 WP 는 **더하는 WP 이지 빼는 WP 가 아니다.**"""
    if mode is ESSOperatingMode.HYBRID:
        ess = _ess(operating_mode=mode, mode_weights={ESSOperatingMode.PEAK_SHAVING: 1.0})
    else:
        ess = _ess(operating_mode=mode)
        assert ess.mode_weights == {mode: 1.0}
    assert ess.discharge_hours
    assert any(v > 0.0 for v in ess.dispatch(_ctx()).electric)


def test_the_battery_first_allocation_priority_is_still_selectable() -> None:
    """판정 ③ — 「배터리 우선」 갈래를 **지우지 않았다.** 이 WP 는 방전 배분에
    축을 하나 더하는 것이고, 낮 전기의 배분 순서(`docs/decisions-2026-09-01-R51.md`
    §1)는 건드리지 않았다 — 이름이 서 있는 것으로는 모자라서 **승격까지** 잰다."""
    assert resolve_pv_allocation_priority("배터리 우선") is PVAllocationPriority.BATTERY_FIRST
    assert resolve_pv_allocation_priority("집 우선") is PVAllocationPriority.HOUSEHOLD_FIRST


def test_pv_surplus_charging_still_stands_next_to_load_following_discharge() -> None:
    """성질 바 — 충전원 축과 방전 배분 축은 **직교한다.** PV 잉여로 충전하면서
    부하를 따라 방전하는 구성이 서야 한다(요구 5 가 가리키는 바로 그 구성이다)."""
    ess = _ess(
        operating_mode=ESSOperatingMode.SELF_CONSUMPTION,
        charge_source=ESSChargeSource.PV_SURPLUS,
        pv_surplus_profile_kwh=[3.0] * 24,
        discharge_allocation=ESSDischargeAllocation.LOAD_FOLLOWING,
        load_profile_kwh=_evening_load(h18=1.0, h19=2.0, h20=2.0, h21=3.0),
    )
    electric = ess.dispatch(_ctx()).electric
    assert any(v < 0.0 for v in electric), "충전이 실려 있어야 한다"
    out = [electric[hour] for hour in ess.discharge_hours]
    assert out == sorted(out)
    assert math.fsum(v for v in electric if v > 0.0) == pytest.approx(
        ess.annual_discharge_kwh(year=1) / DAYS_PER_YEAR, abs=1e-9
    )


def test_check_load_profile_returns_none_for_the_fixed_window() -> None:
    """고정 창은 시계열을 들지 않는다 — 들면 「무엇이 실렸나」가 두 벌이 된다."""
    assert check_load_profile(
        ESSDischargeAllocation.FIXED_WINDOW, None, (18, 19, 20, 21), name="ESS"
    ) is None
