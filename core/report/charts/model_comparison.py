"""모델 비교 바 차트 — FR-1004-AC1.

여러 사업모델(또는 케이스)의 지표 하나를 막대로 나란히 비교한다. **지표
이름을 여기에 박지 않는다** — NPV 든 IRR 이든 호출자가 이미 골라 넘긴 값을
그릴 뿐이며, 지표를 여기서 고르면 다음 지표가 생길 때마다 이 파일을 고쳐야
한다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from core.contracts.chart import Chart
from core.contracts.validation import ValidationError
from core.report.charts._render import new_figure, to_png

_DEFAULT_METRIC_LABEL = "지표값"


class ModelComparison(Chart):
    """모델·케이스별 지표 값을 막대로 대비."""

    tag: ClassVar[str] = "model_comparison"
    label: ClassVar[str] = "모델 비교"
    clauses: ClassVar[tuple[str, ...]] = ("FR-1004-AC1",)
    required_keys: ClassVar[tuple[str, ...]] = ("model_comparison",)

    def draw(self, data: Mapping[str, Any]) -> bytes:
        values: Mapping[str, float] = data["model_comparison"]
        if not values:
            raise ValidationError(
                field="chart.model_comparison.model_comparison",
                reason="비교할 모델이 없습니다",
                action="모델명과 지표값의 사전을 넘기십시오 (예: {'기본안': 1200000})",
            )

        metric_label = str(data.get("comparison_metric_label", _DEFAULT_METRIC_LABEL))
        names = list(values)
        amounts = [float(values[name]) for name in names]
        positions = list(range(len(names)))
        colors = ["#c1452b" if v < 0.0 else "#1f5fa9" for v in amounts]

        figure = new_figure()
        axes = figure.axes[0]
        axes.bar(positions, amounts, color=colors)
        axes.set_xticks(positions)
        axes.set_xticklabels(names)
        axes.axhline(0.0, color="#888888", linewidth=1.0)
        axes.set_ylabel(metric_label)
        axes.set_title(self.label)
        axes.grid(visible=True, axis="y", alpha=0.3)
        return to_png(figure)
