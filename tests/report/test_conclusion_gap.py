"""**전환 인자가 0건일 때 5.1 이 무엇을 싣는가** — FR-1002-AC4 · FR-1001-AC3.

R35 가 잉여 판매단가를 대장으로 올린 뒤, 실물 대장의 두 골든 시나리오는 **어느
인자도 검토 범위 안에서 0 선을 넘기지 못한다**. 그 상태에서 5.1 은 *「단독 전환
인자 — 없음」* 한 줄이었고, 그 한 줄은 참이지만 검토자가 묻는 것에 답하지 않는다
— **「없음」은 *조금 모자란다* 와 *두 배 모자란다* 를 같은 글자로 적는다.**

그래서 본문이 거리를 싣는다. 이 파일이 보는 것은 그 거리가 **환산이지 장식이
아닌가**다.

    거리가 본문에 실린다              ← 「없음」 한 줄로 끝나지 않는다
    ★ 전환 지원율로 다시 돌리면 0 이다  ← 표시만 하는 구현을 걸러 낸다
    ★ 두 시나리오가 같은 값을 낸다      ← 지원이 `t=0` 감액이라는 규약의 대조
    ★ 1절 요약이 그 수를 그대로 싣는다   ← 검토자가 **먼저 보는 표**
    인자마다 남는 거리가 실린다        ← 끝까지 밀어도 얼마가 남는가
    미반영 인자를 「닫힌 자리」로 적지 않는다

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
from core.report._format import NO_VALUE, _num, _won
from core.report.appendix_sections import UNREAD_BY_PIPELINE
from core.report.case_report import (
    CONCLUSION_METRIC,
    PLAN_VARIANT,
    CaseReport,
    _scheme_for,
    build_case_report,
)
from core.report.narrative import GAP_MARGIN, GAP_SHORTFALL, render_markdown

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"


def _report(name: str = "scenario_unsubsidized") -> CaseReport:
    return build_case_report(
        _GOLDEN / f"{name}.yaml", assumptions_path=_ASSUMPTIONS
    )


def _section(report: CaseReport) -> str:
    text = render_markdown(report)
    return text[text.index("### 5.1 불확실 인자") : text.index("### 5.2 정책 설정값")]


#: 1절 요약 표의 그 행 · 본문 5.1 의 그 줄. **머리를 상수로 둔다** — 행 이름이
#: 다른 행의 접두로 자라는 변이(R35 ③ M4)는 접두 검사를 통과하므로, 여기서
#: 「정확히 이 이름의 행이 하나」를 함께 요구한다.
_SUMMARY_ROW_HEAD = "| 결론 전환 지원율 |"
_BODY_LINE_HEAD = "- 결론 전환 지원율 —"
_PERCENT = re.compile(r"\d+(?:\.\d+)?%")


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
def test_the_break_even_support_rate_actually_zeroes_the_conclusion() -> None:
    """★★ **보고된 전환 지원율로 다시 돌려 결론 축이 0 이 되는지 본다.**

    이 검사가 없으면 「지원율 52.6%」를 **인쇄만** 하는 구현이 통과한다. 그
    숫자는 정책 판단에 그대로 쓰이는 값이며(*「얼마를 지원해야 하는가」*),
    계산과 무관해도 그럴듯하게 읽힌다 — R33 이 임계값에서 만난 형태와 같다.

    ⚠ **리포트를 다시 조립하지 않고 파이프라인을 직접 돈다.** 같은 조립기로
    확인하면 그 조립기의 환산을 그 조립기로 검산하는 것이 되어 **동어반복**이
    된다(R35 함정 절). 여기서 정본은 진입점 `run_single_case_e2e` 다.
    """
    report = _report()
    rate = report.break_even_subsidy_rate
    assert 0.0 < rate < 1.0, (
        f"전환 지원율이 {rate:.1%} 로 지원 범위 밖이다 — 이 검사가 재실행으로 "
        "확인할 수 있는 구간을 벗어났다"
    )

    outcome = run_single_case_e2e(
        {},
        level_map=build_level_map(_ASSUMPTIONS),
        horizon_years=report.basis.horizon_years,
        scheme=_scheme_for(rate),
    )
    npv = float(outcome.variants[PLAN_VARIANT][CONCLUSION_METRIC])

    # 허용오차는 **총사업비에 대한 비율**로 잡는다. 원 단위 절대값으로 잡으면
    # 사업 규모가 바뀔 때 이 검사가 의미 없이 빨간불이 된다.
    tolerance = report.total_project_cost_won * 1e-6
    assert abs(npv) <= tolerance, (
        f"전환 지원율 {rate:.4%} 로 다시 돌렸는데 결론 축이 {npv:,.0f}원이다 "
        f"(허용 ±{tolerance:,.2f}원). 리포트가 지원 필요액을 환산이 아니라 "
        "표시로만 싣고 있다"
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
def test_the_summary_row_carries_the_same_support_rate_as_the_body() -> None:
    """★★ **1절 요약의 「결론 전환 지원율」이 세 자리에서 한 수인가.**

    요약 · 본문 5.1 · 붙임 3 산식이 같은 수를 실어야 한다. 요약이 스스로
    환산하면 검토자는 **먼저 보는 표에서 본문과 다른 수**를 읽고, 그 어긋남은
    두 절을 대조할 때에야 드러난다.

    ## ★ 값 셋 중 둘이 **다른 층**에서 온다

    같은 조립기의 세 자리를 서로 견주는 것만으로는 부족하다 — 자기가 계산한 수를
    세 곳에 똑같이 인쇄하는 구현은 전건 통과한다(R35 함정 절). 그래서 둘을 더
    본다.

    - **두 시나리오 대조** — 무보조(0%)와 보조 80% 는 결론 축이 다른데
      전환 지원율은 **한 값**이다. 요약이 *결손/총사업비* 를 직접 계산하면
      무보조에서는 우연히 맞고(지원율이 0 이므로 두 식이 같다) **보조 80% 에서
      갈린다.** 한 시나리오만 보는 검사는 어떤 잘못된 환산도 통과시킨다.
    - **인쇄된 그 수로 진입점을 다시 돌린다** — 정본은 `run_single_case_e2e` 다.
      허용오차는 **표시 자리수의 반 칸**(0.05%p)이므로, `:.0%` 로 자리수를 줄인
      변이는 여기서 걸린다(53% 는 0.4%p 어긋나 약 3.6만원이 남는다).

    ⚠ 백분율은 **값이 아니라 문면**으로 견준다. `53%` 와 `52.6%` 는 값으로는
    가깝고, 자리수 변이는 값 비교로는 보이지 않는다.
    """
    printed: dict[str, str] = {}
    for name in ("scenario_unsubsidized", "scenario_subsidy_80"):
        report = _report(name)
        text = render_markdown(report)

        row = _one_line(text, _SUMMARY_ROW_HEAD)
        rate_text, current_text = _percents(row)[:2]

        body = _one_line(text, _BODY_LINE_HEAD)
        assert rate_text == _percents(body)[0], (
            f"{name}: 요약의 전환 지원율({rate_text})이 본문 5.1"
            f"({_percents(body)[0]})과 다르다 — 검토자가 먼저 보는 표와 근거가 "
            f"갈렸다. 요약 행: {row}"
        )
        substituted = {
            formula.label: formula.substituted for formula in report.formulas
        }
        assert rate_text in substituted["결론 전환 지원율"], (
            f"{name}: 요약의 전환 지원율({rate_text})이 붙임 3 산식"
            f"({substituted['결론 전환 지원율']})의 대입값과 다르다"
        )
        # 수와 **그 수가 나온 조건**의 짝 (R35 ② 함정 절). 현 지원율을 함께
        # 싣지 않으면 두 시나리오의 요약 행이 서로 바뀌어도 매끈하다.
        assert current_text == f"{report.subsidy_rate:.1%}", (
            f"{name}: 요약 행의 현 지원율({current_text})이 이 시나리오의 "
            f"지원율({report.subsidy_rate:.1%})이 아니다 — 행: {row}"
        )

        # ★ 다른 층 — 요약에 **인쇄된 그 수**를 진입점에 그대로 먹인다.
        rate = float(rate_text.rstrip("%")) / 100.0
        outcome = run_single_case_e2e(
            {},
            level_map=build_level_map(_ASSUMPTIONS),
            horizon_years=report.basis.horizon_years,
            scheme=_scheme_for(rate),
        )
        npv = float(outcome.variants[PLAN_VARIANT][CONCLUSION_METRIC])
        # 표시 자리수(`:.1%`)의 반 칸. 이보다 좁게 잡으면 반올림만으로 빨간불이
        # 나고, 넓게 잡으면 자리수를 줄인 변이가 통과한다.
        tolerance = report.total_project_cost_won * 0.0005
        assert abs(npv) <= tolerance, (
            f"{name}: 요약에 실린 지원율 {rate_text} 로 다시 돌렸는데 결론 축이 "
            f"{npv:,.0f}원이다 (허용 ±{tolerance:,.0f}원). 요약이 환산이 아닌 "
            f"수를 싣거나 자리수를 줄여 실었다 — 행: {row}"
        )
        printed[name] = rate_text

    assert len(set(printed.values())) == 1, (
        f"두 시나리오의 요약이 다른 전환 지원율을 싣는다 — {printed}. 지원이 "
        "`t=0` 초기지출 감액이라면 0 선에 닿는 지원율은 한 값이며, 갈렸다는 것은 "
        "요약이 결론 축을 총사업비로 직접 나누고 있다는 뜻이다"
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
                {}, level_map=probe, horizon_years=horizon, scheme=scheme
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
def test_the_recovering_scenario_measures_the_distance_toward_the_flip() -> None:
    """★ **회수하는 시나리오에서는 방향이 뒤집힌다.**

    보조 80% 는 결론 축이 +2,683,608원이다. 그때 5.1 이 답해야 하는 물음은
    *「얼마나 모자란가」* 가 아니라 *「어디까지 나빠지면 뒤집히는가」* 이며,
    두 물음은 **같은 거리의 반대 방향**이다. 방향을 인자마다 부호로 적어 두면
    편익·비용 인자가 늘 때 낡고, 낡은 부호는 반대 끝을 「가까운 끝」으로 싣는다.

    그래서 방향을 **결론에서 읽는다** — 이 검사가 그것을 확인한다.
    """
    report = _report("scenario_subsidy_80")
    assert report.recovers_within_horizon, (
        "보조 80% 가 회수하지 못한다 — 이 검사는 회수 갈래를 보려고 이 "
        "시나리오를 골랐다. 실물이 바뀌었으면 갈래를 다시 고를 것"
    )
    section = _section(report)
    assert GAP_MARGIN in section, "회수하는데 거리가 `결손` 으로 실렸다"
    assert GAP_SHORTFALL not in section, "회수하는데 `결손` 라벨이 남아 있다"

    base_npv = float(report.metrics[CONCLUSION_METRIC])
    for entry in report.uncertain_influences:
        if entry.flips_conclusion:
            continue
        near = min(entry.npv_low, entry.npv_high)
        row = next(
            line
            for line in section.splitlines()
            if line.startswith(f"| `{entry.variable}` ")
        )
        assert near <= base_npv, (
            f"{entry.variable}: 두 끝이 모두 기준보다 좋다 — 스윕이 기준을 "
            "넘겨 계산했다"
        )
        assert _won(abs(near)) in row, (
            f"{entry.variable}: 회수 상태인데 **좋아지는 끝**의 거리가 실렸다 — "
            f"행: {row}. 이 표가 재는 것은 전환 방향의 끝이다"
        )
