"""기준선 증분 분석 — 작업 10.5 / FR-705-AC1.

모든 편익은 «설비 미설치 기준선» 대비 **증분** 이다 (도메인 원칙 1-1·1-2).
기준선 자체 비용도 리포트에 **명시적으로 표시** 해야 한다 (FR-705-AC1).

기준선이 «아무것도 하지 않음» 이 아니라 «현실적 대안» 이라는 점이 핵심이다
(원칙 1-3). 히트펌프의 기준선은 «난방 안 함» 이 아니라 «기존 보일러 유지».
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from core.cba.proforma import aggregate
from core.contracts.schemas import CashFlowRow
from core.contracts.units import ZERO, Money
from core.contracts.validation import ValidationError


class BaselineArrangement(StrEnum):
    """기준선(Without) 갈래 셋 (FR-705-AC2)."""

    NONE = "자가용 없음"  # Without: 한전 전력 전량
    MAINTAIN = "자가용 유지"  # Without: 한전 전력 + 자가용 자가소비
    POOL = "자가용 집합자원화"  # Without: 자가용 유지(=가 또는 현행)


class SelfConsumptionTreatment(StrEnum):
    """자가소비 처리 방식 (FR-705-AC2)."""

    NONE = "없음"  # 자가용이 없어 자가소비가 애초에 없다
    CANCEL_OUT = "소거"  # Without·With 양쪽에 똑같이 있어 차액에서 사라진다
    FORFEIT = "포기(음의 항)"  # With 에서 사라지므로 비용으로 계상해야 한다


@dataclass(frozen=True)
class BaselineBranch:
    """갈래별 기준선 및 자가소비 처리 선언."""

    without_description: str
    with_description: str
    viability_condition: str
    self_consumption_treatment: SelfConsumptionTreatment
    clause: str


#: 갈래별 선언표.
#: if structure == ... 로 짜지 않는다. 선언표로 두면 여덟 번째 구조가 생겨도
#: 이 계약과 엔진은 바뀌지 않는다.
BASELINE_DECLARATIONS: Mapping[BaselineArrangement, BaselineBranch] = MappingProxyType(
    {
        BaselineArrangement.NONE: BaselineBranch(
            without_description="한전 전력 전량",
            with_description="분산e사업자 공급",
            viability_condition="",
            self_consumption_treatment=SelfConsumptionTreatment.NONE,
            clause="예비타당성조사 수행 총괄지침 제45조② · 판정 정본 §1 첫째",
        ),
        BaselineArrangement.MAINTAIN: BaselineBranch(
            without_description="한전 전력 + 자가용 자가소비",
            with_description="분산e 공급 + 자가용 자가소비",
            viability_condition="분산e 요금 < 한전 요금",
            self_consumption_treatment=SelfConsumptionTreatment.CANCEL_OUT,
            clause="예비타당성조사 수행 총괄지침 제45조② · 판정 정본 §1 둘째",
        ),
        BaselineArrangement.POOL: BaselineBranch(
            without_description="자가용 유지",
            with_description="분산e 로부터 공급 + 집합자원화 대가",
            viability_condition="전기사용자에게 자가용 유지보다 유리",
            self_consumption_treatment=SelfConsumptionTreatment.FORFEIT,
            clause="예비타당성조사 수행 총괄지침 제45조② · 판정 정본 §1 셋째",
        ),
    }
)


def get_baseline_branch(arrangement: BaselineArrangement) -> BaselineBranch:
    """갈래 선언을 찾고, **아직 세울 수 없는 갈래를 거부한다** (FR-705-AC2 · DV-15).

    ## ★★ 「나」를 거부하는 것이 옳다 — **「평가할 수 없다」와 「0 이다」는 다른 말이다**

    판정 정본 `docs/decisions-2026-09-03-R57.md` **§2** 가 *「계측이 갈리지 않으면
    「나」는 **평가할 수 없다**」* 고 적는다. 상계처리로는 전기사용자의 전력사용량이
    구분되지 않아 **책임공급비율의 분모가 서지 않는다.** 그리고 **§4④**(총괄지침
    제45조③ 대칭성)에 따라 「집합자원화 대가」를 편익으로 세우려면 「포기한 자가소비」를
    비용으로 세야 하는데 **그 자리가 저장소에 없다.**

    두 자리 중 하나라도 없으면 **거부한다.** 0 으로 채우면 *「없는 제도 위에 편익을
    쌓는」* 것과 같은 형태가 되고, 이 저장소는 `TouArbitrage` 단가에서 이미 같은
    판단을 했다(단가가 없어 0 으로 안 채웠다).
    """
    branch = BASELINE_DECLARATIONS[arrangement]
    if branch.self_consumption_treatment is SelfConsumptionTreatment.FORFEIT:
        raise ValidationError(
            field="baseline.arrangement",
            reason=(
                "포기 항이 서지 않았다: 1. 계측 전제가 안 섰다(상계처리로는 "
                "전기사용자의 전력사용량이 구분되지 않아 책임공급비율의 분모가 서지 않는다. "
                "발전량·전기사용량을 구분해 계측·정산해야 한다). "
                "2. 대칭 항이 없다(집합자원화 대가를 편익으로 세우려면 포기한 자가소비를 "
                "비용으로 세야 하는데 그 자리가 저장소에 없다)."
            ),
            action=(
                "「나」 갈래는 지금 평가할 수 없습니다. 0 으로 채우지 마십시오 — "
                "구분 계측(발전량·전기사용량)을 선언하고 「포기한 자가소비」 비용 항을 "
                "세운 뒤에 이 갈래를 고르십시오"
            ),
            rule="DV-15",
        )
    return branch


@dataclass(frozen=True)
class BaselineComparison:
    """기준선 vs 신규 비교 — 증분과 기준선 자체를 함께 든다 (FR-705-AC1).

    ``baseline_displayed`` 가 0 이면 «기준선이 표시되지 않았다» — 조항 위반.
    편익이 증분이려면 baseline 이 명시되어야 그 차이가 증분임을 보일 수 있다.
    """

    baseline_rows: tuple[CashFlowRow, ...]
    new_rows: tuple[CashFlowRow, ...]
    incremental_rows: tuple[CashFlowRow, ...]

    def baseline_total(self) -> Money:
        """기준선 총비용 — 리포트에 명시적 표시 (FR-705-AC1)."""
        return aggregate(list(self.baseline_rows))

    def new_total(self) -> Money:
        return aggregate(list(self.new_rows))

    def incremental_total(self) -> Money:
        """편익 증분 총액 = new − baseline."""
        return Money(self.new_total() - self.baseline_total())


def compute_incremental(
    baseline: list[CashFlowRow], new: list[CashFlowRow]
) -> list[CashFlowRow]:
    """new − baseline 의 증분 행.

    같은 tag 끼리 짝지어 빼고, baseline 에만 있는 tag 는 음수(감소),
    new 에만 있는 tag 는 그대로(증가).
    """
    baseline_by_tag: dict[str, CashFlowRow] = {
        (r.tag or r.label): r for r in baseline
    }
    new_by_tag: dict[str, CashFlowRow] = {
        (r.tag or r.label): r for r in new
    }
    all_tags = set(baseline_by_tag) | set(new_by_tag)

    incremental: list[CashFlowRow] = []
    for tag in sorted(all_tags):
        b_row = baseline_by_tag.get(tag)
        n_row = new_by_tag.get(tag)
        b_amounts = b_row.amounts if b_row else {}
        n_amounts = n_row.amounts if n_row else {}
        all_years = set(b_amounts) | set(n_amounts)
        diff_amounts = {
            y: n_amounts.get(y, Money(0)) - b_amounts.get(y, Money(0))
            for y in sorted(all_years)
        }
        # 0 이 아닌 연도만 남긴다 — 0 인 행은 보이지 않는 것이 낫다
        diff_amounts = {y: v for y, v in diff_amounts.items() if v != Money(0)}
        if not diff_amounts:
            continue
        incremental.append(CashFlowRow(
            label=f"{tag} 증분",
            tag=tag,
            amounts=diff_amounts,
        ))
    return incremental


def compare_baseline_vs_new(
    baseline: list[CashFlowRow], new: list[CashFlowRow]
) -> BaselineComparison:
    """기준선 vs 신규 비교 — 증분 행과 함께 기준선 자체도 든다."""
    incremental = compute_incremental(baseline, new)
    return BaselineComparison(
        baseline_rows=tuple(baseline),
        new_rows=tuple(new),
        incremental_rows=tuple(incremental),
    )


def assert_baseline_displayed(comparison: BaselineComparison) -> None:
    """10.5 검증 — 기준선이 명시적으로 표시되었는가 (FR-705-AC1).

    기준선 없이 증분만 보이면 조항 위반이다 — 증분의 타당성을 검증할 수 없다.
    """
    if comparison.baseline_total() == ZERO and not comparison.baseline_rows:
        raise ValueError(
            "기준선이 표시되지 않았다 (FR-705-AC1). 증분만 계산하고 기준선을 "
            "보여 주지 않으면 증분의 타당성을 검증할 수 없다 (도메인 원칙 1-2)"
        )
