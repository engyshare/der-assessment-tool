"""비용·편익 구성 파이 — FR-1004-AC1 · FR-1002-AC1.

**음수 항목을 조용히 버리지 않는다.** 파이는 음수를 그릴 수 없는데, 편익
항목에 음수가 섞이는 것은 부호 규약이 어긋났다는 뜻이다 — 버리고 그리면
합계가 맞지 않는 그림이 그럴듯하게 나온다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from core.contracts.chart import Chart
from core.contracts.validation import ValidationError
from core.report.charts._render import new_figure, to_png


class CostBenefitPie(Chart):
    """항목별 구성비. 값은 전부 0 이상이어야 한다."""

    tag: ClassVar[str] = "cost_benefit_pie"
    label: ClassVar[str] = "비용·편익 구성"
    clauses: ClassVar[tuple[str, ...]] = ("FR-1004-AC1",)
    required_keys: ClassVar[tuple[str, ...]] = ("items",)

    def draw(self, data: Mapping[str, Any]) -> bytes:
        items: Mapping[str, float] = data["items"]
        if not items:
            raise ValidationError(
                field="chart.cost_benefit_pie.items",
                reason="구성 항목이 비어 있습니다",
                action="항목명과 금액의 사전을 넘기십시오 (예: {'설비비': 1200000})",
            )

        negative = sorted(name for name, value in items.items() if float(value) < 0.0)
        if negative:
            raise ValidationError(
                field="chart.cost_benefit_pie.items",
                reason=f"음수 항목이 있어 구성비를 그릴 수 없습니다: {', '.join(negative)}",
                action=(
                    "비용과 편익을 각각 양수로 넘기십시오. 부호로 둘을 구분하고 "
                    "있다면 차트를 둘로 나누어야 합니다"
                ),
            )

        total = sum(float(value) for value in items.values())
        if total <= 0.0:
            raise ValidationError(
                field="chart.cost_benefit_pie.items",
                reason="합계가 0 이라 구성비가 정의되지 않습니다",
                action="0 이 아닌 항목을 하나 이상 포함하십시오",
            )

        labels = list(items)
        values = [float(items[name]) for name in labels]

        figure = new_figure(width=6.0, height=6.0)
        axes = figure.axes[0]
        axes.pie(
            values,
            labels=labels,
            autopct="%1.1f%%",
            startangle=90,
            counterclock=False,
        )
        axes.set_title(self.label)
        axes.set_aspect("equal")
        return to_png(figure)
