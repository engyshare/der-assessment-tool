"""`ESS` 조립이 옮겨 온 자리 — `NFR-206-M1` · `FR-102-AC1.ESS` / R57/WP-5.

R57/WP-5 가 `core/casegrid/e2e_runner.py`(코드 **497/500** · 여유 3줄)에서
제원 상수 여덟과 `ESS(...)` 조립 전문을 `core/casegrid/ess_build.py` 로
옮겼다. ★분할의 러너 배선을 넣을 자리를 내기 위해서였다.

## 이 파일이 재는 것 셋 — **옮긴 코드를 다시 적지 않는다**

    ① 제원 여덟이 **세운 자원에 실린다**            배선이 끊기면 잡힌다
    ② ★ 충전원이 `PV_SURPLUS` 가 아니면 프로파일을 **버린다**   이 모듈의 유일한 갈래
    ③ ★★ 러너 이름공간에 **다섯만** 있다            WP-5 4절 ④ 의 판정

**②가 이 파일의 핵심이다.** `ESS._check_pv_surplus` 는 *「충전원=계통인데 PV
잉여 시계열을 받음」* 을 **거부**한다(`core/der/ess.py`). 조립 함수의 조건식이
그 거부를 막고 있으므로, 조건식이 사라지면 계통 충전 케이스가 **실행 자체를
못 한다** — 골든이 잡기는 하지만 *왜* 인지는 말해 주지 않는다.

**③이 문면 하나를 기계로 붙든다.** `core/casegrid/operating_lines.py` 머리말이
*「`_resource_lines()` 가 2.1 표에 인쇄하는 다섯을 러너가 자기 이름공간에
둔다」* 고 적는다 — 그 주장이 참인지 여기서 잰다. 그리고 **나머지 셋이 러너에
없다**는 것도 함께 못 박는다(다 재수출하면 얻으려던 여유를 도로 까먹는다는
것이 WP-5 의 판정이었다).

⚠ **금액을 재지 않는다.** 이 조립이 옳은 수를 내는가는 골든 3건
(`tests/golden/test_regression_scenarios.py`)이 `npv_won` **정확 일치**로 잰다.
여기서 금액 오라클을 또 두면 같은 수의 출처가 둘이 된다.
"""

from __future__ import annotations

import pytest

from core.casegrid import e2e_runner, ess_build
from core.casegrid.ess_build import build_case_ess
from core.der.ess import ESSChargeSource, ESSOperatingMode

#: 조립 함수가 **대장·해석에서 받는** 인자들. 값은 골든의 사본이 아니다 —
#: 이 파일은 금액을 재지 않으므로 대장과 같을 필요가 없고, 같게 두면 대장이
#: 바뀔 때 여기가 따라오지 않아도 아무 일이 없다(탐침값 규약).
_ARGS = {
    "capacity_kwh": 8.0,
    "capex_unit_won_per_kwh": 380_000.0,
    "fixed_om_won_per_year": 90_000.0,
    "replacement_unit_won_per_kwh": 340_000.0,
    "escalation_rate": 0.021,
    "replacement_escalation_rate": 0.0,
}

#: 시각별(0~23) PV 잉여 kWh. `ESS._check_pv_surplus` 가 **24행이고 하나라도
#: 0 보다 커야 한다**고 요구한다 — 그 형태만 맞춘 탐침값이다.
_PROFILE = [0.0] * 10 + [1.5] * 4 + [0.0] * 10


def _built(
    *,
    charge_source: ESSChargeSource,
    profile: list[float] | None,
    mode: ESSOperatingMode = ESSOperatingMode.PEAK_SHAVING,
):
    return build_case_ess(
        operating_mode=mode,
        charge_source=charge_source,
        pv_surplus_profile_kwh=profile,
        **_ARGS,
    )


# ── ① 제원 여덟이 세운 자원에 실린다 ────────────────────────────────────

@pytest.mark.req("FR-102-AC1.ESS")
def test_the_eight_specs_reach_the_resource_that_is_built() -> None:
    """제원 상수 여덟이 **자원에 실린다** — 배선이 끊기면 여기서 갈린다.

    ⚠ **백분율 셋은 자원 안에서 분수가 된다** (`rte`·`soc_min`·`soc_max`·
    `eol_soh`). `ESS.__init__` 이 `rte_pct / 100.0` 으로 담으므로 그 환산까지
    함께 본다 — 단위를 잘못 넘긴 조립은 값이 100배 어긋나고, 그 어긋남은
    `_in_range` 문턱 안에 들어가면 예외를 내지 않는다.
    """
    ess = _built(charge_source=ESSChargeSource.GRID, profile=None)

    assert ess.power_kw == ess_build.ESS_POWER_KW
    assert ess.cycle_life == ess_build.ESS_CYCLE_LIFE
    assert ess.calendar_life == ess_build.ESS_CALENDAR_LIFE
    assert ess.cycles_per_year == ess_build.ESS_CYCLES_PER_YEAR
    assert ess.rte == pytest.approx(ess_build.ESS_RTE_PCT / 100.0)
    assert ess.soc_min == pytest.approx(ess_build.ESS_SOC_MIN_PCT / 100.0)
    assert ess.soc_max == pytest.approx(ess_build.ESS_SOC_MAX_PCT / 100.0)
    assert ess.eol_soh == pytest.approx(ess_build.ESS_EOL_SOH_PCT / 100.0)

    # 받은 인자도 그대로 실린다 — 조립이 인자를 삼키지 않는다.
    assert ess.capacity_kwh == _ARGS["capacity_kwh"]


# ── ② ★ 충전원이 PV 잉여가 아니면 프로파일을 버린다 ─────────────────────

@pytest.mark.req("FR-102-AC1.ESS")
def test_a_profile_is_dropped_unless_the_charge_source_is_pv_surplus() -> None:
    """★ **이 모듈의 유일한 갈래.** 계통 충전에 프로파일을 줘도 서야 한다.

    `ESS._check_pv_surplus` 는 *「충전원=계통인데 PV잉여 시계열을 받음」* 을
    **거부**한다(`core/der/ess.py`). 조립 함수의 조건식이 그 거부를 막으므로,
    조건식이 사라지면 **계통 충전 케이스가 실행 자체를 못 한다.**

    ⚠ **앞뒤를 함께 둔다** — 버리는 것만 재면 「언제나 버리는」 구현도 초록불이
    된다. `PV_SURPLUS` 에서는 실제로 실려야 한다.
    """
    # 계통 충전 + 프로파일 → 예외 없이 서고, 자원은 프로파일을 갖지 않는다
    grid = _built(charge_source=ESSChargeSource.GRID, profile=_PROFILE)
    assert grid.pv_surplus_profile_kwh is None

    # 태양광 잉여 충전 → 그대로 실린다
    pv = _built(charge_source=ESSChargeSource.PV_SURPLUS, profile=_PROFILE)
    assert pv.pv_surplus_profile_kwh == tuple(_PROFILE)


# ── ③ ★★ 러너 이름공간에 다섯만 있다 ───────────────────────────────────

#: `_resource_lines()` 가 2.1 표에 **인쇄하는** 다섯. 러너가 자기 이름공간에
#: 두어야 하며, `core/casegrid/operating_lines.py` 머리말이 그것을 주장한다.
_REEXPORTED = (
    "ESS_RTE_PCT",
    "ESS_SOC_MIN_PCT",
    "ESS_SOC_MAX_PCT",
    "ESS_EOL_SOH_PCT",
    "ESS_CYCLES_PER_YEAR",
)

#: 조립 함수 **안에서만** 쓰이므로 러너 이름공간에 없어야 하는 셋.
_NOT_REEXPORTED = ("ESS_POWER_KW", "ESS_CYCLE_LIFE", "ESS_CALENDAR_LIFE")


@pytest.mark.req("NFR-206-M1")
def test_the_runner_keeps_exactly_the_five_names_it_prints() -> None:
    """★★ **다섯은 있고 셋은 없다** — WP-5 4절 ④ 의 판정을 기계로 못 박는다.

    다섯이 없으면 `core/casegrid/operating_lines.py` 머리말의 *「러너가 자기
    이름공간에 둔다」* 가 거짓이 되고, 2.1 표가 인쇄할 값을 잃는다.

    셋이 **있으면** 이 이동이 목적을 절반 잃는다 — 여덟을 다 다시 내보내면
    그 import 줄들이 코드 줄이라 얻으려던 여유를 도로 까먹는다는 것이
    이 WP 의 판정이었다(여유 3 → 18줄).

    ⚠ **같은 객체인지 본다** — 값만 비교하면 러너가 자기 사본을 따로 든
    구현도 통과하고, 그때 상수가 두 벌이 되어 한쪽만 고쳐진다.
    """
    for name in _REEXPORTED:
        assert hasattr(e2e_runner, name), f"러너가 인쇄할 이름을 잃었다: {name}"
        assert getattr(e2e_runner, name) is getattr(ess_build, name), (
            f"{name} 이 두 벌이다 — 한쪽만 고쳐질 수 있다"
        )

    for name in _NOT_REEXPORTED:
        assert not hasattr(e2e_runner, name), (
            f"{name} 이 러너 이름공간에 다시 들어왔다 — 낸 여유를 까먹는다"
        )
