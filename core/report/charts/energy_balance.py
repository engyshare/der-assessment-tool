"""월별 에너지 수지 — FR-1004-AC1.

「수지」이므로 **들어온 것과 나간 것이 함께** 보여야 한다. 공급측(생산·구입)은
0 위로, 사용측(자가소비·잉여판매)은 0 아래로 쌓아 대비시킨다. 양·음 방향을
쓰는 이유는 그것이 수지의 뜻이기 때문이며, `_render.to_png()` 가 유니코드
마이너스 두부(□)를 이미 막아 두었다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, ClassVar

from core.contracts.chart import Chart
from core.contracts.validation import ValidationError
from core.report.charts._render import new_figure, to_png

_SUPPLY_KEYS: tuple[str, ...] = ("production", "import")
_USE_KEYS: tuple[str, ...] = ("self_consumption", "export")
#: 읽기 전용 사전 — 모듈 수준 가변 컨테이너 금지 (NFR-205, `dict` 리터럴 금지)
_LABELS: Mapping[str, str] = MappingProxyType({
    "production": "생산",
    "import": "구입",
    "self_consumption": "자가소비",
    "export": "잉여판매",
})


class EnergyBalance(Chart):
    """월별 공급(생산·구입) 대 사용(자가소비·잉여판매) 대비."""

    tag: ClassVar[str] = "energy_balance"
    label: ClassVar[str] = "월별 에너지 수지"
    clauses: ClassVar[tuple[str, ...]] = ("FR-1004-AC1",)
    required_keys: ClassVar[tuple[str, ...]] = (
        "production",
        "self_consumption",
        "export",
        "import",
    )

    def draw(self, data: Mapping[str, Any]) -> bytes:
        series: dict[str, Sequence[float]] = {
            key: data[key] for key in self.required_keys
        }
        lengths = {key: len(values) for key, values in series.items()}
        if len(set(lengths.values())) != 1 or next(iter(lengths.values())) == 0:
            raise ValidationError(
                field="chart.energy_balance",
                reason=f"항목별 월 수가 다릅니다: {lengths}",
                action="생산·자가소비·잉여판매·구입 모두 같은 개월 수의 배열로 넘기십시오",
            )

        months = list(range(1, next(iter(lengths.values())) + 1))

        figure = new_figure()
        axes = figure.axes[0]

        supply_base = [0.0] * len(months)
        for key in _SUPPLY_KEYS:
            values = [float(v) for v in series[key]]
            axes.bar(months, values, bottom=supply_base, label=_LABELS[key])
            supply_base = [b + v for b, v in zip(supply_base, values, strict=True)]

        use_base = [0.0] * len(months)
        for key in _USE_KEYS:
            values = [-float(v) for v in series[key]]
            axes.bar(months, values, bottom=use_base, label=_LABELS[key])
            use_base = [b + v for b, v in zip(use_base, values, strict=True)]

        axes.axhline(0.0, color="#888888", linewidth=1.0)
        axes.set_xlabel("월")
        axes.set_ylabel("에너지 (kWh) — 위: 공급, 아래: 사용")
        axes.set_title(self.label)
        axes.set_xticks(months)
        axes.legend(loc="upper right", fontsize="small")
        axes.grid(visible=True, axis="y", alpha=0.3)
        return to_png(figure)
