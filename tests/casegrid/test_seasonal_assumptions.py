"""배포 자산의 **계절 가정**과 그것을 결론에 잇는 **대표일**을 잰다 (R60/WP-4).

사용자 판정 `docs/decisions-2026-09-04-R59b.md` §3 이 R56 의 방침
(*「실측이 없으니 값을 비운다」*)을 뒤집었다 — *「일단 필요한 사항을 **가정하여
설정**하고, **추후 변경할 수 있게 설계**해」*. 그래서 자산의 `seasons:` 가
가정값으로 채워졌고, 이 파일이 그 채움을 두 층에서 붙든다.

    T1~T4  **자산**이 말이 되는가 — 달력·몫·형상의 **성질**
    N1~N4  **대표일**이 그것을 결론에 잇는 방식 — 항등식·기본 경로·혼합·총량

## ★★★ 왜 「값」이 아니라 「성질」을 재는가

여기 있는 계절 몫·일수는 **가정**이며 실측이 아니다. 회신(TMY·가구 실측)이
오면 **바뀐다.** 수를 시험에 박으면 그날 시험이 함께 거짓이 되고, 그때
*「값을 갱신했다」* 와 *「계절성이 깨졌다」* 가 구별되지 않는다. 그래서
붙드는 것은 **부등호와 항등식**이다 — 냉난방으로 여름·겨울 사용량이 크다는
것, 겨울 일사가 여름보다 약하다는 것, 해가 없는 시간에는 발전이 없다는 것,
그리고 **형상은 배분이지 값이 아니라는 것**.

⚠ 자산의 수 자체(0.23·0.28 …)를 이 파일에 옮겨 적지 않는다. 옮겨 적으면
자산의 사본이 되고, 자산을 고칠 때 사본만 낡는다.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from core.casegrid.e2e_runner import (
    DAYS_PER_YEAR,
    HOURS_PER_YEAR,
    PV_CAPACITY_FACTOR,
    run_single_case_e2e,
)
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.profiles import (
    GENERATION_SHAPE_KEY,
    LOAD_SHAPE_KEY,
    SHARE_TOLERANCE,
    load_daily_shapes,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"

#: 연간 일수. 배포 경로와 같은 수이며 러너에서 받아 온다.
DAYS = DAYS_PER_YEAR

#: 부동소수 누적 오차만 흡수하는 폭. 읽는 쪽이 `share` 합에 쓰는 것과 같은
#: 상수를 가져다 쓴다 — 여기서 따로 정하면 두 허용오차가 갈린다.
TOLERANCE = SHARE_TOLERANCE

#: 자산이 선언한 계절 이름. **자산에서 읽지 않고 여기 적는 유일한 것**이며,
#: 부등호를 「어느 계절과 어느 계절 사이」로 쓰려면 이름이 필요하다. 이름이
#: 바뀌면 아래 T1 이 먼저 그 사실을 말한다.
SPRING, SUMMER, AUTUMN, WINTER = "봄", "여름", "가을", "겨울"


def _shares(shape: Any) -> dict[str, float]:
    return {season.name: season.share for season in shape.seasons}


def _weights(shape: Any, name: str) -> tuple[float, ...]:
    for season, weights in shape.by_season:
        if season.name == name:
            return weights
    raise AssertionError(f"{shape.key} 에 계절 {name!r} 이 없다")


def _lit_steps(weights: tuple[float, ...]) -> list[int]:
    return [i for i, w in enumerate(weights) if w != 0.0]


# ── T1~T4 · 자산이 말이 되는가 ────────────────────────────────────────────


def test_t1_both_shapes_declare_four_seasons_that_add_up_to_a_year() -> None:
    """**T1** — 계절 넷 · 일수 합이 **365** · 몫 합이 **정확히 1**.

    ⚠ 읽는 쪽이 몫 합을 이미 거부한다(`DailyShape.__post_init__`). 그래도 여기서
    다시 재는 이유는 **거부가 도는 것**과 **배포 자산이 그 조건을 만족하는 것**이
    다른 사실이기 때문이다 — 자산이 아예 계절을 안 쓰면 거부는 초록불이고 이
    시험은 빨간불이다.
    """
    shapes = load_daily_shapes()
    for shape in (shapes.load, shapes.generation):
        names = [season.name for season in shape.seasons]
        assert names == [SPRING, SUMMER, AUTUMN, WINTER], (
            f"{shape.key} 의 계절이 {names} 다 — 봄·여름·가을·겨울 넷을 "
            "연중 차례로 적어야 한다(`spread()` 가 그 차례로 이어 붙인다)"
        )
        days = [season.days for season in shape.seasons]
        assert None not in days, f"{shape.key} 에 일수를 비운 계절이 있다: {days}"
        assert sum(int(d) for d in days if d is not None) == DAYS, (
            f"{shape.key} 의 계절 일수 합이 {days} → {sum(int(d) for d in days if d)} "
            f"이다 — 연간 일수 {DAYS} 와 같아야 달력이 맞는다"
        )
        total = math.fsum(season.share for season in shape.seasons)
        assert abs(total - 1.0) <= TOLERANCE, (
            f"{shape.key} 의 몫 합이 {total!r} 이다 — 1 이 아니면 연간 에너지가 "
            "조용히 사라지거나 없던 것이 생긴다"
        )


def test_t2_load_and_generation_stand_on_the_same_calendar() -> None:
    """**T2** — 두 항목의 **계절 이름과 일수가 같다**.

    다르면 같은 인덱스가 서로 다른 날을 가리킨다. 읽는 쪽이 거부하지만(그 거부는
    `test_seasonal_axis.py` 가 잰다) **배포 자산이 실제로 같은 달력 위에 서는
    것**은 다른 사실이다.
    """
    shapes = load_daily_shapes()
    load = [(s.name, s.days) for s in shapes.load.seasons]
    generation = [(s.name, s.days) for s in shapes.generation.seasons]
    assert load == generation, (
        f"부하 달력 {load} · 발전 달력 {generation} — 이름과 일수가 같아야 "
        "두 시계열의 같은 인덱스가 같은 날을 가리킨다"
    )


def test_t3_the_shares_carry_the_seasonality_the_asset_claims() -> None:
    """**T3** — 몫의 **부등호**. ⚠ 특정 수가 아니라 방향을 잰다.

    부하는 냉난방 때문에 **여름·겨울이 봄·가을보다** 크고, 발전은 겨울 일사가
    약해 **여름이 겨울보다** 크다. 그것이 자산의 `replace_when` 이 결손으로
    적어 온 축이며, 값이 갱신돼도 **그 성질은 남는다.**

    ⚠ 수를 박으면 회신이 왔을 때 *「값을 갱신했다」* 와 *「계절성이 깨졌다」* 가
    구별되지 않는다.
    """
    shapes = load_daily_shapes()

    load = _shares(shapes.load)
    for cold_or_hot in (SUMMER, WINTER):
        for mild in (SPRING, AUTUMN):
            assert load[cold_or_hot] > load[mild], (
                f"부하 몫이 {cold_or_hot} {load[cold_or_hot]} · {mild} "
                f"{load[mild]} 다 — 냉난방으로 여름·겨울이 커야 한다"
            )

    generation = _shares(shapes.generation)
    assert generation[SUMMER] > generation[WINTER], (
        f"발전 몫이 여름 {generation[SUMMER]} · 겨울 {generation[WINTER]} 다 — "
        "「겨울철 일사가 여름철보다 약하다」를 담지 못한다"
    )
    assert generation[WINTER] == min(generation.values()), (
        f"발전 몫에서 겨울이 가장 작지 않다: {generation}"
    )
    assert all(share > 0.0 for share in generation.values()), (
        f"몫이 0 인 계절이 있다: {generation} — 어느 계절도 0 이 아니어야 한다"
    )
    assert all(share > 0.0 for share in load.values()), (
        f"부하 몫이 0 인 계절이 있다: {load}"
    )


def test_t4_the_sun_is_off_at_night_and_up_longer_in_summer() -> None:
    """**T4** — 해가 없는 스텝은 **정확히 0** 이고 **낮 길이가 계절마다 다르다**.

    ⚠ **몇 시부터 몇 시까지인지는 적지 않는다** — 적으면 자산의 사본이 되고,
    일출·일몰을 옮기는 정당한 갱신이 이 검사를 빨간불로 만든다. 붙드는 것은
    ⓐ 0 인 스텝이 있고 그 값이 **근사가 아니라 정확히 0** 이라는 것,
    ⓑ 켜진 구간이 **끊기지 않는다**는 것, ⓒ **겨울 < 여름**이라는 것.
    """
    generation = load_daily_shapes().generation
    lit: dict[str, list[int]] = {}
    for season, weights in generation.by_season:
        steps_lit = _lit_steps(weights)
        assert steps_lit, f"계절 「{season.name}」 이 전 스텝 0 이다"
        assert len(steps_lit) < len(weights), (
            f"계절 「{season.name}」 에 0 인 스텝이 하나도 없다 — 해가 없는 "
            "시간이 없는 형상이며 태양광의 성질이 아니다"
        )
        for index, weight in enumerate(weights):
            if index not in steps_lit:
                assert weight == 0.0, (
                    f"계절 「{season.name}」 의 {index}번 스텝이 {weight!r} 다 — "
                    "해가 없는 스텝은 근사값이 아니라 정확히 0 이어야 한다"
                )
        assert steps_lit == list(range(steps_lit[0], steps_lit[-1] + 1)), (
            f"계절 「{season.name}」 의 0 이 아닌 스텝이 이어지지 않는다: {steps_lit}"
        )
        lit[season.name] = steps_lit

    assert len(lit[WINTER]) < len(lit[SUMMER]), (
        f"낮 길이가 겨울 {len(lit[WINTER])}스텝 · 여름 {len(lit[SUMMER])}스텝 "
        "이다 — 겨울이 더 짧아야 한다"
    )


# ── N1~N4 · 대표일이 그것을 결론에 잇는 방식 ──────────────────────────────


def test_n1_the_representative_day_times_the_year_is_the_total() -> None:
    """**N1** — 항등식 `Σ_j rep[j] × days == total`.

    계절 하나의 하루 총량은 `total × share / 계절일수` 이고 그 계절이 그만큼
    되풀이되므로 계절일수가 **약분된다** — 그래서 `rep[j]` 를 `days` 로 나눠
    두면 다시 `days` 를 곱했을 때 총량이 되돌아온다. 이 항등식이 깨지면
    **배포 실행이 대장과 다른 총량 위에서 결론을 낸다.**

    ⚠ 허용오차를 명시한다 — 부동소수 누적분만 흡수한다.
    """
    shapes = load_daily_shapes()
    for shape in (shapes.load, shapes.generation):
        for total in (1.0, 3_600.0, 3_942.0, 1_000_000.0):
            day = shape.representative_day(total, days=DAYS)
            assert len(day) == shape.steps
            assert math.fsum(day) * DAYS == pytest.approx(total, rel=1e-12), (
                f"{shape.key} · 총량 {total} — 대표일 합 {math.fsum(day)} 을 "
                f"{DAYS} 배 한 값이 총량과 다르다"
            )
            assert all(value >= 0.0 for value in day), (
                f"{shape.key} 의 대표일에 음수 스텝이 있다: {day}"
            )


def test_n2_one_season_gives_back_exactly_the_first_day_of_spread(
    tmp_path: Path,
) -> None:
    """**N2** — 계절이 하나(`연중`)면 `spread()` 의 **앞 하루와 원소 하나까지 같다**.

    계절 축이 서기 전과 같은 수라는 성질이며, `spread()` 독스트링이 적어 둔 것과
    같은 자리다. 이 성질이 없으면 *「계절을 안 쓰는 자산의 결론이 종전과 같다」*
    가 성립하지 않고, 그때 이 라운드의 변경이 **계절과 무관한 회귀**를 숨긴다.
    """
    path = _asset(tmp_path, seasons=None)
    shapes = load_daily_shapes(path)
    total = 4_000.0
    for shape in (shapes.load, shapes.generation):
        day = shape.representative_day(total, days=DAYS)
        first_day_of_spread = shape.spread(total, days=DAYS)[: shape.steps]
        assert list(day) == first_day_of_spread, (
            f"{shape.key} · 계절 하나인데 대표일이 `spread()` 의 앞 하루와 "
            f"다르다\n  대표일 {day}\n  spread {first_day_of_spread}"
        )


def test_n3_the_representative_day_is_a_share_weighted_blend(tmp_path: Path) -> None:
    """**N3** — 대표일은 **몫 가중 혼합**이다.

    둘을 함께 붙든다.

        ⓐ 어느 **한 계절의 하루와도 같지 않다** — 같으면 그것은 혼합이 아니라
          한 계절을 고른 것이고, R60/WP-4 가 실측한 「첫 계절의 하루」 결함이
          바로 그 형태다
        ⓑ **몫을 바꾸면 대표일이 그에 맞게 바뀐다** — 몫을 읽지 않는 구현은
          ⓐ 를 통과할 수 있어도 여기서 걸린다

    ⚠ 여기 쓰는 몫은 **시험용 가정값이며 사업 전망이 아니다.**
    """
    generation = load_daily_shapes().generation
    total = 10_000.0
    day = generation.representative_day(total, days=DAYS)

    # ⓐ — 어느 계절의 하루와도 다르다.
    for season, weights in generation.by_season:
        season_day = [
            total * season.share * weight / int(season.days or DAYS)
            for weight in weights
        ]
        assert list(day) != pytest.approx(season_day), (
            f"대표일이 계절 「{season.name}」 의 하루와 같다 — 혼합이 아니라 "
            "한 계절을 고른 것이다"
        )

    # ⓑ — 몫을 바꾸면 대표일이 따라 바뀐다. 겨울 몫을 여름과 맞바꾼 자산을
    #     세워 견준다(달력·형상은 그대로이므로 움직인 것은 몫뿐이다).
    swapped = load_daily_shapes(_asset(tmp_path, seasons=_swapped_shares(generation)))
    swapped_day = swapped.generation.representative_day(total, days=DAYS)
    assert list(swapped_day) != pytest.approx(list(day)), (
        "여름과 겨울의 몫을 맞바꿨는데 대표일이 그대로다 — 대표일이 몫을 "
        "읽지 않는다"
    )
    assert math.fsum(swapped_day) * DAYS == pytest.approx(total, rel=1e-12), (
        "몫을 바꾼 뒤 총량이 보존되지 않는다"
    )


def test_n4_a_seasonal_asset_still_annualises_to_the_ledger_totals(
    tmp_path: Path,
) -> None:
    """**N4** ★★★ — 계절 넷이 선 자산에서도 **연간화 총량이 대장값과 같다**.

    ## 왜 새로 세우는가

    `tests/report/test_shaped_run_invariants.py` 의 두 시험이 같은 성질을
    **배포 자산**에 대고 잰다. 그러나 그것은 배포 자산이 계절을 갖는 동안에만
    계절 갈래를 밟는다 — 자산이 계절을 비우는 날 그 시험은 초록불인 채
    **계절 갈래를 아무도 밟지 않게** 된다. 그래서 계절 자산을 **시험이 직접
    세워** 같은 성질을 잰다. **그 파일의 기존 시험은 고치지 않았다.**

    ## 무엇이 걸리나

    러너가 `spread()` 를 넘기면 자원이 잘라 쓰는 앞 하루가 **첫 계절의 하루**가
    되고, 그것을 365배 한 값이 대장·설계 변수의 총량과 어긋난다 — R60/WP-4 가
    실측했다(발전 +281kWh/년 · 부하 −315kWh/년). 여기서 걸린다.

    ⚠ 여기 쓰는 계절 몫은 **시험용 가정값이며 사업 전망이 아니다.**
    """
    levels = build_level_map(_ASSUMPTIONS)
    load_total = float(levels["household_load_annual_kwh"]["base"])
    expected_generation = (
        levels["pv_capacity_kw"]["base"] * PV_CAPACITY_FACTOR * HOURS_PER_YEAR
    )
    outcome = run_single_case_e2e(
        {},
        level_map=levels,
        horizon_years=20,
        daily_shapes=load_daily_shapes(_asset(tmp_path, seasons=_TEST_SEASONS)),
        annual_load_kwh=load_total,
    )
    daily_generation = sum(outcome.dispatch.per_resource["e2e-pv"].electric)
    daily_load = -sum(outcome.dispatch.per_resource["e2e-load"].electric)

    assert daily_generation * DAYS == pytest.approx(expected_generation, rel=1e-6), (
        f"계절 자산의 연간화 발전량이 {daily_generation * DAYS:,.0f}kWh 다 "
        f"(기대 {expected_generation:,.0f}) — 형상이 총량을 바꿨다"
    )
    assert daily_load * DAYS == pytest.approx(load_total, rel=1e-6), (
        f"계절 자산의 연간화 부하가 {daily_load * DAYS:,.0f}kWh 다 "
        f"(대장 {load_total:,.0f}) — 형상이 총량을 바꿨다"
    )


# ── 시험용 자산 ───────────────────────────────────────────────────────────

#: 시험용 계절 넷 — **가정값이며 사업 전망이 아니다. 리포트·검토서에 인용하지
#: 마라.** 배포 자산의 수를 베끼지 않는다(베끼면 자산의 사본이 된다) — 일수 합
#: 365 · 몫 합 1.0 이라는 조건만 만족하는 다른 수다. 하루 안 모양은 발전이
#: **밤에 0 인** 꼴로 두어 `PV` 가 받아들이는 시계열이 되게 한다.
_TEST_SEASONS: tuple[tuple[str, int, float], ...] = (
    (SPRING, 92, 0.25),
    (SUMMER, 92, 0.35),
    (AUTUMN, 91, 0.24),
    (WINTER, 90, 0.16),
)

#: 24스텝 대표일 한 벌. 밤 여덟 스텝을 0 으로 두어 발전 형상의 성질을 지킨다.
_TEST_DAY: list[float] = [0.0] * 6 + [1.0] * 14 + [0.0] * 4


def _asset(tmp_path: Path, *, seasons: Any) -> Path:
    """임시 자산 파일. **배포 자산은 건드리지 않는다.**

    `seasons` 가 `None` 이면 계절을 선언하지 않은(`weights:` 만 있는) 자산이다.
    """
    if seasons is None:
        body: dict[str, Any] = {"weights": list(_TEST_DAY)}
    else:
        body = {
            "seasons": [
                {
                    "name": name,
                    "days": days,
                    "share": share,
                    "weights": list(weights),
                }
                for name, days, share, weights in _with_weights(seasons)
            ]
        }
    profiles = [
        {
            "key": key,
            "title": "시험용 형상",
            "confidence": "가정",
            "derivation_method": "시험용 가정값이며 사업 전망이 아니다.",
            **body,
        }
        for key in (LOAD_SHAPE_KEY, GENERATION_SHAPE_KEY)
    ]
    path = tmp_path / f"profiles-{'seasonal' if seasons else 'plain'}.yaml"
    path.write_text(
        yaml.safe_dump(
            {"version": 1, "profiles": profiles}, allow_unicode=True, sort_keys=False
        ),
        encoding="utf-8",
    )
    return path


def _with_weights(
    seasons: tuple[tuple[str, int, float], ...],
) -> list[tuple[str, int, float, list[float]]]:
    return [(name, days, share, list(_TEST_DAY)) for name, days, share in seasons]


def _swapped_shares(shape: Any) -> tuple[tuple[str, int, float], ...]:
    """배포 자산의 달력을 그대로 쓰되 **여름과 겨울의 몫만 맞바꾼** 계절 목록.

    형상·일수는 그대로이므로 대표일이 달라졌다면 그것은 **몫 때문**이다.
    """
    shares = _shares(shape)
    swapped = dict(shares)
    swapped[SUMMER], swapped[WINTER] = shares[WINTER], shares[SUMMER]
    return tuple(
        (season.name, int(season.days or DAYS), swapped[season.name])
        for season in shape.seasons
    )
