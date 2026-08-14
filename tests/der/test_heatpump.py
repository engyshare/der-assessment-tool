"""`HeatPump` 검증 케이스 — 작업 WP-1d / spec §13.2.3 HeatPump · §13.2.2 공통 비용 5종.

**이 파일이 구현보다 먼저 쓰였다** (NFR-105 TDD). 오라클은 전부 spec 표에서
가져왔고, 자체 계산으로 만든 기대값은 없다 (§13.0.2 자기충족 테스트 금지).

히트펌프가 다른 자원과 다른 점은 **매체를 둘 걸친다**는 것이다 — 전기를
받아들이고 열을 내보낸다. 그래서 이 파일의 무게중심은 `RC-HP-P3`(매체 분리)에
있다. 전기와 열을 한 계열에 섞으면 총량(−1,000 + 3,000 = 2,000)은 남지만
"전기를 얼마 썼고 열을 얼마 냈는가"가 사라지고, 그 상태로도 NFR-102 수지
균형 검사는 통과한다.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.contracts.der import DER, DispatchContext
from core.contracts.units import (
    ENERGY_TOLERANCE_KWH,
    HOURS_PER_YEAR,
    SECONDS_PER_HOUR,
    Money,
    Year,
    steps_per_year,
    to_won,
    won_sum,
)
from core.contracts.validation import ValidationError
from core.der.heatpump import (
    MODE_LOAD_FOLLOWING,
    MODE_NIGHT_STORAGE,
    MODE_PRICE_LINKED,
    HeatBaseline,
    HeatPump,
)
from tests.contract.test_der_contract import DERContractTests

# ── 공통 파라미터 ────────────────────────────────────────────────────
#
# 한 벌의 파라미터로 물리·편익·비용 케이스를 전부 돌린다. 케이스마다 다른
# 설비를 만들면 "어느 설비의 어느 수치인가"가 흩어져, 오라클이 어긋났을 때
# 원인이 파라미터인지 산식인지 구분되지 않는다.

BASE = dict(
    name="세대히트펌프",
    rated_heat_kw=10.0,
    cop_curve=3.0,                      # RC-HP-P1 — COP 고정값
    heat_load_kwh=3000.0,               # 연간 열부하 (spec 표의 3,000 kWh)
    elec_price_won_per_kwh=150.0,
    capex_unit_won_per_kw=1_200_000.0,
    capex_extra_won=500_000.0,          # 부대비 (C-1)
    fixed_om_won=100_000.0,             # C-2 의 A
    escalation_rate=0.02,                 # C-2 의 i
    variable_om_won_per_kwh=5.0,        # C-3
    replacement_cost_won=12_000_000.0,  # C-4
    lifetime=15,
)


def make_hp(**overrides) -> HeatPump:
    params = dict(BASE)
    params.update(overrides)
    return HeatPump(**params)


def annual_ctx(*, temp: float = 7.0, year: int = 1) -> DispatchContext:
    """1년치 컨텍스트. 외기온을 명시하는 이유는 COP가 그 함수이기 때문이다."""
    steps = steps_per_year(SECONDS_PER_HOUR)
    return DispatchContext(
        steps=steps, dt=SECONDS_PER_HOUR, year=year, ambient_temp_c=[temp] * steps
    )


# ── 계약 테스트 상속 (§13.0.3 L3) ────────────────────────────────────

class TestHeatPumpContract(DERContractTests):
    """`DERContractTests` 를 상속해 6개 메서드·9개 속성을 자동 검사한다.

    주의: `make()` 는 **스칼라 열부하**를 쓴다. 계약 테스트가 `steps=24` 짜리
    컨텍스트를 넘기는데, 스텝별 프로파일을 준 인스턴스는 행수 불일치를
    오류로 중단하기 때문이다(FR-301-AC3). 프로파일 경로는 별도로 검사한다.
    """

    def make(self) -> DER:
        return make_hp()


@pytest.mark.req("FR-102-AC1.HeatPump")
def test_tag_is_spec_literal() -> None:
    """`tag` 는 spec 조항 ID `FR-102-AC1.HeatPump` 의 키와 **같은 리터럴**이다.

    여기서 슬러그화하거나 소문자로 바꾸면 NFR-106 레지스트리 순회 검사가
    "케이스 없는 자원"을 못 찾고 헛돈다.
    """
    assert HeatPump.tag == "HeatPump"


# ── FR-104-AC3 수명 종료 (retire) 테스트 ──────────────────────────────

@pytest.mark.req("FR-104-AC3")
def test_heatpump_default_end_of_life_action_is_replace() -> None:
    """1. 기본값은 replace — 아무것도 안 넘기면 결과가 기존과 동일함."""
    hp = make_hp()
    assert hp.end_of_life_action == "replace"
    assert hp.retires_at_end_of_life() is False


@pytest.mark.req("FR-104-AC3")
def test_heatpump_retire_clears_replacement_schedule() -> None:
    """2. retire 면 replacement_schedule() 이 빈다."""
    # lifetime 15년, pump_lifetime 10년설정
    hp = make_hp(
        end_of_life_action="retire",
        pump_lifetime=10,
        pump_replacement_cost_won=1_000_000.0,
    )
    assert hp.retires_at_end_of_life() is True
    sched = hp.replacement_schedule(horizon=40)
    assert sched == {}


@pytest.mark.req("FR-104-AC3")
def test_heatpump_retire_output_zero_after_first_eol() -> None:
    """3. retire 면 첫 수명 종료(min(본체, 부속) = min(15, 10) = 10년) 다음 해(11년차)부터 출력 0.

    손 계산:
    - 1~10년차: 정상 출력 (열부하 3000 kWh 공급)
    - 11년차부터: min(본체15, 펌프10)=10년 수명 만료 후 교체 없이 폐기되므로 열·전기 출력 0 kWh.
    """
    hp = make_hp(
        end_of_life_action="retire",
        pump_lifetime=10,
        pump_replacement_cost_won=1_000_000.0,
    )
    ctx10 = annual_ctx(year=10)
    res10 = hp.dispatch(ctx10)
    assert sum(res10.heat) == pytest.approx(3000.0)

    ctx11 = annual_ctx(year=11)
    res11 = hp.dispatch(ctx11)
    assert sum(res11.heat) == 0.0
    assert sum(res11.electric) == 0.0
    # 미충족 수요는 3000.0 kWh 그대로 남아있어야 함
    assert sum(res11.unmet_heat) == pytest.approx(3000.0)


@pytest.mark.req("FR-104-AC3")
def test_heatpump_retire_output_same_as_replace_until_eol() -> None:
    """4. retire 면 수명 해(10년차)까지는 출력이 replace 와 동일함."""
    hp_replace = make_hp(
        end_of_life_action="replace",
        pump_lifetime=10,
        pump_replacement_cost_won=1_000_000.0,
    )
    hp_retire = make_hp(
        end_of_life_action="retire",
        pump_lifetime=10,
        pump_replacement_cost_won=1_000_000.0,
    )

    ctx10 = annual_ctx(year=10)
    res_rep = hp_replace.dispatch(ctx10)
    res_ret = hp_retire.dispatch(ctx10)

    assert res_ret.heat == res_rep.heat
    assert res_ret.electric == res_rep.electric
    assert res_ret.unmet_heat == res_rep.unmet_heat


@pytest.mark.req("FR-101-AC1")
def test_carries_both_electric_and_heat() -> None:
    """전기·열 **둘 다 참**이다 — 전기를 받아들이고 열을 내보내는 자원이다."""
    hp = make_hp()
    assert hp.carries_electric is True
    assert hp.carries_heat is True
    assert hp.carries_cool is False
    assert hp.consumes_fuel is False


# ── RC-HP-P1 COP 고정값 ──────────────────────────────────────────────

@pytest.mark.req("FR-102-AC1.HeatPump")
def test_rc_hp_p1_fixed_cop_electricity() -> None:
    """COP 3.0, 열부하 3,000 kWh → 소비전력 **1,000.0 kWh** (spec RC-HP-P1)."""
    op = make_hp().simulate(annual_ctx())

    assert op.heat_supplied_kwh == pytest.approx(3000.0, abs=ENERGY_TOLERANCE_KWH)
    assert op.electricity_kwh == pytest.approx(1000.0, abs=ENERGY_TOLERANCE_KWH)
    assert op.unmet_heat_kwh == pytest.approx(0.0, abs=ENERGY_TOLERANCE_KWH)


# ── RC-HP-P2 COP 곡선 보간 (3케이스) ─────────────────────────────────

CURVE = {-10.0: 2.0, 0.0: 3.0, 10.0: 4.0}


@pytest.mark.req("FR-102-AC1.HeatPump")
def test_rc_hp_p2_grid_point_exact() -> None:
    """격자점에서는 **곡선 값 그대로**다. 보간식이 격자점을 비껴가면 곡선
    전체가 미세하게 밀리는데, 결과는 그럴듯해서 눈으로 잡히지 않는다."""
    hp = make_hp(cop_curve=CURVE)
    assert hp.cop_at(-10.0) == pytest.approx(2.0)
    assert hp.cop_at(0.0) == pytest.approx(3.0)
    assert hp.cop_at(10.0) == pytest.approx(4.0)


@pytest.mark.req("FR-102-AC1.HeatPump")
def test_rc_hp_p2_linear_interpolation_between_grid() -> None:
    """격자 사이는 **선형보간**이다."""
    hp = make_hp(cop_curve=CURVE)
    assert hp.cop_at(5.0) == pytest.approx(3.5)
    assert hp.cop_at(-5.0) == pytest.approx(2.5)
    assert hp.cop_at(2.5) == pytest.approx(3.25)


@pytest.mark.req("FR-102-AC1.HeatPump")
def test_rc_hp_p2_clamps_outside_domain() -> None:
    """정의역 **밖은 클램프**한다.

    외삽하면 −30℃에서 COP가 0 이하로 내려가 소비전력이 발산하거나 음수가
    된다. 곡선 밖에서 조용히 외삽하는 것보다 끝점을 유지하는 편이 안전하다.
    """
    hp = make_hp(cop_curve=CURVE)
    assert hp.cop_at(-30.0) == pytest.approx(2.0)
    assert hp.cop_at(40.0) == pytest.approx(4.0)


# ── RC-HP-P3 매체 분리 ───────────────────────────────────────────────

@pytest.mark.req("FR-101-AC4")
def test_rc_hp_p3_media_separation() -> None:
    """전기 수지 **−1,000 kWh**, 열 수지 **+3,000 kWh**. 냉·연료는 0.

    부호 규약(양수=내보냄, 음수=받아들임)에 따라 전기는 음수·열은 양수다.
    두 값을 한 계열에 섞으면 합이 2,000 kWh가 되고, 그 상태로도 총량 검사는
    통과한다 — 그래서 계열별로 각각 확인한다 (spec 도메인 원칙 5-3).
    """
    r = make_hp().dispatch(annual_ctx())

    assert sum(r.electric) == pytest.approx(-1000.0, abs=1e-6)
    assert sum(r.heat) == pytest.approx(3000.0, abs=1e-6)
    assert all(v == 0.0 for v in r.cool)
    assert all(v == 0.0 for v in r.fuel)

    # 부호가 뒤집히면 합산에서 조용히 상쇄된다
    assert all(v <= 0.0 for v in r.electric)
    assert all(v >= 0.0 for v in r.heat)


@pytest.mark.req("FR-101-AC4")
def test_rc_hp_p3_each_balance_closes_independently() -> None:
    """두 수지가 **각각 독립적으로** 균형을 이룬다 (NFR-102 오차 1e-6 kWh).

    전 스텝에서 `열 = 전기 × COP` 가 성립해야 하며, 이 관계가 스텝별로
    성립한다는 것이 곧 두 계열이 섞이지 않았다는 증거다.
    """
    r = make_hp().dispatch(annual_ctx())

    for e, h in zip(r.electric, r.heat, strict=True):
        assert abs(h - (-e) * 3.0) < ENERGY_TOLERANCE_KWH

    # 섞어서 한 계열에 몰아넣었다면 어느 한쪽이 2,000 kWh가 된다
    assert sum(r.electric) != pytest.approx(2000.0, abs=1.0)
    assert sum(r.heat) != pytest.approx(2000.0, abs=1.0)


# ── RC-HP-B1 · B2 열비용 절감 ────────────────────────────────────────

@pytest.mark.req("FR-401-AC2.HeatCostSaving")
def test_rc_hp_b1_saving_against_electric_boiler() -> None:
    """전기보일러 대비 `(3,000 − 1,000) kWh × 150원` = **300,000원/년**."""
    hp = make_hp()
    baseline = HeatBaseline(
        label="전기보일러", efficiency=1.0, fuel_price_won_per_kwh=150.0
    )
    s = hp.heat_cost_saving(baseline=baseline, year=1)

    assert s.baseline_cost == Money(450_000)      # 3,000 / 1.0 × 150
    assert s.hp_electricity_cost == Money(150_000)  # 1,000 × 150
    assert s.saving == Money(300_000)
    assert isinstance(s.saving, Money)


@pytest.mark.req("FR-401-AC2.HeatCostSaving", "FR-705-AC1")
def test_rc_hp_b2_saving_against_gas_boiler_keeps_baseline() -> None:
    """가스보일러 대비 = 기존 연료비 − 신규 전기요금.

    **기준선 자체 비용이 결과에 남아야 한다** (FR-705-AC1, 도메인 원칙 1-2).
    차액만 돌려주면 "무엇에 대비한 절감인가"가 사라지고, 리포트를 읽는 쪽은
    기준선을 확인할 수단이 없어진다.
    """
    hp = make_hp()
    baseline = HeatBaseline(
        label="가스보일러", efficiency=0.85, fuel_price_won_per_kwh=80.0
    )
    s = hp.heat_cost_saving(baseline=baseline, year=1)

    # 3,000 / 0.85 × 80 = 282,352.94… → 282,353원
    assert s.baseline_label == "가스보일러"
    assert s.baseline_heat_kwh == pytest.approx(3000.0, abs=ENERGY_TOLERANCE_KWH)
    assert s.baseline_cost == Money(282_353)
    assert s.hp_electricity_cost == Money(150_000)
    assert s.saving == Money(132_353)
    assert s.saving == Money(s.baseline_cost - s.hp_electricity_cost)


# ── RC-HP-X1 열부하 미충족 ───────────────────────────────────────────

@pytest.mark.req("FR-102-AC1.HeatPump")
def test_rc_hp_x1_unmet_heat_is_flagged() -> None:
    """정격 열출력 초과 요구를 **조용히 충족한 것처럼 처리하지 않는다**.

    정격 1 kW · 연 20,000 kWh 부하 → 시간당 2.283 kWh를 요구받지만 1.0 kWh만
    낼 수 있다. 부족분을 열 수지에 실어 버리면 열비용 절감 편익이 실제보다
    2.3배 크게 잡히고, 그 오류는 화면상 정상으로 보인다.
    """
    hp = make_hp(rated_heat_kw=1.0, heat_load_kwh=20_000.0, aux_heater_kw=0.0)
    op = hp.simulate(annual_ctx())

    assert op.unmet is True
    assert op.heat_demand_kwh == pytest.approx(20_000.0, abs=1e-6)
    assert op.heat_supplied_kwh == pytest.approx(float(HOURS_PER_YEAR), abs=1e-6)
    assert op.unmet_heat_kwh == pytest.approx(20_000.0 - HOURS_PER_YEAR, abs=1e-6)
    # 낼 수 없는 열이 수지에 실리지 않았다
    assert sum(op.result.heat) == pytest.approx(float(HOURS_PER_YEAR), abs=1e-6)


@pytest.mark.req("FR-101-AC4")
def test_rc_hp_x1_unmet_heat_reaches_the_engine_through_dispatch() -> None:
    """미충족이 **`dispatch()` 를 통과해 살아 남는다** (v1.1 계약 개정).

    v1.0 계약의 `DispatchResult` 에는 미충족 계열이 없었다. 그래서 이 자원은
    미충족을 `HeatPumpOperation` 에만 담았고, **엔진은 `dispatch()` 만 보므로
    그 자리에서 사라졌다** — 엔진에 남는 것은 「열이 조금 덜 나온 정상 결과」
    뿐이고, 정격 부족은 어디에도 표시되지 않았다.

    스텝별로 남기는 이유: 연 총량만 있으면 «한겨울 며칠 전량 미충족»과
    «1년 내내 조금씩 부족»이 같은 값이 되어 증설 판단이 성립하지 않는다.
    """
    hp = make_hp(rated_heat_kw=1.0, heat_load_kwh=20_000.0, aux_heater_kw=0.0)
    result = hp.dispatch(annual_ctx())

    assert result.unmet("heat") == pytest.approx(
        [20_000.0 / HOURS_PER_YEAR - 1.0] * HOURS_PER_YEAR, abs=1e-9
    )
    assert result.total_unmet() == pytest.approx(20_000.0 - HOURS_PER_YEAR, abs=1e-6)
    assert result.notes and "미충족" in result.notes[0], (
        "사람이 읽을 진단이 없으면 리포트에 각주를 달 근거가 없다 (RC-HP-X1)"
    )
    # 다른 매체에는 미충족이 없다 — 히트펌프가 못 채운 것은 열이다
    assert result.unmet("electric") == [0.0] * HOURS_PER_YEAR


@pytest.mark.req("FR-105-AC1")
def test_unmet_is_measured_against_the_plan_not_the_hourly_load() -> None:
    """부하 이동 운전에서 미충족은 **계획 대비**로 잰다.

    심야 운전은 주간 부하를 심야에 몰아 생산한다. 미충족을 스텝마다
    `부하 − 공급` 으로 재면 **주간 스텝 전부가 미충족**으로 잡히는데, 그 하루의
    열은 실제로 전량 공급되었다. 그 값을 엔진에 실으면 정격이 충분한 설비가
    「연중 60% 미충족」으로 보고된다.

    합계 항등식도 함께 확인한다 — 스텝별 미충족의 합은 연 미충족과 같아야 한다.
    같지 않으면 두 수치 중 어느 쪽을 믿어야 하는지 알 수 없다.
    """
    hp = make_hp(rated_heat_kw=100.0, heat_load_kwh=8_760.0,
                 aux_heater_kw=0.0, operating_mode=MODE_NIGHT_STORAGE)
    op = hp.simulate(annual_ctx())

    assert op.unmet_heat_kwh == pytest.approx(0.0, abs=1e-6), (
        "정격이 충분하므로 연 미충족은 0이다 (이 전제가 깨지면 아래 검사가 공허하다)"
    )
    assert op.result.total_unmet() == pytest.approx(0.0, abs=1e-6), (
        "부하를 옮긴 것을 미충족으로 세고 있습니다 — 미충족은 계획 대비 부족분입니다"
    )
    assert sum(op.result.heat) == pytest.approx(8_760.0, abs=1e-6)


@pytest.mark.req("FR-102-AC1.HeatPump")
def test_rc_hp_x1_aux_heater_covers_shortfall() -> None:
    """보조 열원(전기 히터)을 두면 부족분을 메우고 미충족이 사라진다.

    보조 열원의 전력은 COP 1.0으로 계상된다 — 저항가열을 히트펌프 COP로
    나누면 전력 소비가 3분의 1로 과소 계상된다.
    """
    hp = make_hp(rated_heat_kw=1.0, heat_load_kwh=20_000.0, aux_heater_kw=5.0)
    op = hp.simulate(annual_ctx())

    assert op.unmet is False
    assert op.unmet_heat_kwh == pytest.approx(0.0, abs=1e-6)
    assert op.hp_heat_kwh == pytest.approx(float(HOURS_PER_YEAR), abs=1e-6)
    assert op.aux_heat_kwh == pytest.approx(20_000.0 - HOURS_PER_YEAR, abs=1e-6)
    assert op.heat_supplied_kwh == pytest.approx(20_000.0, abs=1e-6)
    # 히트펌프분 8,760/3 + 보조분 11,240/1
    assert op.electricity_kwh == pytest.approx(
        HOURS_PER_YEAR / 3.0 + (20_000.0 - HOURS_PER_YEAR), abs=1e-6
    )


# ── RC-ALL-C1 CAPEX ──────────────────────────────────────────────────

# ↓ v0.15 이관 — 이 검사가 보는 것은 메서드의 **존재**(AC2)가 아니라
# **산식**(§13.2.2 C-1~C-3)이다. AC5 가 없던 동안 AC2 를 빌려 인용했다.
@pytest.mark.req("FR-101-AC5")
def test_rc_all_c1_capex_with_vat_separated() -> None:
    """`단가 × 용량 + 부대비`, **부가세는 별도 항목**으로 분리 (§13.2.2 C-1).

    부가세를 본체에 합쳐 두면 프로포마에서 환급·불환급 처리를 나눌 수 없다.

    **세율을 명시해서 넘긴다.** 예전에는 이 자원의 생성자 기본값이 `0.1` 이라
    아무것도 넘기지 않아도 세액이 나왔다 — 그런데 나머지 일곱(자원 5종 +
    공통설비)은 기본값이 `0.0` 이었다. 같은 프로포마에서 히트펌프만 세액이
    잡히고 나머지는 0원이 되는데 **어느 쪽도 오류가 아니었다.** 법정 세율의
    정본은 `docs/assumptions.yaml` 의 `tax.vat_rate` 이며 자원은 그것을
    소유하지 않는다 (NFR-202).
    """
    hp = make_hp(vat_rate=0.10)
    assert hp.capex(year=1) == Money(12_500_000)   # 1,200,000 × 10 + 500,000
    assert hp.capex_vat(year=1) == Money(1_250_000)
    # 초기 투자는 1년차에만 발생한다
    assert hp.capex(year=2) == Money(0)
    assert hp.capex_vat(year=2) == Money(0)

    # 주입하지 않으면 0원이다. **「세율 0%」가 아니라 「주입되지 않음」** 이며,
    # 그 사실이 프로포마에 0원으로 나타나는 것이 이 설계의 대가다 — 누가
    # 주입을 강제하는가는 모델 계층(WP-16 · FR-601)의 몫이다.
    assert make_hp().capex_vat(year=1) == Money(0)


# ── RC-ALL-C2 고정 O&M ───────────────────────────────────────────────

@pytest.mark.req("FR-101-AC2")
def test_rc_all_c2_fixed_om_20year_geometric_sum() -> None:
    """등비수열 합 `A × ((1+i)^n − 1)/i`. A=100,000 i=0.02 n=20 → **2,429,737원**.

    `won_sum` 으로 더하는 이유: 각 항을 반올림한 뒤 더해야 프로포마의 행별
    값을 눈으로 더한 결과와 총계가 일치한다 (NFR-103-M1).
    """
    hp = make_hp()
    assert hp.fixed_om(year=1) == Money(100_000)
    assert hp.fixed_om(year=2) == Money(102_000)

    total = won_sum(hp.fixed_om(year=y) for y in range(1, 21))
    assert total == Money(2_429_737)


# ── RC-ALL-C3 변동 O&M ───────────────────────────────────────────────

# ↓ v0.15 이관 — 이 검사가 보는 것은 메서드의 **존재**(AC2)가 아니라
# **산식**(§13.2.2 C-1~C-3)이다. AC5 가 없던 동안 AC2 를 빌려 인용했다.
@pytest.mark.req("FR-101-AC5")
def test_rc_all_c3_variable_om_on_heat_supplied() -> None:
    """`처리량 × 단가`. HeatPump의 처리량은 **열공급 kWh** (§13.2.2 C-3)."""
    hp = make_hp()
    assert hp.annual_heat_supplied_kwh(year=1) == pytest.approx(
        3000.0, abs=ENERGY_TOLERANCE_KWH
    )
    assert hp.variable_om(year=1) == Money(15_000)   # 3,000 × 5


@pytest.mark.req("FR-101-AC2")
def test_rc_all_c3_throughput_is_heat_not_electricity() -> None:
    """전력량(1,000 kWh)이 아니라 열량(3,000 kWh) 기준임을 못 박는다.

    두 값이 3배 차이라 단가를 잘못 걸면 변동 O&M이 3분의 1로 과소 계상된다.
    """
    hp = make_hp()
    assert hp.variable_om(year=1) != Money(5_000)


# ── RC-ALL-C4 교체비 ─────────────────────────────────────────────────

@pytest.mark.req("FR-104-AC4")
def test_rc_all_c4_replacement_at_year_after_lifetime() -> None:
    """수명 도달 **다음 연도 초**에 계상하고, 부속설비는 본체와 독립이다."""
    hp = make_hp(
        lifetime=15, pump_lifetime=10, pump_replacement_cost_won=1_500_000.0
    )
    schedule = hp.replacement_schedule(horizon=20)

    assert schedule == {11: Money(1_500_000), 16: Money(12_000_000)}


@pytest.mark.req("FR-104-AC4")
def test_rc_all_c4_no_replacement_beyond_horizon() -> None:
    """수명이 분석기간을 넘으면 교체는 계상되지 않는다."""
    assert make_hp(lifetime=25).replacement_schedule(horizon=20) == {}


# ── RC-ALL-C5 잔존가치 ───────────────────────────────────────────────

@pytest.mark.req("FR-104-AC5")
def test_rc_all_c5_salvage_proportional_to_remaining_life() -> None:
    """`취득가 × 잔존수명 / 총수명` 을 최종연도에 계상 후 할인 (§13.2.2 C-5).

    할인은 재무 계층(`core/cba/`)의 몫이므로 자원은 **미할인 명목액**을
    돌려주고, 여기서는 오라클 산식 전체가 재현되는지를 확인한다.
    """
    hp = make_hp(lifetime=25)
    # 12,500,000 × 5/25 = 2,500,000원
    assert hp.salvage_value(year=20) == Money(2_500_000)

    discounted = to_won(Decimal(hp.salvage_value(year=20)) / Decimal("1.045") ** 20)
    assert discounted == Money(1_036_607)


@pytest.mark.req("FR-104-AC5")
def test_rc_all_c5_salvage_resets_after_replacement() -> None:
    """교체가 있었으면 **교체 취득가와 교체 이후 경과년수**로 계산한다.

    교체를 무시하면 20년차 잔존가치가 0으로 잡혀, 16년차에 새로 산 설비의
    가치가 통째로 사라진다 — 회수기간이 실제보다 길게 나온다 (원칙 4-3).
    """
    hp = make_hp(lifetime=15)   # 16년차 교체, 교체비 12,000,000원
    # 16~20년 5년 사용 → 잔존 10년 / 총 15년
    assert hp.salvage_value(year=20) == Money(8_000_000)


# ── FR-104-AC1 성능 저하 ─────────────────────────────────────────────

@pytest.mark.req("FR-104-AC1")
def test_degradation_reduces_cop_over_years() -> None:
    """연 `degradation_rate` 만큼 COP가 낮아진다 — 같은 열을 내는 데 전력이 더 든다."""
    hp = make_hp(degradation_rate=0.01)
    assert hp.cop_at(7.0, year=1) == pytest.approx(3.0)
    assert hp.cop_at(7.0, year=11) == pytest.approx(3.0 * 0.99**10)

    op = hp.simulate(annual_ctx(year=11))
    assert op.electricity_kwh > 1000.0


# ── FR-105-AC1 운전 방법 선언 ────────────────────────────────────────

@pytest.mark.req("FR-105-AC1")
def test_operating_modes_are_declared_on_the_class() -> None:
    """자원 클래스가 자신이 지원하는 운전 방법 목록을 선언한다."""
    assert HeatPump.OPERATING_MODES == (
        MODE_LOAD_FOLLOWING, MODE_NIGHT_STORAGE, MODE_PRICE_LINKED
    )
    assert make_hp().operating_mode == MODE_LOAD_FOLLOWING

    with pytest.raises(ValueError, match="운전 방법"):
        make_hp(operating_mode="아무거나")


@pytest.mark.req("FR-105-AC1")
def test_night_storage_mode_shifts_production_to_night() -> None:
    """축열조 활용 심야 운전은 **심야 시간대에만** 열을 생산한다."""
    hp = make_hp(operating_mode=MODE_NIGHT_STORAGE)
    r = hp.dispatch(annual_ctx())

    daytime = [i for i in range(HOURS_PER_YEAR) if 8 <= i % 24 < 23]
    assert all(r.heat[i] == 0.0 for i in daytime)
    assert all(r.electric[i] == 0.0 for i in daytime)
    assert sum(r.heat) == pytest.approx(3000.0, abs=1e-6)


@pytest.mark.req("FR-105-AC1")
def test_price_linked_mode_runs_in_cheapest_hours() -> None:
    """전력요금 연동은 하루 중 **싼 시간대**에 운전한다."""
    prices = [80.0 if i % 24 < 6 else 200.0 for i in range(HOURS_PER_YEAR)]
    hp = make_hp(
        operating_mode=MODE_PRICE_LINKED,
        price_profile_won_per_kwh=prices,
        price_linked_hours=6,
    )
    r = hp.dispatch(annual_ctx())

    expensive = [i for i in range(HOURS_PER_YEAR) if i % 24 >= 6]
    assert all(r.heat[i] == 0.0 for i in expensive)
    assert sum(r.heat) == pytest.approx(3000.0, abs=1e-6)


@pytest.mark.req("FR-105-AC1")
def test_price_linked_mode_requires_price_profile() -> None:
    """요금 시계열 없이 요금 연동 운전을 선택하면 **생성 시점에** 거부한다.

    조용히 열부하 추종으로 되돌리면 사용자는 요금 연동으로 돌았다고 믿는다.
    """
    with pytest.raises(ValueError, match="요금"):
        make_hp(operating_mode=MODE_PRICE_LINKED)


# ── 입력 검증 ────────────────────────────────────────────────────────

@pytest.mark.req("FR-301-AC3")
def test_heat_load_profile_step_mismatch_is_an_error() -> None:
    """스텝별 프로파일을 준 경우 행수 불일치는 **명확한 오류로 중단**한다."""
    hp = make_hp(heat_load_kwh=[1.0] * HOURS_PER_YEAR)
    with pytest.raises(ValueError, match="스텝"):
        hp.dispatch(DispatchContext(steps=24, dt=SECONDS_PER_HOUR, year=1))


@pytest.mark.req("FR-102-AC1.HeatPump")
def test_heat_load_profile_is_used_as_given() -> None:
    """프로파일을 주면 그대로 쓴다 — 균등 분배로 덮어쓰지 않는다."""
    profile = [0.0] * HOURS_PER_YEAR
    for i in range(0, HOURS_PER_YEAR, 2):
        profile[i] = 1.0
    hp = make_hp(heat_load_kwh=profile)
    r = hp.dispatch(annual_ctx())

    assert sum(r.heat) == pytest.approx(float(HOURS_PER_YEAR // 2), abs=1e-6)
    assert all(r.heat[i] == 0.0 for i in range(1, HOURS_PER_YEAR, 2))


@pytest.mark.req("FR-102-AC1.HeatPump")
def test_rejects_nonpositive_rating_and_cop() -> None:
    """정격 열출력·COP가 0 이하이면 소비전력이 발산하거나 음수가 된다."""
    with pytest.raises(ValueError, match="정격 열출력"):
        make_hp(rated_heat_kw=0.0)
    with pytest.raises(ValueError, match="COP"):
        make_hp(cop_curve=0.0)
    with pytest.raises(ValueError, match="COP"):
        make_hp(cop_curve={0.0: 3.0, 10.0: -1.0})


@pytest.mark.req("FR-102-AC1.HeatPump")
def test_rejects_context_with_different_resolution() -> None:
    """자원의 `dt` 와 다른 해상도의 컨텍스트는 거부한다.

    연간 스텝 수가 달라지면 스칼라 열부하의 균등 분배가 통째로 어긋난다.
    """
    hp = make_hp()
    with pytest.raises(ValueError, match="해상도"):
        hp.dispatch(DispatchContext(steps=96, dt=SECONDS_PER_HOUR // 4, year=1))


@pytest.mark.req("FR-102-AC1.HeatPump")
def test_rejects_bool_heat_load() -> None:
    """열부하 자리의 `bool` 은 **오류다** — 조용히 0·1 kWh 가 되지 않는다.

    `bool` 은 `int` 의 하위 클래스라 스칼라 분기로 들어오면 «연간 열부하
    1 kWh» 가 되고, 그 값은 그럴듯하다. 프로파일 분기로 가면 *"'bool' object
    is not iterable"* 이라는 무관해 보이는 메시지가 뜬다. 어느 쪽도 «열부하
    자리에 플래그가 들어왔다» 를 말해 주지 않는다.

    `to_won()` 이 금액 자리의 `bool` 을 거부하는 것과 같은 판단이다.
    """
    with pytest.raises(TypeError, match="bool"):
        make_hp(heat_load_kwh=True)
    with pytest.raises(TypeError, match="bool"):
        make_hp(heat_load_kwh=False)


@pytest.mark.req("FR-101-AC2")
def test_annual_operation_enforces_one_based_year() -> None:
    """`annual_operation()` 의 연도는 **1-base 규약을 통과한다** (`Year`).

    0을 넘기면 그 자리에서 멈춰야 한다. 통과시키면 20년 분석이 19년이 되거나
    잔존가치가 한 해 밀리며, **두 오류 모두 결과가 그럴듯해 눈으로는 잡히지
    않는다** — `Year` 가 존재하는 이유 그대로다.

    캐시 키가 `Year` 로 바뀌어도 정수 조회가 그대로 동작하는 것도 함께
    고정한다(`Year(1) == 1`). 깨지면 연도마다 운전을 다시 풀게 되고, 그 손실은
    느려지는 것으로만 나타나 원인을 찾기 어렵다.
    """
    hp = make_hp()
    with pytest.raises(ValueError, match="1부터"):
        hp.annual_operation(0)
    with pytest.raises(ValueError, match="1부터"):
        hp.annual_operation(-1)

    first = hp.annual_operation(1)
    assert hp.annual_operation(Year(1)) is first, (
        "Year 로 조회했더니 다른 객체가 나왔습니다 — 캐시 키가 int 와 Year 를 "
        "다른 것으로 보고 있습니다"
    )


# ── NFR-303 입력 검증 오류의 3요소 구조 (ValidationError) ──────────────
#
# 「예외가 났다」만 보지 않는다 — field·reason·action 을 as_dict() 로 꺼내
# 구조를 단언한다 (§13.0 R22-WP32A).

@pytest.mark.req("NFR-303-M1")
def test_baseline_empty_label_carries_field_reason_action() -> None:
    """기준선 이름이 비면 field·reason·action 셋을 갖춘 구조로 거부한다."""
    with pytest.raises(ValidationError) as caught:
        HeatBaseline(label="", efficiency=1.0, fuel_price_won_per_kwh=150.0)
    parts = caught.value.as_dict()
    assert parts["field"] == "heatpump.baseline_label"
    assert "이름" in parts["reason"]
    assert parts["action"]


@pytest.mark.req("NFR-303-M1")
def test_baseline_nonpositive_efficiency_carries_field_reason_action() -> None:
    with pytest.raises(ValidationError) as caught:
        HeatBaseline(label="전기보일러", efficiency=0.0, fuel_price_won_per_kwh=150.0)
    parts = caught.value.as_dict()
    assert parts["field"] == "heatpump.baseline_efficiency"
    assert "0.0" in parts["reason"]
    assert "0" in parts["action"]


@pytest.mark.req("NFR-303-M1")
def test_baseline_negative_fuel_price_carries_field_reason_action() -> None:
    with pytest.raises(ValidationError) as caught:
        HeatBaseline(label="전기보일러", efficiency=1.0, fuel_price_won_per_kwh=-1.0)
    parts = caught.value.as_dict()
    assert parts["field"] == "heatpump.baseline_fuel_price_won_per_kwh"
    assert "-1.0" in parts["reason"]


@pytest.mark.req("NFR-303-M1")
def test_cop_curve_empty_carries_field_reason_action() -> None:
    with pytest.raises(ValidationError) as caught:
        make_hp(cop_curve={})
    parts = caught.value.as_dict()
    assert parts["field"] == "heatpump.cop_curve"
    assert "비어" in parts["reason"]


@pytest.mark.req("NFR-303-M1")
def test_cop_curve_duplicate_temp_carries_field_reason_action() -> None:
    with pytest.raises(ValidationError) as caught:
        make_hp(cop_curve=[(0.0, 3.0), (0.0, 4.0)])
    parts = caught.value.as_dict()
    assert parts["field"] == "heatpump.cop_curve"
    assert "0.0" in parts["reason"]


@pytest.mark.req("NFR-303-M1")
def test_cop_curve_nonpositive_value_carries_field_reason_action() -> None:
    with pytest.raises(ValidationError) as caught:
        make_hp(cop_curve={0.0: 3.0, 10.0: -1.0})
    parts = caught.value.as_dict()
    assert parts["field"] == "heatpump.cop_curve"
    assert "10.0" in parts["reason"]
    assert "-1.0" in parts["reason"]


@pytest.mark.req("NFR-303-M1")
@pytest.mark.parametrize(
    ("kwarg", "field"),
    [
        ("price_profile_won_per_kwh", "heatpump.price_profile_won_per_kwh"),
        ("annual_ambient_temp_c", "heatpump.annual_ambient_temp_c"),
    ],
)
def test_annual_series_wrong_length_carries_field_and_dv4(kwarg: str, field: str) -> None:
    """가격·외기온 시계열이 1년치가 아니면 DV-4 로 거부하고, 공유 헬퍼라도
    필드는 호출부마다 갈린다 (R21 이 확정한 「field 를 인자로」 관례)."""
    with pytest.raises(ValidationError) as caught:
        make_hp(**{kwarg: [1.0] * 100})
    parts = caught.value.as_dict()
    assert parts["field"] == field
    assert parts["rule"] == "DV-4"
    assert "100" in parts["reason"]
    assert "8760" in parts["action"] or "35040" in parts["action"]


@pytest.mark.req("NFR-303-M1")
def test_heat_load_profile_wrong_length_carries_field_and_dv4() -> None:
    with pytest.raises(ValidationError) as caught:
        make_hp(heat_load_kwh=[1.0] * 100)
    parts = caught.value.as_dict()
    assert parts["field"] == "heatpump.heat_load_kwh"
    assert parts["rule"] == "DV-4"


@pytest.mark.req("NFR-303-M1")
def test_rated_heat_kw_nonpositive_carries_field_reason_action() -> None:
    with pytest.raises(ValidationError) as caught:
        make_hp(rated_heat_kw=0.0)
    parts = caught.value.as_dict()
    assert parts["field"] == "heatpump.rated_heat_kw"
    assert "0.0" in parts["reason"]
    assert "0보다 큰" in parts["action"]


@pytest.mark.req("NFR-303-M1")
def test_aux_heater_kw_negative_carries_field_reason_action() -> None:
    with pytest.raises(ValidationError) as caught:
        make_hp(aux_heater_kw=-1.0)
    parts = caught.value.as_dict()
    assert parts["field"] == "heatpump.aux_heater_kw"
    assert "-1.0" in parts["reason"]


@pytest.mark.req("NFR-303-M1")
def test_price_linked_without_profile_carries_field_reason_action() -> None:
    with pytest.raises(ValidationError) as caught:
        make_hp(operating_mode=MODE_PRICE_LINKED)
    parts = caught.value.as_dict()
    assert parts["field"] == "heatpump.price_profile_won_per_kwh"
    assert "요금" in parts["reason"]


@pytest.mark.req("NFR-303-M1")
def test_price_linked_hours_nonpositive_carries_field_reason_action() -> None:
    with pytest.raises(ValidationError) as caught:
        make_hp(
            operating_mode=MODE_PRICE_LINKED,
            price_profile_won_per_kwh=[100.0] * HOURS_PER_YEAR,
            price_linked_hours=0,
        )
    parts = caught.value.as_dict()
    assert parts["field"] == "heatpump.price_linked_hours"
    assert "0" in parts["reason"]


@pytest.mark.req("NFR-303-M1")
def test_heat_load_scalar_negative_carries_field_reason_action() -> None:
    with pytest.raises(ValidationError) as caught:
        make_hp(heat_load_kwh=-1.0)
    parts = caught.value.as_dict()
    assert parts["field"] == "heatpump.heat_load_kwh"
    assert "-1.0" in parts["reason"]


@pytest.mark.req("NFR-303-M1")
def test_heat_load_series_negative_carries_field_reason_action() -> None:
    profile = [1.0] * HOURS_PER_YEAR
    profile[0] = -5.0
    with pytest.raises(ValidationError) as caught:
        make_hp(heat_load_kwh=profile)
    parts = caught.value.as_dict()
    assert parts["field"] == "heatpump.heat_load_kwh"
    assert "음수" in parts["reason"]


@pytest.mark.req("NFR-303-M1")
def test_replacement_schedule_horizon_nonpositive_carries_field_reason_action() -> None:
    hp = make_hp()
    with pytest.raises(ValidationError) as caught:
        hp.replacement_schedule(horizon=0)
    parts = caught.value.as_dict()
    assert parts["field"] == "heatpump.horizon"
    assert "0" in parts["reason"]
    assert "1 이상" in parts["action"]
    assert parts["rule"] is None
