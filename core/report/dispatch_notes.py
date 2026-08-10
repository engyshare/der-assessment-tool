"""`FR-105-AC4` — 선택한 운전 방법이 `FR-302` 디스패치 우선순위와 어떻게
결합되는지 리포트에 표기한다.

`core.engine.rule_based` 의 **공개 접근자**(`rule_for`·`needs_price_signal`)
만 부른다 — 사설 함수(`_rule_for`·`_needs_price_signal`)에 묶이면 엔진
내부 구현을 바꿀 수 없다.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.contracts.der import DER
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
