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
from dataclasses import replace
from decimal import Decimal

from core.casegrid.incentive_cases import (
    Viewpoint,
    build_capex_cashflows_for_all_cases,
)
from core.casegrid.models import (
    BenefitLine,
    CaseBasis,
    CaseOutcome,
    CostLine,
    ResourceLine,
)
from core.casegrid.profiles import DailyShapes
from core.cba.metrics import npv, payback_discounted
from core.cba.proforma import (
    benefit_row,
    check_analysis_period,
    energy_purchase_row,
    fee_row,
    fixed_om_row,
)
from core.contracts.assumptions import AssumptionProvider
from core.contracts.der import DER, DispatchContext, DispatchResult
from core.contracts.schemas import CashFlowRow
from core.contracts.units import Money, Year
from core.contracts.valuestream import ValueStream
from core.der.ess import ESS, ESSOperatingMode
from core.der.load import Load
from core.der.pv import PV, OperatingMode
from core.engine.rule_based import RuleBasedEngine
from core.incentive.schemas import IncentiveScheme
from core.regulation.tariff import TariffEngine
from core.valuestream import PeakShaving, SurplusSale
from core.valuestream.exclusion_table import assert_no_exclusions
from core.valuestream.settlement import SettlementCost, SettlementInputs, assemble

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
MONTHS_PER_YEAR = 12
#: 대표일을 되풀이해 한 해를 덮는 스텝 수. `LEAP_YEAR_POLICY` 가 평년 고정을
#: 선언하며(`DV-4`) 자원들이 8,760 을 요구한다.
HOURS_PER_YEAR = DAYS_PER_YEAR * STEPS_PER_DAY

# ── 평가 대상 모델의 제원 ────────────────────────────────────────────────
#
# ★ **여기 있었던 값들은 `PV(...)`·`ESS(...)` 호출 안의 리터럴이었다 (R33).**
#
# 리포트가 *「무엇을 평가했는가」* 를 말하려면 이 수들이 필요한데, 자원 객체는
# 생성자 인자를 전부 다시 내놓지 않는다(`ESS.rte_pct` 같은 접근자가 없다).
# 그렇다고 리포트 쪽에 같은 수를 적으면 **사본**이 되고, 제원을 고칠 때 리포트는
# 옛 수를 그럴듯하게 계속 인쇄한다 — 아무 예외도 나지 않는다.
#
# 그래서 이름을 붙여 위로 올렸다. 생성자와 리포트가 **같은 이름 하나**를 읽는다.
#
# ⚠ 금액이 아니라 **설비 제원**이다. 단가·할인율은 대장에서 오며(`NFR-202`)
# 여기 없다 — `level_map` 인자가 그 자리다.
# ⚠ **용량은 여기 없다** — `pv_capacity_kw`·`ess_capacity_kwh` 는 **설계 변수**로
# `core/casegrid/ledger_levels.py::_DESIGN_VARS` 가 소유하며 `level_map` 으로
# 들어온다. 상수로 두는 동안 용량은 **어느 케이스 축에도 없었고**, 그래서 27
# 케이스를 다 돌려도 3kW·10kWh 한 값이었다 — 리포트가 *「이 용량이 맞는가」*
# 를 묻지도 답하지도 못한 이유다. 기본값을 여기 남기지 않는 것이 요점이다:
# 남기면 수준표를 고쳐도 러너가 옛 용량을 쓰고 **NPV 만 조용히 달라진다**.
PV_CAPACITY_FACTOR = 0.15
PV_FIXED_OM_WON_PER_YEAR = 100_000
#: **PV 의 물가 계수 — 이름을 `PV_OM_ESCALATION` 에서 바꿨다(R38-D2).** 옛 이름은
#: 「O&M 전용」이라 주장했지만 실제로는 그러지 않는다. `PV` 는 `escalation_rate`
#: 슬롯을 하나만 가지므로(계약 층 설계 — 비용 항목별로 나뉘어 있지 않다), 이 값
#: 하나가 아래 **세 자리**를 함께 굴린다:
#:   ⓐ `pv.py:499` 고정 O&M · `pv.py:531` 변동 O&M · `pv.py:563` 교체비(인버터·본체) capex
#: **`ESS` 는 이 값을 받지 않는다** — 아래 `ESS(...)` 호출에 `escalation_rate` 인자가
#: 없어 기본값 `0.0` 으로 서고, 그래서 ESS 의 18년차 배터리 교체비는 **오늘의
#: 원**으로 적힌다. 대장은 `price_basis: "명목"` 을 한 번 선언하는데(`DV-7`) 그
#: 선언은 자원마다 값을 넣으라는 뜻이지, 넣지 않아도 된다는 뜻이 아니다. 이
#: 어긋남은 `tests/contract/test_escalation_debt.py::KNOWN_ESCALATION_DEBT` 가
#: 부채로 고정해 붙든다 — **이 값을 여기서 조용히 「고치지」 말 것.** 배선 판단은
#: 오케스트레이터가 내리고(§1) 등재는 별도 절차를 거친다.
#: **또한 이 계수는 「설비단가의 실질(물가 제외) 추세」를 0 으로 두는 가정을 겸한다**
#: — 교체비에 학습곡선 등으로 인한 실질 하락이 있다면 별도 대장 항목이 있어야
#: 하는데 지금 그 항목이 없다(`Q-` 신설 검토 대상, `result_escalation_debt.md` §6).
PV_ESCALATION_RATE = 0.02
PV_SELF_CONSUMPTION_RATIO = 0.0

#: ESS **정격출력**(kW). 용량과 달리 설계 변수로 올리지 않았다 — 이 값이
#: `reducible_peak_kw = min(power_kw, 가용량/방전창)` 의 **상한**이라, 고정해
#: 두어야 용량 스윕이 *「용량을 키우면 어디서 출력에 막히는가」* 를 드러낸다.
ESS_POWER_KW = 5.0
ESS_RTE_PCT = 90.0
ESS_SOC_MIN_PCT = 10.0
ESS_SOC_MAX_PCT = 90.0
ESS_CYCLE_LIFE = 6_000
ESS_CALENDAR_LIFE = 20
ESS_EOL_SOH_PCT = 80.0
ESS_CYCLES_PER_YEAR = 365.0
ESS_FIXED_OM_WON_PER_YEAR = 100_000

#: 첨두 기본요금 단가. **요금표 값이며 대장으로 옮겨야 한다** — `Q-6`(고압 단일
#: 계약 평균단가) 회신 뒤 `tariff.*` 항목에서 읽는 것이 맞다. 지금 여기 있는
#: 것은 부채이며 리포트가 출처를 「소스 상수」로 표시해 그 사실을 드러낸다.
DEMAND_CHARGE_WON_PER_KW_MONTH = 8_320.0


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


def _household_load_if_total_given(
    daily_shapes: DailyShapes | None, annual_load_kwh: float | None
) -> Load | None:
    """가구 부하 자원 — **부하 총량(`annual_load_kwh`)이 왔을 때만** 세운다.

    ## 왜 함수 이름이 조건을 말하는가 (R37)

    종전에는 「형상과 총량이 함께 와야 한다」였고, 형상만 오면 **오류로 막았다**.
    그 막음이 잡으려던 실수는 *「부하를 넣을 생각이었는데 총량을 잊었다」* 다.

    R37 이 일사 곡선을 기본 경로에 배선하면서 `daily_shapes` 는 **발전 형상의
    자산이 되었다** — 이제 형상은 모든 실행에 온다. 그러므로 *형상이 왔다* 를
    *부하를 원한다* 로 읽을 수 없다. 부하를 원한다는 뜻은 **총량만이** 말한다.

    ⚠ **그래서 조건을 그냥 풀지 않고 이름으로 갈랐다.** 조건만 완화하면 옛
    실수(총량을 잊었다)가 조용히 통과하고 호출부는 그것을 알 수 없다. 이름이
    `…_if_total_given` 이면 호출 자리에서 *「총량을 주지 않으면 부하가 서지
    않는다」* 가 읽히므로, 통과가 조용하지 않다. 반대 방향의 실수는 **여전히
    오류다** — 총량은 왔는데 형상이 없으면 부하가 하루 안에서 균등 배분되어
    지금 PV 가 겪던 것과 같은 형태가 되고(붙임 8 「일중 발전 프로파일」),
    *「부하를 반영했다」* 는 진술이 성립하는데 **그 부하는 실제로 아무 시간대도
    갖지 않는다.**

    ⚠ **부하는 편익을 만들지 않는다** (`RC-LD-B0`). `Load.value_streams()` 가
    비어 있는 것이 정답이며, 부하가 만드는 절감은 그 절감을 일으킨 자원의
    편익이다 — 부하에도 붙이면 같은 화폐 흐름이 두 번 계상된다
    (`FR-402-AC2.C`). 그래서 이 자원을 더해도 편익 갈래는 늘지 않고 **운전만**
    달라진다.
    """
    if annual_load_kwh is None:
        return None
    if daily_shapes is None:
        raise ValueError(
            "연간 부하(annual_load_kwh)를 주면 대표일 형상(daily_shapes)도 "
            "함께 주어야 합니다 — 총량만 주면 부하가 시간대를 갖지 못한 채 "
            "「반영했다」가 성립합니다"
        )
    return Load(
        name="e2e-load",
        hourly_kwh=daily_shapes.load.spread(annual_load_kwh, days=DAYS_PER_YEAR),
    )


def run_single_case_e2e(
    case_values: dict[str, object],
    *,
    level_map: Mapping[str, Mapping[str, float]],
    extra_value_streams: Sequence[ValueStream] = (),
    horizon_years: int,
    structure: str | None = None,
    provider: AssumptionProvider | None = None,
    daily_shapes: DailyShapes | None = None,
    annual_load_kwh: float | None = None,
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
    pv_capacity_kw = _resolve(
        case_values.get("pv_capacity_kw", "base"), "pv_capacity_kw", level_map
    )
    ess_capacity_kwh = _resolve(
        case_values.get("ess_capacity_kwh", "base"), "ess_capacity_kwh", level_map
    )
    # ★ **계통에서 산 전력의 한계단가** (`tariff.hv_single_contract.energy_only`).
    # 기본값을 두지 않는다 — 두면 수준표에서 이 변수를 빼도 러너가 옛 단가로
    # 계속 계산하고, 그 어긋남은 NPV 를 바꾸면서 아무 예외도 내지 않는다
    # (`horizon_years` 에서 R31 이 내린 것과 같은 판단).
    grid_purchase_price = _resolve(
        case_values.get("grid_purchase_price", "base"),
        "grid_purchase_price",
        level_map,
    )
    # ★ **잉여를 파는 단가** (`tariff.surplus_direct_sale` · R35). 종전에는 아래
    # `SurplusSale(...)` 호출 안의 리터럴 120.0 이었고, 그것이 구매 단가의
    # 기준값과 **우연히 같았다** — 근거와 파급은 `ledger_levels.py::_LEDGER_VARS`
    # 의 그 줄에 있다. 기본값을 두지 않는 이유는 구매 단가와 같다.
    surplus_sale_price = _resolve(
        case_values.get("surplus_sale_price", "base"),
        "surplus_sale_price",
        level_map,
    )

    # 1. Resources
    # ★ **형상이 오면 이용률 대신 시계열을 준다** (둘 다 주면 자원이 거부한다).
    # 연간 발전량은 **그대로**이며 시간대만 옮겨간다 — 형상은 배분이지 값이
    # 아니다.
    #
    # ✔ **R37 에 리포트가 이 통로를 쓴다.** 종전에는 통로가 열려 있는데 배포
    # 경로가 쓰지 않아 결론이 평탄 발전 위에 서 있었고(붙임 8 「일중 발전
    # 프로파일」), 붙임 7 만 곡선을 그렸다. 이제 `build_case_report` 가 본
    # 실행과 스윕에 형상을 넘긴다 — 그 배선은 `tests/report/
    # test_irradiance_wired.py` 가 진입점에서 붙든다.
    #
    # ⚠ **인자를 필수로 만들지 않았다.** 러너는 케이스 그리드·성능 측정도
    # 도는 범용 진입점이고, 형상 없는 실행은 정당한 상태다(그때 이용률 하나로
    # 균등 배분한다는 것을 이 자리가 말한다). 결론을 내는 배포 경로가 하나뿐
    # 이므로 배선은 거기서 붙드는 것이 맞다.
    generation_profile = (
        daily_shapes.generation.spread(
            pv_capacity_kw * PV_CAPACITY_FACTOR * HOURS_PER_YEAR,
            days=DAYS_PER_YEAR,
        )
        if daily_shapes is not None
        else None
    )
    pv = PV(
        name="e2e-pv",
        capacity_kw=pv_capacity_kw,
        capacity_factor=None if daily_shapes is not None else PV_CAPACITY_FACTOR,
        generation_profile_kwh=generation_profile,
        unit_capex_won_per_kw=pv_capex,
        fixed_om_won_per_year=PV_FIXED_OM_WON_PER_YEAR,
        escalation_rate=PV_ESCALATION_RATE,
        self_consumption_ratio=PV_SELF_CONSUMPTION_RATIO,
        operating_mode=OperatingMode.FULL_EXPORT,
    )
    ess = ESS(
        name="e2e-ess",
        capacity_kwh=ess_capacity_kwh,
        power_kw=ESS_POWER_KW,
        rte_pct=ESS_RTE_PCT,
        soc_min_pct=ESS_SOC_MIN_PCT,
        soc_max_pct=ESS_SOC_MAX_PCT,
        cycle_life=ESS_CYCLE_LIFE,
        calendar_life=ESS_CALENDAR_LIFE,
        eol_soh_pct=ESS_EOL_SOH_PCT,
        cycles_per_year=ESS_CYCLES_PER_YEAR,
        operating_mode=ESSOperatingMode.PEAK_SHAVING,
        capex_unit_won_per_kwh=ess_capex,
        fixed_om_won_per_year=ESS_FIXED_OM_WON_PER_YEAR,
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
    engine = RuleBasedEngine()
    # ★ **부하는 편익을 만들지 않는다** (`RC-LD-B0` · `Load.value_streams()` 는
    # 비어 있다). 그래서 여기 더해도 편익 갈래는 늘지 않고 **운전만** 달라진다 —
    # 계통 수전이 실제 수량으로 나온다. 화폐화(자가소비 절감·구매 비용)는 요금
    # 엔진의 몫이며, 한쪽만 계상하면 사업에 불리한 쪽으로 틀린다(NSPM 대칭성).
    household = _household_load_if_total_given(daily_shapes, annual_load_kwh)
    resources: list[DER] = [pv, ess] if household is None else [pv, ess, household]
    dispatch = engine.run(resources, ctx)

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
    # `| None` 이므로 「계약구조 없는 모델」은 정당한 상태다. 그 갈래의 단가는
    # **수준표에서 온다**(R35) — 리터럴이던 동안 그것은 어느 케이스 축에도 없어
    # 영향도 표에 오르지 못했고, 구매 단가와 우연히 같은 값이었다.
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
            # ★★ **발전량은 모형이 계산한다 — 사용자 입력이 아니다** (R34).
            # 아래 `_with_model_generation` 독스트링에 판정 근거가 있다.
            inputs=_with_model_generation(settlement_inputs, pv),
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
        settlement_streams = (
            SurplusSale(sale_price_won_per_kwh=surplus_sale_price),
        )
        settlement_costs = ()

    peak_reduction_kw = ess.reducible_peak_kw(year=1)
    peak = PeakShaving(
        monthly_peak_reduction_kw=[peak_reduction_kw] * MONTHS_PER_YEAR,
        demand_charge_won_per_kw_month=DEMAND_CHARGE_WON_PER_KW_MONTH,
    )

    # ★ **CBA 에 닿기 전에 거부한다.** 계산한 뒤에 막으면 「예외는 나지만 이미
    # 다 돌린 뒤」가 되고, 무엇보다 **위반 조합의 NPV 가 한 번은 만들어진다.**
    assert_no_exclusions([*settlement_streams, peak, *extra_value_streams])

    # ★★★ **연간화를 편익이 선언한 대로 한다 (R34).**
    #
    # 종전 이 자리는 *정산 편익 전건에 365를 곱하고 첨두 절감에는 곱하지
    # 않는다* 는 **암묵 규약**이었다. 그 규약은 잉여판매·상계 두 갈래에서만
    # 맞았고, 생성자에서 **연간** 수량을 받는 편익(「분산특구 직접거래」의
    # 거래량 · 「집합 PPA」의 전량 발전량)에서는 **365배**를 만들었다 — 실측:
    # 집합 PPA 502,605원/년이 183,450,825원으로 실렸다. 금액이 그럴듯하지
    # 않을 만큼 컸는데도 **케이스 그리드가 그 구조를 돌지 않아** 아무도 보지
    # 못했고, 「구조를 넣으면 NPV 가 달라진다」만 보는 배선 검사는 초록불이었다.
    #
    # 이제 곱할지 말지는 **편익이 선언한다**(`scales_with_dispatch_window`).
    # 여기에 태그 목록을 두지 않은 이유는 그 목록이 편익이 늘 때 낡기 때문이다.
    annualised: list[tuple[ValueStream, int]] = []
    for stream in (*settlement_streams, peak):
        value = float(stream.annual_value(grid_export_result, year=1))
        if type(stream).scales_with_dispatch_window:
            value *= DAYS_PER_YEAR
        annualised.append((stream, int(value)))
    settlement_by_stream = annualised[:-1]
    peak_per_year = annualised[-1][1]
    annual_benefit = sum(value for _, value in annualised)

    # 4. Proforma → NPV
    #
    # ★★★ **계통에서 산 전력의 값** (R34 · `energy_purchase_row` 독스트링).
    #
    # 수량은 처음부터 여기 있었다 — `dispatch.grid_import` 다. 빠져 있던 것은
    # 단가와 그것을 곱해 **비용 행으로 만드는 이 세 줄**이었고, 그 동안
    # 저장장치는 심야에 받아 온 전력을 값 없이 썼다.
    #
    # ⚠ **행을 조건부로 만들지 않는다** — 수전이 0이어도 0원 행을 싣는다.
    # 「수전이 없어서 0원」과 「행이 없어서 0원」은 프로포마에서 똑같이 보이는데
    # 뜻이 정반대다(하나는 측정, 하나는 누락). 붙임 8 의 판정 조건도 그래서
    # **「수전이 있는데 비용 행이 없는가」**여야 한다(`unreflected` 독스트링).
    daily_grid_import_kwh = sum(dispatch.grid_import)
    annual_grid_import_kwh = daily_grid_import_kwh * DAYS_PER_YEAR
    annual_purchase_won = int(annual_grid_import_kwh * grid_purchase_price)

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
            escalation_rate=PV_ESCALATION_RATE,
        ),
        fixed_om_row(
            "ESSFixedOM",
            start_year=1,
            end_year=horizon_years,
            annual_amount_won=int(ess.fixed_om(year=1)),
        ),
        energy_purchase_row(
            "GridPurchase",
            start_year=1,
            end_year=horizon_years,
            annual_amount_won=annual_purchase_won,
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

    # 6. 산식의 대입값 — **리포트가 「왜 이 값인가」에 답하는 재료**
    # (`FR-1001-AC3` · `CaseBasis` 독스트링). 여기서 담지 않으면 리포트가
    # 지표를 다시 계산하거나 자원 구성을 사본으로 갖게 된다.
    annual_cost = sum(
        int(row.amounts.get(1, 0)) for row in cost_rows
    )
    benefit_lines = _benefit_lines(
        settlement_by_stream,
        peak=peak,
        peak_per_year=peak_per_year,
        # ★ 연간화에 쓴 **그 창**을 넘긴다 — 산식의 수량은 금액이 나온 창에서
        # 읽어야 한다. 다른 창을 넘기면 산식과 금액이 갈리고, 그 어긋남은
        # 곱해서 나온 합계만 보면 드러나지 않는다.
        dispatch=grid_export_result,
    )

    return CaseOutcome(
        metrics=_metrics_for(initial_investment, all_rows, discount_rate),
        variants=variants,
        # ★ 자원과 운전 결과를 **그대로** 넘긴다 — 리포트가 엔진 규칙과
        # 시간대별 운전을 물을 대상이다(`CaseOutcome` 독스트링). 여기서 요약해
        # 넘기면 무엇을 요약할지가 러너의 판단이 되고, 리포트가 다른 것을
        # 물을 때마다 이 파일이 함께 바뀐다.
        resources=(pv, ess),
        dispatch=dispatch,
        # 엔진 인스턴스가 실제로 쓴 순서다 — 기본 상수를 다시 읽지 않는다
        # (`CaseOutcome.rule_order` 독스트링).
        rule_order=engine.rule_order,
        basis=CaseBasis(
            initial_investment_won=int(initial_investment),
            annual_benefit_won=annual_benefit,
            annual_cost_won=annual_cost,
            discount_rate=discount_rate,
            horizon_years=horizon_years,
            grid_purchase_price_won_per_kwh=grid_purchase_price,
            resources=_resource_lines(pv, pv_capex, ess, ess_capex, benefit_lines),
            benefits=benefit_lines,
            costs=_cost_lines(
                pv_fixed_om=int(pv.fixed_om(year=1)),
                ess_fixed_om=int(ess.fixed_om(year=1)),
                daily_grid_import_kwh=daily_grid_import_kwh,
                grid_purchase_price=grid_purchase_price,
                annual_purchase_won=annual_purchase_won,
                settlement_costs=settlement_costs,
            ),
            dispatch_note=(
                f"대표일 1일을 {STEPS_PER_DAY}스텝(1시간 간격)으로 모의하고 "
                f"{DAYS_PER_YEAR}일로 연간화한다. 계절·요일 변동을 반영하지 "
                "않으므로 잉여 판매량은 대표일의 {DAYS_PER_YEAR}배다. "
                "첨두 절감은 월 단위 12회로 이미 연간값이라 곱하지 않는다"
            ).replace("{DAYS_PER_YEAR}", str(DAYS_PER_YEAR)),
        ),
    )


def _with_model_generation(
    inputs: SettlementInputs | None, pv: PV
) -> SettlementInputs:
    """연간 **전량** 발전량을 모형에서 채워 조립기에 넘긴다 — `FR-401-AC2.AggregatedPPA`.

    ## 왜 이 통로가 비어 있었나 (R32 → R34)

    R32 가 「집합 PPA」 편익 클래스와 조항을 세웠지만 **케이스 그리드에서 그
    구조를 돌릴 수는 없었다** — 조립기가 발전량을 `SettlementInputs` 로만 받고
    러너에는 그것을 채우는 자리가 없었다. 조립 층까지만 닫힌 상태였다.

    ## 왜 사용자 입력이 아닌가 — **모형이 이미 그 수를 계산한다**

    `SettlementInputs` 는 *「당사자가 협상해서 정하는 값」* 을 담는 자료형이다
    (그 독스트링이 기준을 적어 두었다). 계약단가·거래량은 협상의 결과지만
    **발전량은 설비와 일사가 정하는 물리량**이며 협상 대상이 아니다. 사용자
    입력으로 두면 모형이 계산하는 수의 **둘째 출처**가 생기고, 두 값이 갈릴 때
    아무 예외도 나지 않는다 — 이 저장소가 반복해서 잡아 온 형태다.

    ## 어디서 읽는가 — **자원에게 묻는다**

    `PV.annual_generation_kwh()` 가 이미 있다. 러너가 `capacity × 이용률 × 8,760`
    을 다시 곱하지 않는 이유는 그것이 자원 안의 산식과 **사본 관계**가 되기
    때문이다(열화·형상 반영이 자원 쪽에만 들어오면 여기가 조용히 옛 값을 낸다).

    ⚠ **디스패치 결과에서 뽑지 않는다.** `DispatchResult.electric` 은 순 계통
    흐름이라 자가소비분이 이미 상계돼 있고, 「양수 합」을 쓰면 그것은 잉여여서
    이 편익이 `SurplusSale` 의 사본이 된다(`aggregated_ppa.py` 독스트링).

    ⚠ **1년차 발전량이다.** 편익 시계열 전체가 1년차 기준으로 세워지는 이
    파이프라인의 규약을 따른다 — 연도별 열화를 이 편익만 반영하면 갈래마다
    다른 규약이 생긴다. 연도별로 가려면 `AggregatedPPA` 가 스칼라 대신 시계열을
    받아야 하고 그것은 편익 전건이 함께 움직일 때 할 일이다.
    """
    generation = pv.annual_generation_kwh(year=1)
    if inputs is None:
        return SettlementInputs(annual_generation_kwh=generation)
    if inputs.annual_generation_kwh is not None:
        raise ValueError(
            "연간 발전량(annual_generation_kwh)을 사용자 입력으로 주었습니다 — "
            "이 값은 모형이 자원 제원에서 계산하므로 둘 중 어느 것이 정본인지 "
            f"정할 수 없습니다(모형 계산값 {generation:,.0f}kWh · 입력값 "
            f"{inputs.annual_generation_kwh:,.0f}kWh). 협상값이 아닌 물리량이므로 "
            "빼고 넘기십시오"
        )
    return replace(inputs, annual_generation_kwh=generation)


def _cost_lines(
    *,
    pv_fixed_om: int,
    ess_fixed_om: int,
    daily_grid_import_kwh: float,
    grid_purchase_price: float,
    annual_purchase_won: int,
    settlement_costs: Sequence[SettlementCost],
) -> tuple[CostLine, ...]:
    """운영비를 **항목별로** 갈라 담는다 (`CostLine` 독스트링 참조).

    ⚠ **연간화 규약이 항목마다 다르다** — 편익 쪽과 같은 함정이다. 고정 O&M 은
    이미 연간액이고, 전력 구매는 **대표일 수량**에 365를 곱해야 한다. 산식
    문면에 그 곱을 그대로 적는다: 수량과 단가 중 어느 쪽이 틀렸는지 검토자가
    가릴 수 있어야 하고, 둘은 서로 다른 사람이 고친다(단가는 대장, 수량은 운전).
    """
    lines = [
        CostLine(
            tag="PVFixedOM",
            label="태양광 고정 운영비",
            annual_won=pv_fixed_om,
            from_resource="PV",
            formula=f"연 {pv_fixed_om:,}원 (1년차 · 연 2% 상승)",
        ),
        CostLine(
            tag="ESSFixedOM",
            label="저장장치 고정 운영비",
            annual_won=ess_fixed_om,
            from_resource="ESS",
            formula=f"연 {ess_fixed_om:,}원",
        ),
        CostLine(
            tag="GridPurchase",
            label="계통 전력 구매",
            annual_won=annual_purchase_won,
            # ⚠ 자원 이름을 「ESS」로 적지 않는다. 수전은 **부하와 충전의 합**이
            # 발전을 넘을 때 생기므로 어느 한 자원의 것이 아니다 — 지금 구성에서
            # 충전이 대부분이라는 것은 붙임 7 이 스텝별로 보여 준다.
            from_resource="",
            formula=(
                f"대표일 수전 {daily_grid_import_kwh:,.2f}kWh × "  # noqa: RUF001
                f"{DAYS_PER_YEAR}일 × "  # noqa: RUF001
                f"{grid_purchase_price:,.0f}원/kWh "
                f"= {annual_purchase_won:,}원"
            ),
        ),
    ]
    lines.extend(
        CostLine(
            tag=cost.tag,
            label=cost.label,
            annual_won=int(cost.annual_amount_won),
            from_resource="",
            formula=f"연 {int(cost.annual_amount_won):,}원 (정산 구조가 만드는 비용)",
        )
        for cost in settlement_costs
    )
    return tuple(lines)


def _benefit_lines(
    settlement_by_stream: Sequence[tuple[ValueStream, int]],
    *,
    peak: ValueStream,
    peak_per_year: int,
    dispatch: DispatchResult,
) -> tuple[BenefitLine, ...]:
    """편익을 **갈래별로** 갈라 담는다 (`BenefitLine` 독스트링 참조).

    ⚠ **연간화 규약이 갈래마다 다르다.** 창에서 읽는 편익은 대표일 1일치라
    365를 곱하고, 생성자에서 연간 수량을 받는 편익은 곱하지 않는다. 이 차이는
    합계만 보면 보이지 않으므로 **산식 문면에 그대로 적는다** — 검토자가 곱하기
    하나를 잘못 짚으면 365배가 틀린다. 어느 쪽인지는 편익이 선언하며
    (`scales_with_dispatch_window`) 여기서 짐작하지 않는다.

    ⚠ **이름을 인스턴스에서 읽는다.** 종전에는 라벨이 `f"잉여 전력 판매 ({tag})"`
    로 박여 있었고, 그래서 「집합 PPA」·「분산특구 직접거래」가 배선되면
    **전량 판매·직접거래가 「잉여 전력 판매」로 인쇄된다**. 자원 귀속도 마찬가지다.

    ★ **첨두 절감도 같은 통로를 지난다** (R36). 종전에는 이 편익만 라벨과 산식이
    여기에 박여 있었고, 그래서 위 규칙의 예외로 남아 있었다 — 라벨은
    「첨두 수요 절감」으로 고정(인스턴스 이름은 「기본요금(피크) 절감」)이고
    산식은 러너가 지었다. 자원 귀속만 다르므로 그것만 인자로 받는다.
    """
    return tuple(
        _benefit_line(stream, annual_won, resource, dispatch)
        for stream, annual_won, resource in (
            *((s, v, "PV") for s, v in settlement_by_stream),
            (peak, int(peak_per_year), "ESS"),
        )
    )


def _benefit_line(
    stream: ValueStream, annual_won: int, resource: str, dispatch: DispatchResult
) -> BenefitLine:
    """편익 한 줄 — **산식은 편익이 내고 연간화는 여기가 붙인다**.

    ## ★★★ 왜 산식을 여기서 짓지 않는가 (R36)

    종전 이 자리는 창을 읽는 편익에 **`대표일 1,771원 × 365일`** 을 적었다.
    곱해서 나온 금액만 있고 **무엇에 얼마를 곱했는지가 없다** — 같은 리포트의
    비용 쪽은 `대표일 수전 6.19kWh × 365일 × 120원/kWh` 로 수량과 단가를 갈라
    적는데(`_cost_lines`), 편익 쪽만 그러지 못했다. 그래서 **영향도 1위 인자인
    잉여 판매단가의 값이 붙임 4 어디에도 없었다.**

    대입값을 아는 것은 그 값을 생성자에서 받은 **편익 자신**이므로 문면을
    `ValueStream.formula()` 가 낸다. 여기서 지으려면 태그별 분기를 들게 되고
    그 목록은 편익이 늘 때 낡는다 — 위 연간화와 같은 근거다.

    ⚠ **연간화와 합계는 여기가 붙인다.** 편익은 자기 대입값까지만 알고,
    *「이 창이 대표일인가」* 는 호출측의 사정이다. 두 곳이 다 적으면 갈릴 수
    있고 갈린 쪽이 365배다.
    """
    # RUF001: 「×」는 검토자가 읽는 산식 문면이다. `x` 로 바꾸면 곱셈이 변수
    # 이름처럼 보인다 — 대상을 좁히는 면제이지 규칙을 넓히는 것이 아니다.
    body = stream.formula(dispatch, year=1)
    formula = (
        f"대표일 {body} × {DAYS_PER_YEAR}일 = {annual_won:,}원"  # noqa: RUF001
        if type(stream).scales_with_dispatch_window
        else f"{body} = {annual_won:,}원 (연간 수량으로 산정 · 연간화 없음)"
    )
    return BenefitLine(
        tag=stream.tag,
        label=f"{stream.name} ({stream.tag})",
        annual_won=annual_won,
        from_resource=resource,
        formula=formula,
    )


def _resource_lines(
    pv: PV,
    pv_capex: float,
    ess: ESS,
    ess_capex: float,
    benefits: Sequence[BenefitLine],
) -> tuple[ResourceLine, ...]:
    """평가 대상 자원 제원 — 리포트 0절의 재료 (`ResourceLine` 독스트링)."""

    def produced_by(resource: str) -> tuple[str, ...]:
        return tuple(line.tag for line in benefits if line.from_resource == resource)

    return (
        ResourceLine(
            name=pv.name,
            kind="태양광 (옥상 고정형)",
            # ★ **세운 자원에서 읽는다.** 모듈 상수에서 읽으면 용량 스윕이
            # 도는 동안에도 리포트가 기준 용량을 계속 인쇄한다 — 값이 바뀌어도
            # 아무 예외가 나지 않는 형태다.
            capacity=(
                f"{pv.capacity_kw:g} kW · 이용률 {PV_CAPACITY_FACTOR:.0%} · "
                f"자가소비율 {PV_SELF_CONSUMPTION_RATIO:.0%}"
            ),
            operating_mode=str(pv.operating_mode),
            lifetime_years=int(pv.lifetime),
            unit_capex=f"{pv_capex:,.0f}원/kW",
            capex_won=int(pv.capex(year=1)),
            fixed_om_won_per_year=int(pv.fixed_om(year=1)),
            produces=produced_by("PV"),
        ),
        ResourceLine(
            name=ess.name,
            kind="에너지저장장치 (신품)",
            capacity=(
                f"{ess.capacity_kwh:g} kWh / {ess.power_kw:g} kW · "
                f"왕복효율 {ESS_RTE_PCT:g}% · SOC {ESS_SOC_MIN_PCT:g}~"
                f"{ESS_SOC_MAX_PCT:g}% · 수명종료 SOH {ESS_EOL_SOH_PCT:g}% · "
                f"연 {ESS_CYCLES_PER_YEAR:g}사이클"
            ),
            operating_mode=str(ess.operating_mode),
            lifetime_years=int(ess.lifetime),
            unit_capex=f"{ess_capex:,.0f}원/kWh",
            capex_won=int(ess.capex(year=1)),
            fixed_om_won_per_year=int(ess.fixed_om(year=1)),
            produces=produced_by("ESS"),
        ),
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

    ★ **초기지출을 함께 싣는다 (R33).** 지표가 둘뿐일 때 리포트는 *「무지원과
    입력 지원안의 NPV 가 이만큼 다르다」* 까지만 말할 수 있고 **「얼마를 덜
    냈기에 그런가」** 를 말할 수 없었다 — 변형별 초기지출이 경계를 넘지
    않았기 때문이다. `MC-1` 이 재는 것이 정확히 그 「왜」이므로 여기서 싣는다.
    지표가 아니라 대입값이지만, 변형마다 **다른** 값이고 변형별로 담을 자리는
    여기뿐이다(`CaseBasis` 는 케이스 하나에 하나다).
    """
    return {
        "npv": float(npv(initial_investment, operating, discount_rate=discount_rate)),
        "payback_years": payback_discounted(
            initial_investment, operating, discount_rate=discount_rate
        ),
        "initial_outlay_won": float(initial_investment),
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
