"""PV 자원 검증 케이스 — WP-1a / spec §13.2.2(`RC-ALL-C1~C5`) · §13.2.3(`RC-PV-*`).

**이 파일은 구현보다 먼저 쓰였다** (NFR-105 — 테스트 우선).

오라클은 전부 §13.2 표의 **손계산 산식 원문**이며 각 테스트 docstring에 그대로
옮겨 적는다 (§13.2.1 「오라클 명시」). 기대값 숫자만 두면 그 숫자가 어디서 왔는지
나중에 재구성할 수 없고, 구현이 바뀌었을 때 *"오라클을 고칠 것인가 구현을 고칠
것인가"* 를 판정할 근거가 사라진다. 허용 오차는 물리량 상대오차 1e-9 · 에너지
수지 1e-6 kWh (NFR-102) · **금액은 원 단위 완전 일치** (NFR-103).
"""

from __future__ import annotations

import pytest

from core.contracts.der import DER, EOL_RETIRE, DispatchContext
from core.contracts.units import HOURS_PER_YEAR, Money, to_won, won_sum
from core.der.pv import PV, OperatingMode
from tests.contract.test_der_contract import DERContractTests

# §13.2.2 예시 열이 고정한 공통 재무 전제. 테스트마다 다시 적으면 한 곳만
# 고쳤을 때 오라클이 갈린다.
DISCOUNT_RATE = 0.045
ESCALATION_RATE = 0.02
HORIZON = 20

#: §13.2.2 `C-5` 오라클 — `4,500,000 × 5/25`. **취득분이 하나라는 전제**에서만
#: 성립한다(조항의 예시는 본체가 분석기간보다 오래 사는 경우만 다룬다). 분석기간
#: 안에서 부속설비를 **재취득**하면 그 취득분의 잔존가치가 더 붙으므로 이 수는
#: 총액이 아니라 **본체 몫**이 된다 — 아래 두 검사가 그 갈래를 나눠 붙든다.
#: 조항이 「어느 취득가인가」를 말하지 않는 것은 사람 몫이며 `status-human.md`
#: 7단계에 등재돼 있다.
RC_ALL_C5_BODY_ONLY_WON = Money(900_000)


def make_pv_1kw(**overrides: object) -> PV:
    """`RC-PV-P1`~`B3` 기준 자원 — 1kW · 이용률 15%. 다른 효과는 전부 끈다(§13.2.1)."""
    kwargs: dict = {
        "name": "검증용PV_1kW",
        "capacity_kw": 1.0,
        "capacity_factor": 0.15,
        "degradation_rate": 0.005,
        "lifetime": 25,
        "inverter_lifetime": 12,
        "escalation_rate": ESCALATION_RATE,
    }
    kwargs.update(overrides)
    return PV(**kwargs)  # type: ignore[arg-type]


def make_pv_3kw(**overrides: object) -> PV:
    """`RC-ALL-C1`~`C5` 기준 자원 — §13.2.2 예시 열 그대로.

    PV 3kW · 단가 150만원/kW · 할인율 4.5% · 물가 2% · 분석 20년.
    """
    kwargs: dict = {
        "name": "검증용PV_3kW",
        "capacity_kw": 3.0,
        "capacity_factor": 0.15,
        "degradation_rate": 0.005,
        "lifetime": 25,
        "inverter_lifetime": 12,
        "unit_capex_won_per_kw": 1_500_000,
        "fixed_om_won_per_year": 100_000,
        "variable_om_won_per_kwh": 5.0,
        "escalation_rate": ESCALATION_RATE,
    }
    kwargs.update(overrides)
    return PV(**kwargs)  # type: ignore[arg-type]


# ── 계약 준수 (FR-101) ───────────────────────────────────────────────

class TestPVContract(DERContractTests):
    """`DERContractTests` 를 **상속만으로** 통과시킨다 — 손으로 쓰면 빠진다(§13.0.3)."""

    def make(self) -> DER:
        return make_pv_1kw()


# ── 물리 (RC-PV-P1~P3) ───────────────────────────────────────────────

@pytest.mark.req("FR-102-AC1.PV")
def test_rc_pv_p1_annual_generation_from_capacity_factor() -> None:
    """`RC-PV-P1` 오라클(§13.2.3, 손계산): `1kW × 8760h × 0.15 = 1,314.0 kWh`."""
    pv = make_pv_1kw()
    assert pv.annual_generation_kwh(year=1) == pytest.approx(1314.0, rel=1e-9)


@pytest.mark.req("FR-102-AC1.PV")
def test_rc_pv_p1_dispatch_year_sum_matches_annual_generation() -> None:
    """8760 스텝 디스패치 합계 = 연간 발전량. 산식(`annual_generation_kwh()`)과
    시계열이 갈리면 편익은 시계열로, 검증은 산식으로 이뤄져 **둘 다 통과하면서
    서로 다른 값**을 쓰게 된다.
    """
    pv = make_pv_1kw()
    result = pv.dispatch(DispatchContext(steps=HOURS_PER_YEAR, dt=pv.dt, year=1))
    assert sum(result.electric) == pytest.approx(1314.0, rel=1e-9)


@pytest.mark.req("FR-102-AC1.PV")
def test_rc_pv_p1_accepts_8760_generation_profile() -> None:
    """FR-102-AC1.PV 는 이용률 **또는** 8760 발전 시계열을 입력으로 허용한다 —
    상수 0.15kWh/h 프로파일과 이용률 0.15 가 같은 연간 발전량을 준다.
    """
    pv = make_pv_1kw(capacity_factor=None, generation_profile_kwh=[0.15] * HOURS_PER_YEAR)
    assert pv.annual_generation_kwh(year=1) == pytest.approx(1314.0, rel=1e-9)


@pytest.mark.req("FR-104-AC1")
def test_rc_pv_p2_degraded_generation_over_20_years() -> None:
    """`RC-PV-P2` 열화 20년 누계 — 오라클(§13.2.3, 등비수열 합):
        `1,314 × (1 − 0.995²⁰) / 0.005` = 1,314 × 19.0779 = **25,068.4 kWh**

    연 0.5% 열화. 1년차에는 열화가 걸리지 않는다(지수 y−1) — 0-base로 쓰면 20년
    누계가 한 해분 적게 나오는데, 값이 그럴듯해서 눈으로는 잡히지 않는다.
    """
    pv = make_pv_1kw(degradation_rate=0.005)
    assert round(pv.cumulative_generation_kwh(horizon=HORIZON), 1) == 25068.4


@pytest.mark.req("FR-104-AC1")
def test_rc_pv_p2_first_year_is_not_degraded() -> None:
    """열화는 1년차 **다음**부터 걸린다 (FR-104-AC1)."""
    pv = make_pv_1kw(degradation_rate=0.005)
    assert pv.annual_generation_kwh(year=1) == pytest.approx(1314.0, rel=1e-9)
    assert pv.annual_generation_kwh(year=2) == pytest.approx(1314.0 * 0.995, rel=1e-9)
    assert pv.annual_generation_kwh(year=20) == pytest.approx(1314.0 * 0.995**19, rel=1e-9)


@pytest.mark.req("FR-101-AC4")
def test_rc_pv_p3_media_flags() -> None:
    """`RC-PV-P3` — `carries_electric=True`, 열·냉·연료 기여 0. 플래그가 거짓인
    매체에 실린 값은 어느 수지에도 잡히지 않고, NFR-102 균형 검사도 통과한다.
    """
    pv = make_pv_1kw()
    assert pv.carries_electric is True
    assert pv.carries_heat is False
    assert pv.carries_cool is False
    assert pv.consumes_fuel is False

    result = pv.dispatch(DispatchContext(steps=24, dt=pv.dt, year=1))
    assert all(v == 0.0 for v in result.heat)
    assert all(v == 0.0 for v in result.cool)
    assert all(v == 0.0 for v in result.fuel)
    assert sum(result.electric) > 0.0


@pytest.mark.req("FR-101-AC4")
def test_rc_pv_p3_generation_is_positive_sign() -> None:
    """부호 규약: 양수 = 내보냄. 자원마다 뒤집으면 합산이 조용히 상쇄된다."""
    pv = make_pv_1kw()
    result = pv.dispatch(DispatchContext(steps=24, dt=pv.dt, year=1))
    assert all(v >= 0.0 for v in result.electric)


# ── 편익 (RC-PV-B1~B3) ───────────────────────────────────────────────

@pytest.mark.req("FR-401-AC2.SelfConsumption")
def test_rc_pv_b1_self_consumption_saving() -> None:
    """`RC-PV-B1` 오라클(§13.2.3): `자가소비 kWh × 회피 단가` — 1,314 × 150 = **197,100원**."""
    pv = make_pv_1kw(self_consumption_ratio=1.0)
    benefit = pv.self_consumption_benefit(year=1, avoided_tariff_won_per_kwh=150.0)
    assert benefit == Money(197_100)
    assert isinstance(benefit, Money)


@pytest.mark.req("FR-401-AC2.SurplusSale")
def test_rc_pv_b2_surplus_sale_revenue() -> None:
    """`RC-PV-B2` 오라클(§13.2.3): `잉여 kWh × 판매단가` — 1,314 × 120 = **157,680원**."""
    pv = make_pv_1kw(self_consumption_ratio=0.0)
    assert pv.surplus_sale_revenue(year=1, sale_price_won_per_kwh=120.0) == Money(157_680)


@pytest.mark.req("FR-401-AC2.SurplusSale")
@pytest.mark.parametrize("ratio", [0.0, 0.3, 0.5, 1.0])
def test_rc_pv_b2_self_plus_surplus_equals_generation(ratio: float) -> None:
    """`RC-PV-B2` 항등식 — **자가소비분 + 잉여분 = 총발전량** (§13.2.3). 깨지면
    같은 kWh가 두 편익에 동시에 실리거나(FR-402 유형 A) 아무 편익에도 실리지
    않으며, 두 오류 모두 화면에 표시가 남지 않는다. 오차 기준 1e-6 kWh.
    """
    pv = make_pv_1kw(self_consumption_ratio=ratio)
    total = pv.annual_generation_kwh(year=1)
    parts = pv.self_consumption_kwh(year=1) + pv.surplus_kwh(year=1)
    assert abs(parts - total) < 1e-6


@pytest.mark.req("FR-401-AC2.REC")
def test_rc_pv_b3_rec_revenue() -> None:
    """`RC-PV-B3` 오라클(§13.2.3): `발전 MWh × 가중치 × REC 단가`.

    1,314 kWh = 1.314 MWh × 가중치 1.0 × 70,000원/MWh = **91,980원**
    """
    pv = make_pv_1kw()
    revenue = pv.rec_revenue(year=1, rec_price_won_per_mwh=70_000.0, rec_weight=1.0)
    assert revenue == Money(91_980)


@pytest.mark.req("FR-401-AC2.REC")
def test_rc_pv_b3_rec_weight_scales_linearly() -> None:
    """REC 가중치는 선형으로 곱해진다 — 건물형 1.5 가중치 예."""
    pv = make_pv_1kw()
    revenue = pv.rec_revenue(year=1, rec_price_won_per_mwh=70_000.0, rec_weight=1.5)
    assert revenue == Money(137_970)


# ── 공통 비용 5종 (RC-ALL-C1~C5) — §13.2.2 예시 열 ──────────────────

@pytest.mark.req("FR-101-AC5")
def test_rc_all_c1_capex() -> None:
    """`RC-ALL-C1` 오라클(§13.2.2): `단가 × 용량 + 부대비` → 1,500,000 × 3 =
    **4,500,000원**. 부가세는 별도 항목으로 분리한다. 초기 투자는 1년차에만
    계상한다 — 이후 연도에 다시 계상하면 20년 동안 25번 지은 사업이 된다.
    """
    pv = make_pv_3kw()
    assert pv.capex(year=1) == Money(4_500_000)
    assert pv.capex(year=2) == Money(0)


# ↓ v0.15 이관 — 이 검사가 보는 것은 메서드의 **존재**(AC2)가 아니라
# **산식**(§13.2.2 C-1~C-3)이다. AC5 가 없던 동안 AC2 를 빌려 인용했다.
@pytest.mark.req("FR-101-AC5")
def test_rc_all_c1_vat_is_a_separate_line() -> None:
    """부가세는 CAPEX 본체에 섞지 않는다 (§13.2.2 C-1) — 섞으면 프로포마에서
    세액을 분리 표시할 수 없고, 환급·면세 시나리오에서 본체 단가를 역산해야 한다.
    """
    pv = make_pv_3kw(vat_rate=0.10)
    assert pv.capex(year=1) == Money(4_500_000)
    assert pv.capex_vat(year=1) == Money(450_000)
    assert pv.capex_vat(year=2) == Money(0)


# ↓ v0.15 이관 — 이 검사가 보는 것은 메서드의 **존재**(AC2)가 아니라
# **산식**(§13.2.2 C-1~C-3)이다. AC5 가 없던 동안 AC2 를 빌려 인용했다.
@pytest.mark.req("FR-101-AC5")
def test_rc_all_c1_includes_balance_of_system_cost() -> None:
    """부대비는 CAPEX 본체에 더한다 (§13.2.2 C-1 산식의 `+ 부대비`)."""
    pv = make_pv_3kw(bos_capex_won=500_000)
    assert pv.capex(year=1) == Money(5_000_000)


@pytest.mark.req("FR-101-AC5")
def test_rc_all_c2_fixed_om_20_year_cumulative() -> None:
    """`RC-ALL-C2` 오라클(§13.2.2, 등비수열 합): `A × ((1+i)^n − 1) / i`.

    A=100,000, i=0.02, n=20 → **2,429,737원** (원 단위 완전 일치, NFR-103)
    """
    pv = make_pv_3kw(fixed_om_won_per_year=100_000, escalation_rate=0.02)
    assert pv.fixed_om_cumulative(horizon=HORIZON) == Money(2_429_737)


@pytest.mark.req("FR-101-AC5")
def test_rc_all_c2_year_by_year_sum_matches_closed_form() -> None:
    """연도별 합계 = 폐형식 누계, **원 단위 완전 일치** (NFR-103-M1). 프로포마는
    행별 값을 사람이 더해 보는 문서라, 어긋나면 화면상 정상으로 보이면서 근거가
    무너진다.
    """
    pv = make_pv_3kw(fixed_om_won_per_year=100_000, escalation_rate=0.02)
    year_by_year = won_sum(pv.fixed_om(year=y) for y in range(1, HORIZON + 1))
    assert year_by_year == pv.fixed_om_cumulative(horizon=HORIZON)
    assert pv.fixed_om(year=1) == Money(100_000)
    assert pv.fixed_om(year=2) == Money(102_000)


# ↓ v0.15 이관 — 이 검사가 보는 것은 메서드의 **존재**(AC2)가 아니라
# **산식**(§13.2.2 C-1~C-3)이다. AC5 가 없던 동안 AC2 를 빌려 인용했다.
@pytest.mark.req("FR-101-AC5")
def test_rc_all_c3_variable_om() -> None:
    """`RC-ALL-C3` 오라클(§13.2.2): 발전 1,314 kWh × 5원 = **6,570원/년**.

    산식은 `처리량 × 단가`이고 PV의 처리량은 **발전 kWh**다. (§13.2.2 예시 열
    머리는 3kW이나 C-3 수치 1,314 kWh는 1kW 발전량 — 정박점이 «발전량 × 단가»
    이므로 1kW 자원으로 재현한다.)
    """
    pv = make_pv_1kw(variable_om_won_per_kwh=5.0)
    assert pv.variable_om(year=1) == Money(6_570)


@pytest.mark.req("FR-101-AC5")
def test_rc_all_c3_follows_degradation() -> None:
    """변동 O&M은 열화된 발전량을 따라간다 (FR-104-AC1과 정합). 1년차 발전량으로
    20년을 고정하면 발전량과 변동비가 서로 다른 물리를 말한다. 물가 효과를 꺼서
    **열화만** 남긴다 (§13.2.1 단독성).
    """
    pv = make_pv_1kw(variable_om_won_per_kwh=5.0, escalation_rate=0.0)
    assert pv.variable_om(year=2) == to_won(1314.0 * 0.995 * 5.0)
    assert pv.variable_om(year=2) < pv.variable_om(year=1)


@pytest.mark.req("FR-101-AC5")
def test_rc_all_c3_applies_inflation_to_nominal_price() -> None:
    """변동 O&M 단가에도 물가가 걸린다 — 오라클 `1,314 × 0.995 × 5원 × 1.02`.

    §7.5는 금액을 **명목 원**으로 규정하고 §13.2.2 C-2는 고정 O&M에 물가 2%를
    적용한다. 변동 O&M만 실질로 두면 두 비용 항목이 서로 다른 화폐 단위를 말하고,
    20년 합계에서 항목 간 비중이 바뀐다.
    """
    pv = make_pv_1kw(variable_om_won_per_kwh=5.0, escalation_rate=0.02)
    assert pv.variable_om(year=2) == to_won(1314.0 * 0.995 * 5.0 * 1.02)


@pytest.mark.req("FR-104-AC4")
def test_rc_all_c4_inverter_replacement_at_year_13() -> None:
    """`RC-ALL-C4` 교체비 — 수명 도달 **다음 연도 초**에 계상 (§13.2.2).

    오라클: 인버터 12년 수명 → **13년차**. 본체(25년)는 20년 내 교체 없음.
    12년차에 계상하면 **아직 쓰고 있는 해**에 교체비가 들어가고, 그 한 해 차이는
    할인 때문에 회수기간을 바꾼다.
    """
    pv = make_pv_3kw(inverter_lifetime=12, lifetime=25)
    schedule = pv.replacement_schedule(horizon=HORIZON)
    assert set(schedule) == {13}
    assert schedule[13] > Money(0)


@pytest.mark.req("FR-104-AC4")
def test_rc_all_c4_body_replacement_excluded_from_20_year_horizon() -> None:
    """본체 25년 수명은 20년 분석기간 안에서 교체가 없다 (§13.2.2 C-4)."""
    pv = make_pv_3kw(lifetime=25, inverter_lifetime=12)
    assert 26 not in pv.replacement_schedule(horizon=HORIZON)
    assert 25 not in pv.replacement_schedule(horizon=HORIZON)


@pytest.mark.req("FR-104-AC4")
def test_rc_all_c4_body_replacement_appears_in_long_horizon() -> None:
    """20년만 보고 통과하면 «본체 수명을 아예 안 보는 구현»도 함께 통과한다."""
    pv = make_pv_3kw(lifetime=25, inverter_lifetime=12)
    schedule = pv.replacement_schedule(horizon=30)
    assert 26 in schedule, "본체 25년 수명 → 26년차 교체가 빠졌습니다"
    assert 13 in schedule and 25 in schedule


@pytest.mark.req("FR-104-AC4")
def test_rc_all_c4_sums_the_year_where_body_and_inverter_collide() -> None:
    """★ 같은 해에 본체와 인버터가 겹치면 **더한다** — 덮어쓰면 한쪽이 사라진다.

    R44 가 `replacement_schedule()` 을 `_acquisitions()` 에서 파생시키면서
    합산이 사전 갱신 한 줄로 옮겨졌다. 덮어쓰기로 바뀌어도 **연차 집합은 그대로**
    이므로 위 세 검사는 전부 초록불이고, 사라지는 쪽이 본체(금액이 큰 쪽)면
    결론은 **좋아지는 방향으로** 조용히 틀린다.

    오라클 — 손계산(물가 계수를 꺼서 명목 = 실질로 둔다):

        본체 10년 · 인버터 5년 · 3kW · 본체 150만원/kW · 인버터 30만원/kW
        인버터 교체  6 · 11 · 16년차   각  3 × 300,000 =   900,000원
        본체   교체       11년차       각 3 × 1,500,000 = 4,500,000원
        → {6: 900,000, 11: 5,400,000, 16: 900,000}

    ⚠ **붙들지 못하는 것**: 물가 계수를 껐으므로 *「겹친 해에 계수를 각각
    곱했는가」* 는 재지 않는다 — 그쪽은 `tests/casegrid/
    test_lifecycle_wiring.py` 의 실효 래칫이 갖는다.
    """
    pv = make_pv_3kw(
        lifetime=10,
        inverter_lifetime=5,
        inverter_unit_capex_won_per_kw=300_000,
        escalation_rate=0.0,
        replacement_escalation_rate=0.0,
    )
    assert pv.replacement_schedule(horizon=HORIZON) == {
        6: Money(900_000),
        11: Money(5_400_000),
        16: Money(900_000),
    }


@pytest.mark.req("FR-104-AC4")
def test_rc_all_c4_never_counts_the_first_year_acquisition_as_a_replacement() -> None:
    """★★ 1년차 최초 취득은 **CAPEX 이지 교체비가 아니다.**

    `_acquisitions()` 는 본체 최초 취득을 `{1: _gross_capex_won()}` 로 담는다 —
    잔존가치가 그 취득분을 세야 하기 때문이다. `replacement_schedule()` 이 거기서
    파생되므로(R44) **1년차를 거르지 않으면 초기투자가 교체비로 한 번 더
    계상되고**, 그 사업은 같은 설비를 두 번 사는 사업이 된다. 연차 하나가 느는
    것이라 연차 집합만 보는 검사로는 눈에 띄지 않는다.

    오라클 — 손계산(수명을 1년으로 눕혀 **2년차부터 매년** 교체가 걸리게 한다):

        3kW · 본체 150만원/kW · 인버터 22.5만원/kW(기본 15%) · 물가 0
        2 · 3년차  3 × 1,500,000 + 3 × 225,000 = 5,175,000원
        1년차      **없다** (초기투자 4,500,000원은 `capex()` 의 몫)
    """
    pv = make_pv_3kw(
        lifetime=1,
        inverter_lifetime=1,
        escalation_rate=0.0,
        replacement_escalation_rate=0.0,
    )
    assert pv.replacement_schedule(horizon=3) == {
        2: Money(5_175_000),
        3: Money(5_175_000),
    }


@pytest.mark.req("FR-104-AC5")
def test_rc_all_c5_salvage_value_at_horizon_end() -> None:
    """`RC-ALL-C5` — **본체 몫은 조항의 오라클 그대로**이고 재취득분이 더 붙는다.

    산식은 `취득가 × 잔존수명 / 총수명` 을 최종연도에 계상 후 할인이며,
    `salvage_value()` 는 그중 **할인 전 명목액**을 돌려준다. 할인율은 사업 단위
    전제(FR-701)이지 자원의 속성이 아니므로, 자원이 할인율을 알면 같은 자원이
    시나리오마다 다른 잔존가치를 갖는다.

    ## ⚠ 오라클이 움직였다 — 조항이 「어느 취득가」인지 말하지 않는다 (R39-E)

    조항의 예시 수 `4,500,000 × 5/25 = 900,000원` 은 **취득분이 하나**라는
    전제다(§13.2.2 `C-5` 는 본체가 분석기간보다 오래 사는 경우만 다룬다).
    20년 분석에서 이 자원은 **13년차에 인버터를 새로 사고**, 그 인버터는
    20년차에 4년치 수명이 남아 있다 — 그것을 세지 않으면 *새로 산 설비가
    통째로 사라진다.* `ESS._acquisitions()` 가 *「마지막 취득 시점부터 센다」*
    를 사유와 함께 이미 정본으로 세워 두었고 `PV` 가 따르지 않고 있었다.

    **그래서 두 항을 갈라 단언한다** — 조항의 수를 지우지 않고 남긴다:

        본체    4,500,000 × 5/25            = 900,000원   ← 조항 오라클 그대로
        인버터    856,063 × 4/12            = 285,354원   ← 13년차 재취득분
                                              ─────────
                                              1,185,354원

    인버터 취득가 856,063원은 `replacement_schedule()` 이 13년차에 계상하는
    금액과 **같은 수**여야 한다(두 곳이 갈리면 *교체비는 계상되는데 그 취득분의
    잔존가치는 안 세어지는* 상태가 조용히 생긴다). 그 일치는 여기서 단언하지
    않는다 — `tests/casegrid/test_lifecycle_wiring.py` 가 자원 전체를 돌며 잰다.

    ⚠ **조항 문면(spec `:1918`)은 고치지 않았다.** 「어느 취득가인가」의
    명문화는 §16.5 절차이며 `status-human.md` 7단계에 등재돼 있다.
    """
    pv = make_pv_3kw(lifetime=25)
    inverter_share = pv.salvage_value(year=HORIZON) - RC_ALL_C5_BODY_ONLY_WON

    assert pv.salvage_value(year=HORIZON) == Money(1_185_354)
    assert inverter_share == Money(285_354)
    # 13년차 재취득분이 잔존가치의 근거다 — 교체가 없으면 이 몫도 없다.
    assert set(pv.replacement_schedule(horizon=HORIZON)) == {13}


@pytest.mark.req("FR-104-AC5")
def test_rc_all_c5_discounted_salvage_value() -> None:
    """`RC-ALL-C5` 할인 후 잔존가치 — `1,185,354 / 1.045^20` = **491,499원**.

    ⚠ **조항의 예시 수는 `900,000 / 1.045^20 = 373,179원` 이다.** 갈린 이유는
    위 검사(`..._salvage_value_at_horizon_end`)가 갖는다 — **명목액이 움직였고
    할인은 그것을 따라온 것뿐**이다. 두 곳에 사유를 적지 않는다.

    이 검사가 붙드는 것은 **할인 그 자체**다: 명목액이 어떻게 바뀌든
    `명목 / (1+r)^year` 라는 관계가 유지되는지를 본다.
    """
    pv = make_pv_3kw(lifetime=25)
    discounted = pv.discounted_salvage_value(year=HORIZON, discount_rate=DISCOUNT_RATE)
    assert discounted == Money(491_499)
    # 할인 관계 자체 — 명목액이 다시 움직여도 이 단언은 그것을 따라간다.
    assert discounted == to_won(
        pv.salvage_value(year=HORIZON) / Money((1 + DISCOUNT_RATE) ** HORIZON)
    )


@pytest.mark.req("FR-104-AC5")
def test_rc_all_c5_zero_when_lifetime_exhausted() -> None:
    """수명을 다 쓴 **취득분**의 잔존가치는 0이다 — 음수가 되면 편익이 된다.

    ## ⚠ 「다 썼다」는 **재취득이 없을 때만** 자원 전체에 대해 성립한다 (R39-E2)

    종전 문면은 *「수명을 다 쓴 **자원**」* 이었고 25·30년차에 0을 기대했다.
    그 기대는 취득분이 하나라는 전제 위에 서 있었다 — 재취득이 있으면 25년차에
    **그 해에 새로 산 인버터**가 남아 있고, 30년차에는 26년차에 새로 산 본체가
    거의 새것이다. 0을 기대하는 것은 *산 것이 사라졌다고 적는 것*이다.

    ⚠ **`core/cba/salvage.py::salvage_value()` 의 「수명 종료 자원의 잔존가치는
    0」 과 갈리지 않는다.** 그 함수는 **취득분 하나**를 받고 그 문면 바로 위에서
    *「교체 시점이면 elapsed 가 0에 가깝게 리셋된다」* 를 이미 선언한다. 갈렸던
    것은 조항이 아니라 이 검사가 그 선언을 **자원 전체**로 읽은 것이다.

    **그래서 두 갈래를 갈라 잰다** — 원래 걱정(음수 금지)은 양쪽에 그대로 건다.
    """
    # ⓐ 재취득이 없는 구성 — 종전 오라클이 그대로 성립하는 자리다.
    retire_pv = make_pv_3kw(lifetime=25, end_of_life_action=EOL_RETIRE)
    assert retire_pv.replacement_schedule(horizon=30) == {}
    assert retire_pv.salvage_value(year=25) == Money(0)
    assert retire_pv.salvage_value(year=30) == Money(0)

    # ⓑ 재취득이 있는 구성 — 그 해에 산 설비가 남아 있다.
    #      25년차: 25년차 인버터 1,085,695 × 11/12                 =   995,220원
    #      30년차: 26년차 본체 7,382,727 × 20/25 + 인버터 × 6/12   = 6,449,029원
    pv = make_pv_3kw(lifetime=25)
    assert set(pv.replacement_schedule(horizon=30)) == {13, 25, 26}
    assert pv.salvage_value(year=25) == Money(995_220)
    assert pv.salvage_value(year=30) == Money(6_449_029)

    # ⓒ 이 검사의 원래 걱정 — 어느 해에도 음수가 되지 않는다(되면 편익이 된다).
    for year in range(1, 41):
        assert retire_pv.salvage_value(year=year) >= Money(0)
        assert pv.salvage_value(year=year) >= Money(0)


# ── 수명 도달 선택 — `retire` (FR-104-AC3) ────────────────────────────

@pytest.mark.req("FR-104-AC3")
def test_retire_default_is_replace_and_leaves_existing_behavior_unchanged() -> None:
    """단언 1 — 기본값은 `replace`. 아무것도 넘기지 않으면 지금까지와 결과가
    **똑같다**.

    `RC-ALL-C4` 오라클(§13.2.2)과 동일 — 인버터 12년 수명 → 13년차에 교체비가
    계상된다. 이 값이 여전히 나와야 `retire` 도입이 기존 동작을 건드리지
    않았다는 뜻이다.
    """
    pv = make_pv_3kw(inverter_lifetime=12, lifetime=25)
    assert pv.end_of_life_action == "replace"
    assert pv.retires_at_end_of_life() is False
    schedule = pv.replacement_schedule(horizon=HORIZON)
    assert set(schedule) == {13}
    assert schedule[13] > Money(0)


@pytest.mark.req("FR-104-AC3")
def test_retire_leaves_replacement_schedule_empty() -> None:
    """단언 2 — `retire` 면 `replacement_schedule()` 이 **빈다**.

    본체도 부속설비(인버터)도 사지 않는다 (`core/contracts/der.py` 「retire의
    의미」②). `RC-ALL-C4` 오라클이라면 13년차에 인버터 교체비가 계상돼야
    하지만(바로 위 테스트), `retire` 는 그 항목 자체가 없어야 한다.
    """
    pv = make_pv_3kw(inverter_lifetime=12, lifetime=25, end_of_life_action=EOL_RETIRE)
    assert pv.replacement_schedule(horizon=HORIZON) == {}


@pytest.mark.req("FR-104-AC3")
def test_retire_output_is_zero_after_first_end_of_life_year() -> None:
    """단언 3 — `retire` 면 **첫 수명 종료 다음 해부터 출력 0**.

    본체 25년 · 인버터 12년 → 먼저 끝나는 쪽은 인버터(12년) — 계약
    「retire의 의미」⑤: "출력은 `min(본체 수명, 부속설비 수명)` 이후 0".
    13년차부터(그리고 그 뒤로 계속) 발전이 전부 0이어야 한다 — 인버터
    없는 PV 는 계통에 못 싣는다.
    """
    pv = make_pv_1kw(inverter_lifetime=12, lifetime=25, end_of_life_action=EOL_RETIRE)
    for year in (13, 20):
        result = pv.dispatch(DispatchContext(steps=24, dt=pv.dt, year=year))
        assert all(v == 0.0 for v in result.electric), f"{year}년차 발전이 0이 아닙니다"


@pytest.mark.req("FR-104-AC3")
def test_retire_output_matches_replace_up_to_the_end_of_life_year() -> None:
    """단언 4 — `retire` 면 **수명 해까지는 출력이 `replace` 와 같다** — 너무
    일찍 끊지 않는다.

    12년차(첫 수명 종료 해 — 인버터 12년 수명의 마지막 정상 해)의 발전량은
    `retire` 와 `replace` 가 같아야 한다. 오라클: `1kW × 24h × 이용률 0.15 ×
    열화계수(0.995¹¹)` = **3.6 × 0.995¹¹ kWh** (`derate(year=12) =
    (1−0.005)^(12−1)`, §4 `FR-104-AC1`).
    """
    expected_kwh = 1.0 * 0.15 * (0.995**11) * 24
    retire_pv = make_pv_1kw(inverter_lifetime=12, lifetime=25, end_of_life_action=EOL_RETIRE)
    replace_pv = make_pv_1kw(inverter_lifetime=12, lifetime=25)

    retire_result = retire_pv.dispatch(DispatchContext(steps=24, dt=retire_pv.dt, year=12))
    replace_result = replace_pv.dispatch(DispatchContext(steps=24, dt=replace_pv.dt, year=12))

    assert sum(retire_result.electric) == pytest.approx(expected_kwh, rel=1e-9)
    assert sum(retire_result.electric) == pytest.approx(
        sum(replace_result.electric), rel=1e-9
    )


@pytest.mark.req("FR-104-AC3")
def test_retire_salvage_matches_the_body_only_oracle_and_diverges_from_replace() -> None:
    """`retire` 의 잔존가치는 **본체 몫뿐**이고, 그래서 `replace` 와 갈린다.

    ## 무엇이 확정이고 무엇이 미정인가

    **확정** — `retire` 는 *「다시 사지 않는다」* 이므로 `replacement_schedule()`
    이 비고(`FR-104-AC3`), 취득분은 최초 본체 하나다. 그러면 20년차 잔존가치는
    조항의 단일취득 오라클 `4,500,000 × 5/25` 와 **정확히 같다.** R39-E 가
    배선하며 이 갈래를 빠뜨려 *사지도 않은 인버터의 잔존가치*를 `retire` 자원에
    붙였고(1,185,354원) R39-E2 가 `PV._acquisitions()` 에서 닫았다.

    **미정 (사람 몫)** — 조항 `FR-104-AC3`(spec §414 ③)은 *「EOL 前에는 `retire`
    와 `replace` 의 잔존가치가 같다」* 고 적는데 **「어느 EOL 인가」를 말하지
    않는다.** 이 자원의 첫 EOL 은 **인버터 12년**이고 분석기간은 20년이므로,
    「본체 EOL(25년)」로 읽으면 20년차는 EOL 前이라 둘이 같아야 하고, 「첫
    EOL(12년)」로 읽으면 20년차는 이미 EOL 後라 갈리는 것이 맞다. **지금 구현은
    뒤쪽이다.**

    ## 그래서 이 검사는 「같음」이 아니라 **갈림을 부채로 고정한다**

    조항이 침묵하는 자리를 우리가 정해 통과시키지 않는다(*정박점을 우리가
    만들지 않는다*). 대신 **갈리는 크기와 그 출처를 못 박는다** — 차액은
    13년차 인버터 재취득분 하나이며 다른 어떤 것도 아니다. 조항이 개정되어
    「같아야 한다」로 정해지면 이 검사가 **빨간불이 되어 그 사실을 알린다.**
    등재 자리는 `status-human.md` 7단계다.

    ⚠ **`xfail` 을 쓰지 않았다.** `tests/der/` 는 DoD 8 검사
    (`tests/acceptance2/test_17_8_dod8.py`)가 `skip`·`xfail` 을 **금지**하는
    구획이다 — 「케이스가 있다」가 「실행·통과한다」와 같아야 하기 때문이다.
    """
    retire_pv = make_pv_3kw(lifetime=25, end_of_life_action=EOL_RETIRE)
    replace_pv = make_pv_3kw(lifetime=25)

    # 확정 — 재취득이 없으므로 조항의 단일취득 오라클 그대로다.
    assert retire_pv.replacement_schedule(horizon=HORIZON) == {}
    assert retire_pv.salvage_value(year=HORIZON) == RC_ALL_C5_BODY_ONLY_WON

    # 부채 래칫 — 갈리는 크기는 13년차 인버터 재취득분 **하나**다.
    divergence = replace_pv.salvage_value(year=HORIZON) - retire_pv.salvage_value(
        year=HORIZON
    )
    assert divergence == Money(285_354), (
        "`retire` 와 `replace` 의 잔존가치 차이가 13년차 인버터 재취득분과 "
        "다릅니다 — 조항 §414 ③ 의 「어느 EOL 인가」 판정이 내려졌다면 "
        "`status-human.md` 7단계를 보고 이 검사를 그 판정에 맞추십시오"
    )


# ── 운전 방법 (FR-105) ───────────────────────────────────────────────

@pytest.mark.req("FR-105-AC1", "FR-105-AC2")
def test_pv_declares_operating_modes() -> None:
    """자원 클래스가 운전 방법 목록을 **선언**한다 — 엔진이 들고 있으면 신규
    운전 방법 추가가 코어 수정이 된다 (FR-105-AC1·AC2 · NFR-201).
    """
    assert set(PV.OPERATING_MODES) == set(OperatingMode)
    assert make_pv_1kw().operating_mode in PV.OPERATING_MODES


@pytest.mark.req("FR-105-AC1")
def test_pv_rejects_unknown_operating_mode() -> None:
    """선언 목록 밖의 운전 방법은 거부한다 (DV-14)."""
    with pytest.raises(ValueError, match="운전 방법"):
        make_pv_1kw(operating_mode="야간 발전")


@pytest.mark.req("FR-105-AC1")
def test_full_export_mode_forces_zero_self_consumption() -> None:
    """운전 방법이 **발전량의 용도 배분**을 실제로 바꾼다 — 아무 것도 바꾸지
    않으면 FR-105는 선언만 있고 효과가 없는 조항이 된다.
    """
    pv = make_pv_1kw(operating_mode=OperatingMode.FULL_EXPORT, self_consumption_ratio=1.0)
    assert pv.self_consumption_kwh(year=1) == pytest.approx(0.0)
    assert pv.surplus_kwh(year=1) == pytest.approx(1314.0, rel=1e-9)


@pytest.mark.req("FR-105-AC1")
def test_curtailment_mode_respects_grid_limit() -> None:
    """출력제어 운전은 계통 연계 상한을 지킨다 — 무시하면 계통에 실릴 수 없는
    kWh가 편익으로 계상된다 (`DispatchContext.grid_limit_kw`).
    """
    pv = make_pv_1kw(capacity_factor=0.5, operating_mode=OperatingMode.CURTAILMENT)
    ctx = DispatchContext(steps=24, dt=pv.dt, year=1, grid_limit_kw=[0.2] * 24)
    result = pv.dispatch(ctx)
    assert all(v <= 0.2 + 1e-9 for v in result.electric)
    assert sum(result.electric) == pytest.approx(0.2 * 24, rel=1e-9)


@pytest.mark.req("FR-105-AC1")
def test_grid_limit_violation_is_an_error_outside_curtailment_mode() -> None:
    """출력제어를 **선언하지 않은** 자원이 상한을 넘으면 오류다 — 조용히 깎으면
    «수용»과 «미수용»이 같은 결과를 내어 FR-105 선택이 무의미해진다.
    """
    pv = make_pv_1kw(capacity_factor=0.5, operating_mode=OperatingMode.SELF_CONSUMPTION_FIRST)
    ctx = DispatchContext(steps=24, dt=pv.dt, year=1, grid_limit_kw=[0.2] * 24)
    with pytest.raises(ValueError, match="연계 용량"):
        pv.dispatch(ctx)


@pytest.mark.req("FR-105-AC3")
def test_same_type_instances_can_hold_different_modes() -> None:
    """같은 유형의 두 인스턴스가 서로 다른 운전 방법을 갖는다 (FR-105-AC3)."""
    a = make_pv_1kw(name="옥상PV", operating_mode=OperatingMode.SELF_CONSUMPTION_FIRST)
    b = make_pv_1kw(name="벽면BIPV", operating_mode=OperatingMode.FULL_EXPORT)
    assert a.operating_mode is not b.operating_mode


# ── 경계·위반 (RC-PV-X1) ────────────────────────────────────────────

@pytest.mark.req("FR-102-AC1.PV")
@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"capacity_kw": -1.0}, "용량"),
        ({"capacity_kw": 0.0}, "용량"),
        ({"capacity_factor": 1.5}, "이용률"),
        ({"capacity_factor": -0.1}, "이용률"),
        ({"degradation_rate": 1.0}, "degradation_rate"),
        ({"degradation_rate": -0.01}, "degradation_rate"),
        ({"lifetime": 0}, "lifetime"),
        ({"inverter_lifetime": 0}, "인버터"),
        ({"azimuth_deg": 400.0}, "방위"),
        ({"tilt_deg": 120.0}, "경사"),
        ({"self_consumption_ratio": 1.2}, "자가소비율"),
        ({"unit_capex_won_per_kw": -1}, "단가"),
        ({"variable_om_won_per_kwh": -1.0}, "변동"),
        ({"name": ""}, "이름"),
    ],
)
def test_rc_pv_x1_rejects_invalid_parameters(overrides: dict, match: str) -> None:
    """`RC-PV-X1` 경계·위반 — 범위 밖 입력은 **명확한 오류로 거부**한다.

    §13.2.1 「양·음성 쌍」. 조용히 절사하거나 기본값으로 대체하면 «음수 용량
    PV» 가 0원 비용으로 발전하는 사업이 만들어지고, 결과는 그럴듯하게 나온다.
    """
    with pytest.raises(ValueError, match=match):
        make_pv_1kw(**overrides)


@pytest.mark.req("FR-102-AC1.PV")
def test_rc_pv_x1_requires_exactly_one_generation_input() -> None:
    """이용률과 8760 시계열은 **둘 중 하나만** 준다 (FR-102-AC1.PV).

    둘 다 주면 어느 쪽이 이겼는지 알 수 없고, 둘 다 없으면 발전량 0인 PV가
    조용히 만들어진다.
    """
    with pytest.raises(ValueError, match="이용률"):
        make_pv_1kw(capacity_factor=None, generation_profile_kwh=None)
    with pytest.raises(ValueError, match="이용률"):
        make_pv_1kw(capacity_factor=0.15, generation_profile_kwh=[0.15] * HOURS_PER_YEAR)


@pytest.mark.req("FR-102-AC1.PV")
def test_rc_pv_x1_rejects_profile_with_wrong_length() -> None:
    """행수 불일치는 명확한 오류로 중단한다 — 조용히 자르면 어느 시각이
    어긋났는지 영영 모른다 (FR-301-AC3).
    """
    with pytest.raises(ValueError, match="행"):
        make_pv_1kw(capacity_factor=None, generation_profile_kwh=[0.15] * 8759)


@pytest.mark.req("FR-102-AC1.PV")
def test_rc_pv_x1_rejects_negative_generation_in_profile() -> None:
    """발전 시계열의 음수는 거부한다 — 부호 규약상 음수는 «소비»다."""
    profile = [0.15] * HOURS_PER_YEAR
    profile[0] = -1.0
    with pytest.raises(ValueError, match="음수"):
        make_pv_1kw(capacity_factor=None, generation_profile_kwh=profile)


@pytest.mark.req("FR-402-AC2.A")
def test_rc_pv_x1_rejects_double_counted_allocation() -> None:
    """`RC-PV-X1` 배타 위반 — 동일 kWh의 자가소비·판매 이중 계상은 거부한다.

    §13.2.3 `RC-PV-X1` (FR-402 유형 A). 총발전량을 넘는 배분은 **같은 화폐
    흐름을 두 번 세는 것**이며, 차단율 100%가 요구 수준이다.
    """
    pv = make_pv_1kw()
    total = pv.annual_generation_kwh(year=1)
    with pytest.raises(ValueError, match="이중 계상"):
        pv.check_allocation(year=1, self_consumption_kwh=total, surplus_kwh=total)
    # 합이 총발전량과 같으면 정상 — 동시 발생은 중복이 아니다 (FR-402-AC1)
    pv.check_allocation(year=1, self_consumption_kwh=total * 0.4, surplus_kwh=total * 0.6)


@pytest.mark.req("FR-102-AC1.PV")
def test_pv_tag_is_the_registry_literal() -> None:
    """`tag` 는 spec 조항 ID `FR-102-AC1.PV` 의 키와 **같은 리터럴**이다 —
    슬러그화하거나 대소문자를 바꾸면 NFR-106 레지스트리 순회가 헛돈다.
    """
    assert PV.tag == "PV"


@pytest.mark.req("FR-102-AC1.PV")
def test_pv_records_azimuth_and_tilt() -> None:
    """방위·경사는 FR-102-AC1.PV 가 요구하는 입력이다 — 보관하고 리포트에 낸다."""
    pv = make_pv_1kw(azimuth_deg=170.0, tilt_deg=25.0)
    assert pv.azimuth_deg == 170.0
    assert pv.tilt_deg == 25.0
