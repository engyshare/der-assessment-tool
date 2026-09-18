"""대장 행을 **표로 인쇄하는 한 자리** (R69/WP-1).

동반 대상은 `core/report/verification_ledger.py` 다(NFR-105 · 파일명 규약).

## ⚠ 무엇을 재고 무엇을 재지 않는가

승격 9→10 이 같은 `report.assumptions` 표를 **세 자리**에 세웠다(1단계 부분 표 ·
4단계 부분 표 · 4단계 전건 표). 세 자리가 각자 f-문자열로 일곱 열을 적으면 열이
갈리는 날 한 표만 낡고, **갈려도 표는 멀쩡해 보인다.** 이 검사가 붙드는 것은 넷:

1. **부분 표는 «고르는 것»이지 «짓는 것»이 아니다** — 접두로 고른 행이 전건 표의
   행과 **글자로 같아야** 한다. 다르면 같은 대장 항목이 두 단계에서 다른 수로
   인쇄되고 있다는 뜻이다.
2. **대장이 준 차례가 유지된다** — 다시 정렬하면 두 표를 맞대 보는 눈이 같은 행을
   두 번 찾아야 한다.
3. ★★ **산문 칸이 접혀 한 줄로 선다** — `docs/assumptions.yaml::
   load.heatpump.annual` 의 `source` 에 줄바꿈이 있어 그 행이 마크다운 표에서
   **여러 줄로 쪼개져 튕겨 나갔던** 자리다(R68/WP-7 실측). 이 검사가 그 재발을
   막는다.
4. **빈 접두는 표가 아니라 문장이다** — 머리 두 줄만 선 빈 표는 「대장에 그 접두가
   없다」와 「거르는 규칙이 틀렸다」를 구별해 주지 않는다.

⛔ **어느 단계가 어느 접두를 고르는가는 재지 않는다** — 그 판정은
`verification_demand.py` · `verification_economics.py` 가 갖고
`tests/report/test_verification_economics.py` 가 잰다. 여기서는 **인쇄 규칙**만 본다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.report.case_report import CaseReport, build_case_report
from core.report.verification_ledger import (
    LEDGER_TABLE_HEAD,
    NO_LEDGER_ROW,
    ledger_row,
    ledger_table,
    rows_with_prefix,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"

#: 일곱 열 — 검토서가 아니라 **종전 1단계 ⓑ 표의 문면 그대로**다.
_SEVEN_COLUMNS = ("키", "값", "단위", "기준연도", "출처", "신뢰도", "최종확인일")


@pytest.fixture(scope="module")
def report() -> CaseReport:
    return build_case_report(_GOLDEN, assumptions_path=_ASSUMPTIONS)


def test_the_head_names_all_seven_columns() -> None:
    """머리 두 줄이 일곱 열을 세운다 — **한 자리에서만 정해진다.**"""
    header, divider = LEDGER_TABLE_HEAD
    cells = [cell.strip() for cell in header.strip().strip("|").split("|")]
    assert tuple(cells) == _SEVEN_COLUMNS, f"열 이름이 갈렸다: {cells}"
    assert divider.count("---") == len(_SEVEN_COLUMNS), (
        "구분선의 칸 수가 열 수와 다르다 — 마크다운이 표로 읽지 않는다"
    )


def test_a_partial_table_selects_rows_it_does_not_build_them(
    report: CaseReport,
) -> None:
    """★★ **부분 표의 행이 전건 표의 그 행과 «글자로» 같다.**

    다르면 같은 대장 항목이 두 단계에서 다른 수로 인쇄되고 있다는 뜻이며, 그
    어긋남은 표를 나란히 놓고 보기 전에는 드러나지 않는다.
    """
    whole = ledger_table(report.assumptions)
    picked = rows_with_prefix(report, ("load.",))
    assert picked, "픽스처 전제가 깨졌다 — 대장에 `load.*` 행이 없다"
    for row in picked:
        assert ledger_row(row) in whole, (
            f"`{row.key}` 의 부분 표 행이 전건 표의 그 행과 다르다 — "
            "부분 표가 행을 «지었다»"
        )


def test_a_partial_table_keeps_the_ledgers_own_order(report: CaseReport) -> None:
    """대장이 준 차례 그대로다 — **다시 정렬하지 않는다.**"""
    keys = [row.key for row in rows_with_prefix(report, ("load.", "design."))]
    expected = [
        row.key
        for row in report.assumptions
        if row.key.startswith(("load.", "design."))
    ]
    assert keys == expected, f"부분 표가 차례를 바꿨다: {keys}"


def test_every_printed_row_stays_on_one_line(report: CaseReport) -> None:
    """★★★ **산문 칸이 접혀 한 줄로 선다** (R68/WP-7 이 실물로 밟은 함정).

    대장의 `source` 에 줄바꿈이 든 항목이 **실제로 있어야** 이 검사가 뜻을
    갖는다 — 없으면 접기가 꺼져 있어도 통과한다. 그래서 그 전제를 먼저 잰다.
    """
    multiline = [
        row for row in report.assumptions if "\n" in (row.source or "")
    ]
    assert multiline, (
        "픽스처 전제가 깨졌다 — 대장에 줄바꿈이 든 `source` 가 하나도 없어 "
        "이 검사가 접기를 재지 못한다"
    )
    for row in report.assumptions:
        printed = ledger_row(row)
        assert "\n" not in printed, (
            f"`{row.key}` 행이 여러 줄로 쪼개졌다 — 마크다운 표에서 튕겨 나간다"
        )
        assert printed.count("|") == len(_SEVEN_COLUMNS) + 1, (
            f"`{row.key}` 행의 칸 수가 일곱이 아니다 — 값에 든 `|` 가 표를 깼다"
        )


def test_an_empty_prefix_prints_a_sentence_not_an_empty_table(
    report: CaseReport,
) -> None:
    """**빈 표를 세우지 않는다** — 빈칸은 「없다」와 「규칙이 틀렸다」를 안 가른다."""
    assert rows_with_prefix(report, ("이런.접두는.없다.",)) == ()
    assert ledger_table(()) == [NO_LEDGER_ROW]
    assert LEDGER_TABLE_HEAD[0] not in ledger_table(()), (
        "행이 없는데 표 머리를 세웠다 — 읽는 눈이 「빈 표」를 결함으로 읽는다"
    )
