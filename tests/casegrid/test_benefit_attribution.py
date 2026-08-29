"""편익 금액이 **수량대로** 자원에 갈리는가 — 4.3 귀속 (R43-E2).

## 무엇을 붙드는가

4.3 은 편익을 `line.tag in resource.produces` 로 실으면서 표 아래에 **스스로**
*「편익이 자원에 1:1 로 귀속될 때」* 라고 적었다. 기준 구성에서 그 조건이
거짓이었다 — 잉여 판매의 근거 수량인 계통 송전 18.80kWh 중 8.00kWh 는 저장장치
방전분인데 표는 전액을 태양광 몫으로 적었다. 그 귀속을 수량으로 가른 것이
`core/casegrid/attribution.py` 이고, 이 파일이 **가르는 규칙**을 잰다.

## 공통 §4 의 네 물음

① **정본이 어디서 오는가** — 안분 규칙 검사는 **손으로 지은 운전**을 쓴다.
   기대값(몫과 잔차)은 이 파일이 **밖에서 고정**하며 실행에서 뽑지 않는다 —
   뽑아 오면 검사가 자기 오라클을 만들고 규칙이 바뀔 때 함께 따라간다.
   배선 검사(마지막 둘)만 실행 경로를 지나며, 거기서 재는 것은 **금액이 아니라
   항등식**이다(귀속 합 = 연 편익 합계).
② **이 설명이 이 검사에 걸리는가** — 아니다. 소스 문면을 보지 않는다.
③ **이름보다 넓게 주장하는가** — 아니다. 이 파일은 *가르는 규칙*과 *합계
   보존*만 잰다. 인쇄된 문면이 참인지는 `tests/report/test_narrative.py` 다.
④ **수와 그 조건의 짝** — 100원을 셋으로 가른 33·33·34 는 **`to_won` 사사오입
   뒤 잔차를 최종 몫에 가산한다**는 규약의 값이다. 규약이 바뀌면 이 수가 먼저
   틀려야 한다.
"""
from __future__ import annotations

from types import MappingProxyType

import pytest

from core.casegrid.attribution import (
    RESIDUAL_HOLDER_INDEX,
    attribute_benefits,
    export_share_kwh,
)
from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import design_levels
from core.casegrid.models import BenefitLine, ResourceLine
from core.contracts.der import DispatchResult
from core.contracts.engine import SystemDispatch

#: 창을 읽는 편익의 태그. **밖에서 고정한다** — 실행에서 모아 오면 이 목록이
#: 「러너가 지금 넘기는 값」이 되어 무엇과도 어긋날 수 없다.
_WINDOW_TAG = "Window"
#: 창을 읽지 않는 편익의 태그. 선언된 자원에 전액 가야 한다.
_DECLARED_TAG = "Declared"

#: 대장을 읽지 않는다 — 배선 검사가 보는 것은 금액이 아니라 항등식이다.
_LEVEL_MAP = {
    "pv_unit_cost": MappingProxyType({"base": 1_600_000.0}),
    "ess_unit_cost": MappingProxyType({"base": 400_000.0}),
    "discount_rate": MappingProxyType({"base": 0.045}),
    "grid_purchase_price": MappingProxyType({"base": 100.0}),
    "surplus_sale_price": MappingProxyType({"base": 90.0}),
    "replacement_real_trend": MappingProxyType({"base": 0.0}),
    **design_levels(),
}

#: 잉여 판매의 태그. **밖에서 고정한다** — 실행에서 뽑으면 이 편익이 사라져도
#: 아래 검사가 조용히 통과한다.
_SURPLUS_TAG = "SurplusSale"


def _steps(*values: float) -> DispatchResult:
    n = len(values)
    return DispatchResult(
        electric=list(values), heat=[0.0] * n, cool=[0.0] * n, fuel=[0.0] * n
    )


def _resource(name: str, *, produces: tuple[str, ...] = ()) -> ResourceLine:
    """제원은 이 검사가 보는 것이 아니다 — 이름과 `produces` 만 뜻이 있다."""
    return ResourceLine(
        name=name,
        kind=name,
        capacity="—",
        operating_mode="—",
        lifetime_years=20,
        unit_capex="—",
        capex_won=0,
        fixed_om_won_per_year=0,
        produces=produces,
    )


def _benefit(tag: str, annual_won: int, resource_code: str = "") -> BenefitLine:
    return BenefitLine(
        tag=tag,
        label=tag,
        annual_won=annual_won,
        resource_code=resource_code,
        formula="—",
    )


def test_the_export_share_is_taken_step_by_step_not_from_daily_totals() -> None:
    """★★ **스텝마다 가른다 — 하루 합계로 가르면 충전이 송전 몫을 받는다.**

    아래 운전은 그 차이가 드러나도록 지었다. 저장장치는 0스텝에서 **충전**
    (−1.0)하고 1스텝에서만 **방전**(2.0)한다.

        하루 합계로 가르면   PV 4.0 · ESS 1.0  →  ESS 몫 20%
        스텝마다 가르면      PV 3.0 · ESS 2.0  →  ESS 몫 40%

    기준 구성이 정확히 이 형태다(심야 충전 · 오후 방전). 합계로 가르면 저장
    장치 몫이 절반 이하로 줄고, 그 차이는 표에서 그럴듯하게 보인다.
    """
    dispatch = SystemDispatch(
        per_resource={"pv": _steps(3.0, 1.0), "ess": _steps(-1.0, 2.0)},
        grid_import=[1.0, 0.0],
        grid_export=[2.0, 3.0],
    )

    share = export_share_kwh(dispatch)

    assert share == pytest.approx({"pv": 3.0, "ess": 2.0}), (
        "송전 몫이 스텝별 양의 출력 비례가 아니다 — 하루 합계로 가르면 "
        "PV 4.0 · ESS 1.0 이 된다"
    )


def test_a_charging_resource_never_takes_a_share_of_the_export() -> None:
    """음수(충전·소비)는 0으로 클램프한다 — 클램프하지 않으면 몫이 100%를 넘는다."""
    dispatch = SystemDispatch(
        per_resource={"pv": _steps(3.0), "ess": _steps(-1.0)},
        grid_import=[0.0],
        grid_export=[2.0],
    )

    share = export_share_kwh(dispatch)

    assert share["ess"] == 0.0, "충전 중인 자원이 송전 몫을 받았다"
    assert share["pv"] == pytest.approx(2.0), (
        "음수를 그대로 더하면 분모가 2.0 이 되어 PV 몫이 송전량을 넘는다"
    )


def test_a_window_benefit_is_split_by_quantity_and_a_declared_one_is_not() -> None:
    """★ 창을 읽는 편익만 갈린다 — **가를지 말지는 편익이 선언한다.**

    ⚠ 기대값을 밖에서 고정한다: 송전 5.00kWh 중 PV 3.00 · ESS 2.00 이므로
    1,000원은 **600원 / 400원** 이다. 창을 읽지 않는 500원은 선언된 자원
    (`produces`)에 **전액** 간다.
    """
    dispatch = SystemDispatch(
        per_resource={"pv": _steps(3.0, 1.0), "ess": _steps(-1.0, 2.0)},
        grid_import=[1.0, 0.0],
        grid_export=[2.0, 3.0],
    )
    resources = (_resource("pv"), _resource("ess", produces=(_DECLARED_TAG,)))

    rows = attribute_benefits(
        [_benefit(_WINDOW_TAG, 1_000), _benefit(_DECLARED_TAG, 500)],
        dispatch=dispatch,
        export_window_tags=frozenset({_WINDOW_TAG}),
        resources=resources,
    )

    assert [(r.tag, r.resource_name, r.annual_won) for r in rows] == [
        (_WINDOW_TAG, "pv", 600),
        (_WINDOW_TAG, "ess", 400),
        (_DECLARED_TAG, "ess", 500),
    ]
    assert all(row.basis_note for row in rows), (
        "안분 근거 문면이 비었다 — 비면 4.3 이 성립 조건을 다시 문장으로 박게 된다"
    )


def test_the_rounding_residual_goes_to_the_last_share_so_the_total_is_exact() -> None:
    """★★ **합계는 원 단위로 보존된다** (`NFR-103-M1`).

    100원을 셋으로 나누면 몫이 33.33…원이고 사사오입하면 33·33·33 = **99원**
    이다. 남는 1원을 흘리면 4.3 의 「연 편익」 열 합이 프로포마가 쓴 편익보다
    작아지고, 합계를 적지 않는 표에서 그 차이는 아무에게도 보이지 않는다.
    잔차는 규약대로 **최종 몫**이 받는다.
    """
    dispatch = SystemDispatch(
        per_resource={"a": _steps(1.0), "b": _steps(1.0), "c": _steps(1.0)},
        grid_import=[0.0],
        grid_export=[3.0],
    )
    resources = (_resource("a"), _resource("b"), _resource("c"))

    rows = attribute_benefits(
        [_benefit(_WINDOW_TAG, 100)],
        dispatch=dispatch,
        export_window_tags=frozenset({_WINDOW_TAG}),
        resources=resources,
    )

    assert [row.annual_won for row in rows] == [33, 33, 34]
    assert sum(row.annual_won for row in rows) == 100
    assert rows[RESIDUAL_HOLDER_INDEX].resource_name == "c", (
        "잔차를 받는 자리가 규약(최종 몫)에서 벗어났다"
    )


def test_a_benefit_with_no_export_to_split_keeps_its_declared_owner() -> None:
    """송전이 0이면 **가를 근거가 없다** — 선언 귀속으로 두고 그 사실을 적는다.

    가를 수 없는 것을 조용히 0원으로 만들면 편익이 표에서 사라진다.
    """
    dispatch = SystemDispatch(
        per_resource={"pv": _steps(0.0)}, grid_import=[0.0], grid_export=[0.0]
    )

    rows = attribute_benefits(
        [_benefit(_WINDOW_TAG, 1_000)],
        dispatch=dispatch,
        export_window_tags=frozenset({_WINDOW_TAG}),
        resources=(_resource("pv", produces=(_WINDOW_TAG,)),),
    )

    assert [(r.resource_name, r.annual_won) for r in rows] == [("pv", 1_000)]
    assert "0kWh" in rows[0].basis_note, (
        "가를 근거가 없었다는 사실이 문면에 없다 — 「가르지 않기로 했다」와 "
        "「가를 수 없었다」가 표에서 같아 보인다"
    )


@pytest.mark.req("FR-1001-AC2")
def test_the_pipeline_attributes_every_won_of_the_annual_benefit() -> None:
    """★★ **실행 경로가 귀속을 채우고, 그 합이 연 편익 합계와 원 단위로 같다.**

    자료형에 칸을 만들어도 러너가 채우지 않으면 4.3 의 「연 편익」 열이 통째로
    0원이 되고, **그 상태가 아무 예외도 내지 않는다.** 여기가 그 통로를 잰다.

    ⚠ 금액을 오라클로 적지 않는다 — 재는 것은 **항등식**이다. 이 케이스의
    실제 금액과 회수기간은 골든 실행을 보는 `tests/report/test_narrative.py`
    가 밖에서 고정한다.
    """
    basis = run_single_case_e2e({}, level_map=_LEVEL_MAP, horizon_years=20).basis

    assert basis.benefit_attributions, "실행이 편익 귀속을 채우지 않았다"
    assert sum(s.annual_won for s in basis.benefit_attributions) == (
        basis.annual_benefit_won
    ), "자원별 귀속 합이 연 편익 합계와 다르다 — 원 단위로 같아야 한다"

    names = {resource.name for resource in basis.resources}
    assert {s.resource_name for s in basis.benefit_attributions} <= names, (
        "귀속이 자원 이름이 아닌 값으로 실렸다 — 4.3 의 조인이 빈 교집합이 된다"
    )
    assert {s.tag for s in basis.benefit_attributions} == {
        line.tag for line in basis.benefits
    }, "편익 갈래 중 귀속이 없는 것이 있다 — 그 금액이 4.3 에서 사라진다"


def test_the_surplus_sale_is_not_attributed_to_the_pv_alone() -> None:
    """★★★ **가-2 그 자체** — 저장장치가 내보낸 몫이 태양광 편익으로 실리는가.

    실행 경로에서 잉여 판매가 **자원 하나에만** 실리면 이 구성의 성립 조건
    (「1:1 귀속」)이 거짓인 채로 표가 인쇄된다. 이 단언이 그 상태를 거부한다.
    """
    basis = run_single_case_e2e({}, level_map=_LEVEL_MAP, horizon_years=20).basis

    surplus = [s for s in basis.benefit_attributions if s.tag == _SURPLUS_TAG]
    assert len(surplus) >= 2, (
        "잉여 판매가 자원 하나에만 귀속됐다 — 이 구성의 계통 송전에는 저장장치 "
        "방전분이 섞여 있으므로 그 귀속은 거짓이다"
    )
    assert all(row.annual_won > 0 for row in surplus), (
        "송전에 기여한 자원의 몫이 0원이다"
    )
