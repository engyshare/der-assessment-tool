"""배타 규칙 선언적 테이블 — FR-402-AC4.

**규칙이 코드가 아닌 데이터다.** 제도가 바뀌면 테이블만 교체된다. ``if
benefit_a == "REC" and ...`` 로 짜면 제도 개정이 코드 배포를 요구하고,
그것은 FR-402-AC4 의 «선언적 테이블» 요건을 정면으로 위반한다.

각 규칙은 ``(편익A, 편익B, 유형 A~D, 근거, 적용 프로파일)``. 양방향으로
적용한다 — ``(A, B, ...)`` 는 ``(B, A, ...)`` 와 동일한 배타 관계다.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.contracts.valuestream import ExclusionType, ValueStream


@dataclass(frozen=True)
class ExclusionRule:
    """배타 규칙 1건 — FR-402-AC4."""

    benefit_a: str
    benefit_b: str
    exclusion_type: ExclusionType
    rationale: str
    #: ``None`` 은 «모든 프로파일에 적용». 제도 한정 규칙은 프로파일 이름을 둔다.
    applies_to_profile: str | None = None


#: 기본 배타 규칙 — 분산특구 범용. 제도 프로파일이 별도 규칙을 두면 그것이
#: 우선한다 (FR-504). **이 목록을 if 문으로 옮기지 말 것** (FR-402-AC4).
#:
#: 영역:
#:   - 유형 A (동일 물리량 이중 판매): 자가소비↔잉여, 잉여↔직접거래
#:   - 유형 B (인과 하류): 분산편익(망회피)↔자가소비(요금절감)
#:   - 유형 C (이중 화폐화): 본 Phase 1 6종에는 해당 쌍 없음 — 오탐 0 검증용
#:   - 유형 D (제도적 배타): 상계거래 참여 설비의 REC 제한 (프로파일 한정)
DEFAULT_EXCLUSION_RULES: tuple[ExclusionRule, ...] = (
    ExclusionRule(
        benefit_a="SelfConsumption",
        benefit_b="SurplusSale",
        exclusion_type=ExclusionType.A,
        rationale="같은 1 kWh 를 자가소비 절감과 잉여판매로 동시 계상할 수 없다",
    ),
    ExclusionRule(
        benefit_a="SurplusSale",
        benefit_b="DirectTrade",
        exclusion_type=ExclusionType.A,
        rationale="같은 잉여량을 상계거래와 직접거래로 동시 정산할 수 없다",
    ),
    ExclusionRule(
        benefit_a="DistributedBenefit",
        benefit_b="SelfConsumption",
        exclusion_type=ExclusionType.B,
        rationale="송배전 회피·손실 감소는 현행 망이용요금에 반영 — "
        "미래 증설 회피 증분만 계상 (원칙 2-1)",
    ),
    ExclusionRule(
        benefit_a="REC",
        benefit_b="SurplusSale",
        exclusion_type=ExclusionType.D,
        rationale="상계거래 참여 설비의 REC 발급 제한 (제도 한정)",
        applies_to_profile="net_metering",
    ),
)


def rules_for_profile(
    profile: str | None,
    rules: tuple[ExclusionRule, ...] = DEFAULT_EXCLUSION_RULES,
) -> tuple[ExclusionRule, ...]:
    """해당 규제 프로파일에 적용되는 규칙만 거른다.

    ``profile=None`` 이면 «모든 프로파일에 적용»(``applies_to_profile=None``)
    규칙만 돌아간다 — 프로파일을 모르는 상태에서 제도 한정 규칙을 끄는 것은
    보수적 판정이다 (Q4 «확인 못 했으면 보수적으로 배타», 도메인 원칙 부록 A).
    """
    return tuple(
        r for r in rules
        if r.applies_to_profile is None or r.applies_to_profile == profile
    )


def find_rule(
    a: str,
    b: str,
    rules: tuple[ExclusionRule, ...] = DEFAULT_EXCLUSION_RULES,
) -> ExclusionRule | None:
    """두 편익 사이의 배타 규칙을 찾는다. 양방향 대칭."""
    for r in rules:
        if (r.benefit_a == a and r.benefit_b == b) or (
            r.benefit_a == b and r.benefit_b == a
        ):
            return r
    return None


def collect_exclusions(
    streams: list[ValueStream],
    rules: tuple[ExclusionRule, ...] = DEFAULT_EXCLUSION_RULES,
) -> list[tuple[str, str, ExclusionType, str]]:
    """활성화된 편익 쌍 중 배타 규칙에 걸리는 것을 모은다.

    반환: ``(편익A tag, 편익B tag, 유형, 근거)``. FR-402-AC1 의 «정상 계상»
    을 침해하지 않으려면 — 동시 발생하는 정당한 편익을 지우지 않으려면 —
    이 목록에 **들어 있지 않은** 쌍은 그대로 둔다. **오탐 0 이 차단 100%
    만큼 중요**하다 (FR-402-AC1).
    """
    active_tags = {type(s).tag for s in streams if s.enabled}
    out: list[tuple[str, str, ExclusionType, str]] = []
    seen: set[tuple[str, str]] = set()
    for r in rules:
        if r.benefit_a in active_tags and r.benefit_b in active_tags:
            key = (r.benefit_a, r.benefit_b)
            rev = (r.benefit_b, r.benefit_a)
            if key in seen or rev in seen:
                continue
            seen.add(key)
            out.append((r.benefit_a, r.benefit_b, r.exclusion_type, r.rationale))
    return out
