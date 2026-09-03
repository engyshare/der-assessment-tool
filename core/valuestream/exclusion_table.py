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


#: 거부 메시지의 **처방 뒷부분** — 세 갈래가 같은 문장을 쓴다 (R56).
#:
#: R55 까지 이 자리는 *「배타 규칙 쪽이 틀린 것이므로
#: docs/exclusion-rules.yaml 을 고쳐야 합니다」* 하나였다. 그런데 그것은
#: **규칙표가 틀렸을 때의 처방**이고, 규칙은 맞는데 **이 조합의 물량이 다른
#: 경우**의 처방이 아니었다 — 그리고 그 「다르다」를 말할 자리가 계약에
#: 없었으므로 검토자가 할 수 있는 일이 규칙을 지우는 것뿐이었다. 규칙을
#: 지우면 물량이 **같은** 다른 조합까지 함께 열린다.
_QUANTITY_HINT: str = (
    "두 편익 모두에 서로 다른 `quantity_id` 를 선언하십시오"
    "(한쪽만 선언하면 다르다는 것을 증명할 수 없어 그대로 거부됩니다). "
    "규칙 자체가 틀렸다면 docs/exclusion-rules.yaml 을 고쳐야 합니다"
)


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


def _same_quantity_is_possible(
    a_streams: list[ValueStream],
    b_streams: list[ValueStream],
) -> bool:
    """두 무리가 **같은 물리량을 계상할 수 있는가** — 유형 A·E 의 물리량 축.

    `FR-402-AC1` 은 *「지불 주체가 다르거나 **물리량이 다르면 정상 계상한다**」*
    를 명시로 요구하고, `FR-402-AC2.A` 는 금지 범위를 *「**같은** 1 kWh」·
    「**같은 시각** ESS 방전」* 으로 좁힌다. 그러므로 두 편익이 **서로 다른
    물량**을 화폐화한다면 그 조합은 애초에 조항이 말하는 이중 계상이 아니다.

    ⚠⚠ **「한쪽만 선언」을 통과시키지 않는다.** 한쪽이 말하지 않았으면
    *다르다는 것을 증명할 수 없고*, 통과시키면 **한 스트림에 표찰을 다는 것만으로
    배타 규칙 전체를 무력화**할 수 있다 — 거부 기계에 우회로를 내는 것이다.
    그래서 `None` 은 **「말하지 않았다」** 로 읽고 보수적으로 「같을 수 있다」에
    센다 (`ValueStream.quantity_id` 의 규약 · Q4 「확인 못 했으면 보수적으로
    배타」, 도메인 원칙 부록 A).

    ⚠ **쌍마다 본다.** 같은 태그의 인스턴스가 여럿일 수 있고(용량 몫을 갈라
    몫마다 다른 역할을 주는 구성), 그중 **한 쌍이라도** 같은 물량을 질 수 있으면
    그 조합은 걸린다 — 무리 단위로 합쳐 보면 겹치는 한 쌍이 다른 쌍에 가려진다.
    """
    return any(
        a.quantity_id is None
        or b.quantity_id is None
        or a.quantity_id == b.quantity_id
        for a in a_streams
        for b in b_streams
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

    ## ★★ 물리량 축 — 유형 `A`·`E` 는 **같은 물량일 때만** 걸린다 (R56)

    R55 까지 이 함수는 ``active_tags = {type(s).tag for s in active}`` — **태그의
    집합**으로만 판정했으므로 «같은 물리량인가» 를 물을 수단이 **원리적으로
    없었고**, 그래서 물리량이 다른 조합까지 거부했다. 그것은 조항 완화가 아니라
    **조항 위반이었다**: `FR-402-AC1` 이 *「물리량이 다르면 **정상 계상한다**」*
    를 명시로 요구하는데 판정이 그 갈래를 지웠다.

    이제 편익이 `ValueStream.quantity_id` 로 물량을 말할 수 있고, **둘 다
    선언하고 서로 다를 때만** 그 쌍을 목록에서 뺀다 (`_same_quantity_is_possible`).
    선언이 없으면 지금과 같이 걸린다 — 이 축은 **기본 동작을 바꾸지 않는다.**

    ⚠ **유형 `B`~`D` 에는 적용하지 않는다.** 그것들은 애초에 «같은 물리량»이
    판정 근거가 아니다(`B` 는 인과 하류, `C` 는 동일 효과의 이중 화폐화, `D` 는
    제도적 배타) — 물리량 축으로 걸러 내면 **판정 근거가 아닌 것으로 규칙을
    끄게 된다.** 그리고 셋은 `assert_no_exclusions` 가 거부하지도 않는다.
    """
    active = [s for s in streams if s.enabled]
    # ★ **태그 → 인스턴스 목록**이다(집합이 아니다). 물리량 축은 인스턴스가
    # 지므로 태그만 남기면 그 자리에서 물량이 사라진다 — R55 까지가 그 상태였다.
    by_tag: dict[str, list[ValueStream]] = {}
    for s in active:
        by_tag.setdefault(type(s).tag, []).append(s)
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
        if r.benefit_a in by_tag and r.benefit_b in by_tag:
            key = (r.benefit_a, r.benefit_b)
            rev = (r.benefit_b, r.benefit_a)
            if key in seen or rev in seen:
                continue
            if r.exclusion_type in (
                ExclusionType.A,
                ExclusionType.E,
            ) and not _same_quantity_is_possible(
                by_tag[r.benefit_a], by_tag[r.benefit_b]
            ):
                continue
            seen.add(key)
            out.append((r.benefit_a, r.benefit_b, r.exclusion_type, r.rationale))
    return out


def assert_no_exclusions(
    streams: list[ValueStream],
    rules: tuple[ExclusionRule, ...] = DEFAULT_EXCLUSION_RULES,
) -> None:
    """유형 A·E 위반이면 **거부한다** — FR-402-AC2.A · FR-402-AC2.E · DV-12.

    > **R16 이 채운 자리(유형 A).** 조항은 *「선언적 배타 규칙 테이블로
    > 금지하고, **선택 시 검증 오류로 거부**한다」* 인데 저장소에는
    > `collect_exclusions` 의 **감지·라벨링뿐**이었다 — 위반 쌍을 리스트로
    > 돌려줄 뿐 아무것도 막지 않았고, 리포트는 그것을 「배타제외」로
    > **표시**했다. 표시와 거부는 다르다.

    > **R52/WP-3 이 마저 채운 자리(유형 E).** `FR-402-AC2.E` 조항 문면도
    > 그대로 *「선언적 배타 규칙 테이블로 금지하고 선택 시 검증 오류로
    > 거부한다. **차단 100%**」* 다. 그런데 R48 이 그 유형을 신설한 뒤로
    > 이 함수는 유형 `A` 만 걸렀고, `tests/valuestream/test_grid_dispatch_
    > benefits.py` 의 부채 래칫이 그 갈림(조항은 거부·구현은 표시만)을
    > 못박아 두고 있었다. 사용자 판정 §3 앞 문장(*「배터리는 한 번에 하나의
    > 역할만 수행하는 것으로 설계해야 함」*, `docs/decisions-2026-09-02-
    > R52.md` §3)이 그 조항대로 만들라고 답한다 — spec 개정이 아니다.

    **유형 A·E 를 거부한다. `B`~`D` 는 거부하지 않는다.** 조항이 행마다
    수용 수준을 반대로 정해 두었기 때문이다 — `A`·`E` 는 차단 100%(음성
    검증)이고 `B`~`D` 는 **오탐 0**(양성 검증)이다. `B` 는 «증분만 계상»,
    `D` 는 «프로파일 한정»이므로 거부가 아니라 계상 방식의 문제이며,
    여기서 함께 막으면 정당한 동시 계상을 지우게 된다. 그것이 FR-402-AC1
    이 명시로 금지한 방향이다.

    > **R56 이 채운 자리(물리량 축).** 바로 위 문장 — *「여기서 함께 막으면
    > 정당한 동시 계상을 지우게 되며, 그것이 FR-402-AC1 이 명시로 금지한
    > 방향이다」* — 은 **유형 `A` 의 「물리량이 다른 경우」에도 그대로
    > 적용된다.** 그 자리만 아무도 보지 않았다: 판정이 태그 짝만 보았으므로
    > `AC1` 이 *「물리량이 다르면 **정상 계상한다**」* 로 명시한 갈래까지
    > 거부했다. 이제 `collect_exclusions` 가 `ValueStream.quantity_id` 를
    > 읽어 **둘 다 선언하고 서로 다른** 쌍을 빼며, 그래서 이 함수가 받는
    > 목록에 그 쌍이 애초에 오지 않는다. **어느 배포 편익도 아직 물량을
    > 선언하지 않으므로 지금 거부되는 것은 종전과 같다.**
    """
    violations = [
        (a, b, kind, rationale)
        for a, b, kind, rationale in collect_exclusions(streams, rules)
        if kind in (ExclusionType.A, ExclusionType.E)
    ]
    if not violations:
        return

    double_counted = [(a, b, why) for a, b, kind, why in violations if kind is ExclusionType.A]
    conflicting_operation = [
        (a, b, why) for a, b, kind, why in violations if kind is ExclusionType.E
    ]

    reason_parts = []
    if double_counted:
        pairs = "; ".join(f"{a} ↔ {b} ({why})" for a, b, why in double_counted)
        reason_parts.append(f"동일 물리량을 이중 계상하는 편익 조합입니다 — {pairs}")
    if conflicting_operation:
        pairs = "; ".join(f"{a} ↔ {b} ({why})" for a, b, why in conflicting_operation)
        reason_parts.append(
            "동시에 성립할 수 없는 운전 조합입니다(방전 시점을 누가 정하는가가 "
            f"갈립니다) — {pairs}"
        )

    if double_counted and conflicting_operation:
        action = (
            "두 편익 중 하나를 비활성화하거나 ESS 운전 방법을 하나로 고르십시오"
            "(용량을 나누어 각 몫에 다른 역할을 맡기는 것은 허용됩니다). 물리량이"
            " 실제로 다르거나 운전 주체가 실제로 갈린다면 " + _QUANTITY_HINT
        )
    elif conflicting_operation:
        action = (
            "ESS 운전 방법을 하나로 고르십시오(용량을 나누어 각 몫에 다른 "
            "역할을 맡기는 것은 허용됩니다). 몫마다 방전하는 전력이 실제로 "
            "갈린다면 " + _QUANTITY_HINT
        )
    else:
        action = (
            "두 편익 중 하나를 비활성화하십시오. 둘 다 필요한 상황이라면 "
            "물리량이 실제로 다른지 확인하고, 다르다면 " + _QUANTITY_HINT
        )

    raise ValidationError(
        field="valuestream.enabled",
        reason=" / ".join(reason_parts),
        action=action,
        rule="DV-12",
    )
