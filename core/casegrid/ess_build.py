"""ESS 조립 — `core/casegrid/e2e_runner.py` 에서 R57/WP-5 가 옮겼다.

`pv_allocation.py`·`grid_support.py` 와 **같은 사유로 뗀 것이다.** 그 파일이
`NFR-206` 코드 줄 상한(500)에 닿아 있었다 — 옮기기 직전 실측이 **코드
497/500**, 곧 **여유 3줄**이었다. ★분할(한 대의 ESS 를 몫으로 갈라 몫마다
다른 역할을 주는 축)의 러너 배선을 넣을 자리가 **물리적으로 없었다.**

**행동은 한 원도 바뀌지 않았다.** ESS 제원 상수 여덟과 `ESS(...)` 호출
전문을 주석째로 옮겼을 뿐이며, 같은 인자로 같은 자원이 선다. 그것을 재는
것은 골든 3건(`tests/golden/test_regression_scenarios.py`)의 `npv_won`
정확 일치다.

⚠ **결정은 오지 않았다.** 운전 방법·충전원·PV 잉여 프로파일은
`core/casegrid/pv_allocation.py::_resolve_ess_dispatch_inputs` 가 **이미
해석해 둔 값**으로 받고, 용량·단가·고정 O&M·교체 단가·에스컬레이션은 대장에서
온 값으로 받는다. 이 모듈은 **인자를 받아 자원을 돌려줄 뿐**이다 — 해석을
여기로 끌어오면 「자리 옮김」이 아니게 되고, 골든이 움직였을 때 원인이 둘이
된다.

⚠ **`PV(...)` 는 함께 오지 않았다.** 이 WP 의 범위는 `ESS` 뿐이다. 둘을 함께
옮기면 결론축이 움직였을 때 어느 쪽 때문인지 가릴 수 없다.

⚠ **재수출로 때우지 않았다.** `e2e_runner.py` 는 **자기가 실제로 쓰는
이름만** import 한다 — `_resource_lines()` 가 2.1 표에 인쇄하는 다섯
(`ESS_RTE_PCT`·`ESS_SOC_MIN_PCT`·`ESS_SOC_MAX_PCT`·`ESS_EOL_SOH_PCT`·
`ESS_CYCLES_PER_YEAR`)과 `build_case_ess` 다. 여덟을 전부 다시 내보내면 옛
문면은 참인 채로 남지만 그 import 줄들이 코드 줄이라 **얻으려던 여유를 도로
까먹는다.**
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from core.der.ess import ESS, ESSChargeSource, ESSOperatingMode

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
#: ⚠ **고정 O&M 은 여기 없다** — `ESS_FIXED_OM_WON_PER_YEAR` 모듈 상수를
#: R51/WP-2 가 지웠다. 대장 `opex.ess.fixed_om` 에서 `level_map` 으로 온다
#: (사용자 판정 §2) — `opex.pv.fixed_om` 과 같은 이유다.


def build_case_ess(
    *,
    capacity_kwh: float,
    operating_mode: ESSOperatingMode | str,
    charge_source: ESSChargeSource | str,
    pv_surplus_profile_kwh: Sequence[float] | None,
    capex_unit_won_per_kwh: float,
    fixed_om_won_per_year: float,
    replacement_unit_won_per_kwh: float,
    escalation_rate: float,
    replacement_escalation_rate: float,
) -> ESS:
    """이 사업 모델의 ESS 한 대를 세운다 — 위 제원 상수 여덟 + 받은 인자.

    ⚠ **받은 값을 다시 판단하지 않는다.** 운전 방법·충전원·PV 잉여
    프로파일은 `core/casegrid/pv_allocation.py::_resolve_ess_dispatch_inputs`
    가 이미 고른 값이고, 나머지는 대장에서 온 값이다. 여기서 한 번 더
    해석하면 두 벌이 되어 어긋난다(`grid_support.py::_resolve_nwas_cp` 가
    적은 「세운 자원에서 읽는다」와 같은 원칙의 뒷면이다).
    """
    return ESS(
        name="e2e-ess",
        capacity_kwh=capacity_kwh,
        power_kw=ESS_POWER_KW,
        rte_pct=ESS_RTE_PCT,
        soc_min_pct=ESS_SOC_MIN_PCT,
        soc_max_pct=ESS_SOC_MAX_PCT,
        cycle_life=ESS_CYCLE_LIFE,
        calendar_life=ESS_CALENDAR_LIFE,
        eol_soh_pct=ESS_EOL_SOH_PCT,
        cycles_per_year=ESS_CYCLES_PER_YEAR,
        # `ESS.__init__` 의 `operating_mode` 타입은 `ESSOperatingMode` 뿐이다
        # (문자열도 실제로 받는다 — `DER._check_operating_mode` 가 검증한다).
        # 이 `cast` 는 그 사실의 타입 단정이지 런타임 변환이 아니다.
        operating_mode=cast(ESSOperatingMode, operating_mode),
        charge_source=charge_source,
        # PV_SURPLUS 가 아닌 충전원에 시계열을 주면 `ESS` 가 거부한다(판정
        # A-3) — 그래서 충전원이 PV_SURPLUS 일 때만 건넨다. **문자열도 비교
        # 가능하다** — `ESSChargeSource` 는 `StrEnum` 이라 값이 같은 평문
        # 문자열과도 `==` 가 성립한다. 잘못된 값이면 이 비교는 그냥 거짓이
        # 되고, 실제 거부는 `ESS` 생성자(`_coerce_charge_source`)가 한다 —
        # 여기서 미리 변환을 시도하면 그 에러 메시지를 이 자리가 가로챈다.
        pv_surplus_profile_kwh=(
            pv_surplus_profile_kwh
            if charge_source == ESSChargeSource.PV_SURPLUS
            else None
        ),
        capex_unit_won_per_kwh=capex_unit_won_per_kwh,
        fixed_om_won_per_year=fixed_om_won_per_year,
        # ★★ **명목 기준을 ESS 에도 물린다 (R39-E · R38 판정 ②나).** 이 인자가
        # 없는 동안 세운 ESS 의 `DER.escalation_factor()` 는 1.0 이었고 — 옮겨
        # 오기 전 이 주석은 러너의 지역 변수 이름(ess)을 수신자로 적었으나 이
        # 모듈에는 그 변수가 없어 문면 검사가 그것을 `core/der/ess.py` 모듈로
        # 읽는다(「왼쪽이 객체인 점 표기」 규약). **수신자 표기만 선언 자리로
        # 바꿨고 뜻은 그대로다: 세운 자원의 물가 계수다.** 그래서 18년차
        # 배터리 교체비가 **오늘의 원**으로 적혔다 — 대장이 `price_basis:
        # "명목"` 을 선언한 사업에서 그 지출만 실질이 된다.
        #
        # ★ **교체 단가가 이제 대장에서 온다** (`capex.ess.replacement` ·
        # 사용자 판정 §7 · R52/WP-6). 종전에는 이 인자를 넘기지 않아 `ess.py`
        # 가 취득 단가(`capex.ess.new`)를 그대로 교체 단가로 썼다 — 값은
        # **여전히 같다**(조사가 크기 근거를 못 찾았다, WP-5 §7) 지만 통로가
        # 이제 따로 있다 — 「배터리만/시스템 전체」(`Q-2`)가 값 하나만 바꾸는
        # 물음이라면 이 자리를 고치면 된다.
        replacement_unit_won_per_kwh=replacement_unit_won_per_kwh,
        escalation_rate=escalation_rate,
        replacement_escalation_rate=replacement_escalation_rate,
    )
