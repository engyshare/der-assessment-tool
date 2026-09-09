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

from core.casegrid.appliance_load import ApplianceSeasonShares
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

# ★ **가구 수 배수의 판정은 이 파일 것이 아니다** (R64/WP-1) — 아래 `ess_build` ·
# `pv_allocation` 과 같은 사유로 `core/casegrid/household_scale.py` 에 있고
# 판정(1 이상의 정수인가)도 그 모듈이 진다.
#
# ⚠ **R64/WP-4 뒤로 「부하」 쪽 곱은 이 파일에 없다** — 총량에 곱하는 자리가
# 부하 생성자와 함께 `core/casegrid/seasonal_dispatch.py` 로 갔다(아래 import 옆 ⚠).
# ★★★ **R65/WP-2b 에 「설비」 쪽 곱이 이 파일로 왔다** — `pv_capacity_kw` ·
# `ess_capacity_kwh` 는 러너가 `_resolve` 로 직접 얻는 값이라 그 자리가 여기밖에
# 없다. 그래서 이 파일이 배수를 **다시** 읽는다. 사유는 아래 두 `_resolve` 옆 ★★★.
from core.casegrid.household_scale import household_scale
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
    ESS_DISCHARGE_ALLOCATION_DEFAULT,  # noqa: F401
    ESS_OPERATING_MODE_DEFAULT,  # noqa: F401
    FORFEITED_SELF_CONSUMPTION_TAG,
    PV_ALLOCATION_PRIORITY_DEFAULT,  # noqa: F401
    _dispatch_inputs_under_baseline,  # noqa: F401
    _forfeited_self_consumption_rows,
    _resolve_ess_dispatch_inputs,  # noqa: F401
    measured_self_consumption_ratio,
)

# ★★★ **계절 넷을 각각 돌려 합산하는 운전이 이 모듈에 있다** (R64/WP-4 · 착수 36ⓐ).
# 갈라낸 사유는 그 모듈 머리말이 갖는다 — `pv_allocation.py`·`ess_build.py` 와
# 같다(이 파일의 `NFR-206` 코드 줄 상한과 `run_single_case_e2e` 의 `PLR0915`
# 문장 상한이 둘 다 꽉 차 있었다).
# ⚠ **`_household_load_if_total_given` 은 재수출이다** — 계절마다 부하를 세워야
# 해서 생성자가 그 모듈로 갔고, 이름은 여기 남는다(위 ⚠ 주석 참조).
from core.casegrid.seasonal_dispatch import (
    _household_load_if_total_given,  # noqa: F401
    build_and_dispatch_case,
    dispatch_note,
)
from core.cba.baseline import BaselineArrangement, PoolMeteringDeclaration
from core.cba.proforma import (
    benefit_row,
    energy_purchase_row,
    escalation_factor,
    fee_row,
    fixed_om_row,
)
from core.contracts.assumptions import AssumptionProvider
from core.contracts.der import DispatchContext, DispatchResult
from core.contracts.engine import SystemDispatch
from core.contracts.units import Money, to_won
from core.contracts.valuestream import ValueStream
from core.der.ess import ESS, ESSChargeSource, ESSOperatingMode
from core.der.ess_schedule import ESSDischargeAllocation
from core.der.load import Load
from core.der.pv import PV, PVAllocationPriority
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
    "FORFEITED_SELF_CONSUMPTION_TAG",
    "HOURS_PER_YEAR",
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
# ⚠ **이용률도 여기 없다** — `PV_CAPACITY_FACTOR = 0.15` 모듈 상수를
# R67/WP-N2 가 지웠다. 대장 `capacity_factor.pv_rooftop` 에서 `level_map` 으로
# 온다(사용자 판정 R67 §2 「모든 수치는 추후 변경 가능」 ·
# `docs/decisions-2026-09-08-R67b.md` §3-4) — 아래 고정 O&M 과 **같은 사유**로
# 기본값을 남기지 않았다. 그 값을 읽던 자리가 셋이었고(러너의 발전량 · 2.1 표의
# 문면 · 자립 역산의 역수) 그중 어느 것도 사용자가 바꿀 통로를 갖지 못했다.

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

#: ⚠ **가구 부하 생성자도 여기 없다** (R64/WP-4) — `_household_load_if_total_given`
#: 은 `core/casegrid/seasonal_dispatch.py` 로 갔다. 계절마다 부하를 세워야 하는데
#: `Load(...)` 를 두 곳에 적으면 사본이 되기 때문이다. **이름은 그대로이고 이
#: 파일이 재수출한다**(위 import) — 그 이름을 가리키는 문면들
#: (`pv_allocation.py`·`case_metrics.py`·이 파일 `run_single_case_e2e` 독스트링)
#: 은 그래서 여전히 참이다.


def _site_load_kw(
    household: Load | None,
    dispatch: SystemDispatch,
    ctx: DispatchContext,
    coincidence_factor: float,
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

    ## ★★★ **동시율이 걸리는 자리는 여기 하나다** (R66/WP-5 · 사용자 지시)

    사용자 문면은 *「동시율은 내가 임의로 정하기 어려움. 초기설정은 80%로
    하고, 설정을 통해 변경하는 한 것으로 설계해줘」* 까지이고 **적용 자리를
    말하지 않았다.** 그 자리를 정한 것은 판정
    (`docs/decisions-2026-09-07-R66.md` §3)이며 *「출력·ESS 용량에 걸리고
    연간 전력량·태양광 용량에는 걸리지 않는다」* 다. 이 함수의 반환값이
    **단지의 시각별 최대수요(kW)** 이므로 그 「출력」의 자리가 여기다.

    ⛔⛔ **연간 부하 kWh 총량에 곱하지 마라.** `annual_load_kwh` ·
    `extra_appliance_load_kwh` · `household_scale()` 근처에 곱하면 **부하를
    20% 지우는 것**이고, 스무 집이 1년에 쓰는 전기의 합은 동시성과 무관하므로
    그것은 *쓰지 않은 전기를 안 쓴 것으로 만드는* 계산이다 — 결론축이
    **좋아지는 쪽으로** 틀린다.
    ⛔ **`load_profile_kwh`(부하 추종 방전용)에도 곱하지 마라** — 그것은
    kW 가 아니라 **에너지**이고, 곱하면 같은 부하가 계산 안에서 두 크기를
    갖는다(방전량은 줄고 계통 수전량은 안 줄어 잔차가 어디로도 가지 않는다).
    ⛔ **태양광 용량 역산에도 걸지 않는다** — 연간 총량 ÷ (8,760 × 이용률)
    이므로 동시성이 들어올 자리가 없다.

    ⚠ **곱하지 않은 것이 「빠뜨린 것」이 아니다.** 위 셋은 판정이 명시로
    제외한 자리이며, 다음 사람이 「일관성」을 이유로 넣으면 그 순간 결론축이
    조용히 좋아진다. ⚠ **ESS 용량(kWh) 역산에는 걸려야 하는데 그 역산 자체가
    아직 없다**(판정 §6 착수 4) — 세워지면 그 자리에 함께 태운다.

    ⚠ **배수로 받는다**(80% → `0.8`). `%` → 배수 환산은
    `core/casegrid/ledger_levels.py::_LEDGER_VARS` 한 곳에서만 한다.
    기본값을 두지 않는 이유는 `grid_purchase_price` 와 같다 — 두면 수준표에서
    이 변수를 빼도 러너가 옛 값으로 계속 계산하고 아무 예외도 나지 않는다.
    """
    if household is None:
        return None
    hours_per_step = ctx.dt / SECONDS_PER_HOUR
    return [
        -v * coincidence_factor / hours_per_step
        for v in dispatch.per_resource[household.name].electric
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
    appliance_season_shares: ApplianceSeasonShares | None = None,
    household_count: int | None = None,
    dr_shiftable_share_pct: float = 0.0,
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
    ess_discharge_allocation: ESSDischargeAllocation | str | None = None,
    pv_allocation_priority: PVAllocationPriority | str | None = None,
    ess_shares: Sequence[ESSShare] | None = None,
    baseline_arrangement: BaselineArrangement | str | None = None,
    pool_metering: PoolMeteringDeclaration | None = None,
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
    `pv_surplus_profile_kwh` 는 PV 를 먼저 디스패치해 만들고 (충전원이
    `PV_SURPLUS` 일 때만) 넘긴다 — 호출자가 줄 수 있는 값이 아니다.
    ⚠ **R64/WP-4 뒤로 그 잉여는 계절마다 하나씩 만들어진다** — 만드는 자리가
    `core/casegrid/seasonal_dispatch.py::build_and_dispatch_case` 로 옮겼고,
    돈을 매기는 배터리 한 벌은 그 계절별 잉여를 **일수로 가중 평균**한 것 위에
    선다(그 모듈 머리말 마지막 ⚠).

    ★ **`pv_allocation_priority` — 낮 전기를 「가구」·「배터리」 중 누구에게 먼저
    주는가** (판정 §1, `docs/decisions-2026-09-01-R51.md`). 같은 인자 →
    `case_values` → 모듈 상수(`PV_ALLOCATION_PRIORITY_DEFAULT`) 순서를 따르되,
    이 축의 승격·거부는 `_resolve_ess_dispatch_inputs` 가 `resolve_pv_
    allocation_priority()` 로 직접 한다 — 어느 자원 계약도 이 축을 모른다.
    배포 기본값은 **`HOUSEHOLD_FIRST`(집 우선)** 다 — R51/WP-6 이 판정 §1
    (*「지산지소 모델의 경우에는 집에서 우선 사용하는 것이 취지에 맞음」*)에
    따라 뒤집었고, 근거는 그 상수 옆 주석에 있다.

    ★ **`ess_discharge_allocation` — 하루 방전량을 방전창 안에서 어떻게 나누는가**
    (사용자 요구 5 · R64/WP-6a·6b). 같은 사슬(인자 → `case_values` → 모듈 상수
    `ESS_DISCHARGE_ALLOCATION_DEFAULT`)을 따르며, 승격·거부는 `ESS` 자신이
    한다(`ess_operating_mode`·`ess_charge_source` 와 같은 처리). 배포 기본값은
    **「부하 추종」**이다 — 그 시각의 가구 부하에 비례해 나눈다.
    ⚠ **부하를 세우지 않는 실행은 「고정 창」으로 선다** — 따라갈 수요가 없기
    때문이며, 그 떨어짐의 판정문은 `pv_allocation.resolve_ess_discharge_inputs`
    가 갖는다. ⚠⚠ **방전 「창」 자체는 운전 방법이 정하는 그대로다** — 창 밖의
    수요는 여전히 대응하지 못하며, 붙임 8 의 「방전창 밖 가구 수요」 항목이 그
    크기를 매 실행 재어 신고한다(`core/report/unreflected.py`).

    ★ **`extra_appliance_load_kwh` — 「추가 기기 비례 증가」** (판정 §5·B-2,
    `docs/decisions-2026-08-31-R48.md`). 히트펌프 등 추가 전력사용기기가
    있으면 **그 기기의 연간 소비전력량만큼 가구 부하 총량이 늘어난다** — 이
    인자가 그 증분이고, `annual_load_kwh` 에 더해 같은 `Load` 자원 하나로
    세운다(형상도 같은 대표일 형상을 쓴다). 기본값 0.0 은 *「추가 기기가
    없다」* 다.

    ★★ **R64/WP-2 가 이 인자에 배포 통로를 냈다** (사용자 요구 2). 그 전까지
    이 인자를 시험 밖에서 넘기는 코드가 **하나도 없었고** 기본값 0.0 만
    살았다. 지금은 시나리오 yaml 의 `heatpump_load_annual_kwh`·
    `ev_load_annual_kwh` 두 필드가 `core/casegrid/appliance_load.py::
    resolve_appliance_loads` 를 지나 **합계로** 여기 온다.
    ⚠ **인자를 기기별로 쪼개지 않았다** — 쪼개면 러너가 기기 목록을 알게 되고
    셋째 기기가 오는 날 시그니처가 늘어난다. 갈래는 산출물에서만 갈린다
    (`core/report/appendix_sections.py::_appliance_load_table`).
    ★★★ **`appliance_season_shares` — 그 합계가 계절마다 갈린다**
    (R64/WP-3b-1 · 사용자 요구 3 *「계절별로 냉난방수요를 차등하여 설정할 수
    있어야 함」*). 종전에는 위 합계가 `annual_load_kwh` 와 **먼저 합쳐진 뒤**
    자산이 선언한 **기본 부하의 계절 몫**으로 나뉘어, 냉난방 몫이 기본 몫과
    강제로 같았다. 이 인자를 주면 계절 `i` 의 부하 총량이
    `기본×기본몫[i] + 냉난방×냉난방몫[i]` 가 된다.
    ⛔ **`None` 이면 종전 식을 원소 하나까지 그대로 지난다** — 새 식으로 「같은
    값이 나오도록」 다시 계산하지 않는다(`core/casegrid/appliance_load.py::
    ApplianceSeasonShares` 머리말 ⛔ 절). 골든 셋이 그 동일성을 잰다.
    ⚠ 합이 1 이 아니거나 자산의 계절 달력과 이름이 다르면 **거부한다** —
    고쳐 주지 않는다.

    ⚠⚠ **여기 세워지는 것은 부하뿐이다.** 히트펌프·전기차를 **자원**으로
    세우는 것(설치비·유지보수비·편익 갈래가 함께 서는 것)은 이 인자가 하는
    일이 아니며, 부하에 편익을 붙이면 그 절감을 일으킨 자원과 이중 계상된다
    (`RC-LD-B0` · `FR-402-AC2.C`).

    ⚠ **`annual_load_kwh` 가 `None`(부하를 아예 세우지 않는 실행)이면 이
    인자는 무시된다.** 기기 소비량은 가구 부하에 **더하는 증분**이지 그
    자체로 부하를 만드는 값이 아니다 — 기저 없이 증분만 있으면 「무엇에
    비례해 늘었는가」에 답할 수 없다.

    ★★★ **`household_count` — 단지에 몇 호가 있는가** (R64/WP-1 · 착수 47ⓐ).
    `load.household.annual` 이 **kWh/호·년**(한 호당)이므로 단지 총량을
    내려면 이 수가 있어야 한다. `None` 이 **기본**이고 *「적지 않았다」*를
    뜻하며, 그때 러너는 **가구 한 호 기준**으로 돈다 — 이 인자가 생기기 전과
    원소 하나까지 같다. 정수 `n ≥ 1` 을 주면 단지 총부하가 `n` 배가 되고
    형상은 그대로다(`_household_load_if_total_given` 의 ★★ 절이 정본).

    ⚠⚠ **기본 가구 수를 두지 않는다.** 대장의 `load.household.count` 는
    `track: blocked` · `value: null` 이고 *「가정하면 안 된다」* 가 그 항목의
    `derivation_method` 다 — 여기에 수를 두면 그것이 단지 규모를 정하고,
    검토자가 보는 것은 우리가 고른 규모로 우리가 돌린 계산이 된다. 판정과
    거부는 `core/casegrid/household_scale.py::resolve_household_count` 하나가
    진다.

    ★★★ **`dr_shiftable_share_pct` — 「AI 가전」이 하루 안에서 옮기는 몫**
    (R64/WP-7 · 사용자 요구 2 의 남은 절반). *「집 전체 가전 부하 중 ○○% 는
    하루 안에서 옮길 수 있다」* 하나이며, 그 몫은 **그 계절 하루의 태양광
    잉여가 있는 시각으로** 간다(`core/casegrid/load_shift.py::
    shift_into_pv_surplus`).

    ⚠⚠ **총량은 한 kWh 도 변하지 않는다** — 옮기는 것이지 더하는 것이 아니다.
    그래서 이 인자는 **위 두 인자와 성질이 다르다**: 저 둘은 총량을 키우고
    이것은 하루의 모양만 바꾼다. 기본값 `0.0` 은 *「옮기지 않는다」* 이며 그때
    이 배선이 생기기 전과 원소 하나까지 같다.

    ⚠ **기기별 목록을 세우지 않았다.** 냉장고·세탁기의 소비량·이동 가능
    시간 자료가 대장에도 참고자료에도 없다(사용자 판정 §5). 그래서 축은
    **비율 하나**이고, 「AI 가전」을 가산 부하 항목으로 세우지 않은 사유는
    `core/casegrid/appliance_load.py` 머리말의 ⚠⚠ 절이 갖는다.

    ⚠ **새 편익 갈래를 만들지 않는다.** 절감은 사는 전기가 줄어 요금 엔진에서
    나오며, 수요반응 **정산금**(`FR-401-AC2.DemandResponse`)은 정산단가가 없어
    **미매핑 그대로**다 — 그 결손은 붙임 8 이 신고한다.

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
    `_resolve_ess_dispatch_inputs` 를 감싸는 `_dispatch_inputs_under_baseline`
    한 자리에서 하며, R64/WP-4 뒤로 그 호출은 **계절마다** 지나간다
    (`core/casegrid/seasonal_dispatch.py::build_and_dispatch_case`).
    ⓑ(`CANCEL_OUT`)는 자가소비가 Without·With 양쪽에 똑같이 있어 차액에서
    소거되므로 **종전 동작 그대로**이며, 그래서 골든 셋이 움직이지 않는다.

    ★★★ **`pool_metering` — ⓒ(`FORFEIT` · 자가용 집합자원화)의 성립 전제 선언**
    (R60/WP-3). ⓒ 는 R58 이래 `get_baseline_branch` 가 `DV-15` 로 **무조건**
    거부해 왔고 그 사유가 둘이었다: ① 계측 전제가 안 섰다 ② 대칭 항이 없다.

    ②는 **자리를 만들면 닫히는 것**이었고 이 라운드가 만들었다 — 아래
    `operating_cost_rows` 의 `_forfeited_self_consumption_rows` 이며 ⓒ 를 고른
    실행에서 **「포기한 자가소비」 비용 행**이 선다(총괄지침 제45조③ 대칭성).

    ①은 다르다 — 소유·운영권 인계와 구분 계측은 자료가 아니라 **사업 설계**이고
    저장소가 채울 수 없다. 그래서 **입력으로 요구한다**: `pool_metering` 이 그
    통로이며 `None`(= 적지 않았다)이면 **지금까지와 똑같이 `DV-15` 로 거부**되고,
    둘 중 하나만 참이어도 거부되며 **거부 문면이 어느 쪽이 빠졌는지 말한다**
    (사용자 판정 `docs/decisions-2026-09-04-R59b.md` §1 4항 — *「가정하지 말고
    물어라」*).

    ⚠⚠ **그 거부를 풀거나 0 으로 채우지 않았다.** 「평가할 수 없다」와 「0
    이다」는 다른 말이고, 0 으로 메우면 *「없는 제도 위에 편익을 쌓는」* 형태가
    된다. 거부는 **저장장치 조립·디스패치·편익·CBA 어느 것도 돌기 전에** 난다 —
    `DV-5`(`check_analysis_period`)가 *「자원이 서자마자」* 재는 것보다 이른
    자리다.

    ⚠ **ⓒ 는 지금 「포기는 세고 대가는 0인 사업」이다** — 집합자원화 대가의
    단가가 대장에서 `track: default0`(값 0)이기 때문이다
    (`docs/assumptions.yaml::benefit.pool_compensation_price`). 그 사실은
    리포트가 미반영 항목으로 드러낸다(`core/report/unreflected.py`).
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
    # ★★★ **설계 변수는 「한 호가 갖는 설비」다 — 단지 규모를 곱한다** (R65/WP-2b).
    #
    # `ledger_levels.py::_DESIGN_VARS` 의 `pv_capacity_kw` base **3.0** ·
    # `ess_capacity_kwh` base **10.0** 은 **한 호 규모**이고 그 모듈과
    # `household_scale.py`·`appliance_load.py` 가 셋 다 그렇게 적어 두었다.
    #
    # ⚠⚠ **부하와 설비가 같은 배수를 쓰지 않으면 두 절이 다른 사업을 그린다.**
    # 부하 쪽은 `core/casegrid/seasonal_dispatch.py:789` 의
    # `(annual_load_kwh + extra_appliance_load_kwh) * household_scale(household_count)`
    # 이며 **여기가 그것과 같은 함수를 부르는 자리**다. 곱하지 않으면 20호 단지가
    # 부하만 20배가 되고 설비는 1호분이라 낮에도 태양광 잉여가 0 이 되고, 잉여로
    # 충전하는 ESS 가 `DV` 로 실행을 **거부**한다(R65/WP-2 실측: 기기 부하까지
    # 얹으면 **2호부터** 거부되고, 20호가 성립하려면 태양광이 약 32.8 kW 여야 했다).
    # R64 가 `_Sweeper` 에서 고친 어긋남과 **같은 형태**다.
    #
    # ⚠ **`household_count or 1` 을 적지 않는다** — 그 표현은 `0` 도 조용히 `1` 로
    # 바꾼다. `household_scale()` 이 그 함정을 막으려고 있는 함수다.
    # ⚠ **`capex` 는 곱하지 않는다** — 단가(원/kW·원/kWh)이고 총액은 자원 안에서
    # `용량 × 단가` 로 나온다(`seasonal_dispatch.py` 의 `unit_capex_won_per_kw` ·
    # `capex_unit_won_per_kwh`). 여기서 함께 곱하면 **두 번 곱해진다.**
    # ⚠ **미지정(`None`)이면 배수가 `1`** 이라 이 곱이 생기기 전과 원소 하나까지 같다.
    #
    # ⚠⚠ **설비는 셋이고 곱하는 자리도 둘이다** (R65/WP-2c). 여기서 곱하는 것은
    # 용량 둘뿐이며, 셋째인 **ESS 정격출력**은 `_resolve` 를 지나지 않는다 —
    # 설계 변수가 아니라 `core/casegrid/ess_build.py::ESS_POWER_KW`(한 호분
    # 5 kW) 모듈 상수이기 때문이다. 그것은 **같은 배수**를
    # `core/casegrid/seasonal_dispatch.py::_ESSSpec` 이 날라 곱한다(그 자리의
    # ★★★ 주석이 왜 여기가 아닌지를 갖는다). ⛔ **셋 중 하나만 배수를 안 타면
    # 같은 실행 안에서 설비가 서로 다른 규모의 사업을 그린다** — WP-2b 가
    # 용량 둘만 곱했을 때 실행이 `ess.power_kw` 로 거부된 것이 그 증상이다.
    scale = household_scale(household_count)
    pv_capacity_kw = scale * _resolve(
        case_values.get("pv_capacity_kw", "base"), "pv_capacity_kw", level_map
    )
    ess_capacity_kwh = scale * _resolve(
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
    # ★★★ **R66/WP-2 가 PCS 둘을 더했다** (`capex.ess.pcs_power` ·
    # `capex.ess.pcs_share_of_system` · 사용자 판정 ③). 같은 이유로 새 statement 를
    # 만들지 않고 이 대입에 얹는다 — 여섯 다 `_resolve()` 스칼라 조회다.
    # ⚠ **여기서 곱하거나 빼지 않는다.** 배터리 단가에서 몫을 빼는 것도, 몫을
    # 정격출력에 곱하는 것도 `core/casegrid/ess_build.py::_case_ess_spec` 이 한다 —
    # 그 자리가 정격출력의 정본(`ESS_POWER_KW` × 단지 배수)을 아는 유일한 곳이고,
    # 여기서 지으면 그 정본이 둘이 된다(`pv_inverter_share` 를 여기서 단가로
    # 짓는 것과 **갈리는 판단**이며, 갈리는 사유가 그 「출력을 알아야 한다」다).
    demand_charge, pv_fixed_om, ess_fixed_om, ess_replacement_price = (
        _resolve(case_values.get("demand_charge", "base"), "demand_charge", level_map),
        _resolve(case_values.get("pv_fixed_om", "base"), "pv_fixed_om", level_map),
        _resolve(case_values.get("ess_fixed_om", "base"), "ess_fixed_om", level_map),
        _resolve(case_values.get("ess_replacement", "base"), "ess_replacement", level_map),
    )
    # ★★★ **R66/WP-5 가 동시율을 이 대입에 얹었다** (`design.coincidence_factor` ·
    # 사용자 지시 · 판정 §3). 새 statement 를 만들지 않는 이유는 위 넷과 같다 —
    # `PLR0915`(이 함수의 statement 상한 50) 여유가 0 이고, 셋 다 `_resolve()`
    # 스칼라 조회다. ⚠ **여기서 곱하지 않는다** — 곱하는 자리는
    # `_site_load_kw` 하나이며 그 독스트링이 *어디에 곱하면 안 되는가*를 갖는다.
    # ★★★ **R67/WP-N2 가 태양광 이용률을 이 대입에 얹었다**
    # (`capacity_factor.pv_rooftop` · 사용자 판정 R67 §2). 종전에는
    # `PV_CAPACITY_FACTOR = 0.15` 모듈 상수였다 — 새 statement 를 만들지 않는
    # 이유는 위 셋과 같고(`PLR0915` 여유가 0 이다), 넷 다 `_resolve()` 스칼라
    # 조회다. ⚠ **여기서 곱하거나 뒤집지 않는다** — 발전량은 `PV(...)` 가
    # 곱하고, 자립 역산의 **역수**는 `core/report/sizing.py` 가 짓는다.
    # ★★★ **R69/WP-2 가 전기요금 인상률을 이 대입에 얹었다**
    # (`escalation.electricity_tariff` · 케이스 축 `tariff_escalation` ·
    # 오케스트레이터 판정 `.orch/R69/WP-2-fix.md` ①·②). 새 statement 를 만들지
    # 않는 이유는 위 넷과 같고(`PLR0915` 여유가 0 이다), 다섯 다 `_resolve()`
    # 스칼라 조회다. ⚠ **여기서 곱하지 않는다** — 계수를 곱하는 자리는 아래
    # 둘(전력 구매 비용 행 · 편익 일정표)이고, **계수를 짓는 식**은
    # `core/cba/proforma.py::escalation_factor()` **하나**다.
    #
    # ⚠⚠ **이 축은 R69/WP-2 전까지 러너에 소비자가 0곳이었다** — 수준표와
    # 케이스 그리드(`grid.py` 의 빠른·전체 탐색 프리셋)에는 서 있는데 읽는
    # 자리가 없어 결론축이 **0원** 움직였고, 「미반영 항목」 표가 그것을
    # 신고하고 있었다(`tests/report/test_ledger_axes_wired.py::DEAD_AXES`).
    ess_pcs_capex, ess_pcs_share, coincidence_factor, pv_capacity_factor, tariff_escalation = (
        _resolve(case_values.get("ess_pcs_unit_cost", "base"), "ess_pcs_unit_cost", level_map),
        _resolve(case_values.get("ess_pcs_share", "base"), "ess_pcs_share", level_map),
        _resolve(case_values.get("coincidence_factor", "base"), "coincidence_factor", level_map),
        _resolve(case_values.get("pv_capacity_factor", "base"), "pv_capacity_factor", level_map),
        _resolve(case_values.get("tariff_escalation", "base"), "tariff_escalation", level_map),
    )

    # 1·2. Resources & Dispatch — ★★★ **계절 넷의 대표일을 각각 돌려 합산한다**
    # (R64/WP-4 · 착수 36ⓐ). 조립과 운전 전문은 `core/casegrid/seasonal_
    # dispatch.py` 가 갖는다 — 갈라낸 이유는 그 모듈 머리말에 있다(이 파일이
    # `NFR-206` 코드 줄 상한에 499/500 으로 닿아 있었고 이 함수의 `PLR0915`
    # 문장 상한도 꽉 차 있었다. `pv_allocation.py`·`ess_build.py` 와 같은 사유다).
    #
    # ⚠ **여기서 돌아오는 `dispatch` 는 「연간등가 하루」다** — 계절마다 돌린
    # 하루를 **계절일수로 가중 평균**한 것이며, 아래 연간화 규약(`_annualise`
    # 의 ×365 · `daily_grid_import_kwh × DAYS_PER_YEAR`)을 **한 줄도 고치지
    # 않고** 그대로 쓰면 `Σ_계절 (계절 하루 × 계절일수)` 와 같아진다. 그
    # 항등식과 「합산을 금액이 아니라 운전에서 하는」 근거는 그 모듈 머리말이
    # 갖는다. ⚠⚠ **금액에서 합치면 첨두 절감이 계절 수만큼 곱해진다.**
    #
    # ⚠ 분석기간 상한(`DV-5`)·기준선 갈래(`FR-705-AC2`)·ⓒ 계측 선언(`DV-15`)의
    # 거부는 그 모듈 안에서 **편익·프로포마·CBA 어느 것도 돌기 전에** 난다.
    engine = RuleBasedEngine()
    run = build_and_dispatch_case(
        engine=engine, daily_shapes=daily_shapes, case_values=case_values,
        horizon_years=horizon_years,
        steps_per_day=STEPS_PER_DAY, seconds_per_hour=SECONDS_PER_HOUR,
        pv_capacity_kw=pv_capacity_kw, pv_capacity_factor=pv_capacity_factor,
        pv_capex=pv_capex, pv_inverter_share=pv_inverter_share,
        pv_fixed_om=pv_fixed_om, pv_self_consumption_ratio=PV_SELF_CONSUMPTION_RATIO,
        price_escalation_rate=PRICE_ESCALATION_RATE,
        replacement_escalation_rate=replacement_escalation_rate,
        annual_load_kwh=annual_load_kwh,
        extra_appliance_load_kwh=extra_appliance_load_kwh,
        appliance_shares=appliance_season_shares,
        household_count=household_count,
        dr_shiftable_share_pct=dr_shiftable_share_pct,
        ess_shares=ess_shares, ess_capacity_kwh=ess_capacity_kwh, ess_capex=ess_capex,
        ess_fixed_om=ess_fixed_om, ess_replacement_price=ess_replacement_price,
        ess_pcs_capex=ess_pcs_capex, ess_pcs_share=ess_pcs_share,
        ess_operating_mode=ess_operating_mode, ess_charge_source=ess_charge_source,
        ess_discharge_allocation=ess_discharge_allocation,
        pv_allocation_priority=pv_allocation_priority,
        baseline_arrangement=baseline_arrangement, pool_metering=pool_metering,
    )
    pv, household, ctx, dispatch = run.pv, run.household, run.ctx, run.dispatch
    ess_fleet, ess_plans, ess_whole = run.ess_fleet, run.ess_plans, run.ess_whole

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
        site_load_kw=_site_load_kw(household, dispatch, ctx, coincidence_factor),
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
    # ★★★ **요금 인상률의 편익 쪽 절반** (R69/WP-2 · 판정 ②). 요금이 오르면
    # 사 오는 전력의 값(아래 `energy_purchase_row`)만 오르는 것이 아니라
    # **회피한 기본요금**도 함께 오른다 — 첨두 절감(`PeakShaving`)은 대장
    # `tariff.hv_single_contract.demand_charge` 로 값이 매겨지고, 그것은
    # 구매 단가(`…energy_only`)와 **같은 요금표의 다른 칸**이다. 한쪽만
    # 올리면 NSPM 대칭이 깨져 사업이 한 방향으로 틀린다(`energy_purchase_row`
    # 독스트링의 그 절이 정본이고, 계수를 짓는 식은 `escalation_factor()`
    # **하나**가 갖는다).
    #
    # ⚠ **첨두 절감 몫에만 곱한다.** `annual_benefit` 에는 REC·NWAs·CP·
    # 잉여판매가 함께 들어 있고 그것들은 요금표가 정하는 값이 아니다 —
    # 전액에 곱하면 REC 단가가 전기요금 인상률로 오르게 된다.
    # ⚠ **`SurplusSale` 에는 걸지 않는다** — 그 단가는
    # `tariff.surplus_direct_sale`(잉여 직거래 · 도매 계열)이고 정산 구조가
    # 다르다(WP-2 §0·§3-④). 지금 실행에서 그 값은 역송 0kWh 라 0원이다.
    # ⚠ **1년차 계수는 `(1+r)^0 = 1.0`** 이므로 1년차 편익은 종전과 원 하나까지
    # 같다. 반올림은 `to_won()` 한 곳에서 한다(`NFR-103`).
    benefit_rows = [
        benefit_row(
            "E2EBenefit",
            {
                year: annual_benefit - peak_per_year + int(
                    to_won(peak_per_year * escalation_factor(tariff_escalation, year=year))
                )
                for year in range(1, horizon_years + 1)
            },
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
        # ★★★ **요금 인상률의 비용 쪽 절반** (R69/WP-2 · 판정 ①·②). 넘기는
        # 금액은 **1년차** 값이고 연차 계수는 행이 스스로 굴린다 — 여기서
        # 미리 곱하면 행이 연차를 모르는 채 「이미 오른 값」을 20년 깐다.
        # 편익 쪽 절반은 위 `benefit_rows` 의 첨두 절감 몫이며, 두 자리가
        # **같은 `escalation_factor()`** 를 부른다.
        energy_purchase_row(
            "GridPurchase",
            start_year=1,
            end_year=horizon_years,
            annual_amount_won=annual_purchase_won,
            escalation_rate=tariff_escalation,
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
        # ★★★ **포기한 자가소비 — ⓒ「자가용 집합자원화」의 대칭 항** (R60/WP-3 ·
        # 총괄지침 제45조③). ⓐ·ⓑ 에서는 빈 목록이라 **골든 셋이 움직이지
        # 않는다**(ⓑ 의 자가소비는 Without·With 양쪽에 있어 차액에서 소거된다).
        # 판정 근거와 물량·단가의 출처는 `_forfeited_self_consumption_rows`
        # 독스트링이 갖는다.
        *_forfeited_self_consumption_rows(
            baseline_arrangement,
            pool_metering,
            pv=pv,
            ctx=ctx,
            surplus_profile_kwh=run.pv_surplus_profile_kwh,
            price_won_per_kwh=grid_purchase_price,
            horizon_years=horizon_years,
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
        ess_pcs_capex=ess_pcs_capex, ess_pcs_share=ess_pcs_share,
        pv_capacity_factor=pv_capacity_factor,
        self_consumption_ratio=measured_self_consumption_ratio(
            pv, ctx, run.pv_surplus_profile_kwh
        ),
        pv_allocation_priority=run.pv_allocation_priority,
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
        resources=run.resources,
        dispatch=dispatch,
        # ★★★ **계절별 결과** (R64/WP-4 · 판정 ⑤ · 사용자 요구 6). 다음 WP 가
        # 계절별 수치·도표를 세울 재료이며, 여기서 안 실으면 그 WP 가 자원을
        # 다시 세워야 한다 — 그러면 인쇄된 계절과 결론이 선 계절이 갈릴 수 있다.
        # ⚠ **형상 자산이 없는 실행에서는 비어 있다**(케이스 그리드·성능 측정).
        seasons=run.seasons,
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
        # ★★ **요금 연동 갈래를 관점 표에도 알려 준다** (R69/WP-2). 사업자 열은
        # `benefit_rows`(위에서 계수를 이미 태웠다)를 그대로 쓰는데, 참여 주민
        # 열은 `annualised` 의 1년차 값으로 다시 지어지므로 여기를 안 넘기면
        # **같은 첨두 절감의 20년 합계가 표 안에서 두 수로 인쇄된다.**
        # 판정(어느 갈래가 요금 연동인가)은 여기 한 곳에 있고 관점 모듈은
        # 받기만 한다 — 그쪽에 태그를 다시 적으면 정본이 둘이 된다.
        perspectives=build_perspective_wiring(
            annualised, benefit_rows, [*operating_cost_rows, *lifecycle_rows],
            initial_investment, discount_rate, horizon_years=horizon_years,
            society_annualised=build_society_annualised(distributed_sub_items),
            escalation_by_tag={peak.tag: tariff_escalation}),
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
            # ★★★ **문면은 이 실행이 실제로 한 일을 적는다** (R64/WP-4 · 판정 ④).
            # 종전 문면(*「계절·요일 변동을 반영하지 않으므로…」*)은 계절 합산이
            # 서는 순간 거짓이 됐다. 갈래와 「요일은 여전히 미반영」의 근거는
            # `dispatch_note()` 독스트링이 갖는다 — **여기서 문장을 다시 쓰지
            # 않는다**(두 곳에 적으면 갈리고, 갈린 쪽이 산출물에 실린다).
            dispatch_note=dispatch_note(run.seasons, steps_per_day=STEPS_PER_DAY),
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


def _hours_text(hours: Sequence[int]) -> str:
    """방전창을 **연속 구간**으로 접어 적는다 — `(18, 19, 20, 21)` → `18~21시`.

    ⚠ 시각을 스물넷 다 나열하면 표 칸이 넘치고, 첫·끝만 적으면 창이 끊긴
    운전 방법에서 거짓이 된다. 그래서 **끊긴 자리마다 구간을 나눈다.**
    """
    if not hours:
        return "없음"
    spans: list[list[int]] = [[hours[0], hours[0]]]
    for hour in hours[1:]:
        if hour == spans[-1][1] + 1:
            spans[-1][1] = hour
        else:
            spans.append([hour, hour])
    return "·".join(
        f"{lo}시" if lo == hi else f"{lo}~{hi}시" for lo, hi in spans
    )


def _ess_allocation_text(ess: ESS) -> str:
    """저장장치가 이 실행에서 **실제로 적용한 방전 배분** 한 조각 (R68/WP-2).

    ⚠ **함수로 둔 이유** — 이 조각은 `ResourceLine` 의 «두» 칸이 읽는다:
    합친 `operating_mode`(붙임 6 과 골든이 보는 문면 · ⛔ 바꾸지 않는다)와
    뒷조각만 나르는 `applied_allocation`(검증 3단계의 「실제 배분」 열)이다.
    저장장치 줄은 몫마다 서는 **생성식** 안에서 만들어져 지역 변수를 둘 수
    없으므로, 같은 f-문자열을 두 번 적는 대신 여기서 한 번 짓는다.
    """
    return (
        f"방전 배분: {ess.discharge_allocation} "
        f"(방전창 {_hours_text(ess.discharge_hours)} 안)"
    )


def _resource_lines(
    pv: PV,
    pv_capex: float,
    ess_fleet: Sequence[ESS],
    ess_capex: float,
    benefits: Sequence[BenefitLine],
    *,
    #: ★ PCS 둘 — 2.1 표의 단가 칸이 **자기 취득비를 설명할 수 있어야** 한다
    #: (R66/WP-2-fix · 아래 `unit_capex` 의 ★★★ 절). ⚠ **키워드 전용이다** —
    #: 위치 인자를 늘리면 `PLR0917`(위치 인자 5개 상한)에 걸리고, 무엇보다
    #: 두 단가는 호출부에서 **이름으로 구별돼야** 서로 바뀌어도 드러난다.
    ess_pcs_capex: float,
    ess_pcs_share: float,
    #: ★★ 태양광 이용률 — **대장에서 온 값을 호출자가 넘긴다** (R67/WP-N2).
    #: ⚠⚠ **`pv.capacity_factor` 에서 읽으면 안 된다.** 이 러너는 PV 를 이용률이
    #: 아니라 **8,760 발전 시계열**로 세우므로(`core/casegrid/seasonal_dispatch.py`
    #: 가 대표일 형상을 펼친다) 그 속성은 `None` 이고, 그것을 인쇄하면 2.1 표의
    #: 이용률 칸이 **「미지정」으로 사라진다** — R67/WP-N2 가 실물로 밟았다
    #: (`.orch/R67/result_N2.md` ②). 시계열을 만든 수가 곧 이 값이다.
    pv_capacity_factor: float,
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

    # ★★ **배분 조각을 «한 번» 짓는다** (R68/WP-2). 합친 칸과 `applied_
    # allocation` 칸이 같은 지역 변수를 읽으므로 둘이 갈라질 수 없다 — 두 곳에
    # 같은 f-문자열을 적으면 한쪽만 고쳐지는 날 검증 3단계의 「실제 배분」 열이
    # 붙임 6 의 합친 칸과 다른 말을 하고, 아무 예외도 나지 않는다.
    pv_allocation_text = f"본 실행 배분: {pv_allocation_priority}"
    return (
        ResourceLine(
            name=pv.name,
            kind="태양광 (옥상 고정형)",
            # ★ **세운 자원에서 읽는다.** 모듈 상수에서 읽으면 용량 스윕이
            # 도는 동안에도 리포트가 기준 용량을 계속 인쇄한다 — 값이 바뀌어도
            # 아무 예외가 나지 않는 형태다.
            # ★★ **이용률은 대장에서 온 값을 인자로 받는다** (R67/WP-N2) —
            # 위 `pv_capacity_factor` 인자의 ⚠⚠ 가 *왜 자원에서 읽지 않는가*를
            # 갖는다(이 러너의 PV 는 시계열로 세워져 그 속성이 `None` 이다).
            # ★★ **자가소비율은 `PV_SELF_CONSUMPTION_RATIO`(모듈 상수)가 아니라
            # 본 실행의 실측치를 받는다** (판정 §4). `BATTERY_FIRST` 갈래에서만
            # 그 상수가 계속 쓰이며(`pv_allocation._resolve_ess_dispatch_inputs`
            # 독스트링), 여기 인쇄되는 값은 갈래와 무관하게 이 실행이 실제로
            # 배분한 결과다 — 「(본 실행 실측)」 문면이 그 사실을 표시한다.
            capacity=(
                f"{pv.capacity_kw:g} kW · 이용률 {pv_capacity_factor:.0%} · "
                f"자가소비율 {self_consumption_ratio:.0%} (본 실행 실측)"
            ),
            # ★★ **선언(전량 판매)과 본 실행 배분 순서를 함께 적는다** (판정
            # §4 나-4). 두 값이 서로 달라 보이는 것은 결함이 아니다 — PV 는
            # 잉여를 전량 판매로 「선언」했고, 그 잉여가 무엇인지는 `pv_
            # allocation_priority` 축이 낮 동안 따로 정한다(같은 뿌리, 판정
            # §4 ⚠). 배분 순서는 실행이 실제로 고른 값(`resolved_pv_allocation_
            # priority`)에서 읽는다 — 지어내지 않는다.
            operating_mode=f"{pv.operating_mode} (선언) · {pv_allocation_text}",
            # ★ 위 합친 칸의 **뒷조각만** — 검증 3단계가 파싱 없이 「선언」과
            # 「실제 배분」을 두 열로 가른다(`ResourceLine.applied_allocation`).
            applied_allocation=pv_allocation_text,
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
                # ★★ **방전 배분을 함께 적는다** (R64/WP-6b · 사용자 요구 5).
                # ⚠ **모듈 상수(`ESS_DISCHARGE_ALLOCATION_DEFAULT`)를 다시 읽어
                # 재현하지 않는다** — 세운 자원이 실제로 든 값을 읽는다. 상수를
                # 읽으면 부하를 세우지 않는 실행(그 실행은 「고정 창」으로 선다)
                # 에서도 「부하 추종」이 인쇄되고, 그 거짓은 아무 예외도 내지
                # 않는다. 위 `capacity` 칸의 ★ 와 같은 판단이다.
                # ⚠⚠ **방전창을 함께 적는다** — 「부하 추종」만 적으면 *하루
                # 종일 수요를 따라간다* 로 읽힌다. 실제로는 운전 방법이 정한
                # 창 **안에서만** 나눈다(창을 부하로 정하면 충전 계획과
                # 순환한다 — `ess_schedule.pv_surplus_charge_kwh_by_hour`).
                # 창 밖 수요의 크기는 붙임 8 이 재어 신고한다.
                operating_mode=f"{ess.operating_mode} · {_ess_allocation_text(ess)}",
                # ★ 위 합친 칸의 **뒷조각만** — 검증 3단계가 파싱 없이 「선언」과
                # 「실제 배분」을 두 열로 가른다. 같은 함수를 읽으므로 두 칸이
                # 갈라질 수 없다(`_ess_allocation_text` 독스트링의 ⚠).
                applied_allocation=_ess_allocation_text(ess),
                lifetime_years=int(ess.lifetime),
                # ★★★ **두 축을 함께 인쇄한다** (R66/WP-2-fix). R66/WP-2 가
                # 초기투자에 `PCS 단가 × 정격출력` 항을 세우면서 이 칸이
                # **자기 행의 취득비를 설명하지 못하게 됐다** — 실측으로
                # `500,000원/kWh` 를 인쇄하는데 같은 행의 취득비는
                # 105,000,000원이었다(500,000 × 200 kWh = 100,000,000 ≠ 그 수).
                # 즉 심의자가 표에 적힌 단가·용량으로 초기투자를 되짓지 못했다.
                # ⚠ **대장의 시스템 단가를 그대로 적을 수 없다** — 배터리에
                # 실제로 곱해지는 것은 `시스템 단가 × (1 − PCS 몫)` 이다
                # (`core/casegrid/ess_build.py::_case_ess_spec`).
                # ⚠⚠ **자원에서 되읽지 않는다** — `ESS` 는 두 단가를 비공개
                # 속성으로만 갖고(`_capex_unit`·`_capex_pcs_per_kw`) 그 파일은
                # 코드 498/500 이라 접근자를 세울 자리가 없다. 그래서 러너가
                # **같은 값을 같은 자리에서** 받아 넘긴다 — 위 `capacity` 칸의
                # ★ 가 경계한 「모듈 상수에서 다시 읽는」 형태와는 다르다.
                unit_capex=(
                    f"{ess_capex * (1.0 - ess_pcs_share):,.0f}원/kWh (배터리) + "
                    f"{ess_pcs_capex:,.0f}원/kW (PCS)"
                ),
                capex_won=int(ess.capex(year=1)),
                fixed_om_won_per_year=int(ess.fixed_om(year=1)),
                produces=produced_by("ESS"),
                policy_warnings=tuple(ess.policy_warnings()),
            )
            for ess in ess_fleet
        ),
    )
