"""**부하는 자기 총량이 왔을 때만 선다** — R37 이 갈라 놓은 두 갈래를 붙든다.

## 왜 이 검사가 R37 에 필요해졌는가

종전 러너는 「대표일 형상과 연간 부하는 **함께** 주어야 한다」로 양방향을 한
조건에 묶어 막았다. R37 이 일사 곡선을 리포트의 본 실행에 배선하면서 형상은
**모든 실행에 오게 되었고**, 그러면 그 조건이 발전 곡선만 쓰려는 실행을 오류로
막는다. 그래서 조건을 갈랐다(`_household_load_if_total_given`).

⚠ **조건을 갈랐다는 것은 옛 막음이 약해졌다는 뜻이다.** 갈라 두면 *「총량은
줬는데 형상을 잊었다」* 를 여전히 막아야 하고, *「형상만 왔다」* 는 부하를
세우지 않고 통과해야 한다. 그 둘을 **여기서** 붙든다 — 붙들지 않으면 조건을
그냥 풀어 버리는 변이가 초록불이 된다(실측: 변이 ② 는 이 파일이 없을 때
전건 초록불이었다).

## ⚠ `req()` 마커를 달지 않았다

이 파일이 붙드는 것은 spec 조항이 아니라 **배포 경로가 자산을 쓰는가**다.
가까워 보이는 ID(`FR-1001-AC2` 등)를 짐작해서 붙이면 status.md 「수용기준 ID를
추정해서 쓰면 안 된다」가 막으려던 상태가 된다 — ID 가 실재하므로 매핑 검사는
통과하고, **엉뚱한 조항이 초록불**이 된다. 조항을 확인한 사람이 붙일 자리로
남긴다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.profiles import load_daily_shapes

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_LOAD = "e2e-load"
_LOAD_KWH = 3_600.0


def _levels():
    return build_level_map(_ASSUMPTIONS)


def test_a_total_without_a_shape_is_refused() -> None:
    """★★ **총량만 주면 거부한다** — 시간대 없는 부하를 「반영했다」로 만들지 않는다.

    총량만으로 부하를 세우면 하루 안에서 균등 배분이 되어, 지금 PV 가 겪던
    것과 같은 형태가 된다(붙임 8 「일중 발전 프로파일」). 그때 *「부하를
    반영했다」* 는 진술은 성립하는데 **그 부하는 아무 시간대도 갖지 않는다.**
    """
    with pytest.raises(ValueError, match="대표일 형상"):
        run_single_case_e2e(
            {},
            level_map=_levels(),
            horizon_years=20,
            annual_load_kwh=_LOAD_KWH,
        )


def test_a_shape_alone_builds_the_generation_curve_but_no_load() -> None:
    """★★ **형상만 오면 부하를 세우지 않고 지나간다** — 발전 곡선만 쓰는 갈래.

    이것이 R37 이 열어야 했던 갈래다. 막혀 있던 동안 리포트는 일사 곡선을
    쓰려면 **부하까지 함께** 넣어야 했고, 그러면 배타 규칙 유형 A 때문에
    결론에 실을 수 없는 실행이 된다(`_assumed_operation` 주석).
    """
    outcome = run_single_case_e2e(
        {},
        level_map=_levels(),
        horizon_years=20,
        daily_shapes=load_daily_shapes(),
    )
    names = [resource.name for resource in outcome.resources]
    assert _LOAD not in names, (
        f"형상만 주었는데 부하 자원이 섰다 — 자원 {names}. 총량을 주지 않았으니 "
        "그 부하의 총량은 러너가 지어낸 것이다"
    )
    assert _LOAD not in outcome.dispatch.per_resource, (
        "부하가 운전 결과에 있다 — 총량 없이 세워졌다"
    )


def test_both_together_still_build_the_load() -> None:
    """★ 둘을 함께 주면 **부하가 선다** — 갈라 놓아도 정상 갈래는 살아 있다.

    이 단언이 없으면 위 둘은 *「부하를 아예 세우지 않는다」* 로도 통과한다.
    """
    outcome = run_single_case_e2e(
        {},
        level_map=_levels(),
        horizon_years=20,
        daily_shapes=load_daily_shapes(),
        annual_load_kwh=_LOAD_KWH,
    )
    assert _LOAD in outcome.dispatch.per_resource, "부하를 함께 주었는데 서지 않았다"
    daily = -sum(outcome.dispatch.per_resource[_LOAD].electric)
    assert daily > 0.0, f"부하의 대표일 소비가 {daily}kWh 다"
