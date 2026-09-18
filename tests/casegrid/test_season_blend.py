"""**계절별 하루를 연간등가 하루로 접는다** — `core/casegrid/season_blend.py`.

R64/WP-7 이 `core/casegrid/seasonal_dispatch.py` 에서 이 절을 갈라냈다(그 파일이
`NFR-206` 코드 줄 상한을 519줄로 넘겼다). **갈라낸 모듈은 정면이 아니라 직접
재야 한다** — R64/WP-4-fix2 가 CI 게이트 ②(테스트 동반 · `NFR-105`)에서 같은
판정을 받은 자리이며, 러너를 통해서만 재면 접는 식이 틀려도 다른 수에 가려진다.

## 재는 것 셋 — 접기가 **거짓말하지 않는가**

    ⓐ 차례에 무감하다      계절을 적는 차례를 바꿔도 같은 수다(성질 「다」)
    ⓑ 계절 하나면 항등이다  가중치 1 이면 받은 하루가 **원소 하나까지** 그대로다
    ⓒ 미충족을 버리지 않는다 어느 계절이 수요를 못 채웠다는 사실이 사라지지 않는다

ⓒ 가 없으면 접기는 **조용히** 사실을 지운다 — 그 소멸은 아무 예외도 내지 않는다.

## ⚠ `req()` 마커를 달지 않았다

spec 에 「계절별 운전의 합산 방법」을 요구하는 수용기준이 없다. 사유는
`tests/casegrid/test_seasonal_dispatch_run.py` 머리말과 같다.
"""
from __future__ import annotations

import math

import pytest

from core.casegrid.season_blend import blend_dispatch, blend_series
from core.contracts.der import DispatchResult
from core.contracts.engine import SystemDispatch

#: 계절 넷의 일수와 그 가중치 — 배포 자산과 같은 달력(합 365일)이다.
_DAYS = (92, 92, 91, 90)
_WEIGHTS = tuple(days / 365 for days in _DAYS)
_STEPS = 3


def _result(electric: list[float], *, unmet: list[float] | None = None) -> DispatchResult:
    zeros = [0.0] * len(electric)
    return DispatchResult(
        electric=electric,
        heat=list(zeros),
        cool=list(zeros),
        fuel=list(zeros),
        unmet_electric=list(unmet if unmet is not None else zeros),
        unmet_heat=list(zeros),
        unmet_cool=list(zeros),
        unmet_fuel=list(zeros),
    )


def _dispatch(name: str, electric: list[float], unmet: list[float] | None = None):
    return SystemDispatch(
        per_resource={name: _result(electric, unmet=unmet)},
        grid_import=[0.0] * len(electric),
        grid_export=list(electric),
    )


def test_blending_is_insensitive_to_the_order_of_the_seasons() -> None:
    """★★★ **차례에 무감하다** (성질 「다」 · 착수 36번의 위험).

    계절을 적는 차례가 결론을 정하면 자산의 줄 순서만 바꿔도 수가 달라진다 —
    R60/WP-4 가 그것을 실측했다(*「차례만 바꿔도 연간 발전이 +281kWh 생긴다」*).
    이 모듈이 그것을 지키는 방법은 **이어 붙이지 않는 것**과 `math.fsum` 이다.
    """
    series = [[1.0, 2.0, 3.0], [0.5, 0.25, 0.125], [7.0, 0.0, 1.0], [0.1, 0.2, 0.3]]
    straight = blend_series(series, _WEIGHTS)
    reversed_ = blend_series(series[::-1], _WEIGHTS[::-1])
    assert straight == reversed_, (
        f"차례를 뒤집자 접은 하루가 달라졌다: {straight!r} != {reversed_!r}"
    )


def test_a_single_season_is_the_identity() -> None:
    """★★ 계절 하나(가중치 `365/365 == 1.0`)면 **원소 하나까지** 그대로다.

    계절 축이 서기 전과 같은 수라는 성질(성질 「라」)이 이 항등에 서 있다 —
    `fsum([x * 1.0]) == x` 이기 때문이며, 그 사실을 여기서 못 박는다.
    """
    day = [1.0, 0.0, 123.456789]
    assert blend_series([day], (365 / 365,)) == day


def test_the_weighted_mean_times_the_year_returns_the_seasonal_sum() -> None:
    """★★★ **접은 하루 × 365 == Σ(계절 하루 × 계절일수)** — 접기의 정의다.

    러너가 접은 하루에 종전 연간화 규약(×365)을 그대로 먹이므로, 이 항등이
    깨지면 **연간 총량이 조용히 달라진다.**
    """
    series = [[2.0, 1.0, 0.0], [3.0, 0.5, 1.0], [1.5, 2.5, 0.25], [0.0, 4.0, 2.0]]
    blended = blend_series(series, _WEIGHTS)
    for step in range(_STEPS):
        seasonal = math.fsum(
            row[step] * days for row, days in zip(series, _DAYS, strict=True)
        )
        assert blended[step] * 365 == pytest.approx(seasonal, rel=1e-12), (
            f"스텝 {step}: 접은 하루의 365배 {blended[step] * 365!r} 가 "
            f"계절 합 {seasonal!r} 과 다르다"
        )


def test_the_unmet_demand_of_one_season_is_not_dropped() -> None:
    """★★★ **미충족을 빼놓지 않는다** — 빼면 사실이 조용히 사라진다.

    어느 계절이 수요를 못 채웠다는 사실이 연간등가 하루에서 없어지면, 그 소멸은
    아무 예외도 내지 않고 리포트는 **다 채운 사업**을 그린다.
    """
    dispatches = [
        _dispatch("r", [1.0, 1.0, 1.0], unmet=[0.0, 0.0, 0.0]),
        _dispatch("r", [1.0, 1.0, 1.0], unmet=[0.0, 2.0, 0.0]),
        _dispatch("r", [1.0, 1.0, 1.0], unmet=[0.0, 0.0, 0.0]),
        _dispatch("r", [1.0, 1.0, 1.0], unmet=[0.0, 0.0, 0.0]),
    ]
    blended = blend_dispatch(dispatches, _WEIGHTS)
    unmet = blended.per_resource["r"].unmet("electric")
    assert unmet[1] == pytest.approx(2.0 * _WEIGHTS[1]), (
        f"여름의 미충족 2.0kWh 가 접힌 하루에서 {unmet[1]!r} 이 됐다"
    )
    assert math.fsum(unmet) > 0.0, "미충족이 접기에서 통째로 사라졌다"


def test_the_diagnostic_notes_of_every_season_survive_the_fold() -> None:
    """★★ 진단 문구는 **합치지 않고 모은다** — 같은 문구는 한 번만, 차례는 처음 나온 차례.

    계절 하나가 낸 문구를 버리면 그 계절이 무엇을 못 했는지가 연간등가 하루에서
    사라진다. `scripts/check_unread_extension_points.py` 가 `DispatchResult.
    notes` 를 부채 목록에서 지운 근거가 이 읽기다.
    """
    def with_notes(notes: tuple[str, ...]) -> SystemDispatch:
        base = _dispatch("r", [1.0, 1.0, 1.0])
        result = base.per_resource["r"]
        return SystemDispatch(
            per_resource={
                "r": DispatchResult(
                    electric=list(result.electric),
                    heat=list(result.heat),
                    cool=list(result.cool),
                    fuel=list(result.fuel),
                    notes=notes,
                )
            },
            grid_import=list(base.grid_import),
            grid_export=list(base.grid_export),
        )

    blended = blend_dispatch(
        [
            with_notes(("봄 문구",)),
            with_notes(("여름 문구", "봄 문구")),
            with_notes(()),
            with_notes(("겨울 문구",)),
        ],
        _WEIGHTS,
    )
    assert blended.per_resource["r"].notes == ("봄 문구", "여름 문구", "겨울 문구")
