"""**5.3 적자 분해가 재는 값인가** — R49 · 판정 `docs/decisions-2026-08-31-R49.md` §3 ⓐ.

5.1 은 *「단독 전환 인자 — 없음」* 을 정직하게 적는다. 5.3 은 그 옆에서
*「그럼 결손은 어디서 오는가」* 에 답한다. 이 파일이 보는 것은 그 답이
**표시가 아니라 실물인가**다.

    ★★ 합계 = 결손              ← 합이 안 맞는 분해는 답하는 척만 하는 표다
    ★★ 엔진의 수를 나른다        ← 진입점을 직접 돌려 **다른 산식으로** 견준다
    ★  크기 순인가              ← 순위가 다음 검토의 입력이다 (판정 §3 ⓑ)
    ★★ 1위 문장이 표에서 지어졌나 ← 박아 둔 문자열은 여기서 걸린다
    ★  합이 어긋나면 터뜨리는가   ← 오라클이 살아 있는가

⚠ **오라클을 구현의 사본으로 만들지 않는다.** 둘째 검사는 `build_shortfall()`
을 부르지 않고 **진입점이 낸 현금흐름 행을 손으로 할인해** 기대값을 만든 뒤,
**인쇄된 표**와 견준다. 같은 조립기로 검산하면 동어반복이다 —
`test_conclusion_gap.py` 가 적어 둔 규약이며 R33 의 `_find_flip_threshold`
결함이 「표시만 하는 구현」으로 통과했던 형태를 막는다.

⚠ `req()` 마커는 달지 않았다 — 절의 구성은 양식이 정하는 서식 규정이지 spec
조항이 아니다(`tests/report/test_form_conformance.py` 와 같은 판단).
"""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.contracts.schemas import CashFlowRow
from core.report.case_report import (
    CONCLUSION_METRIC,
    PLAN_VARIANT,
    CaseReport,
    _scheme_for,
    build_case_report,
)
from core.report.narrative import render_markdown
from core.report.shortfall import (
    ITEM_INITIAL,
    ITEM_LIFECYCLE,
    ITEM_OPERATING,
    SECTION_NUMBER,
    build_shortfall,
    shortfall_section,
)
from tests.report.conftest import report_shapes

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"

#: 두 골든 시나리오 — **둘 다 본다.** 초기투자 항이 지원율만큼 달라지므로
#: 합계가 맞는지는 시나리오마다 따로 성립해야 하는 성질이다.
_SCENARIOS = ("scenario_unsubsidized", "scenario_subsidy_80")

#: 허용오차 — **총사업비에 대한 비율**이다 (`test_conclusion_gap.py` 규약).
#: 원 단위 절대값으로 잡으면 사업 규모가 바뀔 때 의미 없이 빨간불이 된다.
#: 0.001% 는 총사업비 980만원에서 98원이며, 손으로 다시 할인한 값과 엔진의
#: 원 단위 반올림(`units.won_sum`) 사이의 차를 덮는 폭이다.
_TOLERANCE_RATIO = 1e-5

_WON = re.compile(r"-?[\d,]+원")


def _report(name: str) -> CaseReport:
    return build_case_report(_GOLDEN / f"{name}.yaml", assumptions_path=_ASSUMPTIONS)


def _tolerance(report: CaseReport) -> float:
    return report.total_project_cost_won * _TOLERANCE_RATIO


def _section_text(report: CaseReport) -> str:
    text = render_markdown(report)
    head = f"### {SECTION_NUMBER} "
    return text[text.index(head) : text.index("## 6. 종합")]


def _table_rows(section: str) -> list[tuple[str, float]]:
    """5.3 표를 **(항목 문면, 금액)** 으로. 굵기·들여쓰기는 문면에 남긴다."""
    rows = []
    for line in section.splitlines():
        if not line.startswith("| ") or line.startswith("|---"):
            continue
        cells = line.split("|")
        found = _WON.search(cells[2]) if len(cells) > 2 else None
        if found is None:  # 표 머리(`| 항목 | 현재가치 (원) |`)
            continue
        rows.append((cells[1].strip(), float(found.group(0)[:-1].replace(",", ""))))
    return rows


def _bold_rows(section: str) -> list[tuple[str, float]]:
    """**더해지는 항**만 — 합계 행은 뺀다."""
    return [
        (label, amount)
        for label, amount in _table_rows(section)
        if label.startswith("**") and "합계" not in label
    ]


# ─────────────────────────────────────────────────────────────────────────
# ★★ 1. 합계 = 결손
# ─────────────────────────────────────────────────────────────────────────


def test_the_split_adds_up_to_the_conclusion_gap() -> None:
    """★★ **분해의 합이 결론 축과 같다** — 이 절의 유일한 오라클.

    합이 맞지 않는 분해는 *「어디서 오는가」* 에 답하는 **척만 하는 표**이며,
    그것을 싣는 것이 「없음」 한 줄보다 나쁘다 — 검토자가 확인할 수 없는 수가
    늘기 때문이다.

    ⚠ **인쇄된 표에서 읽어 더한다.** 자료형의 `total_won` 만 보면 *「표에는
    다른 수를 싣는 구현」* 이 통과한다 — 이 저장소가 「표시만 하는 구현」으로
    반복해 만난 형태다.
    """
    for name in _SCENARIOS:
        report = _report(name)
        section = _section_text(report)
        rows = _table_rows(section)
        printed_total = next(
            amount for label, amount in rows if "합계" in label
        )
        added = sum(amount for _, amount in _bold_rows(section))
        npv = float(report.metrics[CONCLUSION_METRIC])

        assert abs(added - npv) <= _tolerance(report), (
            f"{name}: 굵은 항의 합 {added:,.0f}원이 결론 축 {npv:,.0f}원과 "
            f"다르다 — 분해가 결손을 설명하지 못한다"
        )
        assert abs(printed_total - npv) <= _tolerance(report), (
            f"{name}: 표의 합계 행 {printed_total:,.0f}원이 결론 축 "
            f"{npv:,.0f}원과 다르다"
        )


# ─────────────────────────────────────────────────────────────────────────
# ★★ 2. 엔진의 수를 나른다 — 진입점을 직접 돌려 **다른 산식으로** 견준다
# ─────────────────────────────────────────────────────────────────────────


def _hand_discounted(rows: tuple[CashFlowRow, ...], rate: float) -> float:
    """행 묶음의 현가를 **손으로** — 엔진의 `metrics._pv` 를 부르지 않는다.

    엔진은 항마다 원 단위로 반올림해 더하고(`units.won_sum`) 여기는 그러지
    않는다. 그 차가 허용오차 안이라는 것까지가 이 검사가 재는 성질이며,
    같은 함수를 부르면 **반올림 규약이 바뀌어도 둘이 함께 움직여** 아무것도
    잡지 못한다.
    """
    return sum(
        float(amount) / (1.0 + rate) ** year
        for row in rows
        for year, amount in row.amounts.items()
    )


def test_the_printed_split_matches_the_engine_run() -> None:
    """★★ 인쇄된 세 항이 **진입점을 다시 돌린 값**과 같다.

    리포트를 다시 조립하지 않는다 — `run_single_case_e2e` 를 **직접** 돌려
    그 산출(`CaseOutcome.cashflows`)을 손으로 할인한다. 그래야 *리포트가
    자기가 만든 수를 자기가 확인하는* 동어반복을 피한다.

    ⚠ **`annual_load_kwh` 를 함께 넘긴다** (R48/WP-B). 빠뜨리면 부하 있는
    리포트의 수를 **부하 없는 사업**에 대고 재게 되고, 두 수는 언제나 갈린다.
    """
    level_map = build_level_map(_ASSUMPTIONS)
    report = _report("scenario_unsubsidized")
    outcome = run_single_case_e2e(
        {},
        level_map=level_map,
        horizon_years=report.basis.horizon_years,
        scheme=_scheme_for(report.subsidy_rate),
        daily_shapes=report_shapes(),
        annual_load_kwh=level_map["household_load_annual_kwh"]["base"],
    )
    rate = outcome.basis.discount_rate
    split = outcome.cashflows
    benefit = _hand_discounted(split.benefit, rate)
    operating_cost = _hand_discounted(split.operating_cost, rate)
    lifecycle = _hand_discounted(split.lifecycle, rate)
    outlay = float(outcome.variants[PLAN_VARIANT]["initial_outlay_won"])

    expected = {
        ITEM_INITIAL: -outlay,
        ITEM_OPERATING: benefit - operating_cost,
        ITEM_LIFECYCLE: -lifecycle,
    }
    printed = dict(_bold_rows(_section_text(report)))
    assert len(printed) == len(expected), (
        f"굵은 항이 셋이 아니다 — {list(printed)}"
    )

    built = {item.key: item.label for item in build_shortfall(report).items}
    tolerance = _tolerance(report)
    for key, want in expected.items():
        label = f"**{built[key]}**"
        assert label in printed, f"{key}: 인쇄된 표에 그 항이 없다 — {list(printed)}"
        assert abs(printed[label] - want) <= tolerance, (
            f"{key}: 인쇄값 {printed[label]:,.0f}원이 진입점 재실행값 "
            f"{want:,.0f}원과 다르다 — 리포트가 엔진 밖에서 수를 만들었다"
        )


# ─────────────────────────────────────────────────────────────────────────
# ★ 3. 크기 순인가
# ─────────────────────────────────────────────────────────────────────────


def test_the_table_is_ordered_by_size() -> None:
    """★ 항과 속항이 **절대값 내림차순**이다.

    순위 자체가 이 절의 산출물이다 — 판정 §3 ⓑ 가 *「ⓐ 의 분해에서 큰 항목부터
    고른다」* 로 다음에 흔들 축을 고르므로, 순서가 흐트러지면 다음 검토가
    **작은 항부터** 흔들게 된다.

    ⚠ 표에서도 함께 본다. 자료형만 정렬하고 인쇄를 다른 순서로 하는 구현이
    있을 수 있고, 검토자가 읽는 것은 표다.
    """
    for name in _SCENARIOS:
        report = _report(name)
        shortfall = build_shortfall(report)
        sizes = [abs(item.amount_won) for item in shortfall.items]
        assert sizes == sorted(sizes, reverse=True), (
            f"{name}: 항이 크기 순이 아니다 — {sizes}"
        )
        for item in shortfall.items:
            part_sizes = [abs(part.amount_won) for part in item.parts]
            assert part_sizes == sorted(part_sizes, reverse=True), (
                f"{name}: {item.key} 의 속항이 크기 순이 아니다 — {part_sizes}"
            )

        printed = [abs(amount) for _, amount in _bold_rows(_section_text(report))]
        assert printed == sorted(printed, reverse=True), (
            f"{name}: 인쇄된 굵은 항이 크기 순이 아니다 — {printed}"
        )


# ─────────────────────────────────────────────────────────────────────────
# ★★ 4. 1위 항목 문장이 **표에서** 지어졌는가
# ─────────────────────────────────────────────────────────────────────────


_LEAD_HEAD = "- 가장 큰 항 — "


def _lead_sentence(lines: list[str]) -> str:
    hits = [line for line in lines if line.startswith(_LEAD_HEAD)]
    assert len(hits) == 1, f"「{_LEAD_HEAD}」 줄이 하나가 아니다 — {hits}"
    return hits[0]


def test_the_leading_item_sentence_follows_the_table() -> None:
    """★★ **금액을 바꿔치기하면 문장의 이름도 따라 바뀐다.**

    *「최대 원인은 계통 구매다」* 같은 문장을 문자열로 박아 두면 구성이 바뀌어도
    **틀린 채로 계속 인쇄된다.** 그래서 같은 항목 목록의 **금액만 맞바꾼 사본**
    으로 절을 다시 지어, 1위 문장이 다른 항을 가리키는지 본다 — 박아 둔
    문자열은 여기서 걸린다.

    ⚠ 실물 대장에서도 이 성질은 관측된다: 무보조는 1위가 **초기투자**,
    보조 80% 는 **운영 단계**다. 그래서 이 문장은 시나리오마다 실제로 다르다.
    """
    shortfall = build_shortfall(_report("scenario_unsubsidized"))
    original = _lead_sentence(shortfall_section(shortfall))
    worst = min(shortfall.items, key=lambda item: item.amount_won)
    assert worst.label in original, (
        f"1위 문장이 가장 큰 항을 가리키지 않는다 — {original}"
    )

    # 금액만 거꾸로 실은 사본. 이름·순서는 그대로 두어 **문장이 무엇을 읽는지**
    # 만 가른다 — 정렬을 함께 뒤집으면 자리로 골라도 통과한다.
    amounts = [item.amount_won for item in shortfall.items][::-1]
    swapped = replace(
        shortfall,
        items=tuple(
            replace(item, amount_won=amount)
            for item, amount in zip(shortfall.items, amounts, strict=True)
        ),
    )
    moved = _lead_sentence(shortfall_section(swapped))
    new_worst = min(swapped.items, key=lambda item: item.amount_won)

    assert new_worst.label != worst.label, (
        "금액을 뒤집었는데 1위 항이 그대로다 — 이 검사가 재는 것이 없다"
    )
    assert new_worst.label in moved and worst.label not in moved, (
        f"문장이 표를 따라오지 않는다 — 기대 「{new_worst.label}」 · 실물 {moved}"
    )


# ─────────────────────────────────────────────────────────────────────────
# ★ 5. 합이 어긋나면 **터뜨린다**
# ─────────────────────────────────────────────────────────────────────────


def test_a_split_that_does_not_add_up_is_refused() -> None:
    """★ 오라클이 **살아 있는가** — 행 하나를 빼면 거부한다.

    합계 확인이 주석으로만 남고 실제로는 통과시키는 구현을 막는다. 편익 행을
    빼면 분해는 그럴듯한 표를 그대로 낼 수 있지만 합이 결손과 어긋나고,
    그때 인쇄되는 것이 *「어디서 오는가」* 에 답하는 척만 하는 표다.
    """
    report = _report("scenario_unsubsidized")
    crippled = replace(
        report, cashflows=replace(report.cashflows, benefit=())
    )
    try:
        build_shortfall(crippled)
    except ValueError as error:
        assert "결론 축" in str(error), f"사유가 무엇이 어긋났는지 말하지 않는다: {error}"
    else:  # pragma: no cover - 통과하면 오라클이 죽은 것이다
        raise AssertionError(
            "편익 행을 통째로 빼도 분해가 만들어졌다 — 합계 확인이 죽어 있다"
        )
