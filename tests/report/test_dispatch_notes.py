"""`FR-105-AC4` 검증 — `core/report/dispatch_notes.py`.

조항 원문: "선택한 운전 방법이 FR-302 디스패치 우선순위와 어떻게 결합되는지
리포트에 표기한다." §13.2와 같은 방식으로, 기대값은 `DEFAULT_RULE_ORDER`
(및 그 역순)를 직접 세어 손으로 적는다 — 구현을 돌려 나온 값을 옮기지
않는다.
"""

from __future__ import annotations

import pytest

from core.der.ess import ESS, ESSOperatingMode
from core.der.pv import PV
from core.der.pv import OperatingMode as PVOperatingMode
from core.engine.rule_based import DEFAULT_RULE_ORDER, DispatchRule
from core.report.dispatch_notes import build_dispatch_notes


def make_pv() -> PV:
    """비가격 연동 운전 방법(자가소비 우선) — `DEFAULT_RULE_ORDER` 0번째
    (`PV_SELF_CONSUMPTION`)."""
    return PV(
        name="검증PV",
        capacity_kw=1.0,
        capacity_factor=0.15,
        operating_mode=PVOperatingMode.SELF_CONSUMPTION_FIRST,
    )


def make_ess_tou() -> ESS:
    """가격 연동 운전 방법(TOU 차익거래) — `DEFAULT_RULE_ORDER` 1번째
    (`ESS_CHARGE`)."""
    return ESS(
        name="검증ESS_TOU",
        capacity_kwh=10.0,
        power_kw=5.0,
        operating_mode=ESSOperatingMode.TOU_ARBITRAGE,
    )


def make_ess_self_consumption() -> ESS:
    """`make_ess_tou()` 와 자원·규칙·순위가 전부 같고 운전 방법만 다른
    대조군 — 가격 연동 여부 차이가 운전 방법 때문임을 분리해서 본다."""
    return ESS(
        name="검증ESS_자가소비",
        capacity_kwh=10.0,
        power_kw=5.0,
        operating_mode=ESSOperatingMode.SELF_CONSUMPTION,
    )


@pytest.mark.req("FR-105-AC4")
def test_operating_mode_is_reported_per_resource() -> None:
    """단언 1 — 자원마다 선택된 운전 방법이 표기된다."""
    notes = build_dispatch_notes([make_pv(), make_ess_tou()])
    by_name = {n.resource_name: n for n in notes}
    assert by_name["검증PV"].operating_mode == "자가소비 우선"
    assert by_name["검증ESS_TOU"].operating_mode == "TOU 차익거래"


@pytest.mark.req("FR-105-AC4")
def test_dispatch_rule_and_priority_are_reported_per_resource() -> None:
    """단언 2 — 자원마다 묶이는 디스패치 규칙과 그 규칙의 순위가 표기된다.

    `DEFAULT_RULE_ORDER`(`core/engine/rule_based.py`)를 손으로 센다:
        0 PV_SELF_CONSUMPTION · 1 ESS_CHARGE · 2 V2G_CHARGE · 3 GRID_EXPORT ·
        4 ESS_DISCHARGE · 5 V2G_DISCHARGE · 6 GRID_IMPORT
    PV → `PV_SELF_CONSUMPTION`(0번째), ESS → `ESS_CHARGE`(1번째).
    """
    notes = build_dispatch_notes([make_pv(), make_ess_tou()])
    by_name = {n.resource_name: n for n in notes}
    assert by_name["검증PV"].dispatch_rule == DispatchRule.PV_SELF_CONSUMPTION
    assert by_name["검증PV"].dispatch_priority == 0
    assert by_name["검증ESS_TOU"].dispatch_rule == DispatchRule.ESS_CHARGE
    assert by_name["검증ESS_TOU"].dispatch_priority == 1


@pytest.mark.req("FR-105-AC4")
def test_reversing_rule_order_changes_the_reported_priority() -> None:
    """단언 3 (이 구획의 핵심) — `rule_order` 를 바꾸면 표기된 순위도
    따라 바뀐다 (`FR-302-AC1` 「설정 가능한 순서」와의 결합).

    `DEFAULT_RULE_ORDER` 를 그대로 뒤집으면 손으로 세어:
        0 GRID_IMPORT · 1 V2G_DISCHARGE · 2 ESS_DISCHARGE · 3 GRID_EXPORT ·
        4 V2G_CHARGE · 5 ESS_CHARGE · 6 PV_SELF_CONSUMPTION
    `PV_SELF_CONSUMPTION` 은 6번째, `ESS_CHARGE` 는 5번째로 바뀐다 —
    기본 순서(0·1번째)와 정반대다.
    """
    reversed_order = tuple(reversed(DEFAULT_RULE_ORDER))
    notes = build_dispatch_notes([make_pv(), make_ess_tou()], rule_order=reversed_order)
    by_name = {n.resource_name: n for n in notes}
    assert by_name["검증PV"].dispatch_priority == 6
    assert by_name["검증ESS_TOU"].dispatch_priority == 5


@pytest.mark.req("FR-105-AC4")
def test_price_linked_flag_distinguishes_tou_family_modes() -> None:
    """단언 4 — 운전 방법이 가격 신호를 켜는지 여부가 표기된다.

    같은 자원(ESS)·같은 디스패치 규칙·같은 순위인데 운전 방법만 다르다 —
    가격 연동 여부의 차이가 「운전 방법」 자체 때문임을 순위·규칙 차이와
    분리해서 본다. `_PRICE_MODE_TOKENS`(`core/engine/rule_based.py`)에
    `"tou"` 가 있고 `"TOU 차익거래".casefold()` 가 그 토큰을 포함한다.
    `"자가소비 우선"` 은 어느 토큰도 포함하지 않는다.
    """
    tou = build_dispatch_notes([make_ess_tou()])[0]
    self_consumption = build_dispatch_notes([make_ess_self_consumption()])[0]
    assert tou.price_linked is True
    assert self_consumption.price_linked is False
    assert tou.dispatch_rule == self_consumption.dispatch_rule
    assert tou.dispatch_priority == self_consumption.dispatch_priority


@pytest.mark.req("FR-105-AC4")
def test_pv_is_never_price_linked_regardless_of_mode() -> None:
    """PV가 선언한 운전 방법 3종(§4 FR-105-AC1 PV 목록) 전부 가격 토큰이
    없다 — 비가격 연동 자원의 대조 사례로 고정한다."""
    for mode in PVOperatingMode:
        pv = PV(name="검증PV", capacity_kw=1.0, capacity_factor=0.15, operating_mode=mode)
        note = build_dispatch_notes([pv])[0]
        assert note.price_linked is False
