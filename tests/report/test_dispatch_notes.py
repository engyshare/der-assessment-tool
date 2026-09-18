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
from core.report.dispatch_notes import (
    DEMAND_LABEL,
    NO_APPLIED_ALLOCATION,
    DispatchHour,
    applied_allocation,
    build_dispatch_notes,
    declared_operating_mode,
    resolved_operating_mode,
    resource_display_name,
    split_by_direction,
    split_three_ways,
)


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


# ── 부호로 가르기 (`split_by_direction`) — R64/WP-8b ──────────────────
#
# 그 규칙의 소유자가 이 모듈인 이유는 그쪽 독스트링이 갖는다: 붙임 8 의 자가소비
# 측정(`core/report/measured_run.py`)과 붙임 10 의 결손 측정
# (`core/report/ess_sizing_section.py`)이 **같은 발전·같은 부하**를 봐야 한다.


def _hour(step: int, **per_resource: float) -> DispatchHour:
    return DispatchHour(
        step=step, per_resource=dict(per_resource), grid_export=0.0, grid_import=0.0
    )


def test_the_split_is_by_sign_not_by_name() -> None:
    """★★ **이름으로 가르지 않는다** — 이름이 무엇이든 부호가 갈래를 정한다.

    이름으로 가르면 자원이 늘 때마다 그 자리를 고쳐야 하고, 고치지 않으면
    조용히 0 이 된다.
    """
    hours = [
        _hour(0, 이름없는발전=1.0, 이름없는부하=-2.0),
        _hour(1, 이름없는발전=3.0, 이름없는부하=-1.0),
    ]
    assert split_by_direction(hours) == (("이름없는발전",), ("이름없는부하",))


def test_a_resource_that_does_both_is_in_neither_side() -> None:
    """★★ 충·방전을 함께 하는 자원(ESS)은 **어느 쪽도 아니다.**

    한쪽에 넣으면 `min(발전, 부하)` 의 분자·분모에 방전이나 충전이 섞이고, 그
    섞임은 총량이 맞으므로 수지 검사를 지난다.
    """
    hours = [_hour(0, ess=2.0, load=-1.0), _hour(1, ess=-2.0, load=-1.0)]
    generation, load = split_by_direction(hours)
    assert generation == ()
    assert load == ("load",)


def test_a_resource_that_is_flat_zero_is_in_neither_side() -> None:
    """★ 전 스텝 0 인 자원은 발전도 부하도 아니다 — 그 자원은 **아무것도 하지
    않았고**, 발전으로 세면 「발전이 있었다」가 거짓이 된다."""
    hours = [_hour(0, idle=0.0, load=-1.0), _hour(1, idle=0.0, load=-1.0)]
    assert split_by_direction(hours) == ((), ("load",))


def test_an_empty_day_splits_into_nothing() -> None:
    """★ 잴 하루가 없으면 **빈 짝**이다 — 부르는 쪽이 「없다」를 판정한다."""
    assert split_by_direction([]) == ((), ())


def test_the_declaration_and_the_allocation_have_one_accessor_each() -> None:
    """★★ **짝 함수 둘** — 합친 문면을 쪼개지 않고 조각마다 하나씩 (R68/WP-2).

    `resolved_operating_mode()` 는 선언과 배분을 **합친** 문면을 돌려주고 그
    형태를 심의 붙임 6 이 읽는다 — 반환형을 바꾸면 그 붙임이 함께 바뀐다.
    검증 3단계는 같은 재료를 **두 열로** 그려야 하므로, 합친 함수를 고치지 않고
    조각을 읽는 접근자를 둘 세웠다.

    ⛔ **` · ` 로 쪼개 가르지 않는다** — 배분 문면 «안에도» 그 구분자가 있다.
    이 검사가 그 함정을 실물로 붙든다: 배분 조각 자체가 구분자를 품은 자원을
    넣고, 쪼개는 구현이라면 반드시 틀리는 값을 기대한다.
    """
    note = build_dispatch_notes([make_ess_tou()])[0]
    allocation = "방전 배분: 부하 추종 (방전창 18~21시 안) · 창 밖은 대기"
    combined = f"{note.operating_mode} · {allocation}"

    assert declared_operating_mode(note) == note.operating_mode, (
        "선언 칸이 자원이 선언한 짧은 라벨이 아니다"
    )
    assert applied_allocation(note, {note.resource_name: allocation}) == allocation, (
        "배분 칸이 그 조각을 그대로 나르지 않았다 — 쪼개는 구현이면 여기서 "
        f"「{combined.split(' · ')[1]}」 로 잘린다"
    )
    assert resolved_operating_mode(note, {note.resource_name: combined}) == combined, (
        "합친 문면이 바뀌었다 — 심의 붙임 6 이 그것을 읽는다"
    )


def test_a_resource_with_no_allocation_gets_a_statement_not_a_blank() -> None:
    """★★ 못 찾은 배분은 **빈칸이 아니라 「—」**다 (R68/WP-2).

    ⚠ 이름으로 맞추므로 두 목록의 길이가 다를 수 있다(부하는 `dispatch_notes`
    에만 있다). 빈 문자열을 인쇄하면 표에서 「아직 안 적었다」와 구별되지 않는다
    — 이 모듈의 `NO_OPERATING_MODE` 와 같은 판단이다.
    """
    note = build_dispatch_notes([make_ess_tou()])[0]
    assert applied_allocation(note, {}) == NO_APPLIED_ALLOCATION
    assert applied_allocation(note, {note.resource_name: ""}) == NO_APPLIED_ALLOCATION
    assert NO_APPLIED_ALLOCATION, "빈 문면은 「진술」이 아니다"


# ── 세 갈래 가름과 사람용 이름 (R68/WP-3) ─────────────────────────────────────


def _hour(step: int, **values: float) -> DispatchHour:
    """스텝 하나 — 계통 두 칸은 이 검사가 재는 것이 아니라 0 으로 둔다."""
    return DispatchHour(
        step=step, per_resource=dict(values), grid_export=0.0, grid_import=0.0
    )


def test_the_third_way_is_the_leftover_not_a_new_rule() -> None:
    """★★★ **저장장치는 「둘 다 아닌 것」이다** — 새 규칙을 세우지 않았다.

    `split_by_direction()` 독스트링이 이미 적었다: *「충·방전을 함께 하는
    자원(ESS)은 어느 쪽도 아니므로 둘에서 다 빠진다」*. `split_three_ways()` 가
    하는 일은 그 나머지에 **이름을 주는 것**뿐이며, 가름이 두 곳에서 일어나면
    한쪽만 고쳐지는 날 두 자리가 서로 다른 「저장장치」를 본다.

    ⚠ **셋의 합집합이 전건**이어야 한다 — 어느 갈래에도 안 든 자원은 표에서
    조용히 사라진다.
    """
    hours = (
        _hour(0, pv=0.0, ess=-2.0, load=-5.0, idle=0.0),
        _hour(1, pv=3.0, ess=1.5, load=-4.0, idle=0.0),
    )
    generation, storage, load = split_three_ways(hours)
    by_direction = split_by_direction(hours)

    assert generation == ("pv",), f"발전 갈래가 다르다 — {generation}"
    assert load == ("load",), f"부하 갈래가 다르다 — {load}"
    assert (generation, load) == by_direction, (
        "두 함수가 같은 가름을 쓰지 않는다 — 규칙이 두 곳에 있다"
    )
    assert set(storage) == {"ess", "idle"}, (
        f"저장장치 갈래가 「둘 다 아닌 것」이 아니다 — {storage}"
    )
    assert set(generation) | set(storage) | set(load) == set(hours[0].per_resource), (
        "셋의 합집합이 자원 전건이 아니다 — 어느 갈래에도 안 든 자원이 있다"
    )


def test_a_charge_only_day_is_why_the_caller_picks_the_day() -> None:
    """★★★ **한 계절만 보면 저장장치가 「부하」로 떨어진다** — 그 함정을 붙든다.

    그 계절에 충전만 한 저장장치는 전 스텝이 0 이하이므로 **부하로 갈린다.** 그
    상태로 계절 표를 그리면 ESS 충전량이 총부하에 섞여 인쇄되고 **아무 예외도
    나지 않는다.** 그래서 부르는 쪽은 **연간등가 하루**로 한 번 가르고 그 가름을
    계절 전부에 쓴다(`core/report/verification_dispatch.py::season_step_tables`).
    이 검사는 그 사유가 실물이라는 것을 고정한다 — 사라지면 그 규약의 근거가
    함께 사라진다.
    """
    charge_only = (_hour(0, ess=-2.0), _hour(1, ess=-1.0))
    _generation, storage, load = split_three_ways(charge_only)
    assert storage == (), f"충전만 한 하루에서 저장장치가 갈렸다 — {storage}"
    assert load == ("ess",), (
        f"충전만 한 저장장치가 부하로 떨어지지 않았다 — {load}. 이 사실이 "
        "바뀌었다면 「연간등가 하루로 한 번 가른다」는 규약의 근거를 다시 써야 한다"
    )


def test_an_empty_day_splits_into_three_empty_ways() -> None:
    """스텝이 0 인 실행에서 **터지지 않는다** — 세 갈래가 모두 빈다."""
    assert split_three_ways(()) == ((), (), ())


def test_the_human_name_has_three_branches_and_none_is_a_blank() -> None:
    """★★★ **사람용 이름의 갈래 셋** — 대장에 있고 이름이 있으면 그 이름 · 대장에
    없으면 수요 · 대장에 있으나 이름이 비면 `None`.

    ⚠⚠ `None` 은 **빈칸이 아니라 진술**이다 — 「사람용 이름이 없다」이며 부르는
    쪽이 조인 키를 인쇄해야 한다. 여기서 키를 돌려주면 「이름이 「e2e-x」다」와
    「이름이 없다」가 구별되지 않는다.
    """
    kinds = {"e2e-pv": "태양광 (옥상 고정형)", "e2e-blank": ""}
    assert resource_display_name("e2e-pv", kinds) == "태양광 (옥상 고정형)"
    assert resource_display_name("e2e-load", kinds) == DEMAND_LABEL, (
        "대장에 없는 키가 수요로 적히지 않았다 — 가름은 「대장에 있는가」다"
    )
    assert resource_display_name("e2e-blank", kinds) is None, (
        "`kind` 가 빈 자원에 이름을 지어냈다"
    )
    assert DEMAND_LABEL and "수요" in DEMAND_LABEL, (
        f"수요 열의 이름이 「수요」라고 말하지 않는다 — {DEMAND_LABEL!r}"
    )
