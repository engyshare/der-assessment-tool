"""2변수 지표 등고선 + 목표 달성 영역 음영 — FR-803-AC1.

조항 문면이 둘을 요구한다 — *「2변수 히트맵: 축 변수 2개 선택 → 지표 등고선.
"목표 달성 영역" 을 음영으로 구분」*. **그래서 그림에 층이 둘이다**: 아래가
달성 여부 음영, 위가 지표 등고선.

입력은 `core.casegrid.analysis.feasible_region()` 의 셀을 **평범한 사전으로**
받는다(`x_value`·`y_value`·`metric_value`·`achieved`). `FeasibleCell` 을 직접
import 하지 않는 이유는 `tornado` 가 `rank_influences()` 출력을 사전으로 받는
것과 같다 — 계층상 `core.report` → `core.casegrid` 가 허용되더라도, 그림이
분석 구획의 **내부 표현**에 묶이면 그쪽이 필드를 하나 바꿀 때 그림이 깨진다.

**음영을 셀 단위로 칠하고 등고선만 보간한다.** 달성 여부는 케이스를 실제로
돌려 얻은 **이산 판정**이므로, 그것을 보간하면 돌리지 않은 좌표에 대해
「달성」이라고 말하는 셈이 된다. 지표값은 연속량이라 등고선 보간이 뜻을 갖는다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from matplotlib.patches import Patch, Rectangle

from core.contracts.chart import Chart
from core.contracts.validation import ValidationError
from core.report.charts._render import new_figure, to_png

#: 달성 영역 음영 색. 등고선(어두운 선)과 대비되도록 옅게 둔다.
_ACHIEVED_COLOR = "#2e7d32"
_SHADE_ALPHA = 0.25


def _numeric_axis(values: Sequence[object], axis: str) -> list[float]:
    """축 좌표를 실수로 환원한다 — 등고선은 순서 있는 수치축을 요구한다."""
    out: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError(
                field=f"chart.feasible_region.{axis}",
                reason=f"축 좌표가 수치가 아닙니다: {value!r}",
                action=(
                    f"{axis} 축 변수는 등고선을 그릴 수 있는 수치여야 합니다. "
                    "범주형 변수를 비교하려면 model_comparison 차트를 쓰십시오"
                ),
            )
        out.append(float(value))
    return out


class FeasibleRegion(Chart):
    """2변수 그리드의 지표 등고선과 목표 달성 영역."""

    tag: ClassVar[str] = "feasible_region"
    label: ClassVar[str] = "2변수 지표 등고선 · 목표 달성 영역"
    clauses: ClassVar[tuple[str, ...]] = ("FR-803-AC1", "FR-1004-AC1")
    required_keys: ClassVar[tuple[str, ...]] = (
        "cells",
        "x_label",
        "y_label",
        "metric_label",
    )

    def draw(self, data: Mapping[str, Any]) -> bytes:
        cells: Sequence[Mapping[str, Any]] = data["cells"]
        if not cells:
            raise ValidationError(
                field="chart.feasible_region.cells",
                reason="셀 목록이 비어 있습니다",
                action=(
                    "feasible_region() 결과를 넘기십시오. 케이스가 하나도 "
                    "없다면 그리드를 먼저 실행해야 합니다"
                ),
            )

        xs = _numeric_axis(
            sorted({cell["x_value"] for cell in cells}, key=_sort_key), "x"
        )
        ys = _numeric_axis(
            sorted({cell["y_value"] for cell in cells}, key=_sort_key), "y"
        )
        # **2변수 조항이므로 두 축 모두 2수준 이상이어야 한다.** 한 축이 1수준이면
        # 등고선이 성립하지 않는다 — 여기서 막지 않으면 matplotlib 이 빈 그림을
        # 돌려주고, 빈 그림은 「그렸다」로 집계된다 (`ChartArtifact` 가 막는 것은
        # 빈 바이트이고, 축이 없는 PNG 는 바이트가 있다).
        if len(xs) < 2 or len(ys) < 2:
            raise ValidationError(
                field="chart.feasible_region",
                reason=f"축 수준이 모자랍니다: x {len(xs)}수준 · y {len(ys)}수준",
                action=(
                    "FR-803-AC1 은 2변수 등고선이므로 두 축 모두 서로 다른 값이 "
                    "2개 이상 필요합니다. 한 변수만 훑는다면 tornado 를 쓰십시오"
                ),
            )

        x_index = {value: column for column, value in enumerate(xs)}
        y_index = {value: row for row, value in enumerate(ys)}

        metric: list[list[float | None]] = [
            [None] * len(xs) for _ in range(len(ys))
        ]
        achieved: list[list[bool | None]] = [
            [None] * len(xs) for _ in range(len(ys))
        ]
        for cell in cells:
            row = y_index[float(cell["y_value"])]
            column = x_index[float(cell["x_value"])]
            metric[row][column] = float(cell["metric_value"])
            achieved[row][column] = bool(cell["achieved"])

        # **격자가 채워지지 않으면 그리지 않는다.** 빈 칸을 0 으로 메우면
        # 등고선이 그 자리를 지나가고, 그림은 돌리지 않은 조합에 대해
        # 지표값을 주장하게 된다.
        holes = [
            (xs[column], ys[row])
            for row in range(len(ys))
            for column in range(len(xs))
            if metric[row][column] is None
        ]
        if holes:
            raise ValidationError(
                field="chart.feasible_region.cells",
                reason=(
                    f"격자에 빈 칸이 {len(holes)}개 있습니다 "
                    f"(예: x={holes[0][0]}, y={holes[0][1]})"
                ),
                action=(
                    "두 축의 모든 조합이 실행된 결과를 넘기십시오. 일부만 "
                    "실행했다면 등고선은 실행하지 않은 좌표의 값을 지어냅니다"
                ),
            )

        figure = new_figure()
        axes = figure.axes[0]

        # ① 달성 영역 음영 — **셀 단위**. 보간하지 않는다
        shaded = 0
        for row in range(len(ys)):
            for column in range(len(xs)):
                if not achieved[row][column]:
                    continue
                shaded += 1
                axes.add_patch(
                    _cell_patch(xs, ys, column, row),
                )

        # ② 지표 등고선 — 여기서만 보간한다
        contours = axes.contour(
            xs,
            ys,
            [[value for value in line] for line in metric],
            colors="#1f3552",
            linewidths=1.1,
        )
        axes.clabel(contours, inline=True, fontsize="small", fmt="%.3g")

        axes.set_xlabel(str(data["x_label"]))
        axes.set_ylabel(str(data["y_label"]))
        axes.set_title(f"{self.label} — {data['metric_label']}")
        axes.set_xticks(xs)
        axes.set_yticks(ys)
        axes.grid(visible=True, alpha=0.2)
        # **달성 셀이 0개인 것도 결과다** — 범례에 그렇게 적는다. 음영이 없는
        # 그림을 보고 「음영 기능이 빠졌다」고 읽지 않도록 한다
        axes.legend(
            handles=[_shade_proxy(shaded, len(xs) * len(ys))],
            loc="upper right",
            fontsize="small",
        )
        return to_png(figure)


def _sort_key(value: object) -> float:
    """정렬 전용 키. 수치가 아니면 `_numeric_axis` 가 뒤에서 3요소로 거부한다."""
    return float(value) if isinstance(value, (int, float)) else float("nan")


def _cell_patch(
    xs: Sequence[float], ys: Sequence[float], column: int, row: int
) -> Rectangle:
    """셀 하나를 덮는 사각형. 경계는 이웃과의 **중간점**이다."""
    left, right = _bounds(xs, column)
    bottom, top = _bounds(ys, row)
    return Rectangle(
        (left, bottom),
        right - left,
        top - bottom,
        facecolor=_ACHIEVED_COLOR,
        edgecolor="none",
        alpha=_SHADE_ALPHA,
        zorder=0,
    )


def _bounds(axis: Sequence[float], index: int) -> tuple[float, float]:
    """축 위 한 점이 대표하는 구간. 양 끝은 인접 간격의 절반으로 넓힌다."""
    current = axis[index]
    previous = axis[index - 1] if index > 0 else None
    following = axis[index + 1] if index + 1 < len(axis) else None
    low = (current + previous) / 2 if previous is not None else None
    high = (current + following) / 2 if following is not None else None
    if low is None:
        low = current - (high - current)   # type: ignore[operator]
    if high is None:
        high = current + (current - low)
    return low, high


def _shade_proxy(shaded: int, total: int) -> Patch:
    """음영의 뜻을 범례로 적는다 — **0개일 때도 적는다.**"""
    return Patch(
        facecolor=_ACHIEVED_COLOR,
        alpha=_SHADE_ALPHA,
        label=f"목표 달성 영역 ({shaded}/{total} 케이스)",
    )
