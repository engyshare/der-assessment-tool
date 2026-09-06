"""**「AI 가전」은 부하를 옮긴다 — 더하지 않는다** — 사용자 요구 2 (R64/WP-7).

사용자 문면: *「가구의 전기 부하 설정을 변경할 수 있어야 함 (EV, heatpump,
AI 가전)」*. R64/WP-2 가 앞의 둘을 총량으로 열었고 「AI 가전」은 **일부러
떼어냈다** — 가산 항목으로 세우면 냉장고·세탁기의 소비가 두 번 세어진다.

사용자 판정 2026-09-06 (`docs/decisions-2026-09-06-R64.md` §4·§5):
*「기존 가전에 AI 기능이 포함된다고 보면 어떠한가? 냉장고, 세탁기 등 DR 자원
으로 활용 가능한 전자기기에 대해서 기능이 추가되는 것임」* ·
*「(가)만. 집 전체 가전 부하 중 비율로 간단히」*

## ★★★ 이 파일이 실제로 붙드는 것 — **총량이 한 kWh 도 안 움직이는가**

이 축에서 가장 위험한 것은 「부하를 옮기는 것」이 아니라 **옮기다가 총량이
달라지는 것**이다. 총량이 달라지면 결론이 대장(`load.household.annual`)이 정한
부하가 아닌 것 위에 서고, **그 어긋남은 아무 예외도 내지 않는다.** 그래서 첫
검사가 총량 보존이고, 그 위에서만 「어디로 옮겼는가」를 잰다.

## ★★ 둘째로 붙드는 것 — **옮길 곳이 없으면 옮기지 않는가**

겨울처럼 하루 종일 태양광 잉여가 없는 계절에서는 옮길 자리가 없다. 그때 값을
지어내 옮기면(예: 평균 잉여로 옮기면) **없는 잉여로 자가소비를 늘린 것**이
되고, 그 몫이 조용히 계통 수전에서 사라진다.

## ⚠ 배포 실행의 동일성은 여기서 재지 않는다

비율 0 으로 도는 실행이 이 배선 이전과 같은가는 `tests/golden/
test_regression_scenarios.py::test_golden_scenarios_match_current_regression_snapshot`
가 `npv_won` 으로 잰다. 대장이 값(10%)을 가지므로 **배포 기본 실행은 이제
부하를 옮긴다** — 그것이 요구가 시킨 것이며, 그 이동량을 리포트까지 나르는
배선은 `tests/report/test_load_shift_wired.py` 가 잰다.

## ⚠ `req()` 마커를 달지 않았다 — **조항을 대조하고 내린 판정이다**

spec 에 「가전 부하의 시간 이동」을 요구하는 수용기준이 없다. 가까워 보이는
`FR-401-AC2.DemandResponse` 는 **「감축량 × 정산단가」의 정산금 갈래**이고 이
WP 가 하지 않기로 판정한 것이다(사용자 판정 §5) — 그 ID 를 붙이면
`docs/traceability.md` 에 *「그 조항이 검증됐다」* 는 거짓 인용이 실린다.
`tests/casegrid/test_appliance_load.py` 머리말이 같은 자리에서 같은 판정을
적었다.
"""
from __future__ import annotations

import math

import pytest

from core.casegrid.load_shift import (
    MAX_SHIFTABLE_SHARE_PCT,
    resolve_shiftable_share,
    shift_into_pv_surplus,
    shiftable_share_pct,
)
from core.contracts.validation import ValidationError

#: 시험용 하루 — 4스텝. **24스텝을 쓰지 않는 이유**: 손으로 검산할 수 있어야
#: 「어디로 옮겼는가」가 시험 안에서 읽힌다. 배포 하루(24스텝)의 성질은
#: `tests/report/test_load_shift_wired.py` 가 실물 자산으로 잰다.
#:
#:     스텝        0     1     2     3
#:     발전      0.0   6.0   4.0   0.0
#:     부하      2.0   1.0   1.0   4.0
#:     잉여      0.0   5.0   3.0   0.0   ← 합 8.0
#:     원천      2.0   0.0   0.0   4.0   ← 합 6.0 (잉여 없는 시각의 부하)
_GENERATION = (0.0, 6.0, 4.0, 0.0)
_LOAD = (2.0, 1.0, 1.0, 4.0)
_SURPLUS_TOTAL = 8.0
_SOURCE_TOTAL = 6.0


def _shift(share_pct: float, *, appliance_ratio: float = 1.0):
    return shift_into_pv_surplus(
        _LOAD, _GENERATION, share_pct=share_pct, appliance_ratio=appliance_ratio
    )


def test_the_total_does_not_move_by_a_single_kwh() -> None:
    """★★★ **총량 보존** — 옮기는 것이지 더하거나 빼는 것이 아니다 (판정 ①).

    가산 항목으로 세우지 않기로 한 판정(§4)이 코드에서 성립하는 자리가 여기다.
    총량이 움직이면 결론이 대장이 정한 부하가 아닌 것 위에 선다.
    """
    for share in (1.0, 10.0, 25.0, 50.0, MAX_SHIFTABLE_SHARE_PCT):
        shifted = _shift(share)
        assert math.fsum(shifted.day) == pytest.approx(
            math.fsum(_LOAD), abs=1e-12
        ), (
            f"비율 {share}% 에서 하루 총량이 {math.fsum(shifted.day)!r} 이다 "
            f"(원래 {math.fsum(_LOAD)!r}) — 옮기다가 에너지가 생겼거나 사라졌다"
        )


def test_the_moved_amount_goes_to_the_hours_that_have_pv_surplus() -> None:
    """★★★ **옮긴 곳이 잉여가 있는 시각인가** (판정 ② · 사용자 판정 §5 의 (가)).

    잉여에 비례해 나누므로 스텝 1(잉여 5.0)이 스텝 2(잉여 3.0)보다 많이 받고,
    잉여가 없는 스텝 0·3 은 **줄어들기만** 한다.
    """
    shifted = _shift(10.0)
    # 옮길 몫 = 10% × 원천 6.0 = 0.6 이고 잉여 합 8.0 보다 작으므로 비율이 자른다
    assert shifted.moved_kwh == pytest.approx(0.6)
    given = [after - before for after, before in zip(shifted.day, _LOAD, strict=True)]
    assert given[0] < 0.0 and given[3] < 0.0, "잉여 없는 시각이 줄지 않았다"
    assert given[1] > given[2] > 0.0, (
        f"잉여에 비례해 나누지 않았다: {given!r} — 잉여 5.0 인 시각이 3.0 인 "
        "시각보다 많이 받아야 한다"
    )
    assert math.fsum(given) == pytest.approx(0.0, abs=1e-12)


def test_nothing_moves_when_there_is_nowhere_to_move_it() -> None:
    """★★★ **옮길 곳이 없으면 옮기지 않는다** — 값을 지어내지 않는다 (판정 ②).

    하루 종일 부하가 발전보다 크면 잉여가 0 이고, 그때 하루는 **원소 하나까지**
    그대로여야 한다. 평균 잉여 같은 것으로 대신 옮기면 없는 전기로 자가소비를
    늘린 것이 되고 그 몫이 조용히 계통 수전에서 사라진다.
    """
    dark = (0.0, 0.0, 0.0, 0.0)
    shifted = shift_into_pv_surplus(
        _LOAD, dark, share_pct=MAX_SHIFTABLE_SHARE_PCT, appliance_ratio=1.0
    )
    assert shifted.moved_kwh == 0.0
    assert shifted.day == _LOAD


def test_the_move_is_capped_by_that_days_surplus() -> None:
    """★★★ **그 날 잉여보다 많이 옮기지 않는다** (모듈 머리말 ⚠⚠).

    잉여를 넘겨 실으면 그 시각이 다시 계통 수전으로 돌아서고, 그러면
    「자가소비를 늘렸다」가 거짓이 된다. 이 하루는 원천 6.0 · 잉여 8.0 이므로
    비율 100% 에서도 **원천이 먼저 마른다** — 그 자리를 함께 잰다.
    """
    full = _shift(MAX_SHIFTABLE_SHARE_PCT)
    assert full.moved_kwh == pytest.approx(_SOURCE_TOTAL)
    assert full.moved_kwh <= _SURPLUS_TOTAL

    # 잉여가 원천보다 작은 하루 — 이번에는 **잉여가 자른다**
    thin = (0.0, 1.5, 0.0, 0.0)
    capped = shift_into_pv_surplus(
        _LOAD, thin, share_pct=MAX_SHIFTABLE_SHARE_PCT, appliance_ratio=1.0
    )
    surplus = math.fsum(
        max(0.0, g - load) for g, load in zip(thin, _LOAD, strict=True)
    )
    assert capped.moved_kwh == pytest.approx(surplus)
    # ★ 준 몫이 그 시각의 잉여를 넘지 않으므로 옮긴 뒤 부하가 발전을 넘지 않는다
    assert capped.day[1] == pytest.approx(thin[1])


def test_the_load_never_goes_negative() -> None:
    """★★ 옮긴 뒤 부하가 **음수가 되지 않는다** — 음수 부하는 설비 없는 발전이다."""
    for share in (10.0, 50.0, MAX_SHIFTABLE_SHARE_PCT):
        assert min(_shift(share).day) >= 0.0, f"비율 {share}% 에서 부하가 음수다"


def test_the_denominator_is_the_appliance_load_only() -> None:
    """★★★ **분모가 가전 부하뿐이다** — 히트펌프·전기차가 들어오면 몫이 줄어든다.

    사용자 문면이 *「집 전체 **가전** 부하 중 비율」* 이다. 추가 기기까지 옮길
    수 있다고 보면 전기차 충전의 형상 부채(`load.ev.annual` 의 `impact_note`)를
    가정으로 조용히 갚는 것이 된다.
    """
    whole = _shift(20.0)
    half = _shift(20.0, appliance_ratio=0.5)
    assert half.moved_kwh == pytest.approx(whole.moved_kwh / 2.0)
    assert math.fsum(half.day) == pytest.approx(math.fsum(_LOAD), abs=1e-12)


def test_a_zero_share_leaves_the_day_untouched() -> None:
    """★★ 비율 0 은 *「옮기지 않는다」* — 하루가 **원소 하나까지** 그대로다."""
    assert _shift(0.0).day == _LOAD
    assert _shift(0.0).moved_kwh == 0.0


def test_the_share_is_resolved_in_one_place() -> None:
    """★ 대장·화면이 적은 값의 판정은 **한 자리**다 (`NFR-303`).

    `None` 과 빈 문자열이 「적지 않았다」이고, 그때 `shiftable_share_pct` 가
    0(옮기지 않는다)으로 메운다 — 메우는 자리도 하나다.
    """
    assert resolve_shiftable_share(None) is None
    assert resolve_shiftable_share("") is None
    assert resolve_shiftable_share("  ") is None
    assert resolve_shiftable_share(10) == 10.0
    assert resolve_shiftable_share("12.5") == 12.5
    assert shiftable_share_pct(None) == 0.0
    assert shiftable_share_pct("7") == 7.0


@pytest.mark.parametrize(
    "bad",
    [-1, -0.001, 100.5, 1_000, float("nan"), float("inf"), True, False, "열", [10], None],
)
def test_a_share_outside_the_axis_is_refused_with_three_elements(bad: object) -> None:
    """★★ 축 밖의 값은 **3요소를 갖춘 거부**다 (`NFR-303`).

    음수는 「거꾸로 옮긴다」가 되고(자가소비를 줄이면서 리포트에는 「DR 을
    반영했다」로 적힌다), 100 초과는 시각별 부하보다 많이 빼 **부하를 음수로**
    만든다. `bool` 은 `int` 의 하위형이라 막지 않으면 `True` 가 1% 로 조용히
    통과한다.

    ⚠ `None` 은 **거부가 아니다** — *「적지 않았다」* 이므로 이 목록에 있는
    이유는 그 갈래를 함께 못 박기 위해서다.
    """
    if bad is None:
        assert resolve_shiftable_share(bad) is None
        return
    with pytest.raises(ValidationError) as caught:
        resolve_shiftable_share(bad)
    assert caught.value.field
    assert caught.value.reason
    assert caught.value.action
