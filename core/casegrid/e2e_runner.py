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

from core.casegrid.attribution import attribute_benefits

# ★ **지표 조립도 이 파일 것이었다** — 코드 496/500(여유 4줄)에서 R57/WP-9 가
# `metrics_for`·`initial_outlay` 를 `case_metrics.py` 로 옮겼다. `ess_build.py`
# ·`pv_allocation.py`·`grid_support.py` 와 같은 사유다. 밑줄을 뗀 이유는 그
# 파일 머리말에 있다(모듈 밖에서 부르는 이름이다).
from core.casegrid.case_metrics import initial_outlay, metrics_for

# ★ **`ESS` 조립은 이 파일 것이었다** — `NFR-206` 코드 줄 상한(500)에 코드
# 497 로 닿아 ★분할의 러너 배선을 넣을 여유가 3줄뿐이라 제원 상수 여덟과
# `ESS(...)` 호출 전문을 `ess_build.py` 로 옮겼다(R57/WP-5). `pv_allocation.py`
# ·`grid_support.py` 와 같은 사유다. **아래 다섯은 재수출이 아니라 이 파일의
# `_resource_lines()` 가 2.1 표에 실제로 인쇄하는 이름들이다.**
#
# ★★ **몫 분기의 몸통도 그 파일에 있다**(R57/WP-6) — `build_case_ess_fleet`
# 과 `build_fleet_streams` 다. 이 파일은 **코드 여유 18줄 · `PLR0915`
# statement 여유 0** 이라 분기를 여기 둘 수 없다. 그 두 함수가 종전에 이
# 파일이 직접 부르던 `grid_support.py::_resolve_nwas_cp`·`peak_shaving_
# enabled` 를 대신 부르므로 그 import 는 여기서 사라졌다.
from core.casegrid.ess_build import (
    ESS_CYCLES_PER_YEAR,
    ESS_EOL_SOH_PCT,
    ESS_RTE_PCT,
    ESS_SOC_MAX_PCT,
    ESS_SOC_MIN_PCT,
    build_case_ess_fleet,
    build_fleet_streams,
)

# ★★★ **몫 선언을 받는 자리**(R57/WP-6). 이 import 가 서는 순간
# `tests/casegrid/test_ess_share.py` 의 ⑤ 와 `tests/casegrid/
# test_ess_share_benefits.py` 의 ⑥ — *「배포 경로가 이 모듈을 모른다」* 래칫
# 둘 — 이 **빨간불이 된다.** 그 둘은 배선하는 날 울리라고 세운 것이며
# (그 독스트링이 *「배선은 다음 자리의 몫」* 이라 적었다) 이 자리가 그날이다.
# ⚠ **이름을 다른 모듈로 우회해 문자열 검사를 피하지 않는다** — 피하면 그
# 래칫이 거짓을 참으로 인쇄한다.
from core.casegrid.ess_share import ESSShare
from core.casegrid.incentive_cases import (
    Viewpoint,
    build_capex_cashflows_for_all_cases,
)

# ★ **`_resolve` 는 이 파일 것이었다** — `NFR-206` 코드 줄 상한(500줄)에 정확히
# 닿아 이 라운드가 여는 두 축을 더할 자리가 없어 `ledger_levels.py` 로
# 옮겼다(R52/WP-6). 재수출이다 — 이 파일 안의 모든 `_resolve(...)` 호출은
# 그대로 둔다.
from core.casegrid.ledger_levels import _resolve
from core.casegrid.lifecycle import lifecycle_rows as _lifecycle_rows
from core.casegrid.models import (
    BenefitLine,
    CaseBasis,
    CaseOutcome,
    CashflowSplit,
    ResourceLine,
)
from core.casegrid.operating_lines import DAYS_PER_YEAR, net_operating_flows
from core.casegrid.operating_lines import annualise as _annualise

# 이 파일은 `_benefit_line` 을 부르지 않는다. **밖에서 이 경로로 부르므로
# 재수출한다** — `tests/casegrid/test_benefit_line_rendering.py` 가 그 이름을
# 붙든다(`lifecycle.py` 의 `_lifecycle_rows` 와 같은 재수출이다).
from core.casegrid.operating_lines import benefit_line as _benefit_line  # noqa: F401
from core.casegrid.operating_lines import benefit_lines as _benefit_lines
from core.casegrid.operating_lines import cost_lines as _cost_lines
from core.casegrid.perspectives import build_perspective_wiring, build_society_annualised
from core.casegrid.profiles import DailyShapes

# ★ **분리 이유는 `pv_allocation.py` 머리말에 있다** — `NFR-206` 코드 줄 상한에
# 걸려 `_resolve_ess_dispatch_inputs` 를 독스트링·기본값 상수째로 옮겼다(R51/WP-5).
# 재수출이다 — `core/der/ess.py`·`core/der/pv.py` 독스트링과
# `tests/casegrid/test_pv_surplus_allocation_priority.py` 가 이 이름들을
# `e2e_runner.` 경로로 가리킨다(`check_docstring_references.py` 가 재수출을 참으로
# 인정한다).
from core.casegrid.pv_allocation import (
    ESS_CHARGE_SOURCE_DEFAULT,  # noqa: F401
    ESS_OPERATING_MODE_DEFAULT,  # noqa: F401
    PV_ALLOCATION_PRIORITY_DEFAULT,  # noqa: F401
    _dispatch_inputs_under_baseline,
    _resolve_ess_dispatch_inputs,  # noqa: F401
    measured_self_consumption_ratio,
)
from core.cba.baseline import BaselineArrangement
from core.cba.proforma import (
    benefit_row,
    check_analysis_period,
    energy_purchase_row,
    fee_row,
    fixed_om_row,
)
from core.contracts.assumptions import AssumptionProvider
from core.contracts.der import DER, DispatchContext, DispatchResult
from core.contracts.engine import SystemDispatch
from core.contracts.units import Money, Year
from core.contracts.valuestream import ValueStream
from core.der.ess import ESS, ESSChargeSource, ESSOperatingMode
from core.der.load import Load
from core.der.pv import PV, OperatingMode, PVAllocationPriority
from core.engine.rule_based import RuleBasedEngine
from core.incentive.schemas import IncentiveScheme
from core.regulation.tariff import TariffEngine
from core.valuestream import REC, DistributedSubItems, SurplusSale
from core.valuestream.exclusion_table import assert_no_exclusions
from core.valuestream.settlement import SettlementInputs, assemble

#: 이 모듈이 **밖으로 내보내는 이름**. R43-F2 가 `operating_lines.py` 를
#: 갈라내면서 필요해졌다 — `DAYS_PER_YEAR` 와 `net_operating_flows` 는 이제
#: 저쪽이 선언하고 이 파일이 받아 넘기는데, mypy strict 는 import 로 들어온
#: 이름의 **암묵 재수출을 거부한다**(`no_implicit_reexport`). 넘긴다는 사실을
#: 여기에 적어야 `core/report/dispatch_sections.py:32` 의
#: `from core.casegrid.e2e_runner import DAYS_PER_YEAR` 가 성립한다.
#: ⚠ **목록을 줄이지 말 것** — 이 이름들은 밖이 이 경로로 부르고 있고
#: (`tests/report/test_shaped_run_invariants.py` 가 넷 중 셋을 함께 읽는다),
#: 줄이면 그 호출이 조용히 끊긴다.
__all__ = (
    "DAYS_PER_YEAR",
    "HOURS_PER_YEAR",
    "PV_CAPACITY_FACTOR",
    "net_operating_flows",
    "run_single_case_e2e",
)

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
MONTHS_PER_YEAR = 12
#: ⚠ **`DAYS_PER_YEAR` 는 `operating_lines.py` 가 소유한다** — 연간화 계수와
#: 그것을 쓰는 표시줄 조립을 한 파일에 둔다(R43-F2). 아래 `HOURS_PER_YEAR`
#: 와 이 파일의 나머지는 위 import 로 들어온 그 이름 하나를 읽는다.

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
#: ⚠ **고정 O&M 은 여기 없다** — `PV_FIXED_OM_WON_PER_YEAR` 모듈 상수를
#: R51/WP-2 가 지웠다. 대장 `opex.pv.fixed_om` 에서 `level_map` 으로 온다
#: (사용자 판정 §2, `docs/decisions-2026-09-01-R51.md`) — 소스에 기본값을
#: 남기면 대장 한 곳만 고쳐도 실행에 반영된다는 그 판정의 요구가 깨진다.
#: **물가 계수 — 자원의 속성이 아니라 사업 전제다.** 이름이 두 번 움직였다:
#: `PV_OM_ESCALATION`(「O&M 전용」이라 주장했지만 아니었다) → `PV_ESCALATION_RATE`
#: (R38-D2, 「PV 의 것」이라 주장했지만 그것도 아니다) → 지금 이름(R39-E).
#:
#: 대장은 `price_basis: "명목"` 을 **한 번** 선언하고(`DV-7`) 그 선언은 자원마다
#: 값을 넣으라는 뜻이다 — 그러므로 이 계수를 「PV 의 것」으로 두면 다른 자원에
#: 넘길 때마다 *「PV 의 상수를 전용한다」* 가 되고, 그 어색함이 실제로 ESS 를
#: 다섯 라운드 동안 `0.0` 으로 세워 두었다. 이름을 사업 전제로 올려 그 자리를
#: 없앤다. **값은 `0.02` 그대로이며 사본을 만들지 않았다.**
#:
#: 이 값 하나가 **네 자리**를 함께 굴린다(전수 — `Grep` 으로 이 이름을 세면
#: 선언 1 + 호출 4 다):
#:   ⓐ `PV(escalation_rate=)` → `pv.py` 고정 O&M · 변동 O&M · 교체비(인버터·본체)
#:   ⓑ `ESS(escalation_rate=)` → `ess.py` 고정 O&M · 변동 O&M · 배터리 교체비
#:   ⓒ `fixed_om_row("PVFixedOM", escalation_rate=)` — **행이 자기 물가를 직접
#:      굴린다**(`proforma.py:85-89`). 자원의 계수를 보지 않으므로 ⓐ 와 별개다
#:   ⓓ `fixed_om_row("ESSFixedOM", escalation_rate=)` — 같은 이유로 ⓑ 와 별개다
#: ⓒ 는 R38 까지 리터럴 `0.02` 였다(사본. 값이 **우연히** 같아 어긋나지 않았다)
#: 고 ⓓ 는 아예 없었다. 넷을 한 이름에 묶은 것이 R39-E 의 절반이다 — 나머지
#: 절반은 교체비·잔존가치 행 자체다(`_lifecycle_rows`).
#:
#: ⚠ **이 계수는 「설비단가의 실질(물가 제외) 추세」를 0 으로 두는 가정을 겸한다**
#: — 교체비에 학습곡선 등으로 인한 실질 하락이 있다면 별도 대장 항목이 필요하다.
#: ✔ **R41 이 그 항목을 세웠고 R42 가 스윕 축으로 배선했다**:
#: `capex.replacement_real_trend`(`Q-17` · 값 0 · 3수준 −2.0/0.0/+2.0).
#: **이 상수는 그대로이며 기준수준의 수도 그대로다** — 대장의 base 가 0 이라
#: 명목 변화율이 이 상수와 같기 때문이다. 바뀐 것은 *그 가정을 흔들어 볼 수
#: 있는가* 다: 5.1 에 5위로 서고(변동폭 712,020원) 하단 −2.0 이
#: 「물가 계수를 태우지 않았다면」, 곧 **R40 이전 결론**을 다시 잰다
#: (결손 6,289,675 → 5,984,595원 · **차이 305,080원**).
#: ⚠ **이 상수는 O&M 쪽 계수다.** 교체비가 보는 것은
#: `replacement_escalation_rate`(= 이 상수 + 실질 추세)이며 아래
#: `run_single_case_e2e` 가 만든다 — 위 ⓐ~ⓓ 중 교체비 갈래는 그쪽으로 갔다.
#: ⚠ **값 자체가 대장에 없다.** 소스 상수이며 어느 케이스 축에도 없다 — 이
#: 어긋남은 `PV_CAPACITY_FACTOR` 등과 같은 부채이고 리포트가 출처를 「소스
#: 상수」로 표시해 그 사실을 드러낸다.
PRICE_ESCALATION_RATE = 0.02
PV_SELF_CONSUMPTION_RATIO = 0.0

#: ⚠⚠ **R52/WP-6 이 대장으로 옮겼다** — 종전에는 여기 `REC_WEIGHT_PV = 1.0`
#: 모듈 상수였다. `benefit.rec_price` 가 `assume` 으로 올라온 지금 가중치는
#: 어떤 수도 바꾸지 못하던 상태를 벗어나 결론을 정하는 수가 됐다 —
#: `docs/assumptions.yaml::benefit.rec_weight_pv` 가 정본이고, 아래
#: `run_single_case_e2e` 가 `level_map` 에서 읽는다
#: (`tests/casegrid/test_rec_wiring.py::
#: test_rec_weight_moves_to_the_ledger_when_the_price_does` 래칫).

#: ⚠⚠ **ESS 제원 상수 여덟은 여기 없다** — `ESS_POWER_KW`·`ESS_RTE_PCT`·
#: `ESS_SOC_MIN_PCT`·`ESS_SOC_MAX_PCT`·`ESS_CYCLE_LIFE`·`ESS_CALENDAR_LIFE`·
#: `ESS_EOL_SOH_PCT`·`ESS_CYCLES_PER_YEAR` 를 `core/casegrid/ess_build.py` 로
#: R57/WP-5 가 `ESS(...)` 조립 전문과 함께 옮겼다(위 import). 사유는 그 모듈
#: 머리말에 있다 — 이 파일이 코드 **497/500(여유 3)** 이라 ★분할의 러너
#: 배선을 넣을 자리가 없었다. **값도 주석도 한 글자 바뀌지 않았다.**
#: ⚠ **여덟을 다 다시 내보내지 않는다**(4절 ④) — `_resource_lines()` 가 2.1
#: 표에 인쇄하는 다섯만 import 한다. `ESS_POWER_KW`·`ESS_CYCLE_LIFE`·
#: `ESS_CALENDAR_LIFE` 는 조립 함수 안에서만 쓰이므로 이 이름공간에 없다.

#: ⚠ **ESS 운전 방법·충전원·PV 배분 우선순위 기본값 셋은 여기 없다** —
#: `core/casegrid/pv_allocation.py::ESS_OPERATING_MODE_DEFAULT`·
#: `ESS_CHARGE_SOURCE_DEFAULT`·`PV_ALLOCATION_PRIORITY_DEFAULT` 를 R51/WP-5 가
#: 옮겼다(위 import). 이름은 그대로이고 이 파일이 재수출한다.


def _household_load_if_total_given(
    daily_shapes: DailyShapes | None,
    annual_load_kwh: float | None,
    extra_appliance_load_kwh: float = 0.0,
) -> Load | None:
    """가구 부하 자원 — **부하 총량(`annual_load_kwh`)이 왔을 때만** 세운다.

    `extra_appliance_load_kwh` (판정 §5·B-2)는 히트펌프 등 추가 전력사용기기의
    **연간 소비전력량**이며 총량에 더해진다 — `annual_load_kwh` 가 `None`
    이면(부하를 세우지 않는 실행) 더할 기저가 없으므로 **무시된다**.

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
        hourly_kwh=daily_shapes.load.spread(
            annual_load_kwh + extra_appliance_load_kwh, days=DAYS_PER_YEAR
        ),
        # ★ **지금 어떤 수도 움직이지 않는다** — 이 `Load` 에는 비용 인자가 하나도
        # 없어(단가·O&M·부속설비 전부 미지정) 곱할 것이 없다. 그런데도 넘기는
        # 이유는 `test_escalation_debt.py` 래칫이 R42 에 **처음으로 이 자리를
        # 보았기** 때문이다 — 그 래칫은 생성자 인자 이름에 `capex`·`replacement`
        # 가 있는지로 「미래 지출을 갖는 자원」을 가리는데, `Load` 는 그 관례를
        # 안 따르는 이름(`unit_cost_won_per_kw`)을 써서 여태 대상 밖이었다.
        # 즉 **부채가 는 것이 아니라 사각이 드러난 것**이고, 비용 인자가 들어오는
        # 날 조용히 실질 기준이 되지 않도록 지금 닫는다 (`DV-7`).
        escalation_rate=PRICE_ESCALATION_RATE,
    )


def _site_load_kw(
    household: Load | None, dispatch: SystemDispatch, ctx: DispatchContext
) -> list[float] | None:
    """가구 부하의 시각별 kW — `ESS.reducible_peak_kw(site_load_kw=...)` 로 간다
    (판정 §4·B-3, `docs/decisions-2026-08-31-R48.md`).

    부하가 없으면 `None` 이다 — 피크 저감은 그때 0 이 맞다(`reducible_peak_kw`
    독스트링).

    ⚠ **세운 자원(`dispatch`)에서 읽는다** — 형상 자산이나 대장에서 다시
    지으면 두 벌이 되어 어느 쪽이 실렸는지 구분할 수 없다(`_resource_lines()`
    가 적어 둔 같은 원칙).

    ⚠ **kWh 를 kW 로 명시 환산한다.** 스텝이 1시간이면 수는 같지만 단위가
    다르고, `dt` 가 바뀌는 날 조용히 틀린다.
    """
    if household is None:
        return None
    hours_per_step = ctx.dt / SECONDS_PER_HOUR
    return [
        -v / hours_per_step for v in dispatch.per_resource[household.name].electric
    ]


def _rec(rec_price_won_per_unit: float, weight: float) -> REC:
    """★★ **REC 를 화폐화 경로에 세운다** (사용자 판정 §4, `docs/decisions-
    2026-09-01-R51.md` — *「태양광 전력을 ESS에 충전한 후에 계통에 판매하면,
    해당 전력은 재생전력이므로 … 재생에너지 차익(REC)을 기대할 수 있다」*).

    클래스는 R16 이래 있었고 **실행 경로에서 부르는 자리가 0곳**이었다 —
    「구현이 없었다」가 아니라 **받을 자리가 없었다**(`NWAs`·`CP` 가 R51/WP-3
    전까지 그랬던 것과 같은 형태이며, 이 저장소가 다섯 번 만난 형태다).

    ⚠ **단가가 0 이면 0원을 낸다.** 그것이 결함이 아니라 대장의 판정이다
    (`docs/assumptions.yaml::benefit.rec_price` · `track: default0` — 제도·값
    근거가 확인되지 않은 편익은 크기를 추정하지 않는다). **단가가 확보되면
    대장 한 줄로 켜진다** — 그 배선을 `tests/casegrid/test_rec_wiring.py` 가
    붙든다.

    ⚠ **호출부가 이것을 `settlement_streams` 안에 넣는다.** 아래
    `_annualise((*settlement_streams, peak), …)` 가 `annualised[:-1]`·
    `annualised[-1]` 로 **자리로** 쪼개므로 `peak` 가 마지막이라는 성질을
    깨면 안 된다 — 튜플 밖에 더하면 첨두 절감 금액 자리에 REC 의 0원이 들어가고
    **예외도 나지 않는다.**

    ⚠ **구조가 있는 갈래에도 함께 선다.** 상계거래에서 REC 발급이 제한되는
    것은 `docs/exclusion-rules.yaml` 의 유형 `D` 두 규칙이 이미 선언하며,
    여기서 조건을 다시 쓰면 그 표가 정본이 아니게 된다 — 유형 `D` 는 거부가
    아니라 **표시**다(`assert_no_exclusions` 독스트링).

    ⚠ **함수로 뗀 이유는 갈래가 둘이기 때문이다** — 구조를 준 갈래와 주지
    않은 갈래가 각자 편익 튜플을 짓는데, 양쪽에 같은 생성자를 적으면 그것이
    사본이 되고 한쪽만 고치는 날 **구조를 준 실행에서만 REC 가 사라진다.**

    ⚠ **`weight` 는 이제 대장에서 온다** (`benefit.rec_weight_pv` · R52/WP-6).
    호출부가 `level_map` 에서 읽어 넘긴다 — 여기서 기본값을 두면 대장을
    고쳐도 이 함수가 옛 값을 쓴다.
    """
    return REC(weight=weight, rec_price_won_per_unit=rec_price_won_per_unit)


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
    extra_appliance_load_kwh: float = 0.0,
    rec_price_won_per_unit: float = 0.0,
    rec_weight_pv: float = 1.0,
    distributed_sub_items: DistributedSubItems | None = None,
    nwas_price_won_per_kwh: float = 0.0,
    cp_price_won_per_kw_month: float = 0.0,
    settlement_inputs: SettlementInputs | None = None,
    tariff_engine: TariffEngine | None = None,
    scheme: IncentiveScheme | None = None,
    viewpoint: Viewpoint = "OWNER",
    ess_operating_mode: ESSOperatingMode | str | None = None,
    ess_charge_source: ESSChargeSource | str | None = None,
    pv_allocation_priority: PVAllocationPriority | str | None = None,
    ess_shares: Sequence[ESSShare] | None = None,
    baseline_arrangement: BaselineArrangement | str | None = None,
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
    인자가 없으면 위반 조합을 **진입점으로 넣어 볼 방법이 없고** 그러면 이
    호출이 실제로 무언가를 막는지 아무도 확인할 수 없다 — 그것이 이 저장소가
    고치러 온 형태다. 넘긴 편익은 검사에 함께 들어가고, 화폐가치 계산은 아직
    내장 둘만 한다(편익 선택 API 는 `FR-402-AC2.A` 의 「선택 시」 절반이며
    아직 없다).

    ⚠⚠ **진짜 배타 축은 「운전 주체」다 — 「내장 편익 둘은 배타 쌍이 아니다」가
    아니다.** 이 자리는 종전에 `SurplusSale`·`PeakShaving` 이 배타 쌍이
    아니라고 적고 있었고, **그 문장이 이중계상을 정당화하는 근거로 인용돼
    왔다.** 그 진술 자체는 지금도 참일 수 있다(둘 다 **사용자 운전**의
    편익이다) — 그러나 실제 배타 축은 **「계통 급전 편익(CP·NWAs) × 사용자
    운전 편익(SelfConsumption·PeakShaving)」**이다. CP·NWAs 로 급전하는
    구조에서는 방전 시점을 사업자가 정하지 못하므로 자가소비·피크저감이
    성립하지 않는다(`docs/decisions-2026-08-31-R48.md` §2, 사용자 판정
    2026-08-31). **그 규칙은 WP-C 가 `docs/exclusion-rules.yaml` 에 세운다** —
    여기서는 yaml 을 고치지 않는다.

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

    ★ **`ess_operating_mode`·`ess_charge_source` — `:470` 하드코딩을 걷어낸다**
    (판정 §1·§3, `docs/decisions-2026-08-31-R48.md`). 종전에는 이 자리가
    `ESSOperatingMode.PEAK_SHAVING` 을 코드에 박아 두어, 그 모드의 충전창
    (01~06시)이 심야 계통충전을 강제했다 — 태양광 연계 ESS 의 운전이
    아니었다. 이제 인자 → `case_values` → 모듈 상수 순으로 값을 고른다.
    `pv_surplus_profile_kwh` 는 이 함수가 PV 를 먼저 디스패치해 만들고
    (충전원이 `PV_SURPLUS` 일 때만) 넘긴다 — 호출자가 줄 수 있는 값이 아니다.

    ★ **`pv_allocation_priority` — 낮 전기를 「가구」·「배터리」 중 누구에게 먼저
    주는가** (판정 §1, `docs/decisions-2026-09-01-R51.md`). 같은 인자 →
    `case_values` → 모듈 상수(`PV_ALLOCATION_PRIORITY_DEFAULT`) 순서를 따르되,
    이 축의 승격·거부는 `_resolve_ess_dispatch_inputs` 가 `resolve_pv_
    allocation_priority()` 로 직접 한다 — 어느 자원 계약도 이 축을 모른다.
    배포 기본값은 **`HOUSEHOLD_FIRST`(집 우선)** 다 — R51/WP-6 이 판정 §1
    (*「지산지소 모델의 경우에는 집에서 우선 사용하는 것이 취지에 맞음」*)에
    따라 뒤집었고, 근거는 그 상수 옆 주석에 있다.

    ★ **`extra_appliance_load_kwh` — 「추가 기기 비례 증가」** (판정 §5·B-2,
    `docs/decisions-2026-08-31-R48.md`). 히트펌프 등 추가 전력사용기기가
    있으면 **그 기기의 연간 소비전력량만큼 가구 부하 총량이 늘어난다** — 이
    인자가 그 증분이고, `annual_load_kwh` 에 더해 같은 `Load` 자원 하나로
    세운다(형상도 같은 대표일 형상을 쓴다). 기본값 0.0 은 *「추가 기기가
    없다」* 다.

    ⚠ **`annual_load_kwh` 가 `None`(부하를 아예 세우지 않는 실행)이면 이
    인자는 무시된다.** 기기 소비량은 가구 부하에 **더하는 증분**이지 그
    자체로 부하를 만드는 값이 아니다 — 기저 없이 증분만 있으면 「무엇에
    비례해 늘었는가」에 답할 수 없다.

    ★★★ **`ess_shares` — 배터리 한 대를 몫으로 갈라 몫마다 다른 역할을 준다**
    (R57/WP-6 · ★분할). `None` 이 *「몫으로 가르지 않는다」* 이고 **그것이
    기본**이다 — 그때 지금까지와 같은 `ESS` 하나가 서고 같은 편익이 조립된다.
    빈 시퀀스를 「가르지 않는다」로 읽지 마라: `core/casegrid/ess_share.py::
    split_ess` 가 *「몫이 하나도 없습니다」* 로 거부하며 **그 거부가 옳다**(빈
    목록을 넘긴 것은 실수다).

    몫을 주면 ① 몫마다 `ESS` 가 서서 **전건이 디스패치·수명·비용에 실리고**
    ② 몫마다 그 역할의 편익이 서며 ③ **단일 경로의 `PeakShaving`·`NWAs`·`CP`
    는 짓지 않는다**(같은 편익이 두 번 서면 `FR-402-AC1` 이 정의한 중복이고,
    배타 판정은 같은 태그 쌍을 규칙표에서 찾지 못해 막지도 못한다). 분기의
    몸통은 `core/casegrid/ess_build.py::build_case_ess_fleet`·
    `build_fleet_streams` 가 갖는다.

    ⚠⚠ **어느 케이스도 몫을 주지 않는다** — 몫 비율과 역할 배분은 아직 아무도
    정하지 않았고 여기서 지어내지 않는다. 통로만 냈다(R56 이 계절 축에서 쓴
    방식과 같다: *「구조는 섰고 값은 비어 있다」*). 값이 오면 결론축이
    움직이며 **그때가 사용자 판정 자리**다.

    ★★★ **`baseline_arrangement` — 기준선(Without)이 셋으로 갈린다**
    (`FR-705-AC2` · `DV-15` · 사용자 판정 `docs/decisions-2026-09-04-R59b.md`
    §1). R58 이 갈래 셋을 `core/cba/baseline.py` 에 **선언**했으나 이 진입점이
    그것을 **한 번도 읽지 않았다** — 읽는 배포 코드가 그 파일 자기 자신뿐이었고,
    그래서 산출된 `npv` 는 「갈래 미지정」의 수였다.

    `None` 은 *「적지 않았다」* 이고 그때 `DEFAULT_BASELINE_ARRANGEMENT`
    (ⓑ「자가용 유지」)로 돈다 — **기본값은 그 상수 한 곳에서만 정한다**
    (`resolve_baseline_arrangement` 독스트링). 빈 문자열이나 모르는 문면은
    거부되며 조용히 기본값으로 떨어지지 않는다.

    ⚠ **갈래가 계산을 가르는 자리는 자가소비 하나다** — 갈래가
    `SelfConsumptionTreatment.NONE`(ⓐ 자가용 없음)이면 전기사용자에게 자가용
    설비가 없으므로 낮 전기가 **가구로 먼저 가는 몫이 0** 이다. 그 반영은
    아래 `_resolve_ess_dispatch_inputs` 호출 직후 한 자리에서 한다.
    ⓑ(`CANCEL_OUT`)는 자가소비가 Without·With 양쪽에 똑같이 있어 차액에서
    소거되므로 **종전 동작 그대로**이며, 그래서 골든 셋이 움직이지 않는다.

    ⚠⚠ **ⓒ(`FORFEIT` · 자가용 집합자원화)는 `get_baseline_branch` 가 `DV-15`
    로 거부한다 — 그 거부를 여기서 풀거나 0 으로 채우지 않는다.** 포기 항
    (대칭 항)과 구분 계측 선언이 저장소에 없고, 없는 전제를 0 으로 메우면
    *「없는 제도 위에 편익을 쌓는」* 형태가 된다(그 함수 독스트링이 근거를
    갖는다). 거부는 **저장장치 조립·디스패치·편익·CBA 어느 것도 돌기 전에**
    난다 — `DV-5`(`check_analysis_period`)가 *「자원이 서자마자」* 재는 것보다
    이른 자리다.
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
    # ★ **교체 설비단가의 명목 변화율** = 물가 계수 + 실질 추세 (`Q-17` · R42).
    #
    # **덧셈인 근거는 대장이 갖는다** — `capex.replacement_real_trend` 의
    # `applicable_scope` 가 *「명목 교체단가의 연 변화율은 물가 계수 + 이 값」*
    # 이라 적었다. 여기서 다시 정하지 않고 그 문면을 따른다(정하면 정본이 둘이
    # 된다). 기준수준에서 그 값은 0 이므로 **이 배선은 지금 결론을 안 움직인다** —
    # 움직이는 것은 스윕이 하단·상단을 물을 때다.
    #
    # ⚠ **O&M 에는 넘기지 않는다.** 같은 대장 항목이 적용범위를 스스로 좁혀
    # *「고정·변동 O&M 은 대상이 아니다」* 라 적었고, 그래서 자원 계약이 계수를
    # 둘로 나눠 갖는다(`DER.replacement_escalation_factor()`). 한 인자로 두면
    # 하단 −2.0 이 「물가 계수를 태우지 않았다면」이 아니라 「O&M 물가까지 꺼
    # 버렸다면」을 재게 된다.
    #
    # ⚠ **`Load` 에는 넘기지 않는다** — 위 적용범위가 대상을 `ESS` 배터리·PCS 와
    # `PV` 인버터로 명시한다. 부하에 교체 자산이 들어오는 날 함께 본다.
    replacement_escalation_rate = PRICE_ESCALATION_RATE + _resolve(
        case_values.get("replacement_real_trend", "base"),
        "replacement_real_trend",
        level_map,
    )
    # ★ **PV 설비단가 중 인버터 몫** (`capex.pv.inverter_share` · `Q-18` · R43).
    #
    # 종전에는 `core/der/pv.py::DEFAULT_INVERTER_CAPEX_RATIO = 0.15` 라는 모듈
    # 상수였고 **어느 케이스 축에도 없었다** — R39-E 의 배선으로 결론에는
    # 들어왔는데 흔들 수는 없는 상태였다(`ledger_levels.py::_LEDGER_VARS` 의
    # 그 줄에 경위가 있다).
    #
    # ⚠ **비율을 여기서 단가로 짓는다.** 대장이 갖는 것은 *「설비단가의 몇
    # %가 인버터인가」* 이고 `PV` 가 받는 것은 원/kW 이므로 환산이 한 번
    # 필요하다 — 그 환산을 자원 안에 두면 자원이 대장 키를 알게 되고
    # (`NFR-208-AC1` 위반), 리포트 쪽에 두면 사본이 된다.
    # ⚠ **모듈 상수를 읽지 않는다.** 읽으면 이 축이 도는 동안에도 러너가
    # 기준값을 계속 쓰고 **변동폭이 0원으로 나온다** — 「진짜 무영향」과
    # 구별되지 않는 형태이며, 아래 `_resource_lines()` 가 *「세운 자원에서
    # 읽는다」* 로 같은 함정을 적어 두었다. 기본값을 두지 않는 이유도 같다.
    pv_inverter_share = _resolve(
        case_values.get("pv_inverter_share", "base"), "pv_inverter_share", level_map
    )
    # ★ **첨두 기본요금 단가** (`tariff.hv_single_contract.demand_charge` ·
    # `Q-6` · R43). 종전에는 `DEMAND_CHARGE_WON_PER_KW_MONTH = 8_320.0` 모듈
    # 상수였고 **대장에도 축에도 없었다** — 첨두 절감 편익(전체 편익의 21%)을
    # 혼자 정하는 단가인데 붙임 1 의 어느 행도 그 신뢰도·출처를 말하지 못했다
    # (문의사항 나-8 · `ledger_levels.py::_LEDGER_VARS` 의 그 줄에 경위가 있다).
    # 상수를 **지웠다** — 남기면 이 축이 도는 동안에도 러너가 기준값을 계속
    # 쓰고 변동폭이 0원으로 나온다(인버터 몫에서 적어 둔 그 함정이다).
    # ★ **고정 O&M 둘** (`opex.pv.fixed_om`·`opex.ess.fixed_om` · R51/WP-2,
    # 사용자 판정 §2). 종전에는 `PV_FIXED_OM_WON_PER_YEAR`·`ESS_FIXED_OM_
    # WON_PER_YEAR` 모듈 상수였다 — 값은 그대로 옮겼고(100,000원/년 각각),
    # 신뢰도만 「가정」으로 대장에 드러난다. **두 자원의 값이 지금은 같아도
    # 축은 둘이다** — PV·ESS 는 다른 설비이고 값이 갈릴 수 있다.
    # ⚠ **`demand_charge` 와 한 statement 로 묶었다** — `PLR0915`(이 함수의
    # statement 상한 50)에 이미 닿아 있었다(R51/WP-1 브리프 실측). 계산이
    # 얽혀 있어서가 아니라 넷 다 `_resolve()` 스칼라 조회이기 때문이다.
    # ★ **R52/WP-6 이 `ess_replacement` 를 더했다**(`capex.ess.replacement` ·
    # 사용자 판정 §7). 같은 이유로 새 statement 를 만들지 않고 이 대입에
    # 얹는다. ⚠ **`rec_weight_pv` 는 여기 없다** — 이유는
    # `ledger_levels.py::_LEDGER_VARS` 옆 주석에 있다(폭을 지어낼 수 없어
    # 이 함수의 인자로 직접 받는다).
    demand_charge, pv_fixed_om, ess_fixed_om, ess_replacement_price = (
        _resolve(case_values.get("demand_charge", "base"), "demand_charge", level_map),
        _resolve(case_values.get("pv_fixed_om", "base"), "pv_fixed_om", level_map),
        _resolve(case_values.get("ess_fixed_om", "base"), "ess_fixed_om", level_map),
        _resolve(case_values.get("ess_replacement", "base"), "ess_replacement", level_map),
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
        inverter_unit_capex_won_per_kw=pv_capex * pv_inverter_share,
        # ★ **인버터 교체 단가** (사용자 판정 §7 · R52/WP-6). 조사가 크기 근거를
        # 찾지 못해(WP-5 §7) **취득 단가와 같은 값**을 쓴다 — 위 줄과 같은
        # 표현식이며 지어낸 차이가 아니다. `pv.py::inverter_replacement_unit_
        # won_per_kw` 가 그 통로다.
        inverter_replacement_unit_won_per_kw=pv_capex * pv_inverter_share,
        fixed_om_won_per_year=pv_fixed_om,
        escalation_rate=PRICE_ESCALATION_RATE,
        replacement_escalation_rate=replacement_escalation_rate,
        self_consumption_ratio=PV_SELF_CONSUMPTION_RATIO,
        operating_mode=OperatingMode.FULL_EXPORT,
    )

    # ★ **부하는 편익을 만들지 않는다** (`RC-LD-B0` · `Load.value_streams()` 는
    # 비어 있다). 그래서 여기 더해도 편익 갈래는 늘지 않고 **운전만** 달라진다 —
    # 계통 수전이 실제 수량으로 나온다. 화폐화(자가소비 절감·구매 비용)는 요금
    # 엔진의 몫이며, 한쪽만 계상하면 사업에 불리한 쪽으로 틀린다(NSPM 대칭성).
    # ⚠ **여기로 옮겼다(판정 §1 ④)** — `_household_load_if_total_given` 은
    # 함수 인자만 쓰고 그 사이에 만들어지는 어떤 것도 쓰지 않으므로, PV 잉여
    # 배분(`HOUSEHOLD_FIRST`)이 이 부하 시계열을 봐야 하는 지금 자리로 옮겨도
    # 안전하다.
    household = _household_load_if_total_given(
        daily_shapes, annual_load_kwh, extra_appliance_load_kwh
    )

    # ★ **운전 방법·충전원·PV 잉여 배분 순서 — 하드코딩을 세 갈래로 노출한다**
    # (판정 §1·§3·A-3·A-6, `docs/decisions-2026-09-01-R51.md`). 한 statement 로
    # 묶어 부르는 이유는 계산 자체가 아니라 `PLR0915`(이 함수의 statement 상한)
    # 다 — 이 함수는 이미 그 상한에 닿아 있었다(브리프 실측).
    ctx = DispatchContext(steps=STEPS_PER_DAY, dt=SECONDS_PER_HOUR, year=Year(1))
    (
        resolved_ess_operating_mode,
        resolved_ess_charge_source,
        ess_pv_surplus_profile_kwh,
        resolved_pv_allocation_priority,
    # ★★★ **기준선 갈래가 이 자리를 지난다** (`FR-705-AC2` · 위 독스트링).
    # 감싸는 함수가 `core/casegrid/pv_allocation.py` 에 있는 이유는 그 모듈
    # 머리말의 R60/WP-2 절이 갖는다(이 함수의 `PLR0915` 문장 상한이 꽉 차
    # 있었고, 이 파일의 `NFR-206` 코드 줄 상한도 닿아 있었다).
    ) = _dispatch_inputs_under_baseline(
        ess_operating_mode, ess_charge_source, case_values, pv, ctx,
        pv_allocation_priority=pv_allocation_priority, household=household,
        baseline_arrangement=baseline_arrangement,
    )

    # ★ **제원 상수 여덟과 `ESS(...)` 조립 전문은 `ess_build.py` 에 있다**
    # (R57/WP-5). 여기서 넘기는 것은 **이미 해석된 값들**(위
    # `_resolve_ess_dispatch_inputs` 가 골랐다)과 **대장에서 온 값들**뿐이며,
    # 그 해석은 함께 가지 않았다 — 가면 「자리 옮김」이 아니게 된다.
    # ⚠ `cast(ESSOperatingMode, ...)` 와 `pv_surplus_profile_kwh` 의 조건식은
    # 사유 주석째로 그 모듈이 들고 있다.
    #
    # ★★★ **몫 분기도 그 모듈이 진다**(R57/WP-6 · ★분할). 돌려받는 셋은
    # ① 디스패치·수명·자원 표에 실을 **자원 전건** ② 몫 계획 전건(몫이 없으면
    # 빈 튜플) ③ **가르기 전의 물리 배터리**다. ③이 따로 오는 이유는 교체비·
    # 잔존가치가 **물리 배터리 한 대의 사건**이고 그 행을 짓는
    # `core/casegrid/lifecycle.py::lifecycle_rows` 가 자원 하나만 받기
    # 때문이다 — 몫이 없으면 ①의 유일한 원소가 ③과 같은 객체다.
    ess_fleet, ess_plans, ess_whole = build_case_ess_fleet(
        shares=ess_shares,
        capacity_kwh=ess_capacity_kwh,
        operating_mode=resolved_ess_operating_mode,
        charge_source=resolved_ess_charge_source,
        pv_surplus_profile_kwh=ess_pv_surplus_profile_kwh,
        capex_unit_won_per_kwh=ess_capex, fixed_om_won_per_year=ess_fixed_om,
        replacement_unit_won_per_kwh=ess_replacement_price,
        escalation_rate=PRICE_ESCALATION_RATE,
        replacement_escalation_rate=replacement_escalation_rate,
    )

    # ★ **자원이 서자마자 분석기간을 잰다 (DV-5).** 수명은 자원이 갖고 있으므로
    # 여기가 규칙을 평가할 수 있는 가장 이른 자리다 — 디스패치·편익·CBA 어느
    # 것도 돌기 전에 거부한다. 늦게 두면 상한을 넘긴 케이스의 중간 산출물이
    # 한 번은 만들어지고, 그것이 로그·캐시로 새어 나간다(`DV-10` 과 같은 이유).
    # ⚠ **몫 전건의 수명을 넣는다** — 하나만 넣으면 나머지 몫이 상한 판정에서
    # 사라진다(지금은 몫마다 수명이 같지만, 같다는 사실을 여기가 아니라
    # `split_ess` 가 정한다).
    check_analysis_period(
        analysis_years=horizon_years,
        asset_lifetimes_years=[pv.lifetime, *(e.lifetime for e in ess_fleet)],
    )

    # 2. Dispatch
    # ⚠ **몫 전건을 싣는다** — 하나만 실으면 나머지 몫이 방전하지 않는다.
    engine = RuleBasedEngine()
    resources: list[DER] = (
        [pv, *ess_fleet] if household is None else [pv, *ess_fleet, household]
    )
    dispatch = engine.run(resources, ctx)

    # 3. Benefits (one day, annualised)
    grid_export_result = DispatchResult(
        electric=list(dispatch.grid_export),
        heat=[0.0] * ctx.steps,
        cool=[0.0] * ctx.steps,
        fuel=[0.0] * ctx.steps,
    )
    # ★★★ **ESS 가 만드는 편익 — 몫이 있으면 몫 편익이 대체한다** (R57/WP-6).
    #
    # 종전 이 자리는 `_resolve_nwas_cp(ess, …)` 둘과 아래쪽의 `PeakShaving`
    # 하나로 흩어져 있었다. 몫 분기를 그 셋 자리마다 적으면 이 함수의
    # `PLR0915`(statement 상한 50 · 실측 여유 0)를 넘기므로 **한 호출로 묶어**
    # `core/casegrid/ess_build.py::build_fleet_streams` 가 판정한다 —
    # 종전 두 statement(첨두 저감 출력 · `PeakShaving`)를 이 하나가 대신하므로
    # statement 는 오히려 하나 줄었다.
    #
    # ⚠ **디스패치 뒤에 부른다** — 몫의 첨두 저감이 `_site_load_kw(...)` 를
    # 요구하고 그것은 디스패치 결과에서 나온다. 그래서 자원(위)과 편익(여기)이
    # 같은 호출에 들어갈 수 없다.
    # ⚠ **`peak` 는 여전히 연간화 목록의 마지막에 선다** —
    # `tests/casegrid/test_nwas_cp_wiring.py` 의 ③ 이 그 자리를 붙든다.
    ess_streams, peak = build_fleet_streams(
        ess_fleet, ess_plans,
        nwas_price_won_per_kwh=nwas_price_won_per_kwh,
        cp_price_won_per_kw_month=cp_price_won_per_kw_month,
        demand_charge_won_per_kw_month=demand_charge,
        site_load_kw=_site_load_kw(household, dispatch, ctx),
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
        # ★★ **`NWAs`·`CP` 는 `core/casegrid/grid_support.py::_resolve_nwas_cp`
        # 가 짓는다** (판정 §3, `docs/decisions-2026-09-01-R51.md`) — 도우미로 뺀
        # 이유는 `_rec` 와 같지만 여기서는 **별도 statement 를 만들지 않는다**
        # (`PLR0915` 여유가 0 이라 새 대입 자체가 빨간불이다). `*` 로 풀어 기존
        # 대입 표현식 안에 넣는다.
        # ★ R57/WP-6 뒤에는 그 호출을 `build_fleet_streams` 가 대신 하고 이
        # 자리는 그 결과(`ess_streams`)를 푼다 — **몫이 있으면 그 둘 대신 몫
        # 편익이 여기 실린다**(같은 편익을 두 번 세우지 않는다).
        settlement_streams: tuple[ValueStream, ...] = (
            *plan.streams,
            _rec(rec_price_won_per_unit, rec_weight_pv),
            *ess_streams,
        )
        # ★ **구조가 만드는 비용을 비용으로 나른다 (R32).** 조립기가 편익에서
        # 빼 주는 것이 아니라 여기서 프로포마 행이 된다 — 근거는
        # `core/cba/proforma.py::fee_row`. `core.cba` 가 `core.valuestream` 보다
        # 위 계층이라 조립기가 행을 지을 수 없고(`NFR-208-AC1`), 그 경계를
        # `SettlementCost` 가 건넌다.
        settlement_costs = tuple(plan.costs)
    else:
        # ★ **충전원이 계통(GRID)인 ESS 방전분을 잉여판매 수량에서 뺀다**
        # (판정 §4, `docs/decisions-2026-09-01-R51.md` · R51/WP-5). `PV_SURPLUS`
        # 충전분은 태양광 전력이 ESS 를 경유한 것이라 빼지 않는다(0.0).
        #
        # ⚠ **연간값을 그 창(대표일)의 단위로 나눈다.** `SurplusSale` 이 받는
        # `dispatch` 는 대표일 하나이고 그 값에 `DAYS_PER_YEAR` 를 곱하는 것은
        # 호출측(`operating_lines.annualise`)이다 — 여기서 연간 방전량을 그대로
        # 넘기면 대표일에서 연간치를 빼게 된다(`SurplusSale.__init__` 독스트링 참조).
        #
        # ⚠ 이 판단을 여기 한 자리에만 둔다(판정②) — 새 statement 를 만들지
        # 않고 호출 인자 표현식에 싣는 것은 이 함수의 `PLR0915` 여유가 없기
        # 때문이다(위 `demand_charge` 주석과 같은 이유).
        #
        # ⚠ **몫 전건을 더한다**(R57/WP-6) — 계통 충전 몫이 둘이면 둘 다 빼야
        # 한다. 하나만 보면 나머지 몫의 방전분이 태양광 잉여로 팔린다.
        settlement_streams = (
            SurplusSale(
                sale_price_won_per_kwh=surplus_sale_price,
                non_pv_ess_discharge_kwh=sum(
                    (
                        e.annual_discharge_kwh(year=1) / DAYS_PER_YEAR
                        for e in ess_fleet
                        if e.charge_source is ESSChargeSource.GRID
                    ),
                    0.0,
                ),
            ),
            _rec(rec_price_won_per_unit, rec_weight_pv),
            *ess_streams,
        )
        settlement_costs = ()

    # ⚠ **첨두 절감(`peak`)은 위 `build_fleet_streams` 가 이미 지었다**(R57/
    # WP-6). 방식 「나」(배전망 사업자 지시)에서 애초에 만들지 않는다는 판정
    # (사용자 판정 §1, `docs/decisions-2026-09-02-R54.md` · 술어는
    # `core/casegrid/grid_support.py::peak_shaving_enabled`)도 그 함수가 진다.

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
    annualised = _annualise((*settlement_streams, peak), grid_export_result)
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

    # ⚠ **취득비는 몫 전건의 합이다**(R57/WP-6) — 하나만 더하면 나머지 몫의
    # 취득비가 사라져 결론축이 **좋아지는 쪽으로** 틀린다.
    initial_investment = Money(
        pv.capex(year=1) + sum((e.capex(year=1) for e in ess_fleet), Money(0))
    )
    # ⚠ **교체비·잔존가치만은 물리 배터리 한 대의 것이다** — 한 대를 몫으로
    # 가른 것이지 여러 대를 산 것이 아니므로 18년차 재취득도 한 번이다.
    # `core/casegrid/lifecycle.py::lifecycle_rows` 가 자원 하나만 받는 것도
    # 그 때문이며, 몫이 없으면 `ess_whole` 은 `ess_fleet[0]` 과 같은 객체다.
    lifecycle_rows, one_off_flows = _lifecycle_rows(
        pv=pv, ess=ess_whole, horizon_years=horizon_years
    )
    benefit_rows = [
        benefit_row(
            "E2EBenefit",
            {year: annual_benefit for year in range(1, horizon_years + 1)},
        ),
    ]
    # ★ **운영비와 교체·잔존을 이름으로 갈라 둔다** (R49 · 판정 §3 ⓐ).
    # 아래에서 둘을 이어 붙여 순현금흐름을 만드는 것은 **종전 그대로**이며
    # 지표는 여전히 그 합성 위에 선다 — 갈라 두는 것은 `CashflowSplit` 이
    # 나를 **분해용 사본**을 위해서다(그 독스트링 참조).
    operating_cost_rows = [
        fixed_om_row(
            "PVFixedOM",
            start_year=1,
            end_year=horizon_years,
            annual_amount_won=int(pv.fixed_om(year=1)),
            escalation_rate=PRICE_ESCALATION_RATE,
        ),
        fixed_om_row(
            "ESSFixedOM",
            start_year=1,
            end_year=horizon_years,
            # ⚠ **몫 전건의 합이다**(R57/WP-6). 몫마다 `to_won()` 이 따로
            # 반올림하므로 물리 배터리 한 대의 값과 **최대 「몫 수 − 1」원**
            # 어긋날 수 있다 — 그 한계는 `.orch/R57/result_1.md` 6-2 가 실측과
            # 함께 적었고, 여기서 미리 반올림해 맞추면 `NFR-103`(반올림은
            # `to_won()` 한 곳)을 이 자리가 깬다.
            annual_amount_won=int(sum((e.fixed_om(year=1) for e in ess_fleet), Money(0))),
            # ★ **행이 자기 물가를 직접 굴린다** — 위 자원 생성자의
            # `escalation_rate` 를 넣어도 이 행은 따라오지 않는다
            # (`proforma.py:85-89` 의 `current *= (1+i)` 루프이며
            # `annual_amount_won` 은 `year=1` 로 고정 평가한 값이라 지수가 0
            # 이다). 그래서 부채가 **두 항**이었고, 한 항만 닫으면 같은 자원의
            # 고정 O&M 과 교체비가 서로 다른 가격 기준으로 선다 — 리포트의
            # 「가격 기준 · 명목 (전 항목 공통)」이 그 순간 거짓이 된다.
            escalation_rate=PRICE_ESCALATION_RATE,
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
    # ★★★ **교체비·잔존가치 (R39-E).** 판정 근거는 `_lifecycle_rows`
    # 독스트링 — 특히 *왜 잔존가치가 편익 행이 아닌가* 와 *왜 갈라 넣을 수
    # 없는가*. 이 별표 하나가 다섯 라운드 미뤄진 자리다.
    #
    # ⚠ **여기서 이어 붙이는 것은 종전 그대로다** — 지표는 이 합성 위에 선다.
    # 갈라 둔 `operating_cost_rows` 는 분해용 사본으로만 나간다(`CashflowSplit`).
    all_rows = net_operating_flows(
        benefit_rows, [*operating_cost_rows, *lifecycle_rows]
    )

    # 5. 변형별 지표 — **등록된 변형 전부** (FR-607-AC1). 위 독스트링 참조.
    variants = {
        case_flows.tag: metrics_for(
            initial_outlay(case_flows.rows), all_rows, discount_rate
        )
        for case_flows in build_capex_cashflows_for_all_cases(
            scheme, initial_investment, viewpoint
        )
    }

    # 6. 산식의 대입값 — **리포트가 「왜 이 값인가」에 답하는 재료**
    # (`FR-1001-AC3` · `CaseBasis` 독스트링). 여기서 담지 않으면 리포트가
    # 지표를 다시 계산하거나 자원 구성을 사본으로 갖게 된다.
    annual_cost = sum(
        int(row.amounts.get(1, 0))
        for row in (*operating_cost_rows, *lifecycle_rows)
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
    resource_lines = _resource_lines(
        pv, pv_capex, ess_fleet, ess_capex, benefit_lines,
        self_consumption_ratio=measured_self_consumption_ratio(
            pv, ctx, ess_pv_surplus_profile_kwh
        ),
        pv_allocation_priority=resolved_pv_allocation_priority,
    )

    return CaseOutcome(
        metrics=metrics_for(initial_investment, all_rows, discount_rate),
        variants=variants,
        # ★ 자원과 운전 결과를 **그대로** 넘긴다 — 리포트가 엔진 규칙과
        # 시간대별 운전을 물을 대상이다(`CaseOutcome` 독스트링). 여기서 요약해
        # 넘기면 무엇을 요약할지가 러너의 판단이 되고, 리포트가 다른 것을
        # 물을 때마다 이 파일이 함께 바뀐다.
        # ⚠ **몫 전건을 넘긴다**(R57/WP-6) — 하나만 넘기면 리포트·비교 표가
        # 나머지 몫을 「없는 자원」으로 읽는다.
        resources=(pv, *ess_fleet),
        dispatch=dispatch,
        # 엔진 인스턴스가 실제로 쓴 순서다 — 기본 상수를 다시 읽지 않는다
        # (`CaseOutcome.rule_order` 독스트링).
        rule_order=engine.rule_order,
        # ★ **엔진이 만든 행을 갈린 채로 넘긴다** (R49 · 판정 §3 ⓐ).
        # 여기서 요약하거나 합치지 않는다 — 리포트가 결손을 항목별로 가를 때
        # 1년차 값으로 되지으면 물가 상승이 빠져 합계가 결손과 어긋난다
        # (`CashflowSplit` 독스트링의 실측 469,314원).
        cashflows=CashflowSplit(
            benefit=tuple(benefit_rows),
            operating_cost=tuple(operating_cost_rows),
            lifecycle=tuple(lifecycle_rows),
        ),
        # ★★★ 관점 넷 배선 (R52/WP-A) — `build_perspective_wiring()` 독스트링 참조.
        # ★ 사회 편익은 `society_annualised` 로 따로 넣는다 (R53/WP-1 판정 ①) —
        # `annualised` 는 위에서 한 글자도 고치지 않는다.
        perspectives=build_perspective_wiring(
            annualised, benefit_rows, [*operating_cost_rows, *lifecycle_rows],
            initial_investment, discount_rate, horizon_years=horizon_years,
            society_annualised=build_society_annualised(distributed_sub_items)),
        basis=CaseBasis(
            initial_investment_won=int(initial_investment),
            annual_benefit_won=annual_benefit,
            annual_cost_won=annual_cost,
            discount_rate=discount_rate,
            horizon_years=horizon_years,
            grid_purchase_price_won_per_kwh=grid_purchase_price,
            surplus_sale_price_won_per_kwh=surplus_sale_price,
            resources=resource_lines,
            benefits=benefit_lines,
            # ★★ **금액의 자원별 몫은 선언이 아니라 수량에서 나온다 (R43-E2).**
            # 종전 4.3 은 `line.tag in resource.produces` 로 잉여 판매 전액을
            # 태양광에 실었는데, 그 금액의 근거 수량인 계통 송전 18.80kWh 중
            # 8.00kWh 는 **저장장치 방전분**이다 — 표가 스스로 적어 둔 성립
            # 조건(「1:1 로 귀속될 때」)이 그 실행에서 거짓이었다.
            #
            # ⚠ **창을 읽는 편익의 목록을 여기 적지 않는다** — 편익이 선언한
            # 것(`scales_with_dispatch_window`)을 모아 넘긴다. 목록을 적으면
            # 편익이 늘 때 낡고, 낡아도 표는 그대로 인쇄된다(위 연간화 규약과
            # 같은 근거).
            benefit_attributions=attribute_benefits(
                benefit_lines,
                dispatch=dispatch,
                export_window_tags=frozenset(
                    stream.tag
                    for stream, _ in annualised
                    if type(stream).scales_with_dispatch_window
                ),
                resources=resource_lines,
            ),
            # ★ **일회성 흐름은 갈라 담는다** (`OneOffLine` 독스트링 · 붙임 4
            # 판정). `costs` 는 「1년차 금액」의 자리이고 18년차 교체비를 그
            # 칸에 0원으로 적으면 *「합계만 있는 표에서는 빠진 행이 드러나지
            # 않는다」* 가 되돌아온다.
            one_off_flows=one_off_flows,
            costs=_cost_lines(
                pv_fixed_om=int(pv.fixed_om(year=1)),
                # ⚠ 위 `ESSFixedOM` 행과 **같은 합**이어야 한다 — 갈리면 표와
                # 프로포마가 서로 다른 수를 인쇄한다.
                ess_fixed_om=int(
                    sum((e.fixed_om(year=1) for e in ess_fleet), Money(0))
                ),
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


def _resource_lines(
    pv: PV,
    pv_capex: float,
    ess_fleet: Sequence[ESS],
    ess_capex: float,
    benefits: Sequence[BenefitLine],
    *,
    self_consumption_ratio: float,
    pv_allocation_priority: PVAllocationPriority,
) -> tuple[ResourceLine, ...]:
    """평가 대상 자원 제원 — 리포트 0절의 재료 (`ResourceLine` 독스트링).

    ★ **저장장치는 몫 전건이 온다** (R57/WP-6). 몫으로 가르지 않은 실행에서는
    원소가 하나이므로 종전과 같은 표 두 줄이 난다. 몫이 있으면 몫마다 한 줄이
    서고 각 줄의 용량·정격출력·취득비·고정 O&M 이 **그 몫의 것**이다 — 하나만
    인쇄하면 나머지 몫의 취득비·고정 O&M 이 표에서 사라진다.

    ★ **정책 가정 경고도 여기서 실린다** (`FR-404-AC1` · R48 §7). 훅은 `DER`
    계약에 있으므로 자원 종류를 묻지 않는다 — 새 자원이 경고를 내기 시작해도
    이 함수도 리포트도 한 줄이 바뀌지 않는다.

    ★★ **`self_consumption_ratio`·`pv_allocation_priority` 는 호출자가 이미
    본 실행에서 잰 값을 받는다 — 여기서 다시 재지 않는다** (판정 §4 나-2).
    모듈 상수(`PV_SELF_CONSUMPTION_RATIO`)에서 읽으면 실제 배분 결과가 바뀌어도
    이 칸이 그대로여서 아무 예외도 나지 않는다 — 위 정책 경고와 같은 함정.
    """

    def produced_by(resource: str) -> tuple[str, ...]:
        return tuple(
            line.tag for line in benefits if line.resource_code == resource
        )

    return (
        ResourceLine(
            name=pv.name,
            kind="태양광 (옥상 고정형)",
            # ★ **세운 자원에서 읽는다.** 모듈 상수에서 읽으면 용량 스윕이
            # 도는 동안에도 리포트가 기준 용량을 계속 인쇄한다 — 값이 바뀌어도
            # 아무 예외가 나지 않는 형태다.
            # ★★ **자가소비율은 `PV_SELF_CONSUMPTION_RATIO`(모듈 상수)가 아니라
            # 본 실행의 실측치를 받는다** (판정 §4). `BATTERY_FIRST` 갈래에서만
            # 그 상수가 계속 쓰이며(`pv_allocation._resolve_ess_dispatch_inputs`
            # 독스트링), 여기 인쇄되는 값은 갈래와 무관하게 이 실행이 실제로
            # 배분한 결과다 — 「(본 실행 실측)」 문면이 그 사실을 표시한다.
            capacity=(
                f"{pv.capacity_kw:g} kW · 이용률 {PV_CAPACITY_FACTOR:.0%} · "
                f"자가소비율 {self_consumption_ratio:.0%} (본 실행 실측)"
            ),
            # ★★ **선언(전량 판매)과 본 실행 배분 순서를 함께 적는다** (판정
            # §4 나-4). 두 값이 서로 달라 보이는 것은 결함이 아니다 — PV 는
            # 잉여를 전량 판매로 「선언」했고, 그 잉여가 무엇인지는 `pv_
            # allocation_priority` 축이 낮 동안 따로 정한다(같은 뿌리, 판정
            # §4 ⚠). 배분 순서는 실행이 실제로 고른 값(`resolved_pv_allocation_
            # priority`)에서 읽는다 — 지어내지 않는다.
            operating_mode=(
                f"{pv.operating_mode} (선언) · 본 실행 배분: {pv_allocation_priority}"
            ),
            lifetime_years=int(pv.lifetime),
            unit_capex=f"{pv_capex:,.0f}원/kW",
            capex_won=int(pv.capex(year=1)),
            fixed_om_won_per_year=int(pv.fixed_om(year=1)),
            produces=produced_by("PV"),
            policy_warnings=tuple(pv.policy_warnings()),
        ),
        *(
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
                policy_warnings=tuple(ess.policy_warnings()),
            )
            for ess in ess_fleet
        ),
    )
