"""TOU 차익거래 편익 — FR-401-AC2.TouArbitrage · FR-402-AC2.E.

R48 판정 §4 가 비워 둔 자리다. `TOU_ARBITRAGE` 는 **계통에 파는 운전**인데
`SelfConsumption` 편익이 붙어 있었고, R48 이 그 오매핑을 떼면서 자리를 비웠다 —
그래서 `ESS.value_streams()` 가 그 모드에서 **빈 튜플**을 돌려주고
`ESS.tou_arbitrage_benefit()`(`RC-ESS-B1`)은 **호출자가 단위시험 하나뿐**이었다.

⚠ **`SurplusSale` 과의 관계는 R51/WP-5 가 유형 A 배타에서 수량 차감으로
바꿨다**(사용자 판정 §4) — 이 파일의 「더는 배타가 아니다」절이 그것을 잰다.

**오라클**: 순위 1 (해석해) — 곱 둘의 차이라 손계산으로 재현 가능하며,
`ESS.tou_arbitrage_benefit()` 과 **대조한다**(같은 산식이 두 자리에 있으므로
갈리지 못하게 붙드는 것이 이 파일의 몫이다). 배타 쪽은 순위 4
(§13.0.1 ④ — 검사가 실제로 붙드는가).
"""
from __future__ import annotations

import pytest

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.valuestream import ExclusionType, Payer
from core.der.ess import ESS, ESSOperatingMode
from core.valuestream import (
    CapacityPayment,
    NWAs,
    PeakShaving,
    SelfConsumption,
    SurplusSale,
    TouArbitrage,
)
from core.valuestream.exclusion_table import (
    DEFAULT_EXCLUSION_RULES,
    collect_exclusions,
    find_rule,
)
from core.valuestream.report import STATE_EXCLUDED, build_report

#: 운전 주체가 **사업자**인 편익 — R50 이 `TouArbitrage` 를 더해 **셋**이다.
#: 계통 급전 편익 둘과의 유형 `E` 쌍은 그래서 **2 × 3 = 6** 이다.
USER_OPERATED_TAGS = ("SelfConsumption", "PeakShaving", "TouArbitrage")
GRID_DISPATCH_TAGS = ("NWAs", "CP")


def _dispatch_electric(values: list[float]) -> DispatchResult:
    """electric 계열만 채운 DispatchResult. 다른 매체는 0."""
    zeros = [0.0] * len(values)
    return DispatchResult(
        electric=list(values), heat=list(zeros), cool=list(zeros), fuel=list(zeros)
    )


def _tou(**overrides: object) -> TouArbitrage:
    """`RC-ESS-P1` 기준 제원의 ESS 가 내는 연간 수량으로 세운 편익.

    수량을 `_p1_ess()` 와 같은 값으로 두는 이유는 아래
    `test_matches_the_resource_side_oracle_exactly` 가 두 자리를 대조하기
    때문이다 — 여기서 임의 값을 쓰면 그 대조가 성립하지 않는다.
    """
    params: dict[str, object] = {
        "discharge_kwh": 2_920.0,
        "charge_kwh": 2_920.0 / 0.9,
        "peak_price_won_per_kwh": 200.0,
        "offpeak_price_won_per_kwh": 80.0,
    }
    params.update(overrides)
    return TouArbitrage(**params)  # type: ignore[arg-type]


def _p1_ess(**overrides: object) -> ESS:
    """`RC-ESS-B1` 오라클과 같은 제원 — `tests/der/test_ess.py` 의 것과 같다."""
    params: dict[str, object] = {
        "name": "검증용ESS", "capacity_kwh": 10.0, "power_kw": 5.0, "rte_pct": 90.0,
        "soc_min_pct": 10.0, "soc_max_pct": 90.0, "cycle_life": 6000,
        "calendar_life": 20, "eol_soh_pct": 80.0, "cycles_per_year": 365.0,
    }
    params.update(overrides)
    return ESS(**params)  # type: ignore[arg-type]


def _user_operated(tag: str) -> SelfConsumption | PeakShaving | TouArbitrage:
    if tag == "SelfConsumption":
        return SelfConsumption(baseline_annual_bill_won=300, new_annual_bill_won=120)
    if tag == "PeakShaving":
        return PeakShaving(
            monthly_peak_reduction_kw=[1.0] * 12, demand_charge_won_per_kw_month=5_000
        )
    return _tou()


def _grid_dispatch(tag: str, *, enabled: bool = True) -> NWAs | CapacityPayment:
    if tag == "NWAs":
        return NWAs(contribution_price_won_per_kwh=50.0, enabled=enabled)
    return CapacityPayment(
        registered_capacity_kw=10.0,
        capacity_price_won_per_kw_month=6_000.0,
        enabled=enabled,
    )


# ── 산식 — FR-401-AC2.TouArbitrage ───────────────────────────────────────


@pytest.mark.req("FR-401-AC1", "FR-401-AC2.TouArbitrage")
def test_tou_arbitrage_is_discharge_revenue_minus_charge_cost() -> None:
    """편익 = **방전 kWh × 피크단가 − 충전 kWh × 경부하단가**.

    오라클: 순위 1 (해석해) — `RC-ESS-B1` 산식 원문과 같다.

        2,920 × 200 − 3,244.444… × 80 = 584,000 − 259,556 = **324,444원/년**

    259,556 은 259,555.55… 의 사사오입이다. 표시값 3,244.4 로 계산하면 259,552
    가 되어 4원 어긋난다 — **반올림은 금액 경계에서 단 한 번**(NFR-103)이라는
    규약이 여기서 결과를 가른다.
    """
    vs = _tou()
    dispatch = _dispatch_electric([0.0] * 4)

    value = vs.annual_value(dispatch, year=1)
    assert isinstance(value, Money)
    assert value == to_won(584_000) - to_won(2_920.0 / 0.9 * 80.0)
    assert value == 324_444


@pytest.mark.req("FR-401-AC2.TouArbitrage", "FR-302-AC2")
def test_matches_the_resource_side_oracle_exactly() -> None:
    """★★ **`ESS.tou_arbitrage_benefit()` 과 같은 수여야 한다.**

    같은 산식이 두 자리에 있다 — 자원 쪽 메서드는 `RC-ESS-B1` 오라클이고 이
    클래스는 프로포마 행이다. **`core.valuestream` 이 `core.der` 를 import 하면
    구획 경계를 넘으므로**(`NFR-208-AC1`) 한쪽이 다른 쪽을 부를 수 없고,
    `PeakShaving` ↔ `ESS.peak_shaving_benefit()` 이 이미 같은 관계다. 그러면
    **두 산식이 조용히 갈릴 수 있으며** 그것을 붙드는 것은 시험뿐이다.

    ⚠ 수량도 자원에서 읽어 넘긴다 — 손으로 적으면 자원의 연간량 산정이 바뀔 때
    이 대조가 **옛 수량 위에서** 통과한다.
    """
    ess = _p1_ess()
    resource_side = ess.tou_arbitrage_benefit(
        peak_price_won=200.0, offpeak_price_won=80.0, year=1
    )
    benefit_side = TouArbitrage(
        discharge_kwh=ess.annual_discharge_kwh(year=1),
        charge_kwh=ess.annual_charge_kwh(year=1),
        peak_price_won_per_kwh=200.0,
        offpeak_price_won_per_kwh=80.0,
    ).annual_value(_dispatch_electric([0.0] * 4), year=1)

    assert benefit_side == resource_side, (
        "편익 클래스와 자원 쪽 오라클이 갈렸습니다 — 같은 「충방전요금차이」 "
        f"산식인데 {benefit_side} ≠ {resource_side} 입니다 (RC-ESS-B1)"
    )


@pytest.mark.req("NFR-103-M1")
def test_rounds_each_term_before_adding_them() -> None:
    """★ **`won_sum` 이다 — `to_won(a - b)` 가 아니다** (`NFR-103-M1`).

    항별로 반올림한 뒤 더해야 프로포마의 행별 값과 총계가 맞는다. 두 방식이
    실제로 갈리는 수를 골라 못 박는다 — 갈리지 않는 수로 재면 이 검사는
    **무엇도 붙들지 않으면서 초록불**이다.

        항별 반올림   round(+0.5) + round(−0.4) = +1 + 0 = **1원**
        한 번에       round(0.5 − 0.4) = round(0.1) = **0원**
    """
    vs = TouArbitrage(
        discharge_kwh=1.0,
        charge_kwh=1.0,
        peak_price_won_per_kwh=0.5,
        offpeak_price_won_per_kwh=0.4,
    )

    assert vs.annual_value(_dispatch_electric([0.0]), year=1) == to_won(1)
    assert to_won(0.5 - 0.4) == to_won(0), (
        "이 검사가 갈리지 않는 수를 쓰고 있습니다 — 두 방식이 같은 값을 내면 "
        "규약을 붙들지 못합니다"
    )


@pytest.mark.req("FR-401-AC2.TouArbitrage")
def test_the_benefit_may_be_negative_and_is_not_clamped_to_zero() -> None:
    """★ **음수를 0으로 클램프하지 않는다.**

    충전 비용이 방전 수익을 넘으면 편익은 음수다. 클램프하면 「차익이 나지 않는
    요금 구조」가 「편익 0」으로 보이고, 검토자는 그 운전을 **손해 없는 선택**
    으로 읽는다 — 그 오독은 편익이 커진 쪽이 아니라 **손실이 사라진 쪽**으로
    틀리므로 필요 지원 규모를 과소 산정한다.
    """
    vs = TouArbitrage(
        discharge_kwh=100.0,
        charge_kwh=200.0,
        peak_price_won_per_kwh=100.0,
        offpeak_price_won_per_kwh=90.0,
    )

    assert vs.annual_value(_dispatch_electric([0.0]), year=1) == to_won(-8_000)


@pytest.mark.req("FR-401-AC2.TouArbitrage")
def test_formula_keeps_the_subtraction_visible() -> None:
    """산식에 **뺄셈이 남아야 한다** — 차액만 적으면 무엇에서 뺐는지 사라진다.

    ⚠ 비활성일 때도 산식은 나온다(`ValueStream.formula` 계약). 0원 옆에 빈
    산식이 놓이면 「계상하지 않았다」와 「계상했는데 0이다」가 같아 보인다.
    """
    dispatch = _dispatch_electric([0.0] * 4)
    assert _tou().formula(dispatch, year=1) == (
        "방전 2,920.00kWh × 피크단가 200원/kWh "  # noqa: RUF001
        "− 충전 3,244.44kWh × 경부하단가 80원/kWh"  # noqa: RUF001
    )

    off = _tou(enabled=False)
    assert off.annual_value(dispatch, year=1) == to_won(0)
    assert "방전" in off.formula(dispatch, year=1)


@pytest.mark.req("FR-401-AC2.TouArbitrage", "NFR-103-M1")
def test_quantities_come_from_the_constructor_not_from_the_window() -> None:
    """★★ **`scales_with_dispatch_window = False`** — 창을 읽지 않는다.

    `ESS.tou_arbitrage_benefit()` 이 이미 연간값을 쓰므로 창에서 다시 읽으면
    같은 수량에 자가 둘이 되고, 러너의 연간화가 365를 곱해 **365배**가 된다
    (R34 실측: 집합 PPA 502,605원/년 → 183,450,825원). 짐작이 틀리면 금액이
    크게 어긋나면서도 **아무 예외가 나지 않는다** — 그래서 선언을 함께 잰다.
    """
    vs = _tou()

    assert TouArbitrage.scales_with_dispatch_window is False
    assert vs.annual_value(_dispatch_electric([0.0] * 4), year=1) == vs.annual_value(
        _dispatch_electric([999.0] * 8_760), year=1
    )


@pytest.mark.req("FR-402-AC5")
def test_payer_is_the_operator_because_it_sells_to_the_grid() -> None:
    """지불 주체는 **사업자**다 — 계통·시장에 파는 편익이다.

    `SurplusSale`·`AggregatedPPA`·`DirectTrade` 가 같은 자리에 있다. 비우면
    활성화 시 `ValidationError`(DV-13)로 거부된다.
    """
    assert TouArbitrage.payer is Payer.OPERATOR
    assert _tou().effective_payer is Payer.OPERATOR


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("discharge_kwh", -1.0),
        ("charge_kwh", -1.0),
        ("peak_price_won_per_kwh", -1.0),
        ("offpeak_price_won_per_kwh", -1.0),
    ],
)
@pytest.mark.req("FR-401-AC2.TouArbitrage")
def test_negative_inputs_are_refused(field: str, value: float) -> None:
    """음수 단가·음수 수량을 **거부한다** (`nwa.py` 가 세운 규약).

    방전·충전은 둘 다 **크기**로 받는다 — 부호로 방향을 나르게 두면 산식의
    뺄셈과 부호가 겹쳐 이중 부정이 되고, 그때 금액은 **그럴듯한 양수**로 남는다.
    """
    with pytest.raises(ValueError, match="음수"):
        _tou(**{field: value})


# ── 더는 배타가 아니다 — 수량 차감으로 대신한다 (R51/WP-5 · 판정 §4) ────────


@pytest.mark.req("FR-402-AC2.A")
def test_surplus_sale_pair_is_no_longer_an_exclusion() -> None:
    """★★ `SurplusSale` 과는 **더는 배타가 아니다** — 수량에서 뺀다.

    R50 은 이 쌍을 유형 A(같은 kWh 가 두 항목에 각각 판매로 들어간다)로 막았다.
    사용자 판정 §4(`docs/decisions-2026-09-01-R51.md`)는 그것을 *「두 번 센
    것」*이 아니라 *「같은 전력이 길을 돌아간 것」*으로 다시 읽는다 — 답은
    「둘 중 하나를 끄라」가 아니라 **「잉여판매 수량에서 그 몫을 빼라」**다.
    차감은 `SurplusSale.non_pv_ess_discharge_kwh` 가 지고, 그 값을 계산해
    넘기는 것은 러너(`core/casegrid/e2e_runner.py`)다 — 이 파일은 편익 계약
    수준의 배타 여부만 본다(수량 차감 자체는
    `tests/valuestream/test_surplus_sale.py`·
    `tests/casegrid/test_surplus_sale_charge_source_deduction.py` 가 잰다).

    ⚠ **정당한 동시 운전을 지우지 않는다는 것까지 함께 본다** — 배타로 막으면
    ESS 는 `GRID` 충전으로 차익거래를 하고 PV 잉여는 따로 파는 구성이
    사라진다(판정 §4 의 요점).
    """
    assert find_rule("TouArbitrage", "SurplusSale") is None, (
        "TouArbitrage ↔ SurplusSale 배타 규칙이 아직 docs/exclusion-rules.yaml 에 "
        "있습니다 — R51/WP-5 가 뗐어야 합니다(판정 §4)"
    )

    report = build_report(
        [_tou(), SurplusSale(sale_price_won_per_kwh=120.0)],
        _dispatch_electric([10.0, 20.0]),
        year=1,
    )
    states = {line.tag: line.state for line in report.all_lines()}
    assert states["TouArbitrage"] != STATE_EXCLUDED
    assert states["SurplusSale"] != STATE_EXCLUDED


@pytest.mark.req("FR-402-AC1", "FR-402-AC2.E")
def test_it_is_not_exclusive_with_the_other_operator_run_benefits() -> None:
    """★★★ **`SelfConsumption`·`PeakShaving` 과는 배타가 아니다.**

    셋 다 **운전 주체가 사업자**이고 `ESS.mode_weights` 가 혼합 모드를 **명시로
    허용**한다(`tests/der/test_ess.py` 가 `TOU_ARBITRAGE 0.5 + PEAK_SHAVING 0.2`
    를 돌린다). 배타로 적으면 **정당한 동시 계상을 지운다** — `FR-402-AC1` 이
    명시로 금지한 방향이며, 겁내서 하나만 세면 **과대 지원**을 요구하게 된다.

    ⚠ **없음을 재는 검사다.** 규칙이 없다는 것만 보면 「아직 안 적었다」와
    「적지 않기로 했다」가 같아 보이므로, **실행 경로가 셋을 함께 계상하는
    것까지** 함께 고정한다.
    """
    assert find_rule("TouArbitrage", "SelfConsumption") is None
    assert find_rule("TouArbitrage", "PeakShaving") is None

    # ⚠ `SelfConsumption` ↔ `PeakShaving` 은 저장소가 이미 동시 계상으로 두고
    # 있으므로 셋을 한 번에 세울 수 있다 — 그것이 `FR-402-AC1` 의 예시다.
    streams = [_user_operated(t) for t in USER_OPERATED_TAGS]
    dispatch = _dispatch_electric([10.0, 20.0])

    report = build_report(streams, dispatch, year=1)
    states = {line.tag: line.state for line in report.all_lines()}

    for tag in USER_OPERATED_TAGS:
        assert states[tag] != STATE_EXCLUDED, (
            f"{tag} 가 배타제외됐습니다 — 사업자 운전 편익 셋은 동시에 성립하며 "
            "동시 발생하는 다중 효과는 중복이 아닙니다 (FR-402-AC1)"
        )
    assert report.total_accounted() > to_won(0)


# ── 배타 유형 E — 계통 급전 편익 (FR-402-AC2.E) ──────────────────────────


@pytest.mark.req("FR-402-AC2.E")
def test_both_grid_dispatch_pairs_are_declared_as_type_e() -> None:
    """★ 계통 급전 편익 **둘 다**와 유형 `E` 다 — 하나만 적으면 나머지가 열린다.

    방전 시점을 계통운영자가 정하면 사업자가 **피크 시각을 골라 팔 수 없다** —
    같은 kWh 를 두 번 파는 것(`A`)이 아니고 제도가 금지하는 것(`D`)도 아니다.

    ⚠ **`applies_to_profile` 이 비어 있어야 한다** — 제도가 바뀌어도 성립하지
    않으므로 제도 한정이 아니며, 프로파일을 달면 프로파일을 모르는 실행에서
    **규칙이 조용히 꺼진다**.
    """
    for grid_tag in GRID_DISPATCH_TAGS:
        rule = find_rule(grid_tag, "TouArbitrage")
        assert rule is not None, (
            f"{grid_tag} ↔ TouArbitrage 배타 규칙이 docs/exclusion-rules.yaml 에 "
            "없습니다 (FR-402-AC2.E)"
        )
        assert rule.exclusion_type is ExclusionType.E
        assert rule.applies_to_profile is None
        assert rule.applies_to_structure is None
        assert "방전" in rule.rationale


@pytest.mark.req("FR-402-AC2.E")
@pytest.mark.parametrize("grid_tag", GRID_DISPATCH_TAGS)
def test_type_e_pair_is_kept_out_of_accounting_on_the_execution_path(
    grid_tag: str,
) -> None:
    """★★ **실행 경로에서 잰다** — `build_report()` 를 지난다.

    이 저장소는 *「거부 기계는 있는데 배포 코드가 아무도 안 부른다」* 를 실물로
    겪었다(R26 · R17/WP-28B). 그래서 규칙표를 직접 읽는 것으로 끝내지 않는다.

    ⚠ **금액이 있는 상태로 재는 것이 요점이다.** 두 편익 다 0원이면 「배타로
    빠졌다」와 「원래 0이다」가 같아 보인다.
    """
    grid = _grid_dispatch(grid_tag)
    tou = _tou()
    dispatch = _dispatch_electric([10.0, 20.0])

    assert grid.annual_value(dispatch, year=1) > to_won(0)
    assert tou.annual_value(dispatch, year=1) > to_won(0)

    report = build_report([grid, tou], dispatch, year=1)
    states = {line.tag: line.state for line in report.all_lines()}

    assert states[grid_tag] == STATE_EXCLUDED
    assert states["TouArbitrage"] == STATE_EXCLUDED
    assert report.total_accounted() == to_won(0), (
        f"{grid_tag} ↔ TouArbitrage 는 동시에 성립할 수 없는 운전인데 계상 "
        "합계에 값이 남았습니다 (FR-402-AC2.E)"
    )


@pytest.mark.req("FR-402-AC2.E")
def test_the_operating_agent_axis_now_counts_six_pairs() -> None:
    """★★ **2 × 3 = 6쌍이다** — R48 은 「넷」이라 적었고 R50 이 셋째를 세웠다.

    하나라도 빠지면 그 조합만 조용히 열린 채 남고, 남은 조합은 아무 예외 없이
    그럴듯한 금액을 낸다 — R32 가 집합 PPA 에서 *「잉여판매만 막으면 자가소비와
    동시에 켤 수 있다」* 로 밟은 자리와 같다.

    ⚠ 쌍 목록을 손으로 적지 않고 **두 축의 곱**으로 만든다. 손으로 적으면
    하나가 빠져도 초록불이다.
    """
    expected = {
        frozenset((grid, user))
        for grid in GRID_DISPATCH_TAGS
        for user in USER_OPERATED_TAGS
    }
    assert len(expected) == 6

    table = {
        frozenset((r.benefit_a, r.benefit_b))
        for r in DEFAULT_EXCLUSION_RULES
        if r.exclusion_type is ExclusionType.E
    }
    assert table == expected, (
        "운전 주체 축의 유형 E 쌍이 여섯이 아닙니다 — 계통 급전 편익 둘 × "  # noqa: RUF001
        f"사업자 운전 편익 셋입니다. 표에 있는 것: {sorted(map(sorted, table))}"
    )


@pytest.mark.req("FR-402-AC2.E")
def test_type_e_does_not_fire_when_the_grid_dispatch_benefit_is_off() -> None:
    """**오탐 0 쪽도 함께 잰다** — 꺼져 있으면 배타가 발동하지 않는다.

    계통 급전 편익 둘은 **기본 비활성**이 정상 상태이므로, 여기서 잘못 걸리면
    아무것도 켜지 않은 기준 구성에서 TOU 차익거래가 지워진다.
    """
    streams = [_grid_dispatch("NWAs", enabled=False), _tou()]
    dispatch = _dispatch_electric([10.0, 20.0])

    assert collect_exclusions(streams) == []

    report = build_report(streams, dispatch, year=1)
    states = {line.tag: line.state for line in report.all_lines()}
    assert states["TouArbitrage"] != STATE_EXCLUDED
    assert report.total_accounted() > to_won(0)


# ── 운전 방법과의 연결 — FR-105-AC1 (자원 쪽은 tests/der/test_ess.py) ────


@pytest.mark.req("FR-105-AC1", "FR-401-AC2.TouArbitrage")
def test_the_resource_declares_this_tag_for_the_tou_arbitrage_mode() -> None:
    """★ **자원이 이 편익을 선언한다** — 그것이 R48 이 비워 둔 자리였다.

    선언과 클래스가 갈리면 「편익 항목은 있는데 아무 자원도 그것을 내지 않는다」
    또는 그 반대가 되고, 둘 다 리포트에서는 **0원 행**으로 같아 보인다.
    """
    tags = _p1_ess(operating_mode=ESSOperatingMode.TOU_ARBITRAGE).value_streams()
    assert "TouArbitrage" in tags
    assert TouArbitrage.tag == "TouArbitrage", (
        "선언한 tag 와 클래스의 tag 가 갈리면 자원의 선언이 아무 편익도 "
        "가리키지 않습니다 (FR-401-AC2.<키> 는 리터럴이다)"
    )
