"""End-to-end case runner — wraps DER → Engine → Benefit → CBA into a CaseRunner.

This module translates case-grid variable levels into concrete resource parameters,
executes the full dispatch → benefit → CBA pipeline for one case, and returns
metric dict suitable for ``run_cases()``.

The pipeline mirrors ``tests/integration/test_wave2_end_to_end.py`` but is
parameterised by case variable values so the case-grid can drive it.

All numeric parameters come from the *level_map* argument, which the caller
builds from ``docs/assumptions.yaml``.  No financial/quantity value is
hardcoded in this module (NFR-202).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.cba.metrics import npv, payback_discounted
from core.cba.proforma import benefit_row, check_analysis_period, fixed_om_row
from core.contracts.der import DispatchContext, DispatchResult
from core.contracts.units import Money, Year
from core.contracts.valuestream import ValueStream
from core.der.ess import ESS, ESSOperatingMode
from core.der.pv import PV, OperatingMode
from core.engine.rule_based import RuleBasedEngine
from core.valuestream import PeakShaving, SurplusSale
from core.valuestream.exclusion_table import assert_no_exclusions

#: 분석기간 기본값(년). **`DV-5` 문면의 「기본 20년」이 이 상수다.**
#: 상한(최장 자원 수명 × 2)은 이 값이 아니라 `check_analysis_period()` 가 잰다 —
#: 기본값과 상한을 한 상수에 겹쳐 두면 자원 수명이 바뀌어도 아무 일이 없다.
HORIZON_YEARS = 20
STEPS_PER_DAY = 24
SECONDS_PER_HOUR = 3_600
DAYS_PER_YEAR = 365


def _resolve(
    level: str | object,
    var_name: str,
    level_map: Mapping[str, Mapping[str, float]],
) -> float:
    """Translate a case variable level name to a numeric value."""
    key = str(level)
    mapping = level_map.get(var_name, {})
    if key in mapping:
        return mapping[key]
    raise ValueError(f"Unknown level {key!r} for variable {var_name!r}")


def run_single_case_e2e(
    case_values: dict[str, object],
    *,
    level_map: Mapping[str, Mapping[str, float]],
    extra_value_streams: Sequence[ValueStream] = (),
    horizon_years: int = HORIZON_YEARS,
) -> dict[str, float]:
    """Execute the full DER → Engine → Benefit → CBA pipeline for one case.

    *level_map* maps each case-grid variable name (e.g. ``"pv_unit_cost"``)
    to a ``{level_name: numeric_value}`` dict.  The caller builds this from
    ``AssumptionProvider`` so that all financial/quantity parameters originate
    from ``docs/assumptions.yaml`` (NFR-202).

    Returns a metric dict with at least ``npv`` so the case-grid can collect it.

    ★ **배타 규칙을 실행 경로가 지난다 (FR-402-AC2.A · DV-12).**
    ---------------------------------------------------------
    R26 재검증까지 `assert_no_exclusions()` 를 부르는 배포 코드가 **0곳**이었다.
    거부 기계는 R16 이 만들어 두었고 테스트도 촘촘했지만, **그 테스트가 전부 그
    함수를 직접 불렀다.** 실행은 여기(`run_single_case_e2e`)를 지나는데 여기서는
    편익을 조립해 CBA 까지 가면서 배타 검사를 한 번도 부르지 않았다 — DoD 6 의
    *「배타 규칙 위반 조합은 실행이 거부됨」* 이 실행 경로에서는 성립하지 않았다.

    `extra_value_streams` 를 둔 이유는 **배선을 검증 가능하게 만들기 위해서**다.
    내장 편익 둘(`SurplusSale`·`PeakShaving`)은 배타 쌍이 아니므로, 인자가 없으면
    위반 조합을 **진입점으로 넣어 볼 방법이 없고** 그러면 이 호출이 실제로
    무언가를 막는지 아무도 확인할 수 없다 — 그것이 이 저장소가 고치러 온 형태다.
    넘긴 편익은 검사에 함께 들어가고, 화폐가치 계산은 아직 내장 둘만 한다
    (편익 선택 API 는 `FR-402-AC2.A` 의 「선택 시」 절반이며 아직 없다).

    ★ **분석기간 상한을 실행 경로가 지난다 (DV-5).**
    ---------------------------------------------------
    `check_analysis_period()` 는 R24 가 만들었으나 **부르는 배포 코드가 0곳**
    이었다 — 사용자가 200년을 넣어도 그 함수를 지나지 않으면 아무도 막지
    않는다. 위 배타 규칙과 **같은 자리에서 같은 형태**였다.

    `horizon_years` 를 인자로 둔 이유도 `extra_value_streams` 와 같다:
    **상한을 넘는 케이스를 진입점으로 넣어 볼 방법이 없으면** 이 호출이 실제로
    무언가를 막는지 아무도 확인할 수 없다. 기본값은 종전 상수 그대로이므로
    호출측 동작은 바뀌지 않는다.

    ⚠ **이 인자는 검사 전용이 아니다** — 프로포마 행의 연도 범위도 이 값을
    쓴다. 검사만 하고 계산이 상수를 계속 쓰면 **재는 것과 쓰는 것이 갈리고**,
    그때 이 검사는 아무도 쓰지 않는 수를 지키게 된다.

    ⚠ **분석기간의 「소유자」를 정한 것이 아니다.** 사용자가 고르는 분석기간이
    어느 층에 사는가는 여전히 미결이다(`Scenario` 는 `DV-11` 이 금지). 여기서
    닫은 것은 *「케이스 실행이 상한을 지난다」* 이지 *「값을 누가 갖는가」* 가
    아니다.
    """
    pv_capex = _resolve(
        case_values.get("pv_unit_cost", "base"), "pv_unit_cost", level_map
    )
    ess_capex = _resolve(
        case_values.get("ess_unit_cost", "base"), "ess_unit_cost", level_map
    )
    discount_rate = _resolve(
        case_values.get("discount_rate", "base"), "discount_rate", level_map
    )

    # 1. Resources
    pv = PV(
        name="e2e-pv",
        capacity_kw=3.0,
        capacity_factor=0.15,
        unit_capex_won_per_kw=pv_capex,
        fixed_om_won_per_year=100_000,
        escalation_rate=0.02,
        self_consumption_ratio=0.0,
        operating_mode=OperatingMode.FULL_EXPORT,
    )
    ess = ESS(
        name="e2e-ess",
        capacity_kwh=10.0,
        power_kw=5.0,
        rte_pct=90.0,
        soc_min_pct=10.0,
        soc_max_pct=90.0,
        cycle_life=6_000,
        calendar_life=20,
        eol_soh_pct=80.0,
        cycles_per_year=365.0,
        operating_mode=ESSOperatingMode.PEAK_SHAVING,
        capex_unit_won_per_kwh=ess_capex,
        fixed_om_won_per_year=100_000,
    )

    # ★ **자원이 서자마자 분석기간을 잰다 (DV-5).** 수명은 자원이 갖고 있으므로
    # 여기가 규칙을 평가할 수 있는 가장 이른 자리다 — 디스패치·편익·CBA 어느
    # 것도 돌기 전에 거부한다. 늦게 두면 상한을 넘긴 케이스의 중간 산출물이
    # 한 번은 만들어지고, 그것이 로그·캐시로 새어 나간다(`DV-10` 과 같은 이유).
    check_analysis_period(
        analysis_years=horizon_years,
        asset_lifetimes_years=[pv.lifetime, ess.lifetime],
    )

    # 2. Dispatch
    ctx = DispatchContext(steps=STEPS_PER_DAY, dt=SECONDS_PER_HOUR, year=Year(1))
    dispatch = RuleBasedEngine().run([pv, ess], ctx)

    # 3. Benefits (one day, annualised)
    grid_export_result = DispatchResult(
        electric=list(dispatch.grid_export),
        heat=[0.0] * ctx.steps,
        cool=[0.0] * ctx.steps,
        fuel=[0.0] * ctx.steps,
    )
    surplus = SurplusSale(sale_price_won_per_kwh=120.0)
    peak = PeakShaving(
        monthly_peak_reduction_kw=[ess.reducible_peak_kw(year=1)] * 12,
        demand_charge_won_per_kw_month=8_320.0,
    )

    # ★ **CBA 에 닿기 전에 거부한다.** 계산한 뒤에 막으면 「예외는 나지만 이미
    # 다 돌린 뒤」가 되고, 무엇보다 **위반 조합의 NPV 가 한 번은 만들어진다.**
    assert_no_exclusions([surplus, peak, *extra_value_streams])

    surplus_per_day = surplus.annual_value(grid_export_result, year=1)
    peak_per_day = peak.annual_value(grid_export_result, year=1)
    annual_benefit = int(surplus_per_day * DAYS_PER_YEAR + peak_per_day)

    # 4. Proforma → NPV
    initial_investment = Money(pv.capex(year=1) + ess.capex(year=1))
    benefit_rows = [
        benefit_row(
            "E2EBenefit",
            {year: annual_benefit for year in range(1, horizon_years + 1)},
        ),
    ]
    cost_rows = [
        fixed_om_row(
            "PVFixedOM",
            start_year=1,
            end_year=horizon_years,
            annual_amount_won=int(pv.fixed_om(year=1)),
            escalation_rate=0.02,
        ),
        fixed_om_row(
            "ESSFixedOM",
            start_year=1,
            end_year=horizon_years,
            annual_amount_won=int(ess.fixed_om(year=1)),
        ),
    ]
    all_rows = list(benefit_rows) + list(cost_rows)
    project_npv = npv(initial_investment, all_rows, discount_rate=discount_rate)
    discounted_payback = payback_discounted(
        initial_investment, all_rows, discount_rate=discount_rate
    )

    return {
        "npv": float(project_npv),
        "payback_years": discounted_payback,
    }
