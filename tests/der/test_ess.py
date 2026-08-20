"""ESS 자원 검증 케이스 — WP-1b / spec §13.2.3 `RC-ESS-*` + §13.2.2 `RC-ALL-C1~C5`.

**이 파일은 구현보다 먼저 쓰였다** (NFR-105). 오라클은 전부 §13.2 표의 손계산
(§13.0.2 순위 2)이며 **산식 원문**을 각 docstring 에 옮겨 적는다 (§13.2.1).
허용 오차: 물리량 1e-9 / 에너지 수지 1e-6 kWh (NFR-102) / **금액은 원 단위 완전
일치** — 오라클도 `to_won()` 과 같은 사사오입을 쓴다 (NFR-103).
"""

from __future__ import annotations

import pytest

from core.contracts.der import DER, DispatchContext
from core.contracts.units import ENERGY_TOLERANCE_KWH, Money, to_won, won_sum
from core.contracts.validation import ValidationError
from core.der.ess import ESS, ESSOperatingMode
from core.incentive.calculator import build_capex_cashflows
from core.incentive.schemas import IncentiveScheme
from tests.contract.test_der_contract import DERContractTests


def _p1_ess(**overrides) -> ESS:
    """`RC-ESS-P1` 기준 제원. 팩토리로 두는 것은 §13.2.1 「단독성」때문이다 —
    상수를 공유하면 한 케이스의 파라미터 변경이 다른 케이스의 오라클을 무너뜨린다."""
    params = {
        "name": "검증용ESS", "capacity_kwh": 10.0, "power_kw": 5.0, "rte_pct": 90.0,
        "soc_min_pct": 10.0, "soc_max_pct": 90.0, "cycle_life": 6000,
        "calendar_life": 20, "eol_soh_pct": 80.0, "cycles_per_year": 365.0,
    }
    params.update(overrides)
    return ESS(**params)


def _prefunded_scheme(program: str = "사용후배터리 실증 지원사업") -> IncentiveScheme:
    return IncentiveScheme(
        subsidy_rate=0.0,
        subsidy_fixed=None,
        subsidy_limit=None,
        loan_rate=0.0,
        loan_interest=0.0,
        loan_grace_years=0,
        loan_repayment_years=0,
        loan_repayment_type="원리금균등",
        tax_credit_rate=0.0,
        sponsor="국비",
        funding_program=program,
        is_prefunded=True,
        prefunded_status="확정 지원",
    )


class TestESSContract(DERContractTests):
    """`DER` 계약 전건을 상속으로 받는다 — 자원마다 손으로 쓰면 반드시 빠진다."""

    def make(self) -> DER:
        return _p1_ess(
            capex_unit_won_per_kwh=500_000.0, capex_extra_won=1_000_000.0,
            fixed_om_won_per_year=100_000.0, variable_om_won_per_kwh=3.0,
            replacement_unit_won_per_kwh=400_000.0,
        )


# ── FR-102-AC1.ESS 자원 정의 ─────────────────────────────────────────
@pytest.mark.req("FR-102-AC1.ESS")
def test_tag_is_spec_literal_and_only_electric_is_carried() -> None:
    """`tag` 는 spec 조항 ID `FR-102-AC1.ESS` 와 **같은 리터럴**이다.

    슬러그화·소문자화하면 NFR-106 레지스트리 순회가 자원을 못 찾고도 초록불로
    남는다. 매체는 전기만 참이다 — 거짓인 매체에 실린 값은 사라진다.
    """
    ess = _p1_ess()
    assert ESS.tag == "ESS"
    assert ess.carries_electric is True
    assert (ess.carries_heat, ess.carries_cool, ess.consumes_fuel) == (False, False, False)


@pytest.mark.req("FR-102-AC1.ESS")
@pytest.mark.parametrize(
    ("bad", "needle"),
    [
        ({"capacity_kwh": 0.0}, "정격용량"),
        ({"power_kw": -1.0}, "정격출력"),
        ({"rte_pct": 0.0}, "RTE"),
        ({"soc_min_pct": 90.0, "soc_max_pct": 10.0}, "SOC"),
        ({"cycle_life": 0}, "사이클수명"),
        ({"calendar_life": 0}, "달력수명"),
    ],
)
def test_invalid_parameters_are_rejected_with_cause(bad: dict, needle: str) -> None:
    """음성 케이스 (§13.2.1 「양·음성 쌍」) — 원인이 메시지에 있어야 한다."""
    with pytest.raises(ValueError, match=needle):
        _p1_ess(**bad)


# ── NFR-303-M1 입력 검증 오류의 3요소 구조 (field·reason·action) ────────
# 「예외가 났다」만 보는 테스트는 메시지가 비어도 통과한다 — 그래서 `as_dict()`
# 로 구조를 꺼내 관례(field 경로)·받은 값(reason)·규칙 ID(rule) 를 각각 단언한다.
@pytest.mark.req("NFR-303-M1")
@pytest.mark.parametrize(
    ("bad", "field", "value_needle", "action_needle", "rule"),
    [
        ({"capacity_kwh": 0.0}, "ess.capacity_kwh", "0.0", "0보다 큰", None),
        ({"power_kw": -1.0}, "ess.power_kw", "-1.0", "0보다 큰", None),
        ({"cycles_per_year": 0.0}, "ess.cycles_per_year", "0.0", "0보다 큰", None),
        ({"cycle_life": 0}, "ess.cycle_life", "0", "0보다 큰", None),
        ({"calendar_life": 0}, "ess.calendar_life", "0", "0보다 큰", None),
        ({"rte_pct": 0.0}, "ess.rte", "0.0", "100 이하", "DV-3"),
        ({"soc_min_pct": -1.0}, "ess.soc_min", "-1.0", "0.0~100.0", "DV-2"),
        ({"soc_max_pct": 101.0}, "ess.soc_max", "101.0", "0.0~100.0", "DV-2"),
        (
            {"soc_min_pct": 90.0, "soc_max_pct": 10.0},
            "ess.soc_min", "90.0", "상한보다 작은", "DV-2",
        ),
        ({"backup_reserve_pct": 100.0}, "ess.backup_reserve", "100.0", "100 미만", None),
        ({"pcs_lifetime": 0}, "ess.pcs_lifetime", "0", "0보다 큰", None),
        ({"vat_rate": 1.5}, "ess.vat_rate", "1.5", "0.0~1.0", None),
    ],
)
def test_constructor_validation_errors_carry_field_reason_action(
    bad: dict, field: str, value_needle: str, action_needle: str, rule: str | None
) -> None:
    """`DV-2`(SOC 상하한)·`DV-3`(RTE) 를 포함한 생성자 검증 12곳이 필드·사유·
    조치·규칙을 구조로 갖춘다. `soc_min_pct=90/soc_max_pct=10` 케이스는 두 값이
    각각 [0,100] 범위 안이라 개별 범위 검사를 통과하고 **관계 검사**(하한<상한)
    에서만 걸린다 — 그래서 `field` 가 `ess.soc_min` 하나로 좁혀지는지도 함께 본다.

    `action_needle` 은 **`action` 이 비어 있지 않다는 것만으로는 부족하다**는
    것을 스스로 증명한다 — "값을 고치십시오" 같은 빈 조치로 바꿔도 진리값은
    truthy 라 살아남는다. 그래서 조치의 **구체적 내용**(허용 범위·경계)을 본다.
    """
    with pytest.raises(ValidationError) as excinfo:
        _p1_ess(**bad)
    parts = excinfo.value.as_dict()
    assert parts["field"] == field
    assert value_needle in parts["reason"]
    assert action_needle in parts["action"]
    assert parts["rule"] == rule


@pytest.mark.req("NFR-303-M1")
def test_eol_soh_validation_error_carries_field_reason_action() -> None:
    """사용후배터리 EOL 관계 검사(§13.2.3 `RC-ESS-P4` 음성 케이스)도 구조를 갖춘다."""
    with pytest.raises(ValidationError) as excinfo:
        _p1_ess(second_life=True, eol_soh_pct=80.0)
    parts = excinfo.value.as_dict()
    assert parts["field"] == "ess.eol_soh"
    assert "80.0" in parts["reason"]
    assert parts["action"]
    assert parts["rule"] is None


@pytest.mark.req("NFR-303-M1")
def test_annual_fade_over_100_percent_validation_error_carries_field_reason_action() -> None:
    """연간 열화율이 100%를 넘는 파라미터 조합 — `field` 는 개별 입력이 아니라
    **파생값**(`degradation_rate`) 을 가리킨다. 세 입력 중 하나만 탓할 수 없다.

    `rule` 은 비운다 — 대장 `DV-3` 의 열화율 경계는 `[0,10] %/년`(내부 소수
    0~0.1)인데 이 검사의 경계는 `[0,100) %/년`(내부 소수 0~1)로 더 넓다. 경계를
    좁히는 것은 동작 변경이라 이 구획의 일이 아니므로 `rule` 을 달지 않는다.
    """
    with pytest.raises(ValidationError) as excinfo:
        _p1_ess(cycle_life=1)
    parts = excinfo.value.as_dict()
    assert parts["field"] == "ess.degradation_rate"
    assert parts["action"]
    assert parts["rule"] is None


@pytest.mark.req("NFR-303-M1")
@pytest.mark.parametrize(
    ("kwargs", "needle"),
    [
        ({"mode_weights": {ESSOperatingMode.TOU_ARBITRAGE: 1.0}}, "혼합(가중치) 모드에서만"),
        ({"operating_mode": ESSOperatingMode.HYBRID}, "가중치가 필요합니다"),
        (
            {
                "operating_mode": ESSOperatingMode.HYBRID,
                "mode_weights": {
                    ESSOperatingMode.TOU_ARBITRAGE: -0.5, ESSOperatingMode.PEAK_SHAVING: 1.5,
                },
            },
            "음수가 될 수 없습니다",
        ),
        (
            {
                "operating_mode": ESSOperatingMode.HYBRID,
                "mode_weights": {
                    ESSOperatingMode.TOU_ARBITRAGE: 0.5,
                    ESSOperatingMode.PEAK_SHAVING: 0.2,
                },
            },
            "합이 1이 아닙니다",
        ),
    ],
)
def test_mode_weight_validation_errors_carry_field_reason_action(
    kwargs: dict, needle: str
) -> None:
    """운전 방법 가중치 4곳(§FR-105) 모두 `field="ess.mode_weights"` 로 좁혀진다."""
    with pytest.raises(ValidationError) as excinfo:
        _p1_ess(**kwargs)
    parts = excinfo.value.as_dict()
    assert parts["field"] == "ess.mode_weights"
    assert needle in parts["reason"]
    assert parts["action"]
    assert parts["rule"] is None


# ── RC-ESS-P1 왕복효율·SOC 경계 ──────────────────────────────────────
@pytest.mark.req("FR-102-AC1.ESS")
def test_rc_ess_p1_roundtrip_efficiency_and_soc_window() -> None:
    """`RC-ESS-P1` 산식 원문 (§13.2.3 ESS 표):

        가용   = 정격 × (SOC상한 − SOC하한) = 10 × (0.9 − 0.1) = **8 kWh**
        연 방전 = 8 × 365 = **2,920 kWh**
        연 충전 = 2,920 / 0.9 = **3,244.4 kWh** (표기 소수 1자리)
        연 손실 = 3,244.4 − 2,920 = **324.4 kWh**

    **표의 3,244.4 는 표시용 반올림이다.** 내부 값 3,244.4444… 를 `RC-ESS-B1`
    이 요구한다 — 그래서 반올림은 금액 경계에서만 일어난다.
    """
    ess = _p1_ess()
    assert ess.usable_capacity_kwh(year=1) == pytest.approx(8.0, rel=1e-9)
    assert ess.annual_discharge_kwh(year=1) == pytest.approx(2920.0, rel=1e-9)
    assert round(ess.annual_charge_kwh(year=1), 1) == 3244.4
    assert round(ess.annual_loss_kwh(year=1), 1) == 324.4
    assert ess.annual_charge_kwh(year=1) == pytest.approx(2920.0 / 0.9, rel=1e-9)


@pytest.mark.req("FR-102-AC1.ESS")
def test_rc_ess_p1_dispatch_year_totals_match_analytic_values() -> None:
    """8760 디스패치의 연 합계가 위 손계산과 일치한다.

    부호 규약: **양수 = 방전, 음수 = 충전**. 뒤집으면 합산이 조용히 상쇄된다.
    """
    ess = _p1_ess()
    result = ess.dispatch(DispatchContext(steps=8760, dt=3600, year=1))

    assert sum(v for v in result.electric if v > 0) == pytest.approx(2920.0, rel=1e-9)
    assert -sum(v for v in result.electric if v < 0) == pytest.approx(2920 / 0.9, rel=1e-9)
    assert all(v == 0.0 for v in result.heat + result.cool + result.fuel)


# ── RC-ESS-P2 수지 균형 ──────────────────────────────────────────────
@pytest.mark.req("FR-301-AC2")
def test_rc_ess_p2_energy_balance_holds_at_every_step() -> None:
    """`RC-ESS-P2` — 오라클 §13.2.3 / 허용 오차 NFR-102(1e-6 kWh).

    **표의 산식 `충전 = 방전/RTE + 손실` 은 그대로 성립할 수 없다** — P1 수치를
    넣으면 3,244.4 = 3,244.4 + 324.4 가 되어 손실을 두 번 센다. 물리적으로 닫히고
    P1 수치와도 맞는 항등식은 둘이다 (표 문구의 합산형은 재현하지 않는다):

        충전 = 방전 / RTE   (3,244.444… = 2,920 / 0.9)
        충전 = 방전 + 손실   (3,244.444… = 2,920 + 324.444…)

    스텝별로는 SOC 가 창 안에 머물고 하루 주기가 닫히는지를 본다.
    """
    ess = _p1_ess()
    series = ess.dispatch(DispatchContext(steps=8760, dt=3600, year=1)).electric
    lo, hi = ess.soc_bounds_kwh(year=1)

    soc = lo
    for i, step in enumerate(series):
        soc += (-step * ess.rte) if step < 0 else -step
        assert lo - ENERGY_TOLERANCE_KWH <= soc <= hi + ENERGY_TOLERANCE_KWH
        if (i + 1) % 24 == 0:  # 하루 충전 × RTE = 하루 방전 → SOC 가 하한으로 복귀
            assert abs(soc - lo) < ENERGY_TOLERANCE_KWH

    discharge = ess.annual_discharge_kwh(year=1)
    charge = ess.annual_charge_kwh(year=1)
    assert abs(charge - discharge / ess.rte) < ENERGY_TOLERANCE_KWH
    assert abs(charge - (discharge + ess.annual_loss_kwh(year=1))) < ENERGY_TOLERANCE_KWH


# ── RC-ESS-P3 열화 — 사이클/달력 중 보수적 값 ────────────────────────
@pytest.mark.req("FR-104-AC2")
def test_rc_ess_p3_cycle_degradation_dominates() -> None:
    """`RC-ESS-P3` 사이클 지배 — FR-104-AC2 「보수적 값」. 산식 원문:

        SOH_사이클(y) = SOH0 − (SOH0 − EOL) × 누적사이클 / 사이클수명
        SOH_달력(y)   = SOH0 − (SOH0 − EOL) × y / 달력수명
        SOH(y) = min(둘) ← **더 나쁜 쪽**
        사이클 1,000회 · 연 365 · 달력 20년, 3년차 → 0.781(채택) vs 달력 0.970
    """
    ess = _p1_ess(cycle_life=1000, calendar_life=20)
    assert ess.soh_cycle(year=3) == pytest.approx(0.781, rel=1e-9)
    assert ess.soh_calendar(year=3) == pytest.approx(0.970, rel=1e-9)
    assert ess.state_of_health(year=3) == pytest.approx(0.781, rel=1e-9)


@pytest.mark.req("FR-104-AC2")
def test_rc_ess_p3_calendar_degradation_dominates() -> None:
    """`RC-ESS-P3` 달력 지배 — 같은 산식, 파라미터만 뒤집는다.

    사이클 20,000회 · 연 365 · 달력 10년, 5년차:
        사이클 = 1 − 0.2 × 1,825/20,000 = 0.98175 / 달력 = **0.900** ← 채택
    """
    ess = _p1_ess(cycle_life=20000, calendar_life=10)
    assert ess.soh_cycle(year=5) == pytest.approx(0.98175, rel=1e-9)
    assert ess.soh_calendar(year=5) == pytest.approx(0.900, rel=1e-9)
    assert ess.state_of_health(year=5) == pytest.approx(0.900, rel=1e-9)


@pytest.mark.req("FR-104-AC2")
@pytest.mark.req("FR-101-AC1")
def test_rc_ess_p3_degradation_rate_is_the_conservative_annual_equivalent() -> None:
    """`degradation_rate`(FR-101-AC1) 도 보수적 쪽을 따른다.

    사이클 6,000회 · 연 365사이클 · 달력 20년:
        연 사이클 = 0.2 × 365/6,000 = 0.0121667 ← 더 나쁨 / 연 달력 = 0.01
    """
    assert _p1_ess().degradation_rate == pytest.approx(0.2 * 365 / 6000, rel=1e-9)
    # 수명은 달력수명을 넘지 않는다 — 사이클을 적게 쓴다고 영구히 쓰진 못한다
    assert _p1_ess(cycle_life=10**9, calendar_life=12).eol_year() == 12


# ── RC-ESS-P4 EOL 교체 ──────────────────────────────────────────────
@pytest.mark.req("FR-104-AC2")
def test_rc_ess_p4_replacement_is_charged_after_eol_is_reached() -> None:
    """`RC-ESS-P4` — 잔존율 80% 도달 시점에 교체비 계상.

    사이클 1,000회 · 연 365사이클 → 1,000/365 = 2.74년에 EOL, 올림하여 **수명
    3년**. `RC-ALL-C4` 「수명 도달 **다음 연도 초**」로 교체는 **4년차**이며 이후
    3년마다 반복한다.
    """
    ess = _p1_ess(cycle_life=1000, calendar_life=20, replacement_unit_won_per_kwh=400_000.0)

    assert ess.state_of_health(year=2) > 0.80
    assert ess.state_of_health(year=3) <= 0.80
    assert ess.eol_year() == 3
    assert ess.lifetime == 3
    assert sorted(ess.replacement_schedule(horizon=20)) == [4, 7, 10, 13, 16, 19]


@pytest.mark.req("FR-104-AC2")
def test_rc_ess_p4_second_life_battery_starts_at_soh_80() -> None:
    """`RC-ESS-P4` — 사용후배터리는 **초기 SOH 80%** 에서 시작한다.

    잔여 수명(사이클 500회 · 달력 10년)은 EOL 60% 까지의 값이므로
        SOH(1) = 0.8 − (0.8 − 0.6) × 365/500 = **0.654**
        가용    = 10 × 0.8 × 0.8 = **6.4 kWh** (1년차 = 초기 SOH 적용)
        EOL     = 500/365 = 1.37년 → 올림 **2년** → 교체 3년차
    """
    ess = _p1_ess(second_life=True, eol_soh_pct=60.0, cycle_life=500, calendar_life=10)

    assert ess.initial_soh == pytest.approx(0.80, rel=1e-9)
    assert ess.state_of_health(year=0) == pytest.approx(0.80, rel=1e-9)
    assert ess.state_of_health(year=1) == pytest.approx(0.654, rel=1e-9)
    assert ess.usable_capacity_kwh(year=1) == pytest.approx(6.4, rel=1e-9)
    assert ess.eol_year() == 2
    assert sorted(ess.replacement_schedule(horizon=8)) == [3, 5, 7]


@pytest.mark.req("FR-104-AC2")
def test_rc_ess_p4_second_life_with_unreachable_eol_is_rejected() -> None:
    """음성 케이스 — 사용후배터리(초기 80%)에 EOL 80% 를 주면 거부한다.

    허용하면 **취득 즉시 EOL** 인 자원이 된다. 교체비가 매년 잡히는 형태라
    "보수적으로 나왔나 보다"로 읽힌다 — 조용히 틀리는 유형이다.
    """
    with pytest.raises(ValueError, match="EOL"):
        _p1_ess(second_life=True, eol_soh_pct=80.0)


# ── RC-ESS-B1 TOU 차익거래 / B2 피크 저감 ───────────────────────────
@pytest.mark.req("FR-302-AC2")
def test_rc_ess_b1_tou_arbitrage_benefit() -> None:
    """`RC-ESS-B1` 산식 원문 (§13.2.3 ESS 표):

        편익 = 방전 kWh × 피크단가 − 충전 kWh × 경부하단가
             = 2,920 × 200 − 3,244.444… × 80
             = 584,000 − 259,556 = **324,444원/년**

    259,556 은 259,555.55… 의 사사오입이다. 표시값 3,244.4 로 계산하면 259,552
    가 되어 4원 어긋난다 — **반올림은 금액 경계에서 단 한 번**(NFR-103)이라는
    규약이 여기서 결과를 가른다.
    """
    ess = _p1_ess()
    benefit = ess.tou_arbitrage_benefit(peak_price_won=200.0, offpeak_price_won=80.0, year=1)

    assert isinstance(benefit, Money)
    assert benefit == to_won(584_000) - to_won(2920.0 / 0.9 * 80.0)
    assert benefit == 324_444


@pytest.mark.req("FR-401-AC2.PeakShaving")
def test_rc_ess_b2_peak_shaving_benefit() -> None:
    """`RC-ESS-B2` 산식 원문: `저감 kW × 기본요금 단가 × 12개월`

        저감 가능 출력 = 가용 8 kWh / 방전창 4시간 = **2 kW** (정격 5kW 이내)
        편익 = 2 × 8,320 × 12 = **199,680원/년**
    """
    ess = _p1_ess()
    assert ess.reducible_peak_kw(year=1) == pytest.approx(2.0, rel=1e-9)

    benefit = ess.peak_shaving_benefit(demand_charge_won_per_kw=8_320.0, year=1)
    assert isinstance(benefit, Money)
    assert benefit == 199_680

    # 저감 kW 는 정격출력을 넘을 수 없다 — 넘기면 없는 출력으로 편익이 난다
    capped = _p1_ess(power_kw=1.0, capacity_kwh=100.0, cycle_life=20000)
    assert capped.reducible_peak_kw(year=1) == pytest.approx(1.0, rel=1e-9)


@pytest.mark.req("FR-611-AC1")
@pytest.mark.req("FR-611-AC2")
@pytest.mark.req("FR-611-AC3.OWNER")
@pytest.mark.req("FR-611-AC3.GOV")
@pytest.mark.req("FR-611-AC5")
@pytest.mark.req("FR-611-AC6")
def test_rc_ess_b3_prefunded_ess_is_zero_to_owner_full_to_society_and_split_for_gov() -> None:
    """`RC-ESS-B3` 오라클 (§13.2.3 ESS 표):

        취득가         = 2,000,000 × 10 = **20,000,000원**
        사업자 관점    = **0원**
        사회 관점      = **20,000,000원**
        정부 관점      = 본 사업 0원 + `타 사업 국비` 행 **20,000,000원**
        고정 O&M       = **100,000원/년**
        변동 O&M       = 2,920 × 3 = **8,760원/년**
        교체비         = 4·7·10·13·16·19년차 × **4,000,000원**
        잔존가치(20년) = 19년차 교체분 4,000,000 × 1/3 = **1,333,333원**

    경계 짝: `타 사업 국비` 행에는 **재원 사업명**이 남아 있어야 한다. 빠지면
    20,000,000원이 어느 사업에서 온 돈인지 리포트에서 사라진다.
    """
    ess = _p1_ess(
        cycle_life=1000,
        calendar_life=20,
        capex_unit_won_per_kwh=2_000_000.0,
        fixed_om_won_per_year=100_000.0,
        variable_om_won_per_kwh=3.0,
        replacement_unit_won_per_kwh=400_000.0,
    )
    scheme = _prefunded_scheme()
    acquisition = ess.capex(year=1)

    owner_rows = build_capex_cashflows(scheme, acquisition, "OWNER")
    gov_rows = build_capex_cashflows(scheme, acquisition, "GOV")

    assert acquisition == Money(20_000_000)
    assert sum((row.total() for row in owner_rows), Money(0)) == Money(0)
    assert len(gov_rows) == 1
    assert gov_rows[0].tag == "capex.prefunded_subsidy"
    assert gov_rows[0].total() == Money(-20_000_000)
    assert scheme.funding_program in gov_rows[0].label
    assert ess.fixed_om(year=1) == Money(100_000)
    assert ess.variable_om(year=1) == Money(8_760)
    assert ess.replacement_schedule(horizon=20) == {
        4: Money(4_000_000),
        7: Money(4_000_000),
        10: Money(4_000_000),
        13: Money(4_000_000),
        16: Money(4_000_000),
        19: Money(4_000_000),
    }
    assert ess.salvage_value(year=20) == Money(1_333_333)


# ── RC-ESS-X1 SOC 하한 침범 ─────────────────────────────────────────
@pytest.mark.req("FR-102-AC1.ESS")
def test_rc_ess_x1_discharge_below_soc_floor_is_rejected_with_cause() -> None:
    """`RC-ESS-X1` — 하한 미만 방전 지시는 **거부되고 원인이 보고**된다.

    조용히 잘라내면 가용량이 늘어난 것과 같아 편익이 과대 계상되고, 잘라낸
    값으로 수지가 닫혀 NFR-102 검사는 통과한다.
    """
    ess = _p1_ess()
    lo, hi = ess.soc_bounds_kwh(year=1)

    with pytest.raises(ValueError) as excinfo:
        ess.plan_discharge(soc_kwh=lo, energy_kwh=2.0, year=1)

    message = str(excinfo.value)
    assert "SOC 하한" in message
    assert ess.name in message and "2" in message  # 원인 — 자원명·요구량 보고

    # 양성 짝 (§13.2.1) — 하한까지의 방전은 정상 수행된다
    assert ess.plan_discharge(soc_kwh=hi, energy_kwh=hi - lo) == pytest.approx(hi - lo)


# ── RC-ALL-C1~C3 (§13.2.2) ─────────────────────────────────────────
@pytest.mark.req("FR-101-AC5")
def test_rc_all_c1_capex() -> None:
    """`RC-ALL-C1` 산식 원문 (§13.2.2): `단가 × 용량 + 부대비`

    ESS 파라미터화: 500,000 × 10 + 1,000,000 = **6,000,000원**. 1년차에만 발생.
    """
    ess = _p1_ess(capex_unit_won_per_kwh=500_000.0, capex_extra_won=1_000_000.0)
    assert isinstance(ess.capex(year=1), Money)
    assert ess.capex(year=1) == 6_000_000
    assert ess.capex(year=2) == 0


# ↓ v0.15 이관 — 이 검사가 보는 것은 메서드의 **존재**(AC2)가 아니라
# **산식**(§13.2.2 C-1~C-3)이다. AC5 가 없던 동안 AC2 를 빌려 인용했다.
@pytest.mark.req("FR-101-AC5")
def test_rc_all_c1_vat_is_separated_from_the_body() -> None:
    """`RC-ALL-C1` 부가세 분리 — **이 자원은 세액 자체가 없었다.**

    v1.0 계약에 `capex_vat()` 자리가 없어 자원 6종 중 다섯은 각자 지어냈고 ESS
    하나는 만들지 않았다. 그래서 프로포마의 부가세 행에서 ESS 열만 0원이 되고,
    그 0은 **면세인지 누락인지 구분되지 않는다.** 계약 개정(v1.1)이 메운 자리다.

    오라클: 본체 6,000,000 × 10% = **600,000원**. 본체는 세액을 포함하지 않고,
    세액은 1년차에만 발생한다 — `capex()` 가 0인 해에 세액이 남으면 없는 투자에
    세금이 붙는다.
    """
    ess = _p1_ess(capex_unit_won_per_kwh=500_000.0, capex_extra_won=1_000_000.0,
                  vat_rate=0.10)
    assert ess.capex(year=1) == 6_000_000, "본체에 세액이 섞였습니다 (§13.2.2 C-1)"
    assert ess.capex_vat(year=1) == Money(600_000)
    assert ess.capex_vat(year=2) == 0

    # 세율을 주지 않으면 0이다 — 「부가세를 계상하지 않는 케이스」는 §13.2.1
    # 단독성이 요구하는 상태이며, 메서드가 없는 것과는 다르다
    assert _p1_ess(capex_unit_won_per_kwh=500_000.0).capex_vat(year=1) == 0


@pytest.mark.req("FR-101-AC5")
def test_rc_all_c2_fixed_om_20y_cumulative_matches_geometric_sum() -> None:
    """`RC-ALL-C2` ESS 파라미터화 — 연 10만원 · 물가 2% · 20년 → 2,429,737원.

    `won_sum` 은 **각 항을 반올림한 뒤 더한다**(NFR-103-M1). 그 합이 닫힌형과
    일치해야 프로포마의 행별 합과 총계가 어긋나지 않는다.

    **2,429,737원은 이 검사가 계산한 값이 아니다** — spec §13.2.2 `RC-ALL-C2`
    의 오라클(`A × ((1+i)^n − 1)/i`, 손계산 2,429,736.98…)이다. 검사는 그
    상수와 `ess.fixed_om()` 20년 합을 견줄 뿐이며, **양쪽 끝이 서로 다른
    층에서 온다**(R39-C).

    닫힌형 항등식과 반올림 규약 자체는 여기서 재지 않는다 — 갈라 적는다:
      · 닫힌형 = 메서드 합 : `tests/asset/test_common_asset.py::`
        `test_rc_ca_c2_fixed_om_20year_total` (FR-106-AC4, `Decimal` 산술)
      · `to_won` 사사오입 규약 : `tests/contract/test_money_boundary.py::`
        `test_to_won_uses_half_up_not_bankers` (NFR-103-M1)

    ⚠ **여기에 `to_won(a*((1+i)**n-1)/i) == 2_429_737` 을 다시 넣지 말 것.**
    R39-C 가 그 형태를 지웠다 — 검사가 오라클을 스스로 계산하므로 `ess` 를
    어떻게 망가뜨려도 초록불이었고(물가 계수를 지운 변이를 이 검사만 잡았다),
    실제로 붙들던 것은 「`to_won` 이 반올림을 하기는 하는가」 하나였다.
    """
    ess = _p1_ess(fixed_om_won_per_year=100_000.0, escalation_rate=0.02)
    assert ess.fixed_om(year=1) == 100_000
    assert ess.fixed_om(year=2) == 102_000
    assert won_sum(ess.fixed_om(year=y) for y in range(1, 21)) == 2_429_737


@pytest.mark.req("FR-101-AC5")
def test_rc_all_c3_variable_om_is_based_on_throughput_kwh() -> None:
    """`RC-ALL-C3` 산식 원문 (§13.2.2): `처리량 × 단가`

    **ESS 의 처리량은 방전 kWh** 다 (표 원문 「ESS 처리 kWh」).
        1년차 2,920 kWh × 3원 = **8,760원** / 2년차 열화(SOH 0.98783…)로 8,653원
    """
    ess = _p1_ess(variable_om_won_per_kwh=3.0)
    soh1 = 1.0 - 0.2 * max(1 / 20, 365 / 6000)

    assert ess.variable_om(year=1) == 8_760
    assert ess.variable_om(year=2) == to_won(10.0 * 0.8 * soh1 * 365 * 3.0)
    assert ess.variable_om(year=2) < ess.variable_om(year=1)


# ── RC-ALL-C4 교체비 ────────────────────────────────────────────────
@pytest.mark.req("FR-104-AC4")
def test_rc_all_c4_replacement_schedule_separates_battery_and_pcs() -> None:
    """`RC-ALL-C4` — 「수명 도달 **다음 연도 초**」 + 부속설비 독립 스케줄.

        배터리 수명 3년(사이클 1,000회) → 4·7·10·13·16·19년차 × 4,000,000원
        PCS 수명 10년(본체와 무관)      → **11년차** × 2,000,000원

    본체 수명만 보면 PCS 교체비가 통째로 빠진다 (도메인 원칙 4-3).
    """
    ess = _p1_ess(
        cycle_life=1000, calendar_life=20, replacement_unit_won_per_kwh=400_000.0,
        pcs_lifetime=10, pcs_cost_won=2_000_000.0,
    )
    schedule = ess.replacement_schedule(horizon=20)

    assert sorted(schedule) == [4, 7, 10, 11, 13, 16, 19]
    assert schedule[4] == 4_000_000
    assert schedule[11] == 2_000_000
    assert all(isinstance(v, Money) for v in schedule.values())

    # 같은 해에 겹치면 **합산**한다 — 덮어쓰면 한쪽이 조용히 사라진다
    overlap = _p1_ess(
        cycle_life=1000, calendar_life=20, replacement_unit_won_per_kwh=400_000.0,
        pcs_lifetime=3, pcs_cost_won=2_000_000.0,
    )
    assert overlap.replacement_schedule(horizon=5)[4] == 6_000_000


# ── FR-104-AC3 수명 도달 시 처리(`replace`/`retire`) ────────────────
@pytest.mark.req("FR-104-AC3")
def test_default_end_of_life_action_is_replace_and_unchanged() -> None:
    """1번 단언 — 기본값은 `replace`. 아무것도 안 넘기면 `RC-ESS-P4`(위
    `test_rc_all_c4_replacement_schedule_separates_battery_and_pcs`)의 기존
    오라클과 **똑같은 결과**여야 한다. 여기서 값이 달라지면 기본값 경로를
    건드린 것이다.
    """
    ess = _p1_ess(cycle_life=1000, calendar_life=20, replacement_unit_won_per_kwh=400_000.0)
    assert ess.end_of_life_action == "replace"
    assert ess.retires_at_end_of_life() is False
    assert sorted(ess.replacement_schedule(horizon=20)) == [4, 7, 10, 13, 16, 19]


@pytest.mark.req("FR-104-AC3")
def test_retire_empties_replacement_schedule() -> None:
    """2번 단언 — `retire` 면 본체도 부속설비(PCS)도 사지 않는다.

    사이클 1,000회·달력 20년 → 본체 수명 3년(`RC-ESS-P4` 오라클과 동일 제원).
    PCS 수명 10년을 함께 주어도 **아무 해도 계상되지 않아야** 한다 — PCS만
    비우고 본체만 남기거나 그 반대이면 「비용만 끊고 편익은 남기는」 결함이
    부분적으로 되살아난다.
    """
    ess = _p1_ess(
        cycle_life=1000, calendar_life=20, replacement_unit_won_per_kwh=400_000.0,
        pcs_lifetime=10, pcs_cost_won=2_000_000.0, end_of_life_action="retire",
    )
    assert ess.retires_at_end_of_life() is True
    assert ess.replacement_schedule(horizon=20) == {}


@pytest.mark.req("FR-104-AC3")
def test_retire_output_matches_replace_through_eol_year_then_zeroes() -> None:
    """3·4번 단언 — 수명 해(3년차)까지는 `replace` 와 **똑같이** 운전하고,
    그 다음 해(4년차)부터 출력이 **0** 이다.

    사이클 1,000회·달력 20년 → `eol_year()`=`lifetime`=3년(`RC-ESS-P4` 오라클,
    부속설비 없음이므로 첫 수명종료=본체 수명=3년). 하루(24스텝)만 보아도
    충분한 이유: 이 자원의 하루 프로파일은 그 해의 `usable_capacity_kwh`
    하나에만 좌우되고 날짜와 무관하게 반복된다.
    """
    kwargs = {
        "cycle_life": 1000, "calendar_life": 20,
        "replacement_unit_won_per_kwh": 400_000.0,
    }
    replace_ess = _p1_ess(**kwargs, end_of_life_action="replace")
    retire_ess = _p1_ess(**kwargs, end_of_life_action="retire")
    assert retire_ess.lifetime == 3

    ctx_at_eol = DispatchContext(steps=24, dt=3600, year=3)
    ctx_after_eol = DispatchContext(steps=24, dt=3600, year=4)

    # 4번 — 수명 해(3년차)까지는 replace 와 동일
    assert (
        retire_ess.dispatch(ctx_at_eol).electric
        == replace_ess.dispatch(ctx_at_eol).electric
    )

    # 3번 — 수명 해 다음(4년차)부터 retire 는 전 매체 출력 0
    retired_result = retire_ess.dispatch(ctx_after_eol)
    assert all(v == 0.0 for v in retired_result.electric)
    assert all(
        v == 0.0
        for v in retired_result.heat + retired_result.cool + retired_result.fuel
    )
    # replace 는 (열화된 채로) 여전히 운전을 계속한다 — 대조군
    assert any(v != 0.0 for v in replace_ess.dispatch(ctx_after_eol).electric)


@pytest.mark.req("FR-104-AC3")
def test_retire_zeroes_output_at_the_earlier_of_body_or_pcs_lifetime() -> None:
    """계약(`core/contracts/der.py`) 「retire 의 의미」 ⑤ — 출력은 **본체·
    부속설비 중 먼저 수명이 끝나는 쪽**에서 멈춘다.

    사이클 1,000회·달력 20년 → 본체 수명(`eol_year()`) 3년. `pcs_lifetime=2`
    (본체보다 짧음)를 주면 **첫 수명종료는 2년차**다. 본체만 보고 3년차까지
    정상으로 두면 「PCS 없는 ESS」가 3년차에도 운전하는 것과 같은 결함이 되어,
    이것이 이 구획의 핵심이다(브리프 ★ 항목).
    """
    ess = _p1_ess(
        cycle_life=1000, calendar_life=20, replacement_unit_won_per_kwh=400_000.0,
        pcs_lifetime=2, pcs_cost_won=2_000_000.0, end_of_life_action="retire",
    )
    assert ess.lifetime == 3  # 본체 EOL 자체는 그대로 3년

    ctx_at_pcs_eol = DispatchContext(steps=24, dt=3600, year=2)
    ctx_body_still_alive_but_pcs_gone = DispatchContext(steps=24, dt=3600, year=3)

    # PCS 수명 해(2년차)까지는 정상 운전
    assert any(v != 0.0 for v in ess.dispatch(ctx_at_pcs_eol).electric)
    # 본체 수명(3년) 안이지만 PCS 는 이미 끝났다 — 출력 0
    assert all(v == 0.0 for v in ess.dispatch(ctx_body_still_alive_but_pcs_gone).electric)


@pytest.mark.req("FR-104-AC3")
def test_retire_salvage_value_unchanged_before_eol() -> None:
    """계약 「retire 의 의미」 ③ — EOL 전에는 `replace` 와 잔존가치가 같다.

    `retire` 는 미래의 선택이고 EOL 전에는 자산이 정상 가동 중이므로, 분석
    기간이 EOL 前(1·2년차)에 끝나면 두 선택의 잔존가치가 달라질 이유가 없다.
    이 구획은 `salvage_value()` 를 고치지 않았다는 것을 이 테스트로 고정한다.
    """
    kwargs = {
        "cycle_life": 1000, "calendar_life": 20,
        "capex_unit_won_per_kwh": 500_000.0, "capex_extra_won": 1_000_000.0,
        "replacement_unit_won_per_kwh": 400_000.0,
    }
    replace_ess = _p1_ess(**kwargs, end_of_life_action="replace")
    retire_ess = _p1_ess(**kwargs, end_of_life_action="retire")

    for year in (1, 2):
        assert retire_ess.salvage_value(year=year) == replace_ess.salvage_value(year=year)


# ── RC-ALL-C5 잔존가치 ──────────────────────────────────────────────
@pytest.mark.req("FR-104-AC5")
def test_rc_all_c5_salvage_value_is_prorated_by_remaining_life() -> None:
    """`RC-ALL-C5` 산식 원문 (§13.2.2): `취득가 × 잔존수명 / 총수명` 최종연도 계상 후 할인.

    ESS 파라미터화 (달력 25년 · 사이클 20,000회 → 수명 25년):
        취득가   = 500,000 × 10 + 1,000,000 = 6,000,000원
        잔존수명 = 25 − 20 = 5년
        잔존가치 = 6,000,000 × 5/25 = **1,200,000원**
        할인 후  = 1,200,000 / 1.045^20 = **497,571원**

    **할인은 자원의 책임이 아니다** — `DER.salvage_value()` 는 할인율을 받지
    않으며 CBA 계층(WP-7)이 할인한다. 마지막 단계를 테스트가 직접 보여 둔다.
    """
    ess = _p1_ess(
        calendar_life=25, cycle_life=20000,
        capex_unit_won_per_kwh=500_000.0, capex_extra_won=1_000_000.0,
    )

    assert ess.lifetime == 25
    assert ess.salvage_value(year=20) == 1_200_000
    assert to_won(int(ess.salvage_value(year=20)) / 1.045**20) == 497_571
    assert ess.salvage_value(year=25) == 0  # 수명을 다 쓴 해에는 잔존가치가 없다


@pytest.mark.req("FR-104-AC5")
def test_rc_all_c5_salvage_counts_from_the_latest_acquisition() -> None:
    """교체가 있었다면 잔존수명은 **마지막 취득 시점**부터 센다.

    최초 취득분 기준으로 세면 교체 직후에도 잔존가치가 0으로 잡혀, 분석기간
    말에 새 배터리가 통째로 사라진다.
    """
    ess = _p1_ess(
        cycle_life=1000, calendar_life=20, capex_unit_won_per_kwh=500_000.0,
        capex_extra_won=1_000_000.0, replacement_unit_won_per_kwh=400_000.0,
    )
    # 수명 3년, 마지막 교체 19년차(19·20·21년 사용) → 20년 말 잔존수명 1년
    assert ess.salvage_value(year=20) == to_won(4_000_000 * 1 / 3)


# ── FR-105-AC1 운전 방법 선언 ───────────────────────────────────────
@pytest.mark.req("FR-105-AC1")
def test_operating_modes_declared_match_spec_list() -> None:
    """FR-105-AC1 원문: 「`ESS`: 자가소비 우선 / TOU 차익거래 / 피크 저감 /
    백업 예비 확보 / 혼합(가중치)」 — 자원 클래스가 이 목록을 선언한다."""
    assert {m.value for m in ESS.OPERATING_MODES} == {
        "자가소비 우선",
        "TOU 차익거래",
        "피크 저감",
        "백업 예비 확보",
        "혼합(가중치)",
    }


@pytest.mark.req("FR-105-AC3")
def test_two_instances_may_take_different_modes() -> None:
    """FR-105-AC3 — 같은 유형 두 인스턴스가 서로 다른 운전 방법을 갖는다."""
    household = _p1_ess(name="가구용ESS", operating_mode=ESSOperatingMode.SELF_CONSUMPTION)
    common = _p1_ess(name="공용부ESS", operating_mode=ESSOperatingMode.PEAK_SHAVING)

    assert household.operating_mode is ESSOperatingMode.SELF_CONSUMPTION
    assert common.operating_mode is ESSOperatingMode.PEAK_SHAVING
    assert household.discharge_hours != common.discharge_hours


@pytest.mark.req("FR-105-AC1")
def test_backup_reserve_mode_reduces_usable_energy() -> None:
    """백업 예비 확보는 **가용량을 줄인다** — 줄지 않으면 예비가 이름뿐이다.

    예비 25% → 가용 8 × 0.75 = 6 kWh, 연 방전 6 × 365 = 2,190 kWh
    """
    ess = _p1_ess(operating_mode=ESSOperatingMode.BACKUP_RESERVE, backup_reserve_pct=25.0)
    assert ess.usable_capacity_kwh(year=1) == pytest.approx(6.0, rel=1e-9)
    assert ess.annual_discharge_kwh(year=1) == pytest.approx(2190.0, rel=1e-9)


@pytest.mark.req("FR-105-AC1")
def test_hybrid_mode_requires_weights_that_sum_to_one() -> None:
    """혼합 모드는 가중치를 요구한다 — 없으면 무엇을 섞는지 판정할 수 없다."""
    with pytest.raises(ValueError, match="가중치"):
        _p1_ess(operating_mode=ESSOperatingMode.HYBRID)

    half = {ESSOperatingMode.TOU_ARBITRAGE: 0.5, ESSOperatingMode.PEAK_SHAVING: 0.2}
    with pytest.raises(ValueError, match="합"):
        _p1_ess(operating_mode=ESSOperatingMode.HYBRID, mode_weights=half)

    mixed = _p1_ess(
        operating_mode=ESSOperatingMode.HYBRID,
        backup_reserve_pct=40.0,
        mode_weights={
            ESSOperatingMode.TOU_ARBITRAGE: 0.75,
            ESSOperatingMode.BACKUP_RESERVE: 0.25,
        },
    )
    # 예비 가중치 0.25 × 예비율 0.4 = 10% 만 예비로 묶인다
    assert mixed.usable_capacity_kwh(year=1) == pytest.approx(8.0 * 0.9, rel=1e-9)


# ── 해상도·계통 제약 ────────────────────────────────────────────────
@pytest.mark.req("FR-301-AC1")
def test_dispatch_totals_are_resolution_independent() -> None:
    """15분(35,040 스텝) 해상도에서도 연 합계가 같다 (§7.5 · FR-301).

    해상도를 바꿨더니 연 방전량이 달라지면 케이스 비교가 해상도에 좌우된다.
    """
    ess = _p1_ess(dt=900)
    series = ess.dispatch(DispatchContext(steps=35_040, dt=900, year=1)).electric

    assert sum(v for v in series if v > 0) == pytest.approx(2920.0, rel=1e-9)
    assert -sum(v for v in series if v < 0) == pytest.approx(2920.0 / 0.9, rel=1e-9)


@pytest.mark.req("FR-301-AC4")
def test_dispatch_rejects_plan_that_exceeds_grid_limit() -> None:
    """계통 연계 한도를 넘는 계획은 **거부하고 원인을 보고**한다 (FR-403 취지).

    조용히 잘라내면 잘린 만큼의 편익이 사라지고, 남은 값으로 수지는 닫힌다.
    """
    ctx = DispatchContext(steps=24, dt=3600, year=1, grid_limit_kw=[0.5] * 24)
    with pytest.raises(ValueError, match="계통 연계"):
        _p1_ess().dispatch(ctx)


@pytest.mark.req("NFR-303-M1")
def test_dispatch_grid_limit_violation_carries_field_reason_action() -> None:
    """`_check_grid_limit` 도 3요소 구조로 던진다 — `grid_limit_kw` 는 엔진이
    자원에 건네는 시나리오 입력(계통 연계 한도)이므로 **전환** 대상이다."""
    ctx = DispatchContext(steps=24, dt=3600, year=1, grid_limit_kw=[0.5] * 24)
    with pytest.raises(ValidationError) as excinfo:
        _p1_ess().dispatch(ctx)
    parts = excinfo.value.as_dict()
    assert parts["field"] == "ess.power_kw"
    assert "계통 연계" in parts["reason"]
    assert parts["action"]
    assert parts["rule"] is None


@pytest.mark.req("FR-102-AC1.ESS")
def test_dispatch_rejects_plan_that_exceeds_rated_power() -> None:
    """정격출력을 넘는 운전 계획도 거부한다 — 없는 출력으로 편익이 나면 안 된다."""
    ess = _p1_ess(capacity_kwh=200.0, power_kw=1.0, cycle_life=20000)
    with pytest.raises(ValueError, match="정격출력"):
        ess.dispatch(DispatchContext(steps=24, dt=3600, year=1))


@pytest.mark.req("NFR-303-M1")
def test_dispatch_rated_power_violation_carries_field_reason_action() -> None:
    """`_check_power`(§ dispatch 내부) 도 3요소 구조로 던진다.

    `capacity_kwh`·`power_kw`·`cycles_per_year`·운전 방법의 조합이 만든 계획이
    사용자가 넘긴 정격출력을 넘는 것이라 **전환** 대상이다(대상아님이 아니다) —
    엔진이 임의로 계산해 넘긴 값이 아니라 이 자원 자신의 생성자 파라미터에서
    파생된 값이다.
    """
    ess = _p1_ess(capacity_kwh=200.0, power_kw=1.0, cycle_life=20000)
    with pytest.raises(ValidationError) as excinfo:
        ess.dispatch(DispatchContext(steps=24, dt=3600, year=1))
    parts = excinfo.value.as_dict()
    assert parts["field"] == "ess.power_kw"
    assert "정격출력" in parts["reason"]
    assert parts["action"]
    assert parts["rule"] is None


@pytest.mark.req("NFR-205-M1")
def test_mode_windows_table_is_read_only() -> None:
    """운전 시간대 표는 **읽기 전용**이다 (NFR-205).

    모듈 수준 `dict` 였을 때는 아무도 고치지 않았지만, 그것이 다음 사람도
    고치지 않는다는 보장은 아니다. **케이스 그리드 병렬 실행(FR-805)에서 한
    번의 변형은 다른 케이스의 결과를 조용히 바꾼다** — 표가 바뀐 뒤에 도는
    케이스만 다른 시간대로 운전하고, 그 결과는 그럴듯하다. 조항의 근거인
    DER-VET `Params.py` 가 정확히 그 형태였다.

    값도 함께 고정한다. 읽기 전용으로 만드는 과정에서 표가 바뀌면 `RC-ESS-P1`
    의 손계산 오라클이 어긋나는데, 그 어긋남은 총량으로만 나타나 원인을 찾기
    어렵다.
    """
    from core.der.ess import _MODE_WINDOWS

    with pytest.raises(TypeError):
        _MODE_WINDOWS[ESSOperatingMode.SELF_CONSUMPTION] = ((0,), (1,))  # type: ignore[index]

    charge, discharge = _MODE_WINDOWS[ESSOperatingMode.SELF_CONSUMPTION]
    assert charge == (10, 11, 12, 13, 14, 15)
    assert discharge == (18, 19, 20, 21)
    assert set(_MODE_WINDOWS) == set(ESSOperatingMode) - {ESSOperatingMode.HYBRID}, (
        "운전 방법이 늘거나 줄었는데 표가 따라가지 않았습니다 — FR-105-AC2 는 "
        "운전 방법을 자원이 소유하라고 요구합니다"
    )
