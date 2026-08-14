"""리포트 한 장이 **조항이 정한 순서**로 서는가 — FR-1002-AC1 · UI-7.

`FR-1002-AC1` 은 *「리포트 첫 화면은 영향도 순위로 시작한다. 입력 순·분류 순
나열은 부록으로 보낸다」* 이고 `UI-7` 이 화면에 같은 것을 요구한다. 즉 **절의
순서 자체가 조항**이므로, 여기서 보는 것은 문장이 아니라 자리다.

    영향도가 가정 목록보다 앞에 온다     ← 뒤바뀌면 조항 위반이다
    전환 인자가 순위보다도 앞에 온다     ← FR-1002-AC4 「최상단에 별도 강조」
    ★ 지수 표기가 없다                  ← `1.6e+06` 은 검토자가 읽는 수가 아니다
    미반영 의심을 본문이 말한다          ← 「영향 0」을 조용히 최하위로 두지 않는다
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.report.case_report import build_case_report
from core.report.narrative import render_markdown

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"


def _markdown(name: str = "scenario_unsubsidized") -> str:
    report = build_case_report(
        _GOLDEN / f"{name}.yaml", assumptions_path=_ASSUMPTIONS
    )
    return render_markdown(report)


@pytest.mark.req("FR-1002-AC1", "UI-7-AC1")
def test_influence_ranking_comes_before_the_assumption_list() -> None:
    """입력 나열이 위로 올라오면 조항 위반이다."""
    text = _markdown()
    ranking = text.index("## 2. 영향도 순위")
    appendix = text.index("## 부록. 전 가정 목록")
    assert ranking < appendix, (
        "가정 목록이 영향도 순위보다 앞에 있다 — FR-1002-AC1 은 나열을 "
        "부록으로 보내라고 한다"
    )


@pytest.mark.req("FR-1002-AC4")
def test_flipping_factors_are_the_first_section() -> None:
    """결론을 뒤집는 인자가 **맨 앞**이다."""
    text = _markdown()
    flip = text.index("## 1. 결론을 뒤집는 인자")
    ranking = text.index("## 2. 영향도 순위")
    assert flip < ranking


def test_no_scientific_notation_reaches_the_reviewer() -> None:
    """★ `1.6e+06` 은 검토자가 읽는 수가 아니다.

    `MC-1` 이 재는 것은 「리포트만 보고 설명할 수 있는가」다. 읽으려면 변환이
    필요한 표기는 그 자체로 미달 사유이며, 그 미달은 **리포트가 아니라
    서식**에서 온 것이라 원인을 짚기도 어렵다.

    ⚠ **`req("FR-1001-AC5")` 를 달지 않았다.** 달아 보았고, 그 순간 매핑표에서
    `FR-1001-AC5` 가 「수동 + MC-1(미수행)」에서 **「자동」으로 바뀌었다** —
    Phase 1 인수를 막고 있는 유일한 차단 수동검증이 표에서 사라진 것이다.
    조항이 재는 것은 **사람의 이해**이고 이 검사가 재는 것은 서식이다.
    spec §16.5 가 *「분류를 규정하는 조항에 수동 항목을 걸지 말라」* 며 막으려는
    자기충족과 같은 형태이므로, 마커 없이 둔다. **읽히지 않는 조항 하나를 얻고
    차단 표시를 잃는 거래는 하지 않는다.**
    """
    text = _markdown()
    offenders = re.findall(r"\d+\.?\d*e[+-]\d+", text)
    assert not offenders, f"지수 표기가 리포트에 남았다: {offenders[:5]}"


@pytest.mark.req("FR-1001-AC4")
def test_every_ranked_factor_carries_its_provenance_in_the_same_row() -> None:
    """출처·기준연도·신뢰도가 **같은 행**에 있다.

    별표로 미루면 검토자가 두 표를 대조해야 하고, 그 대조는 `MC-1` 이 금지한
    「부연」에 해당한다 — 대조 방법을 설명해야 하기 때문이다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    section = text[text.index("## 2. 영향도 순위") : text.index("## 3.")]
    for entry in report.influences:
        row = next(
            line for line in section.splitlines() if line.startswith(f"| {entry.variable} ")
        )
        assert entry.confidence in row, f"{entry.variable}: 신뢰도가 행에 없다"
        assert entry.source in row, f"{entry.variable}: 출처가 행에 없다"


@pytest.mark.req("FR-1002-AC3")
def test_unread_variable_is_called_out_in_the_body() -> None:
    """변동폭 0 을 **본문이 말한다** — 표의 마지막 줄로 흘려보내지 않는다."""
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    for entry in report.unread_variables:
        assert entry.variable in text
        assert "계산이 이 인자를 읽지 않고 있을 가능성" in text, (
            "미반영 의심을 본문이 말하지 않는다"
        )


@pytest.mark.req("FR-607-AC1")
def test_baseline_is_the_first_row_of_the_variant_table() -> None:
    """무지원 기준선이 변형 표 맨 위다 — 「결과 상단에 표시」."""
    report = build_case_report(
        _GOLDEN / "scenario_subsidy_80.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    section = text[text.index("## 3. 지원 유무 비교") : text.index("## 4.")]
    # 머리행(`| 변형 | …`)에도 「무지원 대비 증분」때문에 「원」이 들어 있다.
    # 그래서 문자열 포함이 아니라 **금액 칸이 있는 행**을 고른다.
    rows = [
        line
        for line in section.splitlines()
        if re.match(r"^\| [^|]+\| [\d,-]+원 \|", line)
    ]
    assert rows, "변형 표에 금액 행이 하나도 없다"
    assert rows[0].startswith("| 무지원 기준선 "), f"기준선이 맨 위가 아니다: {rows[0]}"
