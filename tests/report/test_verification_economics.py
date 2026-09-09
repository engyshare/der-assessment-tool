"""검증 **4단계 「경제성 입력」** — 옛 1단계의 뒤 절반 (R69/WP-1 · 검토서 §3.1·§6-2).

동반 대상은 `core/report/verification_economics.py` 다(NFR-105 · 파일명 규약).

## ⚠ 무엇을 재고 무엇을 재지 않는가

승격 9→10 의 진짜 위험은 **번호가 아니라 「행이 조용히 사라지는 것」**이다. 옛
1단계 하나가 둘로 갈렸으므로, 어느 쪽도 안 싣는 대장 항목이 생기면 그 항목은
산출물 어디에도 없고 **없다는 사실조차 보이지 않는다.** 이 검사가 붙드는 것은
그것이다:

1. ★★★ **대장 전건이 4단계 ⓑ 에 한 덩어리로 남는다** — 행 수가 `report.assumptions`
   와 같아야 한다. 주제별로 쪼개 흩는 순간 이 검사가 빨간불이다.
2. ★★ **두 부분 표의 접두가 겹치지 않는다** — 겹치면 같은 항목이 1단계와 4단계
   둘 다에서 「이 단계가 읽은 값」으로 서고, 그때 어느 단계가 그 값을 정했는지
   산출물이 말해 주지 않는다.
3. **할인율·지원율은 대장 표 «밖»에 선다** — 대장 항목이 아니기 때문이며, 값은
   실행에서 온다(리터럴이 아니다).
4. ⛔ **설비 단가(`capex.*`)가 이 단계의 부분 표에 없다** — 2단계에 남기기로 한
   R68 판정이 정본이고, 검토서 §3.1 의 반대 문면이 되살아나면 여기가 빨간불이다.

⛔ **문서 전체가 이 단계를 싣는지는 재지 않는다** — `tests/report/test_verification.py`
가 잰다. 일곱 열의 인쇄 규칙도 재지 않는다 —
`tests/report/test_verification_ledger.py` 가 잰다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.report.case_report import CaseReport, build_case_report
from core.report.verification_demand import (
    DEMAND_LEDGER_PREFIXES,
    demand_ledger_lines,
)
from core.report.verification_economics import (
    ECONOMIC_LEDGER_PREFIXES,
    economic_axis_lines,
    economic_ledger_lines,
    influence_lines,
    ledger_all_lines,
)
from core.report.verification_ledger import ledger_row, rows_with_prefix

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"


@pytest.fixture(scope="module")
def report() -> CaseReport:
    return build_case_report(_GOLDEN, assumptions_path=_ASSUMPTIONS)


def _table_rows(lines: list[str]) -> list[str]:
    """표의 **데이터 행**만 — 머리·구분선·글머리는 뺀다."""
    return [
        line
        for line in lines
        if line.startswith("| `") or (line.startswith("| ") and "---" not in line)
    ]


def test_the_whole_ledger_stays_in_one_block(report: CaseReport) -> None:
    """★★★ **전건이 한 덩어리로 남는다** — 쪼개 흩으면 행이 조용히 사라진다."""
    lines = ledger_all_lines(report)
    printed = [ledger_row(row) for row in report.assumptions]
    assert printed, "픽스처 전제가 깨졌다 — 값이 실린 대장 항목이 0건이다"
    for row_text in printed:
        assert row_text in lines, "전건 표에서 대장 행이 빠졌다"
    assert sum(1 for line in lines if line.startswith("| `")) == len(printed), (
        "전건 표의 행 수가 대장 항목 수와 다르다 — 「1 의 나머지」가 깨졌다"
    )
    assert f"항목 {len(report.assumptions)}건" in " ".join(lines), (
        "그 N 이 무엇인지 말하지 않는다 — 검토자는 대장 파일의 항목 수로 읽는다"
    )


def test_the_two_partial_tables_do_not_overlap(report: CaseReport) -> None:
    """★★ **1단계와 4단계가 같은 대장 항목을 「자기 것」이라 하지 않는다.**

    ⚠ 접두 문자열을 견주는 것으로는 부족하다(`load.` 와 `l` 은 글자로 다르지만
    겹친다) — **실제로 고른 행**을 견준다.
    """
    demand = {row.key for row in rows_with_prefix(report, DEMAND_LEDGER_PREFIXES)}
    economic = {row.key for row in rows_with_prefix(report, ECONOMIC_LEDGER_PREFIXES)}
    assert demand, "픽스처 전제가 깨졌다 — 1단계 부분 표가 비었다"
    assert economic, "픽스처 전제가 깨졌다 — 4단계 부분 표가 비었다"
    assert not demand & economic, (
        f"두 단계가 같은 대장 항목을 함께 싣는다: {sorted(demand & economic)}"
    )


def test_the_economic_partial_table_leaves_equipment_prices_to_stage_two(
    report: CaseReport,
) -> None:
    """⛔ **설비 단가는 2단계에 남는다** — 초기투자가 그것으로 계산된다(R68 판정).

    검토서 §3.1 은 *「PV·ESS 단가도 경제성 입력으로」* 라 적었으나 그 판정이
    뒤집었다. 되살아나면 여기가 빨간불이어야 한다.
    """
    capex = [row for row in report.assumptions if row.key.startswith("capex.")]
    assert capex, "픽스처 전제가 깨졌다 — 대장에 `capex.*` 행이 없다"
    picked = {row.key for row in rows_with_prefix(report, ECONOMIC_LEDGER_PREFIXES)}
    assert not picked & {row.key for row in capex}, (
        f"설비 단가가 4단계 부분 표로 옮겨졌다: {sorted(picked)}"
    )


def test_the_partial_table_carries_the_price_and_rec_rows(
    report: CaseReport,
) -> None:
    """요금·REC 단가가 앞머리에 선다 — 검토서 §3.1 이 이 단계로 옮기라 한 것."""
    lines = economic_ledger_lines(report)
    picked = rows_with_prefix(report, ECONOMIC_LEDGER_PREFIXES)
    for row in picked:
        assert ledger_row(row) in lines, f"`{row.key}` 가 부분 표에 없다"
    assert any("rec" in row.key for row in picked), (
        "REC 단가가 이 단계에 서지 않았다 — 검토서 §3.1 의 요구다"
    )
    assert any(row.key.startswith("tariff.") for row in picked), (
        "요금이 이 단계에 서지 않았다"
    )


def test_the_two_axes_the_ledger_does_not_hold_stand_outside_its_table(
    report: CaseReport,
) -> None:
    """★ **할인율·지원율은 대장 항목이 아니다** — 값은 실행에서 온다.

    ⚠ 값을 여기 박지 않는다. 박으면 시나리오가 바뀌는 날 이 검사가 거짓이 된다.
    """
    text = "\n".join(economic_axis_lines(report))
    assert f"{report.basis.discount_rate:.1%}" in text, "할인율 값이 실행과 다르다"
    assert f"{report.subsidy_rate:.0%}" in text, "지원율 값이 실행과 다르다"
    assert text.count("**대장에 없다**") == 2, (
        "두 축이 「대장에 없다」로 서지 않았다 — 대장 값과 평가자가 고른 값이 "
        "한 표에서 같아 보인다"
    )
    keys = {row.key for row in report.assumptions}
    assert not any("discount" in key or "subsidy" in key for key in keys), (
        "전제가 깨졌다 — 대장에 할인율·지원율 항목이 생겼다면 「대장에 없다」가 "
        "거짓이 된다"
    )


def test_the_handoff_carries_every_wired_influence(report: CaseReport) -> None:
    """ⓒ 가 «실제로 읽어 결론에 반영한» 대장 키를 전건 싣는다."""
    text = "\n".join(influence_lines(report))
    assert report.uncertain_influences, "픽스처 전제가 깨졌다 — 결선된 인자가 0건이다"
    for entry in report.uncertain_influences:
        assert f"`{entry.ledger_key}`" in text, (
            f"ⓒ 가 결선된 인자 `{entry.ledger_key}` 를 잃었다"
        )


def test_the_demand_partial_table_says_it_is_not_the_whole_ledger(
    report: CaseReport,
) -> None:
    """1단계 부분 표가 **전건이 아님을 글자로 적는다** — 그리고 어디에 있는지 짚는다.

    적지 않으면 검토자가 여섯 행을 대장 전건으로 읽고 항목 수를 잘못 센다.
    """
    text = "\n".join(demand_ledger_lines(report))
    assert "전건이 아니다" in text, "부분 표가 전건이 아님을 적지 않았다"
    assert f"전건 {len(report.assumptions)}건" in text, (
        "전건이 몇 건인지 적지 않았다 — 검토자가 어디를 볼지 알 수 없다"
    )
    assert "4단계" in text, "전건 표가 어느 단계에 있는지 짚지 않았다"
