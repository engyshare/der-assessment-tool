"""검증 9단계 비교표 — **세 갈래**와 목차의 정책 변형 한 문장 (R68/WP-9).

동반 대상은 `core/report/verification_variants.py` 다(NFR-105 · 파일명 규약).

## 무엇을 재는가 — 독립 검증이 찾은 결함 둘

`.orch/R68/result_V.md` 가 검토서 §3.7 에서 둘이 안 닫혔음을 실물로 짚었다.

- **결함 #3** — *「「무지원」·「입력 지원안」·「전액 지원」의 차이를 표로 구분한다」*
  인데 ⓑ 표가 **두 행**뿐이고 「전액 지원」은 8단계 ⓓ **산식으로만** 있었다.
- **결함 #2** — *「이 시나리오가 어떤 정책 변형을 의미하는지 목차에서 한 문장으로」*
  인데 목차 머리표가 「평가 대상」만 싣고 지원 조건을 한 자도 안 적었다.

## ⛔ 이 검사가 **막는 것** — 「두 곳이 같은 수를 따로 짓는 것」

「전액 지원」 행의 순현재가치는 8단계 ⓓ 의 「전액 지원 시 잔여 결손」과 **같은
수여야** 한다. 다른 수가 서면 그것은 9단계가 그 값을 **자기가 다시 세운** 것이고,
그때 산식이 바뀌는 날 한쪽만 고쳐진다. 그래서 아래 검사는 리터럴을 적지 않고
**`CaseReport` 의 그 프로퍼티와 견준다.**

⛔ 결론축의 크기는 재지 않는다 — 그것은 `tests/golden` 과 사다리의 몫이다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.report.case_report import (
    CONCLUSION_METRIC,
    MAX_SUBSIDY_RATE,
    CaseReport,
    build_case_report,
)
from core.report.verification_variants import (
    policy_variant_sentence,
    variant_comparison_lines,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"
_UNSUBSIDIZED = _GOLDEN / "scenario_unsubsidized.yaml"
_SUBSIDY_20 = _GOLDEN / "scenario_subsidy_20.yaml"

#: 검토서 §3.7 이 요구한 세 갈래의 마지막 — 문면을 여기서 짓지 않고 그 낱말이
#: 산출물에 서 있는지만 본다.
_FULL_SUPPORT = "전액 지원"


@pytest.fixture(scope="module")
def report() -> CaseReport:
    return build_case_report(_UNSUBSIDIZED, assumptions_path=_ASSUMPTIONS)


@pytest.fixture(scope="module")
def subsidized() -> CaseReport:
    return build_case_report(_SUBSIDY_20, assumptions_path=_ASSUMPTIONS)


def _rows(lines: list[str]) -> list[list[str]]:
    """표 행만 골라 칸으로 가른다 — 구분선과 글머리 줄은 뺀다."""
    return [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in lines
        if line.startswith("|") and "---" not in line
    ]


def _row_starting(lines: list[str], head: str) -> list[str]:
    for cells in _rows(lines):
        if cells[0].startswith(head):
            return cells
    raise AssertionError(f"그 행이 없다: {head} — 실제 행: {[c[0] for c in _rows(lines)]}")


def test_the_comparison_table_carries_a_full_support_row(report: CaseReport) -> None:
    """★ 검토서 §3.7 의 **세 번째 갈래**가 표의 행으로 선다 (결함 #3).

    머리행을 뺀 값 행이 **셋**이어야 하고, 그 마지막이 「전액 지원」이다.
    """
    lines = variant_comparison_lines(report)
    value_rows = _rows(lines)[1:]
    assert len(value_rows) == 3, [cells[0] for cells in value_rows]
    assert value_rows[-1][0].startswith(_FULL_SUPPORT), value_rows[-1][0]


def test_the_full_support_row_reads_the_stage8_residual_instead_of_recomputing(
    report: CaseReport,
) -> None:
    """★★ **8단계와 같은 수여야 한다** — 이 행이 값을 다시 세우면 빨간불이다.

    ⛔ 리터럴을 적지 않는다. 견주는 상대는 `CaseReport` 가 8단계 ⓓ 에 넘기는
    바로 그 프로퍼티이며(`residual_gap_at_full_support_won`), 두 수가 갈리는
    날은 9단계가 자기 산식을 갖게 된 날이다.
    """
    lines = variant_comparison_lines(report)
    head = _rows(lines)[0]
    npv_column = next(
        index for index, name in enumerate(head) if name.startswith("순현재가치")
    )
    printed = _row_starting(lines, _FULL_SUPPORT)[npv_column]
    expected = f"{round(report.residual_gap_at_full_support_won):,}원"
    assert printed == expected, (printed, expected)
    # ⚠ 그리고 그 수는 무지원 행과 **달라야** 한다 — 같으면 지원분이 결론축에
    #   닿지 않은 것이고, 그때 세 갈래 표는 아무 차이도 구분하지 못한다.
    baseline = _rows(lines)[1][npv_column]
    assert printed != baseline, (printed, baseline)


def test_the_full_support_row_says_which_cells_it_did_not_run(
    report: CaseReport,
) -> None:
    """⚠ 「전액 지원」은 **돌린 변형이 아니라 환산**임을 표가 스스로 적는다.

    초기투자·할인 회수기간을 0원·즉시로 채우면 돌리지 않은 수가 돌린 수 옆에
    실행 결과처럼 선다 — 그래서 그 둘은 「미산출(환산)」이고, 표 아래 줄이
    사유를 든다. ⛔ 이 사유가 사라지면 독자가 그 칸을 실행 결과로 읽는다.
    """
    lines = variant_comparison_lines(report)
    cells = _row_starting(lines, _FULL_SUPPORT)
    assert cells.count("미산출(환산)") == 2, cells
    notes = "\n".join(line for line in lines if line.startswith("- "))
    assert "환산" in notes and _FULL_SUPPORT in notes, notes


def test_the_sameness_note_still_speaks_only_of_the_variants_that_ran(
    report: CaseReport,
) -> None:
    """★ 세 번째 행이 서도 **「돌린 둘이 같다」는 사유 줄이 남는다**.

    환산 행을 그 비교에 넣으면 지원율 0% 실행에서 늘 「같지 않다」가 되어 그
    줄이 통째로 사라지고, 그때 같은 수 두 줄이 사유 없이 인쇄된다 — 독자가
    오류로 읽는 바로 그 자리다.
    """
    lines = variant_comparison_lines(report)
    sameness = [line for line in lines if "수가 전부 같다" in line]
    assert len(sameness) == 1, lines
    assert "돌린" in sameness[0], sameness[0]


def test_the_policy_sentence_reads_the_subsidy_rate_from_the_run(
    report: CaseReport, subsidized: CaseReport
) -> None:
    """★★ 목차 한 문장이 **시나리오마다 갈린다** (결함 #2).

    ⛔ `scenario_unsubsidized` 를 글자로 박으면 이 검사가 빨간불이다 — 세
    시나리오가 같은 목차를 쓰므로, 박는 순간 지원 20% 실행의 목차가 자기를
    무지원이라고 적는다.
    """
    plain = policy_variant_sentence(report)
    with_subsidy = policy_variant_sentence(subsidized)
    assert plain != with_subsidy

    assert report.scenario_name_slug in plain
    assert subsidized.scenario_name_slug in with_subsidy
    assert f"{subsidized.subsidy_rate:.0%}" in with_subsidy
    # 지원이 없는 갈래는 그 사실을 말한다 — 비율만 적으면 「0%」가 무엇을
    # 뜻하는지 독자가 다시 물어야 한다.
    assert "지원이 없는" in plain, plain
    # 상한도 실행이 아니라 한 상수에서 온다.
    assert f"{MAX_SUBSIDY_RATE:.0%}" in plain


def test_the_policy_sentence_does_not_use_the_forbidden_word(
    report: CaseReport,
) -> None:
    """⚠ 이 문장은 **사람이 읽는 자리**다 — 「전제」를 쓰지 않는다 (판정 R63b §1).

    목차 머리표의 「전제 대장」은 대장을 부르는 이름이라 그대로 두고, 새로
    세우는 이 문장에는 그 낱말이 0건이어야 한다. 어기면 화면(`/ui/verify`)의
    같은 규약과 e2e 가 함께 빨간불이 된다.
    """
    assert "전제" not in policy_variant_sentence(report)


def test_the_conclusion_metric_column_is_the_one_the_report_names(
    report: CaseReport,
) -> None:
    """⚠ 결론축 열을 **이름으로** 찾는다 — 열 차례가 바뀌어도 검사가 안 흔들린다."""
    head = _rows(variant_comparison_lines(report))[0]
    assert any(name.startswith("순현재가치") for name in head), head
    assert CONCLUSION_METRIC in report.metrics
