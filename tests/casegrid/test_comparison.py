"""FR-202 다중 모델 동시 비교 — Phase 1 범위 (N=2).

**기대값을 구현 출력에서 옮겨 적지 않는다.** 이 파일의 단언은 두 종류뿐이다.

1. **손으로 따질 수 있는 관계** — 같은 편익·같은 전제 위에서 설비단가만 낮춘
   변형은 NPV 가 더 크고 회수기간이 더 짧으며 필요 지원율이 더 낮다. 대장이
   `capex.ess.second_life`(30만원/kWh) < `capex.ess.new`(50만원/kWh) 라고
   적고 있으므로 부등호의 방향은 구현을 보지 않아도 정해진다.
2. **계약** — 반환 형태, 오류 조건, 강조 대상.

수치는 전부 `docs/assumptions.yaml` 에서 읽는다 (NFR-202).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.assumption.provider import AssumptionSet
from core.casegrid.comparison import (
    AssumptionSetMismatch,
    ComparisonTable,
    compare_models,
)
from core.der.ess import ESSOperatingMode
from core.der.pv import OperatingMode
from core.model.model import Model
from core.model.schemas import DERConfig, ModelConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER = REPO_ROOT / "docs" / "assumptions.yaml"

# 모델링 파라미터 — 대장 항목이 아니다 (할인율·판매단가·기본요금은 사업 조건이며
# 대장은 설비단가·요금표를 다룬다). 호출자가 넘기는 값이므로 여기서 고정한다.
DISCOUNT_RATE = 0.045
SALE_PRICE_WON_PER_KWH = 120.0
DEMAND_CHARGE_WON_PER_KW_MONTH = 8_320.0
HORIZON_YEARS = 20


def _ledger() -> AssumptionSet:
    return AssumptionSet.load_from_yaml(str(LEDGER))


def _variant(name: str, *, ess_capex_won_per_kwh: float, provider: AssumptionSet) -> Model:
    """PV + ESS 2자원 변형. ESS 설치단가만 다르다."""
    pv_capex = provider.require_float("capex.pv.rooftop")
    config = ModelConfig(
        name=name,
        resources=[
            DERConfig(
                tag="PV",
                params={
                    "name": f"{name}-pv",
                    "capacity_kw": 3.0,
                    "capacity_factor": 0.15,
                    "unit_capex_won_per_kw": pv_capex,
                    "fixed_om_won_per_year": 100_000,
                    "escalation_rate": 0.02,
                    "self_consumption_ratio": 0.0,
                    "operating_mode": OperatingMode.FULL_EXPORT.value,
                },
            ),
            DERConfig(
                tag="ESS",
                params={
                    "name": f"{name}-ess",
                    "capacity_kwh": 10.0,
                    "power_kw": 5.0,
                    "rte_pct": 90.0,
                    "soc_min_pct": 10.0,
                    "soc_max_pct": 90.0,
                    "cycle_life": 6_000,
                    "calendar_life": 20,
                    "eol_soh_pct": 80.0,
                    "cycles_per_year": 365.0,
                    "operating_mode": ESSOperatingMode.PEAK_SHAVING.value,
                    "capex_unit_won_per_kwh": ess_capex_won_per_kwh,
                    "fixed_om_won_per_year": 100_000,
                },
            ),
        ],
    )
    return Model(config, provider)


def _two_variants(provider: AssumptionSet) -> tuple[Model, Model]:
    """신품 ESS 변형과 사용후배터리 ESS 변형 — Phase 1 의 2변형."""
    return (
        _variant(
            "신품ESS형",
            ess_capex_won_per_kwh=provider.require_float("capex.ess.new"),
            provider=provider,
        ),
        _variant(
            "사용후배터리형",
            ess_capex_won_per_kwh=provider.require_float("capex.ess.second_life"),
            provider=provider,
        ),
    )


def _run(models: tuple[Model, ...]) -> ComparisonTable:
    return compare_models(
        models,
        discount_rate=DISCOUNT_RATE,
        sale_price_won_per_kwh=SALE_PRICE_WON_PER_KWH,
        demand_charge_won_per_kw_month=DEMAND_CHARGE_WON_PER_KW_MONTH,
        horizon_years=HORIZON_YEARS,
    )


# ── AC1 일괄 실행 ─────────────────────────────────────────────────────────


@pytest.mark.req("FR-202-AC1")
def test_two_models_on_one_assumption_set_run_in_one_batch() -> None:
    """하나의 AssumptionSet 을 참조하는 두 모델이 한 번의 호출로 실행된다."""
    provider = _ledger()
    table = _run(_two_variants(provider))

    assert [row.model_name for row in table.rows] == ["신품ESS형", "사용후배터리형"]
    # 실행되었다는 것은 지표가 나왔다는 뜻이다 — 자리만 잡혀 있는 것과 다르다.
    for row in table.rows:
        assert row.npv is not None
        assert row.payback_years > 0.0


@pytest.mark.req("FR-202-AC1")
def test_a_model_built_on_a_different_assumption_set_is_refused() -> None:
    """전제가 다른 모델이 비교에 섞이면 실행을 거부한다.

    이것이 없으면 「같은 전제 위의 비교」라는 표의 전제 자체가 무너진다.
    """
    provider = _ledger()
    other = AssumptionSet(
        name="다른대장.yaml",
        version="9.9",
        items=dict(provider.items()),
    )
    mixed = (_variant("A", ess_capex_won_per_kwh=500_000.0, provider=provider),
             _variant("B", ess_capex_won_per_kwh=500_000.0, provider=other))

    with pytest.raises(AssumptionSetMismatch) as excinfo:
        _run(mixed)
    # 무엇이 어긋났는지 말해야 고칠 수 있다.
    assert "다른대장.yaml" in str(excinfo.value)


@pytest.mark.req("FR-202-AC1")
def test_an_empty_comparison_is_refused() -> None:
    """비교할 것이 없는 비교표는 「전부 통과」로 읽힌다."""
    with pytest.raises(ValueError):
        _run(())


# ── AC2 비교표 4지표 ──────────────────────────────────────────────────────


@pytest.mark.req("FR-202-AC2")
def test_comparison_table_carries_all_four_metrics_per_model() -> None:
    """NPV·IRR·회수기간·필요 지원율이 모델별로 나란히 선다."""
    table = _run(_two_variants(_ledger()))

    for row in table.rows:
        assert row.npv is not None
        assert row.irr is not None
        assert row.payback_years is not None
        assert row.required_subsidy_rate is not None


@pytest.mark.req("FR-202-AC2")
def test_cheaper_variant_dominates_on_every_metric() -> None:
    """설비단가만 낮춘 변형은 네 지표 전부에서 낫다.

    편익·전제·기간이 모두 같고 초기투자만 작으므로 부등호 방향은 구현과
    무관하게 정해진다. **이 단언이 지표가 실제 계산에서 나왔다는 증거다** —
    상수를 돌려주는 구현은 등호가 되어 여기서 걸린다.
    """
    new_ess, second_life = _run(_two_variants(_ledger())).rows

    assert second_life.npv > new_ess.npv
    assert second_life.irr > new_ess.irr
    assert second_life.payback_years < new_ess.payback_years
    assert second_life.required_subsidy_rate <= new_ess.required_subsidy_rate


@pytest.mark.req("FR-202-AC2")
def test_metrics_move_when_the_discount_rate_moves() -> None:
    """할인율을 올리면 NPV 가 내려간다 — 지표가 입력에 반응하는지 본다."""
    models = _two_variants(_ledger())
    base = _run(models)
    steeper = compare_models(
        models,
        discount_rate=DISCOUNT_RATE * 2.0,
        sale_price_won_per_kwh=SALE_PRICE_WON_PER_KWH,
        demand_charge_won_per_kw_month=DEMAND_CHARGE_WON_PER_KW_MONTH,
        horizon_years=HORIZON_YEARS,
    )

    for base_row, steep_row in zip(base.rows, steeper.rows, strict=True):
        assert steep_row.npv < base_row.npv


# ── AC3 전제 동일성 보장 · 차이 강조 ──────────────────────────────────────


@pytest.mark.req("FR-202-AC3")
def test_shared_assumption_set_id_is_shown() -> None:
    """비교표는 어떤 전제 위에 선 것인지 스스로 밝힌다."""
    provider = _ledger()
    table = _run(_two_variants(provider))

    assert provider.set_name in table.assumption_set_id
    assert provider.set_version in table.assumption_set_id


@pytest.mark.req("FR-202-AC3")
def test_a_model_with_an_overridden_value_is_highlighted() -> None:
    """전제를 덮어쓴 모델은 그 항목이 강조된다.

    **`override()` 는 이름과 판본을 그대로 둔다.** 그래서 ID 대조만으로는
    「같은 전제」로 보이면서 값이 다를 수 있다 — 이 조항이 막는 것이 정확히
    그것이므로, 강조가 없으면 ID 표시는 거짓 안심이 된다.
    """
    base = _ledger()
    overridden = base.override({"capex.pv.rooftop": base.require_float("capex.pv.rooftop") * 2.0})

    # ID 는 같다. 그것이 이 시험의 전제다.
    assert base.set_name == overridden.set_name
    assert base.set_version == overridden.set_version

    table = _run((
        _variant("표준형", ess_capex_won_per_kwh=500_000.0, provider=base),
        _variant("전제변경형", ess_capex_won_per_kwh=500_000.0, provider=overridden),
    ))

    standard, changed = table.rows
    assert dict(standard.divergent_assumptions) == {}
    assert set(changed.divergent_assumptions) == {"capex.pv.rooftop"}
    assert table.divergent_keys == frozenset({"capex.pv.rooftop"})


@pytest.mark.req("FR-202-AC3")
def test_no_override_means_nothing_is_highlighted() -> None:
    """음성 쌍 — 덮어쓴 것이 없으면 강조도 없다.

    강조가 항상 켜져 있으면 그것은 강조가 아니다.
    """
    table = _run(_two_variants(_ledger()))

    assert table.divergent_keys == frozenset()
    for row in table.rows:
        assert dict(row.divergent_assumptions) == {}
