"""`FR-105-AC4` — 선택한 운전 방법이 `FR-302` 디스패치 우선순위와 어떻게
결합되는지 리포트에 표기한다.

`core.engine.rule_based` 의 **공개 접근자**(`rule_for`·`needs_price_signal`)
만 부른다 — 사설 함수(`_rule_for`·`_needs_price_signal`)에 묶이면 엔진
내부 구현을 바꿀 수 없다.

## ⚠ 이 파일은 **배포 호출자가 0곳이었다** (R33 · 검토 「1차 의견」 2·3)

`build_dispatch_notes()` 를 부르는 코드는 `tests/report/test_dispatch_notes.py`
뿐이었다. 즉 `FR-105-AC4`(*「리포트에 표기한다」*)는 매핑표에서 「자동」인데
**표기하는 리포트가 없었다** — 이 저장소가 R32·R33 에서 여섯 번 만난
「선언·계산은 있는데 읽는 쪽이 없다」와 같은 형태다.

검토 의견 둘이 정확히 그 자리를 짚었다 — *「규칙이 붙임에 기재되지 않으면
내용을 이해할 수 없음」*(의견 2)과 *「시간대별 디스패치 표」*(의견 3). 지금은
`core/report/dispatch_sections.py` 가 이 파일을 읽어 붙임 6·7 을 그린다.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from core.contracts.der import DER
from core.contracts.engine import SystemDispatch
from core.engine.rule_based import (
    DEFAULT_RULE_ORDER,
    DispatchRule,
    needs_price_signal,
    rule_for,
)


@dataclass(frozen=True)
class DispatchNote:
    """자원 하나의 「운전 방법 × FR-302 우선순위」 결합 표기."""

    resource_name: str
    operating_mode: str
    dispatch_rule: DispatchRule
    dispatch_priority: int
    price_linked: bool


def build_dispatch_notes(
    resources: list[DER],
    *,
    rule_order: tuple[DispatchRule, ...] = DEFAULT_RULE_ORDER,
) -> list[DispatchNote]:
    """자원마다 위 표기를 만든다.

    `dispatch_priority` 는 `rule_order` 안에서 그 자원의 규칙이 몇 번째인지다
    — `rule_order` 를 바꾸면 이 값도 그대로 따라간다.
    """
    rank = {rule: index for index, rule in enumerate(rule_order)}
    notes: list[DispatchNote] = []
    for resource in resources:
        rule = rule_for(resource)
        notes.append(
            DispatchNote(
                resource_name=resource.name,
                operating_mode=resource.operating_mode,
                dispatch_rule=rule,
                dispatch_priority=rank[rule],
                price_linked=needs_price_signal(resource),
            )
        )
    return notes


@dataclass(frozen=True)
class DispatchHour:
    """대표일 한 스텝의 운전 — 검토 「1차 의견」 3.

    ⚠ **부호를 여기서 뒤집지 않는다.** `DispatchResult` 의 규약이
    *「양수 = 내보냄(발전·방전) · 음수 = 받아들임(소비·충전)」* 이고, 그
    규약대로 실어야 표를 읽는 사람이 **충전과 방전을 한 열에서** 볼 수 있다.
    표시 층이 부호를 뒤집으면 ESS 의 충·방전이 두 열로 갈리고, 그때 「스텝
    합계가 계통 송전량과 맞는가」를 눈으로 셀 수 없게 된다.
    """

    #: 대표일 안에서 몇 번째 스텝인가 (0부터).
    step: int
    #: 자원 이름 → 그 스텝의 전력(kWh). 위 부호 규약을 따른다.
    per_resource: Mapping[str, float]
    #: 계통으로 내보낸 양(kWh, 양수).
    grid_export: float
    #: 계통에서 받은 양(kWh, 양수).
    grid_import: float


def build_hourly_profile(dispatch: SystemDispatch) -> tuple[DispatchHour, ...]:
    """운전 결과를 **스텝별 한 줄씩**으로 편다.

    ## 왜 리포트가 이것을 필요로 하는가

    리포트는 *「잉여 전력 판매 — 대표일 2,268원 × 365일」* 을 싣는데, 그
    대표일 금액이 **어느 시간대의 어느 kWh 에서 왔는지**는 어디에도 없었다.
    검토 의견이 시간대별 표를 요구한 자리가 그것이며, 재료(24스텝)는 실행이
    이미 만들고 있었다 — 경계를 넘지 않았을 뿐이다.

    ⚠ **여기서 합계를 내지 않는다.** 표시 층이 합을 내고 그것이 편익 산식의
    대입값과 맞는지 보게 한다 — 두 곳에서 합하면 어느 쪽이 옳은지 말할 수
    없다.
    """
    steps = len(dispatch.grid_export)
    return tuple(
        DispatchHour(
            step=step,
            per_resource={
                name: float(result.electric[step])
                for name, result in sorted(dispatch.per_resource.items())
            },
            grid_export=float(dispatch.grid_export[step]),
            grid_import=float(dispatch.grid_import[step]),
        )
        for step in range(steps)
    )
