"""PV 입력 검증 오류의 3요소(field·reason·action) 구조화 — R21/WP-31C, NFR-303-M1.

`ValidationError` 로 전환한 raise 지점이 실제로 «어떤 필드가 / 왜 / 어떻게»
세 칸을 모두 채우는지 확인한다 (`core/contracts/validation.py`). **«예외가 났다»
만 보는 테스트는 셋이 빈 채로도 통과**하므로(``ValidationError`` 는 셋이 갖춰져야만
만들어지긴 하지만 그 내용이 이 오류에 맞는지는 보지 않는다), 각 테스트는
`field`·`reason`·`action` 의 **내용**을 개별 단언한다.
"""

from __future__ import annotations

import pytest

from core.contracts.der import DispatchContext
from core.contracts.units import HOURS_PER_YEAR
from core.contracts.validation import ValidationError
from core.der.pv import OperatingMode
from tests.der.test_pv import make_pv_1kw, make_pv_3kw

# ── §1 운전 방법 (DV-14) ──────────────────────────────────────────────


@pytest.mark.req("FR-105-AC1")
def test_unknown_operating_mode_carries_field_reason_action() -> None:
    """선언 목록 밖 운전 방법은 field·reason·action 셋을 모두 채운 채 거부된다."""
    with pytest.raises(ValidationError) as exc:
        make_pv_1kw(operating_mode="야간 발전")
    err = exc.value
    assert err.field == "pv.operating_mode"
    assert "야간 발전" in err.reason
    for mode in OperatingMode:
        assert mode.value in err.action
    assert err.rule == "DV-14"


# ── §2 이용률 XOR 시계열 (FR-102-AC1.PV) ─────────────────────────────


@pytest.mark.req("FR-102-AC1.PV")
def test_capacity_factor_and_profile_both_given_carries_field_reason_action() -> None:
    with pytest.raises(ValidationError) as exc:
        make_pv_1kw(capacity_factor=0.15, generation_profile_kwh=[0.15] * HOURS_PER_YEAR)
    err = exc.value
    assert err.field == "pv.capacity_factor"
    assert "둘 다 주었습니다" in err.reason
    assert "capacity_factor" in err.action
    assert "generation_profile_kwh" in err.action


@pytest.mark.req("FR-102-AC1.PV")
def test_capacity_factor_and_profile_both_missing_carries_field_reason_action() -> None:
    with pytest.raises(ValidationError) as exc:
        make_pv_1kw(capacity_factor=None, generation_profile_kwh=None)
    err = exc.value
    assert err.field == "pv.capacity_factor"
    assert "둘 다 주지 않았습니다" in err.reason
    assert "capacity_factor" in err.action
    assert "generation_profile_kwh" in err.action


# ── §3 시계열 행수 (DV-4 · FR-301-AC3) ───────────────────────────────


@pytest.mark.req("FR-301-AC3")
def test_profile_length_mismatch_carries_field_reason_action() -> None:
    with pytest.raises(ValidationError) as exc:
        make_pv_1kw(capacity_factor=None, generation_profile_kwh=[0.15] * 8759)
    err = exc.value
    assert err.field == "pv.generation_profile_kwh"
    assert "8759행" in err.reason
    assert "8760" in err.reason
    assert "8760" in err.action  # 조치에 허용 행수가 구체적으로 들어가야 한다
    assert err.rule == "DV-4"


@pytest.mark.req("NFR-303-M1")
def test_profile_negative_step_carries_field_reason_action() -> None:
    profile = [0.15] * HOURS_PER_YEAR
    profile[3] = -2.0
    with pytest.raises(ValidationError) as exc:
        make_pv_1kw(capacity_factor=None, generation_profile_kwh=profile)
    err = exc.value
    assert err.field == "pv.generation_profile_kwh"
    assert "3번째" in err.reason
    assert "-2.0" in err.reason
    assert "0 이상" in err.action


# ── §4 이중 계상 (DV-12 · FR-402-AC2.A) ──────────────────────────────


@pytest.mark.req("FR-402-AC2.A")
def test_double_counted_allocation_carries_field_reason_action() -> None:
    pv = make_pv_1kw()
    total = pv.annual_generation_kwh(year=1)
    with pytest.raises(ValidationError) as exc:
        pv.check_allocation(year=1, self_consumption_kwh=total, surplus_kwh=total)
    err = exc.value
    assert err.field == "pv.allocation"
    assert "이중 계상" in err.reason
    assert "자가소비" in err.action and "잉여판매" in err.action
    assert err.rule == "DV-12"


# ── §5 계통 연계 상한 (FR-301-AC4) ───────────────────────────────────


@pytest.mark.req("FR-301-AC4")
def test_grid_limit_exceeded_carries_field_reason_action() -> None:
    pv = make_pv_1kw(capacity_factor=0.5, operating_mode=OperatingMode.SELF_CONSUMPTION_FIRST)
    ctx = DispatchContext(steps=24, dt=pv.dt, year=1, grid_limit_kw=[0.2] * 24)
    with pytest.raises(ValidationError) as exc:
        pv.dispatch(ctx)
    err = exc.value
    assert err.field == "pv.operating_mode"
    assert "연계 용량 상한" in err.reason
    assert OperatingMode.CURTAILMENT.value in err.action


# ── §6 REC 가중치·단가 ────────────────────────────────────────────────


@pytest.mark.req("NFR-303-M1")
def test_negative_rec_weight_carries_field_reason_action() -> None:
    pv = make_pv_1kw()
    with pytest.raises(ValidationError) as exc:
        pv.rec_revenue(year=1, rec_price_won_per_mwh=70_000.0, rec_weight=-1.0)
    err = exc.value
    assert err.field == "pv.rec_weight"
    assert "-1.0" in err.reason
    assert "0 이상" in err.action


@pytest.mark.req("NFR-303-M1")
def test_negative_rec_price_carries_field_reason_action() -> None:
    pv = make_pv_1kw()
    with pytest.raises(ValidationError) as exc:
        pv.rec_revenue(year=1, rec_price_won_per_mwh=-1.0, rec_weight=1.0)
    err = exc.value
    assert err.field == "pv.rec_price_won_per_mwh"
    assert "-1.0" in err.reason
    assert "0 이상" in err.action


# ── §7 분석기간 (horizon) ────────────────────────────────────────────


@pytest.mark.req("NFR-303-M1")
def test_zero_horizon_in_fixed_om_cumulative_carries_field_reason_action() -> None:
    pv = make_pv_1kw()
    with pytest.raises(ValidationError) as exc:
        pv.fixed_om_cumulative(horizon=0)
    err = exc.value
    assert err.field == "pv.horizon"
    assert "0" in err.reason
    assert "1 이상" in err.action


@pytest.mark.req("NFR-303-M1")
def test_negative_horizon_in_replacement_schedule_carries_field_reason_action() -> None:
    pv = make_pv_1kw()
    with pytest.raises(ValidationError) as exc:
        pv.replacement_schedule(horizon=-3)
    err = exc.value
    assert err.field == "pv.horizon"
    assert "-3" in err.reason
    assert "1 이상" in err.action


# ── §8 할인율 ─────────────────────────────────────────────────────────


@pytest.mark.req("NFR-303-M1")
def test_discount_rate_at_minus_one_carries_field_reason_action() -> None:
    pv = make_pv_3kw()
    with pytest.raises(ValidationError) as exc:
        pv.discounted_salvage_value(year=20, discount_rate=-1.0)
    err = exc.value
    assert err.field == "pv.discount_rate"
    assert "-1.0" in err.reason
    assert "-100" in err.action


# ── §9 공유 헬퍼(_positive · _in_range · _non_negative) ──────────────
# 세 헬퍼는 raise 지점이 각각 하나뿐이지만 생성자 필드 10여 개가 공유한다.
# 헬퍼별로 대표 필드 하나씩만 확인한다 — 나머지 필드는 같은 코드 경로다.


@pytest.mark.req("NFR-303-M1")
def test_non_positive_capacity_carries_field_reason_action() -> None:
    """`_positive` 경로 — 대표 필드 `capacity_kw`."""
    with pytest.raises(ValidationError) as exc:
        make_pv_1kw(capacity_kw=0.0)
    err = exc.value
    assert err.field == "pv.capacity_kw"
    assert "용량(kW)" in err.reason
    assert "0보다 큰" in err.action


@pytest.mark.req("NFR-303-M1")
def test_out_of_range_azimuth_carries_field_reason_action() -> None:
    """`_in_range` 경로 — 대표 필드 `azimuth_deg`."""
    with pytest.raises(ValidationError) as exc:
        make_pv_1kw(azimuth_deg=400.0)
    err = exc.value
    assert err.field == "pv.azimuth_deg"
    assert "400.0" in err.reason
    assert "0.0~360.0" in err.action


@pytest.mark.req("NFR-303-M1")
def test_negative_unit_capex_carries_field_reason_action() -> None:
    """`_non_negative` 경로 — 대표 필드 `unit_capex_won_per_kw`."""
    with pytest.raises(ValidationError) as exc:
        make_pv_1kw(unit_capex_won_per_kw=-1.0)
    err = exc.value
    assert err.field == "pv.unit_capex_won_per_kw"
    assert "설비 단가(원/kW)" in err.reason
    assert "0 이상" in err.action
