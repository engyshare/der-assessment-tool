"""**평가 대상 요약**과 **전제의 주제별 묶음** — 「1차 의견」 4·5 (R33).

    「2.1 이 표부터 시작해 무엇을 평가하는가가 문장으로 없음」      ← 의견 4
    「전제를 주제별로 묶어 달라 (설비단가/요금/제도/분석조건)」     ← 의견 5

둘 다 **서식이 아니라 찾을 수 있는가**의 문제다. 표는 *어떤 값인가* 에 답하지만
*무엇을 평가한 것인가* 에는 답하지 않고, 신뢰도별 묶음은 *「설비 단가를 어디서
보는가」* 에 답하지 않는다.

    ★ 요약의 값이 **전부 계산에서** 온다   ← 박아 두면 구성이 바뀔 때 틀린다
    ★ 요약이 표보다 앞에 선다
    ★ 주제로 묶어도 **신뢰도를 잃지 않는다**
    ★ 전 항목이 어느 주제엔가 실린다      ← 묶다가 빠지면 `FR-1002-AC6` 위반
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.report.appendix_sections import (
    TOPIC_PREFIXES,
    appendix_section,
    topic_of,
)
from core.report.case_report import build_case_report
from core.report.method_sections import model_section
from core.report.narrative import render_markdown

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"


def _report():
    return build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )


def _summary_paragraph(report) -> str:
    lines = model_section(report)
    start = lines.index("### 2.1 평가 대상") + 2
    return lines[start]


def test_target_summary_stands_before_the_specification_table() -> None:
    """요약이 **표보다 앞**에 선다 (의견 4).

    ⚠ `req()` 마커는 달지 않았다 — 절 안의 배치는 양식
    (`docs/report-form-심의보고서.md`)이 정하는 서식 규정이지 spec 조항이
    아니다.
    """
    lines = model_section(_report())
    heading = lines.index("### 2.1 평가 대상")
    table = next(
        i for i, line in enumerate(lines) if line.startswith("| 자원 | 용량·성능")
    )
    paragraph = next(
        i
        for i, line in enumerate(lines)
        if i > heading and line and not line.startswith(("#", "|", "-"))
    )
    assert heading < paragraph < table, "요약이 표 앞에 없다"


def test_target_summary_is_about_three_hundred_characters() -> None:
    """분량이 **한 문단**으로 남는다.

    길어지면 그 자체가 본문을 늘리고(양식 4~5쪽), 짧으면 대상을 말하지 못한다.
    의견이 요구한 「300자 요약」의 폭을 넉넉히 잡아 고정한다.
    """
    text = _summary_paragraph(_report())
    assert 200 <= len(text) <= 420, f"요약이 {len(text)}자다 — 한 문단을 벗어났다"


def test_target_summary_is_filled_from_the_run_not_authored() -> None:
    """★ **값이 전부 계산에서 온다.**

    자원 종류·총 초기투자·보조율·편익 갈래·분석기간·할인율이 실행 결과와
    같아야 한다. 하나라도 박아 둔 값이면 구성이 바뀔 때 리포트가 **옛 수를
    그럴듯하게 계속 인쇄한다** — 아무 예외도 나지 않는다.
    """
    report = _report()
    basis = report.basis
    text = _summary_paragraph(report)

    for line in basis.resources:
        assert line.kind in text, f"{line.kind}: 자원 종류가 요약에 없다"
    for line in basis.benefits:
        assert line.label in text, f"{line.tag}: 편익 갈래가 요약에 없다"
    total = sum(line.capex_won for line in basis.resources)
    assert f"{total:,}원" in text, "총 초기투자가 요약에 없다"
    assert f"{basis.horizon_years}년" in text, "분석기간이 요약에 없다"
    assert f"{basis.discount_rate:.1%}" in text, "할인율이 요약에 없다"
    assert f"{report.subsidy_rate:.0%}" in text, "보조율이 요약에 없다"


def test_target_summary_carries_no_result() -> None:
    """★ 요약이 **결과를 앞당겨 싣지 않는다** (양식 0절).

    2.1 은 *무엇을 평가했는가* 이지 *결과가 어떤가* 가 아니다. 결론이 여기
    새면 검토자는 대상을 읽기 전에 판정을 먼저 읽는다.

    ⚠ **지표 이름은 금지어가 아니다.** *「할인 회수기간과 순현재가치를
    낸다」* 는 무엇을 계산하는지의 진술이며 결과가 아니다. 막아야 하는 것은
    **결론 값과 판정 어휘**다.
    """
    report = _report()
    text = _summary_paragraph(report)
    from core.report.case_report import CONCLUSION_METRIC

    assert f"{report.metrics[CONCLUSION_METRIC]:,.0f}" not in text, (
        "2.1 이 결론 수치를 앞당겨 실었다"
    )
    for banned in ("미회수", "유리", "불리", "타당", "경제성이 있"):
        assert banned not in text, f"요약에 판정이 섞였다: {banned}"


@pytest.mark.req("FR-1002-AC6")
def test_every_ledger_row_lands_in_a_topic() -> None:
    """★ 주제로 묶다가 **빠지는 항목이 없다.**

    조항은 *「전 가정 목록을 부록으로」* 이므로, 묶음이 바뀌었다고 항목이
    사라지면 그 순간 조항 위반이다. 주제별 건수의 합이 전건과 같아야 한다.
    """
    report = _report()
    lines = appendix_section(report)
    counts = [
        int(line.split("—", maxsplit=1)[1].split("건", maxsplit=1)[0].strip())
        for line in lines
        if line.startswith("### ")
    ]
    assert sum(counts) == len(report.assumptions), (
        f"주제별 합 {sum(counts)} 이 전건 {len(report.assumptions)} 과 다르다"
    )
    text = "\n".join(lines)
    for row in report.assumptions:
        assert f"`{row.key}`" in text, f"{row.key}: 붙임 1 에서 사라졌다"


@pytest.mark.req("FR-1002-AC6")
def test_confidence_survives_the_topic_grouping() -> None:
    """★ 주제로 묶어도 **신뢰도를 잃지 않는다** (의견 5 — 「둘 다 필요」).

    종전 묶음이 신뢰도별이었으므로 주제로 바꾸면서 신뢰도가 사라지면
    *「무엇을 확인해야 하는가」* 를 답할 수 없게 된다. 열과 주제 머리의
    내역 **둘 다** 로 남는지 본다.
    """
    report = _report()
    lines = appendix_section(report)
    header = next(line for line in lines if line.startswith("| 대장 키 |"))
    assert "신뢰도" in header, "신뢰도가 열에서 사라졌다"

    for line in lines:
        if line.startswith("### "):
            assert "신뢰도:" in line, f"주제 머리에 신뢰도 내역이 없다: {line}"

    for row in report.assumptions:
        entry = next(line for line in lines if line.startswith(f"| `{row.key}` "))
        assert f"| {row.confidence} |" in entry, f"{row.key}: 신뢰도가 행에 없다"


def test_topics_come_from_the_ledger_key_prefix() -> None:
    """주제가 **대장 키의 접두어**에서 온다 — 리포트가 새 분류를 만들지 않는다.

    ⚠ `req()` 마커는 달지 않았다 — 묶음 축은 양식이 정하는 서식 규정이다.
    """
    for topic, prefixes in TOPIC_PREFIXES:
        for prefix in prefixes:
            assert topic_of(f"{prefix}sample") == topic


def test_unclassified_key_is_shown_not_absorbed() -> None:
    """★ 선언에 없는 접두어는 **미분류로 드러난다.**

    조용히 기타로 흡수하면 새 주제가 생겼다는 사실이 보이지 않는다. 지금
    대장에는 미분류가 없어야 하며, 생기면 이 검사가 아니라 **리포트가** 먼저
    보인다.
    """
    assert topic_of("brand_new_axis.value") == "미분류"
    text = "\n".join(appendix_section(_report()))
    assert "### 미분류" not in text, (
        "대장에 새 접두어가 생겼다 — `TOPIC_PREFIXES` 에 주제를 선언할 것"
    )


def test_appendix_one_carries_no_reading_instructions() -> None:
    """★ **해설을 싣지 않는다** (양식 0절)."""
    for section in (appendix_section(_report()), model_section(_report())):
        quoted = [line for line in section if line.startswith(">")]
        assert not quoted, f"해설 인용문이 남았다: {quoted[:2]}"


def test_body_stays_within_the_form_length_budget() -> None:
    """본문이 **양식이 정한 부피** 안에 있다 (4~5쪽 · 130~170줄 기준).

    붙임을 셋 늘리면서 본문이 함께 부풀면 *「본문은 짧게, 근거는 붙임으로」*
    가 무너진다. 여기서는 본문(표제~6절 끝)의 줄 수를 본다.

    ⚠ `req()` 마커는 달지 않았다 — 분량 규정은 양식 소관이다.
    """
    text = render_markdown(_report())
    body = text[: text.index("# 붙임")]
    lines = [line for line in body.splitlines() if line.strip()]
    assert len(lines) <= 200, (
        f"본문이 {len(lines)}줄이다 — 양식이 정한 부피를 넘었다. "
        "늘어난 것을 붙임으로 내릴 것"
    )
