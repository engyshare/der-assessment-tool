"""계절별 하루를 **연간등가 하루 하나로 접는** 자리 (R64/WP-7 이 갈라냈다).

## 왜 `seasonal_dispatch.py` 에서 갈라냈나

`core/casegrid/seasonal_dispatch.py` 가 `NFR-206` 코드 줄 상한(500)을 **519줄**로
넘겼다(`scripts/check_file_size.py --code-strict` 실측, 2026-09-06). 넘긴 것은
R64/WP-7 이 그 파일에 「AI 가전」의 부하 이동 절을 세운 몫이다.
⛔ **상한을 올려 푸는 것은 spec 개정(§16.5)이므로 하지 않는다** — 이 저장소가
이미 세 번 쓴 방법(`core/casegrid/pv_allocation.py` R51/WP-5 ·
`core/casegrid/ess_build.py` R57/WP-5 · `core/casegrid/seasonal_dispatch.py`
R64/WP-4)을 따라 새 모듈로 뽑는다.

**가르는 선은 「접기」다.** 계절을 세우고 돌리는 일은 그 파일에 남고, 이 파일이
갖는 것은 *「계절 수만큼의 하루를 하나로 어떻게 접는가」* 하나다 — 그 셋은
`math` 와 `DispatchResult`·`SystemDispatch` 밖에 보지 않으므로 의존이 한 방향
으로만 흐른다(그 파일이 이것을 부르고, 이것은 그 파일을 모른다).

## ★★★ 접는 식 — **일수 가중 평균 하루**

    연간등가 하루[j] = Σ_계절 ( 그 계절 하루[j] × 계절일수 / 365 )

그렇게 접은 하루에 러너의 종전 연간화 규약(×365)을 그대로 먹이면
**`연간등가 하루 × 365 == Σ_계절 (계절 하루 × 계절일수)`** 이므로 계절별 합산과
같아진다. 그 근거와 「금액에서 합치면 안 되는」 사유는
`core/casegrid/seasonal_dispatch.py` 머리말의 ★★★ 절이 갖는다.

⚠ **여기서 금액을 만들지 않는다.** 이 파일이 다루는 것은 물리량뿐이며, 그래서
*「월 단위로 이미 연간값인 편익이 계절 수만큼 곱해지는」* 사고가 구조적으로
불가능하다.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

from core.contracts.der import DispatchResult
from core.contracts.engine import SystemDispatch

__all__ = ("blend_dispatch", "blend_series")


def blend_series(series: Sequence[Sequence[float]], weights: Sequence[float]) -> list[float]:
    """스텝별 일수 가중 평균. **`math.fsum` 이라 차례에 무감하다**(성질 「다」).

    ⚠ 계절이 하나면 가중치가 `365/365 == 1.0` 이고 `fsum([x * 1.0]) == x` 이므로
    **원소 하나까지** 계절 축이 서기 전과 같다(성질 「라」).
    """
    return [
        math.fsum(row[step] * weight for row, weight in zip(series, weights, strict=True))
        for step in range(len(series[0]))
    ]


def _blend_result(results: Sequence[DispatchResult], weights: Sequence[float]) -> DispatchResult:
    """자원 하나의 계절별 결과를 연간등가 하루로 접는다 — **매체 넷과 미충족 넷 전부.**

    ⚠ **미충족을 빼놓지 않는다.** 빼면 어느 계절이 수요를 못 채웠다는 사실이
    연간등가 하루에서 사라지고, 그 소멸은 아무 예외도 내지 않는다.
    """
    return DispatchResult(
        electric=blend_series([r.electric for r in results], weights),
        heat=blend_series([r.heat for r in results], weights),
        cool=blend_series([r.cool for r in results], weights),
        fuel=blend_series([r.fuel for r in results], weights),
        unmet_electric=blend_series([r.unmet("electric") for r in results], weights),
        unmet_heat=blend_series([r.unmet("heat") for r in results], weights),
        unmet_cool=blend_series([r.unmet("cool") for r in results], weights),
        unmet_fuel=blend_series([r.unmet("fuel") for r in results], weights),
        # ⚠ **진단 문구는 합치지 않고 모은다** — 계절 하나가 낸 문구를 버리면 그
        # 계절이 무엇을 못 했는지가 연간등가 하루에서 사라진다. 같은 문구가 여러
        # 계절에서 나면 한 번만 싣는다(차례는 **처음 나온 차례**다).
        notes=tuple(dict.fromkeys(n for result in results for n in result.notes)),
    )


def blend_dispatch(
    dispatches: Sequence[SystemDispatch], weights: Sequence[float]
) -> SystemDispatch:
    """계절별 하루를 **연간등가 하루** 하나로 접는다 (모듈 머리말 ★★★ 절).

    ⚠ **수지는 선형이라 그대로 닫힌다** — `Σ 자원 + 수전 − 송전 = 0` 이 계절마다
    성립하므로 그 일수 가중 평균에서도 성립한다. 그래서 이 하루를 다시
    `verify_balance()` 에 걸 필요가 없고, 걸어도 통과한다.

    ⚠ **연간등가 하루의 한 스텝에서 송전과 수전이 함께 0 이 아닐 수 있다.**
    그것은 결함이 아니라 **평균이라는 뜻**이다 — 어떤 계절은 그 시각에 내보내고
    어떤 계절은 받아들인다. 붙임 7 이 인쇄하는 하루가 그 하루이며, 그 표의
    문면(`dispatch_note`)이 계절 넷을 각각 돌려 합산했다고 적는다.
    """
    names = tuple(dispatches[0].per_resource)
    return SystemDispatch(
        per_resource={
            name: _blend_result([d.per_resource[name] for d in dispatches], weights)
            for name in names
        },
        grid_import=blend_series([d.grid_import for d in dispatches], weights),
        grid_export=blend_series([d.grid_export for d in dispatches], weights),
    )
