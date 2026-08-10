"""영향도 토네이도 — FR-803-AC2 · FR-1004-AC1 · FR-1002-AC1.

입력은 `core.report.sensitivity.rank_influences()` 의 출력 형식을 그대로
받는다. **정렬을 여기서 다시 하지 않는다** — 순위 판정은 민감도 쪽 몫이고,
그림이 제 나름대로 정렬하면 표와 그림이 어긋난다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from core.contracts.chart import Chart
from core.contracts.validation import ValidationError
from core.report.charts._render import new_figure, to_png


class Tornado(Chart):
    """인자별 영향폭을 가로 막대로 — 위가 가장 큰 영향."""

    tag: ClassVar[str] = "tornado"
    label: ClassVar[str] = "인자별 영향도"
    clauses: ClassVar[tuple[str, ...]] = ("FR-803-AC2", "FR-1004-AC1")
    required_keys: ClassVar[tuple[str, ...]] = ("influences",)

    def draw(self, data: Mapping[str, Any]) -> bytes:
        influences: Sequence[Mapping[str, Any]] = data["influences"]
        if not influences:
            raise ValidationError(
                field="chart.tornado.influences",
                reason="영향도 목록이 비어 있습니다",
                action=(
                    "rank_influences() 결과를 넘기십시오. 인자가 하나도 없다면 "
                    "민감도 분석 대상 변수를 먼저 지정해야 합니다"
                ),
            )

        names = [str(item["name"]) for item in influences]
        deltas = [abs(float(item["delta"])) for item in influences]
        # 가장 큰 것이 위로 오도록 뒤집어 그린다 (barh 는 아래에서 위로 쌓인다)
        positions = list(range(len(names)))

        figure = new_figure(height=max(2.5, 0.45 * len(names) + 1.2))
        axes = figure.axes[0]
        # **결론을 뒤집는 인자는 색으로 구분한다** — 영향이 큰 것과 결론을
        # 바꾸는 것은 다르며, 정책 판단에서 중요한 쪽은 뒤쪽이다
        colors = [
            "#c1452b" if bool(item.get("flips_conclusion")) else "#1f5fa9"
            for item in influences
        ]
        axes.barh(positions, deltas, color=colors)
        axes.set_yticks(positions)
        axes.set_yticklabels(names)
        axes.invert_yaxis()
        # ASCII 하이픈을 쓴다 — 한국어 글꼴 다수가 유니코드 마이너스(U+2212)
        # 글리프를 갖지 않아 두부(□)로 찍힌다
        axes.set_xlabel("지표 변화폭 |high - low|")
        axes.set_title(self.label)
        axes.grid(visible=True, axis="x", alpha=0.3)
        return to_png(figure)
