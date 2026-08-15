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

from core.report.case_report import CONCLUSION_METRIC, build_case_report
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
    # 조항이 말하는 「영향도 순위」는 **본문**의 것이다. 붙임끼리의 앞뒤는
    # 양식(`docs/report-form-심의보고서.md`)이 정하며 조항 소관이 아니다.
    ranking = text.index("## 5. 결론을 좌우하는 요인")
    listing = text.index("## 붙임 1. 전제 대장 전건")
    assert ranking < listing, (
        "가정 목록이 영향도 순위보다 앞에 있다 — FR-1002-AC1 은 나열을 "
        "붙임으로 보내라고 한다"
    )
    assert text.index("# 붙임") < listing, "전 가정 목록이 본문에 있다"


@pytest.mark.req("FR-1002-AC4")
def test_flipping_factors_are_the_first_section() -> None:
    """결론을 뒤집는 인자가 **맨 앞**이다."""
    text = _markdown()
    flip = text.index("### 5.1 불확실 인자")
    ranking = text.index("## 붙임 2. 영향도 산출 상세")
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


def test_no_machine_local_path_reaches_the_reviewer() -> None:
    """★ **절대 경로가 리포트에 새지 않는다.**

    검토자에게 나가는 문서에 개발 기계의 경로(`D:/...` · `/home/...`)가 박히면
    ⓐ `SC-3` 비공개 정보 유입이고 ⓑ 무엇보다 **다른 기계에서 같은 리포트를
    다시 뽑을 수 없다** — 재현 정보로서 쓸모가 없어진다.

    실물을 처음 뽑았을 때 실제로 새어 있었고, 변이를 심어 보니 **이 검사가
    없으면 아무것도 붙들지 않았다.** `req()` 마커는 달지 않았다 — `SC` 표의
    행은 수용기준 파서가 읽는 형식이 아니라 인용하면 매달린 참조가 된다
    (`status-human.md` 7단계의 승격 판단 대기 항목).
    """
    text = _markdown()
    offenders = re.findall(r"(?:[A-Za-z]:[\\/]|/(?:home|Users|mnt)/)\S*", text)
    assert not offenders, f"기계 지역 경로가 리포트에 남았다: {offenders[:3]}"


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
    section = text[text.index("## 붙임 2. 영향도 산출 상세") : text.index("## 붙임 3.")]
    for entry in report.uncertain_influences:
        row = next(
            line for line in section.splitlines() if line.startswith(f"| {entry.variable} ")
        )
        assert entry.confidence in row, f"{entry.variable}: 신뢰도가 행에 없다"
        assert entry.source in row, f"{entry.variable}: 출처가 행에 없다"


@pytest.mark.req("FR-1002-AC1")
def test_policy_parameters_are_not_ranked_with_the_uncertain_ones() -> None:
    """★ **할인율은 영향도 순위표에 없다** (R33 검토 지적 4).

    영향도 순위가 답하려는 물음은 *「어느 자료를 먼저 확보할 것인가」*다.
    할인율은 확보할 자료가 아니라 **평가자가 정하는 값**이므로, 한 표에 섞이면
    1위가 「확보 대상」이 아니게 되고 표를 읽은 사람이 우선순위를 잘못 잡는다.

    ⚠ **빼는 것과 버리는 것은 다르다.** 5절에 반드시 있어야 한다 — 할인율
    선택이 결론을 바꾸는 것은 사실이고, 그것을 지우면 리포트가 덜 정직해진다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    ranking = text[text.index("## 붙임 2. 영향도 산출 상세") : text.index("## 붙임 3.")]
    policy = text[text.index("### 5.2 정책 설정값") : text.index("## 6. 종합 판단")]

    assert report.policy_influences, "정책 설정값이 하나도 없다 — 전제가 바뀌었다"
    for entry in report.policy_influences:
        assert f"| {entry.variable} " not in ranking, (
            f"{entry.variable} 은 정해 놓고 쓰는 값인데 영향도 순위에 섞였다"
        )
        assert f"| {entry.variable} " in policy, (
            f"{entry.variable} 이 5절에도 없다 — 빼는 것과 버리는 것은 다르다"
        )


@pytest.mark.req("FR-1005-AC1")
def test_reproduction_appendix_carries_what_another_agent_needs() -> None:
    """★ **다른 사람이 이 결과를 다시 낼 수 있는가** (R33 검토 지적 5).

    매니페스트 해시만으로는 부족하다 — 해시는 **같은지 다른지**만 말하고
    어떻게 만드는지는 말하지 않는다. 명령 · 입력 좌표 · 규약 · 대조 수단 넷이
    다 있어야 「해 보았더니 다른 수가 나왔다」가 어디서 갈렸는지 말할 수 있다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    appendix = text[text.index("## 붙임 5. 재현 절차") :]

    assert "app.run.report_cli" in appendix, "재현 명령이 없다"
    assert report.scenario_name_slug in appendix, "어느 시나리오인지 없다"
    assert report.manifest_hash in appendix, "대조할 매니페스트 해시가 없다"
    assert report.assumption_set_version in appendix, "전제 대장 판이 없다"
    assert f"{report.basis.horizon_years}년" in appendix, "분석기간이 없다"
    assert "e2e_runner" in appendix, "설비 제원의 소유자를 밝히지 않는다"


@pytest.mark.req("FR-1001-AC2")
def test_the_report_says_what_it_evaluated_and_how() -> None:
    """★ **대상과 방법이 리포트 안에 있다** (R33 검토 지적 1·3).

    첫 판은 결론과 민감도만 실었다 — 검토자는 *무엇을 평가했는지* 모르는 채
    *그 결론이 무엇에 민감한지*를 읽었고, 그것으로 `MC-1` 의 「이 회수기간이
    왜 이 값인가」에 답할 수는 없다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    model = text[text.index("## 2. 평가 개요") : text.index("## 3. 평가 방법")]

    assert report.basis.resources, "평가 대상 자원이 비어 있다"
    for resource in report.basis.resources:
        assert resource.kind in model, f"{resource.kind} 가 대상 표에 없다"
        assert resource.capacity in model, f"{resource.kind}: 용량이 없다"
        assert f"{resource.lifetime_years}년" in model, f"{resource.kind}: 수명이 없다"

    method = text[text.index("## 3. 평가 방법") : text.index("## 4. 평가 결과")]
    assert "이 평가가 하지 않은 것" in method, "한계를 밝히지 않는다"
    assert report.basis.dispatch_note in method, "시간 해상도 규약이 없다"


@pytest.mark.req("FR-1001-AC2")
def test_each_resource_shows_what_it_cost_and_what_it_earns() -> None:
    """★ **자원마다 얼마를 넣고 얼마를 버는가** (R33 검토 지적 2).

    지적 원문은 *「pv.rooftop capex 는 잡혀 있는데 그 비용 대비 편익이 적정한지는
    어떻게 보는가」*였다. 연 편익을 한 덩어리로만 실으면 답할 자리가 없다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    section = text[text.index("### 4.3 자원별 수지") : text.index("## 5. 결론을 좌우하는 요인")]
    detail = text[text.index("## 붙임 4.") : text.index("## 붙임 5.")]

    assert report.basis.benefits, "편익 갈래가 비어 있다"
    for line in report.basis.benefits:
        assert line.label in section, f"{line.tag}: 편익 갈래가 표에 없다"
        assert f"{line.annual_won:,}원" in section, f"{line.tag}: 금액이 없다"
        # 산식은 붙임 4 로 내렸다 — 본문 표가 화면 밖으로 넘쳤기 때문이다.
        # **버린 것이 아니라 옮긴 것**이므로 붙임에 있는지 본다.
        assert line.formula in detail, f"{line.tag}: 산식이 붙임 4 에도 없다"
    for resource in report.basis.resources:
        assert f"{resource.capex_won:,}원" in section, (
            f"{resource.kind}: 초기투자가 수지표에 없다"
        )


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
    section = text[text.index("### 4.2 지원 유무 비교") : text.index("### 4.3")]
    # 머리행(`| 변형 | …`)에도 「무지원 대비 증분」때문에 「원」이 들어 있다.
    # 그래서 문자열 포함이 아니라 **금액 칸이 있는 행**을 고른다.
    rows = [
        line
        for line in section.splitlines()
        if re.match(r"^\| [^|]+\| [\d,-]+원 \|", line)
    ]
    assert rows, "변형 표에 금액 행이 하나도 없다"
    assert rows[0].startswith("| 무지원 기준선 "), f"기준선이 맨 위가 아니다: {rows[0]}"


def test_resources_outliving_the_horizon_are_flagged_as_uncosted() -> None:
    """★ **분석기간 안에 수명이 끝나는 자원을 리포트가 스스로 짚는다.**

    ⚠ **`req("FR-104-AC2")` 를 달지 않았다.** 그 조항은 *「EOL 도달 시 교체비를
    **계상**한다」* 인데 이 검사가 보는 것은 정반대 — **계상하지 않았다는 사실을
    리포트가 밝히는가**다. 마커를 달면 「교체비를 계상한다」가 검증된 것으로
    세어지고, 실제로는 계상되지 않는다.

    실측: `ESS.replacement_schedule()` · `core/cba/salvage.py::salvage_value()`
    는 있으나 **프로포마에 넣는 배포 코드가 0곳**이다(비용 행은 고정 O&M 뿐).
    R32 가 세 번, R33 이 앞서 두 번 만난 「부품은 있는데 읽는 쪽이 없다」와
    같은 형태이며, `status.md` 미해결에 올렸다. 배선되면 이 검사는 `else`
    가지로 넘어가 그대로 통과한다.

    지금 구성은 ESS 수명 17년 · 분석기간 20년이라 **교체가 한 번 필요한데
    프로포마에 교체 비용 행이 없다.** 즉 현 결과는 그 자원에 관대하며, 그
    사실을 말하지 않으면 검토자는 완결된 비용 구조를 읽었다고 믿는다.

    ⚠ **문면을 고정하지 않는다.** 「ESS 는 교체비가 빠졌다」로 박아 두면 제원이
    바뀔 때(수명 25년 ESS) 리포트가 틀린 경고를 계속 인쇄하고, 분석기간을
    늘리면 PV 도 대상인데 아무 말도 하지 않는다. 그래서 **수명과 분석기간을
    견주어** 판정한다 — 이 검사도 같은 방식으로 본다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    limits = text[text.index("### 3.4 이 평가가 하지 않은 것") : text.index("## 4. 평가 결과")]

    basis = report.basis
    short = [r for r in basis.resources if r.lifetime_years < basis.horizon_years]
    if short:
        assert "교체 비용을 계상하지 않았다" in limits, (
            "분석기간 안에 수명이 끝나는 자원이 있는데 경고가 없다"
        )
        for resource in short:
            assert resource.kind in limits, (
                f"{resource.kind}(수명 {resource.lifetime_years}년)이 경고에 없다"
            )
    else:
        assert "영향이 없다" in limits, (
            "수명이 넉넉한데도 「교체비 미계상」을 경고처럼 적고 있다"
        )


def test_summary_section_stands_alone_for_the_committee() -> None:
    """★ **1절 요약만 읽고도 판단의 뼈대가 잡히는가.**

    양식(`docs/report-form-심의보고서.md`)이 요구하는 셋이 다 있어야 한다 —
    결론 한 문장 · 결론을 좌우하는 요인 · 읽을 때의 유의사항. 심의위원이 본문
    전체를 읽지 않는다는 전제가 그 양식의 근거이며, 요약이 비면 **뒤 절이
    아무리 충실해도 그 전제가 무너진다.**

    ⚠ `req()` 마커는 달지 않았다 — 양식은 이 저장소의 서식 규정이지 spec 조항이
    아니다. `FR-1003` 에 「사람이 읽는 문서」 형식이 신설되면 그때 단다
    (`status-human.md` 7단계).
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    assert "## 1. 요약" in text, "요약 절이 없다"
    summary = text[text.index("## 1. 요약") : text.index("## 2. 평가 개요")]

    # ① 결론 한 문장 — 본문의 결론과 **같은 수**여야 한다
    assert str(report.basis.horizon_years) in summary, "요약에 분석기간이 없다"
    if report.recovers_within_horizon:
        assert "회수된다" in summary
    else:
        assert "회수되지 않는다" in summary
        assert f"{report.metrics[CONCLUSION_METRIC]:,.0f}원" in summary, (
            "요약의 결론 수치가 본문과 다르다"
        )

    # ② 결론을 좌우하는 요인
    assert "결론을 좌우하는 요인" in summary
    for entry in report.flipping:
        assert entry.variable in summary, f"{entry.variable} 이 요약에 없다"

    # ③ 유의사항 — 있는 것만 적되, 있으면 반드시 적는다
    assert "이 결과를 읽을 때" in summary
    if report.provisional_warning:
        assert "잠정" in summary, "잠정성 경고가 요약에 없다"
    if report.unread_variables:
        assert "반영되지 않은" in summary, "미반영 경고가 요약에 없다"
    short = [
        r
        for r in report.basis.resources
        if r.lifetime_years < report.basis.horizon_years
    ]
    if short:
        assert "교체비" in summary, "교체비 미계상 경고가 요약에 없다"
