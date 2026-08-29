"""자원을 가리키는 **두 규약**이 갈린 채로 있는가 — 계약 검사 (R43-B).

리포트 자료형 셋이 자원을 가리키는데, 담기는 값이 **서로 조인되지 않는 두
이름공간**이다(`core/casegrid/models.py` 의 「두 규약」 블록):

    ① 자원 이름  `OneOffLine.resource_name`  = `ResourceLine.name`  (`"e2e-pv"`)
    ② 짧은 코드  `CostLine.resource_code` · `BenefitLine.resource_code`
                                              (`"PV"` · `"ESS"` · `""`)

## 이 검사가 막는 것 — **아직 일어나지 않은 잘못된 조인**

지금은 틀린 값을 인쇄하지 않는다. 붙임 8(`core/report/unreflected.py::
_replacement_items`)은 ① 만 조인하고 그쪽 규약은 맞다. 무너지는 것은 **다음
사람이 ② 로 같은 조인을 쓰는 날**이며, 그때 아무 예외 없이 **빈 교집합**이
나오고 붙임 8 의 판정이 조용히 *「미반영」* 으로 넘어간다.

이름을 갈라 두는 것(`resource_name` / `resource_code`)이 그 실수를 **읽는
순간 보이게** 만들지만, 이름만으로는 **값이 규약을 지키는지**를 아무도 재지
않는다 — 러너가 `resource_name=` 자리에 짧은 코드를 넣어도 타입은 둘 다
`str` 이라 통과한다. 그 자리를 이 파일이 막는다.

## 공통 §4 의 네 물음

① **정본이 어디서 오는가** — 자원 이름 집합은 **그 실행의 결과**
   (`basis.resources`)에서 온다. 짧은 코드 목록은 **밖에서 고정한다**(아래
   `_SHORT_CODES`) — 실행에서 뽑아 오면 검사가 자기 오라클을 스스로 만들고,
   러너가 규약을 바꾸는 순간 검사도 함께 따라가 **아무것도 재지 않게** 된다.
② **이 설명이 이 검사에 걸리는가** — 아니다. 소스 문면을 보지 않는다.
③ **이름보다 넓게 주장하는가** — 이 파일은 **한 실행이 낸 값**만 잰다. 다른
   자원 구성(히트펌프·EV)이 들어오는 날 그 자원이 규약을 지키는지는 재지
   못한다 — 그것은 그 배선이 서는 날의 몫이다.
④ **수와 그 조건의 짝** — 금액을 오라클로 적지 않는다. 재는 것은 **두 집합의
   포함·배타 관계**다.
"""
from __future__ import annotations

from types import MappingProxyType

import pytest

from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import design_levels
from core.casegrid.models import CaseBasis

#: 탐침 분석기간. **대장의 20 과 다른 수를 일부러 쓴다** — 같은 수를 쓰면 이
#: 파일이 대장의 사본을 갖게 된다. ESS 수명 17 보다 커서 **교체 흐름과 잔존
#: 흐름이 둘 다 서는** 값을 고른다(둘 중 하나만 서면 ① 이 반쪽만 검사된다).
_PROBE_HORIZON = 18

#: ★ **밖에서 고정한 오라클.** 실행에서 뽑아 오지 않는다 — 뽑아 오면 이 목록이
#: 「러너가 지금 쓰는 값」이 되어 무엇과도 어긋날 수 없다. 빈 문자열은 **자원에
#: 귀속되지 않는 거래 비용**(수전·정산 수수료)의 규약이다.
_SHORT_CODES = frozenset({"PV", "ESS", ""})

#: 대장을 읽지 않는다 — 이 파일이 보는 것은 금액이 아니라 **규약**이다.
_LEVEL_MAP = {
    "pv_unit_cost": MappingProxyType({"base": 1_600_000.0}),
    "ess_unit_cost": MappingProxyType({"base": 400_000.0}),
    "discount_rate": MappingProxyType({"base": 0.045}),
    "grid_purchase_price": MappingProxyType({"base": 100.0}),
    "surplus_sale_price": MappingProxyType({"base": 90.0}),
    "replacement_real_trend": MappingProxyType({"base": 0.0}),
    **design_levels(),
}


@pytest.fixture(scope="module")
def basis() -> CaseBasis:
    """실행 경로를 **한 번** 지난 결과 — 러너를 다시 조립하지 않는다."""
    return run_single_case_e2e(
        {}, level_map=_LEVEL_MAP, horizon_years=_PROBE_HORIZON
    ).basis


def _resource_names(basis: CaseBasis) -> frozenset[str]:
    """그 실행이 실제로 세운 자원의 이름 집합 — **결과에서 온다.**"""
    return frozenset(r.name for r in basis.resources)


@pytest.mark.contract
def test_the_two_namespaces_do_not_overlap(basis: CaseBasis) -> None:
    """전제 — 자원 이름과 짧은 코드는 **겹치지 않는다.**

    겹치면 아래 두 검사가 서로를 통과시킨다(포함과 배타가 같은 뜻이 된다).
    자원을 `"PV"` 라고 이름 짓는 날 이 검사가 먼저 빨간불이 난다.
    """
    names = _resource_names(basis)

    assert names, "자원이 하나도 없다 — 아래 검사들이 공허하게 통과한다"
    assert not (names & _SHORT_CODES), (
        f"자원 이름이 짧은 코드와 겹친다: {sorted(names & _SHORT_CODES)}"
    )


@pytest.mark.req("FR-104-AC5")
def test_one_off_flows_carry_a_resource_name(basis: CaseBasis) -> None:
    """① `OneOffLine.resource_name` 은 **그 실행의 자원 이름 집합에 속한다.**

    붙임 8 이 이 값으로 조인한다 — 속하지 않으면 그 조인이 빈 교집합을 내고
    이미 계상된 교체비·잔존가치가 **「미반영」으로 인쇄된다.** 아무 예외도
    나지 않는다.
    """
    names = _resource_names(basis)
    flows = basis.one_off_flows

    assert flows, (
        "일회성 흐름이 하나도 없다 — 배선이 끊겼거나 탐침 분석기간이 짧다. "
        "이 상태에서는 이 검사가 아무것도 재지 않는다"
    )
    off_convention = sorted(
        {line.resource_name for line in flows} - names
    )
    assert not off_convention, (
        f"자원 이름 규약을 벗어난 값: {off_convention} — "
        f"그 실행의 자원 이름은 {sorted(names)} 이다"
    )


@pytest.mark.req("FR-1001-AC3")
def test_cost_and_benefit_lines_carry_a_short_code(basis: CaseBasis) -> None:
    """② `CostLine`·`BenefitLine` 의 `resource_code` 는 **자원 이름이 아니다.**

    밖에서 고정한 짧은 코드 집합에 속하고, 자원 이름 집합에는 **속하지
    않는다.** 여기서 자원 이름이 나오기 시작하면 두 규약이 한 이름공간으로
    뭉개진 것이고, 그때 붙임 4 의 표는 종전과 다른 문면을 인쇄한다
    (골든·수용 검사가 그 문면을 본다).
    """
    names = _resource_names(basis)
    codes = {line.resource_code for line in basis.costs} | {
        line.resource_code for line in basis.benefits
    }

    assert basis.costs and basis.benefits, "항목이 비었다 — 검사가 공허하다"
    assert not (codes & names), (
        f"짧은 코드 자리에 자원 이름이 들어 있다: {sorted(codes & names)}"
    )
    assert codes <= _SHORT_CODES, (
        f"밖에서 고정한 짧은 코드 목록에 없는 값: {sorted(codes - _SHORT_CODES)} — "
        "코드가 늘었으면 이 파일의 `_SHORT_CODES` 를 **손으로** 늘리십시오"
    )
