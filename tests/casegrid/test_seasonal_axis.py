"""계절 축이 **실제로 계절 차이를 담는가** · **결론축이 대장 총량 위에 서는가**.

사용자 판정 §4 는 *「계절별로 프로파일, 부하, 발전특성 등을 고려할 수 있도록
설계되야 함」* 이다. R56/WP-1 은 그 **축만** 세웠고, 사용자 판정 §3
(*「일단 필요한 사항을 가정하여 설정하고」*)에 따라 **R60/WP-4 가 배포 자산의
`seasons:` 를 가정으로 채웠다.**

그래서 이 파일은 둘을 함께 붙든다.

    ① 배포 경로   배포 자산이 러너에 넘기는 시계열이 손계산과 같고 **연간
                 총량이 보존된다** (결론축 회귀 방어) · 계절 값이 슬며시
                 바뀌거나 실측으로 승격되면 여기가 먼저 말한다
    ②③ 계절 경로  계절을 선언한 자산이 연간 총량을 보존하고, **몫(`share`)이
                 실제로 계절 차이를 만든다**
    ④ 거부       말이 안 되는 자산·호출이 조용히 통과하지 않는다

⚠ ①만 있으면 *「아무것도 안 바뀌었다」* 만 붙들게 되고, **축이 비어 있어도
초록불**이다. ③ 이 계절 축의 존재 증명이다.

⚠⚠ **이 파일이 세우는 계절 일수·몫은 전부 시험용 가정값이며 사업 전망이
아니다. 이 수를 리포트·검토서에 인용하지 마라.** 배포 자산
(`fixtures/profiles/representative-day.yaml`)의 계절 값도 **가정**이며 실측이
아니고, 이 파일의 시험용 수와는 **다른 수**다 — 섞지 마라.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from core.casegrid.profiles import (
    GENERATION_SHAPE_KEY,
    LOAD_SHAPE_KEY,
    DailyShape,
    Season,
    load_daily_shapes,
)

#: 연간 일수. 배포 경로(`operating_lines.DAYS_PER_YEAR`)와 같은 수다.
DAYS = 365

#: 시험 자산의 스텝 수. **24 를 다 쓰지 않는다** — 스텝 수는 두 자원에서 같기만
#: 하면 되고, 4 로 줄이면 계절 경계 인덱스를 눈으로 따라갈 수 있다.
STEPS = 4

#: 하루 안에서 평평한 대표일. 이 시험이 붙드는 것은 *일중* 배분이 아니라
#: *연중* 배분이므로, 일중 모양이 평평해야 계절 차이만 남는다.
FLAT_DAY = [1.0] * STEPS

#: 시험용 계절 넷 — **가정값이며 사업 전망이 아니다.** 일수 합 365,
#: 몫 합 1.0 이며, 겨울 몫을 여름 몫보다 작게 두어 ③ 이 잴 것이 있게 한다.
FOUR_SEASONS: list[dict[str, Any]] = [
    {"name": "봄", "days": 92, "share": 0.26, "weights": list(FLAT_DAY)},
    {"name": "여름", "days": 92, "share": 0.34, "weights": list(FLAT_DAY)},
    {"name": "가을", "days": 91, "share": 0.25, "weights": list(FLAT_DAY)},
    {"name": "겨울", "days": 90, "share": 0.15, "weights": list(FLAT_DAY)},
]


def _item(key: str, *, seasons: Any = None, weights: Any = None) -> dict[str, Any]:
    """자산 항목 하나를 세운다 — 부기는 **시험용 가정값**이라고 적는다."""
    item: dict[str, Any] = {
        "key": key,
        "title": "시험용 형상",
        "confidence": "가정",
        "derivation_method": "시험용 가정값이며 사업 전망이 아니다.",
    }
    if seasons is not None:
        item["seasons"] = seasons
    if weights is not None:
        item["weights"] = weights
    return item


def _asset(tmp_path: Path, load: dict[str, Any], generation: dict[str, Any]) -> Path:
    """임시 자산 파일을 쓴다. 배포 자산은 건드리지 않는다."""
    path = tmp_path / "seasonal-profiles.yaml"
    path.write_text(
        yaml.safe_dump(
            {"version": 1, "profiles": [load, generation]},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _seasonal_asset(tmp_path: Path, seasons: list[dict[str, Any]]) -> Path:
    """두 자원이 **같은 달력**을 선언한 계절 자산."""
    return _asset(
        tmp_path,
        _item(LOAD_SHAPE_KEY, seasons=seasons),
        _item(GENERATION_SHAPE_KEY, seasons=seasons),
    )


# ── ① 기본 경로 — 결론축 회귀 방어 ────────────────────────────────────────


def test_the_deployed_asset_feeds_the_runner_a_total_preserving_year() -> None:
    """★★ 배포 자산이 **러너에 넘기는 연간 시계열**을 손계산과 대조한다.

    ## ⚠ 이 시험이 무엇에서 무엇으로 옮겨 갔나 (R60/WP-4-fix)

    종전 문면은 *「계절을 선언하지 않은 배포 자산의 출력이 종전과 원소 하나까지
    같다」* 였고, `spread()` 의 출력을 `총량/365 × 가중치` 로 손계산해 대조했다.
    사용자 판정 §3 에 따라 자산의 `seasons:` 가 **가정으로 채워지면서** 그
    전제(계절 하나)가 거짓이 됐다.

    **그러나 이 시험이 지키던 것은 잃지 않았다.** 그것은 두 가지였다 —
    ⓐ 배포 자산이 러너에 넘기는 시계열이 **손계산과 같은가**,
    ⓑ 그 시계열의 **연간 총량이 보존되는가**(빨간불이면 결론축이 움직였다).
    재는 대상만 `spread()` 에서 러너가 실제로 부르는
    `spread_over_representative_day()` 로 옮겼고, 손계산은 여전히 **이 시험
    안에서 직접** 세운다 — 구현을 다시 불러 비교하면 동어반복이고, 이 저장소가
    R35 에 실제로 밟은 형태다.

    ⚠ ⓑ 는 계절이 채워진 지금 **더 강한 단언**이다. 계절을 이어 붙인
    `spread()` 를 그대로 넘기면 앞 하루가 「첫 계절의 하루」가 되어 연간화
    총량이 대장과 어긋나는데(R60/WP-4 실측), 아래 마지막 단언이 그것을 잡는다.
    """
    generation = load_daily_shapes().generation
    total = 4_000.0
    series = generation.spread_over_representative_day(total, days=DAYS)

    # 손계산 — 몫 가중 평균 하루를 여기서 직접 세운다.
    by_hand_day = [
        math.fsum(
            total * season.share * weights[step]
            for season, weights in generation.by_season
        )
        / DAYS
        for step in range(generation.steps)
    ]
    by_hand = [value for _day in range(DAYS) for value in by_hand_day]

    assert generation.steps == 24, (
        f"배포 자산이 {generation.steps}스텝이다 — 아래 길이 단언은 "
        "24스텝 대표일을 전제한다"
    )
    assert len(series) == 8_760, (
        f"연간 스텝 수가 {len(series)} 이다 — 24스텝을 365일 되풀이한 길이여야 한다"
    )
    assert series == pytest.approx(by_hand)
    assert math.fsum(series) == pytest.approx(total), (
        "연간 총량이 보존되지 않는다 — 형상은 배분이지 값이 아니다"
    )
    # ★★ **러너가 잡는 것은 앞 하루뿐이고 그것을 365배 한다.** 그 곱이 총량이
    # 아니면 리포트가 대장과 다른 총량 위에서 결론을 낸다.
    assert math.fsum(series[:24]) * DAYS == pytest.approx(total), (
        "앞 하루를 365배 한 값이 연간 총량과 다르다 — 배포 실행의 연간화가 "
        "대장값과 어긋난다"
    )


def test_the_deployed_asset_declares_four_seasons_and_calls_them_assumed() -> None:
    """★ 배포 자산이 계절 넷을 **가정으로** 선언하고 있다 (R60/WP-4).

    ## ⚠ 이 시험도 뒤집혔다 — 지키던 것은 같다

    종전 문면은 *「배포 자산이 계절을 선언하지 않은 채로 있다」* 였고, 그것이
    지키던 것은 *「계절 값이 슬며시 들어오면 결론축 시험보다 **먼저** 그 사실을
    말한다」* 였다. 사용자 판정 §3 이 값을 채우게 했으므로 **감시 방향만
    뒤집는다** — 이제는 *「채워진 값이 슬며시 바뀌거나 실측으로 승격되면 먼저
    말한다」* 다. 위 시험이 빨간불이 되기 전에 여기가 먼저 말한다는 성질은 그대로다.

    ⚠⚠ **신뢰도를 함께 붙든다.** 이 값들은 **가정**이며 실측이 아니다 —
    `confidence` 가 조용히 `확정` 으로 바뀌면 리포트가 *「가정값으로 채웠다」*
    를 말하지 않게 되고(`core/report/unreflected.py::_season_reason` 이 이 칸을
    읽는다), 다음 사람이 가정값을 실측으로 읽는다.
    """
    shapes = load_daily_shapes()
    for shape in (shapes.load, shapes.generation):
        assert len(shape.by_season) == 4, (
            f"{shape.key} 가 계절 {len(shape.by_season)}개를 선언했다 — "
            "R60/WP-4 는 봄·여름·가을·겨울 넷을 가정으로 채웠다"
        )
        assert shape.confidence == "가정", (
            f"{shape.key} 의 신뢰도가 {shape.confidence!r} 다 — 계절 값은 "
            "가정이며 실측이 아니다. 회신이 와서 승격한 것이라면 이 시험과 "
            "자산의 `derivation_method`·`replace_when` 을 함께 고칠 것"
        )


# ── ② 계절 경로 — 연간 총량 보존 ──────────────────────────────────────────


def test_four_seasons_preserve_the_annual_total(tmp_path: Path) -> None:
    """★ 계절 넷으로 편 뒤에도 **연간 총량**이 그대로다.

    몫이 총량을 나누는 것이지 만들거나 없애는 것이 아니다.

    ⚠ 여기 쓰는 일수·몫은 시험용 가정값이며 사업 전망이 아니다.
    """
    shapes = load_daily_shapes(_seasonal_asset(tmp_path, FOUR_SEASONS))
    total = 10_000.0
    spread = shapes.generation.spread(total, days=DAYS)

    assert len(spread) == DAYS * STEPS
    assert math.fsum(spread) == pytest.approx(total)


# ── ③ 계절 경로 — 축이 실제로 계절 차이를 담는다 ──────────────────────────


def test_a_smaller_winter_share_makes_winter_days_smaller_than_summer_days(
    tmp_path: Path,
) -> None:
    """★★ **이 시험이 이 WP 의 존재 증명이다** — 몫이 계절 차이를 만든다.

    형상만 계절별로 두고 총량을 일수에 비례해 나누면 겨울 하루와 여름 하루의
    에너지가 **같아진다.** 그러면 스케치 6절 ④의 *「겨울철 일사가 여름철보다
    약하다」* 를 구조적으로 표현할 수 없다. 몫(`share`)이 그 차이를 담는
    유일한 자리이므로, 겨울 몫을 작게 준 자산이 실제로 작은 겨울 하루를 내는지
    잰다.

    ⚠ 여기 쓰는 일수·몫은 시험용 가정값이며 사업 전망이 아니다. 이 수를
    리포트·검토서에 인용하지 마라.
    """
    shapes = load_daily_shapes(_seasonal_asset(tmp_path, FOUR_SEASONS))
    total = 10_000.0
    spread = shapes.generation.spread(total, days=DAYS)

    # 계절 경계를 시험이 직접 센다 — 구현에서 받아오면 동어반복이다.
    # ⚠ 나눗수(일수)도 **같은 순회에서** 담는다. 손으로 적으면 `FOUR_SEASONS` 의
    # 일수를 고칠 때 조용히 낡고, 그때 시험은 빨간불이 아니라 **엉뚱한 값을
    # 비교한 채 초록불**이 된다.
    bounds: dict[str, tuple[int, int, int]] = {}
    cursor = 0
    for season in FOUR_SEASONS:
        season_days = int(season["days"])
        span = season_days * STEPS
        bounds[str(season["name"])] = (cursor, cursor + span, season_days)
        cursor += span
    assert cursor == len(spread)

    summer_start, summer_end, summer_days = bounds["여름"]
    winter_start, winter_end, winter_days = bounds["겨울"]
    summer_per_day = math.fsum(spread[summer_start:summer_end]) / summer_days
    winter_per_day = math.fsum(spread[winter_start:winter_end]) / winter_days

    assert winter_per_day < summer_per_day, (
        f"겨울 하루 {winter_per_day} · 여름 하루 {summer_per_day} — 겨울 몫을 "
        "작게 주었는데 하루 에너지가 작아지지 않았다. 축이 계절 차이를 담지 "
        "못하고 있다"
    )


def test_equal_shares_would_flatten_the_seasons(tmp_path: Path) -> None:
    """★ 대조군 — 몫을 **일수에 비례**해 주면 계절 차이가 사라진다.

    ③ 이 붙드는 것이 「계절을 넣었다」가 아니라 「**몫이** 차이를 만든다」임을
    보인다. 몫이 일수 비례이면 계절 넷이어도 하루 에너지가 모두 같다 — 그것이
    5절 ②가 몫을 따로 둔 이유다.

    ⚠ 여기 쓰는 일수·몫은 시험용 가정값이며 사업 전망이 아니다.
    """
    proportional = [
        {**season, "share": int(season["days"]) / DAYS} for season in FOUR_SEASONS
    ]
    shapes = load_daily_shapes(_seasonal_asset(tmp_path, proportional))
    total = 10_000.0
    spread = shapes.generation.spread(total, days=DAYS)

    cursor = 0
    per_day: list[float] = []
    for season in proportional:
        span = int(season["days"]) * STEPS
        per_day.append(math.fsum(spread[cursor:cursor + span]) / int(season["days"]))
        cursor += span

    assert per_day == pytest.approx([total / DAYS] * len(proportional))


# ── ④ 거부가 실제로 걸린다 ────────────────────────────────────────────────


def test_shares_that_do_not_sum_to_one_are_refused(tmp_path: Path) -> None:
    """★ 몫의 합이 1 이 아니면 거부한다 — 합이 0.9 면 연간 에너지의 10%가 사라진다."""
    broken = [{**season, "share": 0.2} for season in FOUR_SEASONS]  # 합 0.8
    with pytest.raises(ValueError, match="share"):
        load_daily_shapes(_seasonal_asset(tmp_path, broken))


def test_a_season_calendar_that_does_not_add_up_to_the_year_is_refused(
    tmp_path: Path,
) -> None:
    """★ 계절 일수의 합이 받은 `days` 와 다르면 거부한다."""
    shapes = load_daily_shapes(_seasonal_asset(tmp_path, FOUR_SEASONS))
    with pytest.raises(ValueError, match="일수"):
        shapes.generation.spread(10_000.0, days=DAYS - 1)


def test_a_season_with_zero_days_is_refused_instead_of_dividing_by_zero(
    tmp_path: Path,
) -> None:
    """★ 일수 0 인 계절은 **거부**한다 — `ZeroDivisionError` 로 죽지 않는다.

    계절 하나를 「안 쓴다」는 뜻으로 `days: 0` 을 적는 것은 사람이 충분히 할 수
    있는 실수다. 그때 나오는 것이 이 저장소의 거부 메시지가 아니라 파이썬 기본
    예외이면, 무엇이 왜 성립하지 않는지 아무도 말해 주지 않는다.

    ⚠ 여기 쓰는 일수·몫은 시험용 가정값이며 사업 전망이 아니다.
    """
    zeroed = [
        {**season, "days": 0} if season["name"] == "겨울" else dict(season)
        for season in FOUR_SEASONS
    ]
    with pytest.raises(ValueError, match="양수"):
        load_daily_shapes(_seasonal_asset(tmp_path, zeroed))


def test_two_resources_on_different_season_calendars_are_refused(
    tmp_path: Path,
) -> None:
    """★ 부하와 발전의 계절 달력이 다르면 거부한다.

    길이는 맞은 채로 어긋나므로 아무 검사도 걸리지 않는다 — 같은 인덱스가 서로
    다른 날을 가리키는데도 조용하다. 스텝 수가 다를 때 거부하는 것과 같은 이유다.
    """
    renamed = [{**season, "name": season["name"] + "철"} for season in FOUR_SEASONS]
    path = _asset(
        tmp_path,
        _item(LOAD_SHAPE_KEY, seasons=FOUR_SEASONS),
        _item(GENERATION_SHAPE_KEY, seasons=renamed),
    )
    with pytest.raises(ValueError, match="달력"):
        load_daily_shapes(path)


def test_an_item_that_declares_both_seasons_and_weights_is_refused(
    tmp_path: Path,
) -> None:
    """★ `seasons:` 와 `weights:` 를 둘 다 준 항목은 거부한다.

    어느 쪽이 정본인지 말하지 않은 것이고, 둘 다 받으면 하나가 조용히 무시된다.
    """
    path = _asset(
        tmp_path,
        _item(LOAD_SHAPE_KEY, seasons=FOUR_SEASONS),
        _item(
            GENERATION_SHAPE_KEY,
            seasons=FOUR_SEASONS,
            weights=list(FLAT_DAY),
        ),
    )
    with pytest.raises(ValueError, match="둘 다"):
        load_daily_shapes(path)


def test_asking_one_shape_for_its_weights_when_it_has_four_seasons_is_refused(
    tmp_path: Path,
) -> None:
    """★★ 계절이 여럿일 때 `weights` 속성이 거부한다.

    조용히 첫 계절을 돌려주면, 계절을 넣은 뒤에도 읽는 쪽이 **봄만 보고
    「형상을 읽었다」** 가 성립한다 — 그것이 이 저장소가 반복해 만난 「검사는
    있고 재는 것이 다르다」의 형태다.
    """
    shapes = load_daily_shapes(_seasonal_asset(tmp_path, FOUR_SEASONS))
    with pytest.raises(ValueError, match="계절"):
        _ = shapes.generation.weights


def test_more_than_one_season_may_not_leave_its_day_count_open() -> None:
    """★ 계절이 여럿인데 일수를 비운 것이 있으면 거부한다.

    `days: null` 은 *「읽는 쪽이 준 `days` 전부」* 라는 뜻이므로, 계절이 여럿일
    때는 나머지를 누가 갖는지 말할 수 없다.
    """
    with pytest.raises(ValueError, match="일수"):
        DailyShape(
            key="시험용",
            title="시험용 형상",
            confidence="가정",
            derivation_method="시험용 가정값이며 사업 전망이 아니다.",
            by_season=(
                (Season(name="여름", days=None, share=0.5), tuple(FLAT_DAY)),
                (Season(name="겨울", days=180, share=0.5), tuple(FLAT_DAY)),
            ),
        )


def test_seasons_that_do_not_share_a_step_grid_are_refused() -> None:
    """★ 한 자원 안에서 계절마다 스텝 수가 다르면 거부한다 — 이어 붙일 수 없다."""
    with pytest.raises(ValueError, match="스텝"):
        DailyShape(
            key="시험용",
            title="시험용 형상",
            confidence="가정",
            derivation_method="시험용 가정값이며 사업 전망이 아니다.",
            by_season=(
                (Season(name="여름", days=183, share=0.5), (0.5, 0.5)),
                (Season(name="겨울", days=182, share=0.5), (0.25, 0.25, 0.25, 0.25)),
            ),
        )
