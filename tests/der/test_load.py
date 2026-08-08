"""`Load` 전기부하 자원 테스트 — WP-1e / spec FR-102-AC1.Load · §13.2.2 · §13.2.3.

**부하 자원 테스트가 다른 자원과 다른 점은 「없음」을 고정한다는 것이다.**
`RC-LD-B0` 은 값을 맞추는 케이스가 아니라 *편익이 생기지 않는다* 를 못 박는
케이스다. 부하에 편익을 붙이면 그것은 PV 자가소비 절감 등 **다른 자원의
편익을 이중 계상**하는 것이 되고(FR-402-AC2.C), 그 이중 계상은 총계가 커지는
방향으로만 작용해 회수기간을 짧게 만든다. 화면상으로는 정상이다.

오라클 출처는 전부 spec 표다 — 여기서 다시 계산해 적지 않는다(§13.2.4-5).
"""

from __future__ import annotations

import math

import pytest

from core.contracts.der import DER, DispatchContext
from core.contracts.units import HOURS_PER_YEAR, Money, to_won, won_sum
from core.der.load import Load
from tests.contract.test_der_contract import DERContractTests

# §13.2.3 RC-LD-P1 오라클: 4인 가구 월 350 kWh (§13.3 1번 근거)
MONTHLY_KWH = 350.0
ANNUAL_KWH = 4_200.0

# §13.2.2 C-2 오라클: A=100,000 i=0.02 n=20 → 2,429,737원
OM_A = 100_000.0
OM_I = 0.02
OM_N = 20
OM_20Y_TOTAL = Money(2_429_737)


def make_load(**overrides) -> Load:
    """기본 부하 — 월 350 kWh, 설비비 없음."""
    params: dict = {"name": "가구부하", "monthly_kwh": MONTHLY_KWH}
    params.update(overrides)
    return Load(**params)


# ── 계약 테스트 상속 (§13.0.3 L3) ────────────────────────────────────

class TestLoadContract(DERContractTests):
    """`DERContractTests` 를 상속받아 6메서드·9속성·매체 플래그를 전부 검사한다.

    비용 파라미터를 일부러 채워 넣는다 — 전부 0인 인스턴스로 계약을 통과시키면
    "0원을 돌려주는 메서드"만 검증되고, 금액이 실제로 흐를 때의 정수 원 규약
    (NFR-103)은 검사되지 않은 채 초록불이 된다.
    """

    def make(self) -> DER:
        return make_load(
            capacity_kw=3.0,
            unit_cost_won_per_kw=100_000.0,
            incidental_cost_won=50_000.0,
            fixed_om_won_per_year=OM_A,
            variable_om_won_per_kwh=5.0,
            inflation_rate=OM_I,
            subcomponents=[("계량기", 12, 300_000.0)],
        )


# ── RC-LD-P1 월사용량 → 8760 전개 ────────────────────────────────────

@pytest.mark.req("FR-102-AC1.Load")
def test_monthly_usage_expands_to_8760_preserving_total() -> None:
    """월 350 kWh × 12 = 4,200.0 kWh, 전개 후 합계 일치 (오차 1e-9).

    **전개는 총량 보존이 전부다.** 프로파일 모양이 틀리면 시간대별 편익이
    틀리지만, 총량이 틀리면 연간 요금 자체가 틀린다. 후자는 모든 하류 계산을
    같은 방향으로 밀어내므로 민감도 분석으로도 드러나지 않는다.
    """
    load = make_load()

    assert load.annual_energy_kwh(year=1) == pytest.approx(ANNUAL_KWH, abs=1e-9)

    series = load.step_series_kwh(year=1)
    assert len(series) == HOURS_PER_YEAR
    # math.fsum 을 쓰는 이유: 8760항 누적합의 부동소수 오차만으로 1e-9 를 넘길 수
    # 있다(항당 eps 누적). 합산 방식 탓에 오라클이 깨지면 원인을 오해한다.
    assert math.fsum(series) == pytest.approx(ANNUAL_KWH, abs=1e-9)
    assert all(v >= 0.0 for v in series), "step_series_kwh 는 소비량 크기(양수)다"


@pytest.mark.req("FR-102-AC1.Load")
def test_monthly_totals_are_preserved_per_month_not_just_annually() -> None:
    """월별 총량이 각각 보존된다 — 연 합계만 맞추면 계절이 뒤섞인다.

    표준 프로파일 가중치를 연 전체로 한 번에 정규화하면 가중치가 큰 달이 다른
    달의 사용량을 빨아들인다. 연 합계는 그대로라 눈에 띄지 않는다.
    """
    monthly = [100.0 * (m + 1) for m in range(12)]
    # 1월에만 큰 가중치를 준 프로파일 — 정규화가 잘못되면 1월이 연간을 삼킨다
    shape = [10.0 if i < 31 * 24 else 1.0 for i in range(HOURS_PER_YEAR)]
    load = make_load(monthly_kwh=monthly, shape=shape)

    got = load.monthly_energy_kwh(year=1)
    assert got == pytest.approx(monthly, abs=1e-9)
    assert math.fsum(load.step_series_kwh(year=1)) == pytest.approx(
        math.fsum(monthly), abs=1e-9
    )


@pytest.mark.req("FR-102-AC1.Load")
def test_hourly_series_input_path() -> None:
    """8760 시계열 직접 입력 경로 (FR-102-AC1.Load 의 다른 한 갈래)."""
    series = [0.5] * HOURS_PER_YEAR
    load = make_load(monthly_kwh=None, hourly_kwh=series)
    assert load.annual_energy_kwh(year=1) == pytest.approx(4_380.0, abs=1e-9)


@pytest.mark.req("FR-102-AC1.Load")
def test_dispatch_puts_consumption_on_electric_as_negative() -> None:
    """부하는 **받아들이므로 음수**다 (DispatchResult 부호 규약).

    부호를 뒤집으면 자원 합산에서 조용히 상쇄된다 — 부하 4,200 kWh 를 양수로
    실으면 PV 4,200 kWh 와 더해져 순 8,400 kWh 발전으로 보인다.
    """
    load = make_load()
    ctx = DispatchContext(steps=HOURS_PER_YEAR, dt=load.dt, year=1)
    result = load.dispatch(ctx)

    assert all(v <= 0.0 for v in result.electric)
    assert math.fsum(result.electric) == pytest.approx(-ANNUAL_KWH, abs=1e-9)
    assert not any(result.heat), "carries_heat=False 인데 열 계열에 값이 실렸다"
    assert not any(result.cool)
    assert not any(result.fuel)


@pytest.mark.req("FR-102-AC1.Load")
def test_media_flags_only_electric() -> None:
    load = make_load()
    assert load.tag == "Load", "spec 조항 ID `FR-102-AC1.Load` 와 같은 리터럴이어야 한다"
    assert load.carries_electric is True
    assert load.carries_heat is False
    assert load.carries_cool is False
    assert load.consumes_fuel is False


# ── RC-LD-P2 연간 증가율 ─────────────────────────────────────────────

@pytest.mark.req("FR-102-AC1.Load")
def test_annual_growth_compounds_from_year_one() -> None:
    """n년차 = 4,200 × (1+g)^(n−1). **1년차 지수는 0** 이다.

    0-base/1-base 혼동은 연 2% 증가에서 20년 뒤 2% 차이를 만든다 — 그럴듯해서
    눈으로는 잡히지 않는다(`Year` 가 타입으로 막는 것과 같은 오류 유형).
    """
    g = 0.02
    load = make_load(annual_growth_rate=g)

    for n in (1, 2, 5, 20):
        expected = ANNUAL_KWH * (1.0 + g) ** (n - 1)
        assert load.annual_energy_kwh(year=n) == pytest.approx(expected, rel=1e-12)

    assert load.annual_energy_kwh(year=1) == pytest.approx(ANNUAL_KWH, abs=1e-9)


@pytest.mark.req("FR-102-AC1.Load")
def test_growth_is_not_degradation_rate() -> None:
    """증가율을 `degradation_rate` 로 표현하지 않는다.

    계약의 `degradation_rate` 는 0~1 소수이며 **감소**를 뜻한다(FR-101-AC1).
    성장을 여기에 실으면 부호가 반대인 값이 열화 계산식에 들어간다.
    """
    load = make_load(annual_growth_rate=0.02)
    assert load.degradation_rate == 0.0
    assert load.annual_growth_rate == 0.02


@pytest.mark.req("FR-102-AC1.Load")
def test_dispatch_scales_with_year() -> None:
    load = make_load(annual_growth_rate=0.03)
    ctx = DispatchContext(steps=HOURS_PER_YEAR, dt=load.dt, year=5)
    total = math.fsum(load.dispatch(ctx).electric)
    assert total == pytest.approx(-ANNUAL_KWH * 1.03**4, rel=1e-12)


# ── RC-LD-B0 편익 없음 ───────────────────────────────────────────────

@pytest.mark.req("FR-102-AC1.Load")
def test_load_produces_no_value_streams() -> None:
    """**RC-LD-B0** — 부하 자원은 편익을 생성하지 않는다.

    부하가 만드는 것은 *기준선 요금*이지 편익이 아니다. 「부하가 줄어서 생긴
    절감」은 그 절감을 일으킨 자원(PV 자가소비·히트펌프)의 편익이며, 부하에도
    붙이면 같은 화폐 흐름이 두 번 계상된다(FR-402-AC2.C 동일 효과 이중 화폐화).
    """
    load = make_load()
    assert load.value_streams() == []


@pytest.mark.req("FR-102-AC1.Load")
def test_baseline_cost_is_reported_but_is_not_a_benefit() -> None:
    """기준선 요금은 산출하되 **편익 목록에는 들어가지 않는다** (FR-607)."""
    load = make_load()
    baseline = load.baseline_energy_cost(year=1, tariff_won_per_kwh=150.0)
    assert baseline == to_won(ANNUAL_KWH * 150.0)
    assert isinstance(baseline, Money)
    assert load.value_streams() == []


# ── 경계·위반 ────────────────────────────────────────────────────────

@pytest.mark.req("FR-102-AC1.Load")
def test_rejects_negative_usage() -> None:
    with pytest.raises(ValueError, match="음수"):
        make_load(monthly_kwh=-1.0)
    with pytest.raises(ValueError, match="음수"):
        make_load(monthly_kwh=None, hourly_kwh=[1.0] * (HOURS_PER_YEAR - 1) + [-1.0])


@pytest.mark.req("FR-102-AC1.Load")
def test_rejects_growth_rate_out_of_range() -> None:
    """%를 소수로 정규화하지 않고 넘긴 경우를 잡는다 (§7.5 비율)."""
    with pytest.raises(ValueError, match="증가율"):
        make_load(annual_growth_rate=2.0)
    with pytest.raises(ValueError, match="증가율"):
        make_load(annual_growth_rate=-1.0)


@pytest.mark.req("FR-102-AC1.Load")
def test_rejects_ambiguous_or_missing_input_path() -> None:
    """두 입력 경로 중 **정확히 하나**를 쓴다.

    둘 다 주면 어느 쪽이 채택됐는지 결과만 보고는 알 수 없고, 둘 다 없으면
    0 kWh 부하가 조용히 성립해 요금이 통째로 사라진다.
    """
    with pytest.raises(ValueError, match="하나"):
        make_load(hourly_kwh=[0.5] * HOURS_PER_YEAR)
    with pytest.raises(ValueError, match="하나"):
        make_load(monthly_kwh=None)


@pytest.mark.req("FR-102-AC1.Load")
def test_rejects_series_length_mismatch() -> None:
    """시계열 행수 불일치는 명확한 오류로 중단한다 (FR-301-AC3)."""
    with pytest.raises(ValueError, match="행"):
        make_load(monthly_kwh=None, hourly_kwh=[0.5] * 8759)
    with pytest.raises(ValueError, match="12"):
        make_load(monthly_kwh=[350.0] * 11)
    with pytest.raises(ValueError, match="행"):
        make_load(shape=[1.0] * 100)


@pytest.mark.req("FR-102-AC1.Load")
def test_dispatch_rejects_mismatched_resolution_and_oversized_window() -> None:
    load = make_load()
    with pytest.raises(ValueError, match="해상도"):
        load.dispatch(DispatchContext(steps=24, dt=900, year=1))
    with pytest.raises(ValueError, match="스텝"):
        load.dispatch(DispatchContext(steps=HOURS_PER_YEAR + 1, dt=load.dt, year=1))


# ── RC-ALL-C1 CAPEX (§13.2.2) ────────────────────────────────────────

@pytest.mark.req("FR-101-AC2")
def test_capex_unit_times_capacity_plus_incidental_with_vat_separated() -> None:
    """C-1: `단가 × 용량 + 부대비`, 부가세는 **별도 항목**.

    부가세를 본체에 섞으면 관점별 계상(FR-704)에서 분리할 수 없다 — 사업자에게는
    매입세액 공제 대상이지만 사회 관점에서는 이전지출이다.
    """
    load = make_load(
        capacity_kw=3.0, unit_cost_won_per_kw=1_500_000.0, vat_rate=0.1
    )
    assert load.capex(year=1) == Money(4_500_000)
    assert load.capex_vat(year=1) == Money(450_000)
    assert load.capex(year=2) == Money(0), "초기 투자는 1년차에만 발생한다"

    with_incidental = make_load(
        capacity_kw=3.0, unit_cost_won_per_kw=1_500_000.0, incidental_cost_won=200_000.0
    )
    assert with_incidental.capex(year=1) == Money(4_700_000)


@pytest.mark.req("FR-101-AC2")
def test_zero_cost_load_returns_money_zero_for_all_five() -> None:
    """설비비 0인 부하도 다섯 메서드가 **`Money(0)` 을 정상 반환**한다.

    계약상 추상 메서드이므로 구현 자체가 의무다. 0원과 「미구현」이 구분되지
    않으면 비용이 조용히 사라져도 아무도 모른다 (der.py 모듈 주석의 그 문제).
    """
    load = make_load()
    for name in ("capex", "capex_vat", "fixed_om", "variable_om", "salvage_value"):
        value = getattr(load, name)(year=1)
        assert value == Money(0)
        assert isinstance(value, Money), f"{name}() 가 Money 가 아니다"
    assert load.replacement_schedule(horizon=20) == {}


# ── RC-ALL-C2 고정 O&M ───────────────────────────────────────────────

@pytest.mark.req("FR-101-AC2")
def test_fixed_om_20y_total_matches_geometric_series() -> None:
    """C-2: `A × ((1+i)^n − 1)/i`. A=100,000 i=0.02 n=20 → **2,429,737원**.

    연차별 값을 각각 반올림해 더한 값(`won_sum`)과 해석해를 함께 본다 —
    두 경로가 갈리면 프로포마 행 합계와 총계가 어긋난다 (NFR-103-M1).
    """
    load = make_load(fixed_om_won_per_year=OM_A, inflation_rate=OM_I)

    closed_form = OM_A * ((1.0 + OM_I) ** OM_N - 1.0) / OM_I
    assert to_won(closed_form) == OM_20Y_TOTAL

    yearly = [load.fixed_om(year=y) for y in range(1, OM_N + 1)]
    assert yearly[0] == Money(100_000), "1년차는 물가상승 미적용 (지수 0)"
    assert won_sum(yearly) == OM_20Y_TOTAL


# ── RC-ALL-C3 변동 O&M ───────────────────────────────────────────────

@pytest.mark.req("FR-101-AC2")
def test_variable_om_is_throughput_times_unit_price() -> None:
    """C-3: `처리량 × 단가`. 부하의 처리량은 **연간 소비 kWh** 다."""
    load = make_load(variable_om_won_per_kwh=5.0)
    assert load.variable_om(year=1) == to_won(ANNUAL_KWH * 5.0)

    growing = make_load(variable_om_won_per_kwh=5.0, annual_growth_rate=0.02)
    assert growing.variable_om(year=3) == to_won(ANNUAL_KWH * 1.02**2 * 5.0)


# ── RC-ALL-C4 교체비 ─────────────────────────────────────────────────

@pytest.mark.req("FR-104-AC3")
@pytest.mark.req("FR-104-AC4")
def test_replacement_is_booked_at_the_year_after_life_is_reached() -> None:
    """C-4: 수명 도달 **다음 연도 초**. 부속설비는 본체와 독립 스케줄.

    한 해 밀리면 할인 계수가 한 해분 달라진다 — 20년 분석에서 교체비 300만원의
    4.5% ≈ 13만원이 조용히 이동한다.
    """
    load = make_load(
        lifetime=25,
        capacity_kw=3.0,
        unit_cost_won_per_kw=1_500_000.0,
        subcomponents=[("계량기", 12, 300_000.0)],
    )
    schedule = load.replacement_schedule(horizon=20)
    assert schedule == {13: Money(300_000)}, "12년 수명 → 13년차 계상, 본체(25년)는 없음"

    # 분석기간을 늘리면 본체 교체와 부속설비 2회차가 함께 드러난다
    longer = load.replacement_schedule(horizon=30)
    assert longer[13] == Money(300_000)
    assert longer[25] == Money(300_000), "12년 주기 2회차 = 25년차"
    assert longer[26] == Money(4_500_000), "본체 25년 → 26년차"


@pytest.mark.req("FR-104-AC3")
def test_replacement_schedule_stays_inside_horizon() -> None:
    load = make_load(subcomponents=[("계량기", 12, 300_000.0)])
    assert load.replacement_schedule(horizon=12) == {}
    with pytest.raises(ValueError, match="분석기간"):
        load.replacement_schedule(horizon=0)


# ── RC-ALL-C5 잔존가치 ───────────────────────────────────────────────

@pytest.mark.req("FR-104-AC5")
def test_salvage_value_is_prorated_by_remaining_life_and_not_discounted() -> None:
    """C-5: `취득가 × 잔존수명/총수명` 을 최종연도에 계상.

    **할인은 여기서 하지 않는다.** 자원은 할인율을 모르며(FR-101-AC3), 할인을
    자원과 재무 계층 두 곳에서 하면 어느 쪽이 이미 했는지 판정할 수 없다.
    §13.2.2 C-5 의 373,179원은 재무 계층이 900,000원을 20년 할인한 결과다.
    """
    load = make_load(
        lifetime=25, capacity_kw=3.0, unit_cost_won_per_kw=1_500_000.0
    )
    assert load.salvage_value(year=20) == Money(900_000)
    assert load.salvage_value(year=25) == Money(0), "수명 만료 시점 잔존가치 0"

    # 재무 계층이 할인하면 spec 의 373,179원이 된다 — 여기서는 확인만 한다
    assert to_won(float(load.salvage_value(year=20)) / 1.045**20) == Money(373_179)


@pytest.mark.req("FR-104-AC5")
def test_salvage_counts_subcomponents_on_their_own_clock() -> None:
    """부속설비는 자기 수명으로 잔존가치를 갖는다 (FR-104-AC4 와 짝).

    12년 수명 계량기는 13년차에 새로 설치되므로, 20년차 기준 잔존수명은
    12 − (20−13+1) = 4년이다.
    """
    load = make_load(
        lifetime=25,
        capacity_kw=3.0,
        unit_cost_won_per_kw=1_500_000.0,
        subcomponents=[("계량기", 12, 300_000.0)],
    )
    expected = to_won(4_500_000.0 * 5 / 25 + 300_000.0 * 4 / 12)
    assert load.salvage_value(year=20) == expected


# ── NFR-206 파일 규모 ────────────────────────────────────────────────

@pytest.mark.req("FR-102-AC1.Load")
def test_module_stays_within_size_budget() -> None:
    """자원 파일 1개는 500줄 이내 (NFR-206)."""
    import inspect

    import core.der.load as module

    lines = inspect.getsource(module).splitlines()
    assert len(lines) <= 500, f"core/der/load.py 가 {len(lines)}줄입니다 (NFR-206: 500)"
