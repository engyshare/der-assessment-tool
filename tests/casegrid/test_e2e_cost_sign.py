"""비용 행이 NPV 를 **줄이는가** — R32 가 밟은 기존 결함.

`CashFlowRow` 는 **부호 규약을 갖지 않는다** — 「비용도 양수, 편익도 양수」이고
가르는 것은 소비자다(`core/cba/proforma.py::capex_row` 독스트링). 그래서
`bcr()` 은 편익 목록과 비용 목록을 **따로** 받는다. 그런데 `npv()` 는 목록
하나를 받아 `_pv()` 로 **부호 있는 합**을 낸다 — 그 하나는 순현금흐름이어야 한다.

`core/casegrid/e2e_runner.py` 는 `benefit_rows + cost_rows` 를 **그대로** 넘기고
있었다. 고정 O&M 이 양수이므로 **비용이 편익으로 더해졌고** NPV 가 O&M 현가의
두 배만큼 과대 계상됐다. 아무 예외도 나지 않았다.

> **R32 가 관리 수수료(`Q-14`)를 비용 행으로 넣자 「수수료율을 올릴수록 NPV 가
> 커진다」로 드러났다.** 비용 항목이 O&M 둘뿐일 때는 아무도 이 자리를 밟지
> 않았다 — 새 항목이 기존 결함을 밟은 형태다.

두 층을 따로 붙든다:

    ① 경계 함수가 비용만 뒤집는다      편익 행은 손대지 않는다
    ② 그 결과의 NPV 가 손계산과 같다   뒤집지 않으면 1,400, 뒤집으면 600
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.casegrid.e2e_runner import net_operating_flows
from core.cba.metrics import npv
from core.contracts.schemas import AssumptionRef, CashFlowRow
from core.contracts.units import Money

_BENEFIT = CashFlowRow(label="편익", tag="B", amounts={1: Decimal(1_000)})
_COST = CashFlowRow(
    label="비용",
    tag="C",
    amounts={1: Decimal(400)},
    assumption_refs=(
        AssumptionRef(
            set_name="검사", set_version="1", key="fee.manager_entity",
            confidence="가정",
        ),
    ),
)


@pytest.mark.req("FR-703-AC1.npv")
def test_only_the_cost_rows_flip_sign() -> None:
    """① 비용 행만 음수가 된다 — 편익 행은 그대로다.

    편익까지 뒤집으면 부호가 다시 맞아떨어져 ②의 손계산이 통과한다(−1,000 +
    400 = −600 은 절댓값이 같다). 그래서 두 층을 따로 본다.
    """
    rows = net_operating_flows([_BENEFIT], [_COST])

    by_tag = {row.tag: row for row in rows}
    assert by_tag["B"].amounts[1] == Decimal(1_000), "편익 행을 건드렸다"
    assert by_tag["C"].amounts[1] == Decimal(-400)


@pytest.mark.req("FR-703-AC1.npv")
def test_the_label_and_assumption_refs_survive_the_flip() -> None:
    """부기가 함께 살아 있다 — 리포트가 그 행을 이름과 출처로 찾는다.

    새 행을 만들면서 `assumption_refs` 를 빠뜨리면 `FR-1001`(산식·출처 표시)이
    그 행에서만 조용히 깨진다.
    """
    flipped = net_operating_flows([], [_COST])[0]

    assert flipped.label == "비용"
    assert flipped.tag == "C"
    assert flipped.assumption_refs == _COST.assumption_refs


@pytest.mark.req("FR-703-AC1.npv")
def test_the_cost_reduces_the_npv() -> None:
    """② 손계산 오라클 — 할인율 0, 편익 1,000, 비용 400 → **600**.

    뒤집지 않으면 1,400 이 된다. 그 수는 「그럴듯한 큰 수」이고, 비용 항목이
    늘어날수록 더 좋아 보이는 결과가 나온다.
    """
    rows = net_operating_flows([_BENEFIT], [_COST])

    assert npv(Money(0), rows, discount_rate=0.0) == Money(600)
