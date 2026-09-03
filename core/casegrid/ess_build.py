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

## ★ R57/WP-6 이 여기에 **몫 분기의 몸통**을 넣었다

`build_case_ess_fleet`(자원 전건·몫 계획·물리 자원)과 `build_fleet_streams`
(ESS 가 만드는 편익)이 그것이다. 러너에 넣지 않은 이유는 위와 같다 — 그
파일은 코드 줄 여유 18줄이고 `PLR0915` statement 여유는 **0** 이다. 러너가
하는 일은 **받아서 자리에 꽂는 것**뿐이며, 몫을 주지 않으면 지금까지와 같은
`ESS` 하나가 서고 같은 편익이 조립된다(골든 3건이 그것을 잰다).

⚠ **재수출로 때우지 않았다.** `e2e_runner.py` 는 **자기가 실제로 쓰는
이름만** import 한다 — `_resource_lines()` 가 2.1 표에 인쇄하는 다섯
(`ESS_RTE_PCT`·`ESS_SOC_MIN_PCT`·`ESS_SOC_MAX_PCT`·`ESS_EOL_SOH_PCT`·
`ESS_CYCLES_PER_YEAR`)과 `build_case_ess` 다. 여덟을 전부 다시 내보내면 옛
문면은 참인 채로 남지만 그 import 줄들이 코드 줄이라 **얻으려던 여유를 도로
까먹는다.**
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from core.casegrid.ess_share import ESSShare, ESSSharePlan, split_ess
from core.casegrid.ess_share_benefits import ShareBenefitContext, build_share_benefits
from core.casegrid.grid_support import _resolve_nwas_cp, peak_shaving_enabled
from core.contracts.validation import ValidationError
from core.contracts.valuestream import ValueStream
from core.der.ess import ESS, ESSChargeSource, ESSOperatingMode
from core.valuestream import PeakShaving, TouArbitrage

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


def _case_ess_spec(
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
) -> dict[str, Any]:
    """이 사업 모델의 ESS **제원 한 벌** — 위 제원 상수 여덟 + 받은 인자.

    ★★ **제원을 한 자리에서만 적는다 (R57/WP-6).** `build_case_ess` 는 이것을
    `ESS(**spec)` 로 세우고, `build_case_ess_fleet` 은 **같은 묶음**을
    `core/casegrid/ess_share.py::split_ess` 에 넘긴다 — 그 함수가 인스턴스가
    아니라 제원 `Mapping` 을 받는 사유는 그 독스트링이 갖는다. **두 벌로
    적으면 몫 경로와 단일 경로가 서로 다른 배터리를 세우고**, 그 어긋남은
    용량·정격출력·고정 O&M 을 전부 갈라 놓으면서 아무 예외도 내지 않는다.

    ⚠ **받은 값을 다시 판단하지 않는다.** 운전 방법·충전원·PV 잉여
    프로파일은 `core/casegrid/pv_allocation.py::_resolve_ess_dispatch_inputs`
    가 이미 고른 값이고, 나머지는 대장에서 온 값이다. 여기서 한 번 더
    해석하면 두 벌이 되어 어긋난다(`grid_support.py::_resolve_nwas_cp` 가
    적은 「세운 자원에서 읽는다」와 같은 원칙의 뒷면이다).
    """
    return dict(
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
    """이 사업 모델의 ESS **한 대**를 세운다 — `_case_ess_spec` 그대로다.

    ⚠ **제원을 여기 다시 적지 않는다**(위 함수의 ★★). 이 함수가 남아 있는
    이유는 밖에서 이 이름으로 부르기 때문이며(`tests/`), 러너는 이제
    `build_case_ess_fleet` 을 부른다.
    """
    return ESS(**_case_ess_spec(
        capacity_kwh=capacity_kwh,
        operating_mode=operating_mode,
        charge_source=charge_source,
        pv_surplus_profile_kwh=pv_surplus_profile_kwh,
        capex_unit_won_per_kwh=capex_unit_won_per_kwh,
        fixed_om_won_per_year=fixed_om_won_per_year,
        replacement_unit_won_per_kwh=replacement_unit_won_per_kwh,
        escalation_rate=escalation_rate,
        replacement_escalation_rate=replacement_escalation_rate,
    ))


def build_case_ess_fleet(
    *,
    shares: Sequence[ESSShare] | None,
    capacity_kwh: float,
    operating_mode: ESSOperatingMode | str,
    charge_source: ESSChargeSource | str,
    pv_surplus_profile_kwh: Sequence[float] | None,
    capex_unit_won_per_kwh: float,
    fixed_om_won_per_year: float,
    replacement_unit_won_per_kwh: float,
    escalation_rate: float,
    replacement_escalation_rate: float,
) -> tuple[tuple[ESS, ...], tuple[ESSSharePlan, ...], ESS]:
    """★★★ **몫 분기의 몸통** — 러너는 이 함수의 결과를 받기만 한다 (R57/WP-6).

    분기를 `core/casegrid/e2e_runner.py` 에 넣지 않는 이유는 그 파일이
    `NFR-206` 코드 줄 상한(500)에 **여유 18줄**로 닿아 있고 `PLR0915` statement
    상한 50 에는 **여유 0** 이기 때문이다(둘 다 실측이다).

    돌려주는 셋:

    ① **자원 목록** — 디스패치·수명·비용·자원 표에 실을 **전건**이다. 하나만
       실으면 나머지 몫이 방전하지 않고, 그 몫의 취득비·고정 O&M 도 사라진다.
    ② **몫 계획 목록** — `ESSSharePlan` 전건이며 몫이 없으면 빈 튜플이다.
       표찰을 편익에 실으려면 선언과 자원이 **묶인 채로** 가야 한다.
    ③ **물리 자원 하나** — 가르기 전의 배터리다. 교체비·잔존가치는 물리 배터리
       **한 대의 사건**이며(한 대를 가른 것이지 여러 대를 산 것이 아니다), 그
       행을 짓는 `core/casegrid/lifecycle.py::lifecycle_rows` 도 자원 하나만
       받는다.

    ★ ②가 「몫 **편익** 목록」이 아닌 이유는 `build_fleet_streams` 의 독스트링이
    갖는다 — 편익은 디스패치 뒤에야 지을 수 있다.

    ⚠ **`None` 이 「가르지 않는다」이고 그것이 기본이다.** 빈 시퀀스를 그렇게
    읽지 않는다 — `split_ess` 가 *「몫이 하나도 없습니다」* 로 거부하며 그
    거부가 옳다(빈 목록을 넘긴 것은 실수다).

    ⚠ 몫이 없으면 ①의 유일한 원소가 ③과 **같은 객체**다. 사본을 하나 더 세우면
    디스패치한 배터리와 비용을 문 배터리가 갈릴 수 있다.
    """
    spec = _case_ess_spec(
        capacity_kwh=capacity_kwh,
        operating_mode=operating_mode,
        charge_source=charge_source,
        pv_surplus_profile_kwh=pv_surplus_profile_kwh,
        capex_unit_won_per_kwh=capex_unit_won_per_kwh,
        fixed_om_won_per_year=fixed_om_won_per_year,
        replacement_unit_won_per_kwh=replacement_unit_won_per_kwh,
        escalation_rate=escalation_rate,
        replacement_escalation_rate=replacement_escalation_rate,
    )
    whole = ESS(**spec)
    if shares is None:
        return (whole,), (), whole
    plans = split_ess(spec, shares)
    return tuple(plan.resource for plan in plans), plans, whole


def _reject_tou_arbitrage(plans: Sequence[ESSSharePlan]) -> None:
    """★★ **「TOU 차익거래」 몫은 이 통로로 편익이 되지 않는다 — 단가가 없다.**

    `core/casegrid/ess_share_benefits.py::ShareBenefitContext` 는 첨두·경부하
    **에너지 단가 둘**을 요구하는데, 그 둘은 `docs/assumptions.yaml` 에도
    `core/casegrid/ledger_levels.py` 에도 `core/casegrid/e2e_runner.py` 에도
    **없다**(실측 — 세 파일에서 `peak_price`·`offpeak` 를 찾으면 0건이다).
    러너가 들고 있는 단가는 계통 구매 한계단가와 잉여 판매단가이며 **둘 다
    시간대 단가가 아니다.**

    ⚠ **0 으로 채우지 않는다.** 채우면 「제도가 없어서 0원」
    (`docs/assumptions.yaml` · `track: default0`)과 **「단가를 못 찾아서 0원」**
    이 같은 모양이 된다 — 이 저장소가 반복해 경계해 온 형태다. 그래서 그
    갈래를 **여기서 먼저 닫는다**: 아래 `build_fleet_streams` 가 그 둘에
    넘기는 0.0 은 **도달 불가능한 자리**이며, 0 을 값으로 쓰는 것이 아니라
    0 이 쓰이는 갈래가 없다는 뜻이다.

    ⚠ 태그는 `TouArbitrage.tag` 에서 읽는다 — 문자열을 여기 적으면 사본이 된다.
    태그 목록은 몫 자원에게 묻는다(`ESS.value_streams()` 가 정본이다).
    """
    named = [
        plan.share.name
        for plan in plans
        if TouArbitrage.tag in plan.resource.value_streams()
    ]
    if not named:
        return
    raise ValidationError(
        field="ess_build.TouArbitrage",
        reason=(
            f"몫 「{', '.join(named)}」이 「TOU 차익거래」를 역할로 골랐는데 그 "
            "편익의 첨두·경부하 에너지 단가가 이 저장소에 없습니다 — 대장·수준표·"
            "러너 어디에도 그 두 단가가 없어 금액을 지을 수 없습니다"
        ),
        action=(
            "먼저 `docs/assumptions.yaml` 에 시간대별 에너지 단가(첨두·경부하)를 "
            "근거와 함께 세우고 `core/casegrid/ledger_levels.py` 로 러너까지 나른 "
            "뒤에 이 역할을 쓰십시오. 지금 0원으로 채우면 「제도가 없어서 0원」과 "
            "「단가를 못 찾아서 0원」이 구별되지 않습니다 — 이 몫에 다른 역할을 "
            "주거나 몫을 가르지 마십시오"
        ),
    )


def build_fleet_streams(
    fleet: Sequence[ESS],
    plans: Sequence[ESSSharePlan],
    *,
    nwas_price_won_per_kwh: float,
    cp_price_won_per_kw_month: float,
    demand_charge_won_per_kw_month: float,
    site_load_kw: Sequence[float] | None,
) -> tuple[tuple[ValueStream, ...], ValueStream]:
    """★★★ **ESS 가 만드는 편익** — 몫이 있으면 몫 편익이 **대체한다** (R57/WP-6).

    돌려주는 둘은 러너의 자리 둘에 그대로 들어간다 — `settlement_streams` 안에
    `*` 로 풀어 넣을 묶음과, 연간화 목록의 **마지막**에 서는 첨두 절감 하나다
    (`tests/casegrid/test_nwas_cp_wiring.py` 의 ③ 이 그 자리를 붙든다).

    ## 왜 「자원 목록 + 몫 편익 목록」을 한 번에 못 돌려주는가

    `ShareBenefitContext.site_load_kw` 는 `core/casegrid/e2e_runner.py::
    _site_load_kw` 가 **디스패치 결과에서** 만든다. 디스패치는 자원이 서야
    돌고, 그래서 **자원(`build_case_ess_fleet`)과 편익(이 함수)은 같은 호출에
    들어갈 수 없다.** 부하 시계열을 여기서 다시 지으면 두 벌이 된다.

    ## ⚠⚠ 몫이 있으면 단일 경로의 셋을 짓지 않는다

    지금까지 러너는 `ESS` 하나에서 `PeakShaving` 과 `NWAs`·`CP` 를 지었다.
    **몫이 그 역할을 가져갔으므로 함께 지으면 같은 편익이 두 번 선다** —
    `FR-402-AC1` 이 정의한 중복이고, 배타 판정은 **같은 태그 쌍을 규칙표에서
    찾지 못하므로 막지도 못한다.** `SurplusSale`·`REC` 등 ESS 와 무관한
    편익은 러너가 그대로 둔다 — 몫은 배터리를 가른 것이지 태양광을 가른
    것이 아니다.

    ## 첨두 절감이 왜 따로 나가는가

    `core/casegrid/operating_lines.py::benefit_lines` 가 첨두 절감을 **인자
    하나로** 받아 자원 귀속을 「ESS」로 적는다. 그래서 몫 경로에서도 그 자리에
    **하나**가 서야 하고, 몫 편익 중 `PeakShaving` 이 있으면 **그것이** 그
    자리에 선다(표찰을 든 채로다). 없으면 0kW·꺼짐인 자리지기가 서는데,
    그것은 방식 「나」에서 이미 나던 모양과 같다(`peak_shaving_enabled` 가
    거짓일 때의 0원 행) — 「꺼져서 0원」이지 「빠져서 없음」이 아니다.
    """
    if not plans:
        return (
            _resolve_nwas_cp(
                fleet[0], nwas_price_won_per_kwh, cp_price_won_per_kw_month
            ),
            PeakShaving(
                monthly_peak_reduction_kw=[
                    fleet[0].reducible_peak_kw(year=1, site_load_kw=site_load_kw)
                ] * PeakShaving.MONTHS,
                demand_charge_won_per_kw_month=demand_charge_won_per_kw_month,
                # ★ 방식 「나」(배전망 사업자 지시)에서는 애초에 만들지 않는다
                # (사용자 판정 §1, `docs/decisions-2026-09-02-R54.md`). 술어는
                # `core/casegrid/grid_support.py::peak_shaving_enabled`.
                enabled=peak_shaving_enabled(fleet[0]),
            ),
        )
    _reject_tou_arbitrage(plans)
    benefits = tuple(
        build_share_benefits(
            plan,
            ShareBenefitContext(
                # ⚠ 이 둘은 **도달 불가능한 자리**다 — 위 `_reject_tou_arbitrage`
                # 가 그 둘을 쓰는 유일한 편익을 먼저 거부한다. 0 을 값으로
                # 쓰는 것이 아니라 0 이 쓰이는 갈래를 닫은 것이다.
                peak_price_won_per_kwh=0.0,
                offpeak_price_won_per_kwh=0.0,
                demand_charge_won_per_kw_month=demand_charge_won_per_kw_month,
                nwas_price_won_per_kwh=nwas_price_won_per_kwh,
                cp_price_won_per_kw_month=cp_price_won_per_kw_month,
                site_load_kw=site_load_kw,
            ),
        )
        for plan in plans
    )
    at = next(
        (i for i, b in enumerate(benefits) if isinstance(b, PeakShaving)), -1
    )
    return (
        tuple(b for i, b in enumerate(benefits) if i != at),
        benefits[at] if at >= 0 else PeakShaving(
            monthly_peak_reduction_kw=[0.0] * PeakShaving.MONTHS,
            demand_charge_won_per_kw_month=demand_charge_won_per_kw_month,
            enabled=False,
        ),
    )
