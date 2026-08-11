"""등록된 변형 목록 × 지원 계산 — `FR-607-AC1` 의 **합성 자리**.

**왜 이 파일이 `core/incentive/` 가 아니라 여기 있는가.** 조항은 *「지원 0
케이스가 모든 실행에서 자동 포함되어 결과 상단에 표시된다」* 를 요구하고, 그
「모든 실행」의 목록은 `core.casegrid.variants.run_order()` 다. 그런데
`.importlinter` 의 `layers` 가 `core.casegrid` 를 `core.incentive` **위**에
둔다 — 아래가 위를 알면 역방향 import 이고 `lint-imports` 가 막는다
(`NFR-208-AC1`).

R21 에 `core/incentive/calculator.py` 가 `run_order()` 를 직접 import 해서
그 게이트가 실제로 빨간불이 났다. **고칠 곳은 계층 설정이 아니라 합성이 놓인
자리였다** — 계층을 느슨하게 하면 조항 `NFR-208-AC1` 자신이 깨진다.

> **이것이 R20 이 찾은 형태의 세 번째다.** `regulation_axis.py`·
> `dataset_axis.py` 가 각각 「하위가 만든 재료를 상위가 소비한다」의 빈 자리를
> 메웠고, 이 파일은 그 자리가 **편익 계산과 케이스 목록 사이**에도 있었음을
> 말한다. 구획을 옳게 가르면 **구획 사이에 아무도 소유하지 않는 일이 남고**,
> 그것은 워커 브리프로는 잡히지 않는다.

아래가 하는 일은 **판정이 아니라 순회**다. 「기준선이 정확히 하나이고 맨
위인가」는 `ordered_variants()` 가 이미 보증하며, 이 파일은 그 보증에
의존할 뿐 재구현하지 않는다.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, NamedTuple

from core.casegrid.variants import run_order
from core.contracts.schemas import CashFlowRow
from core.incentive.calculator import (
    build_baseline_capex_cashflows,
    build_capex_cashflows,
)
from core.incentive.schemas import IncentiveScheme

Viewpoint = Literal["OWNER", "PARTICIPANT", "GOV", "SOCIAL"]


class CaseCapexCashflows(NamedTuple):
    """등록된 변형 하나의 CAPEX 현금흐름 (`FR-607-AC1`).

    `tag`·`label` 을 함께 나르는 이유: 리포트가 「상단에 표시」할 때 그 행이
    **어느 케이스인가**를 적어야 한다. 행만 돌려주면 표시 쪽이 순서에 의존해
    이름을 붙이게 되고, 순서가 바뀌면 이름이 조용히 어긋난다.
    """

    tag: str
    label: str
    rows: tuple[CashFlowRow, ...]


def build_capex_cashflows_for_all_cases(
    scheme: IncentiveScheme | None,
    capex: float | Decimal,
    viewpoint: Viewpoint,
) -> tuple[CaseCapexCashflows, ...]:
    """`FR-607-AC1`: **모든 실행에서** 지원 0 케이스가 자동 포함되어 상단에 온다.

    `run_order()` 가 등록한 변형 목록을 그대로 따라 돈다 — 호출자가
    「기준선도 계산해 달라」를 따로 기억해서 요청할 필요가 없다. 그것이
    이 조항이 없애려던 것이다: 예전 `build_capex_cashflows(..., is_baseline=)`
    은 **안 넘기면 기준선이 그냥 없었고, 빠졌을 때 나는 증상이 없었다.**
    """
    order = run_order()
    if not order or not order[0].baseline:
        raise ValueError(
            "기준선 변형이 맨 위에 없습니다 (FR-607-AC1). 「지원 0 케이스가 "
            "자동 포함되어 결과 상단에 표시된다」가 성립하지 않습니다"
        )

    results: list[CaseCapexCashflows] = []
    for variant_cls in order:
        rows = (
            build_baseline_capex_cashflows(scheme, capex, viewpoint)
            if variant_cls.baseline
            else build_capex_cashflows(scheme, capex, viewpoint)
        )
        results.append(
            CaseCapexCashflows(variant_cls.tag, variant_cls.label, tuple(rows))
        )
    return tuple(results)
