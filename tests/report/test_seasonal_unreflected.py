"""붙임 8 의 「계절·요일 변동」이 **계절 축의 상태를 읽어서** 적는가 (R56/WP-2).

R56/WP-1 이 형상 자산에 계절 축을 세웠다. 그 전까지 이 항목의 해소 조건은
*「연간 시계열(일사량·부하) 입력 배선」* — 곧 8,760 전량 — 하나였고, 축이 선
지금 그 문면은 **요구를 실제보다 크게 적는다**: 계절은 계절별 대표일 몇 벌로
접힌다.

    ① 인쇄된다        배포 경로 리포트에 이 항목이 실제로 실린다
    ② 계절 수를 말한다 계절 넷인 배포 자산에서 문면이 계절 넷과 **신뢰도**를 말한다
    ③ ★★ 갈린다      계절 하나를 준 자산에서 `reason`·`resolves_when` 이 달라진다
    ④ 몫을 말한다      해소 조건이 형상만이 아니라 **몫(`share`)** 을 요구한다
    ⑤ ★★ 남는 결손    계절 간 하루 차이가 **결론에 서지 않는다**를 말한다

⚠ ①②만 있으면 *「대상이 스스로 정한 문자열이 그 문자열이다」* 에 그친다 —
③ 이 **축이 실제로 읽힌다는 증명**이다. 계절 수를 읽지 않고 문면을 박아 두면
③ 만 빨간불이 된다.

## ⚠⚠ 대조군이 뒤집혔다 (R60/WP-4-fix)

R60/WP-4 가 **배포 자산의 `seasons:` 를 가정으로 채웠다.** 그래서 ②는
*「배포 자산이 계절 넷을 말한다」* 가 되고, ③의 대조군은 임시 자산 쪽이
**계절 하나**가 된다 — 방향만 뒤집었고 재는 것은 같다(*「문면이 자산의 계절
수를 읽는가」*).

★★ 그리고 ⑤가 늘었다 — *「계절을 채워도 **계절 간 하루 차이는 결론에 서지
않는다**」* 를 문면이 말하는가. 배포 실행은 몫 가중 평균 대표일 한 벌을
365일로 연간화하므로 그 차이가 운전에 서지 않는데, 문면이 *「접혔다」* 로
적으면 검토자는 **계절이 결론을 가른다**고 읽는다.

⚠⚠ **이 파일이 세우는 계절 일수·몫은 전부 시험용 가정값이며 사업 전망이
아니다. 이 수를 리포트·검토서에 인용하지 마라.** 배포 자산
(`fixtures/profiles/representative-day.yaml`)의 계절 값도 **가정**이며 이
파일의 시험용 수와는 **다른 수**다 — 섞지 마라.
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


def _one_season_asset(tmp_path: Path) -> Path:
    """계절을 **선언하지 않은** 임시 자산 — ③ 의 대조군 (R60/WP-4-fix).

    배포 자산이 계절 넷을 갖게 됐으므로 「계절 하나」 쪽이 임시 자산이 됐다.
    스텝 수는 배포 자산에서 읽어 맞춘다 — 손으로 적으면 배포 자산이 24스텝을
    벗어나는 날 이 시험이 *계절 수 말고 스텝 수까지* 바꾼 채 「문면이 달라졌다」
    를 통과시킨다.
    """
    steps = load_daily_shapes().generation.steps
    profiles = [
        {
            "key": key,
            "title": "시험용 형상",
            "confidence": "가정",
            "derivation_method": "시험용 가정값이며 사업 전망이 아니다.",
            "weights": [1.0] * steps,
        }
        for key in (LOAD_SHAPE_KEY, GENERATION_SHAPE_KEY)
    ]
    path = tmp_path / "one-season-profiles.yaml"
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


def test_the_wording_reports_the_four_seasons_of_the_deployed_asset() -> None:
    """★ 배포 자산이 계절 넷이고, **문면이 그것을 말한다** (R60/WP-4-fix 로 뒤집힘).

    계절 수는 **자산이** 정한다 — 시험이 자산을 직접 읽어(`load_daily_shapes`)
    그 수를 얻고, 리포트 문면이 같은 수를 말하는지 본다. 대상이 스스로 정한
    문자열만 보면 문면을 박아 둔 구현도 통과한다.

    ⚠ 문면 전체를 단언하지 않는다 — 담겨야 하는 **조각**만 붙든다. 전체를
    박으면 문면을 다듬을 때마다 빨간불이다.
    """
    shape = load_daily_shapes().generation
    declared = len(shape.seasons)
    assert declared == 4, (
        f"배포 자산이 계절 {declared}개를 선언했다 — R60/WP-4 는 넷을 가정으로 "
        "채웠다. 수가 달라졌다면 아래 문면 단언이 아니라 "
        "`tests/casegrid/test_seasonal_axis.py` 가 먼저 그것을 말해야 한다"
    )
    item = _deployed_item()
    assert f"계절 {declared}개" in item.magnitude, (
        f"크기 칸이 계절 수를 말하지 않는다: {item.magnitude!r}"
    )
    for season in shape.seasons:
        assert season.name in item.reason, (
            f"「비어 있는 자리」 칸이 계절 「{season.name}」 을 말하지 않는다: "
            f"{item.reason!r}"
        )
    # ★★ **값이 가정임을 말하는가** — 이것이 사라지면 다음 사람이 가정값을
    # 실측으로 읽는다(사용자 판정 §3 2항). 리터럴을 박지 않고 **자산의
    # `confidence` 칸**을 읽어 대조한다.
    assert shape.confidence in item.reason, (
        f"문면이 계절 값의 신뢰도({shape.confidence!r})를 말하지 않는다 — "
        f"채운 것이 가정임이 리포트에서 사라졌다: {item.reason!r}"
    )


# ── ③ ★★ 축이 읽힌다 ─────────────────────────────────────────────────────


def test_the_wording_splits_on_how_many_seasons_the_asset_declares(
    tmp_path: Path,
) -> None:
    """★★ **이것이 「축이 읽힌다」의 증명이다** — 계절 수가 달라지면 문면이 갈린다.

    계절 수를 읽지 않고 문면을 박아 두면 ①② 는 그대로 초록불이고 여기만
    빨간불이 된다. 이 저장소가 다섯 번 밟은 *「선언·계산은 있는데 읽는 쪽이
    없다」* 를 리포트 쪽에서 붙드는 자리다.

    ## ⚠ 대조군이 뒤집혔다 (R60/WP-4-fix)

    종전에는 **배포 자산이 계절 하나**였으므로 임시 자산 쪽에 계절 넷을 주어
    갈랐다. 이제 배포 자산이 계절 넷이므로 **임시 자산 쪽이 계절 하나**다 —
    두 상태를 견주는 것은 같고 어느 쪽이 배포인지만 바뀌었다.

    ⚠ 여기 쓰는 계절 일수·몫은 **시험용 가정값이며 사업 전망이 아니다. 이 수를
    리포트·검토서에 인용하지 마라.**
    """
    hours = _report().dispatch_hours
    seasonal_items = _season_item(hours)  # 배포 자산 — 계절 넷
    plain_items = _season_item(hours, _one_season_asset(tmp_path))

    assert len(seasonal_items) == 1 and len(plain_items) == 1, (
        "계절을 넷 선언해도 항목은 남아야 한다 — 요일 변동은 그대로 미반영이고 "
        "계절 간 하루 차이도 운전에 서지 않는다"
    )
    seasonal, plain = seasonal_items[0], plain_items[0]

    assert plain.label == seasonal.label == _LABEL, (
        "항목 이름이 상태에 따라 갈리면 본문 3.4 표와 붙임 8 이 갈린다"
    )
    assert seasonal.reason != plain.reason, (
        "계절 넷을 선언한 자산과 하나뿐인 자산의 「비어 있는 자리」 문면이 "
        f"같다 — 판정이 계절 수를 읽지 않는다: {plain.reason!r}"
    )
    assert seasonal.resolves_when != plain.resolves_when, (
        "두 상태의 「해소 조건」 문면이 같다 — 판정이 계절 수를 읽지 "
        f"않는다: {plain.resolves_when!r}"
    )
    assert "1계절" in plain.reason, (
        f"계절 하나인 자산의 문면이 그것을 말하지 않는다: {plain.reason!r}"
    )
    declared = load_daily_shapes().generation.seasons
    assert f"계절 {len(declared)}개" in seasonal.magnitude, (
        f"크기 칸이 선언된 계절 수를 말하지 않는다: {seasonal.magnitude!r}"
    )
    for season in declared:
        assert season.name in seasonal.reason, (
            f"「비어 있는 자리」 칸이 계절 「{season.name}」 을 말하지 않는다: "
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


# ── ⑤ ★★ 남는 결손 — 계절 간 하루 차이는 결론에 서지 않는다 ────────────────


def test_the_wording_says_the_between_season_difference_does_not_reach_the_result(
) -> None:
    """★★★ **N5** — 계절을 채워도 **계절 간 하루 차이는 결론에 서지 않는다**.

    ## 이 검사가 막는 것

    배포 실행은 24스텝 하루를 365일로 연간화하므로, 계절이 여럿인 자산은
    `DailyShape.representative_day()` 가 내는 **몫 가중 평균 하루 한 벌**로
    접혀 들어간다(`core/casegrid/e2e_runner.py` 의 두 호출부). 그런데 문면이
    *「계절 4개로 접었다」* 라고만 적으면 검토자는 **계절이 결론을 가른다**고
    읽는다 — 그것이 R60/WP-4-fix 전의 상태였다.

    ⚠⚠ **「미반영이 줄었다」를 「결손이 해소됐다」로 적지 않는다**(사용자 판정
    §3 2항). 그래서 셋을 함께 붙든다:

        ⓐ 계절 넷과 몫이 **선언됐다**  · 그 값은 **가정**이다 (②가 신뢰도를 잰다)
        ⓑ 배포 실행은 **평균 대표일 한 벌**을 연간화한다 → 계절 간 하루 차이 미반영
        ⓒ 해소 조건이 **셋으로 갈린다** — 계절별 운전 · 요일 변동 · 8,760 실측

    ⚠ 문면 전체를 박지 않는다 — **담겨야 하는 조각**만 본다.
    """
    item = _deployed_item()

    # ⓑ — 무엇이 결론에 서지 않는가를 「비어 있는 자리」가 말한다.
    assert "평균" in item.reason and "대표일" in item.reason, (
        "「비어 있는 자리」 칸이 배포 실행이 **평균 대표일 한 벌**을 쓴다는 "
        f"것을 말하지 않는다: {item.reason!r}"
    )
    assert "계절 간 하루 차이" in item.reason, (
        "문면이 **무엇이 결론에 서지 않는가**를 말하지 않는다 — 「접었다」로만 "
        f"적으면 계절이 결론을 가른다고 읽힌다: {item.reason!r}"
    )
    assert "미반영" in item.reason, (
        f"계절 간 차이가 **미반영**임을 말하지 않는다: {item.reason!r}"
    )
    assert "접었다" not in item.reason, (
        "문면이 아직 「접었다」로 적는다 — 계절이 운전을 가른다고 읽힌다: "
        f"{item.reason!r}"
    )

    # ⓒ — 해소 조건 셋이 **각각** 서 있다.
    resolves = item.resolves_when
    assert "ⓐ" in resolves and "ⓑ" in resolves and "ⓒ" in resolves, (
        f"해소 조건이 세 갈래로 갈려 있지 않다: {resolves!r}"
    )
    assert "계절 간 하루 차이" in resolves, (
        f"해소 조건 ⓐ(계절별 대표일 운전)가 없다: {resolves!r}"
    )
    assert "요일 변동" in resolves, f"해소 조건 ⓑ(요일 변동)가 없다: {resolves!r}"
    assert "TMY" in resolves, f"해소 조건 ⓒ(실측)가 TMY 를 가리키지 않는다: {resolves!r}"


def test_the_season_item_count_did_not_grow(tmp_path: Path) -> None:
    """★★ **항목 수를 늘리지 않았다** — 본문 분량 예산의 여유가 1줄이다.

    미반영 항목 하나는 본문에 **두 줄**을 만든다(3.4 미반영 표 + 6.3 미해소
    표에 두 번 인쇄된다 · R60/WP-3 실측). 본문 상한은 219줄이고 지금 218줄이라
    **항목을 하나 늘리면 곧바로 넘는다.** 그래서 R60/WP-4-fix 는 계절 결손을
    **새 항목으로 세우지 않고 같은 항목의 문면을 고쳤다.**

    ⚠ 이 검사가 빨간불이면 상한을 올리지 말고 **문면으로 되돌려라** —
    상한은 이미 다섯 번 밀린 자리다(`tests/report/test_overview_sections.py`).
    """
    hours = _report().dispatch_hours
    assert len(_season_item(hours)) == 1, "배포 자산(계절 넷)에서 항목이 1건이 아니다"
    assert len(_season_item(hours, _one_season_asset(tmp_path))) == 1, (
        "계절 하나인 자산에서 항목이 1건이 아니다 — 상태에 따라 항목 수가 갈리면 "
        "본문 줄 수가 자산을 따라 움직인다"
    )
