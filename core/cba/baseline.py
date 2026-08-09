"""기준선 증분 분석 — 작업 10.5 / FR-705-AC1.

모든 편익은 «설비 미설치 기준선» 대비 **증분** 이다 (도메인 원칙 1-1·1-2).
기준선 자체 비용도 리포트에 **명시적으로 표시** 해야 한다 (FR-705-AC1).

기준선이 «아무것도 하지 않음» 이 아니라 «현실적 대안» 이라는 점이 핵심이다
(원칙 1-3). 히트펌프의 기준선은 «난방 안 함» 이 아니라 «기존 보일러 유지».
"""
from __future__ import annotations

from dataclasses import dataclass

from core.cba.proforma import aggregate
from core.contracts.schemas import CashFlowRow
from core.contracts.units import ZERO, Money


@dataclass(frozen=True)
class BaselineComparison:
    """기준선 vs 신규 비교 — 증분과 기준선 자체를 함께 든다 (FR-705-AC1).

    ``baseline_displayed`` 가 0 이면 «기준선이 표시되지 않았다» — 조항 위반.
    편익이 증분이려면 baseline 이 명시되어야 그 차이가 증분임을 보일 수 있다.
    """

    baseline_rows: tuple[CashFlowRow, ...]
    new_rows: tuple[CashFlowRow, ...]
    incremental_rows: tuple[CashFlowRow, ...]

    def baseline_total(self) -> Money:
        """기준선 총비용 — 리포트에 명시적 표시 (FR-705-AC1)."""
        return aggregate(list(self.baseline_rows))

    def new_total(self) -> Money:
        return aggregate(list(self.new_rows))

    def incremental_total(self) -> Money:
        """편익 증분 총액 = new − baseline."""
        return Money(self.new_total() - self.baseline_total())


def compute_incremental(
    baseline: list[CashFlowRow], new: list[CashFlowRow]
) -> list[CashFlowRow]:
    """new − baseline 의 증분 행.

    같은 tag 끼리 짝지어 빼고, baseline 에만 있는 tag 는 음수(감소),
    new 에만 있는 tag 는 그대로(증가).
    """
    baseline_by_tag: dict[str, CashFlowRow] = {
        (r.tag or r.label): r for r in baseline
    }
    new_by_tag: dict[str, CashFlowRow] = {
        (r.tag or r.label): r for r in new
    }
    all_tags = set(baseline_by_tag) | set(new_by_tag)

    incremental: list[CashFlowRow] = []
    for tag in sorted(all_tags):
        b_row = baseline_by_tag.get(tag)
        n_row = new_by_tag.get(tag)
        b_amounts = b_row.amounts if b_row else {}
        n_amounts = n_row.amounts if n_row else {}
        all_years = set(b_amounts) | set(n_amounts)
        diff_amounts = {
            y: n_amounts.get(y, Money(0)) - b_amounts.get(y, Money(0))
            for y in sorted(all_years)
        }
        # 0 이 아닌 연도만 남긴다 — 0 인 행은 보이지 않는 것이 낫다
        diff_amounts = {y: v for y, v in diff_amounts.items() if v != Money(0)}
        if not diff_amounts:
            continue
        incremental.append(CashFlowRow(
            label=f"{tag} 증분",
            tag=tag,
            amounts=diff_amounts,
        ))
    return incremental


def compare_baseline_vs_new(
    baseline: list[CashFlowRow], new: list[CashFlowRow]
) -> BaselineComparison:
    """기준선 vs 신규 비교 — 증분 행과 함께 기준선 자체도 든다."""
    incremental = compute_incremental(baseline, new)
    return BaselineComparison(
        baseline_rows=tuple(baseline),
        new_rows=tuple(new),
        incremental_rows=tuple(incremental),
    )


def assert_baseline_displayed(comparison: BaselineComparison) -> None:
    """10.5 검증 — 기준선이 명시적으로 표시되었는가 (FR-705-AC1).

    기준선 없이 증분만 보이면 조항 위반이다 — 증분의 타당성을 검증할 수 없다.
    """
    if comparison.baseline_total() == ZERO and not comparison.baseline_rows:
        raise ValueError(
            "기준선이 표시되지 않았다 (FR-705-AC1). 증분만 계산하고 기준선을 "
            "보여 주지 않으면 증분의 타당성을 검증할 수 없다 (도메인 원칙 1-2)"
        )
