"""**부하의 「형상」을 화면에서 바꾸는 칸** — R64/WP-WEB ⓐⓑ (사용자 요구 2·3).

## 왜 이 파일이 생겼는가

R64 는 로직을 먼저 세웠고 화면을 마지막 한 WP 로 모았다(사용자 지시
2026-09-06 — *「최종 코드가 확정된 다음에 …」* · *「웹 코드를 말하는 것임」*).
그래서 아래 둘은 **계산·판정·거부가 이미 다 서 있고 칸만 없던 상태**였다:

    ⓐ 하루 안에서 옮길 수 있는 가전 부하 비율   `core/casegrid/load_shift.py`
    ⓑ 냉난방 부하의 계절별 몫                   `core/casegrid/appliance_load.py`

⚠⚠ **총량이 아니라 형상의 축이다.** 둘 다 연간 부하 총량을 한 kWh 도 바꾸지
않는다 — ⓐ 는 하루 안에서 시각을 옮기고 ⓑ 는 계절 사이에서 옮긴다. 그래서
「부하를 더 얹는 칸」(히트펌프·전기차)과 **다른 묶음**으로 그린다.

## ★★★ 통로를 새로 내지 않는다 — 둘이 «서로 다른» 통로를 이미 갖는다

**ⓐ 는 전제 대장 오버라이드**(`assumption_overrides`)로 간다 — **대장이 값을
갖기 때문**이다(`load.dr_shiftable_share` · `track: assume`). 시나리오 필드를
또 세우면 통로가 둘이 되고 어느 것이 이겼는지 산출물에서 알 수 없다
(`core/report/case_report.py` 의 ★★★ 절 · `.orch/R64/result_7.md` 판정 ㉳).

**ⓑ 는 시나리오 필드**(`appliance_load_season_shares`)로 간다 — **대장이 값을
갖지 않는다.** 계절 몫은 *사업 계획이 정하는 사실*이고 자산
(`fixtures/profiles/representative-day.yaml`)의 계절 이름에 걸린다.
히트펌프·전기차 칸과 같은 규약이다.

⚠ **칸 이름을 라우터가 짓지 않는다.** 계절은 **자산이 정하므로** 이름·개수가
자산과 함께 변한다 — `Query(...)` 로 받으면 자산이 계절을 늘릴 때 라우트
시그니처를 고쳐야 하고, 자산을 데이터로 둔 이유가 그것을 막는 것이다
(`app/routers/ui_scenarios.py::save_settings_form` 이 대장 칸 50개에 대해 같은
판단을 적었다). 그래서 **이름은 여기서 짓고 받는 쪽도 여기서 거둔다.**

## ⚠ 판정·거부를 여기서 하지 않는다

합 ≠ 1 · 달력 불일치 · 범위 밖 비율은 **`core/` 의 판정 함수 하나**가 거부하고
(`resolve_appliance_season_shares` · `resolve_shiftable_share`) 그 3요소가
화면으로 그대로 나간다(`web/render.py::run_error_context`). 여기서 미리
걸러 내면 같은 거부의 문면이 두 곳에 생긴다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.ui_run import assumptions_path
from core.assumption.provider import AssumptionSet
from core.casegrid.load_shift import (
    DR_SHIFTABLE_SHARE_LEDGER_KEY,
    DR_SHIFTABLE_SHARE_TITLE,
    DR_SHIFTABLE_SHARE_UNIT,
)
from core.casegrid.profiles import load_daily_shapes

#: 계절 몫 칸의 **이름 앞머리**. `season_share-<계절이름>` 이며 계절 이름은
#: 자산이 정한다. 앞머리를 두는 이유는 받는 쪽이 *「내 칸인가」* 를 이름만
#: 보고 답할 수 있어야 하기 때문이다 — `app/routers/ui_scenarios.py` 의
#: `val-<대장 키>` 가 같은 모양이다.
SEASON_SHARE_PREFIX = "season_share-"

#: ⓐ 비율 칸의 이름. **하나뿐이므로 라우트가 `Query(...)` 로 받는다** —
#: 그러면 그 칸이 `openapi.json` 에 서고, 심의에서 인용되는 주소의 파라미터가
#: 문서에 있게 된다. 계절 몫과 달리 자산이 개수를 정하지 않는다.
SHIFTABLE_SHARE_FIELD = "dr_shiftable_share_pct"

#: 계절 몫의 **단위**. 자산의 `share` 규약(합이 1)을 글자로 적은 것이다 —
#: 「%」로 적으면 사용자가 100 을 넣고, 그때 합 판정이 100배로 거부한다.
SEASON_SHARE_UNIT = "몫 (합 1)"


def appliance_season_share_fields() -> tuple[dict[str, Any], ...]:
    """ⓑ 의 화면 칸 — **자산이 선언한 계절마다 하나**.

    ⚠⚠ **계절 이름을 여기 박지 않는다.** 자산
    (`fixtures/profiles/representative-day.yaml`)이 정본이며, 박으면 자산이
    달력을 고치는 날 화면만 옛 이름을 그리고 **`_matched` 가 「달력이 다르다」로
    거부한다** — 사용자에게 그것은 「칸을 채웠는데 거부됐다」이고 원인은 보이지
    않는다.

    `base_share` 를 함께 싣는 이유(판정 ④): **비우면 무엇이 쓰이는지**를 글자로
    적어야 한다. 비운 실행에서 냉난방은 **기본 부하와 같은 계절 몫**으로 도는데,
    그 몫이 얼마인지 화면에 없으면 사용자는 자기가 넣는 수가 무엇을 대신하는지
    모른다.
    """
    shape = load_daily_shapes().load
    return tuple(
        {
            "season": season.name,
            "name": f"{SEASON_SHARE_PREFIX}{season.name}",
            "id": f"run-season-share-{season.name}",
            "unit_id": f"run-season-share-{season.name}-unit",
            "unit": SEASON_SHARE_UNIT,
            "days": season.days,
            #: 자산이 그 계절에 준 **기본 부하의 몫**. 비운 칸이 쓰는 수다.
            "base_share": f"{season.share:g}",
        }
        for season in shape.seasons
    )


def shiftable_share_field() -> dict[str, Any]:
    """ⓐ 의 화면 칸 — **대장이 가진 값을 함께 싣는다** (판정 ④).

    ⚠⚠ **기본 비율을 화면에 박지 않는다.** 이 값은 대장이 갖고
    (`load.dr_shiftable_share`) 그 항목의 `derivation_method` 는 *「가정이며
    실측이 아니다」* 로 시작한다. 박으면 대장을 고쳐도 화면만 옛 수를 적고,
    그때 사용자가 읽는 것은 **쓰이지 않는 수**다.

    ⚠ **「비우면 0」이 아니다.** 비운 칸은 오버라이드를 걸지 않으므로 대장 값
    (지금 10)이 쓰인다 — 0 을 밀어 넣으면 *「옮기지 않는다」* 라는 **다른
    실행**이 되고 축이 움직인다. 그 구별을 글자로 적는다.
    """
    item = AssumptionSet.load_from_yaml(str(assumptions_path())).items()[
        DR_SHIFTABLE_SHARE_LEDGER_KEY
    ]
    return {
        "name": SHIFTABLE_SHARE_FIELD,
        "id": "run-dr-shiftable-share",
        "unit_id": "run-dr-shiftable-share-unit",
        # 단위 문면은 대장의 `value_unit` 이 정본이고 코드 상수가 그것을
        # 비추고 있다(`DR_SHIFTABLE_SHARE_UNIT` 의 ⚠). 화면은 대장 쪽을 그린다.
        "unit": str(item.value_unit or DR_SHIFTABLE_SHARE_UNIT),
        "title": DR_SHIFTABLE_SHARE_TITLE,
        "ledger_key": DR_SHIFTABLE_SHARE_LEDGER_KEY,
        "ledger_value": f"{item.value:g}" if isinstance(item.value, float) else str(
            item.value
        ),
        # ⚠ `str(...)` 로 낮추지 않는다 — `ConfidenceLevel` 은 `str` 하위형이나
        # `str(enum)` 은 `"ConfidenceLevel.ASSUMED"` 다(파이썬 3.11). 화면에
        # 나가야 하는 것은 그 등급의 **한국어 문면**(「가정」)이다.
        "confidence": item.confidence.value if item.confidence else "",
    }


def appliance_season_shares(
    params: Mapping[str, str],
) -> dict[str, str] | None:
    """받은 질의에서 계절 몫 칸을 거둔다 — **하나도 없으면 `None`**.

    ## ⚠⚠ 「전부 비었다」와 「일부만 적었다」를 여기서 가르지 않는다

    빈 칸을 **버리지 않고 그대로 실어 보낸다.** 그 둘을 가르는 자리는
    `resolve_appliance_season_shares` 하나이며(전부 비면 미지정, 일부만 적으면
    *「그 계절의 냉난방이 사라지는지 아직 안 적었는지 구별할 수 없다」* 로 거부),
    여기서 빈 칸을 버리면 **일부만 적은 제출이 「그 계절을 안 적은 제출」로
    바뀌어** 거부가 사라진다 — 그때 사용자가 못 채운 계절의 냉난방은 조용히
    다른 계절로 옮겨 간다.

    ⚠ 칸 이름이 하나도 안 왔으면 `None` 이다(필드를 시나리오에 넣지 않는다) —
    「적지 않았다」가 그대로 내려가야 출력이 이 통로가 생기기 전과 **원소
    하나까지** 같다. 빈 매핑(`{}`)으로 내려보내도 판정 결과는 같지만, 그러면
    안 준 실행의 시나리오 문면이 바뀌고 그 문면은 화면이 인쇄하는 자리다.
    """
    mine = {
        key[len(SEASON_SHARE_PREFIX) :]: value
        for key, value in params.items()
        if key.startswith(SEASON_SHARE_PREFIX)
    }
    return mine or None
