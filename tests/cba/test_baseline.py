"""10.5 — 기준선 증분 (FR-705-AC1).

설비 미설치 기준선을 명시적으로 계산·표시. **기준선이 없으면 증분의 타당성을
검증할 수 없다** (도메인 원칙 1-2).
"""
from __future__ import annotations

import pytest

from core.cba.baseline import (
    assert_baseline_displayed,
    compare_baseline_vs_new,
    compute_incremental,
)
from core.cba.proforma import benefit_row
from core.contracts.units import Money


@pytest.mark.req("FR-705-AC1")
def test_incremental_is_new_minus_baseline() -> None:
    """편익 증분 = new − baseline. 비용 항목은 음수 편익으로 모델링 (도메인 원칙 1-1).

    오라클: 순위 1 (정의 항등식). 전기요금 비용이 baseline 300만 → new 120만으로
    줄면 «비용» 행은 baseline=-3M, new=-1.2M (음수). 증분 = new − baseline = +1.8M (절감 = 편익).
    """
    baseline = [benefit_row(tag="elec_bill", schedule={1: -3_000_000})]  # 비용=음수
    new = [benefit_row(tag="elec_bill", schedule={1: -1_200_000})]
    comparison = compare_baseline_vs_new(baseline, new)
    assert comparison.incremental_total() == Money(1_800_000)


def test_baseline_must_be_displayed() -> None:
    """기준선 자체 비용이 리포트에 표시되어야 한다 (FR-705-AC1).

    오라클: 순위 4 (정의 항등식 — 표시 여부). 기준선 행이 있고 총액이 0 이
    아니면 표시된 것이다.
    """
    baseline = [benefit_row(tag="baseline", schedule={1: 3_000_000})]
    new = [benefit_row(tag="baseline", schedule={1: 1_200_000})]
    comparison = compare_baseline_vs_new(baseline, new)
    assert_baseline_displayed(comparison)  # 예외 없으면 통과
    assert comparison.baseline_total() == Money(3_000_000)


def test_missing_baseline_raises() -> None:
    """기준선 없으면 assert_baseline_displayed 가 예외 — FR-705-AC1 위반."""
    comparison = compare_baseline_vs_new([], [benefit_row(tag="x", schedule={1: 100})])
    with pytest.raises(ValueError, match="기준선이 표시되지 않았다"):
        assert_baseline_displayed(comparison)


def test_incremental_handles_tag_only_in_new() -> None:
    """new 에만 있는 tag — baseline 0, new 그대로 (증가)."""
    baseline = [benefit_row(tag="A", schedule={1: 100})]
    new = [
        benefit_row(tag="A", schedule={1: 100}),
        benefit_row(tag="B", schedule={1: 50}),
    ]
    inc = compute_incremental(baseline, new)
    inc_tags = {r.tag for r in inc}
    assert "B" in inc_tags


def test_incremental_baseline_is_realistic_alternative() -> None:
    """기준선은 «현실적 대안» (도메인 원칙 1-3).

    히트펌프 기준선은 «난방 안 함» 이 아니라 «기존 보일러 유지» —
    기준선에 연료비(음수 편익)가 있다. 절감 = new − baseline.
    """
    # 기존 보일러 연료비 200만/년 (비용 = 음수 편익)
    baseline = [benefit_row(tag="fuel_cost", schedule={y: -2_000_000 for y in range(1, 6)})]
    # 히트펌프 전력비 80만/년 (비용 = 음수, 더 작음)
    new = [benefit_row(tag="fuel_cost", schedule={y: -800_000 for y in range(1, 6)})]
    comparison = compare_baseline_vs_new(baseline, new)
    # 증분 = 매년 120만 절감 × 5년 = 600만 (양수 편익)
    assert comparison.incremental_total() == Money(6_000_000)


@pytest.mark.req("FR-705-AC2")
def test_pool_branch_is_rejected() -> None:
    """「나」(자가용 집합자원화) 갈래를 고르면 거부한다 (FR-705-AC2 · DV-15).

    ⚠ **거부가 옳다.** 판정 정본 §2 는 *「계측이 갈리지 않으면 「나」는 **평가할 수
    없다**」* 고 적는다 — **「평가할 수 없다」와 「0 이다」는 다른 말이다.** 거부
    메시지가 두 사유(구분 계측 · 대칭 항)를 **둘 다** 들고 있어야 한다.
    """
    from core.cba.baseline import BaselineArrangement, get_baseline_branch
    from core.contracts.validation import ValidationError

    with pytest.raises(ValidationError, match="계측 전제가 안 섰다") as excinfo:
        get_baseline_branch(BaselineArrangement.POOL)
    assert excinfo.value.rule == "DV-15"
    assert "대칭 항이 없다" in excinfo.value.reason, (
        "거부 사유가 계측 전제 하나만 들고 있다 — 대칭성(판정 정본 §4④ · 총괄지침 "
        "제45조③)이 빠지면 「집합자원화 대가만 세우고 포기분은 안 센다」가 통과한다"
    )
    assert "0 으로 채우지 마십시오" in excinfo.value.action


@pytest.mark.req("FR-705-AC2")
def test_other_two_branches_are_declared_and_not_rejected() -> None:
    """나머지 둘은 선언이 서 있고 거부되지 않는다 (FR-705-AC2).

    ⚠ **거부만 검사하면 「전부 거부한다」도 통과한다.** 셋 중 둘이 실제로 통과하는
    것을 함께 재야 그 거부가 「이 갈래만」이라는 뜻이 된다.
    """
    from core.cba.baseline import (
        BaselineArrangement,
        SelfConsumptionTreatment,
        get_baseline_branch,
    )

    none_branch = get_baseline_branch(BaselineArrangement.NONE)
    assert none_branch.self_consumption_treatment is SelfConsumptionTreatment.NONE
    assert none_branch.without_description == "한전 전력 전량"

    keep_branch = get_baseline_branch(BaselineArrangement.MAINTAIN)
    assert keep_branch.self_consumption_treatment is SelfConsumptionTreatment.CANCEL_OUT
    assert "자가용 자가소비" in keep_branch.without_description
    assert "자가용 자가소비" in keep_branch.with_description, (
        "「가」는 자가소비가 Without·With 양쪽에 똑같이 있어 차액에서 소거된다 "
        "(판정 정본 §1 둘째) — 한쪽에만 적으면 그 소거가 성립하지 않는다"
    )


@pytest.mark.req("FR-705-AC2")
def test_baseline_arrangement_ratchet() -> None:
    """기준선 갈래가 처음 지정됐다. 이 시험을 지우지 말고 뒤집되,
    ① 그 갈래의 Without 이 실제로 계산에 쓰이는지 ② 「나」면 계측 전제와 포기 항이
    함께 섰는지를 검사로 먼저 세워라. ⚠ 갈래를 정하는 순간 요금 거래가 새로 서서
    결론축이 움직인다.
    """
    import ast
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent.parent
    core_dir = project_root / "core"

    usages = 0
    for path in core_dir.rglob("*.py"):
        if path.name == "baseline.py" and path.parent.name == "cba":
            continue
        code = path.read_text(encoding="utf-8")
        tree = ast.parse(code, filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Name) and node.id == "BaselineArrangement") or (
                isinstance(node, ast.Attribute) and node.attr == "BaselineArrangement"
            ):
                usages += 1

    assert usages == 0, (
        "기준선 갈래가 처음 지정됐다. 이 시험을 지우지 말고 뒤집되, "
        "① 그 갈래의 Without 이 실제로 계산에 쓰이는지 ② 「나」면 계측 전제와 포기 항이 "
        "함께 섰는지를 검사로 먼저 세워라. ⚠ 갈래를 정하는 순간 요금 거래가 새로 서서 "
        "결론축이 움직인다."
    )
