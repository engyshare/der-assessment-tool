"""영향도 스윕 한 덩어리 — `core/report/case_report.py` 에서 R54/WP-2 가 옮겼다.
R72/WP-5: 단일 실행 리포트에서 민감도 스윕(_influences)을 제거하고
대장 투입 파라미터 메타데이터 수집(_ledger_inputs)으로 간소화했다.
"""
from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from core.assumption.provider import AssumptionSet
from core.casegrid.appliance_load import ApplianceSeasonShares
from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import (
    design_variables,
    ledger_backed_variables,
    ledger_unit_scales,
)
from core.casegrid.profiles import DailyShapes
from core.cba.baseline import BaselineArrangement, PoolMeteringDeclaration
from core.contracts.assumptions import AssumptionValue
from core.der.ess import ESSOperatingMode
from core.der.pv import PVAllocationPriority
from core.incentive.schemas import IncentiveScheme
from core.valuestream import DistributedSubItems

#: 주 지표 — 표시되는 결론이다 (`FR-1002-AC1`).
HEADLINE_METRIC = "payback_years"
#: 전환 판정에 쓰는 축.
CONCLUSION_METRIC = "npv"
#: 결론을 읽는 변형 — **지원을 반영한 사업**이다.
PLAN_VARIANT = "as_planned"
#: 무지원 기준선 — `FR-607-AC1` 이 「모든 실행에 자동 포함」을 요구하는 변형.
BASELINE_VARIANT = "unsupported"
#: 지원의 **상한** — 사업비 전액(100%).
MAX_SUBSIDY_RATE = 1.0

#: 파이프라인이 읽지만 계산에 쓰지 않는 대장 축 — 선언 목록(R72 전에는 스윕으로 측정).
DEAD_AXES: frozenset[str] = frozenset(
    {"surplus_sale_price", "grid_supply_allowance"}
)


@dataclass(frozen=True)
class LedgerInput:
    """리포트에 투입된 대장 기반 파라미터 (R72/WP-5)."""

    variable: str
    ledger_key: str
    used_value: float
    value_unit: str
    source: str
    confidence: str
    base_year: str
    verified_at: date | None
    derivation_method: str
    #: 대장 검토 범위(`sensitivity.low`·`high`) — 스윕 없이 대장에서 읽는다.
    low: float
    high: float
    unread_by_pipeline: bool


def break_even_subsidy_rate(
    *, subsidy_rate: float, npv_won: float, total_project_cost_won: float
) -> float:
    """결론 축(NPV)을 0으로 만드는 지원율."""
    if total_project_cost_won <= 0.0:
        return 0.0
    return subsidy_rate - (npv_won / total_project_cost_won)


def residual_gap_at_full_support_won(
    *, subsidy_rate: float, npv_won: float, total_project_cost_won: float
) -> float:
    """최대 지원(100%) 시에도 남는 결손 금액(원)."""
    return npv_won + (MAX_SUBSIDY_RATE - subsidy_rate) * total_project_cost_won


class _Sweeper:
    """용량 검토 등에서 다변수 스윕을 수행하는 도우미 (R54)."""

    def __init__(
        self,
        *,
        level_map: Mapping[str, Mapping[str, float]],
        horizon_years: int,
        scheme: IncentiveScheme | None,
        daily_shapes: DailyShapes,
        rec_price_won_per_unit: float,
        rec_weight_pv: float,
        distributed_sub_items: DistributedSubItems | None,
        baseline_arrangement: BaselineArrangement,
        pool_metering: PoolMeteringDeclaration | None = None,
        household_count: int | None = None,
        extra_appliance_load_kwh: float = 0.0,
        appliance_season_shares: ApplianceSeasonShares | None = None,
        dr_shiftable_share_pct: float = 0.0,
        nwas_price_won_per_kwh: float,
        cp_price_won_per_kw_month: float,
        ess_operating_mode: ESSOperatingMode | str | None,
        pv_allocation_priority: PVAllocationPriority | str | None,
    ) -> None:
        self._baseline_arrangement = baseline_arrangement
        self._household_count = household_count
        self._extra_appliance_load_kwh = extra_appliance_load_kwh
        self._appliance_season_shares = appliance_season_shares
        self._dr_shiftable_share_pct = dr_shiftable_share_pct
        self._pool_metering = pool_metering
        self._nwas_price_won_per_kwh = nwas_price_won_per_kwh
        self._cp_price_won_per_kw_month = cp_price_won_per_kw_month
        self._ess_operating_mode = ess_operating_mode
        self._pv_allocation_priority = pv_allocation_priority
        self._level_map = level_map
        self._horizon_years = horizon_years
        self._scheme = scheme
        self._daily_shapes = daily_shapes
        self._rec_price_won_per_unit = rec_price_won_per_unit
        self._rec_weight_pv = rec_weight_pv
        self._distributed_sub_items = distributed_sub_items
        self._memo: dict[tuple[tuple[str, float], ...], float] = {}

    def conclusion_at(self, variable: str, value: float) -> float:
        """그 변수를 `value` 로 두었을 때의 결론 축(NPV, 원)."""
        return self.conclusion_at_many({variable: value})

    def conclusion_at_many(self, assignment: Mapping[str, float]) -> float:
        """여럿을 함께 옮겼을 때의 결론 축."""
        key = tuple(sorted(assignment.items()))
        cached = self._memo.get(key)
        if cached is not None:
            return cached
        probe = {
            name: dict(levels) for name, levels in self._level_map.items()
        }
        for variable, value in assignment.items():
            probe[variable] = {**probe[variable], "base": value}
        outcome = run_single_case_e2e(
            {},
            level_map=probe,
            horizon_years=self._horizon_years,
            scheme=self._scheme,
            daily_shapes=self._daily_shapes,
            annual_load_kwh=probe["household_load_annual_kwh"]["base"],
            household_count=self._household_count,
            extra_appliance_load_kwh=self._extra_appliance_load_kwh,
            appliance_season_shares=self._appliance_season_shares,
            dr_shiftable_share_pct=self._dr_shiftable_share_pct,
            rec_price_won_per_unit=self._rec_price_won_per_unit,
            rec_weight_pv=self._rec_weight_pv,
            distributed_sub_items=self._distributed_sub_items,
            baseline_arrangement=self._baseline_arrangement,
            pool_metering=self._pool_metering,
            nwas_price_won_per_kwh=self._nwas_price_won_per_kwh,
            cp_price_won_per_kw_month=self._cp_price_won_per_kw_month,
            ess_operating_mode=self._ess_operating_mode,
            pv_allocation_priority=self._pv_allocation_priority,
        )
        result = float(outcome.variants[PLAN_VARIANT][CONCLUSION_METRIC])
        self._memo[key] = result
        return result


def _ledger_inputs(
    *,
    level_map: Mapping[str, Mapping[str, float]],
    provider: AssumptionSet,
    provenance: Callable[[AssumptionValue | None], dict[str, Any]],
    read_keys: frozenset[str] | set[str] | Collection[str],
) -> tuple[LedgerInput, ...]:
    """level_map 의 변수 중 설계 변수가 아니고 ledger_backed_variables() 에 대장 키가 있으며
    그 키가 read_keys 에 든 것만 변수 이름순으로 정렬해 돌려준다 (R72/WP-5).
    """
    design = {variable.name for variable in design_variables()}
    ledger_keys = ledger_backed_variables()
    scales = ledger_unit_scales()
    inputs: list[LedgerInput] = []

    for variable, levels in level_map.items():
        if variable in design:
            continue
        ledger_key = ledger_keys.get(variable)
        if ledger_key is None or ledger_key not in read_keys:
            continue
        scale = scales.get(variable, 1.0) or 1.0
        used_value = float(levels["base"]) / scale
        low = float(levels["low"]) / scale if "low" in levels else 0.0
        high = float(levels["high"]) / scale if "high" in levels else 0.0
        effective = provider.get(ledger_key)
        prov = provenance(effective)
        inputs.append(
            LedgerInput(
                variable=variable,
                ledger_key=ledger_key,
                used_value=used_value,
                value_unit=prov["value_unit"],
                source=prov["source"],
                confidence=prov["confidence"],
                base_year=prov["base_year"],
                verified_at=prov["verified_at"],
                derivation_method=prov["derivation_method"],
                low=low,
                high=high,
                unread_by_pipeline=variable in DEAD_AXES,
            )
        )
    return tuple(sorted(inputs, key=lambda x: x.variable))
