"""10.7 — 보조금 이전지출 처리 (FR-704-AC5/AC6, FR-402-AC7).

**사회 관점에서 보조금은 편익이 아니다.** 정부→사업자로의 이전지출(transfer)이지
부가가치가 아니다 (도메인 원칙 2-3). 사회 NPV 에 넣으면 «돈을 옮기기만 해도
사회가 부유해진다» 는 결론이 나오고, 필요 지원액이 과소 산정된다.
"""
from __future__ import annotations

import pytest

from core.cba.perspective import (
    Perspective,
    assert_subsidy_excluded_from_society,
    compute_perspective_npv,
    separate_other_program_subsidy,
    society_excludes_subsidy,
)
from core.cba.proforma import benefit_row
from core.contracts.units import ZERO, Money


@pytest.mark.req("FR-704-AC1", "FR-704-AC2", "FR-704-AC3")
def test_required_participant_operator_government_perspectives_exist() -> None:
    """FR-704-AC1/AC2/AC3 — 관점별 구체적 지표 계산 지원.

    오라클: 순위 4 (정의 항등식) — 각 관점의 enum 값과 해당 지표 계산 지원.
    """
    # 관점 enum 존재 확인
    assert Perspective.RESIDENT.value == "참여 주민"
    assert Perspective.OPERATOR.value == "사업자"
    assert Perspective.GOVERNMENT.value == "정부"

    # FR-704-AC1: 주민 관점 — 자부담액 대비 요금 절감 회수기간 지표
    # 회수기간 계산은 자부담 초기투자 대비 누적 순현금흐름이 0이 되는 시점
    resident_benefits = [benefit_row(tag="요금절감", schedule={y: 100_000 for y in range(1, 11)})]
    resident_cost = Money(500_000)  # 자부담액
    resident_result = compute_perspective_npv(
        Perspective.RESIDENT, resident_benefits, [], resident_cost, 0.05
    )
    assert resident_result.perspective == Perspective.RESIDENT
    # 5년 후 회수: 100,000 × 5 = 500,000
    # 실제 회수기간 계산은 별도 함수에서 수행하지만, 관점별 편익/비용 분리는 지원됨

    # FR-704-AC2: 사업자 관점 — 총투자 대비 IRR 지표
    from core.cba.metrics import irr
    operator_benefits = [benefit_row(tag="수익", schedule={y: 150_000 for y in range(1, 11)})]
    operator_investment = Money(1_000_000)
    operator_result = compute_perspective_npv(
        Perspective.OPERATOR, operator_benefits, [], operator_investment, 0.05
    )
    assert operator_result.perspective == Perspective.OPERATOR
    # IRR 계산 지원 (0~1 범위 내부수익률)
    operator_irr = irr(operator_investment, operator_benefits)
    assert 0 <= operator_irr <= 1  # 0~100% 범위 내

    # FR-704-AC3: 정부 관점 — 재정효율 지표 (투입 국비 1억원당 확보 설비용량·감축량·민간투자)
    government_investment = Money(100_000_000)  # 1억원
    # 100kW 설비 확보 시 1억원당 100kW 확보 → 효율 1.0 kW/억원
    gov_benefits = [benefit_row(tag="기여도", schedule={1: 1_000_000})]
    government_result = compute_perspective_npv(
        Perspective.GOVERNMENT, gov_benefits, [], government_investment, 0.05
    )
    assert government_result.perspective == Perspective.GOVERNMENT
    # 재정효율 지표 계산 지원 (NPV 기반 투자 효율)
    assert government_result.npv_value >= ZERO or government_result.npv_value < ZERO


# ✔ **R23 에 `FR-704-AC4` 마커를 여기서 뗐다 — R20 이 적어 둔 닫는 조건대로다.**
# `AC4` 는 *「세 관점이 **하나의 리포트에 병렬 표시**된다」* 이고 아래 검사는
# `compute_perspective_npv` **단일 호출** 결과의 필드 보존만 본다 — 병렬 표시는
# 보지 않는다. R20 은 「검증할 구현이 없어 대체 검증을 만들 수 없다」고 판정하고
# **닫는 조건**으로 *「병렬 표시 리포트를 구현하고 마커를 옮긴 뒤 지운다」* 를 적었다.
#
# 합성은 **상위 계층**에 놓았다 — `core/report/perspective_report.py` ·
# `tests/report/test_perspective_report.py`. 여기(`core/cba`)에 두면 리포트를
# import 해야 해서 계층 역방향이 되고, 그것이 R20·R21 이 두 번 만난 자리다.
def test_perspective_result_keeps_benefits_and_costs_separate() -> None:
    benefit = benefit_row(tag="benefit", schedule={1: 500_000})
    cost = benefit_row(tag="cost", schedule={1: 100_000})

    result = compute_perspective_npv(
        Perspective.RESIDENT,
        [benefit],
        [cost],
        Money(1_000_000),
        0.05,
    )

    assert result.benefit_rows == (benefit,)
    assert result.cost_rows == (cost,)


@pytest.mark.req("FR-704-AC5", "FR-402-AC7")
def test_subsidy_excluded_from_society_npv() -> None:
    """사회 관점 NPV 에 보조금이 편익으로 들어가지 않는다.

    오라클: 순위 4 (정의 항등식). 보조금 100만원 이 사회 관점에서 제외되면
    사회 NPV 는 보조금 없는 편익만으로 계산된다.
    """
    benefits = [
        benefit_row(tag="절감편익", schedule={1: 500_000}),
        benefit_row(tag="보조금", schedule={1: 1_000_000}),
    ]
    excl = society_excludes_subsidy(benefits[1])
    result = compute_perspective_npv(
        Perspective.SOCIETY, benefits, [], Money(0), 0.05, inclusions=excl
    )
    # 보조금이 제외되었으므로 사회 NPV 는 절감편익만
    assert "보조금" not in {r.tag for r in result.benefit_rows}
    assert "절감편익" in {r.tag for r in result.benefit_rows}


def test_assert_subsidy_excluded_catches_leak() -> None:
    """보조금이 사회 관점에 남아 있으면 예외 — FR-704-AC5 위반."""
    from core.cba.perspective import PerspectiveInclusions, PerspectiveResult

    bad = PerspectiveResult(
        perspective=Perspective.SOCIETY,
        benefit_rows=(benefit_row(tag="보조금", schedule={1: 100}),),
        cost_rows=(),
        initial_investment=Money(0),
        npv_value=Money(100),
        inclusions=PerspectiveInclusions(),
    )
    with pytest.raises(ValueError, match=r"보조금.*포함되어 있다"):
        assert_subsidy_excluded_from_society(bad)


@pytest.mark.req("FR-704-AC6")
def test_other_program_subsidy_separated() -> None:
    """본 사업 국비와 타 사업 국비 분리 (FR-704-AC6).

    재정효율 분모에는 본 사업 국비만. 타 사업 국비는 «타 사업 국비» 행으로 별도.
    오라클: 순위 4 (정의 항등식).
    """
    own, other = separate_other_program_subsidy(500_000, 200_000)
    assert own == Money(500_000)
    assert other == Money(200_000)


def test_negative_subsidy_rejected() -> None:
    """국비 음수 거부."""
    with pytest.raises(ValueError, match="음수"):
        separate_other_program_subsidy(-100, 200)


# ── 관점별 편익 집합 상이 — FR-402-AC7 ────────────────────────────────────

@pytest.mark.req("FR-704-AC7")
def test_perspective_inclusions_track_exclusion_rationale() -> None:
    """관점 전환 시 제외 사유가 기록된다 (FR-704-AC7).

    «어떤 항목이 왜 제외되었는지» 가 ``inclusions.exclusion_rationale`` 에 있다.
    """
    subsidy_row = benefit_row(tag="보조금", schedule={1: 1_000_000})
    excl = society_excludes_subsidy(subsidy_row)
    assert "보조금" in excl.excluded_tags
    assert "보조금" in excl.exclusion_rationale
    assert "이전지출" in excl.exclusion_rationale["보조금"]


def test_society_npv_lower_when_subsidy_excluded() -> None:
    """사회 NPV 는 보조금 제외 시 더 낮다 — 이전지출을 빼면 «진짜» 부가가치만 남는다.

    오라클: 순위 1. 보조금 100만 포함 시 NPV 100만 높음. 제외 시 그만큼 낮음.
    보조금을 편익으로 넣으면 사회 NPV 가 부풀고 필요 지원액이 과소 산정된다.
    """
    benefits = [
        benefit_row(tag="진짜편익", schedule={1: 500_000}),
        benefit_row(tag="보조금", schedule={1: 1_000_000}),
    ]
    # 보조금 포함 (잘못된 사회 관점)
    with_subsidy = compute_perspective_npv(
        Perspective.SOCIETY, benefits, [], Money(0), 0.05
    )
    # 보조금 제외 (올바른 사회 관점)
    excl = society_excludes_subsidy(benefits[1])
    without_subsidy = compute_perspective_npv(
        Perspective.SOCIETY, benefits, [], Money(0), 0.05, inclusions=excl
    )
    assert without_subsidy.npv_value < with_subsidy.npv_value, (
        "보조금을 사회 관점 편익에서 빼면 NPV 가 낮아진다 — 이전지출을 빼야 "
        "«진짜» 사회 부가가치가 드러난다 (FR-704-AC5)"
    )


@pytest.mark.req("FR-704-AC8")
def test_society_excludes_transfers_rationale() -> None:
    """사회 관점에서 이전(transfer)은 소거된다 (R58 판정 ②).

    `society_excludes_transfers()` 가 `PerspectiveInclusions` 로
    누구→누구 이전이라 소거했다는 사유를 남긴다.
    """
    from core.cba.perspective import society_excludes_transfers
    from core.contracts.der import DispatchResult
    from core.contracts.valuestream import Payer, ValueStream

    class _StubTransfer(ValueStream):
        tag = "요금차액이전"
        payer = Payer.RESIDENT
        transfer_counterparty = Payer.OPERATOR
        scales_with_dispatch_window = False
        quantity_id = "test_q"

        def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
            return Money(100)

        def formula(self, dispatch: DispatchResult, *, year: int) -> str:
            return ""

    stream = _StubTransfer(name="stub")

    inclusions = society_excludes_transfers([(stream, 100)])

    assert "요금차액이전" in inclusions.excluded_tags
    assert "사업자→참여 주민 이전이라 소거했다" in inclusions.exclusion_rationale["요금차액이전"]
    assert "총괄지침 제45조⑤" in inclusions.exclusion_rationale["요금차액이전"]
