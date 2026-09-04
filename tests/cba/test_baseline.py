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


#: 갈래를 **읽어야 하는 실행 경로 두 자리** — 아래 뒤집힌 래칫이 이름으로 붙든다.
#:
#: ⚠ **「0곳이 아니다」만으로는 부족하다.** 어딘가 한 곳이 읽으면 참이 되는데,
#: 이 축이 뜻하는 것은 *「평가를 돌릴 때 갈래를 고를 수 있다」* 이므로 **고르는
#: 자리**(시나리오 yaml 을 읽는 조립기)와 **계산하는 자리**(러너 진입점)가 둘 다
#: 읽어야 한다. 한쪽만 남으면 「고를 수는 있는데 계산이 안 본다」 또는 「계산은
#: 보는데 고를 통로가 없다」가 되고, 둘 다 이 저장소가 반복해 만난 형태다.
#:
#: ⚠ 파일을 옮기면 이 목록도 함께 고쳐야 한다 — **일부러 그렇게 두었다.** 배선이
#: 사라지는 것과 자리가 바뀌는 것은 다른 사건이고, 후자는 사람이 한 번 보는 것이
#: 맞다(`scripts/check_docstring_references.py` 가 같은 판단을 한다).
_MUST_READ_THE_ARRANGEMENT: tuple[str, ...] = (
    "core/casegrid/e2e_runner.py",
    "core/report/case_report.py",
)


@pytest.mark.req("FR-705-AC2")
def test_baseline_arrangement_ratchet() -> None:
    """★★★ **뒤집힌 래칫** — 갈래를 읽는 배포 코드가 **다시 0곳이 되지 않는다**.

    ## 이 시험은 뒤집혔다 (R60/WP-2 · 2026-09-04)

    종전 문면은 `usages == 0` 이었고 스스로 뒤집는 조건을 적어 두었다:

        「기준선 갈래가 처음 지정됐다. 이 시험을 지우지 말고 뒤집되,
         ① 그 갈래의 Without 이 실제로 계산에 쓰이는지
         ② 「나」면 계측 전제와 포기 항이 함께 섰는지를 **검사로 먼저 세워라**」

    **그 둘을 먼저 세우고 뒤집었다.** ①·② 를 재는 검사는
    `tests/report/test_baseline_arrangement_wiring.py` 넷이며 **구현보다 앞선
    커밋**에 들어갔다(`NFR-105-M3` 가 재는 순서):

        T1  필드가 없으면 ⓑ(`MAINTAIN`)로 돈다 — 부재 ≡ 명시한 ⓑ (원 단위 일치)
        T2  ① ⓐ 를 고르면 자가소비가 0 이 되어 `npv` 가 ⓑ 와 **다르다**
            실측 ⓑ −11,537,129원 · ⓐ −10,743,661원 (차 +793,468원)
        T3  ② ⓒ 는 실행 경로가 `DV-15` 로 **거부**한다 — 계측 전제도 포기 항도
            서지 않았으므로 **고를 수 없는 것이 옳다**(0 으로 채우지 않았다)
        T4  리포트(붙임 1 셋째 표)가 고른 갈래의 선언 다섯을 인쇄한다

    ⚠ **종전 문면의 경고(*「갈래를 정하는 순간 요금 거래가 새로 서서 결론축이
    움직인다」*)는 아직 실현되지 않았다.** 기본값이 ⓑ 이고 ⓑ 의 자가소비 처리가
    현행 러너 동작(소거)과 같으므로 **골든 3건은 한 원도 움직이지 않았다.**
    요금 거래(사업자 판매수익·사용자 요금)를 모형에 세우는 것은 이 WP 가 하지
    않았고, 그날 결론축이 움직인다 — 그 경고는 살아 있다.

    ## 무엇을 재는가

    `core/` 안에서 `BaselineArrangement` 를 **이름으로 만지는** 자리를 `ast` 로
    센다(선언 파일 자신은 뺀다 — 종전과 같은 규칙이다). 문자열이 아니라 `ast` 인
    이유도 종전과 같다: 주석·독스트링의 언급이 소비자로 세어지면 래칫이 조용히
    초록불이 된다.
    """
    import ast
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent.parent
    core_dir = project_root / "core"

    readers: dict[str, int] = {}
    for path in core_dir.rglob("*.py"):
        if path.name == "baseline.py" and path.parent.name == "cba":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        hits = sum(
            1
            for node in ast.walk(tree)
            if (isinstance(node, ast.Name) and node.id == "BaselineArrangement")
            or (isinstance(node, ast.Attribute) and node.attr == "BaselineArrangement")
        )
        if hits:
            readers[path.relative_to(project_root).as_posix()] = hits

    assert readers, (
        "갈래를 읽는 배포 코드가 다시 0곳이 됐다 — 선언만 남고 실행 경로가 "
        "그것을 보지 않는 상태다(이 저장소가 다섯 번 밟은 형태 · "
        "scripts/check_unread_extension_points.py 머리말). 배선을 지웠다면 "
        "tests/report/test_baseline_arrangement_wiring.py 넷도 함께 빨간불일 "
        "것이다 — 그쪽을 먼저 보라"
    )
    missing = [name for name in _MUST_READ_THE_ARRANGEMENT if name not in readers]
    assert not missing, (
        f"실행 경로가 갈래를 읽지 않는다: {missing} — 읽는 곳은 "
        f"{sorted(readers)} 다. 「고르는 자리」와 「계산하는 자리」가 둘 다 "
        "읽어야 이 축이 성립한다(위 _MUST_READ_THE_ARRANGEMENT 주석)"
    )
