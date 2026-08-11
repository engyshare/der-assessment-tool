"""일간 대표일 디스패치 스택 — FR-1004-AC1.

「스택」이 조항의 말이다. 자원별 발전·방전 기여를 시간대별로 **쌓아 올려**
부하를 얼마나 덮었는지 한눈에 보여야 한다. 선 그래프를 여러 개 겹쳐 그리면
조항이 요구한 그림이 아니다 — 겹친 선은 합이 부하를 덮는지 눈으로 셀 수 없다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from core.contracts.chart import Chart
from core.contracts.validation import ValidationError
from core.report.charts._render import new_figure, to_png

_PALETTE: tuple[str, ...] = ("#1f5fa9", "#2e9e6b", "#e0a527", "#8956a3", "#c1452b")


class DispatchStack(Chart):
    """대표일 시간대별 자원 기여 스택 + 부하 곡선."""

    tag: ClassVar[str] = "dispatch_stack"
    label: ClassVar[str] = "일간 대표일 디스패치"
    clauses: ClassVar[tuple[str, ...]] = ("FR-1004-AC1",)
    required_keys: ClassVar[tuple[str, ...]] = ("resource_dispatch", "load")

    def draw(self, data: Mapping[str, Any]) -> bytes:
        resource_dispatch: Mapping[str, Sequence[float]] = data["resource_dispatch"]
        load: Sequence[float] = data["load"]

        if not resource_dispatch:
            raise ValidationError(
                field="chart.dispatch_stack.resource_dispatch",
                reason="자원별 디스패치가 비어 있습니다",
                action="자원명별 시간대 기여(kW) 사전을 넘기십시오",
            )
        if not load:
            raise ValidationError(
                field="chart.dispatch_stack.load",
                reason="부하 곡선이 비어 있습니다",
                action="같은 시간 해상도의 부하(kW) 배열을 넘기십시오",
            )

        mismatched = sorted(
            name for name, series in resource_dispatch.items() if len(series) != len(load)
        )
        if mismatched:
            raise ValidationError(
                field="chart.dispatch_stack.resource_dispatch",
                reason=f"부하와 시간 해상도가 다른 자원이 있습니다: {', '.join(mismatched)}",
                action="모든 자원 기여와 부하를 같은 스텝 수로 넘기십시오",
            )

        steps = list(range(len(load)))
        names = list(resource_dispatch)
        series = [list(resource_dispatch[name]) for name in names]

        figure = new_figure()
        axes = figure.axes[0]
        colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(names))]
        axes.stackplot(steps, *series, labels=names, colors=colors, alpha=0.85)
        axes.plot(steps, list(load), color="#222222", linewidth=1.6, linestyle="--", label="부하")
        axes.set_xlabel("시간대")
        axes.set_ylabel("전력 (kW)")
        axes.set_title(self.label)
        axes.legend(loc="upper right", fontsize="small")
        axes.grid(visible=True, alpha=0.3)
        return to_png(figure)
