"""다중 모델 동시 비교 — FR-202 `AC1`~`AC3` (Phase 1, N=2 범위).

**왜 실행기가 필요한가.** 두 모델의 NPV 를 나란히 놓는 것만으로는 비교가
되지 않는다. 두 값이 같은 전제 위에서 나온 것이어야 뺄셈에 뜻이 생긴다.
그래서 이 모듈은 표를 그리는 것이 아니라 **전제의 동일성을 보장한 채 N개를
한 번에 돌린다** — 그것이 `AC3` 가 *"시스템적으로 보장"* 이라 쓴 것이다.

**여기서 가장 조심할 것.** `AssumptionSet.override()` 는 이름과 판본을 그대로
둔 사본을 만든다. 그러므로 ID 대조만으로는 **「같은 전제」로 보이면서 값이
다를 수 있다.** ID 만 확인하고 통과시키면 그 표시는 거짓 안심이 된다. 이
모듈이 ID 대조와 덮어쓴 항목 강조를 **함께** 하는 이유다.

**이 모듈이 보장하지 못하는 것.** 덮어쓰기 강조는 `get_overrides()` 를
내놓는 제공자(`AssumptionSet`)에 한한다. 그 창구 없이 값을 다르게 내놓는
제공자는 ID 가 같으면 같은 전제로 보인다. 그것은 이 모듈의 한계이며, 고칠
자리는 `AssumptionProvider` 계약이다.

수치 상수는 두지 않는다 (NFR-202). 할인율·판매단가·기본요금·기간은 전부
호출자가 넘긴다 — 대장에서 읽어 넘기는 것은 호출자의 몫이다.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from core.cba.metrics import irr, npv, payback_discounted
from core.cba.proforma import benefit_row, fixed_om_row
from core.contracts.der import DER, DispatchContext, DispatchResult
from core.contracts.schemas import CashFlowRow
from core.contracts.units import Money, Year
from core.engine.rule_based import RuleBasedEngine
from core.incentive.solver import solve_min_subsidy_rate
from core.model.model import Model
from core.valuestream import PeakShaving, SurplusSale

SECONDS_PER_HOUR = 3_600
STEPS_PER_DAY = 24
DAYS_PER_YEAR = 365
MONTHS_PER_YEAR = 12


class AssumptionSetMismatch(ValueError):
    """비교 대상 모델들이 서로 다른 전제 집합 위에 서 있다.

    이것을 통과시키면 비교표의 열 사이에 뺄셈이 성립하지 않는다.
    """


@dataclass(frozen=True)
class ComparisonRow:
    """비교표 한 줄 — 모델 하나의 지표 (`AC2`)."""

    model_name: str
    npv: Money
    irr: float
    payback_years: float
    required_subsidy_rate: float
    divergent_assumptions: Mapping[str, Any]


@dataclass(frozen=True)
class ComparisonTable:
    """비교표 (`AC1`~`AC3`)."""

    assumption_set_id: str
    rows: tuple[ComparisonRow, ...]

    @property
    def divergent_keys(self) -> frozenset[str]:
        """어느 모델에서든 덮어쓰인 전제 키 전체 (`AC3` 강조 대상)."""
        keys: set[str] = set()
        for row in self.rows:
            keys.update(row.divergent_assumptions)
        return frozenset(keys)


def _set_id(provider: Any) -> str:
    return f"{provider.set_name}@{provider.set_version}"


def _overrides_of(provider: Any) -> Mapping[str, Any]:
    getter = getattr(provider, "get_overrides", None)
    if getter is None:
        return MappingProxyType({})
    return MappingProxyType(dict(getter()))


def _peak_reduction_kw(resources: Sequence[DER], *, year: int) -> float:
    """정격 피크 저감량 — 그것을 낼 수 있는 자원만 합산한다.

    자원 종류를 열거하지 않는다. 열거하면 자원이 늘 때마다 이 파일을 고쳐야
    하고, 그것은 NFR-201(코어 수정 0줄)이 막으려는 것이다.
    """
    total = 0.0
    for resource in resources:
        reducible = getattr(resource, "reducible_peak_kw", None)
        if reducible is not None:
            total += float(reducible(year=year))
    return total


def _cash_flows(
    model: Model,
    *,
    sale_price_won_per_kwh: float,
    demand_charge_won_per_kw_month: float,
    horizon_years: int,
) -> tuple[Money, list[CashFlowRow]]:
    """모델 하나를 자원 → 엔진 → 편익 → 프로포마까지 실제로 돌린다.

    **가짜 계산 함수를 받지 않는다.** 편익을 주입받으면 이 실행기는 무엇도
    검증하지 않게 된다 — 17.2 가 그렇게 초록불이었다.
    """
    resources = list(model.resources)
    ctx = DispatchContext(steps=STEPS_PER_DAY, dt=SECONDS_PER_HOUR, year=Year(1))
    dispatch = RuleBasedEngine().run(resources, ctx)

    grid_export = DispatchResult(
        electric=list(dispatch.grid_export),
        heat=[0.0] * ctx.steps,
        cool=[0.0] * ctx.steps,
        fuel=[0.0] * ctx.steps,
    )
    surplus_per_day = SurplusSale(
        sale_price_won_per_kwh=sale_price_won_per_kwh
    ).annual_value(grid_export, year=1)
    peak_per_year = PeakShaving(
        monthly_peak_reduction_kw=[_peak_reduction_kw(resources, year=1)] * MONTHS_PER_YEAR,
        demand_charge_won_per_kw_month=demand_charge_won_per_kw_month,
    ).annual_value(grid_export, year=1)
    annual_benefit = int(surplus_per_day * DAYS_PER_YEAR + peak_per_year)

    rows: list[CashFlowRow] = [
        benefit_row(
            "ComparisonBenefit",
            {year: annual_benefit for year in range(1, horizon_years + 1)},
        )
    ]
    for resource in resources:
        rows.append(
            fixed_om_row(
                f"{resource.name}FixedOM",
                start_year=1,
                end_year=horizon_years,
                annual_amount_won=int(resource.fixed_om(year=1)),
            )
        )

    initial_investment = Money(sum(resource.capex(year=1) for resource in resources))
    return initial_investment, rows


def _required_subsidy_rate(
    initial_investment: Money,
    rows: list[CashFlowRow],
    *,
    discount_rate: float,
) -> float:
    """NPV 0 을 만드는 최소 지원율 (FR-608 역산기 재사용).

    지원은 초기투자를 덜어 주는 형태로 본다. 지원 없이 이미 NPV ≥ 0 이면 0.0
    이고, 100% 지원으로도 못 미치면 1.0 을 넘지 않는 값이 아니라 **미달**이
    보고되어야 하므로 그 경우 1.0 을 돌려주지 않고 solver 의 판정을 따른다.
    """

    def evaluate(rate: float) -> float:
        subsidised = Money(int(float(initial_investment) * (1.0 - rate)))
        return float(npv(subsidised, rows, discount_rate=discount_rate))

    result = solve_min_subsidy_rate(evaluate, 0.0, "NPV")
    return float(result.subsidy_rate)


def compare_models(
    models: Sequence[Model],
    *,
    discount_rate: float,
    sale_price_won_per_kwh: float,
    demand_charge_won_per_kw_month: float,
    horizon_years: int,
) -> ComparisonTable:
    """여러 모델을 하나의 전제 집합 위에서 일괄 실행한다 (`AC1`).

    Phase 1 의 화면 제약은 2변형이지만 (부록 A.1), 실행기 자체는 N 을 세지
    않는다 — 세는 자리는 화면이고, 여기서 막으면 같은 제약이 두 곳에 생긴다.

    Raises:
        ValueError: 비교 대상이 없을 때. 빈 표는 「전부 통과」로 읽힌다.
        AssumptionSetMismatch: 모델들이 서로 다른 전제 집합 위에 있을 때.
    """
    if not models:
        raise ValueError(
            "비교할 모델이 없습니다. 빈 비교표는 「차이가 없다」로 읽힙니다"
        )

    providers = [model.provider for model in models]
    baseline_id = _set_id(providers[0])
    for model, provider in zip(models, providers, strict=True):
        current_id = _set_id(provider)
        if current_id != baseline_id:
            raise AssumptionSetMismatch(
                f"모델 {model.name!r} 의 전제 집합이 다릅니다 "
                f"({current_id} ≠ {baseline_id}). 서로 다른 전제 위의 값은 "
                "나란히 놓아도 비교가 되지 않습니다"
            )

    rows: list[ComparisonRow] = []
    for model, provider in zip(models, providers, strict=True):
        initial_investment, flows = _cash_flows(
            model,
            sale_price_won_per_kwh=sale_price_won_per_kwh,
            demand_charge_won_per_kw_month=demand_charge_won_per_kw_month,
            horizon_years=horizon_years,
        )
        rows.append(
            ComparisonRow(
                model_name=model.name,
                npv=npv(initial_investment, flows, discount_rate=discount_rate),
                irr=irr(initial_investment, flows),
                payback_years=payback_discounted(
                    initial_investment, flows, discount_rate=discount_rate
                ),
                required_subsidy_rate=_required_subsidy_rate(
                    initial_investment, flows, discount_rate=discount_rate
                ),
                divergent_assumptions=_overrides_of(provider),
            )
        )

    return ComparisonTable(assumption_set_id=baseline_id, rows=tuple(rows))
