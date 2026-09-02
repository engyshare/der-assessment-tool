"""붙임 8 의 「계절·요일 변동」이 **계절 축의 상태를 읽어서** 적는가 (R56/WP-2).

R56/WP-1 이 형상 자산에 계절 축을 세웠다. 그 전까지 이 항목의 해소 조건은
*「연간 시계열(일사량·부하) 입력 배선」* — 곧 8,760 전량 — 하나였고, 축이 선
지금 그 문면은 **요구를 실제보다 크게 적는다**: 계절은 계절별 대표일 몇 벌로
접힌다.

    ① 인쇄된다        배포 경로 리포트에 이 항목이 실제로 실린다
    ② 계절 수를 말한다 계절 하나인 배포 자산에서 문면이 「1계절」을 말한다
    ③ ★★ 갈린다      계절 넷을 준 자산에서 `reason`·`resolves_when` 이 달라진다
    ④ 몫을 말한다      해소 조건이 형상만이 아니라 **몫(`share`)** 을 요구한다

⚠ ①②만 있으면 *「대상이 스스로 정한 문자열이 그 문자열이다」* 에 그친다 —
③ 이 **축이 실제로 읽힌다는 증명**이다. 계절 수를 읽지 않고 문면을 박아 두면
③ 만 빨간불이 된다.

⚠⚠ **이 파일이 세우는 계절 일수·몫은 전부 시험용 가정값이며 사업 전망이
아니다. 이 수를 리포트·검토서에 인용하지 마라.** 배포 자산
(`fixtures/profiles/representative-day.yaml`)에는 계절이 하나도 없다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from core.casegrid.profiles import (
    GENERATION_SHAPE_KEY,
    LOAD_SHAPE_KEY,
    load_daily_shapes,
)
from core.report.case_report import build_case_report
from core.report.narrative import render_markdown
from core.report.unreflected import _season_item, build_unreflected

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"

#: 붙임 8 이 싣는 항목 이름. 본문 3.4 표와 같은 문자열이어야 한다.
_LABEL = "계절·요일 변동"

#: 시험용 계절 넷 — **가정값이며 사업 전망이 아니다. 리포트·검토서에 인용하지
#: 마라.** 일수 합 365 · 몫 합 1.0 이며, 꼴은
#: `tests/casegrid/test_seasonal_axis.py` 의 `FOUR_SEASONS` 와 같다(부하와
#: 발전이 **같은 달력**을 적어야 자산이 거부되지 않는다).
_FOUR_SEASONS: tuple[tuple[str, int, float], ...] = (
    ("봄", 92, 0.26),
    ("여름", 92, 0.34),
    ("가을", 91, 0.25),
    ("겨울", 90, 0.15),
)


def _report():
    return build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )


def _season_entry(name: str, days: int, share: float, *, steps: int) -> dict[str, Any]:
    """계절 하나. 하루 안은 **평평하게** 둔다 — 여기서 재는 것은 일중 배분이
    아니라 *자산이 계절을 몇 개 선언했는가*이므로 일중 모양은 잡음이다.
    """
    return {"name": name, "days": days, "share": share, "weights": [1.0] * steps}


def _four_season_asset(tmp_path: Path) -> Path:
    """계절 넷을 선언한 **임시** 자산의 경로. 배포 자산은 건드리지 않는다.

    스텝 수를 배포 자산에서 읽어 맞춘다 — 손으로 적으면 배포 자산이 24스텝을
    벗어나는 날 이 시험이 *계절 수 말고 스텝 수까지* 바꾼 채 「문면이 달라졌다」
    를 통과시킨다. ③ 이 붙들려는 것은 **계절 수 하나**다.
    """
    steps = load_daily_shapes().generation.steps
    seasons = [
        _season_entry(name, days, share, steps=steps)
        for name, days, share in _FOUR_SEASONS
    ]
    profiles = [
        {
            "key": key,
            "title": "시험용 형상",
            "confidence": "가정",
            "derivation_method": "시험용 가정값이며 사업 전망이 아니다.",
            "seasons": seasons,
        }
        for key in (LOAD_SHAPE_KEY, GENERATION_SHAPE_KEY)
    ]
    path = tmp_path / "seasonal-profiles.yaml"
    path.write_text(
        yaml.safe_dump(
            {"version": 1, "profiles": profiles}, allow_unicode=True, sort_keys=False
        ),
        encoding="utf-8",
    )
    return path


def _deployed_item():
    """배포 경로 리포트가 낸 「계절·요일 변동」 한 건."""
    items = [item for item in build_unreflected(_report()) if item.label == _LABEL]
    assert len(items) == 1, (
        f"배포 경로 리포트의 미반영 항목에 「{_LABEL}」 이 {len(items)}건이다 — "
        "대표일 24스텝 모의에서는 정확히 1건이어야 한다"
    )
    return items[0]


# ── ① 인쇄된다 ────────────────────────────────────────────────────────────


def test_the_season_item_is_actually_printed_by_the_deployed_path() -> None:
    """★ 이 항목이 **실제로 실려 나간다** — 함수만 초록불인 것이 아니다.

    붙임 8 은 `build_unreflected()` 가 낸 항목을 그대로 인쇄하므로, 문면을
    아무리 정확히 고쳐도 **리포트가 그 항목을 싣지 않으면 아무도 못 본다.**
    그래서 항목 자체가 아니라 **렌더된 마크다운**에서 문면을 찾는다.
    """
    item = _deployed_item()
    text = render_markdown(_report())
    assert _LABEL in text, f"렌더된 리포트에 「{_LABEL}」 행이 없다"
    assert item.reason in text, (
        "붙임 8 이 이 항목의 「비어 있는 자리」 칸을 싣지 않는다 — "
        f"{item.reason!r}"
    )
    assert item.resolves_when in text, (
        "붙임 8 이 이 항목의 「해소 조건」 칸을 싣지 않는다 — "
        f"{item.resolves_when!r}"
    )


# ── ② 계절 수를 말한다 ────────────────────────────────────────────────────


def test_the_wording_reports_the_single_season_of_the_deployed_asset() -> None:
    """★ 배포 자산이 계절 하나이고, **문면이 그것을 말한다.**

    계절 수는 **자산이** 정한다 — 시험이 자산을 직접 읽어(`load_daily_shapes`)
    그 수를 얻고, 리포트 문면이 같은 수를 말하는지 본다. 대상이 스스로 정한
    문자열만 보면 문면을 박아 둔 구현도 통과한다.

    ⚠ 문면 전체를 단언하지 않는다 — 담겨야 하는 **조각**만 붙든다. 전체를
    박으면 문면을 다듬을 때마다 빨간불이다.
    """
    declared = len(load_daily_shapes().generation.seasons)
    assert declared == 1, (
        f"배포 자산이 계절 {declared}개를 선언했다 — R56/WP-1 은 `seasons:` 를 "
        "비운 채로 두었다. 값이 들어왔다면 아래 문면 단언이 아니라 "
        "`tests/casegrid/test_seasonal_axis.py` 가 먼저 그것을 말해야 한다"
    )
    item = _deployed_item()
    assert f"계절 {declared}개" in item.magnitude, (
        f"크기 칸이 계절 수를 말하지 않는다: {item.magnitude!r}"
    )
    assert "1계절" in item.reason, (
        f"「비어 있는 자리」 칸이 연중 1계절임을 말하지 않는다: {item.reason!r}"
    )
    assert "선언하지 않았다" in item.reason, (
        "계절 축이 선 것과 자산이 계절을 선언한 것은 다른 사건인데 문면이 "
        f"그것을 가르지 않는다: {item.reason!r}"
    )


# ── ③ ★★ 축이 읽힌다 ─────────────────────────────────────────────────────


def test_four_seasons_change_the_wording(tmp_path: Path) -> None:
    """★★ **이 시험이 이 WP 의 존재 증명이다** — 계절 넷을 주면 문면이 달라진다.

    계절 수를 읽지 않고 문면을 박아 두면 ①② 는 그대로 초록불이고 여기만
    빨간불이 된다. 이 저장소가 다섯 번 밟은 *「선언·계산은 있는데 읽는 쪽이
    없다」* 를 리포트 쪽에서 붙드는 자리다.

    ⚠ 여기 쓰는 계절 일수·몫은 **시험용 가정값이며 사업 전망이 아니다. 이 수를
    리포트·검토서에 인용하지 마라.**
    """
    hours = _report().dispatch_hours
    one_season = _season_item(hours)
    four_seasons = _season_item(hours, _four_season_asset(tmp_path))

    assert len(one_season) == 1 and len(four_seasons) == 1, (
        "계절을 넷 선언해도 항목은 남아야 한다 — 요일 변동은 그대로 미반영이고 "
        "계절 안에서는 여전히 같은 하루가 되풀이된다"
    )
    plain, seasonal = one_season[0], four_seasons[0]

    assert plain.label == seasonal.label == _LABEL, (
        "항목 이름이 상태에 따라 갈리면 본문 3.4 표와 붙임 8 이 갈린다"
    )
    assert seasonal.reason != plain.reason, (
        "계절 넷을 선언한 자산에서도 「비어 있는 자리」 문면이 그대로다 — "
        f"판정이 계절 수를 읽지 않는다: {plain.reason!r}"
    )
    assert seasonal.resolves_when != plain.resolves_when, (
        "계절 넷을 선언한 자산에서도 「해소 조건」 문면이 그대로다 — "
        f"판정이 계절 수를 읽지 않는다: {plain.resolves_when!r}"
    )
    assert f"계절 {len(_FOUR_SEASONS)}개" in seasonal.magnitude, (
        f"크기 칸이 선언된 계절 수를 말하지 않는다: {seasonal.magnitude!r}"
    )
    for name, _days, _share in _FOUR_SEASONS:
        assert name in seasonal.reason, (
            f"「비어 있는 자리」 칸이 계절 「{name}」 을 말하지 않는다: "
            f"{seasonal.reason!r}"
        )


# ── ④ 몫을 말한다 ────────────────────────────────────────────────────────


def test_the_resolution_asks_for_shares_and_not_shapes_alone() -> None:
    """★ 해소 조건이 **몫(`share`)** 을 함께 요구한다 — 형상만으로는 거짓이다.

    계절별 형상만 채우고 총량을 일수에 비례해 나누면 겨울 하루와 여름 하루의
    에너지가 **같아진다**(`core/casegrid/profiles.py` 의 `Season.share` 와
    `DailyShape.__post_init__` 이 그 자리다). *「계절별 형상만 채우면 된다」*
    고 적으면 검토자는 자산을 절반만 채우고 계절을 넣었다고 읽는다.

    ⚠ 8,760 갈래도 함께 붙든다 — 계절 접기는 그것을 **대신하지 않는다.**
    요일 변동은 계절을 채워도 남는다.
    """
    resolves = _deployed_item().resolves_when
    assert "몫" in resolves and "share" in resolves, (
        f"해소 조건이 계절별 몫(`share`)을 요구하지 않는다: {resolves!r}"
    )
    assert "형상" in resolves, (
        f"해소 조건이 계절별 대표일 형상을 요구하지 않는다: {resolves!r}"
    )
    assert "seasons:" in resolves, (
        f"해소 조건이 **어느 칸**을 채우면 되는지 가리키지 않는다: {resolves!r}"
    )
    assert "8,760" in resolves, (
        "해소 조건이 8,760 갈래를 잃었다 — 계절을 채워도 요일 변동은 남으므로 "
        f"그 갈래는 여전히 참이다: {resolves!r}"
    )
