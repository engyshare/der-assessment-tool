"""편익 계상 내역 리포트 — FR-402-AC6.

편익 목록을 받아 네 부류로 나누어 계상 내역을 낸다:
    1. **계상된 편익** — 활성화되고 배타 제외되지 않은 편익
    2. **배타로 제외된 편익** — 활성화됐지만 배타 규칙에 걸려 제외
    3. **증분만 계상된 편익** — 유형 B (인과 하류) 로 전액이 아닌 증분만
    4. **미화폐화로 0 처리된 편익** — 제도 미확인 등으로 0 (FR-404)

**관점별 분리 (FR-402-AC7)**: 보조금은 사회 관점에서 이전지출이라 편익에
넣지 않는다. ``BenefitReport`` 는 한 관점의 편익만 다룬다 — 여러 관점을
섞으면 §2-3 의 «가장 흔한 중복 오류» 가 된다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.contracts.der import DispatchResult
from core.contracts.units import ZERO, Money
from core.contracts.valuestream import ExclusionType, Payer, ValueStream
from core.valuestream.exclusion_table import (
    DEFAULT_EXCLUSION_RULES,
    collect_exclusions,
    rules_for_profile,
)


@dataclass(frozen=True)
class BenefitLine:
    """리포트 1행 — 편익 tag, 연간액, 상태."""

    tag: str
    name: str
    payer: Payer
    annual_value: Money
    state: str  # "계상됨" | "배타제외" | "증분만" | "미화폐화0"


@dataclass
class BenefitReport:
    """FR-402-AC6 편익 계상 내역."""

    accounted: list[BenefitLine] = field(default_factory=list)
    excluded: list[BenefitLine] = field(default_factory=list)
    increment_only: list[BenefitLine] = field(default_factory=list)
    unmonetized_zero: list[BenefitLine] = field(default_factory=list)

    def total_accounted(self) -> Money:
        """계상된 편익 합계 (배타 제외·미화폐화 0 제외)."""
        total = ZERO
        for line in self.accounted:
            total = Money(total + line.annual_value)
        return total

    def all_lines(self) -> list[BenefitLine]:
        """리포트 전체 행 — 순서: 계상 / 배타제외 / 증분만 / 미화폐화0."""
        return (
            self.accounted + self.excluded
            + self.increment_only + self.unmonetized_zero
        )


def build_report(
    streams: list[ValueStream],
    dispatch: DispatchResult,
    *,
    year: int,
    profile: str | None = None,
) -> BenefitReport:
    """편익 목록 → 계상 내역 리포트.

    ``profile`` 은 규제 프로파일 이름. ``None`` 이면 제도 한정 배타 규칙이
    빠지고 «모든 프로파일에 적용» 규칙만 돈다 (보소수적).
    """
    rules = rules_for_profile(profile, DEFAULT_EXCLUSION_RULES)
    # 배타 쌍 — 둘 다 활성화된 쌍만. 한 쪽이 비활성이면 배타가 발동하지 않는다.
    excluded_pairs = collect_exclusions(streams, rules)
    excluded_tags: set[str] = set()
    type_b_tags: set[str] = set()
    for a, b, etype, _ in excluded_pairs:
        # 유형 B 는 «둘 다 비활성»이 아니라 «증분만» 으로 분류 — Q2.
        # 단순 구현: B 면 둘 중 «하류» 쪽(BenefitExclusionRule.benefit_b)을
        # 증분-only 로 표시하고, A·C·D 면 양쪽 다 제외.
        if etype is ExclusionType.B:
            # 유형 B: benefit_a 가 «하류 편익» (DistributedBenefit) 이고
            # benefit_b 가 «상류» (SelfConsumption). 하류를 «증분만» 분류한다
            # (원칙 2-1 — 하류가 상류에 이미 포함되어 있으므로 증분만 계상).
            type_b_tags.add(a)
        else:
            excluded_tags.add(a)
            excluded_tags.add(b)

    report = BenefitReport()
    for s in streams:
        line = BenefitLine(
            tag=type(s).tag,
            name=s.name,
            payer=s.payer,
            annual_value=s.annual_value(dispatch, year=year),
            state="계상됨",
        )
        if type(s).tag in excluded_tags:
            line = _with_state(line, "배타제외")
            report.excluded.append(line)
        elif type(s).tag in type_b_tags:
            line = _with_state(line, "증분만")
            report.increment_only.append(line)
        elif line.annual_value == ZERO and s.enabled:
            # 활성화됐지만 0 — FR-404 미화폐화 (제도 미확인)
            line = _with_state(line, "미화폐화0")
            report.unmonetized_zero.append(line)
        else:
            report.accounted.append(line)

    return report


def _with_state(line: BenefitLine, state: str) -> BenefitLine:
    """상태만 바꾼 사본. ``BenefitLine`` 이 frozen 이므로 새 객체를 만든다."""
    return BenefitLine(
        tag=line.tag,
        name=line.name,
        payer=line.payer,
        annual_value=line.annual_value,
        state=state,
    )
