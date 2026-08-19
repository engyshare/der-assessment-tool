"""배타 규칙이 **계약구조로도** 걸리는가 — `FR-402-AC4` · `FR-205` / R31 (결정 §2-4).

`R13-WP24G` 설계서가 「결정 필요 4」로 올린 자리다: *「`ContractConfig.structure`
(`FR-205`)와 `RegulationProfile`(`FR-504`)이 **완전히 독립된 두 축**이라, 사용자가
「상계거래」를 고르고도 다른 규제 프로파일을 선택하면 REC 발급 제한이 **조용히 안
걸린다**」*.

**설계서의 선택지 (가)(구조가 프로파일을 자동 강제)도 (나)(경고만)도 택하지
않았다.** 자동 강제는 두 축을 묶어 **새 구조·새 프로파일 조합마다 매핑 코드를
고치게** 한다. 대신 규칙표에 **구조 축**을 더했다 — 금지 여부가 코드가 아니라
데이터로 늘고, 거부는 이미 실행 경로에 배선된 `assert_no_exclusions()`(R27)가
그대로 담당한다.

붙드는 것 넷:

    ① 구조 한정 규칙이 **그 구조에서만** 걸린다
    ② 구조를 모르는 조합에는 걸리지 않는다      FR-402-AC1 (오탐 0)
    ③ 프로파일과 **독립**으로 걸린다            설계서가 지적한 그 구멍
    ④ 오타 난 구조 이름은 **기동 시점에** 터진다  조용히 꺼진 규칙을 막는다

**③이 이 파일의 핵심이다.** ①만 두면 「구조로 걸린다」는 알 수 있지만, 구조 규칙이
프로파일 규칙과 같은 조건에서만 걸리는 구현도 통과한다 — 그러면 구멍이 그대로다.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import ClassVar

import pytest

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.valuestream import (
    ExclusionRule,
    ExclusionType,
    Payer,
    ValueStream,
)
from core.valuestream.exclusion_loader import (
    ExclusionRulesError,
    load_exclusion_rules_from_text,
)
from core.valuestream.exclusion_table import collect_exclusions, rules_for_profile

#: 구조 한정 규칙 하나만 든 최소 규칙표 — 실물 표를 쓰면 다른 규칙이 함께 걸려
#: 「무엇이 이 결과를 냈는가」가 흐려진다.
_RULES: tuple[ExclusionRule, ...] = (
    ExclusionRule(
        benefit_a="_StructA",
        benefit_b="_StructB",
        exclusion_type=ExclusionType.D,
        rationale="검사용 구조 한정 금지",
        applies_to_structure="상계거래",
    ),
)


class _StructA(ValueStream):
    tag: ClassVar[str] = "_StructA"
    #: 검사용 편익 — 창을 읽지 않으므로 연간화 대상이 아니다 (R34 계약).
    scales_with_dispatch_window = False
    #: **클래스 기본값이 있어야 구조 없이도 설 수 있다.** 없으면 구조를 주지 않은
    #: 인스턴스가 `DV-13`(지불 주체 미특정)으로 거부되고, 그러면 아래 「구조를
    #: 모르는 조합」 케이스를 만들 수 없다 — 실물 편익도 전부 기본값을 갖는다.
    payer = Payer.OPERATOR
    payer_by_structure: ClassVar[MappingProxyType[str, Payer]] = MappingProxyType({
        "상계거래": Payer.RESIDENT,
    })

    def __init__(self, *, structure: str | None = None) -> None:
        super().__init__(name="A", structure=structure)

    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        return to_won(0)

    def formula(self, dispatch: DispatchResult, *, year: int) -> str:
        return "검사용 스텁 0원"


class _StructB(ValueStream):
    tag: ClassVar[str] = "_StructB"
    #: 검사용 편익 — 창을 읽지 않으므로 연간화 대상이 아니다 (R34 계약).
    scales_with_dispatch_window = False
    payer = Payer.OPERATOR

    def __init__(self, *, structure: str | None = None) -> None:
        super().__init__(name="B", structure=structure)

    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        return to_won(0)

    def formula(self, dispatch: DispatchResult, *, year: int) -> str:
        return "검사용 스텁 0원"


# ── ① 구조 한정 규칙이 그 구조에서만 걸린다 ──────────────────────────

@pytest.mark.req("FR-402-AC4")
def test_a_structure_scoped_rule_fires_in_that_structure() -> None:
    """상계거래에서 그 쌍이 배타로 잡힌다."""
    found = collect_exclusions(
        [_StructA(structure="상계거래"), _StructB(structure="상계거래")], _RULES
    )

    assert [(a, b) for a, b, _, _ in found] == [("_StructA", "_StructB")]


@pytest.mark.req("FR-402-AC1", "FR-402-AC4")
def test_the_same_pair_is_allowed_in_another_structure() -> None:
    """★ **다른 구조에서는 걸리지 않는다** — 오탐 0 이 차단 100% 만큼 중요하다.

    이 단언이 없으면 「구조를 무시하고 늘 거는」 구현도 위 테스트를 통과하고,
    그 상태는 `FR-402-AC1` 이 명시로 금지한 방향이다(정당한 동시 계상을 지운다).
    """
    found = collect_exclusions(
        [_StructA(structure="잉여 직거래"), _StructB(structure="잉여 직거래")], _RULES
    )

    assert found == []


# ── ② 구조를 모르는 조합에는 걸리지 않는다 ───────────────────────────

@pytest.mark.req("FR-402-AC1")
def test_streams_without_a_structure_do_not_trigger_structure_rules() -> None:
    """구조를 선언하지 않은 편익에는 구조 한정 규칙이 걸리지 않는다.

    ⚠ **반대로 두면 위험하다.** 「구조를 모르면 전부 적용」으로 읽으면 구조를
    지정하지 않은 **기존 케이스가 갑자기 거부된다** — 프로파일 축이 같은 판단을
    이미 하고 있다(`profile=None` 이면 제도 한정 규칙을 끈다).
    """
    found = collect_exclusions([_StructA(), _StructB()], _RULES)

    assert found == []


# ── ③ 프로파일과 독립으로 걸린다 (설계서가 지적한 구멍) ───────────────

@pytest.mark.req("FR-402-AC4", "FR-205-AC1.NetMetering")
def test_the_structure_axis_fires_regardless_of_the_regulation_profile() -> None:
    """★★★ **구조 규칙이 프로파일과 독립으로 걸린다** — 그 구멍이 이 축의 존재 이유다.

    설계서: *「사용자가 「상계거래」를 고르고도 다른 규제 프로파일을 선택하면 이
    배타 규칙이 조용히 안 걸린다」*.

    `rules_for_profile(None)` 은 **제도 한정 규칙을 끈다**(프로파일을 모르는
    상태에서의 보수적 판정). 그 상태에서도 구조 규칙은 살아 있어야 한다 —
    그러지 않으면 두 축이 사실상 하나로 묶인 것이고 구멍이 그대로다.
    """
    # 프로파일 축으로는 아무 규칙도 남지 않게 한다(구조 규칙은 프로파일이 없다)
    in_effect = rules_for_profile(None, _RULES)
    assert in_effect == _RULES, "구조 한정 규칙이 프로파일 필터에 걸러졌습니다"

    found = collect_exclusions(
        [_StructA(structure="상계거래"), _StructB(structure="상계거래")], in_effect
    )
    assert found, (
        "프로파일을 모르는 상태에서 구조 규칙이 꺼졌습니다 — 두 축이 하나로 "
        "묶였고 설계서가 지적한 구멍이 그대로입니다"
    )


@pytest.mark.req("FR-402-AC4", "FR-205-AC1.NetMetering")
def test_the_real_table_has_a_structure_scoped_rule() -> None:
    """실물 규칙표가 구조 축을 **실제로 쓴다**.

    축만 만들고 쓰지 않으면 이 저장소가 반복해 만난 형태가 된다 — 기계는 있고
    부르는 곳이 없다. 그러면 축이 동작하는지 아무도 확인하지 않는다.
    """
    from core.valuestream.exclusion_table import DEFAULT_EXCLUSION_RULES

    scoped = [r for r in DEFAULT_EXCLUSION_RULES if r.applies_to_structure is not None]

    assert scoped, "실물 규칙표에 구조 한정 규칙이 하나도 없습니다"
    for rule in scoped:
        assert rule.rationale.strip(), f"{rule.benefit_a}↔{rule.benefit_b} 근거가 비었습니다"


# ── ④ 오타 난 구조 이름은 기동 시점에 터진다 ─────────────────────────

@pytest.mark.req("FR-402-AC4", "FR-205-AC1.NetMetering")
def test_a_misspelled_structure_name_is_refused_at_load_time() -> None:
    """★★ 열거 밖의 구조 이름은 **로드 시점에** 거부된다.

    통과시키면 그 규칙은 어느 케이스에도 매치되지 않아 **조용히 꺼진 채** 규칙표에
    남고, 읽는 사람은 금지가 걸려 있다고 믿는다. `payer_by_structure` 의 키를
    `__init_subclass__` 가 기동 시점에 대조하는 것과 같은 근거다.
    """
    text = """
rules:
  - benefit_a: REC
    benefit_b: SurplusSale
    type: D
    rationale: 오타 검사
    applies_to_structure: 상계
"""
    with pytest.raises(ExclusionRulesError) as caught:
        load_exclusion_rules_from_text(text)

    message = str(caught.value)
    assert "상계" in message
    # 허용 목록을 사유에 실어 「무엇을 고르라」를 말한다
    assert "상계거래" in message
    assert "조용히 꺼집니다" in message


@pytest.mark.req("FR-402-AC4")
def test_a_valid_structure_name_loads() -> None:
    """정상 구조 이름은 통과한다 — 무엇이든 거부하지 않는다."""
    text = """
rules:
  - benefit_a: REC
    benefit_b: SurplusSale
    type: D
    rationale: 정상 검사
    applies_to_structure: 분산특구 직접거래
"""
    (rule,) = load_exclusion_rules_from_text(text)

    assert rule.applies_to_structure == "분산특구 직접거래"
