"""관점 3종 — 작업 10.6 / FR-704.

사업자·참여 주민·정부(재정) 3개 관점으로 편익·비용을 분리한다 (FR-704-AC1~AC4).
**관점 섞기가 가장 흔한 중복 오류** (도메인 원칙 2-3).

**보조금은 사회 관점에서 이전지출** (FR-704-AC5, 원칙 2-3). 편익으로 넣으면
«돈을 옮기기만 해도 사회가 부유해진다» 는 결론이 나오고, 그만큼 필요 지원액이
과소 산정된다.

**FR-704-AC6** — 타 사업 기지원 설비의 국비는 정부 관점 «재정효율 지표» 의
분모에서 제외하되 «타 사업 국비» 행으로 별도 병기. 이것을 섞으면 본 사업의
재정효율이 실제보다 나쁘게 나온다.

**FR-704-AC7** — 관점 전환 시 어떤 항목이 왜 포함/제외되었는지 리포트에 표시.
``PerspectiveInclusions`` 가 그 근거를 들고 있다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from core.cba.metrics import npv
from core.cba.proforma import aggregate
from core.contracts.schemas import CashFlowRow
from core.contracts.units import ZERO, Money
from core.contracts.valuestream import ValueStream


class Perspective(StrEnum):
    """3 관점 (FR-704-AC1~AC3). 어휘는 spec FR-704 본문."""

    RESIDENT = "참여 주민"
    OPERATOR = "사업자"
    GOVERNMENT = "정부"
    #: 사회 관점 — 보조금 이전지출 처리의 기준. FR-704-AC5.
    SOCIETY = "사회"


@dataclass(frozen=True)
class PerspectiveInclusions:
    """한 관점에서 «무엇을 왜 포함/제외했는가»» (FR-704-AC7).

    리포트가 «관점 전환 시 어떤 항목이 왜 포함/제외되었는지» 를 표시하려면
    이 자료가 있어야 한다. 빈 문자열이면 «포함 사유 없음(표시 안 함)».
    """

    included_tags: tuple[str, ...] = ()
    excluded_tags: tuple[str, ...] = ()
    inclusion_rationale: dict[str, str] = field(default_factory=dict)
    exclusion_rationale: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PerspectiveResult:
    """한 관점의 CBA 결과 — 편익/비용 행 + NPV + 포함 근거."""

    perspective: Perspective
    benefit_rows: tuple[CashFlowRow, ...]
    cost_rows: tuple[CashFlowRow, ...]
    initial_investment: Money
    npv_value: Money
    inclusions: PerspectiveInclusions

    def total_benefit(self) -> Money:
        return aggregate(list(self.benefit_rows))

    def total_cost(self) -> Money:
        return Money(aggregate(list(self.cost_rows)) + self.initial_investment)


def society_excludes_subsidy(
    subsidy_row: CashFlowRow,
) -> PerspectiveInclusions:
    """사회 관점에서 보조금을 «편익» 에서 제외 (FR-704-AC5, 원칙 2-3).

    보조금은 정부→사업자로의 이전지출이다. 사회 관점 NPV 에 편익으로 넣으면
    «돈을 옮기기만 해도 사회가 부유해진다» 는 결론이 나온다.
    """
    tag = subsidy_row.tag or "보조금"
    return PerspectiveInclusions(
        included_tags=(),
        excluded_tags=(tag,),
        exclusion_rationale={
            tag: "사회 관점에서 보조금은 이전지출(transfer)이지 부가가치가 아니다 "
            "(FR-704-AC5, 원칙 2-3). 편익으로 넣으면 사회 NPV 가 부풀고 필요 "
            "지원액이 과소 산정된다",
        },
    )


def society_excludes_transfers(
    streams: list[tuple[ValueStream, int]],
) -> PerspectiveInclusions:
    """사회 관점에서 이전(transfer)을 소거 (R58 신설).

    한쪽의 편익이 다른 쪽의 같은 크기 손실인 흐름은 사회 전체에 순가치를 더하지
    않으므로 사회 관점 편익에서 뺀다.
    근거: 예비타당성조사 수행 총괄지침 제45조⑤ (「세금 등은 한 곳에서 다른 곳으로
    이전하는 지출로 순수한 경제적 비용으로 간주할 수 없기 때문에 가능한 범위까지는
    배제하고 분석하여야 하며」).

    `society_excludes_subsidy()`(FR-704-AC5 전용)와 관계: 보조금(정부→사업자 이전)은
    이 일반 소거 규칙의 한 사례다.
    """
    excluded_tags = []
    exclusion_rationale = {}

    for stream, _annual_won in streams:
        if stream.transfer_counterparty is not None:
            excluded_tags.append(stream.tag)
            from_payer = stream.transfer_counterparty.value
            to_payer = stream.effective_payer.value
            exclusion_rationale[stream.tag] = (
                f"{from_payer}→{to_payer} 이전이라 소거했다 "
                "(총괄지침 제45조⑤ 「세금 등은 한 곳에서 다른 곳으로 이전하는 지출로 "
                "순수한 경제적 비용으로 간주할 수 없기 때문에 가능한 범위까지는 "
                "배제하고 분석하여야 하며」)"
            )

    return PerspectiveInclusions(
        included_tags=(),
        excluded_tags=tuple(excluded_tags),
        exclusion_rationale=exclusion_rationale,
    )


def compute_perspective_npv(
    perspective: Perspective,
    benefit_rows: list[CashFlowRow],
    cost_rows: list[CashFlowRow],
    initial_investment: Money,
    discount_rate: float,
    *,
    inclusions: PerspectiveInclusions | None = None,
) -> PerspectiveResult:
    """한 관점의 NPV 산출.

    ``inclusions`` 로 «제외된 tag» 를 받으면 그 tag 의 benefit_rows 를 빼고 계산.
    사회 관점에서 보조금을 제외하는 데 쓴다 (FR-704-AC5).
    """
    excl: set[str] = set(inclusions.excluded_tags) if inclusions else set()
    effective_benefits = [r for r in benefit_rows if (r.tag or "") not in excl]
    npv_val = npv(initial_investment, effective_benefits, discount_rate)
    return PerspectiveResult(
        perspective=perspective,
        benefit_rows=tuple(effective_benefits),
        cost_rows=tuple(cost_rows),
        initial_investment=initial_investment,
        npv_value=npv_val,
        inclusions=inclusions or PerspectiveInclusions(),
    )


def assert_subsidy_excluded_from_society(
    society_result: PerspectiveResult,
) -> None:
    """10.7 검증 — 사회 관점 NPV 에 보조금이 편익으로 들어가지 않았는지."""
    for row in society_result.benefit_rows:
        if row.tag and "보조" in row.tag:
            raise ValueError(
                f"사회 관점 편익에 보조금({row.tag})이 포함되어 있다 (FR-704-AC5). "
                "보조금은 이전지출이지 편익이 아니다 — society_excludes_subsidy 로 "
                "제외해야 한다"
            )


def separate_other_program_subsidy(
    own_subsidy_won: int, other_program_subsidy_won: int
) -> tuple[Money, Money]:
    """FR-704-AC6 — 본 사업 국비와 타 사업 국비 분리.

    정부 관점 «재정효율 지표» 의 분모(투입 국비)에는 **본 사업 국비만** 포함.
    타 사업 국비는 «타 사업 국비» 행으로 별도 병기. 섞으면 본 사업의 재정효율이
    실제보다 나쁘게 나온다.
    """
    if own_subsidy_won < 0 or other_program_subsidy_won < 0:
        raise ValueError(
            f"국비는 음수일 수 없습니다: 본 사업 {own_subsidy_won}, "
            f"타 사업 {other_program_subsidy_won}"
        )
    return (Money(own_subsidy_won), Money(other_program_subsidy_won))


def is_economic_from_perspective(result: PerspectiveResult) -> bool:
    """해당 관점에서 경제성이 있는가 — NPV > 0."""
    return result.npv_value > ZERO
