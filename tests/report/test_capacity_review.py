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
from core.contracts.validation import ValidationError
from core.report.capacity import (
    BLOCKED_BY_DESIGN,
    BLOCKED_BY_FAILURE,
    SHAPE_DECREASING,
    SHAPE_INCREASING,
    SHAPE_INTERIOR,
    build_capacity_review,
    capacity_appendix,
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
            # ⚠ **`ValidationError` 로 던진다 (R43-H).** 실물이 그것이고
            # (`ESS._check_power`), 이 예외형이 곧 「설계 제약」 판정의 근거다 —
            # 평범한 `ValueError` 로 두면 이 검사가 **결함 갈래**를 재게 되고
            # 「제약에 걸린 점」이라는 이름과 어긋난다.
            raise ValidationError(
                field="probe.power_kw",
                reason="probe: 계획이 정격출력을 넘습니다",
                action="출력을 키우십시오",
            )
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
    # ⚠ **문면을 상수에서 가져온다 (R43-H).** 종전 이 줄은 리터럴 「계산 불가」
    # 였고, 그 문면이 사라지자 **검사가 조용히 아무것도 재지 않게 됐다.**
    for banned in (BLOCKED_BY_DESIGN, BLOCKED_BY_FAILURE):
        assert banned not in section, f"제약 상세({banned})가 본문에 실렸다"


def test_the_section_carries_no_reading_instructions() -> None:
    """양식 0절 — 해설·독법 지시를 싣지 않는다."""
    lines = capacity_section(_report().capacity_review)
    assert not [line for line in lines if line.startswith(">")], "인용문이 남았다"
    for banned in ("읽지 말", "권고", "건의", "바람직"):
        assert not [line for line in lines if banned in line], f"{banned} 가 실렸다"


def _blocked_review(error: Exception):
    """세 점째부터 `error` 를 던지는 탐침의 검토 결과."""

    def probe(_variable: str, value: float) -> float:
        if value > 2.0:
            raise error
        return value * 1_000.0

    return build_capacity_review(probe, used={})


def test_a_design_refusal_and_a_real_failure_do_not_print_the_same_thing() -> None:
    """★★ **「계산 불가」 하나로 둘을 인쇄하고 있었다** (문의사항 나-9).

    붙임 10 의 30kWh 행은 *「e2e-ess: 방전 계획 6 kW 가 정격출력 5 kW 를
    넘습니다」* 를 「계산 불가」 칸에 실었다. 검토자에게 그것은 **프로그램
    결함**으로 보인다 — 실제로는 자원이 그 조합을 거부한 것이다.

    ⚠ **문면만 바꾸면 반대 방향으로 거짓말이 된다.** 진짜 계산 실패에도
    「설계 제약」이라 인쇄하면 결함이 정상으로 보인다. 그래서 여기서 재는 것은
    *예쁜 문면*이 아니라 **둘이 갈리는가**다 — 같은 자리에 서로 다른 예외를
    넣어 두 문면을 함께 본다.
    """
    design = _blocked_review(
        ValidationError(
            field="probe.power_kw",
            reason="probe: 계획이 정격출력을 넘습니다",
            action="출력을 키우십시오",
        )
    )
    failure = _blocked_review(ZeroDivisionError("division by zero"))

    for finding in design:
        refused = [p for p in finding.points if p.conclusion is None]
        assert refused, f"{finding.variable}: 거부된 점이 사라졌다"
        assert all(p.by_design for p in refused), "입력 검증 실패가 결함으로 세어졌다"
        assert all(p.blocked_field == "probe.power_kw" for p in refused), (
            "거부한 필드가 실리지 않았다 — 「무엇을 함께 바꿔야 하는가」에 답할 수 없다"
        )
    for finding in failure:
        refused = [p for p in finding.points if p.conclusion is None]
        assert refused, f"{finding.variable}: 실패한 점이 사라졌다"
        assert not any(p.by_design for p in refused), "결함이 설계 제약으로 세어졌다"

    def rows(findings) -> str:
        """**표의 행만** — 머리말 설명은 두 라벨을 둘 다 소개하므로 뺀다."""
        return "\n".join(
            line for line in capacity_appendix(findings) if line.startswith("| ")
        )

    design_text = "\n".join(capacity_appendix(design))
    assert BLOCKED_BY_DESIGN in rows(design), "거부된 점이 설계 제약으로 인쇄되지 않았다"
    assert BLOCKED_BY_FAILURE not in rows(design), (
        "입력 검증 실패가 「계산 실패」로 인쇄됐다 — 검토자에게 결함으로 보인다"
    )
    assert BLOCKED_BY_FAILURE in rows(failure), "결함이 계산 실패로 인쇄되지 않았다"
    assert BLOCKED_BY_DESIGN not in rows(failure), (
        "결함이 「설계 제약」으로 인쇄됐다 — 이번에는 반대 방향으로 거짓말이 된다"
    )

    # ★ **원문은 지우지 않는다 — 주로 내려간다.** 우리 판정이 맞는지 검토자가
    # 되짚을 수 있어야 하고, 그 근거는 자원이 실제로 한 말이다.
    assert "계획이 정격출력을 넘습니다" in design_text, "거부 원문이 사라졌다"
    assert "주1)" in design_text, "원문이 주로 내려가지 않았다"
    # 조치 지시는 표에도 주에도 싣지 않는다 (양식 0절).
    assert "십시오" not in design_text, "조치 지시가 표나 주에 실렸다"


def test_a_real_failure_is_not_counted_as_a_capacity_bound() -> None:
    """★★ **결함은 설계의 상한을 말해 주지 않는다.**

    `binding_constraint` 가 `bounded`(적정 용량이 이 모델 안에서 정해지는가)를
    정한다. 종전에는 `except Exception` 하나가 둘을 함께 받아, **예외가 나는
    구간이 「제약에 걸렸다」로 세어져** 4.4 가 *「적정값이 정해진다」* 를
    냈다 — 실제로 정해진 것은 아무것도 없고 계산이 깨진 것이다.
    """
    for finding in _blocked_review(ZeroDivisionError("division by zero")):
        assert finding.binding_constraint is None, (
            f"{finding.variable}: 계산 실패가 자원 제약으로 세어졌다 — "
            f"{finding.binding_constraint}"
        )
        assert not finding.bounded, (
            "결함이 났을 뿐인데 「적정 용량이 정해진다」로 나왔다"
        )
