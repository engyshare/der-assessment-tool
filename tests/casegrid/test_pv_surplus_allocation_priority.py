"""**PV 잉여를 ESS 충전이 가구 부하보다 먼저 가져간다** — 그 순서를 붙든다 (R50/WP-3).

## 무엇을 붙드는가

러너가 짓는 `surplus_profile_kwh` 는 **PV 출력의 배분 순서를 정한다.** 정본
선언은 `e2e_runner._resolve_ess_dispatch_inputs` 독스트링에 있고 여기는 그
선언이 **동작과 같은지** 재는 자리다.

    ① PV 출력 중 「자가소비 비율」분    → 가구 자가소비
    ② 그 나머지(= 잉여) 중 ESS 가 받을 수 있는 만큼 → ESS 충전 (PV_SURPLUS)
    ③ 그래도 남은 몫                   → 계통 역송
       가구가 ① 을 넘어 쓰는 수요       → 계통 수전

`ESS._pv_surplus_charge_kwh_by_hour` 는 가구 부하를 보지 않는다 — 러너가 그
부하를 충전 계획에 넘기지 않기 때문이다(피크 저감에는 `_site_load_kw` 로
넘긴다). 그래서 **부하를 아무리 키워도 ② 의 몫은 줄지 않는다.**

## ⚠ 왜 「잉여 합이 `pv.surplus_kwh()` 와 같은가」로 재지 않았는가

그것은 **같은 함수를 두 번 부른 것**이고, 이 저장소가 반복해 밟은 동어반복이다
(`status.md` 「함정」 절 — *「이 단언에 등장하는 값 중 몇 개를 검사 대상이 스스로
정하는가? 전부라면 동어반복이다」*). 대신 **입력 하나(가구 부하 총량)만 바꾼 두
실행을 견준다** — 단언에 쓰는 값은 두 실행이 각각 따로 내놓은 운전 결과이고,
어느 쪽도 다른 쪽을 정하지 않는다.

## ⚠ 단언이 **둘**인 이유

「부하를 키워도 ESS 충전이 같다」만으로는 **「부하가 아예 반영되지 않는다」와
구별되지 않는다.** 그래서 같은 두 실행에서 **계통 수전은 달라야 한다**는 것을
함께 잰다 — 부하가 크면 그만큼 수전이 늘어야 한다.

## ⚠ `req()` 마커를 달지 않았다

`FR-302-AC1` 이 이 7단계 우선순위를 적기는 하지만, 그 ① 은 *「즉시」* 자가소비
(그 스텝의 실제 부하)이고 구현의 ① 은 **연간 고정 비율**이다. 마커를 달면
매핑표가 그 조항을 「검증됨」으로 세는데, 이 검사가 재는 것은 조항의 ① 이
아니라 **지금 구현이 실제로 하는 순서**다. 조항과 구현의 그 어긋남을 사람이
판정한 뒤에 붙일 자리로 남긴다 — `test_household_load_gate.py` 가 같은 이유로
비워 둔 자리와 같다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.casegrid.e2e_runner import DAYS_PER_YEAR, run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.models import CaseOutcome
from core.casegrid.profiles import load_daily_shapes

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_ESS = "e2e-ess"
_LOAD = "e2e-load"

#: 부하 0 인 케이스도 **부하 자원을 세운다** — 총량만 0 이다. 자원 구성을 같게
#: 두어야 두 실행의 차이가 「부하의 크기」 하나로 좁혀진다(자원이 하나 없어지면
#: 「없어서 달라졌다」와 「앞서서 달라졌다」를 가를 수 없다).
_NO_LOAD_KWH = 0.0
#: 가구 10호분(3,600kWh/호·년 · 대장 `load.household.annual` 의 가정값). PV 연간
#: 발전량을 넘도록 크게 잡는다 — 넘지 않으면 「잉여가 넉넉해서 부하와 다투지
#: 않았다」로도 통과한다.
_HEAVY_LOAD_KWH = 36_000.0


def _run(annual_load_kwh: float) -> CaseOutcome:
    return run_single_case_e2e(
        {},
        level_map=build_level_map(_ASSUMPTIONS),
        horizon_years=20,
        daily_shapes=load_daily_shapes(),
        annual_load_kwh=annual_load_kwh,
    )


def _annual_ess_charge_kwh(outcome: CaseOutcome) -> float:
    """ESS 의 **연간 충전량**(kWh) — 대표일 운전 결과의 음수분(= 충전)을 연간화한다.

    ⚠ `ESS.annual_charge_kwh()` 를 부르지 않는다. 그것은 자원이 스스로 내놓는
    **계획**이고, 여기서 재려는 것은 러너가 실제로 실은 **운전 결과**다.
    """
    electric = outcome.dispatch.per_resource[_ESS].electric
    return -sum(v for v in electric if v < 0.0) * DAYS_PER_YEAR


def _annual_grid_import_kwh(outcome: CaseOutcome) -> float:
    return sum(outcome.dispatch.grid_import) * DAYS_PER_YEAR


def _annual_grid_export_kwh(outcome: CaseOutcome) -> float:
    return sum(outcome.dispatch.grid_export) * DAYS_PER_YEAR


def test_both_runs_stand_the_load_resource() -> None:
    """★ 성립 조건 — 두 실행 **모두** 부하 자원을 세운다.

    이것이 거짓이면 아래 두 검사는 「부하가 있는 실행 vs 없는 실행」을 견주는
    것이 되고, 그때 「충전량이 같다」는 우선순위가 아니라 **자원 구성**을 잰
    것이 된다.
    """
    for load_kwh in (_NO_LOAD_KWH, _HEAVY_LOAD_KWH):
        outcome = _run(load_kwh)
        assert _LOAD in outcome.dispatch.per_resource, (
            f"부하 총량 {load_kwh}kWh 를 주었는데 부하 자원이 서지 않았다"
        )


def test_ess_charge_does_not_yield_to_household_demand() -> None:
    """★★ ② 가 가구의 추가 수요보다 **앞선다** — 부하를 키워도 ESS 충전이 같다.

    가구 부하를 0 에서 10호분으로 올려도 ESS 가 받아 가는 연간 kWh 는 **한
    kWh 도 줄지 않는다.** 충전 계획(`ESS._pv_surplus_charge_kwh_by_hour`)이
    보는 것은 PV 잉여뿐이고, 그 잉여는 가구가 무엇을 쓰든 그대로이기 때문이다.

    ⚠ **이 단언은 「그래야 한다」가 아니라 「지금 그렇다」다.** 순서를 바꾸는
    것은 결론축을 움직이는 판정이며 사용자 몫이다 — 바꾸기로 하면 이 검사가
    먼저 빨간불이 되어 그 변경이 조용히 지나가지 않는다.
    """
    quiet = _annual_ess_charge_kwh(_run(_NO_LOAD_KWH))
    heavy = _annual_ess_charge_kwh(_run(_HEAVY_LOAD_KWH))
    assert quiet > 0.0, f"부하 0 인 실행에서 ESS 충전이 {quiet}kWh 다 — 견줄 것이 없다"
    assert heavy == pytest.approx(quiet), (
        f"가구 부하를 {_HEAVY_LOAD_KWH:,.0f}kWh 로 올리자 ESS 연간 충전이 "
        f"{quiet:,.4f} → {heavy:,.4f}kWh 로 움직였다. 우선순위가 바뀌었다면 "
        "`_resolve_ess_dispatch_inputs` 독스트링의 선언을 함께 고쳐야 한다 — "
        "선언과 동작이 갈리면 다음 사람이 문면을 믿는다"
    )


def test_the_household_demand_lands_on_grid_import_instead() -> None:
    """★★ 밀려난 수요는 **계통 수전**으로 간다 — 「부하가 반영되지 않는다」와 가른다.

    앞 검사만으로는 *「부하를 아예 계산에 넣지 않았다」* 도 통과한다. 같은 두
    실행에서 **계통 수전이 실제로 늘어나는지**를 함께 재어 그 갈래를 막는다.
    수전이 느는 만큼 계통 역송은 줄어야 한다 — 같은 PV 출력을 나눠 갖는
    자리이므로(③).
    """
    quiet = _run(_NO_LOAD_KWH)
    heavy = _run(_HEAVY_LOAD_KWH)
    quiet_import = _annual_grid_import_kwh(quiet)
    heavy_import = _annual_grid_import_kwh(heavy)
    assert heavy_import > quiet_import, (
        f"가구 부하를 {_HEAVY_LOAD_KWH:,.0f}kWh 로 올렸는데 계통 수전이 "
        f"{quiet_import:,.4f} → {heavy_import:,.4f}kWh 로 늘지 않았다 — 부하가 "
        "운전에 반영되지 않았을 수 있다"
    )
    assert _annual_grid_export_kwh(heavy) < _annual_grid_export_kwh(quiet), (
        "부하가 늘었는데 계통 역송이 줄지 않았다 — ③ 이 잔여분이 아니게 됐다"
    )
