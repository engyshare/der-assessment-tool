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

R48-E 가 같은 두 자리에 둘을 더 걸었다 — **두 표가 실행을 말하는가**이다:

    ★ 붙임 1 이 **실행이 쓴 값**을 싣는다  ← 오버라이드를 놓치면 재구성이 틀린다
    ★ 2.1 의 편익 열이 **번 금액**이고 4.3 과 **같은 수**를 말한다
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.assumption.provider import AssumptionSet
from core.report.appendix_sections import (
    TOPIC_PREFIXES,
    appendix_section,
    topic_of,
)
from core.report.case_report import _appendix, build_case_report
from core.report.method_sections import cost_benefit_section, model_section
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

    ⚠ **상한을 200 → 202 로 올렸다 (R51/WP-2).** 고정 O&M 둘
    (`opex.pv.fixed_om`·`opex.ess.fixed_om`)이 스윕 축이 되면서 본문 5.1
    영향도 표에 행이 둘 늘었다 — 실측(변경 전 199줄 → 변경 후 201줄, 이
    골든 시나리오 기준). 사용자 판정 §2 의 *「대장에 오르면 5.1 영향도 축이
    하나 는다」* 가 예고한 변화이며(이 항목은 둘로 갈랐으므로 둘이 늘었다),
    값이 아니라 **표의 행 수**가 바뀐 것이다 — 결론축(NPV)은 그대로다.
    """
    text = render_markdown(_report())
    body = text[: text.index("# 붙임")]
    lines = [line for line in body.splitlines() if line.strip()]
    assert len(lines) <= 202, (
        f"본문이 {len(lines)}줄이다 — 양식이 정한 부피를 넘었다. "
        "늘어난 것을 붙임으로 내릴 것"
    )


# ─────────────────────────────────────────────────────────────────────────
# R48-E1 — 붙임 1 이 **실행이 쓴 값**을 싣는가
# ─────────────────────────────────────────────────────────────────────────

_OVERRIDDEN_KEY = "capex.pv.rooftop"


def _provider() -> AssumptionSet:
    return AssumptionSet.load_from_yaml(str(_ASSUMPTIONS))


def test_appendix_one_carries_the_value_the_run_actually_used() -> None:
    """★ 붙임 1 이 **오버라이드를 반영한다** (R48-E1 · 판정 §8-a).

    종전 `_appendix()` 는 `items()`(= 대장 기준값)를 읽었고 오버라이드는
    `get()` 에만 반영됐다. 그래서 전제를 덮어쓴 실행에서 **계산은 새 값으로
    하고 「전 가정 전건」은 옛 값을 실었다** — 검토자가 붙임 1 만으로 결과를
    재구성하면 다른 수가 나온다.

    ⚠ **값을 박지 않는다.** 기준값을 대장에서 읽어 그와 다른 수를 만들어
    덮어쓴다 — 대장이 바뀌어도 이 검사가 재는 성질은 그대로다.
    """
    provider = _provider()
    base = provider.get(_OVERRIDDEN_KEY)
    assert base is not None, f"{_OVERRIDDEN_KEY}: 대장에 없다 — 검사의 재료가 없다"
    changed = float(base.value) * 1.25
    overridden = provider.override({_OVERRIDDEN_KEY: changed}, {_OVERRIDDEN_KEY: "검사"})

    rows = {row.key: row.value for row in _appendix(overridden)}
    assert rows[_OVERRIDDEN_KEY] == changed, (
        f"{_OVERRIDDEN_KEY}: 붙임 1 이 {rows[_OVERRIDDEN_KEY]} 를 실었다 — "
        f"실행이 쓴 값은 {changed} 다"
    )


def test_appendix_one_keeps_every_row_when_one_is_overridden() -> None:
    """★ 값만 바뀌고 **행의 집합은 그대로다.**

    전건을 오버라이드 쪽에서 세면 덮어쓰지 않은 항목이 붙임 1 에서 사라지고,
    그 순간 `FR-1002-AC6`(전 가정 목록) 위반이다.
    """
    provider = _provider()
    base = provider.get(_OVERRIDDEN_KEY)
    assert base is not None
    overridden = provider.override({_OVERRIDDEN_KEY: float(base.value) * 1.25})

    before = [row.key for row in _appendix(provider)]
    after = [row.key for row in _appendix(overridden)]
    assert before == after, "오버라이드가 붙임 1 의 행 집합을 바꿨다"


def test_appendix_one_is_unchanged_without_an_override() -> None:
    """★ 오버라이드가 **없는** 실행에서 값이 종전과 같다 (R48-E1 회귀).

    고친 자리가 기준 실행의 값을 함께 움직이면 골든 전부가 흔들린다. 대장이
    적어 둔 값 그대로여야 한다.
    """
    provider = _provider()
    items = provider.items()
    for row in _appendix(provider):
        assert row.value == items[row.key].value, (
            f"{row.key}: 오버라이드가 없는데 붙임 1 값이 대장과 다르다"
        )


# ─────────────────────────────────────────────────────────────────────────
# R48-E2 — 2.1 의 편익 열이 **번 금액**인가
# ─────────────────────────────────────────────────────────────────────────


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _row_starting_with(lines: list[str], kind: str) -> str:
    return next(line for line in lines if line.startswith(f"| {kind} |"))


def _won_total(text: str) -> int:
    """칸에 실린 금액을 **전부 더한다** — 갈래가 여럿이면 여럿을 더한다."""
    return sum(int(found.replace(",", "")) for found in re.findall(r"([\d,]+)원", text))


def test_the_target_table_carries_amounts_not_a_declaration_list() -> None:
    """★ 2.1 의 편익 열이 **금액**을 싣는다 (R48-E2 · 판정 §8-b).

    종전 이 칸은 `resource.produces` 였고 태그 이름뿐이었다 — 같은 표가 그
    옆에 초기투자를 적는데도 *「그 비용 대비 얼마를 버는가」* 에는 답이
    없었다.

    ⚠ **금액을 박지 않는다.** 귀속(`basis.benefit_attributions`)에서 지어
    대조한다 — 라운드가 운전 축을 바꾸면 금액은 바뀌고 성질만 남는다.
    """
    report = _report()
    basis = report.basis
    lines = model_section(report)

    header = next(line for line in lines if line.startswith("| 자원 | 용량·성능"))
    assert "버는 편익" in header, f"열 이름이 「번다」라고 말하지 않는다: {header}"

    for resource in basis.resources:
        shares = [
            share
            for share in basis.benefit_attributions
            if share.resource_name == resource.name
        ]
        assert shares, f"{resource.name}: 귀속 행이 없다 — 검사가 잴 것이 없다"
        cell = _cells(_row_starting_with(lines, resource.kind))[-1]
        for share in shares:
            assert f"{share.tag} {share.annual_won:,}원" in cell, (
                f"{resource.name}/{share.tag}: 2.1 의 편익 칸에 몫이 없다 — {cell}"
            )


def test_the_target_table_counts_what_a_resource_earns_not_what_it_declares() -> None:
    """★ 선언하지 않은 갈래의 **몫도** 실린다.

    저장장치는 잉여 판매를 `produces` 로 선언하지 않지만 계통 송전의 일부를
    방전으로 만들어 그 몫을 번다(R43-E2). 선언으로 열을 지으면 그 몫이
    사라지고, 열의 합이 4.3 의 「연 편익」과 어긋난다.

    ⚠ 이 구성에 갈린 갈래가 없으면 검사가 스스로 건너뛴다 — **없는 것을
    있다고 박아 두지 않는다.**
    """
    report = _report()
    basis = report.basis
    undeclared = [
        (resource, share)
        for resource in basis.resources
        for share in basis.benefit_attributions
        if share.resource_name == resource.name
        and share.tag not in resource.produces
        and share.annual_won
    ]
    if not undeclared:
        pytest.skip("이 구성에는 선언 밖 귀속이 없다")

    lines = model_section(report)
    for resource, share in undeclared:
        cell = _cells(_row_starting_with(lines, resource.kind))[-1]
        assert f"{share.tag} {share.annual_won:,}원" in cell, (
            f"{resource.name}: 선언하지 않은 {share.tag} 몫이 2.1 에서 빠졌다"
        )


def test_the_target_table_and_four_three_say_the_same_earnings() -> None:
    """★★ 2.1 과 4.3 이 **같은 수**를 말한다 — 인쇄물끼리 대조한다.

    두 표가 같은 출처를 읽는지는 코드를 봐야 알지만, **검토자가 보는 것은
    인쇄물**이다. 그래서 두 절의 행을 각각 파싱해 맞춘다 — 한쪽만 새로 세는
    변경이 들어오면 여기가 먼저 빨간불이 된다.
    """
    report = _report()
    basis = report.basis
    overview = model_section(report)
    ledger = cost_benefit_section(basis)

    for resource in basis.resources:
        earned_cell = _cells(_row_starting_with(overview, resource.kind))[-1]
        # 4.3 — | 자원 | 초기투자 | 연 운영비 | 연 편익 | 연 순편익 | 단순 회수 |
        ledger_cell = _cells(_row_starting_with(ledger, resource.kind))[3]
        assert _won_total(earned_cell) == _won_total(ledger_cell), (
            f"{resource.kind}: 2.1 이 {earned_cell} · 4.3 이 {ledger_cell} 를 "
            "말한다 — 한 리포트가 두 수를 말한다"
        )
