"""`CommonAsset` 검증 케이스 세트 — 구획 WP-1f / spec FR-106 · §13.2.3 `RC-CA-*`.

**이 스위트는 `DERContractTests` 를 상속하지 않는다.** CEMS·HEMS는 발전하지도
소비하지도 않으므로 `dispatch()`·매체 플래그·성능 저하가 성립하지 않는다
(FR-106). `DER` 계약 테스트를 끌어다 쓰면 존재하지 않아야 할 것을 요구하게
되므로, `CommonAsset` 계약에 맞는 검사를 직접 쓴다.

오라클 출처 (§13.2.1 "오라클 명시"):
    C-1~C-5  §13.2.2 공통 비용 5종의 틀. 단 CAPEX는 HW/SW로 분해되고 교체 스케줄이 각각 독립
    A-1·A-2  §13.2.3 안분 합계 보존 — 반올림 잔차를 규약대로 처리해 **가구별 합계 = 단지
             총계**(오차 0원)를 만드는지
    X-1      `CommonAsset` 부재 모델의 정상 동작 (FR-106-AC7)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.asset.common_asset import (
    CEMS,
    COMMON_ASSET_TYPES,
    COMMON_COST_ROW,
    HEMS,
    OWN_COST_ROW,
    RESIDUAL_HOLDER_INDEX,
    AllocationResult,
    MeteringComm,
    StandardCommonAsset,
    allocate,
    allocate_assets,
    annual_cost,
    household_proforma_rows,
)
from core.contracts.asset import AllocationRule, CommonAsset
from core.contracts.der import DER
from core.contracts.units import Money, to_won, won_sum

# §13.2.1 결정성: 손계산 가능한 값만 쓴다. 아래 값을 바꾸면 오라클도 다시 세운다.
CAPEX_SW = Money(30_000_000)   # CEMS 소프트웨어 개발비
CAPEX_HW = Money(20_000_000)   # 서버·게이트웨이 등 하드웨어 구축비
FIXED_OM = Money(100_000)      # §13.2.2 C-2 오라클과 같은 A
INFLATION = 0.02               # §13.2.2 C-2 오라클과 같은 i
HORIZON = 20                   # §13.2.2 C-2 오라클과 같은 n


def make_cems(**over) -> StandardCommonAsset:
    """C-1~C-5 공용 인스턴스. 케이스마다 필요한 값만 덮어쓴다."""
    kwargs = {
        "name": "단지 CEMS",
        "capex_sw": CAPEX_SW,
        "capex_hw": CAPEX_HW,
        "fixed_om_annual": FIXED_OM,
        "lifetime_sw": 5,
        "lifetime_hw": 10,
        "escalation_rate": INFLATION,
    }
    kwargs.update(over)
    return CEMS(**kwargs)  # type: ignore[arg-type]


# ── FR-106-AC1 : DER 이 아니다 ───────────────────────────────────────

@pytest.mark.req("FR-106-AC1")
@pytest.mark.parametrize("cls", COMMON_ASSET_TYPES)
def test_common_asset_is_not_a_der(cls) -> None:
    """공통설비는 `DER` 의 하위 클래스가 **아니다** (FR-106)."""
    assert issubclass(cls, CommonAsset)
    assert not issubclass(cls, DER), (
        f"{cls.__name__} 이 DER 을 상속했습니다. 발전·소비하지 않는 설비를 DER 로 "
        "두면 dispatch()·매체 플래그가 무의미하게 요구됩니다 (FR-106)"
    )


@pytest.mark.req("FR-106-AC1")
def test_common_asset_has_no_dispatch_or_media_flags() -> None:
    """`dispatch()` 와 매체 플래그가 **없어야** 한다 — 있으면 엔진이 이 설비를
    수지 집계 대상으로 오인한다. "매체 플래그 전부 거짓"은 `DER` 이 거부하는 상태다."""
    asset = make_cems()
    for attr in ("dispatch", "carries_electric", "carries_heat", "carries_cool",
                 "consumes_fuel", "degradation_rate", "variable_om", "dt"):
        assert not hasattr(asset, attr), (
            f"공통설비에 `{attr}` 이 있습니다. FR-106은 이 설비가 발전·소비하지 "
            "않으므로 해당 개념이 성립하지 않는다고 규정합니다"
        )


@pytest.mark.req("FR-106-AC1")
def test_common_asset_declares_required_methods() -> None:
    """AC1이 열거한 다섯 가지를 보유한다. 대표 수명은 SW·HW 중 짧은 쪽이다."""
    asset = make_cems()
    for method in ("capex", "fixed_om", "replacement_schedule", "salvage_value"):
        assert callable(getattr(asset, method, None)), f"FR-106-AC1 메서드 누락: {method}"
    assert isinstance(asset.lifetime, int) and asset.lifetime > 0
    assert asset.lifetime == min(asset.lifetime_sw, asset.lifetime_hw), (
        "긴 쪽을 쓰면 짧은 쪽 교체 시점이 분석기간 밖으로 밀려 교체비가 사라집니다")


@pytest.mark.req("FR-106-AC1")
def test_money_methods_return_whole_won() -> None:
    """금액은 전부 `Money`(정수 원)다 (NFR-103 재무 계층)."""
    asset = make_cems()
    for name in ("capex", "capex_software", "capex_hardware", "fixed_om", "salvage_value"):
        value = getattr(asset, name)(year=1)
        assert isinstance(value, Money), f"{name}() 가 Money 가 아닙니다"
        assert value == value.to_integral_value(), f"{name}() 가 원 미만 소수를 냈습니다"


# ── FR-106-AC2 : 기본 제공 유형 3종 ──────────────────────────────────

@pytest.mark.req("FR-106-AC2")
def test_three_builtin_types_exist() -> None:
    """CEMS(단지 통합 제어·모니터링) / HEMS(가구 단위) / 공용 계량·통신 설비."""
    assert [cls.__name__ for cls in COMMON_ASSET_TYPES] == ["CEMS", "HEMS", "MeteringComm"]
    assert {cls.tag for cls in COMMON_ASSET_TYPES} == {"CEMS", "HEMS", "MeteringComm"}
    assert {cls.display_name for cls in COMMON_ASSET_TYPES} == {
        "CEMS", "HEMS", "공용 계량·통신 설비",
    }


@pytest.mark.req("FR-106-AC2")
@pytest.mark.parametrize("cls", COMMON_ASSET_TYPES)
def test_tag_is_ascii_and_scope_declared(cls) -> None:
    """`tag` 는 레지스트리 키이므로 ASCII 로 둔다. 표시명은 별도 속성이다."""
    assert cls.tag.isascii() and cls.tag.isidentifier()
    assert cls.scope in ("단지", "가구")


@pytest.mark.req("FR-106-AC2")
def test_metering_comm_follows_the_same_cost_rules() -> None:
    """공용 계량·통신 설비도 같은 계산 규약을 따른다 (AC2 3종 중 마지막).

    SW 비용 0이면 재개발 항목 자체가 없어야 한다 — 0원 행은 "교체 불필요"와
    구분되지 않는다. HW 15년 → 16년차만 남는다.
    """
    asset = MeteringComm(
        name="공용 계량기", capex_sw=Money(0), capex_hw=Money(5_000_000),
        fixed_om_annual=Money(200_000), lifetime_sw=5, lifetime_hw=15,
        escalation_rate=INFLATION, allocation=AllocationRule.NO_ALLOCATION)
    assert asset.display_name == "공용 계량·통신 설비"
    assert asset.capex(year=1) == Money(5_000_000)
    assert asset.replacement_schedule(horizon=HORIZON) == {16: Money(5_000_000)}
    assert asset.allocation is AllocationRule.NO_ALLOCATION


# ── RC-CA-C1 : CAPEX (FR-106-AC3) ────────────────────────────────────

@pytest.mark.req("FR-106-AC3")
def test_rc_ca_c1_capex_splits_software_and_hardware() -> None:
    """RC-CA-C1 — 오라클: `capex = capex_sw + capex_hw`, 부가세는 별도 항목.

    30,000,000(SW) + 20,000,000(HW) = 50,000,000원, 부가세 10% → 세액
    5,000,000원 분리(§13.2.2 C-1). 초기 투자는 1년차에만 발생한다 — 재계상되면
    20년 분석에서 CAPEX가 20배가 된다.
    """
    asset = make_cems(vat_rate=0.10)
    assert asset.capex_software(year=1) == Money(30_000_000)
    assert asset.capex_hardware(year=1) == Money(20_000_000)
    assert asset.capex(year=1) == Money(50_000_000), "부가세가 capex() 에 섞였습니다"
    assert asset.capex_vat(year=1) == Money(5_000_000)
    assert asset.capex(year=2) == Money(0)
    assert asset.capex_software(year=5) == Money(0)
    assert asset.capex_hardware(year=5) == Money(0)


@pytest.mark.req("FR-106-AC3")
@pytest.mark.parametrize("cls", COMMON_ASSET_TYPES)
def test_capex_sum_rule_is_not_overridden(cls) -> None:
    """`capex()` 는 계약이 정한 합계 규칙을 그대로 쓴다 — 덮어쓰면 어느 쪽이
    얼마인지 리포트에서 되짚을 수 없어 SW/HW 분리 계상(AC3)이 무의미해진다."""
    assert cls.capex is CommonAsset.capex


# ── RC-CA-C2·C3 : 운영비 (FR-106-AC4) ────────────────────────────────

@pytest.mark.req("FR-106-AC4")
def test_rc_ca_c2_fixed_om_20year_total() -> None:
    """RC-CA-C2 — 오라클: 등비수열 합 `A × ((1+i)^n − 1) / i`.

    A=100,000 / i=0.02 / n=20 → 2,429,736.98 → **2,429,737원**. 연차별 값을 각각
    반올림해 더한 값도 같아야 한다 (NFR-103-M1 — 어긋나면 눈으로 검산 불가).
    """
    asset = make_cems()
    closed_form = to_won(
        Decimal(FIXED_OM) * ((Decimal("1.02") ** HORIZON - 1) / Decimal("0.02"))
    )
    assert closed_form == Money(2_429_737)
    assert won_sum([asset.fixed_om(year=y) for y in range(1, HORIZON + 1)]) == Money(2_429_737)


@pytest.mark.req("FR-106-AC4")
def test_rc_ca_c2_fixed_om_applies_inflation() -> None:
    """1년차 100,000 / 2년차 102,000 / 3년차 104,040원 (AC4). 물가를 빼먹으면
    20년 누계가 2,000,000원이 되어 429,737원(21.5%)이 사라진다."""
    asset = make_cems()
    assert asset.fixed_om(year=1) == Money(100_000)
    assert asset.fixed_om(year=2) == Money(102_000)
    assert asset.fixed_om(year=3) == Money(104_040)
    assert asset.fixed_om(year=HORIZON) == to_won(Decimal(FIXED_OM) * Decimal("1.02") ** 19)


@pytest.mark.req("FR-106-AC4")
def test_rc_ca_c3_no_variable_om() -> None:
    """RC-CA-C3 대응 — 공통설비에는 **변동 O&M이 없다**.

    C-3의 변동 O&M은 처리량(kWh)에 비례하는데 공통설비는 처리량이 없다. 0원짜리
    메서드를 두면 "처리량 정의를 잊었다"와 "원래 없다"가 구분되지 않는다.
    """
    assert not hasattr(make_cems(), "variable_om")
    assert "variable_om" not in CommonAsset.__abstractmethods__


# ── RC-CA-C4 : 교체 스케줄 (FR-106-AC3) ──────────────────────────────

@pytest.mark.req("FR-106-AC3")
def test_rc_ca_c4_replacement_schedules_are_independent() -> None:
    """RC-CA-C4 — 오라클: 수명 도달 **다음 연도 초**에 계상, SW·HW 독립.

    SW 5년 → 6·11·16년차 재개발, HW 10년 → 11년차 교체. 11년차는 겹치므로
    **합산**된다(30,000,000 + 20,000,000). 덮어쓰면 20,000,000원이 사라지는데
    그 해 현금흐름만 보면 정상처럼 보인다. 분석기간 밖 교체는 담지 않는다.
    """
    assert make_cems().replacement_schedule(horizon=HORIZON) == {
        6: Money(30_000_000),
        11: Money(50_000_000),
        16: Money(30_000_000),
    }
    assert make_cems(lifetime_sw=25, lifetime_hw=30).replacement_schedule(horizon=HORIZON) == {}


@pytest.mark.req("FR-106-AC3")
def test_rc_ca_c4_replacement_ratios_differ_for_sw_and_hw() -> None:
    """SW는 재개발, HW는 교체 — 비율이 다르다. 60%/100% → 6년차 18,000,000원."""
    schedule = make_cems(
        sw_redevelopment_ratio=0.6, hw_replacement_ratio=1.0
    ).replacement_schedule(horizon=HORIZON)
    assert schedule[6] == Money(18_000_000)
    assert schedule[11] == Money(38_000_000)


# ── RC-CA-C5 : 잔존가치 (FR-106-AC3) ─────────────────────────────────

@pytest.mark.req("FR-106-AC3")
def test_rc_ca_c5_salvage_value_computed_separately() -> None:
    """RC-CA-C5 — 오라클: `취득가 × 잔존수명 / 총수명`, SW·HW **각각**.

    SW 8년 → 9·17년차 재개발이므로 20년차 기준 마지막 설치는 17년차,
    사용 4년·잔존 4년 → 30,000,000 × 4/8 = 15,000,000원. HW 25년 → 교체 없음,
    사용 20년·잔존 5년 → 20,000,000 × 5/25 = 4,000,000원. 합계 19,000,000원.
    할인은 하지 않는다 — 자원이 할인까지 하면 CBA에서 두 번 할인된다.
    """
    asset = make_cems(lifetime_sw=8, lifetime_hw=25)
    assert asset.salvage_software(year=HORIZON) == Money(15_000_000)
    assert asset.salvage_hardware(year=HORIZON) == Money(4_000_000)
    assert asset.salvage_value(year=HORIZON) == Money(19_000_000)
    # 수명을 정확히 채운 해의 잔존가치는 0이다 (음수로 내려가지 않는다).
    assert make_cems(lifetime_sw=5, lifetime_hw=10).salvage_value(year=10) == Money(0)


# ── RC-CA-A1 : 안분 합계 보존 (FR-106-AC5) ───────────────────────────

@pytest.mark.req("FR-106-AC5")
def test_rc_ca_a1_residual_goes_to_final_household() -> None:
    """RC-CA-A1 — 오라클: 20,000,000원 / 15가구.

    20,000,000 / 15 = 1,333,333.33… → 가구당 1,333,333원이고 단순 합계는
    19,999,995원으로 **원액과 5원 어긋난다.** 잔차 5원을 규약대로 최종 가구에
    가산 → 최종 가구 1,333,338원, 합계 20,000,000원 **정확 일치**(NFR-103).
    """
    total = Money(20_000_000)
    result = allocate(total, rule=AllocationRule.EQUAL_PER_HOUSEHOLD, households=15)
    naive = won_sum([to_won(Decimal(total) / 15)] * 15)
    assert naive == Money(19_999_995), "잔차가 생기는 조합이어야 이 케이스가 의미를 갖습니다"
    assert result.per_household[:14] == tuple([Money(1_333_333)] * 14)
    assert result.per_household[RESIDUAL_HOLDER_INDEX] == Money(1_333_338)
    assert won_sum(result.per_household) == total
    assert result.total == total


@pytest.mark.req("FR-106-AC5")
@pytest.mark.parametrize("total", [0, 1, 7, 999, 100_000, 20_000_000, 123_456_789])
@pytest.mark.parametrize("households", [1, 2, 3, 7, 15, 23, 100])
@pytest.mark.parametrize("rule", list(AllocationRule))
def test_allocation_preserves_total_for_many_combinations(total, households, rule) -> None:
    """15가구 20,000,000원 하나만 맞추면 우연히 통과하는 구현이 남는다. 금액·가구
    수·규칙을 넓게 조합해 **모든 조합에서 합계 = 원액**임을 본다 — 합계 보존은
    특정 숫자의 성질이 아니라 안분 규약의 성질이어야 한다."""
    caps = [1.0 + (i % 5) * 0.5 for i in range(households)]
    result = allocate(Money(total), rule=rule, households=households,
                      capacities=caps if rule is AllocationRule.BY_CAPACITY else None)
    assert len(result.per_household) == households
    assert won_sum([*result.per_household, result.unallocated]) == Money(total)


# ── RC-CA-A2 : 안분 규칙 3종 (FR-106-AC5) ────────────────────────────

@pytest.mark.req("FR-106-AC5")
def test_rc_ca_a2_equal_rule() -> None:
    """균등 — 10,000,000 / 4가구 = 2,500,000원씩, 잔차 없음."""
    result = allocate(Money(10_000_000), rule=AllocationRule.EQUAL_PER_HOUSEHOLD, households=4)
    assert result.per_household == tuple([Money(2_500_000)] * 4)
    assert result.unallocated == Money(0)
    assert result.rule is AllocationRule.EQUAL_PER_HOUSEHOLD


@pytest.mark.req("FR-106-AC5")
def test_rc_ca_a2_by_capacity_rule() -> None:
    """용량 비례 — 10,000,000원, 용량 3:5:2 → 3,000,000 / 5,000,000 / 2,000,000원."""
    result = allocate(Money(10_000_000), rule=AllocationRule.BY_CAPACITY,
                      households=3, capacities=[3.0, 5.0, 2.0])
    assert result.per_household == (Money(3_000_000), Money(5_000_000), Money(2_000_000))
    assert result.total == Money(10_000_000)


@pytest.mark.req("FR-106-AC5")
def test_rc_ca_a2_by_capacity_residual_also_goes_to_final_household() -> None:
    """용량 비례에서도 잔차 규약은 같다 — 1,000,000원, 용량 1:1:1 → 마지막 가구 +1원."""
    result = allocate(Money(1_000_000), rule=AllocationRule.BY_CAPACITY,
                      households=3, capacities=[1.0, 1.0, 1.0])
    assert result.per_household == (Money(333_333), Money(333_333), Money(333_334))
    assert result.total == Money(1_000_000)


@pytest.mark.req("FR-106-AC5")
def test_rc_ca_a2_no_allocation_rule() -> None:
    """미안분 — 가구 프로포마에 0원, **단지 총계에만** 계상. 가구 행 자체는 남긴다
    (없애면 "안분하지 않기로 했다"와 "공통설비가 없다"가 구분되지 않는다)."""
    result = allocate(Money(20_000_000), rule=AllocationRule.NO_ALLOCATION, households=15)
    assert result.per_household == tuple([Money(0)] * 15)
    assert result.unallocated == Money(20_000_000)
    assert result.total == Money(20_000_000)


@pytest.mark.req("FR-106-AC5")
def test_allocation_rule_is_recorded_for_report() -> None:
    """선택한 규칙이 결과에 남아야 한다 — 규칙 없는 가구당 부담액은 해석 불가."""
    for rule in AllocationRule:
        result = allocate(Money(1_000_000), rule=rule, households=2,
                          capacities=[1.0, 1.0] if rule is AllocationRule.BY_CAPACITY else None)
        assert result.rule is rule
        assert str(rule.value) in result.describe()


@pytest.mark.req("FR-106-AC5")
def test_allocation_result_rejects_broken_invariant() -> None:
    """합계가 어긋난 안분 결과는 **만들어질 수 없다** (음성 케이스). 자료구조가
    검사하지 않으면 리포트까지 흘러가서야 불일치가 발견된다."""
    with pytest.raises(ValueError, match="합계"):
        AllocationResult(
            rule=AllocationRule.EQUAL_PER_HOUSEHOLD,
            source_total=Money(100),
            per_household=(Money(33), Money(33), Money(33)),
            unallocated=Money(0),
        )


@pytest.mark.req("FR-106-AC5")
def test_allocation_rejects_zero_households() -> None:
    """가구 수 0은 경계 위반이다 (§13.2.1 양·음성 쌍)."""
    with pytest.raises(ValueError, match="가구 수"):
        allocate(Money(100), rule=AllocationRule.EQUAL_PER_HOUSEHOLD, households=0)


@pytest.mark.req("FR-106-AC5")
@pytest.mark.parametrize(
    "households,caps",
    [(3, None),            # 용량 누락 — 균등으로 조용히 되돌아가면 안 된다
     (3, [1.0, 1.0]),      # 개수 불일치
     (2, [0.0, 0.0]),      # 합계 0 — 0으로 나누기
     (2, [-1.0, 3.0])],    # 음수 용량
)
def test_allocation_rejects_invalid_capacities(households, caps) -> None:
    """용량 비례 안분의 위반 입력은 전부 거부한다."""
    with pytest.raises(ValueError, match="용량"):
        allocate(Money(100), rule=AllocationRule.BY_CAPACITY,
                 households=households, capacities=caps)


# ── FR-106-AC6 : 가구 프로포마 별도 행 ───────────────────────────────

@pytest.mark.req("FR-106-AC6")
def test_household_proforma_separates_common_allocation_row() -> None:
    """안분된 공통비용은 가구 자체 설비 비용과 **구분되는 별도 행**이다 — 합치면
    부담액의 근거도, 안분 규칙을 바꿨을 때의 변화도 보이지 않는다."""
    result = allocate(Money(20_000_000), rule=AllocationRule.EQUAL_PER_HOUSEHOLD, households=15)
    rows = household_proforma_rows(own_costs={"옥상 PV 3kW": Money(4_500_000)},
                                   allocations={"단지 CEMS": result}, household_index=0)
    own = [r for r in rows if r.category == OWN_COST_ROW]
    common = [r for r in rows if r.category == COMMON_COST_ROW]
    assert len(own) == 1 and len(common) == 1
    assert own[0].amount == Money(4_500_000), "자체 설비 비용에 공통비가 섞였습니다"
    assert common[0].amount == Money(1_333_333)
    assert common[0].rule is AllocationRule.EQUAL_PER_HOUSEHOLD, (
        "안분 규칙이 행에 남아야 리포트에 명시할 수 있습니다 (AC5)")
    assert won_sum([r.amount for r in rows]) == Money(5_833_333)


@pytest.mark.req("FR-106-AC6")
def test_household_proforma_keeps_zero_row_for_no_allocation() -> None:
    """미안분이어도 가구 행은 0원으로 남는다 — 규칙 선택이 보여야 한다."""
    result = allocate(Money(20_000_000), rule=AllocationRule.NO_ALLOCATION, households=15)
    rows = household_proforma_rows(own_costs={}, allocations={"단지 CEMS": result},
                                   household_index=3)
    assert len(rows) == 1
    assert rows[0].category == COMMON_COST_ROW
    assert rows[0].amount == Money(0)
    assert rows[0].rule is AllocationRule.NO_ALLOCATION


@pytest.mark.req("FR-106-AC6")
def test_household_proforma_rejects_out_of_range_index() -> None:
    """존재하지 않는 가구 번호는 오류다 — 조용히 마지막 가구 값을 주면 안 된다."""
    result = allocate(Money(100), rule=AllocationRule.EQUAL_PER_HOUSEHOLD, households=2)
    with pytest.raises(IndexError):
        household_proforma_rows(own_costs={}, allocations={"CEMS": result}, household_index=2)


# ── RC-CA-X1 : 공통설비 없는 모델 (FR-106-AC7) ───────────────────────

@pytest.mark.req("FR-106-AC7")
def test_rc_ca_x1_model_without_common_asset(monkeypatch) -> None:
    """RC-CA-X1 — 부재 시 정상 동작하고 **안분 로직을 부르지 않는다.**

    안분 함수를 폭발하게 바꿔 두고도 통과해야 한다. 부재를 "총액 0원 안분"으로
    처리하면 0으로 나누기·빈 리스트에서 단독주택 모델이 깨진다.
    """
    import core.asset.common_asset as module

    def boom(*args, **kwargs):
        raise AssertionError("공통설비가 없는데 안분 로직이 호출되었습니다")

    monkeypatch.setattr(module, "allocate", boom)
    assert module.allocate_assets([], year=1, horizon=HORIZON, households=1) == {}


@pytest.mark.req("FR-106-AC7")
def test_rc_ca_x1_no_default_instance() -> None:
    """기본값 없음 — 인자 없이 만들어지는 공통설비는 존재하지 않는다. 기본값을 주면
    아무도 지정하지 않은 비용이 모델에 들어오고, 그 값이 0원이면 조용히 사라진다."""
    for cls in COMMON_ASSET_TYPES:
        with pytest.raises(TypeError):
            cls()  # type: ignore[call-arg]


@pytest.mark.req("FR-106-AC7")
def test_allocate_assets_allocates_each_asset() -> None:
    """X1의 양성 쌍 — 1년차 CEMS 총액 = CAPEX 50,000,000 + O&M 100,000 =
    50,100,000원. 10가구 균등 → 5,010,000원씩, 잔차 0."""
    hems = HEMS(
        name="가구 HEMS", capex_sw=Money(1_000_000), capex_hw=Money(2_000_000),
        fixed_om_annual=Money(50_000), lifetime_sw=5, lifetime_hw=10,
        escalation_rate=INFLATION)
    results = allocate_assets([make_cems(), hems], year=1, horizon=HORIZON, households=10)
    assert set(results) == {"단지 CEMS", "가구 HEMS"}
    assert results["단지 CEMS"].source_total == Money(50_100_000)
    assert results["단지 CEMS"].per_household == tuple([Money(5_010_000)] * 10)
    assert won_sum(results["가구 HEMS"].per_household) == Money(3_050_000)


@pytest.mark.req("FR-106-AC7")
def test_annual_cost_includes_replacement_year() -> None:
    """연차 총액 = CAPEX + 고정 O&M + 해당 연도 교체비. 6년차: 교체 30,000,000 +
    O&M 100,000×1.02^5(=110,408) = 30,110,408원."""
    assert annual_cost(make_cems(), year=6, horizon=HORIZON) == Money(30_110_408)


@pytest.mark.req("FR-106-AC7")
def test_allocate_assets_rejects_duplicate_names() -> None:
    """이름이 겹치면 한쪽 안분 결과가 조용히 덮인다 — 즉시 오류로 잡는다."""
    with pytest.raises(ValueError, match="이름"):
        allocate_assets([make_cems(), make_cems()], year=1, horizon=HORIZON, households=5)


# ── 생성자·연도 검증 (음성 케이스) ───────────────────────────────────

@pytest.mark.req("FR-106-AC3")
def test_constructor_rejects_invalid_values() -> None:
    """음수 비용·0 이하 수명·비정규화 물가상승률·빈 이름은 거부한다."""
    with pytest.raises(ValueError, match="음수"):
        make_cems(capex_sw=Money(-1))
    with pytest.raises(ValueError, match="음수"):
        make_cems(fixed_om_annual=Money(-1))
    with pytest.raises(ValueError, match="lifetime_sw"):
        make_cems(lifetime_sw=0)
    with pytest.raises(ValueError, match="소수"):
        make_cems(escalation_rate=2.0)
    with pytest.raises(ValueError, match="이름"):
        make_cems(name="")


@pytest.mark.req("FR-106-AC3")
def test_year_is_one_based() -> None:
    """분석 연도는 1부터 센다 — 0-base 인덱스를 그대로 넘기면 오류다."""
    asset = make_cems()
    for call in (asset.capex, asset.fixed_om, asset.salvage_value):
        with pytest.raises(ValueError):
            call(year=0)
    with pytest.raises(ValueError):
        asset.replacement_schedule(horizon=0)
