"""`DailyShape.representative_day_by_season()` — **계절 하나의 대표일**이 성립하는가.

배포 실행은 8,760 을 쓰지 않는다. 24스텝 하루 한 벌을 돌리고 365배하므로
(`e2e_runner` 의 `DispatchContext(steps=STEPS_PER_DAY)`), R60 이 세운
`representative_day()` 가 계절을 **몫 가중 평균 하루 하나로 접는다.** 접힌 뒤에는
계절 간 하루 차이가 운전에 하나도 남지 않는다.

이 파일이 붙드는 것은 그 **접기 전 해상도**다 — 계절마다 (계절, 그 계절의 대표일,
그 계절의 일수). 다음 WP 가 이것을 계절일수로 가중 합산하는 운전을 세운다.

    가  Σ(계절 대표일 합 × 계절일수) == total      연간 총량 보존
    나  Σ(계절일수) == days                        달력이 닫힌다
    다  계절 하나(`연중`)면 `representative_day()` 와 **원소 하나까지** 같다
    라  계절 대표일을 일수로 가중 평균하면 `representative_day()` 와 같다
    마  계절을 적는 **차례를 바꿔도** 가·나·다·라가 그대로다

⚠⚠ **「마」가 이 파일의 요점이다.** R60/WP-4 가 실측한 것이 *「계절을 적는 차례만
바꿔도 연간 발전이 +281kWh 생기고 연간 부하가 −315kWh 사라진다」* 였다. 그것은
`spread()` 가 계절을 **이어 붙이기** 때문에 앞 하루가 「첫 계절의 하루」가 되어
생긴 일이고, 새 메서드가 그 함정을 다시 열지 않는다는 증거가 「마」다. 아래
`test_spread_is_order_dependent_and_that_is_why_the_new_method_is_measured` 가
그 대조군이다.

⚠ **손계산은 이 파일 안에서 직접 세운다.** 구현을 다시 불러 비교하면 동어반복이고,
이 저장소가 R35 에 실제로 밟은 형태다.

⚠⚠ 여기 쓰는 계절 일수·몫·형상은 전부 **시험용 가정값이며 사업 전망이 아니다.**
배포 자산(`fixtures/profiles/representative-day.yaml`)의 계절 값도 **가정**이고 이
파일의 시험용 수와는 **다른 수**다 — 섞지 마라. 이 수를 리포트·검토서에 인용하지 마라.
"""
from __future__ import annotations

import math
from itertools import permutations
from pathlib import Path
from typing import Any

import pytest

from core.casegrid.profiles import (
    GENERATION_SHAPE_KEY,
    LOAD_SHAPE_KEY,
    YEAR_ROUND,
    DailyShape,
    load_daily_shapes,
)
from tests.casegrid.test_seasonal_axis import (
    DAYS,
    _asset,
    _item,
    _seasonal_asset,
)

#: 이 파일의 시험 자산이 쓰는 스텝 수. **24 를 다 쓰지 않는다** — 계절 경계
#: 인덱스를 눈으로 따라갈 수 있게 4 로 줄인다. ⚠ 이웃 파일에서 가져오지 않고
#: 여기 세운다 — 아래 `SHAPED_SEASONS` 의 가중치 길이와 **한 곳에서** 맞아야
#: 하고, 남의 파일이 그 수를 고치면 이 파일이 조용히 어긋난다.
STEPS = 4

#: 시험용 계절 넷 — **가정값이며 사업 전망이 아니다.** 일수 합 365 · 몫 합 1.0.
#: ⚠ `test_seasonal_axis.FOUR_SEASONS` 와 달리 **계절마다 형상이 다르다** —
#: 형상이 전부 같으면 「차례를 바꿨다」가 값에 아무 흔적도 남기지 못해 「마」가
#: 무엇을 재는지 알 수 없다(평평한 하루끼리는 뒤섞어도 같은 하루다).
SHAPED_SEASONS: list[dict[str, Any]] = [
    {"name": "봄", "days": 92, "share": 0.26, "weights": [0.10, 0.20, 0.30, 0.40]},
    {"name": "여름", "days": 92, "share": 0.34, "weights": [0.40, 0.30, 0.20, 0.10]},
    {"name": "가을", "days": 91, "share": 0.25, "weights": [0.25, 0.25, 0.25, 0.25]},
    {"name": "겨울", "days": 90, "share": 0.15, "weights": [0.00, 0.50, 0.50, 0.00]},
]

TOTAL = 10_000.0


def _shaped(tmp_path: Path, seasons: list[dict[str, Any]]) -> DailyShape:
    """시험용 계절 자산 하나를 읽어 발전 형상을 돌려준다.

    ⚠ 자산 파일은 **읽는 즉시 쓸모가 끝난다** — 형상은 값으로 들고 나오므로
    같은 `tmp_path` 에 덮어써도 앞서 읽은 형상이 달라지지 않는다.
    """
    return load_daily_shapes(_seasonal_asset(tmp_path, seasons)).generation


def _year_round(tmp_path: Path, weights: list[float]) -> DailyShape:
    """`seasons:` 를 적지 않은 자산 — 읽는 쪽이 `연중` 한 계절로 세운다."""
    path = _asset(
        tmp_path,
        _item(LOAD_SHAPE_KEY, weights=list(weights)),
        _item(GENERATION_SHAPE_KEY, weights=list(weights)),
    )
    return load_daily_shapes(path).generation


def _annual_total_of(
    by_season: tuple[tuple[Any, tuple[float, ...], int], ...],
) -> float:
    """성질 「가」의 좌변 — **시험이 직접 센다.**

    계절 대표일 하나의 합이 그 계절의 **하루** 에너지이고, 그 계절이 계절일수만큼
    되풀이되므로 곱이 그 계절의 연간 몫이다.
    """
    return math.fsum(
        math.fsum(day) * season_days for _season, day, season_days in by_season
    )


def _day_weighted_mean_of(
    by_season: tuple[tuple[Any, tuple[float, ...], int], ...], *, days: int, steps: int
) -> tuple[float, ...]:
    """성질 「라」의 좌변 — 계절 대표일을 **일수로 가중 평균**한다."""
    return tuple(
        math.fsum(day[step] * season_days for _season, day, season_days in by_season)
        / days
        for step in range(steps)
    )


def _by_name(
    by_season: tuple[tuple[Any, tuple[float, ...], int], ...],
) -> dict[str, tuple[tuple[float, ...], int]]:
    """차례를 지운 꼴 — 「어느 계절이 어떤 하루를 갖는가」만 남긴다."""
    return {season.name: (day, season_days) for season, day, season_days in by_season}


# ── 가 · 연간 총량 보존 ───────────────────────────────────────────────────


def test_season_days_weighted_sum_returns_the_annual_total(tmp_path: Path) -> None:
    """★★ 「가」 Σ(계절 대표일 합 × 계절일수) == `total`.

    안 되면 **에너지가 생기거나 사라진다.** 형상은 배분이지 값이 아니므로,
    해상도를 계절로 올린 뒤에도 총량은 그대로 대장·설계 변수의 것이어야 한다.

    ⚠ 여기 쓰는 일수·몫은 시험용 가정값이며 사업 전망이 아니다.
    """
    shape = _shaped(tmp_path, SHAPED_SEASONS)
    by_season = shape.representative_day_by_season(TOTAL, days=DAYS)

    assert len(by_season) == len(SHAPED_SEASONS)
    assert _annual_total_of(by_season) == pytest.approx(TOTAL), (
        "계절 대표일을 계절일수만큼 되풀이한 합이 연간 총량과 다르다 — "
        "에너지가 생기거나 사라졌다"
    )


def test_the_deployed_asset_also_preserves_its_annual_total() -> None:
    """★ 「가」·「나」·「라」를 **배포 자산**으로 다시 잰다.

    시험용 자산만 재면 *「이 시험이 세운 수에서는 성립한다」* 까지만 말한다.
    결론이 서는 것은 배포 자산이므로 그것으로도 재야 한다.
    """
    shapes = load_daily_shapes()
    for shape in (shapes.load, shapes.generation):
        by_season = shape.representative_day_by_season(TOTAL, days=DAYS)

        assert _annual_total_of(by_season) == pytest.approx(TOTAL), shape.key
        assert sum(season_days for _s, _d, season_days in by_season) == DAYS, shape.key
        assert _day_weighted_mean_of(
            by_season, days=DAYS, steps=shape.steps
        ) == pytest.approx(shape.representative_day(TOTAL, days=DAYS)), shape.key


# ── 나 · 달력이 닫힌다 ───────────────────────────────────────────────────


def test_the_season_day_counts_close_the_calendar(tmp_path: Path) -> None:
    """★ 「나」 Σ(계절일수) == `days`, 그리고 그 일수는 **`spread()` 와 같은 자리**에서 온다.

    일수를 새로 세면 두 곳에 사는 사실이 생기고 한쪽만 고쳐진다 — 그래서
    `_calendar_days()` 하나에서 받는다. 아래 둘째 단언이 그 사실을 붙든다.

    ⚠ 여기 쓰는 일수·몫은 시험용 가정값이며 사업 전망이 아니다.
    """
    shape = _shaped(tmp_path, SHAPED_SEASONS)
    by_season = shape.representative_day_by_season(TOTAL, days=DAYS)

    counted = [season_days for _season, _day, season_days in by_season]
    assert sum(counted) == DAYS
    # 자산이 적은 일수 그대로다 — 「합만 맞고 배분이 다르다」를 함께 막는다.
    assert counted == [int(season["days"]) for season in SHAPED_SEASONS]


def test_a_calendar_that_does_not_add_up_is_refused(tmp_path: Path) -> None:
    """★ 「나」의 뒷면 — 일수 합이 받은 `days` 와 다르면 **거부**한다.

    `spread()` 와 같은 `_calendar_days()` 를 쓰므로 그쪽의 거부를 그대로 물려받는다.
    조용히 넘기면 계절 축이 연도와 어긋난 채로 운전이 선다.
    """
    shape = _shaped(tmp_path, SHAPED_SEASONS)
    with pytest.raises(ValueError, match="일수"):
        shape.representative_day_by_season(TOTAL, days=DAYS - 1)


# ── 다 · 계절 하나면 종전과 원소 하나까지 같다 ────────────────────────────


def test_one_season_gives_exactly_the_folded_representative_day(tmp_path: Path) -> None:
    """★★ 「다」 계절이 `연중` 하나뿐이면 `representative_day()` 와 **원소 하나까지** 같다.

    계절 축이 서기 전과의 연속성이다 — `spread()` 가 갖는 성질과 같은 자리이며,
    `approx` 가 아니라 **`==`** 로 잰다. 부동소수 마지막 자리가 어긋나면 두
    메서드가 「같은 자산의 다른 해상도」라는 말이 거짓이 된다.

    ⚠ 여기 쓰는 가중치는 시험용 가정값이며 사업 전망이 아니다.
    """
    shape = _year_round(tmp_path, [0.10, 0.20, 0.30, 0.40])
    by_season = shape.representative_day_by_season(TOTAL, days=DAYS)

    assert len(by_season) == 1
    season, day, season_days = by_season[0]
    assert season.name == YEAR_ROUND
    assert season_days == DAYS, (
        "계절 하나이고 일수가 열려 있으면 읽는 쪽이 준 `days` 전부여야 한다"
    )
    assert day == shape.representative_day(TOTAL, days=DAYS), (
        "계절 하나일 때 두 메서드가 원소 하나까지 같지 않다 — 계절 축이 서기 "
        "전과의 연속성이 깨졌다"
    )


def test_each_season_day_is_exactly_what_spread_lays_down_for_that_season(
    tmp_path: Path,
) -> None:
    """★★ 계절 대표일이 `spread()` 가 **그 계절에 펴는 하루**와 원소 하나까지 같다.

    「다」를 계절 넷으로 넓힌 것이다. 두 메서드가 다른 하루를 뜻하게 되면
    「계절별로 돌린 결과」와 「이어 붙인 결과」가 조용히 어긋난다 — 길이도 총량도
    맞은 채로 어긋나므로 아무 검사도 걸리지 않는다.

    ⚠ 경계는 이 시험이 직접 센다. 구현에서 받아오면 동어반복이다.
    ⚠ 여기 쓰는 일수·몫은 시험용 가정값이며 사업 전망이 아니다.
    """
    shape = _shaped(tmp_path, SHAPED_SEASONS)
    laid = shape.spread(TOTAL, days=DAYS)
    by_season = shape.representative_day_by_season(TOTAL, days=DAYS)

    cursor = 0
    for (season, day, season_days), declared in zip(by_season, SHAPED_SEASONS, strict=True):
        assert season.name == str(declared["name"])
        assert tuple(laid[cursor:cursor + STEPS]) == day, (
            f"{season.name} 의 대표일이 `spread()` 가 그 계절에 편 하루와 다르다"
        )
        cursor += season_days * STEPS
    assert cursor == len(laid)


# ── 라 · 일수로 가중 평균하면 접힌 하루가 된다 ────────────────────────────


def test_the_day_weighted_mean_of_the_seasons_is_the_folded_day(tmp_path: Path) -> None:
    """★★ 「라」 계절 대표일을 **일수로 가중 평균**하면 `representative_day()` 와 같다.

    두 메서드가 **같은 자산의 다른 해상도**임을 못 박는다. 이것이 깨지면 다음
    WP 가 세울 계절별 운전이 지금 배포 경로와 다른 총량 위에 서게 된다.

    ⚠ 여기 쓰는 일수·몫은 시험용 가정값이며 사업 전망이 아니다.
    """
    shape = _shaped(tmp_path, SHAPED_SEASONS)
    by_season = shape.representative_day_by_season(TOTAL, days=DAYS)

    assert _day_weighted_mean_of(
        by_season, days=DAYS, steps=shape.steps
    ) == pytest.approx(shape.representative_day(TOTAL, days=DAYS))


def test_the_seasons_are_not_all_the_same_day(tmp_path: Path) -> None:
    """★ 대조군 — 「라」가 **접을 것이 있어서** 성립하는지 확인한다.

    계절 대표일이 전부 같은 하루라면 「라」는 아무것도 재지 않고 초록불이다.
    그때 이 메서드는 `representative_day()` 를 계절 수만큼 되풀이한 것에
    지나지 않는다 — 계절을 넣고도 계절 차이를 표현하지 못하는 상태다.
    """
    shape = _shaped(tmp_path, SHAPED_SEASONS)
    by_name = _by_name(shape.representative_day_by_season(TOTAL, days=DAYS))

    summer_day, _summer_days = by_name["여름"]
    winter_day, _winter_days = by_name["겨울"]
    assert summer_day != winter_day
    assert math.fsum(winter_day) < math.fsum(summer_day), (
        f"겨울 하루 {math.fsum(winter_day)} · 여름 하루 {math.fsum(summer_day)} — "
        "겨울 몫을 작게 주었는데 하루 에너지가 작아지지 않았다"
    )


# ── 마 · 차례에 무감하다 ─────────────────────────────────────────────────


def test_reordering_the_seasons_changes_none_of_the_properties(tmp_path: Path) -> None:
    """★★★ 「마」 계절을 적는 **차례를 바꿔도** 가·나·다·라가 그대로다.

    R60 이 막은 것이 *「계절을 적는 차례만 바꿔도 연간 발전이 +281kWh 생기고
    연간 부하가 −315kWh 사라진다」* 였다. 36번의 위험이 정확히 **「차례가 결론을
    만든다」** 이므로, 이 메서드는 차례에 무감해야 한다.

    차례 스물넷을 **전부** 돈다 — 하나만 바꿔 보면 「그 한 자리만 우연히
    무감했다」와 구별되지 않는다.

    ⚠ 「다」는 계절이 하나일 때의 성질이라 **바꿀 차례가 없다** — 그래서 여기서는
    가·나·라 와, 그보다 강한 **「어느 계절이 어떤 하루를 갖는가가 통째로
    같다」** 를 잰다.

    ⚠ 여기 쓰는 일수·몫은 시험용 가정값이며 사업 전망이 아니다.
    """
    baseline = _shaped(tmp_path, SHAPED_SEASONS)
    baseline_by_season = baseline.representative_day_by_season(TOTAL, days=DAYS)
    baseline_by_name = _by_name(baseline_by_season)
    baseline_folded = baseline.representative_day(TOTAL, days=DAYS)

    for order in permutations(SHAPED_SEASONS):
        shuffled = _shaped(tmp_path, list(order))
        by_season = shuffled.representative_day_by_season(TOTAL, days=DAYS)
        where = " → ".join(str(season["name"]) for season in order)

        # 가
        assert _annual_total_of(by_season) == pytest.approx(TOTAL), where
        # 나
        assert sum(season_days for _s, _d, season_days in by_season) == DAYS, where
        # 라 — 접힌 하루도 **차례에 무감**해야 같은 값으로 모인다.
        assert _day_weighted_mean_of(
            by_season, days=DAYS, steps=shuffled.steps
        ) == pytest.approx(baseline_folded), where
        # 가·나·라 보다 강한 것 — 어느 계절이 어떤 하루를 갖는가가 통째로 같다.
        assert _by_name(by_season) == baseline_by_name, (
            f"차례 {where} 에서 계절별 대표일이 달라졌다 — 이 메서드가 차례에 "
            "무감하지 않다"
        )


def test_spread_is_order_dependent_and_that_is_why_the_new_method_is_measured(
    tmp_path: Path,
) -> None:
    """★★ 대조군 — **`spread()` 는 차례에 무감하지 않다.** 그것이 「마」가 있는 이유다.

    `spread()` 의 차례 의존은 **결함이 아니라 정의**다 — 계절을 이어 붙이는 것이
    그 메서드의 뜻이고 차례가 곧 연중 시간 순서다. 위험은 그 출력의 **앞 하루를
    잘라 365배** 하는 소비자 쪽에 있었고(R60/WP-4 실측), 그래서 R60 이
    `representative_day()` 를 세웠다.

    이 시험이 없으면 「마」가 *「아무것도 안 바뀌었다」* 만 붙들게 되고, 무엇을
    피한 것인지 다음 사람이 알 수 없다.

    ⚠ 이 시험은 `spread()` 의 동작을 **재기만 한다** — 고치지 않는다.
    ⚠ 여기 쓰는 일수·몫은 시험용 가정값이며 사업 전망이 아니다.
    """
    forward = _shaped(tmp_path, SHAPED_SEASONS)
    backward = _shaped(tmp_path, list(reversed(SHAPED_SEASONS)))

    forward_first_day = forward.spread(TOTAL, days=DAYS)[:STEPS]
    backward_first_day = backward.spread(TOTAL, days=DAYS)[:STEPS]
    assert forward_first_day != backward_first_day, (
        "`spread()` 의 앞 하루가 차례에 무감하다 — 그렇다면 이 대조군이 재는 "
        "함정이 사라진 것이므로 「마」의 근거 문면을 다시 적어야 한다"
    )
    # ⚠ **총량은 두 차례 모두 보존된다** — 함정은 총량이 아니라 「앞 하루」에
    # 있었다. 그것을 365배 하는 소비자에게서 R60 이 +281kWh 를 실측했다.
    assert math.fsum(forward.spread(TOTAL, days=DAYS)) == pytest.approx(TOTAL)
    assert math.fsum(backward.spread(TOTAL, days=DAYS)) == pytest.approx(TOTAL)

    # 새 메서드는 같은 자산에서 **차례를 바꿔도 계절별 하루가 그대로다.**
    assert _by_name(
        backward.representative_day_by_season(TOTAL, days=DAYS)
    ) == _by_name(forward.representative_day_by_season(TOTAL, days=DAYS))
