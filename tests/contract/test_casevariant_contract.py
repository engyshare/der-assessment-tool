"""케이스 변형 계약 — FR-607-AC1 · FR-607-AC3 · FR-606-AC1.

**「자동 포함」이 호출자의 기억이 아니라 구조가 되었는가**를 본다.

R15 까지 기준선은 `build_capex_cashflows(..., is_baseline=True)` 라는
**호출자가 손으로 넘기는 깃발**이었다. 안 넘기면 기준선은 그냥 없고,
빠졌을 때 나는 증상이 없다 — 기준선 없는 결과도 완전한 결과처럼 보인다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

import pytest

from core.casegrid.variants import run_order, variant_registry
from core.contracts.casevariant import CaseVariant, ordered_variants


class _Fake(CaseVariant):
    """정렬·기준선 규칙 검증용."""

    tag: ClassVar[str] = "_fake"
    label: ClassVar[str] = "가짜"

    def overrides(self, base: Mapping[str, Any]) -> dict[str, Any]:
        return {}


def _variant(tag: str, *, order: int, baseline: bool) -> type[CaseVariant]:
    return type(
        f"_V{tag}",
        (_Fake,),
        {"tag": tag, "label": tag, "order": order, "baseline": baseline},
    )


@pytest.mark.contract
@pytest.mark.req("FR-607-AC1")
def test_the_baseline_is_always_present_and_first() -> None:
    """★ 기준선이 **자동으로** 목록에 있고 **맨 위**다.

    호출자가 넘기는 것이 아니라 등록된 변형 목록의 성질이므로, 빠뜨리려면
    파일을 지워야 하고 그러면 아래 `test_...refused` 가 빨간불이 된다.
    """
    order = run_order()
    assert order, "변형이 하나도 등록되지 않았다"
    assert order[0].baseline is True
    assert order[0].tag == "unsupported"
    assert "FR-607-AC1" in order[0].clauses


@pytest.mark.contract
@pytest.mark.req("FR-606-AC1")
def test_the_planned_case_runs_alongside_the_baseline() -> None:
    """지원안 케이스와 기준선이 **한 목록에** 있다.

    FR-606-AC1 의 *「이 모드에서도 무지원 기준선은 함께 표시된다」* 가
    이것으로 표현된다 — 하나만 도는 경로가 없다.
    """
    tags = [cls.tag for cls in run_order()]
    assert tags == ["unsupported", "as_planned"]


@pytest.mark.contract
@pytest.mark.req("FR-607-AC1")
def test_missing_or_duplicated_baseline_is_refused() -> None:
    """기준선이 없거나 둘이면 **오류다.**

    둘 다 조용한 실패다 — 빠진 기준선은 결과에 아무 흔적을 남기지 않고,
    읽는 사람은 지원안 케이스를 기준선으로 읽는다.
    """
    with pytest.raises(ValueError, match="기준선 변형이 없습니다"):
        ordered_variants({"a": _variant("a", order=0, baseline=False)})

    with pytest.raises(ValueError, match="둘 이상"):
        ordered_variants(
            {
                "a": _variant("a", order=0, baseline=True),
                "b": _variant("b", order=1, baseline=True),
            }
        )


@pytest.mark.contract
@pytest.mark.req("FR-607-AC1")
def test_baseline_not_on_top_is_refused() -> None:
    """기준선이 있어도 **맨 위가 아니면** 조항 위반이다.

    「결과 상단에 표시」는 있고 없고의 문제가 아니라 순서의 문제다.
    """
    with pytest.raises(ValueError, match="맨 위가 아닙니다"):
        ordered_variants(
            {
                "a": _variant("a", order=1, baseline=True),
                "b": _variant("b", order=0, baseline=False),
            }
        )


@pytest.mark.contract
@pytest.mark.req("FR-607-AC3")
def test_baseline_zeroes_only_this_projects_support() -> None:
    """★ 기준선이 끄는 것은 **본 사업 지원뿐**이다 (FR-607-AC3).

    타 사업으로 **확정** 지원된 설비는 기준선에 **포함된 소여**다 — 이미
    받기로 확정된 ESS 를 없는 셈 치고 산출한 보조율은 실제로 필요한 금액이
    아니기 때문이다. `prefunded_*` 를 건드리면 그 정의가 깨진다.
    """
    baseline = variant_registry()["unsupported"]()
    overrides = baseline.overrides({"subsidy_rate": 0.5, "prefunded_capex_won": 3_000_000})

    assert overrides["subsidy_rate"] == 0.0
    assert overrides["loan_rate"] == 0.0
    assert "prefunded_capex_won" not in overrides, (
        "타 사업 확정 지원분을 건드렸다 — FR-607-AC3 의 기준선 정의가 깨진다"
    )


@pytest.mark.contract
@pytest.mark.req("FR-607-AC1")
def test_variants_return_only_what_they_change() -> None:
    """변형은 **덮어쓰는 것만** 돌려준다.

    전체 입력을 다시 만들면 기준 입력에 항목이 하나 늘 때 모든 변형이
    그것을 따라 늘려야 하고, 빠뜨린 변형은 그 항목이 조용히 사라진 채로
    계산된다.
    """
    base = {"subsidy_rate": 0.5, "discount_rate": 0.045, "horizon": 20}
    for cls in run_order():
        overrides = cls().overrides(base)
        assert set(overrides) <= set(base) | {
            "subsidy_fixed_won",
            "loan_rate",
        }, f"{cls.tag}: 기준 입력에 없는 키를 만들어 냈다"
