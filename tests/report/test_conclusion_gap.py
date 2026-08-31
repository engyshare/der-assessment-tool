"""**전환 인자가 0건일 때 5.1 이 무엇을 싣는가** — FR-1002-AC4 · FR-1001-AC3.

R35 가 잉여 판매단가를 대장으로 올린 뒤, 실물 대장의 두 골든 시나리오는 **어느
인자도 검토 범위 안에서 0 선을 넘기지 못한다**. 그 상태에서 5.1 은 *「단독 전환
인자 — 없음」* 한 줄이었고, 그 한 줄은 참이지만 검토자가 묻는 것에 답하지 않는다
— **「없음」은 *조금 모자란다* 와 *두 배 모자란다* 를 같은 글자로 적는다.**

그래서 본문이 거리를 싣는다. 이 파일이 보는 것은 그 거리가 **환산이지 장식이
아닌가**다.

    거리가 본문에 실린다              ← 「없음」 한 줄로 끝나지 않는다
    ★ 상한에서 다시 돌린 값과 맞는다     ← 표시만 하는 구현을 걸러 낸다
    ★ 두 시나리오가 같은 값을 낸다      ← 지원이 `t=0` 감액이라는 규약의 대조
    ★ 1절 요약이 그 수를 그대로 싣는다   ← 검토자가 **먼저 보는 표**
    인자마다 남는 거리가 실린다        ← 끝까지 밀어도 얼마가 남는가
    미반영 인자를 「닫힌 자리」로 적지 않는다

★ **R49/WP-2 가 재는 대상을 옮겼다** (판정 `docs/decisions-2026-08-31-R49.md`
§2). 전환 지원율이 지원 상한(100%)을 넘어 **답으로 제시할 수 없게** 되면서,
둘째·셋째가 견주는 수가 「전환 지원율(백분율)」에서 **「전액 지원해도 남는
결손(원)」** 으로 바뀌었다. 지키는 성질은 그대로다 — *인쇄된 수가 재실행으로
확인되는 실물인가* · *네 자리가 한 수를 싣는가*.

둘째·셋째가 요점이다. 첫째와 넷째는 **거리를 인쇄만 하는 구현도 통과한다** —
R33 의 `_find_flip_threshold` 결함이 「임계값을 표시만」 하는 구현으로도 통과했던
것과 같은 형태이므로, 값의 뜻을 **다른 층에서** 확인한다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.contracts.validation import ValidationError
from core.report._format import NO_VALUE, _num, _won
from core.report.appendix_sections import UNREAD_BY_PIPELINE
from core.report.case_report import (
    CONCLUSION_METRIC,
    MAX_SUBSIDY_RATE,
    PLAN_VARIANT,
    CaseReport,
    _scheme_for,
    build_case_report,
)
from core.report.narrative import (
    FULL_SUPPORT_LINE_HEAD,
    GAP_MARGIN,
    GAP_SHORTFALL,
    render_markdown,
)
from tests.report.conftest import report_shapes

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"


def _report(name: str = "scenario_unsubsidized") -> CaseReport:
    return build_case_report(
        _GOLDEN / f"{name}.yaml", assumptions_path=_ASSUMPTIONS
    )


def _load_kwh() -> float:
    """본 실행과 **같은 가구 부하** (R48/WP-B → WP-F).

    `build_case_report` 가 `annual_load_kwh` 를 넘기므로, 재실행이 그것을
    빠뜨리면 **부하 있는 리포트의 수를 부하 없는 사업**에 대고 재게 되고
    두 수는 언제나 갈린다 — 그 어긋남은 지원율 환산의 잘못처럼 읽힌다.
    """
    return float(build_level_map(_ASSUMPTIONS)["household_load_annual_kwh"]["base"])


def _section(report: CaseReport) -> str:
    text = render_markdown(report)
    return text[text.index("### 5.1 불확실 인자") : text.index("### 5.2 정책 설정값")]


#: 1절 요약 표의 그 행 · 본문 5.1 의 그 줄. **머리를 상수로 둔다** — 행 이름이
#: 다른 행의 접두로 자라는 변이(R35 ③ M4)는 접두 검사를 통과하므로, 여기서
#: 「정확히 이 이름의 행이 하나」를 함께 요구한다.
_SUMMARY_ROW_HEAD = "| 결론 전환 지원율 |"
_BODY_LINE_HEAD = "- 결론 전환 지원율 —"
#: 6.2 종합의 지원 행 — **네 번째 자리**다 (R43-G · `narrative._subsidy_flip_row`).
_SUPPORT_ROW_HEAD = "| 지원 (보조율) |"
#: 붙임 3 이 「전액 지원해도 얼마가 남는가」를 대입값으로 지는 산식의 이름.
_RESIDUAL_FORMULA = "전액 지원 시 잔여 결손"
_PERCENT = re.compile(r"\d+(?:\.\d+)?%")
_WON = re.compile(r"[\d,]+원")
#: 값 칸의 **머리에 선 백분율** — 굵게(`**52.6%**`)든 맨눈이든.
_LEADING_PERCENT = re.compile(r"\*{0,2}-?\d+(?:\.\d+)?%")


def _one_line(text: str, head: str) -> str:
    """`head` 로 시작하는 줄이 **정확히 하나**임을 요구하고 그 줄을 낸다."""
    hits = [line for line in text.splitlines() if line.startswith(head)]
    assert len(hits) == 1, (
        f"「{head}」로 시작하는 줄이 {len(hits)}개다 — 0개면 그 행이 지워졌거나 "
        f"다른 이름을 달고 나온 것이고, 둘 이상이면 같은 수가 두 곳에 실린 "
        f"것이다: {hits}"
    )
    return hits[0]


def _percents(line: str) -> list[str]:
    """줄에 실린 백분율을 **적힌 그대로** 왼쪽부터. 자리수 변이를 보려면 값이
    아니라 문면을 견주어야 한다 — `53%` 와 `52.6%` 는 값으로는 가깝다."""
    found = _PERCENT.findall(line)
    assert found, f"백분율이 없다 — 줄: {line}"
    return found


def _answer_cells(text: str) -> dict[str, str]:
    """전환 지원율 물음에 **답하는 자리 셋의 값 칸**만 떼어 낸다.

    1. 요약 · 6.2 는 표의 셋째 칸(`| 이름 | 값 | …`)이고 5.1 은 줄 이름 뒤다.
    붙임 3 은 여기 없다 — 그쪽은 *「이 수가 어디서 왔는가」* 를 대입값으로 답하는
    **산식 자리**이고, 답을 내세우는 자리가 아니다.
    """
    return {
        "1. 요약": _one_line(text, _SUMMARY_ROW_HEAD).split("|")[2].strip(),
        "5.1": _one_line(text, _BODY_LINE_HEAD)[len(_BODY_LINE_HEAD) :].strip(),
        "6.2": _one_line(text, _SUPPORT_ROW_HEAD).split("|")[2].strip(),
    }


def _first_won(line: str) -> str:
    """줄에 실린 **첫 금액을 적힌 그대로**. 백분율과 같은 이유로 문면이다 —
    `316만원` 과 `3,156,180원` 은 값으로는 같고 자리수 변이는 값 비교로는
    보이지 않는다."""
    found = _WON.search(line)
    assert found is not None, f"금액이 없다 — 줄: {line}"
    return found.group(0)


@pytest.mark.req("FR-1002-AC4")
def test_the_body_says_how_far_the_conclusion_is_from_the_zero_line() -> None:
    """5.1 이 **거리를 수로** 싣는다 — 「없음」 한 줄로 끝나지 않는다.

    ⚠ 「없음」 줄의 유무를 조건으로 걸지 않았다. 거리는 전환 인자가 있든 없든
    같은 물음에 답하므로 **어느 경우에도** 실려야 하며, 조건을 걸면 전환 인자가
    생기는 날 이 검사가 0회 순회로 조용히 통과한다.
    """
    report = _report()
    section = _section(report)

    gap = report.conclusion_gap_won
    assert gap > 0.0, (
        "결론 축이 정확히 0 이다 — 이 검사가 「거리 0」을 정당한 상태로 읽는다. "
        "그런 실행에서는 거리가 아니라 회수 여부만 물어야 한다"
    )
    assert _won(gap) in section, (
        f"5.1 에 결론까지 남은 거리({_won(gap)})가 없다 — 검토자가 「얼마나 "
        "모자란가」를 본문에서 읽을 수 없다"
    )
    direction = GAP_MARGIN if report.recovers_within_horizon else GAP_SHORTFALL
    assert direction in section, (
        f"거리의 방향 라벨(`{direction}`)이 없다 — 금액만 있으면 결손과 여유가 "
        "같은 글자로 읽힌다"
    )
    assert f"{report.break_even_subsidy_rate:.1%}" in section, (
        "결론 전환 지원율이 5.1 에 없다"
    )
    # 총사업비 분모가 **기준선**의 것이다 — 지원을 받은 변형의 초기지출을 쓰면
    # 같은 사업의 결손 비율이 지원율에 따라 달라진다.
    assert _won(report.total_project_cost_won) in section, (
        "거리를 견줄 총사업비가 5.1 에 없다"
    )


@pytest.mark.req("FR-1002-AC4", "FR-607-AC1")
def test_support_at_the_ceiling_moves_the_conclusion_to_the_reported_residual() -> None:
    """★★ **지원을 상한까지 올려 다시 돌리고, 리포트가 싣는 잔여 결손과 맞춘다.**

    ## 오라클은 그대로다 — **재는 대상만 옮겼다** (R49/WP-2 · 판정 §2)

    종전 이 검사는 *「보고된 전환 지원율로 다시 돌리면 결론 축이 0 인가」* 를
    물었다. 지키던 성질은 **「인쇄된 수는 표시가 아니라 재실행으로 확인되는
    실물이다」** 이고, 그것은 여전히 지켜야 한다 — 정책 판단에 그대로 쓰이는
    수는 계산과 무관해도 그럴듯하게 읽힌다(R33 이 임계값에서 만난 형태).

    바뀐 것은 **인쇄되는 수**다. 전환 지원율이 지원 상한
    (`MAX_SUBSIDY_RATE`)을 넘어 **그 값으로는 돌릴 수조차 없으므로**(아래
    `DV-1`), 리포트는 그것을 답으로 제시하지 않고 *「전액 지원해도 남는
    결손」* 을 대신 싣는다. 그래서 재실행도 **상한에서** 한다.

    ⚠ **리포트를 다시 조립하지 않고 파이프라인을 직접 돈다.** 같은 조립기로
    확인하면 그 조립기의 환산을 그 조립기로 검산하는 것이 되어 **동어반복**이
    된다(R35 함정 절). 여기서 정본은 진입점 `run_single_case_e2e` 다.
    """
    report = _report()
    rate = report.break_even_subsidy_rate
    assert not report.support_alone_can_flip, (
        f"전환 지원율이 {rate:.1%} 로 지원 상한({MAX_SUBSIDY_RATE:.0%}) 안에 "
        "들어왔다 — 그러면 리포트는 다시 그 값을 답으로 싣고, 이 검사는 "
        "**그 지원율로** 돌려 결론 축이 0 인지 보아야 한다. 실물이 바뀌었으면 "
        "재는 자리를 되돌릴 것"
    )

    # ★ **그 지원율은 넣어 돌릴 수 없다.** 판정 §2 가 「있을 수 없는 답」이라
    # 적은 근거가 이것이며, 규칙이 사라지면 리포트는 다시 **실행되지 않는
    # 조건**을 달성 조건으로 실을 수 있게 된다. 🚫 `DV-1` 을 풀어 이 검사를
    # 통과시키지 마라 — 자부담이 음수인 사업을 만드는 것이다.
    with pytest.raises(ValidationError) as refused:
        run_single_case_e2e(
            {},
            level_map=build_level_map(_ASSUMPTIONS),
            horizon_years=report.basis.horizon_years,
            scheme=_scheme_for(rate),
            daily_shapes=report_shapes(),
            annual_load_kwh=_load_kwh(),
        )
    assert refused.value.rule == "DV-1", (
        f"전환 지원율 {rate:.4%} 를 넣었는데 `DV-1` 이 아닌 "
        f"`{refused.value.rule}` 로 거부됐다 — 자부담 음수를 막는 규칙이 "
        "아니라면 이 검사의 전제가 다른 것이다"
    )

    # ★ **리포트와 같은 배선으로 돌린다 (R37 · R48/WP-B).** `build_case_report`
    # 가 일사 곡선과 **가구 부하**를 본 실행에 넘기므로, 둘 없이 다시 돌리면
    # 리포트의 수를 **다른 사업**의 0 선에 대고 재는 것이 된다.
    outcome = run_single_case_e2e(
        {},
        level_map=build_level_map(_ASSUMPTIONS),
        horizon_years=report.basis.horizon_years,
        scheme=_scheme_for(MAX_SUBSIDY_RATE),
        daily_shapes=report_shapes(),
        annual_load_kwh=_load_kwh(),
    )
    npv = float(outcome.variants[PLAN_VARIANT][CONCLUSION_METRIC])

    # 허용오차는 **총사업비에 대한 비율**로 잡는다. 원 단위 절대값으로 잡으면
    # 사업 규모가 바뀔 때 이 검사가 의미 없이 빨간불이 된다.
    tolerance = report.total_project_cost_won * 1e-6
    residual = report.residual_gap_at_full_support_won
    assert npv == pytest.approx(residual, abs=tolerance), (
        f"지원 {MAX_SUBSIDY_RATE:.0%} 로 다시 돌렸더니 결론 축이 {npv:,.0f}원인데 "
        f"리포트는 잔여 결손을 {residual:,.0f}원으로 싣는다 "
        f"(허용 ±{tolerance:,.2f}원). 리포트가 「전액 지원해도 남는 결손」을 "
        "환산이 아니라 표시로만 싣고 있다"
    )


@pytest.mark.req("FR-1002-AC4", "FR-607-AC1")
def test_the_break_even_support_rate_agrees_across_two_support_levels() -> None:
    """★★ **지원율이 다른 두 시나리오가 같은 전환 지원율을 낸다.**

    무보조와 보조 80% 는 결론 축이 서로 다르다(−5,156,392원 · +2,683,608원).
    그런데 지원이 `t=0` 초기지출 감액이라면 **0 선에 닿는 지원율은 한 값**이다.
    두 리포트가 그 한 값을 내는지가 환산 규약의 대조군이다 — 어긋나면 지원이
    다른 경로로 들어온 것이고, 그때는 이 환산을 본문에 실을 수 없다.

    ⚠ 한 시나리오만 보는 검사로는 이것을 잡을 수 없다. 어떤 잘못된 환산도
    자기 시나리오에서는 자기 자신과 맞는다.
    """
    plain = _report("scenario_unsubsidized")
    subsidised = _report("scenario_subsidy_80")

    assert plain.metrics[CONCLUSION_METRIC] != pytest.approx(
        subsidised.metrics[CONCLUSION_METRIC]
    ), "두 시나리오의 결론 축이 같다 — 이 대조가 아무것도 재지 못한다"
    assert plain.subsidy_rate != subsidised.subsidy_rate

    assert plain.break_even_subsidy_rate == pytest.approx(
        subsidised.break_even_subsidy_rate, rel=1e-9
    ), (
        f"전환 지원율이 시나리오마다 다르다 — 무보조 "
        f"{plain.break_even_subsidy_rate:.4%} · 보조 "
        f"{subsidised.subsidy_rate:.0%} 에서 "
        f"{subsidised.break_even_subsidy_rate:.4%}. 지원이 `t=0` 초기지출 "
        "감액이라는 규약이 깨졌다"
    )


@pytest.mark.req("FR-1001-AC3")
def test_the_support_rate_formula_carries_the_same_number_as_the_body() -> None:
    """붙임 3 의 산식과 본문 5.1 이 **같은 수**를 싣는다.

    본문은 값만, 붙임 3 은 대입값을 진다. 둘이 갈리면 검토자가 값을 따라가
    확인하는 순간 리포트가 스스로를 부정한다 — 그것이 `MC-1` 의 첫 물음이다.
    """
    report = _report("scenario_subsidy_20")
    substituted = {formula.label: formula.substituted for formula in report.formulas}

    assert "결론 전환 지원율" in substituted, (
        "붙임 3 에 전환 지원율 산식이 없다 — 본문 5.1 이 값만 싣고 근거가 "
        "어디에도 없다"
    )
    line = substituted["결론 전환 지원율"]
    assert f"{report.break_even_subsidy_rate:.1%}" in line, (
        f"산식 대입값({line})이 본문의 전환 지원율과 다르다"
    )
    assert f"{report.total_project_cost_won:,.0f}원" in line, (
        "산식에 총사업비가 없다 — 환산의 분모를 검토자가 볼 수 없다"
    )


@pytest.mark.req("FR-1002-AC4", "FR-607-AC1", "FR-1001-AC3")
def test_the_summary_row_carries_the_same_support_numbers_as_the_body() -> None:
    """★★ **1절 요약이 「지원만으로는 안 된다」를 본문과 같은 수로 싣는가.**

    ## 오라클은 그대로다 — **재는 대상만 옮겼다** (R49/WP-2 · 판정 §2)

    지키던 성질은 **「요약 · 5.1 · 6.2 · 붙임 3 이 한 수를 싣는다」** 이고,
    그것은 여전히 지켜야 한다 — 요약이 스스로 환산하면 검토자는 **먼저 보는
    표에서 본문과 다른 수**를 읽고, 그 어긋남은 두 절을 대조할 때에야 드러난다.

    바뀐 것은 **견주는 수**다. 전환 지원율(백분율)은 지원 상한을 넘어 답으로
    성립하지 않으므로, 네 자리가 함께 지는 수는 이제 **전액 지원해도 남는
    결손(원 단위)** 이다. 백분율 쪽 네 자리 일치는
    `test_narrative.py::test_the_break_even_subsidy_rate_is_one_number_in_four_places`
    가 계속 붙든다.

    ## ★ 같은 조립기의 네 자리를 서로 견주는 것만으로는 부족하다

    자기가 계산한 수를 네 곳에 똑같이 인쇄하는 구현은 전건 통과한다(R35 함정
    절). 그래서 둘을 더 본다.

    - **두 시나리오 대조** — 무보조(0%)와 보조 80% 는 결론 축이 다른데
      (−12,956,180원 · −5,116,180원) 잔여 결손은 **한 값**이다. 지원이 `t=0`
      감액이라는 규약이 그렇게 만든다. 한 시나리오만 보는 검사는 어떤 잘못된
      환산도 통과시킨다 — 자기 시나리오에서는 자기 자신과 맞기 때문이다.
    - **인쇄된 그 금액을 진입점의 실측과 맞댄다** — 정본은
      `run_single_case_e2e` 이고, 지원을 **상한까지** 올려 돌린 결론 축이
      그 금액이어야 한다.

    ⚠ 금액도 백분율과 마찬가지로 **값이 아니라 문면**으로 견준다.
    `316만원` 과 `3,156,180원` 은 값으로는 같다.
    """
    printed: dict[str, str] = {}
    for name in ("scenario_unsubsidized", "scenario_subsidy_80"):
        report = _report(name)
        text = render_markdown(report)
        assert not report.support_alone_can_flip, (
            f"{name}: 지원만으로 전환된다 — 그러면 네 자리는 「전액 지원해도 "
            "남는 결손」을 싣지 않는다(그 갈래는 리포트가 지운 것이 아니라 "
            "서지 않은 것이다). 실물이 바뀌었으면 재는 자리를 되돌릴 것"
        )
        expected = _won(abs(report.residual_gap_at_full_support_won))

        row = _one_line(text, _SUMMARY_ROW_HEAD)
        substituted = {
            formula.label: formula.substituted for formula in report.formulas
        }
        assert _RESIDUAL_FORMULA in substituted, (
            f"{name}: 붙임 3 에 「{_RESIDUAL_FORMULA}」 산식이 없다 — 본문이 "
            "금액만 싣고 그 금액이 어디서 왔는지 따라갈 자리가 없다"
        )
        places = {
            "1. 요약": row,
            "5.1": _one_line(text, FULL_SUPPORT_LINE_HEAD),
            "6.2": _one_line(text, _SUPPORT_ROW_HEAD),
            "붙임 3": substituted[_RESIDUAL_FORMULA],
        }
        for where, line in places.items():
            assert expected in line, (
                f"{name}: {where} 의 잔여 결손이 환산({expected})과 다르다 — "
                f"그 자리가 스스로 계산했거나 자리수를 줄여 실었다. 줄: {line}"
            )

        # 수와 **그 수가 나온 조건**의 짝 (R35 ② 함정 절). 현 지원율을 함께
        # 싣지 않으면 두 시나리오의 요약 행이 서로 바뀌어도 매끈하다.
        # ⚠ **자리로 집지 않는다** — 값 칸의 백분율이 하나가 아니므로(상한
        # 100% · 환산값) 「몇 번째 백분율」로 집으면 문면이 늘 때마다 낡는다.
        assert f"(현 지원율 {report.subsidy_rate:.1%}" in row, (
            f"{name}: 요약 행에 이 시나리오의 현 지원율"
            f"({report.subsidy_rate:.1%})이 없다 — 행: {row}"
        )

        # ★ 다른 층 — 요약에 **인쇄된 그 금액**을 진입점의 실측과 맞댄다.
        # 지원을 상한까지 올린 실행의 결론 축이 그 금액이다.
        shown = float(_first_won(row).rstrip("원").replace(",", ""))
        outcome = run_single_case_e2e(
            {},
            level_map=build_level_map(_ASSUMPTIONS),
            horizon_years=report.basis.horizon_years,
            scheme=_scheme_for(MAX_SUBSIDY_RATE),
            # ★ 리포트와 같은 배선 (R37 · R48/WP-B) — 형상·부하 없이 돌리면
            # 리포트의 수를 **다른 사업**의 0 선에 대고 재게 된다. 실측으로
            # 걸렸다: 곡선 배선 뒤 이 검사가 125,808원(≈ 곡선↔평탄 차이
            # 128,194원)을 남겼다.
            daily_shapes=report_shapes(),
            annual_load_kwh=_load_kwh(),
        )
        npv = float(outcome.variants[PLAN_VARIANT][CONCLUSION_METRIC])
        assert npv < 0.0, (
            f"{name}: 지원 {MAX_SUBSIDY_RATE:.0%} 로 돌렸더니 결론 축이 "
            f"{npv:,.0f}원이다 — 전액 지원으로 결론이 서는데도 리포트는 "
            "「전환되지 않는다」고 적고 있다"
        )
        # 표시 자리수(원 단위)의 반 칸보다 넓게 잡되 사업 규모에 비례시킨다.
        # 원 단위 절대값으로 잡으면 사업 규모가 바뀔 때 의미 없이 빨간불이 된다.
        tolerance = report.total_project_cost_won * 0.0005
        assert abs(npv) == pytest.approx(shown, abs=tolerance), (
            f"{name}: 요약에 실린 잔여 결손 {shown:,.0f}원이 지원 "
            f"{MAX_SUBSIDY_RATE:.0%} 실측({abs(npv):,.0f}원)과 다르다 "
            f"(허용 ±{tolerance:,.0f}원) — 요약이 환산이 아닌 수를 싣고 있다. "
            f"행: {row}"
        )
        printed[name] = expected

    assert len(set(printed.values())) == 1, (
        f"두 시나리오가 다른 잔여 결손을 싣는다 — {printed}. 지원이 `t=0` "
        "초기지출 감액이라면 전액 지원 시 남는 결손은 **한 값**이며, 갈렸다는 "
        "것은 지원이 다른 경로로 들어왔다는 뜻이다"
    )


@pytest.mark.req("FR-1002-AC4")
def test_no_answer_cell_leads_with_a_support_rate_that_cannot_be_given() -> None:
    """★★ **줄 수 없는 지원율이 「답」 자리에 서지 않는다** (판정 §2).

    ## 무엇을 잡는 검사인가

    *「세 자리가 같은 잔여 결손을 싣는가」* 는 위 검사가 본다. 그런데 그것만으로는
    **굵은 `132.2%` 를 먼저 싣고 뒤에 단서를 붙인** 문면이 전건 통과한다 — 판정이
    적은 것은 *「그 숫자를 **답으로 제시하지 않는다**」* 이지 *「제시한 뒤에 단서를
    붙인다」* 가 아니다.

    ★ 이 저장소는 그 위험을 **이미 한 번 겪었다**: 실제로 발췌돼 인용되는 것은
    행의 말이 아니라 **그 굵은 수**다(R43-G · `narrative._subsidy_flip_row`
    독스트링 · 문의사항 나-2). 심의회 자료에서 「지원율 132.2%」 한 칸만 떼어
    가면 **줄 수 없는 지원율이 달성 조건으로 나간다.**

    ## 함께 보는 것 — **현 지원율은 남아 있어야 한다**

    백분율을 걷어내면서 `(현 지원율 …%)` 까지 함께 지우는 변이가 있다. 그것은
    **실제로 적용된 값**이지 달성 조건이 아니며, 없으면 검토자가 *어느 지원
    수준의 사업을 보고 있는지* 알 수 없다. 둘 다 보아야 한 쪽만 고친 구현이
    걸린다.

    ⚠ **문면으로 본다.** 값 비교로는 「어느 수가 값 칸의 머리에 서 있는가」를
    잴 수 없다.
    """
    for name in ("scenario_unsubsidized", "scenario_subsidy_80"):
        report = _report(name)
        text = render_markdown(report)
        assert not report.support_alone_can_flip, (
            f"{name}: 지원만으로 전환된다 — 그 갈래에서 백분율은 **정당한 답**"
            "이므로 이 검사가 재는 것이 없다. 실물이 바뀌었으면 갈래를 다시 고를 것"
        )
        rate_text = f"{report.break_even_subsidy_rate:.1%}"
        won_text = _won(abs(report.residual_gap_at_full_support_won))

        for where, cell in _answer_cells(text).items():
            assert _LEADING_PERCENT.match(cell) is None, (
                f"{name}: {where} 의 값 칸이 백분율로 시작한다 — 지원 상한을 "
                f"넘어 **줄 수 없는 지원율**이 답의 자리에 서 있다. 칸: {cell}"
            )
            assert f"(현 지원율 {report.subsidy_rate:.1%}" in cell, (
                f"{name}: {where} 의 값 칸에 현 지원율"
                f"({report.subsidy_rate:.1%})이 없다 — 백분율을 걷어내면서 "
                f"**적용된 값**까지 함께 지웠다. 칸: {cell}"
            )
            if rate_text in cell:
                # 환산값을 통째로 없애라는 것이 아니다(붙임 3 이 그 수의 출처를
                # 진다). 다만 **답의 자리는 금액**이어야 하므로 순서를 본다.
                assert cell.index(won_text) < cell.index(rate_text), (
                    f"{name}: {where} 의 값 칸에서 전환 지원율({rate_text})이 "
                    f"잔여 결손({won_text})보다 앞선다 — 읽는 눈에는 앞선 수가 "
                    f"답이다. 칸: {cell}"
                )


def test_the_flipping_branch_still_leads_with_the_support_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ **갈래를 지우지 않았는가** — 전환되는 쪽은 백분율이 답이다.

    ⚠ **골든에 그 갈래가 없다.** 셋 다 전환 지원율이 상한을 넘는다(실측
    132.2%). 그래서 시나리오를 **지어내지 않고**(없는 사업을 만드는 것이다)
    `support_alone_can_flip` 한 갈래만 뒤집어 **문면의 갈래**를 확인한다 —
    이 검사가 재는 것은 사업이 아니라 `narrative._support_answer` 의 분기다.

    이 갈래가 사라지면 보조율이 오르거나 사업비가 바뀌어 다시 전환 가능해진
    날에도 리포트가 *「지원만으로는 안 된다」* 를 계속 인쇄한다 — 그리고 그
    문장은 그때 **거짓**이다.

    ⚠ 붙임 3 은 여기서 보지 않는다. 그쪽 갈래는 프로퍼티가 아니라
    `case_report._formulas()` 가 환산값에서 직접 판정하므로, 이 뒤집기로는
    함께 움직이지 않는다.
    """
    report = _report()
    monkeypatch.setattr(
        CaseReport, "support_alone_can_flip", property(lambda self: True)
    )
    text = render_markdown(report)
    expected = f"**{report.break_even_subsidy_rate:.1%}**"

    for where, cell in _answer_cells(text).items():
        assert cell.startswith(expected), (
            f"{where}: 전환되는 갈래인데 값 칸이 전환 지원율({expected})로 "
            f"시작하지 않는다 — 갈래가 지워졌다. 칸: {cell}"
        )


@pytest.mark.req("FR-1002-AC3", "FR-1002-AC4")
def test_every_factor_that_does_not_flip_shows_the_gap_that_remains() -> None:
    """전환하지 못한 인자마다 **끝까지 밀었을 때 남는 거리**가 실린다.

    ★ 이 표가 없으면 검토자는 붙임 2 의 `변동폭` 으로 우선순위를 잡는데, 변동폭
    이 큰 인자가 반드시 0 선에 가까운 것은 아니다 — 반대 끝에서 시작하면 끝까지
    밀어도 더 멀다. 실측이 그렇다(판매단가는 변동폭 1위이면서 남는 거리도 가장
    작지만, 그 둘은 서로를 함의하지 않는다).

    ⚠ **행을 줄이지 않는다.** 상위 몇 개만 싣는 표는 「그 밖의 인자는 영향이
    없다」로 읽힌다.
    """
    report = _report()
    section = _section(report)
    expected = [
        entry for entry in report.uncertain_influences if not entry.flips_conclusion
    ]
    assert expected, "전환하지 않는 불확실 인자가 0건이다 — 이 검사가 0회 순회한다"

    for entry in expected:
        row = next(
            (
                line
                for line in section.splitlines()
                if line.startswith(f"| `{entry.variable}` ")
            ),
            None,
        )
        assert row is not None, (
            f"{entry.variable}: 전환하지 못한 인자가 5.1 의 어느 표에도 없다"
        )
        # 남는 거리는 **끝에서의 결론 축 절대값**이며, 두 끝 중 결론에 가까운
        # 쪽이어야 한다. 반대 끝을 싣는 구현은 사업을 실제보다 어둡게(또는
        # 밝게) 그린다.
        nearest_gap = min(abs(entry.npv_low), abs(entry.npv_high))
        farthest_gap = max(abs(entry.npv_low), abs(entry.npv_high))
        assert _won(nearest_gap) in row, (
            f"{entry.variable}: 5.1 이 가까운 끝의 거리"
            f"({_won(nearest_gap)})가 아니라 먼 끝({_won(farthest_gap)})을 "
            f"싣고 있다 — 행: {row}"
        )
        # 끝의 **값**도 같은 행에 있어야 한다. 거리만 실으면 검토자는 「무엇을
        # 얼마로 두었을 때인가」를 알 수 없고, 그러면 이 표는 순위표일 뿐이다.
        if entry.npv_low == entry.npv_high:
            # 두 끝이 같은 인자는 **방향이 없다.** 어느 끝을 적어도 「그쪽으로
            # 밀면 가까워진다」를 함의하므로 방향 칸은 비운다(위 미반영 검사가
            # 같은 행에서 라벨을 본다).
            assert NO_VALUE in row, (
                f"{entry.variable}: 두 끝의 결론 축이 같은데 한쪽 끝을 "
                f"전환 방향으로 적었다 — 행: {row}"
            )
            continue
        nearest_end = (
            entry.low if abs(entry.npv_low) < abs(entry.npv_high) else entry.high
        )
        assert _num(nearest_end) in row, (
            f"{entry.variable}: 가까운 끝의 값({_num(nearest_end)})이 행에 없다 "
            f"— 행: {row}"
        )
        assert entry.confidence in row, f"{entry.variable}: 신뢰도가 행에 없다"


@pytest.mark.req("FR-1002-AC2")
def test_the_endpoint_values_are_paired_with_the_run_that_produced_them() -> None:
    """★★ **두 끝의 결론 축이 그 끝에서 실제로 나온 값인가** — 짝을 검산한다.

    5.1 의 행은 「인자를 *이 값*으로 두면 *이만큼* 남는다」를 말한다. 두 끝의
    NPV 가 **서로 바뀌어** 실리면 거리 숫자는 그대로 맞고 열 순서도 그대로인데
    **문장만 거짓**이 된다 — *「판매단가를 150원까지 올려도 210만원 부족」* 이
    실은 80원일 때의 수인 것이다. 그 변이는 거리만 보는 검사를 전건 통과한다
    (실제로 심어 확인했다).

    그래서 짝을 **다른 층에서** 검산한다: 대장이 만든 수준표의 `low`·`high` 로
    진입점을 직접 돌려, 리포트가 그 이름에 붙여 둔 수와 맞는지 본다.
    """
    report = _report()
    level_map = build_level_map(_ASSUMPTIONS)
    horizon = report.basis.horizon_years
    scheme = _scheme_for(report.subsidy_rate)

    for entry in report.uncertain_influences:
        levels = level_map[entry.variable]
        for level, reported in (
            ("low", entry.npv_low),
            ("high", entry.npv_high),
        ):
            probe = {name: dict(values) for name, values in level_map.items()}
            probe[entry.variable] = {**levels, "base": levels[level]}
            outcome = run_single_case_e2e(
                {},
                level_map=probe,
                horizon_years=horizon,
                scheme=scheme,
                # ★ 리포트와 같은 배선 (R37) — `conftest.report_shapes` 참조.
                daily_shapes=report_shapes(),
                # ★★ 가구 부하도 같은 배선 (R48/WP-B → WP-F) — 본 실행·
                # `_Sweeper.conclusion_at_many()` 모두 `annual_load_kwh` 를
                # 넘긴다. 이 재실행만 안 넘기면 부하 있는 리포트 수를 부하 없는
                # 재실행과 맞대는 것이 되어 항상 갈린다.
                annual_load_kwh=probe["household_load_annual_kwh"]["base"],
            )
            measured = float(outcome.variants[PLAN_VARIANT][CONCLUSION_METRIC])
            assert reported == pytest.approx(measured, abs=1.0), (
                f"{entry.variable}: `{level}` 끝의 결론 축이 리포트에는 "
                f"{reported:,.0f}원인데 그 값으로 다시 돌리면 "
                f"{measured:,.0f}원이다 — 두 끝이 서로 바뀌어 실렸을 수 있다"
            )


@pytest.mark.req("FR-1002-AC3")
def test_a_factor_the_pipeline_never_read_is_not_shown_as_a_closed_gap() -> None:
    """★ **변동폭 0 인 인자를 「끝까지 밀어도 그대로」로만 적지 않는다.**

    미반영 인자는 어느 끝으로 밀어도 거리가 줄지 않는다. 그 행을 라벨 없이
    실으면 *「이 인자는 결론에 영향이 없다」* 로 읽히는데, 기계는 「진짜
    무영향」과 「미배선」을 가르지 못한다 — 붙임 2 가 같은 자리에서 같은 라벨을
    쓰는 이유다.
    """
    report = _report()
    section = _section(report)
    unread = [
        entry
        for entry in report.uncertain_influences
        if entry.unread_by_pipeline and not entry.flips_conclusion
    ]
    assert unread, (
        "미반영 인자가 0건이다 — 실물 대장에는 `tariff_escalation` 이 있다. "
        "정말 해소됐다면 이 검사를 지우는 것이 맞다"
    )

    for entry in unread:
        row = next(
            line
            for line in section.splitlines()
            if line.startswith(f"| `{entry.variable}` ")
        )
        assert UNREAD_BY_PIPELINE in row, (
            f"{entry.variable}: 미반영 인자가 5.1 에서 라벨 없이 실렸다 — "
            f"행: {row}"
        )
        assert _won(report.conclusion_gap_won) in row, (
            f"{entry.variable}: 미반영 인자인데 거리가 기준과 다르다 — 이 인자를 "
            "흔들면 결론 축이 움직인다는 뜻이므로 라벨이 틀렸다"
        )


@pytest.mark.req("FR-1002-AC4")
def test_the_subsidised_scenario_measures_the_distance_toward_the_flip() -> None:
    """★ **방향은 인자가 아니라 결론에서 읽는다** — 지원을 받은 갈래에서 본다.

    ## 갈래를 다시 골랐다 (R49/WP-2)

    이 검사는 **회수하는** 갈래를 보려고 보조 80% 를 골랐다(당시 결론 축
    +2,683,608원). R48 이 가구 전기요금을 세운 뒤 **그 시나리오도 회수하지
    못하고**(−5,116,180원), 골든 셋 어디에도 회수 갈래가 남아 있지 않다 —
    검사 자신이 적어 두었던 *「실물이 바뀌었으면 갈래를 다시 고를 것」* 이
    그것이다. 🚫 회수 갈래를 **만들려고** 탐침 단가를 낮추지 않는다: 현실에
    없는 설비값이 되고 *「이 값이면 됩니다」* 가 실현 불가능한 조건이 된다
    (판정 §3).

    ## 살아 있는 오라클 — **거리가 실물인가**

    5.1 이 답해야 하는 물음은 *「어디까지 좋아져야 뒤집히는가」* 이고, 방향을
    인자마다 부호로 적어 두면 편익·비용 인자가 늘 때 낡는다 — 낡은 부호는
    반대 끝을 「가까운 끝」으로 싣는다. 그래서 방향을 **결론에서** 읽는다.

    ⚠ 무보조 갈래는 `test_every_factor_that_does_not_flip_shows_the_gap_that_
    remains` 가 본다. 여기서 보는 것은 **지원 조건이 붙은** 실행이며, 지원이
    결론 축을 옮겨도 방향 읽기가 같은 자리에서 나오는지가 이 갈래의 몫이다.
    """
    report = _report("scenario_subsidy_80")
    assert not report.recovers_within_horizon, (
        "보조 80% 가 회수한다 — 이 검사는 **미회수** 갈래에서 거리를 재도록 "
        "전제를 바꾼 것이다. 회수 갈래가 다시 생겼으면 방향이 뒤집히는 쪽"
        "(`GAP_MARGIN`)을 보도록 되돌릴 것"
    )
    section = _section(report)
    assert GAP_SHORTFALL in section, "회수하지 못하는데 거리가 `결손` 이 아니다"

    base_npv = float(report.metrics[CONCLUSION_METRIC])
    for entry in report.uncertain_influences:
        if entry.flips_conclusion:
            continue
        # 미회수 갈래에서 **전환 방향**은 결론 축이 올라가는 쪽이다. 회수
        # 갈래에서는 같은 자리가 `min` 이었다 — 방향을 뒤집는 것은 인자가
        # 아니라 `recovers_within_horizon` 이며, 그 대칭이 이 검사의 요점이다.
        near = max(entry.npv_low, entry.npv_high)
        far = min(entry.npv_low, entry.npv_high)
        row = next(
            line
            for line in section.splitlines()
            if line.startswith(f"| `{entry.variable}` ")
        )
        assert far <= base_npv, (
            f"{entry.variable}: 두 끝이 모두 기준보다 좋다 — 스윕이 기준을 "
            "넘겨 계산했다"
        )
        assert _won(abs(near)) in row, (
            f"{entry.variable}: 미회수 상태인데 **나빠지는 끝**의 거리가 "
            f"실렸다 — 행: {row}. 이 표가 재는 것은 전환 방향의 끝이다"
        )
