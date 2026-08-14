"""배타 규칙 선언적 테이블 — FR-402-AC4 · FR-402-AC2.A.

**규칙이 코드가 아닌 데이터다.** 제도가 바뀌면 테이블만 교체된다. ``if
benefit_a == "REC" and ...`` 로 짜면 제도 개정이 코드 배포를 요구하고,
그것은 FR-402-AC4 의 «선언적 테이블» 요건을 정면으로 위반한다.

> **R16 정정 — 상수도 코드였다.** v0.3~R15 동안 이 파일은 위 문장을 적어
> 두고 규칙을 **파이썬 튜플 상수**로 들고 있었다. 「`if` 문으로 옮기지 말
> 것」은 지켜졌지만 «데이터» 요건은 지켜지지 않았다 — 제도가 바뀌면 여전히
> 파이썬 파일을 고쳐 배포해야 했다. 지금 정본은
> **`docs/exclusion-rules.yaml`** 이고 이 상수는 그것을 읽은 결과다.
>
> R15 가 요금표(`FR-501-AC4`)에서 같은 자리를 지났다. 그때의 교훈은
> 로더를 만드는 것이 아니라 **로더가 실제 경로가 되게 하는 것**이었다.

각 규칙은 ``(편익A, 편익B, 유형 A~D, 근거, 적용 프로파일)``. 양방향으로
적용한다 — ``(A, B, ...)`` 는 ``(B, A, ...)`` 와 동일한 배타 관계다.
"""
from __future__ import annotations

from core.contracts.validation import ValidationError
from core.contracts.valuestream import ExclusionRule, ExclusionType, ValueStream
from core.valuestream.exclusion_loader import load_exclusion_rules

__all__ = (
    "DEFAULT_EXCLUSION_RULES",
    "ExclusionRule",
    "ExclusionType",
    "assert_no_exclusions",
    "collect_exclusions",
    "find_rule",
    "rules_for_profile",
)

#: 기본 배타 규칙 — 분산특구 범용. **`docs/exclusion-rules.yaml` 에서 읽는다.**
#: 제도 프로파일이 별도 규칙을 두면 그것이 우선한다 (FR-504).
#:
#: 파일이 없거나 깨졌으면 **여기서 import 가 실패한다.** 조용히 빈 표로
#: 떨어지면 배타 검사가 「위반 0건」을 내고 통과하는데, 그것은 규칙이 없는
#: 것이 아니라 검사가 없는 것이다 (§13.0.1 ④).
DEFAULT_EXCLUSION_RULES: tuple[ExclusionRule, ...] = load_exclusion_rules()


def rules_for_profile(
    profile: str | None,
    rules: tuple[ExclusionRule, ...] = DEFAULT_EXCLUSION_RULES,
) -> tuple[ExclusionRule, ...]:
    """해당 규제 프로파일에 적용되는 규칙만 거른다.

    ``profile=None`` 이면 «모든 프로파일에 적용»(``applies_to_profile=None``)
    규칙만 돌아간다 — 프로파일을 모르는 상태에서 제도 한정 규칙을 끄는 것은
    보수적 판정이다 (Q4 «확인 못 했으면 보수적으로 배타», 도메인 원칙 부록 A).

    ⚠ **계약구조 축은 여기서 걸러지지 않는다.** 구조는 편익 인스턴스가 들고
    있으므로(`ValueStream.structure`) 판정이 활성 편익에서 직접 읽는다 —
    `collect_exclusions` 를 보라. 이 함수에 구조 인자를 더하면 **호출부마다
    구조를 다시 넘겨야 하고**, 넘기지 않은 호출부에서 구조 규칙이 조용히 꺼진다.
    """
    return tuple(
        r for r in rules
        if r.applies_to_profile is None or r.applies_to_profile == profile
    )


def _structure_applies(rule: ExclusionRule, structures: frozenset[str]) -> bool:
    """구조 한정 규칙이 이 조합에 걸리는가.

    **활성 편익이 선언한 구조**를 본다. 구조를 모르는 편익만 있으면 구조 한정
    규칙은 걸리지 않는다 — 프로파일에서와 같은 판단이며, 「구조를 모른다」를
    「어느 구조든 아니다」로 읽는 것이다.

    ⚠ **반대로 읽으면 위험하다.** 「구조를 모르면 전부 적용」으로 두면 구조를
    지정하지 않은 기존 케이스가 갑자기 거부되고, 그것은 `FR-402-AC1`(정당한
    동시 계상을 막지 말 것)을 어긴다.
    """
    return rule.applies_to_structure is None or rule.applies_to_structure in structures


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
    active = [s for s in streams if s.enabled]
    active_tags = {type(s).tag for s in active}
    # ★ **구조를 인자로 받지 않고 편익에서 읽는다 (R31).** 인자로 두면 호출부마다
    # 다시 넘겨야 하고, 넘기지 않은 호출부에서 구조 규칙이 조용히 꺼진다 —
    # 이미 배선된 `assert_no_exclusions()` 호출 둘이 그 자리가 될 것이었다.
    active_structures = frozenset(
        s.structure for s in active if s.structure is not None
    )
    out: list[tuple[str, str, ExclusionType, str]] = []
    seen: set[tuple[str, str]] = set()
    for r in rules:
        if not _structure_applies(r, active_structures):
            continue
        if r.benefit_a in active_tags and r.benefit_b in active_tags:
            key = (r.benefit_a, r.benefit_b)
            rev = (r.benefit_b, r.benefit_a)
            if key in seen or rev in seen:
                continue
            seen.add(key)
            out.append((r.benefit_a, r.benefit_b, r.exclusion_type, r.rationale))
    return out


def assert_no_exclusions(
    streams: list[ValueStream],
    rules: tuple[ExclusionRule, ...] = DEFAULT_EXCLUSION_RULES,
) -> None:
    """유형 A 위반이면 **거부한다** — FR-402-AC2.A · DV-12.

    > **R16 이 채운 자리.** 조항은 *「선언적 배타 규칙 테이블로 금지하고,
    > **선택 시 검증 오류로 거부**한다」* 인데 저장소에는 `collect_exclusions`
    > 의 **감지·라벨링뿐**이었다 — 위반 쌍을 리스트로 돌려줄 뿐 아무것도 막지
    > 않았고, 리포트는 그것을 「배타제외」로 **표시**했다. 표시와 거부는 다르다.

    **유형 A 만 거부한다.** 조항이 행마다 수용 수준을 반대로 정해 두었기
    때문이다 — `A` 는 차단 100%(음성 검증)이고 `B`~`D` 는 **오탐 0**(양성
    검증)이다. `B` 는 «증분만 계상», `D` 는 «프로파일 한정»이므로 거부가
    아니라 계상 방식의 문제이며, 여기서 함께 막으면 정당한 동시 계상을
    지우게 된다. 그것이 FR-402-AC1 이 명시로 금지한 방향이다.
    """
    violations = [
        (a, b, rationale)
        for a, b, kind, rationale in collect_exclusions(streams, rules)
        if kind is ExclusionType.A
    ]
    if not violations:
        return

    pairs = "; ".join(f"{a} ↔ {b} ({why})" for a, b, why in violations)
    raise ValidationError(
        field="valuestream.enabled",
        reason=f"동일 물리량을 이중 계상하는 편익 조합입니다 — {pairs}",
        action=(
            "두 편익 중 하나를 비활성화하십시오. 둘 다 필요한 상황이라면 "
            "물리량이 실제로 다른지 확인하고, 다르다면 배타 규칙 쪽이 틀린 "
            "것이므로 docs/exclusion-rules.yaml 을 고쳐야 합니다"
        ),
        rule="DV-12",
    )
