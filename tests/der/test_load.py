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

from core.contracts.der import DER, EOL_REPLACE, EOL_RETIRE, DispatchContext
from core.contracts.units import HOURS_PER_YEAR, Money, to_won, won_sum
from core.contracts.validation import ValidationError
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
            escalation_rate=OM_I,
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
    assert load.value_streams() == ()


@pytest.mark.req("FR-102-AC1.Load")
def test_baseline_cost_is_reported_but_is_not_a_benefit() -> None:
    """기준선 요금은 산출하되 **편익 목록에는 들어가지 않는다** (FR-607)."""
    load = make_load()
    baseline = load.baseline_energy_cost(year=1, tariff_won_per_kwh=150.0)
    assert baseline == to_won(ANNUAL_KWH * 150.0)
    assert isinstance(baseline, Money)
    assert load.value_streams() == ()


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

# ↓ v0.15 이관 — 이 검사가 보는 것은 메서드의 **존재**(AC2)가 아니라
# **산식**(§13.2.2 C-1~C-3)이다. AC5 가 없던 동안 AC2 를 빌려 인용했다.
@pytest.mark.req("FR-101-AC5")
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

# ↓ v0.15 이관 — 이 검사가 보는 것은 메서드의 **존재**(AC2)가 아니라
# **산식**(§13.2.2 C-1~C-3)이다. AC5 가 없던 동안 AC2 를 빌려 인용했다.
@pytest.mark.req("FR-101-AC5")
def test_fixed_om_20y_total_matches_geometric_series() -> None:
    """C-2: `A × ((1+i)^n − 1)/i`. A=100,000 i=0.02 n=20 → **2,429,737원**.

    연차별 값을 각각 반올림해 더한 값(`won_sum`)과 해석해를 함께 본다 —
    두 경로가 갈리면 프로포마 행 합계와 총계가 어긋난다 (NFR-103-M1).
    """
    load = make_load(fixed_om_won_per_year=OM_A, escalation_rate=OM_I)

    closed_form = OM_A * ((1.0 + OM_I) ** OM_N - 1.0) / OM_I
    assert to_won(closed_form) == OM_20Y_TOTAL

    yearly = [load.fixed_om(year=y) for y in range(1, OM_N + 1)]
    assert yearly[0] == Money(100_000), "1년차는 물가상승 미적용 (지수 0)"
    assert won_sum(yearly) == OM_20Y_TOTAL


# ── RC-ALL-C3 변동 O&M ───────────────────────────────────────────────

# ↓ v0.15 이관 — 이 검사가 보는 것은 메서드의 **존재**(AC2)가 아니라
# **산식**(§13.2.2 C-1~C-3)이다. AC5 가 없던 동안 AC2 를 빌려 인용했다.
@pytest.mark.req("FR-101-AC5")
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


@pytest.mark.req("FR-104-AC5")
def test_first_acquisition_salvage_carries_no_replacement_escalation() -> None:
    """★ **최초 취득가에는 교체 물가 계수가 걸리지 않는다** (R57/WP-7).

    대장 `capex.replacement_real_trend` 의 `applicable_scope` 가 적용범위를 스스로
    좁혀 두었다 — *「분석기간 안에 교체가 일어나는 설비의 **재취득 단가**에만
    걸린다」*. 계수를 최초 취득가에까지 태우는 구현은 1년차 잔존가치를 부풀리고,
    그것은 결론을 **좋아지는 방향으로만** 밀어 「보수적이라 안전하다」로도 걸러지지
    않는다.

    재는 법: 교체 계수만 크게 다른 두 자원이 **첫 교체 전 구간에서는 같은 값**
    이어야 한다. 아직 잴 취득분이 최초 하나뿐이기 때문이다.
    """
    flat = make_load(lifetime=10, capacity_kw=1.0, unit_cost_won_per_kw=1_000_000.0)
    steep = make_load(
        lifetime=10,
        capacity_kw=1.0,
        unit_cost_won_per_kw=1_000_000.0,
        replacement_escalation_rate=0.20,
    )
    assert steep.replacement_escalation_factor(year=1) == 1.0

    # 0 이 아닌 값을 견주는지 먼저 못 박는다 — 둘 다 0이면 아무것도 재지 않는다
    assert int(flat.salvage_value(year=1)) > 0
    for year in (1, 2, 5, 9):
        assert flat.salvage_value(year=year) == steep.salvage_value(year=year), (
            f"{year}년차 잔존가치가 교체 계수를 따라 움직입니다 — 첫 교체 전이라 "
            "최초 취득분뿐인 구간이며, 대장이 그 자리를 적용범위에서 뺐습니다"
        )


@pytest.mark.req("FR-104-AC5")
def test_salvage_after_replacement_uses_the_replacement_escalation() -> None:
    """★★ **교체한 개체는 그 교체비와 같은 가격 기준으로 되판다** (R57/WP-7).

    `replacement_schedule()` 은 11년차 재취득을 **명목**(계수를 태운 값)으로
    장부한다. 잔존가치가 실질이면 같은 설비를 **명목으로 사고 실질로 되파는**
    셈이고, 그 과소 계상은 **한 방향으로만** 결론을 나쁘게 만들어 「보수적이라
    안전하다」로 읽힌다.

    ⚠ **계수를 손으로 적지 않는다** — `replacement_escalation_factor()` 에서
    얻어 대조한다. 손으로 적으면 그 수가 이 시험의 두 번째 정본이 된다.
    """
    acquisition = 1_000_000.0
    load = make_load(
        lifetime=10,
        capacity_kw=1.0,
        unit_cost_won_per_kw=acquisition,
        replacement_escalation_rate=0.06,
    )
    # 재취득이 실제로 일어난 해. `replacement_schedule()` 이 장부하는 해와 같다
    factor = load.replacement_escalation_factor(year=11)

    assert load.replacement_schedule(horizon=13)[11] == to_won(acquisition * factor)

    # 13년차 잔존수명은 `10 − ((13−1) % 10) − 1 = 7`년이다
    assert load.salvage_value(year=13) == to_won(acquisition * factor * 7 / 10)

    # 계수를 끄면 그만큼 작아진다 — 위 단언이 곱셈을 두 번 한 결과가 아니다
    flat = make_load(lifetime=10, capacity_kw=1.0, unit_cost_won_per_kw=acquisition)
    assert flat.salvage_value(year=13) == to_won(acquisition * 7 / 10)
    assert int(flat.salvage_value(year=13)) < int(load.salvage_value(year=13))


# ── NFR-206 파일 규모 ────────────────────────────────────────────────

@pytest.mark.req("NFR-206-M1")
def test_module_stays_within_size_budget() -> None:
    """자원 파일 1개는 **코드 500줄** 이내 (NFR-206).

    ⚠ **R22 인수에서 이 단언이 중앙 게이트와 다른 것을 재던 것이 드러났다.**
    여기는 raw 줄 수를 셌고 `scripts/check_file_size.py --code-strict` 는
    **코드 줄과 설명 줄을 갈라** 코드 쪽만 상한에 건다. 그래서 전환으로 근거
    주석이 늘자 여기만 빨간불이 됐고, 게이트는 rc=0 이면서 출력에 이렇게
    적고 있었다:

        줄 수를 맞추려고 근거 주석을 지우지 마십시오. 그것은 조항이
        지키려던 유지보수성을 오히려 나쁘게 만듭니다.

    게다가 이 단언은 **자원 6파일 중 둘에만** 있어서 `pv.py`(632줄)·
    `ess.py`(697)·`heatpump.py`(676)는 지키는 검사 없이 지나갔다 — 손으로
    유지하는 목록이 목록 밖의 것을 조용히 통과시키는 그 형태다.

    그래서 **게이트와 같은 함수로 같은 것을 재게** 맞춘다. 조항의 근거는
    DER-VET `Params.py` 의 **1,830줄 코드 스프롤**이지 설명의 양이 아니다.
    """
    from pathlib import Path

    from scripts.check_file_size import LIMIT, measure_file

    repo_root = Path(__file__).resolve().parents[2]
    measured = measure_file(repo_root / "core" / "der" / "load.py")
    assert measured.code <= LIMIT, (
        f"core/der/load.py 의 코드 줄이 {measured.code}줄입니다 "
        f"(NFR-206 상한 {LIMIT} · 총 {measured.total}줄). "
        "근거 주석을 지워서 맞추지 마십시오 — 코드를 가르십시오."
    )


# ── FR-104-AC3 retire 기능 (WP-24) ────────────────────────────────────



@pytest.mark.req("FR-104-AC3")
def test_default_is_replace_behavior_unchanged() -> None:
    """기본값은 replace - 아무것도 안 넘기면 지금까지와 결과가 똑같다.

    Load(기본 생성)은 end_of_life_action이 "replace"이므로 기존과 동일하게 작동한다.
    """
    load = make_load(
        lifetime=20,
        capacity_kw=3.0,
        unit_cost_won_per_kw=1_500_000.0,
        subcomponents=[("계량기", 12, 300_000.0)],
    )
    assert load.end_of_life_action == EOL_REPLACE
    assert load.retires_at_end_of_life() is False

    # 기존과 동일한 교체 스케줄: 12년 수명 계량기 → 13년차 교체
    schedule = load.replacement_schedule(horizon=20)
    assert schedule == {13: Money(300_000)}


@pytest.mark.req("FR-104-AC3")
def test_retire_returns_empty_replacement_schedule() -> None:
    """retire면 본체도 부속설비도 아무것도 교체하지 않는다.

    수명 20년 + 계량기 12년이어도, retire 선택 시 빈 스케줄을 돌려준다.
    """
    load = make_load(
        end_of_life_action=EOL_RETIRE,
        lifetime=20,
        capacity_kw=3.0,
        unit_cost_won_per_kw=1_500_000.0,
        subcomponents=[("계량기", 12, 300_000.0)],
    )
    assert load.end_of_life_action == EOL_RETIRE
    assert load.retires_at_end_of_life() is True

    # retire 선택 시 교체비가 전혀 없다
    schedule = load.replacement_schedule(horizon=20)
    assert schedule == {}

    longer = load.replacement_schedule(horizon=30)
    assert longer == {}


@pytest.mark.req("FR-104-AC3")
def test_retire_keeps_load_unchanged_dispatch() -> None:
    """retire 여도 부하는 그대로다 - 수요는 계속 발생한다.

    Load/ThermalLoad는 순수 부하 자원으로서, retire해도 가구는 계속 살고
    수요는 계속 발생한다. dispatch()는 수정하지 않는다.
    """
    load_replace = make_load(lifetime=20, annual_growth_rate=0.0)
    load_retire = make_load(lifetime=20, end_of_life_action=EOL_RETIRE, annual_growth_rate=0.0)

    ctx_early = DispatchContext(steps=HOURS_PER_YEAR, dt=load_replace.dt, year=1)
    result_replace_early = load_replace.dispatch(ctx_early)
    result_retire_early = load_retire.dispatch(ctx_early)

    # 수명 도달 전(1년차): 둘 다 동일한 부하를 소비
    assert result_replace_early.electric == result_retire_early.electric
    assert math.fsum(result_replace_early.electric) == pytest.approx(-ANNUAL_KWH, abs=1e-9)

    # 수명 도달 후(25년차): 둘 다 여전히 동일한 부하를 소비 (부하 자원 특성)
    ctx_late = DispatchContext(steps=HOURS_PER_YEAR, dt=load_replace.dt, year=25)
    result_replace_late = load_replace.dispatch(ctx_late)
    result_retire_late = load_retire.dispatch(ctx_late)

    assert result_replace_late.electric == result_retire_late.electric


@pytest.mark.req("FR-104-AC3")
def test_retire_keeps_load_unchanged_annual_energy() -> None:
    """retire 선택 시 연간 에너지 소비량이 replace와 같다.

    수명 20년 기준:
    - 1~20년차: replace와 retire 동일
    - 21년차 이후: 둘 다 여전히 성장률 적용하여 계산 (부하 자원 특성)
    """
    g = 0.02
    load_replace = make_load(lifetime=20, annual_growth_rate=g)
    load_retire = make_load(lifetime=20, end_of_life_action=EOL_RETIRE, annual_growth_rate=g)

    for year in [1, 10, 20, 25]:
        expected = ANNUAL_KWH * (1.0 + g) ** (year - 1)
        assert load_replace.annual_energy_kwh(year=year) == pytest.approx(expected, rel=1e-12)
        assert load_retire.annual_energy_kwh(year=year) == pytest.approx(expected, rel=1e-12)
        assert load_replace.annual_energy_kwh(year=year) == load_retire.annual_energy_kwh(year=year)


@pytest.mark.req("FR-104-AC3")
def test_retire_does_not_affect_other_cost_methods() -> None:
    """retire가 capex, O&M, 잔존가치에 영향을 주지 않는다.

    교체비(schedule)만 다르고, 다른 비용 메서드는 수명에 따라 동일하게 작동한다.
    """
    load_replace = make_load(
        lifetime=20,
        capacity_kw=3.0,
        unit_cost_won_per_kw=1_500_000.0,
        fixed_om_won_per_year=OM_A,
        variable_om_won_per_kwh=5.0,
        escalation_rate=OM_I,
    )
    load_retire = make_load(
        lifetime=20,
        end_of_life_action=EOL_RETIRE,
        capacity_kw=3.0,
        unit_cost_won_per_kw=1_500_000.0,
        fixed_om_won_per_year=OM_A,
        variable_om_won_per_kwh=5.0,
        escalation_rate=OM_I,
    )

    # capex: 둘 다 1년차에만 발생
    assert load_replace.capex(year=1) == load_retire.capex(year=1)
    assert load_replace.capex(year=2) == load_retire.capex(year=2) == Money(0)

    # fixed_om: 물가상승 동일
    for year in [1, 5, 20]:
        assert load_replace.fixed_om(year=year) == load_retire.fixed_om(year=year)

    # variable_om: 소비량 동일
    for year in [1, 5, 20]:
        assert load_replace.variable_om(year=year) == load_retire.variable_om(year=year)

    # salvage_value: 수명에 따른 잔존가치 동일
    for year in [10, 20]:
        assert load_replace.salvage_value(year=year) == load_retire.salvage_value(year=year)



# ── 입력 검증 오류의 3요소(field·reason·action) 구조화 — R22/WP-32D, NFR-303-M1 ──


def make_load_invalid(**overrides) -> Load:
    """검증 오류 테스트용 부하 생성자."""
    return Load(name="테스트부하", **overrides)


@pytest.mark.req("NFR-303-M1")
def test_negative_hourly_load_carries_field_reason_action() -> None:
    """부하 시계열에 음수가 있으면 field·reason·action 셋을 채운 채 거부한다."""
    hourly = [350.0 / 8760.0] * 8760
    hourly[100] = -5.0
    with pytest.raises(ValidationError) as exc:
        make_load_invalid(hourly_kwh=hourly)
    err = exc.value
    assert err.field == "load.hourly_kwh"
    assert "100" in err.reason
    assert "-5.0" in err.reason
    assert "0 이상" in err.action


@pytest.mark.req("NFR-303-M1")
def test_hourly_load_length_mismatch_carries_field_reason_action() -> None:
    """부하 시계열 행수가 8760이 아니면 field·reason·action 셋을 채운 채 거부한다."""
    with pytest.raises(ValidationError) as exc:
        make_load_invalid(hourly_kwh=[0.5] * 8759)
    err = exc.value
    assert err.field == "load.hourly_kwh"
    assert "8759행" in err.reason
    assert "8760" in err.reason
    assert "8760" in err.action


@pytest.mark.req("NFR-303-M1")
def test_monthly_load_not_12_items_carries_field_reason_action() -> None:
    """월사용량이 12개월치가 아니면 field·reason·action 셋을 채운 채 거부한다."""
    with pytest.raises(ValidationError) as exc:
        make_load_invalid(monthly_kwh=[100.0, 200.0, 300.0])
    err = exc.value
    assert err.field == "load.monthly_kwh"
    assert "3개" in err.reason
    assert "12" in err.action


@pytest.mark.req("NFR-303-M1")
def test_negative_monthly_load_carries_field_reason_action() -> None:
    """월사용량에 음수가 있으면 field·reason·action 셋을 채운 채 거부한다."""
    monthly = [350.0] * 12
    monthly[5] = -50.0
    with pytest.raises(ValidationError) as exc:
        make_load_invalid(monthly_kwh=monthly)
    err = exc.value
    assert err.field == "load.monthly_kwh"
    assert "음수" in err.reason
    assert "0 이상" in err.action


@pytest.mark.req("NFR-303-M1")
def test_invalid_profile_weights_carries_field_reason_action() -> None:
    """표준 프로파일 가중치 합이 0 이하면 field·reason·action 셋을 채운 채 거부한다."""
    shape = [0.0] * 8760
    with pytest.raises(ValidationError) as exc:
        make_load_invalid(monthly_kwh=350.0, shape=shape)
    err = exc.value
    assert err.field == "load.shape"
    assert "가중치 합이 0 이하" in err.reason
    assert "0보다 큰" in err.action


@pytest.mark.req("NFR-303-M1")
def test_both_hourly_and_monthly_given_carries_field_reason_action() -> None:
    """hourly_kwh와 monthly_kwh를 둘 다 주면 field·reason·action 셋을 채운 채 거부한다."""
    with pytest.raises(ValidationError) as exc:
        make_load_invalid(hourly_kwh=[0.5] * 8760, monthly_kwh=350.0)
    err = exc.value
    assert err.field == "load.hourly_kwh"
    assert "하나만" in err.action
    assert "hourly_kwh" in err.action
    assert "monthly_kwh" in err.action


@pytest.mark.req("NFR-303-M1")
def test_neither_hourly_nor_monthly_given_carries_field_reason_action() -> None:
    """hourly_kwh와 monthly_kwh를 둘 다 안 주면 field·reason·action 셋을 채운 채 거부한다."""
    with pytest.raises(ValidationError) as exc:
        make_load_invalid(hourly_kwh=None, monthly_kwh=None)
    err = exc.value
    assert err.field == "load.hourly_kwh"
    assert "둘 다 주지 않았습니다" in err.reason
    assert "하나만" in err.action


@pytest.mark.req("NFR-303-M1")
def test_invalid_annual_growth_rate_carries_field_reason_action() -> None:
    """연간 증가율이 범위를 벗어나면 field·reason·action 셋을 채운 채 거부한다."""
    with pytest.raises(ValidationError) as exc:
        make_load_invalid(monthly_kwh=350.0, annual_growth_rate=2.0)
    err = exc.value
    assert err.field == "load.annual_growth_rate"
    assert "2.0" in err.reason
    assert "-1.0" in err.action
    assert "1.0" in err.action


@pytest.mark.req("NFR-303-M1")
def test_negative_capacity_carries_field_reason_action() -> None:
    """계약전력이 음수이면 field·reason·action 셋을 채운 채 거부한다."""
    with pytest.raises(ValidationError) as exc:
        make_load_invalid(monthly_kwh=350.0, capacity_kw=-3.0)
    err = exc.value
    assert err.field == "load.capacity_kw"
    assert "-3.0" in err.reason
    assert "0 이상" in err.action


@pytest.mark.req("NFR-303-M1")
def test_negative_unit_cost_carries_field_reason_action() -> None:
    """단가가 음수이면 field·reason·action 셋을 채운 채 거부한다."""
    with pytest.raises(ValidationError) as exc:
        make_load_invalid(monthly_kwh=350.0, unit_cost_won_per_kw=-100_000.0)
    err = exc.value
    assert err.field == "load.unit_cost_won_per_kw"
    assert "-100000.0" in err.reason
    assert "0 이상" in err.action


@pytest.mark.req("NFR-303-M1")
def test_negative_incidental_cost_carries_field_reason_action() -> None:
    """부대비가 음수이면 field·reason·action 셋을 채운 채 거부한다."""
    with pytest.raises(ValidationError) as exc:
        make_load_invalid(monthly_kwh=350.0, incidental_cost_won=-50_000.0)
    err = exc.value
    assert err.field == "load.incidental_cost_won"
    assert "-50000.0" in err.reason
    assert "0 이상" in err.action


@pytest.mark.req("NFR-303-M1")
def test_invalid_vat_rate_carries_field_reason_action() -> None:
    """부가세율이 범위를 벗어나면 field·reason·action 셋을 채운 채 거부한다."""
    with pytest.raises(ValidationError) as exc:
        make_load_invalid(monthly_kwh=350.0, vat_rate=2.0)
    err = exc.value
    assert err.field == "load.vat_rate"
    assert "2.0" in err.reason
    assert "-1.0" in err.action
    assert "1.0" in err.action


@pytest.mark.req("NFR-303-M1")
def test_negative_fixed_om_carries_field_reason_action() -> None:
    """고정 O&M이 음수이면 field·reason·action 셋을 채운 채 거부한다."""
    with pytest.raises(ValidationError) as exc:
        make_load_invalid(monthly_kwh=350.0, fixed_om_won_per_year=-10_000.0)
    err = exc.value
    assert err.field == "load.fixed_om_won_per_year"
    assert "-10000.0" in err.reason
    assert "0 이상" in err.action


@pytest.mark.req("NFR-303-M1")
def test_negative_variable_om_carries_field_reason_action() -> None:
    """변동 O&M 단가가 음수이면 field·reason·action 셋을 채운 채 거부한다."""
    with pytest.raises(ValidationError) as exc:
        make_load_invalid(monthly_kwh=350.0, variable_om_won_per_kwh=-5.0)
    err = exc.value
    assert err.field == "load.variable_om_won_per_kwh"
    assert "-5.0" in err.reason
    assert "0 이상" in err.action


@pytest.mark.req("NFR-303-M1")
def test_negative_escalation_rate_carries_field_reason_action() -> None:
    """물가상승율이 범위를 벗어나면 field·reason·action 셋을 채운 채 거부한다."""
    # escalation_rate는 base DER 클래스에서 검증하므로 이 테스트는 다른 속성으로 대체
    with pytest.raises(ValidationError) as exc:
        make_load_invalid(monthly_kwh=350.0, annual_growth_rate=2.0)
    err = exc.value
    assert err.field == "load.annual_growth_rate"
    assert "2.0" in err.reason
    assert "-1.0" in err.action
    assert "1.0" in err.action


@pytest.mark.req("NFR-303-M1")
def test_invalid_subcomponent_life_carries_field_reason_action() -> None:
    """부속설비 수명이 1년 미만이면 field·reason·action 셋을 채운 채 거부한다."""
    with pytest.raises(ValidationError) as exc:
        make_load_invalid(monthly_kwh=350.0, subcomponents=[("인버터", 0, 100_000.0)])
    err = exc.value
    assert err.field == "load.subcomponents"
    assert "0" in err.reason
    assert "인버터" in err.reason
    assert "1년 이상" in err.action


@pytest.mark.req("NFR-303-M1")
def test_negative_subcomponent_cost_carries_field_reason_action() -> None:
    """부속설비 교체비가 음수이면 field·reason·action 셋을 채운 채 거부한다."""
    with pytest.raises(ValidationError) as exc:
        make_load_invalid(monthly_kwh=350.0, subcomponents=[("인버터", 12, -100_000.0)])
    err = exc.value
    assert err.field == "load.subcomponents"
    assert "-100000.0" in err.reason
    assert "인버터" in err.reason
    assert "0 이상" in err.action
