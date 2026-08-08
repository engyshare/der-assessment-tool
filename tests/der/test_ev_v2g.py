"""`EV_V2G` 자원 검증 — 작업 6.3 / WP-1c.

spec §13.2.2(공통 비용 5종) · §13.2.3 EV_V2G 표(`RC-EV-P1~P3`·`B1`·`C6`·`X1`)
· §15.1 Q-8(V2G 방전 정산 제도 미확인 → 편익 기본 비활성).

**이 파일이 고정하려는 가장 중요한 사실은 「기본 상태에서 V2G는 순수 비용」**
이라는 것이다. 충전기 비용은 계상되고 방전 편익은 0이다. 그것이 오류로 보여도
오류가 아니라 제도 미비의 정직한 반영이므로(§15.1 Q-8 격상 사유 · 가정 A-11),
테스트로 못 박아 둔다. 못 박아 두지 않으면 "V2G인데 편익이 0이라니 버그다"
라는 선의의 수정이 존재하지 않는 제도 위에 편익을 얹는다.

오라클 출처는 케이스마다 docstring에 산식 원문으로 적는다 (§13.2.1 오라클 명시).
"""

from __future__ import annotations

import pytest

from core.contracts.der import DER, DispatchContext
from core.contracts.units import HOURS_PER_YEAR, Money, to_won, won_sum
from core.der.ev_v2g import EV_V2G
from tests.contract.test_der_contract import DERContractTests

DAYS_PER_YEAR = 365
HOUR = 3600

#: §13.2.3 EV_V2G 표가 전제한 제원. 오라클 18 kWh/일·6,570 kWh/년·6,044.4 kWh
#: 가 전부 이 값들에서 나오므로, 여기를 고치면 표와 어긋난다.
SPEC_KWARGS = {
    "name": "에너지자립가구 V2G",
    "vehicle_count": 2,
    "battery_kwh": 60.0,
    "max_charge_kw": 7.0,
    "max_discharge_kw": 7.0,
    "connect_start_hour": 18,
    "connect_end_hour": 8,
    "participation": 0.5,
    "available_dod": 0.3,
    "arrival_soc": 0.8,
    "min_departure_soc": 0.8,
    "discharge_efficiency": 0.92,
    "charge_efficiency": 0.92,
    "lifetime": 10,
    "degradation_rate": 0.0,
    "inflation_rate": 0.0,
    "charger_unit_cost_won": 3_000_000.0,
    "ancillary_cost_won": 500_000.0,
    "vat_rate": 0.10,
    "fixed_om_won_per_year": 100_000.0,
    "variable_om_won_per_kwh": 5.0,
    "degradation_compensation_won_per_kwh": 0.0,
}


def make_ev(**overrides) -> EV_V2G:
    """§13.2.3 표 제원의 EV_V2G. 케이스별 차이만 인자로 덮어쓴다."""
    return EV_V2G(**{**SPEC_KWARGS, **overrides})


def year_ctx(der: EV_V2G) -> DispatchContext:
    return DispatchContext(steps=HOURS_PER_YEAR, dt=der.dt, year=1)


# ── 계약 상속 (§13.0.3 L3) ───────────────────────────────────────────

class TestEVV2GContract(DERContractTests):
    """`DER` 계약 전건을 상속으로 검사한다.

    손으로 다시 쓰지 않는 이유는 계약 스위트 docstring에 있다 — 자원마다
    손으로 쓰면 반드시 빠진다.
    """

    def make(self) -> DER:
        return make_ev()


# ── 물리 (RC-EV-P1~P3) ───────────────────────────────────────────────

@pytest.mark.req("FR-102-AC1.EV_V2G")
def test_rc_ev_p1_available_discharge() -> None:
    """`RC-EV-P1` 가용 방전량.

    오라클(순위 1 — 해석해, spec §13.2.3 EV_V2G 표 원문):
        2대 × 60 kWh × 참여율 0.5 × 가용 DOD 0.3 = **18 kWh/일**
        18 × 365 = **6,570 kWh/년**  (배터리 방출 기준)
    """
    ev = make_ev()

    assert ev.daily_available_discharge_kwh(year=1) == pytest.approx(18.0, rel=1e-9)
    assert ev.annual_available_discharge_kwh(year=1) == pytest.approx(6570.0, rel=1e-9)


@pytest.mark.req("FR-102-AC1.EV_V2G")
def test_rc_ev_p1_dispatch_matches_available_discharge() -> None:
    """`RC-EV-P1` — 8760 디스패치 합계가 해석해와 일치한다.

    오라클: 계통 인도량 = 배터리 방출 6,570 × 방전효율 0.92 = **6,044.4 kWh**,
    계통 인출량 = 배터리 재충전 6,570 ÷ 충전효율 0.92 = **7,141.304348 kWh**.

    해석해만 검사하면 디스패치가 전혀 다른 값을 내도 통과한다 — 두 경로가
    같은 값을 낼 때에만 「가용량」이라는 말이 의미를 갖는다.
    """
    ev = make_ev()
    elec = ev.dispatch(year_ctx(ev)).electric

    discharged = sum(v for v in elec if v > 0)
    charged = sum(-v for v in elec if v < 0)

    assert discharged == pytest.approx(6044.4, rel=1e-9)
    assert discharged == pytest.approx(
        ev.annual_available_discharge_kwh(year=1) * 0.92, rel=1e-9
    )
    assert charged == pytest.approx(6570.0 / 0.92, rel=1e-9)


@pytest.mark.req("FR-102-AC1.EV_V2G")
def test_rc_ev_p2_outside_connection_window_is_exactly_zero() -> None:
    """`RC-EV-P2` 접속시간대 제약.

    오라클: 접속 시간대(18~08시) **밖** 스텝의 충·방전량이 **정확히 0**.
    근사 0(1e-12 따위)이 아니라 정확히 0이어야 한다 — 미세값을 허용하면
    "차가 없는 시각에 조금씩 방전"이 8,760번 누적되어도 눈에 띄지 않는다.
    """
    ev = make_ev()
    elec = ev.dispatch(year_ctx(ev)).electric

    outside = [i for i in range(HOURS_PER_YEAR) if 8 <= (i % 24) < 18]
    assert outside, "검사 대상 시각이 비어 있으면 이 테스트는 아무것도 보지 않는다"
    assert all(elec[i] == 0.0 for i in outside), (
        "접속 시간대 밖 스텝에 0이 아닌 충·방전량이 있습니다"
    )
    # 접속 시간대 안에서는 실제로 운전이 일어나야 한다 (전건 0이면 위 검사는 공허하다)
    assert any(elec[i] != 0.0 for i in range(HOURS_PER_YEAR) if i not in set(outside))


@pytest.mark.req("FR-102-AC1.EV_V2G")
def test_rc_ev_p3_minimum_departure_soc_every_day() -> None:
    """`RC-EV-P3` 최소 보장 SOC.

    오라클: 출발 시각(접속 종료 직전 스텝) SOC ≥ 보장값(0.8)을 **전 일자**에서
    만족. 하루라도 빠뜨리면 차주는 그날 출근을 못 한다 — 연평균으로 검사하면
    그 하루가 평균에 묻힌다.
    """
    ev = make_ev()
    ctx = year_ctx(ev)
    soc = ev.soc_profile(ctx)
    departures = ev.departure_steps(ctx)

    assert len(departures) == DAYS_PER_YEAR
    assert all((i % 24) == 7 for i in departures), "출발 직전 스텝은 07시다 (접속 18~08시)"
    for i in departures:
        assert soc[i] >= ev.min_departure_soc - 1e-12, (
            f"{i}번 스텝(출발 시각) SOC {soc[i]} < 보장값 {ev.min_departure_soc}"
        )
    # 방전이 실제로 일어났는지 — SOC가 내내 만충이면 위 검사는 공허하다
    assert min(soc) == pytest.approx(0.8 - 0.3, abs=1e-9)


@pytest.mark.req("FR-102-AC1.EV_V2G")
def test_rc_ev_p3_negative_guarantee_cannot_be_met() -> None:
    """`RC-EV-P3` 음성 쌍 — 보장 SOC를 지킬 수 없는 설정은 **거부**한다.

    도착 SOC 0.8인데 출발 보장 0.95를 요구하면 방전을 아예 하지 않아도
    지킬 수 없다. 조용히 0.8로 낮추면 리포트는 "보장 충족"으로 나온다.
    """
    with pytest.raises(ValueError, match="보장"):
        make_ev(min_departure_soc=0.95)


@pytest.mark.req("FR-102-AC1.EV_V2G")
def test_dod_deeper_than_arrival_soc_is_rejected() -> None:
    """가용 DOD가 도착 SOC보다 깊으면 SOC가 음수가 된다 — 거부한다."""
    with pytest.raises(ValueError, match="DOD"):
        make_ev(available_dod=0.9, arrival_soc=0.8, min_departure_soc=0.0)


@pytest.mark.req("FR-102-AC1.EV_V2G")
def test_media_flags_electric_only() -> None:
    """전기만 나른다. 열·냉·연료 플래그가 참이면 수지 분리가 무의미해진다."""
    ev = make_ev()
    assert ev.carries_electric is True
    assert (ev.carries_heat, ev.carries_cool, ev.consumes_fuel) == (False, False, False)
    assert ev.tag == "EV_V2G", "spec 조항 ID `FR-102-AC1.EV_V2G` 와 같은 리터럴이어야 한다"


# ── 운전 방법 (FR-105-AC1) ───────────────────────────────────────────

@pytest.mark.req("FR-105-AC1")
def test_operating_modes_declared() -> None:
    """운전 방법 3종을 자원 클래스가 **선언**한다 (FR-105-AC1 EV_V2G 행).

    spec 원문: *단방향 충전만 / 양방향(최소 SOC 보장) / 접속시간대 제한 운전*.
    """
    assert EV_V2G.supported_operating_modes() == (
        "단방향 충전만",
        "양방향(최소 SOC 보장)",
        "접속시간대 제한 운전",
    )
    assert make_ev().operating_mode == "양방향(최소 SOC 보장)"


@pytest.mark.req("FR-105-AC1")
def test_unknown_operating_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="운전 방법"):
        make_ev(operating_mode="아무거나")


@pytest.mark.req("FR-105-AC1")
def test_unidirectional_mode_never_discharges() -> None:
    """`단방향 충전만` 은 방전하지 않는다.

    양방향과 같은 시계열을 내면 운전 방법 선택이 리포트에만 남고 계산에는
    반영되지 않는다 — FR-105가 막으려는 것이 그것이다.
    """
    ev = make_ev(operating_mode="단방향 충전만", daily_charge_kwh=10.0)
    elec = ev.dispatch(year_ctx(ev)).electric

    assert all(v <= 0.0 for v in elec), "단방향 모드에 방전(양수)이 있습니다"
    assert sum(-v for v in elec if v < 0) == pytest.approx(10.0 * DAYS_PER_YEAR, rel=1e-9)
    assert ev.annual_available_discharge_kwh(year=1) == 0.0
    assert ev.v2g_discharge_benefit(year=1) == Money(0)


@pytest.mark.req("FR-105-AC1")
def test_window_limited_mode_requires_a_real_window() -> None:
    """`접속시간대 제한 운전` 인데 24시간 접속이면 제한이 없다 — 거부한다."""
    with pytest.raises(ValueError, match="접속"):
        make_ev(
            operating_mode="접속시간대 제한 운전",
            connect_start_hour=0,
            connect_end_hour=0,
        )


# ── 편익 (RC-EV-B1) — 기본 비활성이 핵심이다 ─────────────────────────

@pytest.mark.req("FR-404-AC1")
@pytest.mark.req("FR-102-AC1.EV_V2G")
def test_rc_ev_b1_discharge_benefit_is_zero_by_default() -> None:
    """`RC-EV-B1` **기본 비활성**. spec §15.1 Q-8 · `docs/assumptions.yaml`
    `benefit.v2g_discharge` (track: default0, value: 0).

    회피단가를 넣어 두어도 활성화 전에는 0이다. 단가가 있으면 자동으로
    켜지게 두면, 단가를 참고삼아 입력한 사용자가 존재하지 않는 제도의
    편익을 받게 된다.
    """
    ev = make_ev(avoided_price_won_per_kwh=150.0)

    assert ev.discharge_benefit_enabled is False
    assert ev.v2g_discharge_benefit(year=1) == Money(0)
    assert isinstance(ev.v2g_discharge_benefit(year=1), Money)
    assert ev.policy_warnings() == [], "비활성 상태에서는 경고할 것이 없다"


@pytest.mark.req("FR-404-AC1")
@pytest.mark.req("FR-102-AC1.EV_V2G")
def test_default_state_is_pure_cost_and_that_is_not_a_bug() -> None:
    """기본 상태의 V2G = **비용만 있고 편익은 0**.

    §15.1 Q-8: *"충전기 비용은 계상되고 편익은 0이므로 현 결과는 V2G에 대해
    보수적이다."* 이 상태를 고정해 두지 않으면 누군가가 "편익 0은 버그"라며
    추정단가를 넣는다 — 가정 A-11이 금지하는 바로 그 행동이다.
    """
    ev = make_ev()

    assert ev.capex(year=1) > Money(0), "충전기 비용은 정상 계상된다"
    assert ev.fixed_om(year=1) > Money(0)
    assert ev.v2g_discharge_benefit(year=1) == Money(0)


@pytest.mark.req("FR-404-AC1")
def test_enabling_discharge_benefit_warns_policy_assumption() -> None:
    """`RC-EV-B1` 활성화 시 **"제도 미확인 — 정책 가정 편익" 경고** (FR-404-AC1).

    경고 없이 켜지면 리포트를 받은 쪽은 이 편익이 확인된 제도 위에 있는지
    가정 위에 있는지 구분할 수 없다.
    """
    with pytest.warns(UserWarning, match="제도 미확인"):
        ev = make_ev(discharge_benefit_enabled=True, avoided_price_won_per_kwh=150.0)

    assert any("제도 미확인" in w for w in ev.policy_warnings())


@pytest.mark.req("FR-404-AC1")
@pytest.mark.req("FR-102-AC1.EV_V2G")
def test_rc_ev_b1_discharge_benefit_when_enabled() -> None:
    """`RC-EV-B1` V2G 방전 편익 — **활성화한 경우에만**.

    오라클(순위 1 — 해석해, spec §13.2.3 원문):
        방전 kWh × 방전효율 × 회피단가
        = 6,570 × 0.92 × 150 = 6,044.4 × 150 = **906,660원/년**
    """
    with pytest.warns(UserWarning):
        ev = make_ev(discharge_benefit_enabled=True, avoided_price_won_per_kwh=150.0)

    value = ev.v2g_discharge_benefit(year=1)
    assert value == Money(906_660)
    assert isinstance(value, Money)


# ── 비용 (RC-EV-C6) ──────────────────────────────────────────────────

@pytest.mark.req("FR-104-AC2")
@pytest.mark.req("FR-102-AC1.EV_V2G")
def test_rc_ev_c6_degradation_compensation_is_a_cost_not_a_benefit_offset() -> None:
    """`RC-EV-C6` 열화 보상 비용.

    오라클: 방전 kWh × 열화 보상단가 = 6,570 × 30 = **197,100원/년**.
    변동 O&M 6,570 × 5 = 32,850원과 **별도 행**으로 표시하고, 합계
    229,950원이 `variable_om()` 으로 엔진에 전달된다.

    **편익과 상계하지 않는다.** 상계하면 순편익은 같아 보이지만 "얼마를 벌고
    얼마를 물어 주는가"가 사라진다 — 차주 보상액은 사업 구조 협의의 대상이므로
    금액이 보여야 한다 (도메인 원칙 2-3 관점 분리).
    """
    with pytest.warns(UserWarning):
        ev = make_ev(
            degradation_compensation_won_per_kwh=30.0,
            discharge_benefit_enabled=True,
            avoided_price_won_per_kwh=150.0,
        )

    breakdown = ev.cost_breakdown(year=1)
    assert breakdown["충전기 변동 O&M"] == Money(32_850)
    assert breakdown["V2G 배터리 열화 보상"] == Money(197_100)

    # 엔진은 계약 6종만 본다. 별도 행에만 두면 이 비용은 조용히 사라진다.
    assert ev.variable_om(year=1) == Money(229_950)
    assert ev.variable_om(year=1) == won_sum(breakdown.values())

    # 편익은 보상비만큼 깎이지 않는다
    assert ev.v2g_discharge_benefit(year=1) == Money(906_660)


@pytest.mark.req("FR-104-AC2")
def test_degradation_compensation_zero_when_rate_zero() -> None:
    """Q-8b도 `track: default0` 이다 — 단가 0이면 보상비도 0이다."""
    ev = make_ev()
    assert ev.cost_breakdown(year=1)["V2G 배터리 열화 보상"] == Money(0)


# ── 경계 (RC-EV-X1) ──────────────────────────────────────────────────

@pytest.mark.req("FR-102-AC1.EV_V2G")
def test_rc_ev_x1_zero_participation() -> None:
    """`RC-EV-X1` 참여율 0.

    오라클: 참여율 0에서 **운전에서 파생되는** 편익·비용이 모두 0이고
    오류 없이 정상 종료한다. 0으로 나누기(참여 차량 0대로 SOC 계산)가
    숨어 있기 쉬운 자리다.

    **CAPEX·고정 O&M은 0이 아니다** — 충전기는 이미 설치되어 있고 아무도
    참여하지 않는다고 사라지지 않는다. 이것까지 0으로 만들면 "참여율 0이면
    손해도 0"이라는 잘못된 결론이 나온다.
    """
    with pytest.warns(UserWarning):
        ev = make_ev(
            participation=0.0,
            degradation_compensation_won_per_kwh=30.0,
            discharge_benefit_enabled=True,
            avoided_price_won_per_kwh=150.0,
        )

    ctx = year_ctx(ev)
    result = ev.dispatch(ctx)
    assert all(v == 0.0 for v in result.electric)
    assert ev.annual_available_discharge_kwh(year=1) == 0.0
    assert ev.v2g_discharge_benefit(year=1) == Money(0)
    assert ev.variable_om(year=1) == Money(0)
    assert ev.cost_breakdown(year=1)["V2G 배터리 열화 보상"] == Money(0)
    # SOC 계산이 0으로 나누기로 죽지 않는다
    assert len(ev.soc_profile(ctx)) == HOURS_PER_YEAR

    assert ev.capex(year=1) > Money(0)
    assert ev.fixed_om(year=1) > Money(0)


@pytest.mark.req("FR-102-AC1.EV_V2G")
def test_negative_or_impossible_parameters_are_rejected() -> None:
    """음성 쌍 — 물리적으로 불가능한 입력은 거부된다 (§13.2.1 양·음성 쌍)."""
    with pytest.raises(ValueError):
        make_ev(vehicle_count=0)
    with pytest.raises(ValueError):
        make_ev(battery_kwh=-60.0)
    with pytest.raises(ValueError):
        make_ev(participation=1.5)
    with pytest.raises(ValueError):
        make_ev(discharge_efficiency=0.0)
    with pytest.raises(ValueError):
        make_ev(connect_start_hour=24)
    with pytest.raises(ValueError):
        make_ev(charger_unit_cost_won=-1.0)


@pytest.mark.req("FR-102-AC1.EV_V2G")
def test_charger_power_too_small_for_the_window_is_rejected() -> None:
    """접속 시간대 안에 방전+재충전이 들어가지 못하면 거부한다.

    조용히 재충전을 덜 하면 출발 SOC 보장이 깨지고, 조용히 방전을 줄이면
    편익이 소리 없이 작아진다. 둘 다 화면상 정상으로 보인다.
    """
    with pytest.raises(ValueError, match="접속 시간대"):
        make_ev(max_charge_kw=0.5, max_discharge_kw=0.5)


# ── 공통 비용 5종 (RC-ALL-C1~C5, spec §13.2.2) ───────────────────────

@pytest.mark.req("FR-101-AC2")
@pytest.mark.req("FR-102-AC1.EV_V2G")
def test_rc_all_c1_capex_with_vat_separated() -> None:
    """`RC-ALL-C1` CAPEX.

    오라클: `단가 × 대수 + 부대비`, **부가세는 별도 항목으로 분리**.
        3,000,000 × 2 + 500,000 = **6,500,000원** (세전)
        부가세 10% = **650,000원** (분리 표시)
    초기 투자는 1년차에만 발생한다.
    """
    ev = make_ev()

    assert ev.capex(year=1) == Money(6_500_000)
    assert ev.capex_vat(year=1) == Money(650_000)
    assert ev.capex(year=2) == Money(0)
    assert ev.capex_vat(year=2) == Money(0)


@pytest.mark.req("FR-101-AC2")
@pytest.mark.req("FR-102-AC1.EV_V2G")
def test_rc_all_c2_fixed_om_20yr_geometric_sum() -> None:
    """`RC-ALL-C2` 고정 O&M 20년 누계.

    오라클(순위 1 — 해석해): 등비수열 합 `A × ((1+i)^n − 1) / i`
        A = 100,000, i = 0.02, n = 20 → **2,429,737원**

    누계를 `won_sum` 으로 내는 이유는 NFR-103-M1 이다 — 항별로 반올림한 뒤
    더해야 프로포마의 행별 값과 총계가 눈으로 더해도 맞는다.
    """
    ev = make_ev(inflation_rate=0.02, fixed_om_won_per_year=100_000.0)

    assert ev.fixed_om(year=1) == Money(100_000)
    total = won_sum(ev.fixed_om(year=y) for y in range(1, 21))
    assert total == Money(2_429_737)

    # 해석해와 **원 단위 완전 일치**여야 한다 (§13.2.1 허용 오차 — 금액은
    # 상대오차가 아니라 원 단위 일치다). 항별 반올림 후 합계이므로 해석해
    # 자체(2,429,736.98원)와는 0.02원 차이가 나지만, 원 단위로 맞춘 값은 같다.
    closed_form = 100_000 * ((1 + 0.02) ** 20 - 1) / 0.02
    assert total == to_won(closed_form)


@pytest.mark.req("FR-101-AC2")
@pytest.mark.req("FR-102-AC1.EV_V2G")
def test_rc_all_c3_variable_om_by_throughput() -> None:
    """`RC-ALL-C3` 변동 O&M.

    오라클: `처리량 × 단가`. EV_V2G의 처리량은 **연간 배터리 방전 kWh**다
    (PV는 발전 kWh, ESS는 처리 kWh — §13.2.2 표).
        6,570 kWh × 5원 = **32,850원/년**
    """
    ev = make_ev()

    assert ev.variable_om(year=1) == Money(32_850)
    assert ev.throughput_kwh(year=1) == pytest.approx(6570.0, rel=1e-9)


@pytest.mark.req("FR-104-AC4")
@pytest.mark.req("FR-104-AC3")
def test_rc_all_c4_replacement_at_year_after_lifetime() -> None:
    """`RC-ALL-C4` 교체비 — 수명 도달 **다음 연도 초**에 계상.

    오라클: 충전기 수명 10년 → **11년차**에 교체비. 물가 2% 적용 시
        3,000,000 × 2 × 1.02^10 = 7,313,966.52 → **7,313,967원**
    부대비(전기 인입·설치 공사)는 교체 시 재발생하지 않으므로 제외한다.
    """
    ev = make_ev(inflation_rate=0.02, lifetime=10)
    schedule = ev.replacement_schedule(horizon=20)

    assert list(schedule) == [11], "수명 10년이면 11년차 한 번만 교체된다 (20년 분석)"
    assert schedule[11] == Money(7_313_967)

    # 분석기간 안에 수명이 도달하지 않으면 교체는 없다
    assert make_ev(lifetime=25).replacement_schedule(horizon=20) == {}


@pytest.mark.req("FR-104-AC5")
def test_rc_all_c5_salvage_value_and_discount() -> None:
    """`RC-ALL-C5` 잔존가치.

    오라클(§13.2.2 C-5 예시를 EV_V2G 파라미터로 재현):
        취득가 1,500,000 × 3대 = 4,500,000원, 총수명 25년, 20년 분석
        4,500,000 × 5/25 = **900,000원** (최종연도 계상)
        900,000 / 1.045^20 = **373,179원** (할인 후)
    """
    ev = make_ev(
        vehicle_count=3,
        charger_unit_cost_won=1_500_000.0,
        ancillary_cost_won=0.0,
        lifetime=25,
    )

    assert ev.salvage_value(year=20) == Money(900_000)
    assert ev.discounted_salvage_value(year=20, discount_rate=0.045) == Money(373_179)
    # 수명을 다 쓴 시점에는 잔존가치가 없다
    assert ev.salvage_value(year=25) == Money(0)


@pytest.mark.req("FR-104-AC1")
def test_degradation_reduces_discharge_over_years() -> None:
    """열화율이 연차별 방전량을 줄인다 (FR-104 성능 저하 · 도메인 원칙 4-4).

    오라클: n년차 가용 방전량 = 18 × (1 − d)^(n−1).
    d = 0.02, n = 11 → 18 × 0.98^10 = 14.7167... kWh/일
    """
    ev = make_ev(degradation_rate=0.02)

    assert ev.daily_available_discharge_kwh(year=1) == pytest.approx(18.0, rel=1e-9)
    assert ev.daily_available_discharge_kwh(year=11) == pytest.approx(
        18.0 * 0.98**10, rel=1e-9
    )


@pytest.mark.req("FR-101-AC2")
def test_money_methods_are_whole_won() -> None:
    """금액 반환 전건이 정수 원 `Money` 다 (NFR-103).

    계약 스위트가 4종을 보지만, EV_V2G가 추가로 내는 금액(부가세·열화 보상·
    편익·할인 잔존가치)도 같은 규약 아래 있어야 한다 — 한 곳이라도 float면
    그 경로에서 반올림이 다시 일어난다.
    """
    with pytest.warns(UserWarning):
        ev = make_ev(
            degradation_compensation_won_per_kwh=30.0,
            discharge_benefit_enabled=True,
            avoided_price_won_per_kwh=150.0,
        )

    values = [
        ev.capex_vat(year=1),
        ev.v2g_discharge_benefit(year=1),
        ev.discounted_salvage_value(year=20, discount_rate=0.045),
        *ev.cost_breakdown(year=1).values(),
    ]
    for v in values:
        assert isinstance(v, Money)
        assert v == v.to_integral_value()


@pytest.mark.req("FR-301-AC3")
def test_grid_limit_series_is_respected() -> None:
    """계통 연계 상한이 주어지면 스텝당 인도량이 그 값을 넘지 않는다.

    상한을 무시하면 물리적으로 불가능한 편익이 계상된다. 상한 때문에
    재충전이 끝나지 않으면 **오류로 중단**한다 — 조용히 SOC 보장을 깨뜨리는
    쪽이 훨씬 나쁘다.
    """
    ev = make_ev()
    limit = [3.0] * HOURS_PER_YEAR
    ctx = DispatchContext(steps=HOURS_PER_YEAR, dt=ev.dt, year=1, grid_limit_kw=limit)

    elec = ev.dispatch(ctx).electric
    assert max(abs(v) for v in elec) <= 3.0 + 1e-12
    # 상한이 걸려도 하루 방전 총량은 시간대 안에서 여전히 소화된다
    assert sum(v for v in elec if v > 0) == pytest.approx(6044.4, rel=1e-9)
