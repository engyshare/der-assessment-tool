"""누적 현금흐름 곡선 + 손익분기점 — FR-1004-AC1 · FR-701-AC2.

**손익분기 시점을 그림에서 읽을 수 있어야 한다.** 곡선만 그리면 「언제
회수되는가」를 사람이 눈금에서 세게 되고, 그것이 심의 자리에서 가장 먼저
나오는 질문이다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from core.contracts.chart import Chart
from core.contracts.validation import ValidationError
from core.report.charts._render import new_figure, to_png


class CashflowLine(Chart):
    """연차별 누적 현금흐름과 최초 흑자 전환 연차."""

    tag: ClassVar[str] = "cashflow_line"
    label: ClassVar[str] = "누적 현금흐름"
    clauses: ClassVar[tuple[str, ...]] = ("FR-1004-AC1",)
    required_keys: ClassVar[tuple[str, ...]] = ("cashflows",)

    def draw(self, data: Mapping[str, Any]) -> bytes:
        flows: Sequence[float] = data["cashflows"]
        if len(flows) < 2:
            raise ValidationError(
                field="chart.cashflow_line.cashflows",
                reason=f"연차가 {len(flows)}개뿐이라 곡선이 되지 않습니다",
                action="분석기간 전체의 연차별 순현금흐름을 넘기십시오 (2개 이상)",
            )

        cumulative: list[float] = []
        running = 0.0
        for value in flows:
            running += float(value)
            cumulative.append(running)
        years = list(range(1, len(cumulative) + 1))

        figure = new_figure()
        axes = figure.axes[0]
        axes.plot(years, cumulative, marker="o", linewidth=1.8, color="#1f5fa9")
        axes.axhline(0.0, color="#888888", linewidth=1.0, linestyle="--")
        axes.set_xlabel("연차")
        axes.set_ylabel("누적 현금흐름 (원)")
        axes.set_title(self.label)
        axes.grid(visible=True, alpha=0.3)

        # **손익분기 연차** — 누적이 처음으로 0 이상이 되는 해. 없으면 표시하지
        # 않는다. 없는 것을 «마지막 해» 로 찍으면 회수되지 않는 사업이 회수되는
        # 것처럼 보인다.
        breakeven = next(
            (year for year, value in zip(years, cumulative, strict=True) if value >= 0.0),
            None,
        )
        if breakeven is not None:
            axes.axvline(breakeven, color="#c1452b", linewidth=1.2)
            axes.annotate(
                f"손익분기 {breakeven}년차",
                xy=(breakeven, 0.0),
                xytext=(6, 10),
                textcoords="offset points",
                color="#c1452b",
            )
        return to_png(figure)
