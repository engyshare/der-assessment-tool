"""계절별 시간대별 운전 — **수요 · 발전 · 저장장치를 계절마다 갈라 그린다**.

사용자 요구 6 문면: *「계절별로 가구의 전력 수요, 발전, ESS 운전 등을 시간대별로
수치와 도표로 확인할 수 있어야 함」*. **수치**는 붙임 7 의 계절별 표
(`core/report/dispatch_sections.py::dispatch_profile_section`)가 싣고, **도표**가
이 파일이다.

## ⛔ `energy_balance`(월별)에 계절 넷을 먹이지 않는다 — 그래서 파일이 하나 늘었다

그 차트는 축에 **월**을 적고 자기가 받은 배열 길이만큼 눈금을 세운다
(`core/report/charts/energy_balance.py` 의 `axes.set_xlabel("월")` ·
`set_xticks(months)`). 계절은 **넷이지 열둘이 아니므로** 계절 넷을 그 축에 얹으면
그림이 「1월~4월」을 주장한다. 조항 `FR-1004-AC1` 이 그 차트를 *「월별 에너지
수지」*로 세운 것이므로 축의 뜻을 바꾸는 것은 그 차트를 없애는 것과 같다.

## 조항 — `FR-1004-AC1` 의 **첫 항목**이다

그 수용기준의 여섯 중 첫째가 *「일간 대표일 디스패치 스택」*이고
`core/report/charts/dispatch_stack.py` 가 그것을 **연간등가 하루 한 벌**로
그린다. 이 차트가 그리는 것은 같은 그림을 **계절의 대표일마다** 그린 것이다 —
새 조항을 지어내지 않았고, 계절 축은 조항이 아니라 사용자 요구 6 이 연 것이다.

## 왜 스택 선이 아니라 막대인가

저장장치는 **충전이 음수**다(`DispatchHour` 의 부호 규약). 쌓아 올리는 선으로
그리면 음수 구간이 누적 높이를 끌어내려 「그 시각에 발전이 줄었다」로 보인다.
0 위·아래로 **따로** 쌓는 막대는 그 둘을 가르며, 그것은 이 저장소가
`energy_balance.py` 에서 이미 고른 관용구다(공급은 0 위, 사용은 0 아래).

## ⚠ 범례는 **조인 키가 아니라 사람 말**이다 (R65/WP-4)

`resource_dispatch` 의 키는 `ResourceLine.name`(`e2e-pv`)이고 그것은 조인 키다 —
`core/report/method_sections.py::_earner_cell` 이 *「그것은 심의위원이 읽을
이름이 아니다」* 라고 이미 적었다. 그래서 계열 이름은 **입력이 함께 넘긴
`resource_labels`** 로 인쇄한다. ⛔ 사전의 키를 라벨로 갈아 끼우지 않는다:
종류가 같은 자원이 둘이면 키가 겹쳐 **계열 하나가 사라진다.**

## ⚠ 계절 사이를 이어 그리지 않는다

계절 넷은 **같은 하루를 네 번** 그린 것이지 96시간이 이어진 것이 아니다. 그래서
막대는 계절마다 자기 구간에만 서고 사이에 세로 칸막이가 선다 — 이어 그리면
검토자가 봄 23시 다음에 여름 0시가 온 것으로 읽을 수 있다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from core.contracts.chart import Chart
from core.contracts.validation import ValidationError
from core.report.charts._render import new_figure, to_png
from core.report.dispatch_notes import DEMAND_LABEL

#: 자원 색. `dispatch_stack.py` 와 **같은 순서**다 — 두 그림이 같은 실행의 같은
#: 자원을 그리므로 색이 갈리면 검토자가 둘을 맞대 볼 수 없다.
_PALETTE: tuple[str, ...] = ("#1f5fa9", "#2e9e6b", "#e0a527", "#8956a3", "#c1452b")

#: 계절 칸막이·0선의 색.
_GUIDE = "#888888"

#: 수요 곡선의 색·모양. `dispatch_stack.py` 의 부하 곡선과 같다.
_DEMAND_COLOR = "#222222"

#: 수요 곡선의 범례 이름 (R65/WP-4).
#:
#: ## ★★ R68/WP-3 — **글자가 여기 있었고, 정본이 아래로 내려갔다**
#:
#: 종전에는 이 파일과 `app/services/ui_charts.py` **두 곳**에 같은 글자가 따로
#: 적혀 있었고(계층이 서로의 import 를 막아서 — `core.report` 가 `app` 을 알면
#: `lint-imports` 가 거부한다) **검사가 두 글자를 맞댔다**
#: (`tests/app/test_ui_charts.py`). R68/WP-3 이 검증 3단계 표에도 같은 낱말을
#: 세워야 해서 자리가 셋이 되었고, 셋을 맞대는 검사는 더 버티지 못한다.
#: ⇒ 정본은 `core/report/dispatch_notes.py::DEMAND_LABEL` 이다. **이 파일이
#: 정본을 갖지 않는 이유**는 이 모듈이 `matplotlib` 을 끄는 `_render` 를 모듈
#: 수준에서 import 하기 때문이다 — 글자를 여기 두면 «표»를 짓는 텍스트 층이
#: 그림 묶음을 끌어오게 된다(그 상수의 주석이 그 실측을 진다).
#: ⛔ 글자를 바꾸지 마라 — 화면·그림·표가 같은 낱말이어야 한다.
_DEMAND_LABEL = DEMAND_LABEL


class SeasonalOperation(Chart):
    """계절마다 하루 24스텝의 수요·발전·저장장치 운전."""

    tag: ClassVar[str] = "seasonal_operation"
    label: ClassVar[str] = "계절별 시간대별 운전"
    clauses: ClassVar[tuple[str, ...]] = ("FR-1004-AC1",)
    required_keys: ClassVar[tuple[str, ...]] = ("seasons",)

    def draw(self, data: Mapping[str, Any]) -> bytes:
        seasons = _checked(data["seasons"])
        names = tuple(seasons[0]["resource_dispatch"])
        steps = len(seasons[0]["load"])
        # ★ 범례에 인쇄할 글자 — **조인 키가 아니다** (R65/WP-4). 없으면 키를
        # 그대로 쓴다: 라벨이 안 온 실행에서 계열 이름이 사라지는 것보다
        # `e2e-pv` 가 보이는 편이 낫다.
        labels: Mapping[str, str] = data.get("resource_labels") or {}

        figure = new_figure(width=12.0, height=5.0)
        axes = figure.axes[0]
        colors = {name: _PALETTE[i % len(_PALETTE)] for i, name in enumerate(names)}

        for index, season in enumerate(seasons):
            offset = index * steps
            xs = [offset + step for step in range(steps)]
            up = [0.0] * steps
            down = [0.0] * steps
            for name in names:
                values = [float(v) for v in season["resource_dispatch"][name]]
                # 0 위·아래로 **따로** 쌓는다 — 위 머리말의 사유.
                positive = [max(0.0, v) for v in values]
                negative = [min(0.0, v) for v in values]
                axes.bar(
                    xs, positive, bottom=up, width=0.9, color=colors[name],
                    label=labels.get(name, name) if index == 0 else None,
                )
                axes.bar(xs, negative, bottom=down, width=0.9, color=colors[name])
                up = [b + v for b, v in zip(up, positive, strict=True)]
                down = [b + v for b, v in zip(down, negative, strict=True)]
            axes.plot(
                xs, [float(v) for v in season["load"]],
                color=_DEMAND_COLOR, linewidth=1.4, linestyle="--",
                label=_DEMAND_LABEL if index == 0 else None,
            )
            if index:
                axes.axvline(offset - 0.5, color=_GUIDE, linewidth=1.0)

        axes.axhline(0.0, color=_GUIDE, linewidth=1.0)
        axes.set_xticks([index * steps + steps / 2 - 0.5 for index in range(len(seasons))])
        axes.set_xticklabels(
            [f"{season['name']} ({int(season['days'])}일)" for season in seasons]
        )
        axes.set_xlabel(f"계절별 대표일 — 각 구간이 하루 {steps}스텝이다")
        axes.set_ylabel("전력 (kWh/스텝) — 위: 내보냄, 아래: 받아들임")
        axes.set_title(SeasonalOperation.label)
        axes.legend(loc="upper right", fontsize="small", ncol=2)
        axes.grid(visible=True, axis="y", alpha=0.3)
        return to_png(figure)


def _checked(raw: Any) -> tuple[Mapping[str, Any], ...]:
    """계절 목록을 **거부로** 검사한다 — 빈 그림을 내지 않는다 (`NFR-303`).

    ⚠ 모자란 계절을 건너뛰거나 0 으로 메우지 않는다. `render_charts` 독스트링이
    같은 판단을 적었다 — *「그 빈자리는 심의자료가 인쇄된 뒤에 발견된다」*.
    """
    seasons = tuple(raw) if isinstance(raw, Sequence) else ()
    if not seasons:
        raise ValidationError(
            field="chart.seasonal_operation.seasons",
            reason="계절이 하나도 없습니다",
            action=(
                "계절마다 이름·일수·자원별 시간대 기여·수요 곡선을 담은 목록을 "
                "넘기십시오. 계절이 없는 실행이라면 그림을 그리지 마십시오 — "
                "빈 그림은 「그렸다」로 집계됩니다"
            ),
        )

    required = ("name", "days", "resource_dispatch", "load")
    for index, season in enumerate(seasons):
        missing = [key for key in required if key not in season]
        if missing:
            raise ValidationError(
                field="chart.seasonal_operation.seasons",
                reason=f"{index + 1}번째 계절에 없는 칸이 있습니다: {', '.join(missing)}",
                action=f"계절마다 {', '.join(required)} 를 모두 넘기십시오",
            )
        if not season["resource_dispatch"] or not season["load"]:
            raise ValidationError(
                field="chart.seasonal_operation.seasons",
                reason=f"계절 {season['name']!r} 의 자원 기여나 수요 곡선이 비어 있습니다",
                action="자원별 시간대 기여 사전과 같은 길이의 수요 배열을 넘기십시오",
            )

    steps = len(seasons[0]["load"])
    names = tuple(seasons[0]["resource_dispatch"])
    for season in seasons:
        lengths = {len(season["load"])} | {
            len(series) for series in season["resource_dispatch"].values()
        }
        if lengths != {steps}:
            raise ValidationError(
                field="chart.seasonal_operation.seasons",
                reason=(
                    f"계절 {season['name']!r} 의 스텝 수가 다릅니다: "
                    f"{sorted(lengths)} — 기준은 {steps}스텝입니다"
                ),
                action=(
                    "계절마다 같은 해상도의 하루를 넘기십시오. 계절을 이어 붙인 "
                    "배열을 넘기면 그림이 없는 시간축을 주장합니다"
                ),
            )
        if tuple(season["resource_dispatch"]) != names:
            raise ValidationError(
                field="chart.seasonal_operation.seasons",
                reason=(
                    f"계절 {season['name']!r} 의 자원 목록이 다릅니다: "
                    f"{tuple(season['resource_dispatch'])} ≠ {names}"
                ),
                action=(
                    "계절마다 같은 자원 목록을 같은 차례로 넘기십시오. 갈리면 "
                    "같은 색이 계절마다 다른 자원을 가리킵니다"
                ),
            )
    return seasons
