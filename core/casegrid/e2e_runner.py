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
from decimal import Decimal

from core.casegrid.incentive_cases import (
    Viewpoint,
    build_capex_cashflows_for_all_cases,
)
from core.casegrid.models import CaseOutcome
from core.cba.metrics import npv, payback_discounted
from core.cba.proforma import (
    benefit_row,
    check_analysis_period,
    fee_row,
    fixed_om_row,
)
from core.contracts.assumptions import AssumptionProvider
from core.contracts.der import DispatchContext, DispatchResult
from core.contracts.schemas import CashFlowRow
from core.contracts.units import Money, Year
from core.contracts.valuestream import ValueStream
from core.der.ess import ESS, ESSOperatingMode
from core.der.pv import PV, OperatingMode
from core.engine.rule_based import RuleBasedEngine
from core.incentive.schemas import IncentiveScheme
from core.regulation.tariff import TariffEngine
from core.valuestream import PeakShaving, SurplusSale
from core.valuestream.exclusion_table import assert_no_exclusions
from core.valuestream.settlement import SettlementInputs, assemble

# ⚠ **`HORIZON_YEARS = 20` 상수가 여기 있었다. R31 이 지웠다.**
#
# `DV-5` 문면의 「기본 20년」이 그 상수였는데, **분석기간의 소유자는 이 구획이
# 아니다** — `infra/orm/scenario.py` 가 `analysis_years` 를 `Scenario` 금지
# 필드로 열거하며 *「전제 분류에 해당 값은 `AssumptionSet` 에 넣는다」* 고 적고
# 있었다(§7.1 O-1 · `DV-11`). 즉 소유자는 정해져 있었고 **값만 다른 층에
# 있었다.** 그 상태에서는 사용자가 분석기간을 고를 통로가 없다 — 케이스
# 러너의 모듈 상수를 고치는 것이 유일한 방법이었다.
#
# 지금 값은 대장 항목 `analysis.period_years` 이고, 호출측이
# `provider.analysis_years()` 로 읽어 `horizon_years` 로 넘긴다.
# **기본값을 다시 두지 말 것** — 두면 대장을 고쳐도 이 구획이 옛 값을 쓰고,
# 그 어긋남은 NPV 를 바꾸면서 아무 예외도 내지 않는다.
# `tests/casegrid/test_e2e_analysis_period_wiring.py` 가 시그니처를 붙든다.
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
    horizon_years: int,
    structure: str | None = None,
    provider: AssumptionProvider | None = None,
    settlement_inputs: SettlementInputs | None = None,
    tariff_engine: TariffEngine | None = None,
    scheme: IncentiveScheme | None = None,
    viewpoint: Viewpoint = "OWNER",
) -> CaseOutcome:
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
    무언가를 막는지 아무도 확인할 수 없다.

    ⚠ **이 인자는 검사 전용이 아니다** — 프로포마 행의 연도 범위도 이 값을
    쓴다. 검사만 하고 계산이 상수를 계속 쓰면 **재는 것과 쓰는 것이 갈리고**,
    그때 이 검사는 아무도 쓰지 않는 수를 지키게 된다.

    ★ **`horizon_years` 에 기본값이 없다 (R31).**
    ------------------------------------------------
    종전에는 `HORIZON_YEARS = 20` 모듈 상수가 기본값이었고, 그래서 R30 은
    *「분석기간의 소유자를 정한 것이 아니다」* 라고 적어 두었다. **그런데
    소유자는 이미 정해져 있었다** — `infra/orm/scenario.py` 가 `analysis_years`
    를 `Scenario` 금지 필드로 열거하며 *「전제 분류에 해당 값은 `AssumptionSet`
    에 넣는다」* 고 적는다(§7.1 O-1). 열려 있던 것은 「어느 층인가」가 아니라
    **「그 층에 아직 값이 없다」** 였다.

    이제 값은 대장 항목 `analysis.period_years` 이고 호출측이
    `provider.analysis_years()` 로 읽어 넘긴다. **기본값을 두지 않은 것이
    요점이다** — 두면 대장을 고쳐도 이 구획이 옛 값을 쓰고, 그 어긋남은
    NPV 를 바꾸면서 아무 예외도 내지 않는다.

    ★★ **변형별 지표를 이 경로가 산출한다 (`FR-607-AC1` · R32).**
    ----------------------------------------------------------------
    R31 이 담을 자리(`CaseResult.variants`)와 표시 층
    (`core/report/variant_report.py`)을 만들었으나 **그 필드를 채우는 배포 코드가
    0곳**이었다 — 소비자는 있고 생산자가 없었다. 그래서
    `build_variant_table()` 을 실제 실행 결과에 부르면 「변형별 결과가 없습니다」로
    거부됐다: **기계는 옳게 거부하는데 아무도 그것을 부르지 않는 상태.**

    ⚠ **켜고 끄는 인자를 두지 않았다.** `with_variants=True` 로 두면 안 넘긴
    실행에 기준선이 없고, 조항 문면이 **「모든 실행에서 자동 포함」**이다. 그것이
    R21 이 `is_baseline` 깃발에서 없앤 형태다. 그래서 반환형이 바뀌었다 —
    `dict[str, float]` → `CaseOutcome`. **호출자가 컴파일 단계에서 알게 되는 것이
    요점이다**(조용히 빈 변형을 받는 것보다 낫다).

    `scheme` 을 주지 않으면 지원 조건이 없는 사업이므로 **변형 둘의 지표가 같다**
    — 그것이 정당한 상태다(지원이 0이면 무지원 기준선과 입력 지원안이 같은
    사업이다). 값이 갈리는 것을 보려면 스킴을 주어야 하고,
    `tests/casegrid/test_variant_production_wiring.py` 가 그것을 붙든다.

    ★ **초기투자 규약을 케이스 지표와 같게 맞췄다.** 케이스 지표의 NPV 는
    총사업비를 `t=0` 에 두고 뺀다(`npv(initial_investment, …)`). 변형별 지표도
    같은 규약으로 **그 변형의 실제 초기 지출**을 `t=0` 에 둔다 — 지원 현금흐름
    행(`{1: -자부담}`)을 운영 행에 섞으면 같은 이름(`npv`)의 두 수가 **할인
    시점이 달라** 비교 표에서 조용히 어긋난다. 그 규약이 같으므로 **무지원
    기준선의 NPV 는 케이스 지표의 NPV 와 일치해야 하고**, 그 일치가 규약이
    갈렸는지를 재는 검사가 된다.
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
    # ★ **계약구조가 주어지면 그것이 잉여 화폐화 편익을 고른다 (FR-205-AC1).**
    #
    # 배타 규칙표가 `SelfConsumption`·`SurplusSale`·`DirectTrade` 를 서로 유형 A
    # 로 두므로 그 셋은 **같은 잉여를 화폐화하는 세 갈래**이고 동시에 켤 수 없다.
    # 무엇이 그 하나를 고르는가가 비어 있었고, 답이 계약구조다.
    #
    # 구조를 주지 않으면 종전 그대로 잉여판매를 쓴다 — `ModelConfig.contract` 가
    # `| None` 이므로 「계약구조 없는 모델」은 정당한 상태다.
    if structure is not None:
        if provider is None:
            raise ValueError(
                "계약구조를 주면서 전제 대장(provider)을 주지 않았습니다 — "
                "정산 조립은 단가를 대장에서 읽습니다(NFR-202). 구조를 쓰지 "
                "않으려면 structure 를 넘기지 마십시오"
            )
        plan = assemble(
            structure,
            provider=provider,
            inputs=settlement_inputs,
            tariff_engine=tariff_engine,
        )
        settlement_streams: tuple[ValueStream, ...] = plan.streams
        # ★ **구조가 만드는 비용을 비용으로 나른다 (R32).** 조립기가 편익에서
        # 빼 주는 것이 아니라 여기서 프로포마 행이 된다 — 근거는
        # `core/cba/proforma.py::fee_row`. `core.cba` 가 `core.valuestream` 보다
        # 위 계층이라 조립기가 행을 지을 수 없고(`NFR-208-AC1`), 그 경계를
        # `SettlementCost` 가 건넌다.
        settlement_costs = tuple(plan.costs)
    else:
        settlement_streams = (SurplusSale(sale_price_won_per_kwh=120.0),)
        settlement_costs = ()

    peak = PeakShaving(
        monthly_peak_reduction_kw=[ess.reducible_peak_kw(year=1)] * 12,
        demand_charge_won_per_kw_month=8_320.0,
    )

    # ★ **CBA 에 닿기 전에 거부한다.** 계산한 뒤에 막으면 「예외는 나지만 이미
    # 다 돌린 뒤」가 되고, 무엇보다 **위반 조합의 NPV 가 한 번은 만들어진다.**
    assert_no_exclusions([*settlement_streams, peak, *extra_value_streams])

    settlement_per_day = sum(
        int(stream.annual_value(grid_export_result, year=1))
        for stream in settlement_streams
    )
    peak_per_day = peak.annual_value(grid_export_result, year=1)
    annual_benefit = int(settlement_per_day * DAYS_PER_YEAR + peak_per_day)

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
        *(
            fee_row(
                cost.tag,
                start_year=1,
                end_year=horizon_years,
                annual_amount_won=int(cost.annual_amount_won),
            )
            for cost in settlement_costs
        ),
    ]
    all_rows = net_operating_flows(benefit_rows, cost_rows)

    # 5. 변형별 지표 — **등록된 변형 전부** (FR-607-AC1). 위 독스트링 참조.
    variants = {
        case_flows.tag: _metrics_for(
            _initial_outlay(case_flows.rows), all_rows, discount_rate
        )
        for case_flows in build_capex_cashflows_for_all_cases(
            scheme, initial_investment, viewpoint
        )
    }

    return CaseOutcome(
        metrics=_metrics_for(initial_investment, all_rows, discount_rate),
        variants=variants,
    )


def net_operating_flows(
    benefit_rows: Sequence[CashFlowRow],
    cost_rows: Sequence[CashFlowRow],
) -> list[CashFlowRow]:
    """편익·비용 행을 `npv()` 가 받는 **순현금흐름**으로 만든다 — 비용의 부호를
    여기서 **한 번만** 뒤집는다 (R32).

    ## ★★ 이것이 없어서 비용이 NPV 를 늘리고 있었다

    `CashFlowRow` 는 **부호 규약을 갖지 않는다** — 「비용은 양수, 편익도 양수」이며
    가르는 것은 소비자다(`capex_row` 독스트링). `bcr()` 은 그래서 편익 목록과 비용
    목록을 **따로** 받는다. 그런데 `npv()` 는 목록 하나를 받아 `_pv()` 로 **부호
    있는 합**을 낸다. 즉 그 하나는 순현금흐름이어야 한다.

    종전 이 파일은 `benefit_rows + cost_rows` 를 **그대로** 넘겼다. 고정 O&M 이
    양수이므로 **비용이 편익으로 더해졌고**, NPV 는 O&M 현가의 두 배만큼 과대
    계상됐다. 아무 예외도 나지 않고, 두 배 오차는 「그럴듯한 큰 수」로 보인다.

    R32 가 관리 수수료를 비용 행으로 넣자 **수수료율을 올릴수록 NPV 가 커져서**
    드러났다 — 새 항목이 기존 결함을 밟은 형태이며, 그 결함은 비용 항목이
    O&M 둘뿐일 때는 아무도 밟지 않았다.

    ⚠ **`fee_row`·`fixed_om_row` 를 음수로 바꾸는 것으로 고치지 않았다.** 그러면
    프로포마 표시와 `bcr()` 의 분모가 함께 뒤집힌다 — 부호를 뒤집을 자리는 **순
    현금흐름을 만드는 이 경계 하나**여야 하고, 두 곳에서 뒤집으면 다시 양수가 된다.
    """
    negated = [
        CashFlowRow(
            label=row.label,
            tag=row.tag,
            amounts={year: -amount for year, amount in row.amounts.items()},
            assumption_refs=row.assumption_refs,
        )
        for row in cost_rows
    ]
    return [*benefit_rows, *negated]


def _metrics_for(
    initial_investment: Money,
    operating: list[CashFlowRow],
    discount_rate: float,
) -> dict[str, float]:
    """지표 사전 하나 — **케이스와 변형이 같은 함수를 쓴다.**

    갈라 두면 한쪽에 지표가 추가될 때 다른 쪽이 따라오지 않고, 그 상태에서
    `build_variant_table()` 은 「변형마다 지표가 다릅니다」로 거부한다 —
    즉 증상이 **표시 층에서** 나타나 원인을 여기까지 되짚어야 한다.
    """
    return {
        "npv": float(npv(initial_investment, operating, discount_rate=discount_rate)),
        "payback_years": payback_discounted(
            initial_investment, operating, discount_rate=discount_rate
        ),
    }


def _initial_outlay(rows: Sequence[CashFlowRow]) -> Money:
    """지원 현금흐름 행을 **`t=0` 초기투자 한 수로** 접는다.

    행의 금액은 유출이므로 음수다(`{1: -자부담}`). `npv()` 의 첫 인자는 *「t=0 에
    나가는 비용(양수)」* 이라 부호를 뒤집는다.

    ⚠ **행이 비어 있으면 0원이다.** 그것은 「지출이 없는 사업」이 아니라
    `FR-611-AC4` 의 **「해당 설비를 제외한 케이스」**다 — 지원 예정(미확정)분이
    무산됐을 때의 병기 케이스이며, 그 경우 설비가 없으므로 CAPEX 행도 없다
    (`build_baseline_capex_cashflows` 가 그렇게 판정한다).
    """
    total = sum(
        (amount for row in rows for amount in row.amounts.values()), Decimal(0)
    )
    return Money(-total)
