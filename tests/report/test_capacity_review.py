"""**적정 용량 검토** — 검토 지적 (2026-08-15).

지적 원문: *「ESS, heatpump, p2h 등은 **적정 용량 검토가 선행**되어야 함」*.

그때까지 용량은 `e2e_runner` 의 **모듈 상수**였다. 즉 27 케이스를 다 돌려도
용량은 한 값이고, 민감도 표에도 오르지 않으며, 리포트는 *「이 구성이 맞는가」*
를 묻지도 답하지도 못했다.

    ★ 용량이 **케이스 축**이다              ← 상수로 두면 스윕이 무의미하다
    ★ 리포트가 **형태를 재고** 고르지 않는다  ← 단조면 「적정값 미정」이다
    ★ 제약에 걸린 점을 **빼지 않는다**       ← 제약이 적정 용량을 정한다
    ★ 5.1 과 **갈라 싣는다**                ← 확보 대상과 설계 결정은 다르다
"""
from __future__ import annotations

from pathlib import Path

from core.casegrid.ledger_levels import design_variables
from core.report.capacity import (
    SHAPE_DECREASING,
    SHAPE_INCREASING,
    SHAPE_INTERIOR,
    build_capacity_review,
    capacity_section,
)
from core.report.case_report import build_case_report
from core.report.narrative import render_markdown

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"


def _report():
    return build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )


def test_capacity_is_a_case_axis_not_a_module_constant() -> None:
    """★★ **용량이 실제로 결론을 움직인다.**

    상수로 두면 용량을 바꿔도 NPV 가 그대로다 — 그 상태에서는 4.4 표가
    「한계 기여 0원」을 실으면서도 초록불이다. 그래서 *표가 있는가* 가 아니라
    **결론 축이 움직이는가**를 본다.
    """
    review = _report().capacity_review
    assert review, "설계 변수가 하나도 없다"
    for finding in review:
        solved = [p.conclusion for p in finding.points if p.conclusion is not None]
        assert len(solved) >= 2, f"{finding.variable}: 계산된 점이 둘 미만이다"
        assert len(set(solved)) > 1, (
            f"{finding.variable}: 용량을 {finding.points[0].value:g}~"
            f"{finding.points[-1].value:g} 로 움직여도 결론 축이 그대로다 — "
            "축에 붙지 않았다"
        )


def test_the_shape_is_measured_not_asserted() -> None:
    """★ 형태를 **탐침으로** 확인한다 — 라벨을 박아 두지 않았는지.

    실물은 지금 둘 다 단조다. 그래서 *「단조가 나오는가」* 만 보면 상수를
    돌려주는 구현도 초록불이다. 내부 최적점을 가진 응답을 주입해 **그때
    형태가 바뀌는지** 본다.
    """
    # 봉우리를 **그 변수의 구간 한가운데**에 둔다. 고정값으로 두면 어떤
    # 변수에서는 봉우리가 구간 밖이라 단조가 되고, 그때 실패하는 것은 검사다.
    middle = {
        variable.name: (variable.low + variable.high) / 2
        for variable in design_variables()
    }

    def humped(variable: str, value: float) -> float:
        return -((value - middle[variable]) ** 2) * 1_000.0

    findings = build_capacity_review(humped, used={})
    assert findings, "설계 변수가 없다"
    for finding in findings:
        assert finding.shape == SHAPE_INTERIOR, (
            f"{finding.variable}: 내부 최대인 응답에 {finding.shape} 이 나왔다"
        )
        assert finding.bounded, "내부 최적점이 있으면 적정값이 정해진다"

    rising = build_capacity_review(lambda _v, value: value * 1_000.0, used={})
    assert {f.shape for f in rising} == {SHAPE_INCREASING}
    falling = build_capacity_review(lambda _v, value: -value * 1_000.0, used={})
    assert {f.shape for f in falling} == {SHAPE_DECREASING}


def test_a_blocked_point_is_carried_not_dropped() -> None:
    """★★ **자원 제약에 걸린 점을 빼지 않는다.**

    빼면 표가 매끈해지고 제약이 사라진 것처럼 보인다 — 그런데 **제약이야말로
    적정 용량을 정하는 것**이다. 실물에서 ESS 용량을 키우면 정격출력에 걸리므로
    그 자리가 값으로 실리는지 본다.
    """
    blocked_at = 5.0

    def refusing(_variable: str, value: float) -> float:
        if value >= blocked_at:
            raise ValueError("probe: 계획이 정격출력을 넘습니다. 출력을 키우십시오")
        return value * 1_000.0

    for finding in build_capacity_review(refusing, used={}):
        refused = [p for p in finding.points if p.conclusion is None]
        assert refused, f"{finding.variable}: 거부된 점이 표에서 사라졌다"
        assert all(p.blocked_by for p in refused), "걸린 제약이 비어 있다"
        assert finding.binding_constraint, "걸린 제약이 요약되지 않았다"
        # 「어떻게 고치는가」는 개발자에게 하는 말이다 (양식 0절).
        assert "십시오" not in finding.binding_constraint, (
            f"조치 지시가 표에 실렸다: {finding.binding_constraint}"
        )


def test_design_variables_stay_out_of_the_uncertainty_table() -> None:
    """★ 5.1 은 **확보 대상**이다 — 고르는 값을 섞지 않는다.

    할인율을 5.2 로 가른 것과 같은 판단이다. 섞으면 「자료를 더 알아보라」와
    「설계를 다시 하라」가 한 우선순위 표에서 경쟁하고, 그 둘은 받는 사람이
    다르다.
    """
    report = _report()
    names = {variable.name for variable in design_variables()}
    listed = {entry.variable for entry in report.influences}
    assert not (names & listed), f"설계 변수가 영향도 표에 섞였다: {names & listed}"

    text = render_markdown(report)
    body = text[text.index("### 5.1") : text.index("## 6. 종합")]
    for name in names:
        assert name not in body, f"5절에 설계 변수 {name} 이 실렸다"


def test_the_body_carries_the_shape_and_the_appendix_carries_the_points() -> None:
    """본문 4.4 는 형태만, 붙임 10 은 점별 값 — 양식이 정한 경계."""
    report = _report()
    text = render_markdown(report)
    section = text[text.index("### 4.4") : text.index("## 5. 결론을 좌우하는 요인")]
    appendix = text[text.index("## 붙임 10.") :]

    for finding in report.capacity_review:
        assert finding.label in section, f"{finding.variable}: 4.4 에 없다"
        assert finding.shape in section, f"{finding.variable}: 형태가 4.4 에 없다"
        for point in finding.points:
            assert f"| {point.value:g}" in appendix, (
                f"{finding.variable}: {point.value:g} 점이 붙임 10 에 없다"
            )
    # 점별 결론 축은 본문에 싣지 않는다 — 본문이 붙임이 되면 분량 규정이 깨진다.
    assert "계산 불가" not in section, "제약 상세가 본문에 실렸다"


def test_the_section_carries_no_reading_instructions() -> None:
    """양식 0절 — 해설·독법 지시를 싣지 않는다."""
    lines = capacity_section(_report().capacity_review)
    assert not [line for line in lines if line.startswith(">")], "인용문이 남았다"
    for banned in ("읽지 말", "권고", "건의", "바람직"):
        assert not [line for line in lines if banned in line], f"{banned} 가 실렸다"
