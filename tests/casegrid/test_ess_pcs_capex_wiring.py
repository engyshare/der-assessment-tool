"""★ **초기투자에 「원/kW 항」이 섰다** — PCS 배선 (R66/WP-2 · 사용자 판정 ③).

## 무엇이 어긋나 있었는가 — **정격출력을 키우는 것이 공짜였다**

`ESS._gross_capex_won()` 은 `단가(원/kWh) × 용량 + 부대비` 였고 **원/kW 항이
없었다.** 그래서 정격출력은 초기투자에 한 원도 들어가지 않았다. 실측
(`.orch/R66/probe/pcs_power.py`)은 20 kW → 400 kW 를 훑어도 초기투자가
**196,000,000원으로 같고** 결론축이 40 kW 이상에서 포화하는 것을 보였다 —
방전 가용량이 먼저 막기 때문이다. 즉 *「20가구 단지에 PCS 몇 kW 가 맞는가」*
를 **경제성으로 물을 수 없었다.**

R66/WP-1 이 대장에 값 둘을 세웠고(`capex.ess.pcs_power` 250,000원/kW ·
`capex.ess.pcs_share_of_system` 20.0%) 이 라운드가 그것을 계산에 배선한다.

## 이 파일이 재는 것 다섯

    ⓐ 초기투자 = 배터리 + PCS 가 **손계산과 일치**한다
    ⓑ ★ **정격출력을 바꾸면 초기투자가 바뀐다**    ← 이 배선의 존재 이유
    ⓒ `pcs_lifetime=None` 이면 교체비도 잔존가치도 **둘 다** 없다 (대칭)
    ⓓ 몫으로 갈랐을 때 **PCS 몫의 합이 통짜와 같다**
    ⓔ 대장 통로가 `%` 를 비율로, 원/kW 를 그대로 나른다

**ⓑ 가 이 파일의 핵심이다.** ⓐ 만 있으면 「식을 그렇게 적었다」를 재는 것이고,
배선이 다시 용량 비례로 접히더라도(예: 몫으로 PCS 를 떼기만 하는 형태) ⓐ 는
초록불일 수 있다. ⓑ 는 **출력을 줄이면 돈이 아껴지는가**를 직접 묻는다.

**ⓒ 가 R40 ② 의 비대칭을 막는다.** `core/der/ess.py::ESS._acquisitions` 가
*「스케줄에만 있다 → 교체비는 냈는데 잔존가치가 사라진다」* 를 적어 두었고
`tests/casegrid/test_lifecycle_wiring.py` ⓒ 가 그 방향의 그물이다. 수명을
`None` 으로 두는 것은 **양쪽이 함께 없는** 상태여야 한다.

⚠ **금액 오라클을 골든에서 베끼지 않는다.** 아래 탐침값은 손계산이 쉬운 수로
고른 것이며 대장의 사본이 아니다 — 대장이 바뀌어도 이 파일은 옳다. 배포 구성의
결론축을 재는 것은 골든 3건(`tests/golden/test_regression_scenarios.py`)이다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.casegrid.ess_build import build_case_ess, build_case_ess_fleet
from core.casegrid.ess_share import PRORATED_FIELDS, ESSShare
from core.casegrid.ledger_levels import build_level_map, ledger_backed_variables
from core.der.ess import ESS, ESSChargeSource, ESSOperatingMode
from core.der.ess_schedule import ESSDischargeAllocation

#: 대장 정본. `tests/casegrid/test_ledger_levels.py` 와 **같은 자리를 가리킨다** —
#: 사본을 만들지 않으려면 경로를 여기서도 저장소 뿌리에서 지어야 한다.
_ASSUMPTIONS_YAML = Path(__file__).resolve().parents[2] / "docs" / "assumptions.yaml"

#: 손계산이 쉬운 탐침값. 배터리 400,000원/kWh × 200 kWh = 80,000,000 ·
#: PCS 250,000원/kW × 100 kW = 25,000,000 ⇒ 합 **105,000,000원**.
_CAPACITY_KWH = 200.0
_POWER_KW = 100.0
_BATTERY_UNIT = 400_000.0
_PCS_UNIT = 250_000.0

#: 조립 함수에 주는 것은 **시스템 단가와 몫**이다 — 배터리 단가를 직접 주지
#: 않는 것이 요점이다(그 감산이 배선의 일부다). 500,000 × (1 − 0.20) = 400,000.
_SYSTEM_UNIT = 500_000.0
_PCS_SHARE = 0.20

_BUILD_ARGS = {
    "operating_mode": ESSOperatingMode.PEAK_SHAVING,
    "charge_source": ESSChargeSource.GRID,
    "pv_surplus_profile_kwh": None,
    "discharge_allocation": ESSDischargeAllocation.FIXED_WINDOW,
    "load_profile_kwh": None,
    "capex_unit_won_per_kwh": _SYSTEM_UNIT,
    "capex_pcs_won_per_kw": _PCS_UNIT,
    "pcs_share_of_system": _PCS_SHARE,
    "fixed_om_won_per_year": 100_000.0,
    "replacement_unit_won_per_kwh": _SYSTEM_UNIT,
    "escalation_rate": 0.0,
    "replacement_escalation_rate": 0.0,
}


def _ess(**overrides: object) -> ESS:
    """자원 단독 — 조립 함수를 지나지 않고 `ESS` 의 식만 잰다."""
    params: dict[str, object] = {
        "name": "검증용ESS",
        "capacity_kwh": _CAPACITY_KWH,
        "power_kw": _POWER_KW,
        "calendar_life": 20,
        "capex_unit_won_per_kwh": _BATTERY_UNIT,
        "capex_pcs_won_per_kw": _PCS_UNIT,
    }
    params.update(overrides)
    return ESS(**params)  # type: ignore[arg-type]


# ── ⓐ 초기투자 = 배터리 + PCS ────────────────────────────────────────

@pytest.mark.req("FR-101-AC5")
def test_capex_is_battery_per_kwh_plus_pcs_per_kw() -> None:
    """`RC-ALL-C1` 에 **원/kW 항**이 더해졌다 — 손계산과 원소 하나까지 같다.

    400,000 × 200 + 250,000 × 100 = 80,000,000 + 25,000,000 = **105,000,000원**.
    """
    assert _ess().capex(year=1) == 105_000_000
    assert _ess().capex(year=2) == 0


@pytest.mark.req("FR-101-AC5")
def test_the_pcs_term_is_absent_when_the_unit_price_is_not_given() -> None:
    """⚠ **기본값 0.0 은 「이 인자가 생기기 전」과 같은 수를 낸다.**

    이 단정이 없으면 인자를 더한 것 자체가 `capex_pcs_won_per_kw` 를 넘기지
    않는 호출자 전부(`tests/der/test_ess.py` 의 C-1 오라클을 포함)의 수를
    조용히 움직일 수 있다.
    """
    assert _ess(capex_pcs_won_per_kw=0.0).capex(year=1) == 80_000_000


@pytest.mark.req("FR-101-AC5")
def test_the_pcs_term_is_not_the_extra_cost_line() -> None:
    """⚠⚠ **PCS 를 「부대비」로 넣지 않았다** — 둘은 함께 서고 서로 다르다.

    `capex_extra_won` 의 이름은 부대비이고 `_gross_capex_won()`·리포트가
    그렇게 인쇄한다. PCS 를 그 인자에 접어 넣으면 **문면이 거짓**이 되며,
    이 단정은 두 항이 **각각** 더해지는 것을 붙든다.
    """
    ess = _ess(capex_extra_won=1_000_000.0)
    assert ess.capex(year=1) == 106_000_000


@pytest.mark.req("FR-102-AC1.ESS")
def test_the_ledger_share_reduces_the_battery_unit_price_in_the_builder() -> None:
    """조립 함수가 **시스템 단가에서 몫을 뺀다** — 두 번 세지 않는다.

    500,000 × (1 − 0.20) × 200 + 250,000 × 100 = 80,000,000 + 25,000,000.
    ⚠ 몫을 빼지 않으면 100,000,000 + 25,000,000 = 125,000,000 이 되어 **PCS 가
    두 번** 선다. 그 사실을 아래 마지막 단정이 이름으로 붙든다.
    """
    ess = build_case_ess(capacity_kwh=_CAPACITY_KWH, household_scale_factor=20.0, **_BUILD_ARGS)
    assert ess.power_kw == pytest.approx(_POWER_KW)
    assert ess.capex(year=1) == 105_000_000
    assert ess.capex(year=1) != 125_000_000


# ── ⓑ ★ 정격출력을 바꾸면 초기투자가 바뀐다 ──────────────────────────

@pytest.mark.req("FR-101-AC5")
def test_changing_the_rated_power_changes_the_initial_investment() -> None:
    """★★★ **이 배선의 존재 이유다.**

    종전에는 이 단정이 **거짓**이었다 — 20 kW 든 400 kW 든 초기투자가 같았고,
    그래서 적정 출력을 경제성으로 물을 수 없었다. 40 kW 면 PCS 항이
    10,000,000원이므로 100 kW(25,000,000원)보다 **15,000,000원 싸다.**
    """
    at_100 = _ess(power_kw=100.0).capex(year=1)
    at_40 = _ess(power_kw=40.0).capex(year=1)
    assert at_100 == 105_000_000
    assert at_40 == 90_000_000
    assert at_100 - at_40 == 15_000_000, "출력을 줄였는데 초기투자가 안 줄었다"


@pytest.mark.req("FR-102-AC1.ESS")
def test_the_household_scale_reaches_the_pcs_term_too() -> None:
    """⚠ **단지 규모 배수가 PCS 항에도 걸린다** — 안 걸리면 20호 단지가 한 호분
    PCS 를 문다.

    `ESS_POWER_KW`(한 호 5 kW) × 20호 = 100 kW ⇒ PCS 25,000,000원.
    배수 1.0 이면 5 kW ⇒ 1,250,000원이다.
    """
    one = build_case_ess(capacity_kwh=10.0, household_scale_factor=1.0, **_BUILD_ARGS)
    twenty = build_case_ess(capacity_kwh=200.0, household_scale_factor=20.0, **_BUILD_ARGS)
    assert one.capex(year=1) == 4_000_000 + 1_250_000
    assert twenty.capex(year=1) == 80_000_000 + 25_000_000


# ── ⓒ 수명이 없으면 교체비도 잔존가치도 없다 ─────────────────────────

@pytest.mark.req("FR-104-AC4")
def test_no_pcs_lifetime_means_neither_replacement_nor_salvage() -> None:
    """⚠⚠ **대칭이어야 한다** — R40 ② 가 남긴 비대칭의 반대 방향이다.

    `pcs_lifetime=None` 은 「PCS 재취득을 아직 모형에 넣지 않았다」이고, 그
    상태에서 교체비만 서거나 잔존가치만 서면 결론이 **한 방향으로만** 틀린다.
    비교 대상은 「같은 자원에서 PCS 단가만 0 으로 둔 것」이다 — PCS 항이
    교체·잔존 경로에 **아무것도 더하지 않았음**을 그 동일성이 말한다.
    """
    with_pcs = _ess(pcs_lifetime=None, pcs_cost_won=25_000_000.0)
    without = _ess(capex_pcs_won_per_kw=0.0, pcs_lifetime=None, pcs_cost_won=0.0)

    assert with_pcs.replacement_schedule(horizon=20) == without.replacement_schedule(horizon=20)
    # 잔존가치는 **같지 않다** — 최초 PCS 값이 배터리 취득가에 들어 있으므로
    # 그 몫만큼 크다. 재는 것은 「PCS 갈래가 따로 서지 않았다」이므로 부품
    # 개수로 묻는다(금액으로 물으면 위 사실과 뒤섞인다).
    assert len(with_pcs._acquisitions(horizon=20)) == 1, "PCS 갈래가 수명 없이 섰다"


@pytest.mark.req("FR-104-AC4")
def test_a_pcs_lifetime_would_add_both_at_once() -> None:
    """★ 위 단정이 「배선이 끊긴 것」과 구별되는지 — 수명을 주면 **둘이 함께 선다.**

    이 검사가 없으면 `pcs_lifetime` 통로 자체가 죽어 있어도 위 검사가 초록불
    이다(이 저장소가 다섯 번 만난 「읽는 쪽이 없다」의 형태다).
    """
    lived = _ess(pcs_lifetime=10, pcs_cost_won=25_000_000.0)
    assert lived.replacement_schedule(horizon=20)[11] == 25_000_000
    assert len(lived._acquisitions(horizon=20)) == 2


# ── ⓓ 몫으로 갈라도 PCS 합이 통짜와 같다 ─────────────────────────────

@pytest.mark.req("FR-102-AC1.ESS")
def test_the_shares_add_back_up_to_the_whole_pcs_cost() -> None:
    """몫으로 갈라도 **초기투자 합이 통짜와 같다** — PCS 항을 포함해서다.

    `capex_pcs_won_per_kw` 는 **단위당**이라 갈린 `power_kw` 에 곱해져 저절로
    갈리고, `pcs_cost_won`(금액)은 `PRORATED_FIELDS` 가 갈라 준다. 어느 한쪽이
    빠지면 이 합이 어긋난다 — 그것이 이 단정의 요점이다.
    """
    shares = (
        ESSShare(name="첨두", fraction=0.6, operating_mode=ESSOperatingMode.PEAK_SHAVING,
                 quantity_id="첨두저감"),
        ESSShare(name="망지원", fraction=0.4, operating_mode=ESSOperatingMode.GRID_DISCHARGE,
                 quantity_id="망지원량"),
    )
    fleet, plans, whole = build_case_ess_fleet(
        shares=shares, capacity_kwh=_CAPACITY_KWH, household_scale_factor=20.0, **_BUILD_ARGS
    )
    assert whole.capex(year=1) == 105_000_000
    assert sum(int(r.capex(year=1)) for r in fleet) == 105_000_000
    assert sum(r.power_kw for r in fleet) == pytest.approx(_POWER_KW)
    assert len(plans) == 2


@pytest.mark.req("FR-102-AC1.ESS")
def test_the_prorated_list_holds_the_amount_and_not_the_unit_price() -> None:
    """★ **어느 이름이 갈리고 어느 이름이 그대로인가**를 이름으로 붙든다.

    `pcs_cost_won` 은 금액이라 갈라야 하고, `capex_pcs_won_per_kw` 는 단위당
    이라 갈리면 **몫의 제곱만큼** 작아진다. 목록이 뒤집히면 위 합 단정보다
    이 검사가 먼저 *어느 쪽을 잘못 골랐는지* 말한다.
    """
    assert "pcs_cost_won" in PRORATED_FIELDS
    assert "capex_pcs_won_per_kw" not in PRORATED_FIELDS


# ── ⓔ 대장 통로 ──────────────────────────────────────────────────────

@pytest.mark.req("NFR-202-M1")
def test_both_pcs_items_come_from_the_ledger_with_the_right_unit() -> None:
    """수준표가 **대장에서** 두 값을 나른다 — 기대 수치를 여기 적지 않는다.

    적으면 사본이 되고 대장을 고칠 때 여기가 따라오지 않아도 아무 일이 없다.
    재는 것은 ① 두 키가 통로에 있는가 ② 단위가 옳게 환산되는가 둘이다 —
    몫은 대장이 `%` 이고 자원이 비율을 쓰므로 `< 1.0` 이어야 한다.
    """
    keys = ledger_backed_variables()
    assert keys["ess_pcs_unit_cost"] == "capex.ess.pcs_power"
    assert keys["ess_pcs_share"] == "capex.ess.pcs_share_of_system"

    levels = build_level_map(_ASSUMPTIONS_YAML)
    assert levels["ess_pcs_unit_cost"]["base"] > 1_000.0, "원/kW 를 비율로 환산했다"
    assert 0.0 < levels["ess_pcs_share"]["base"] < 1.0, "`%` 가 환산되지 않았다"
