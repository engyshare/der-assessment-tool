"""배타 규칙표가 **데이터**인가, 그리고 위반을 **거부**하는가 — FR-402-AC2.A · AC4.

두 가지가 R15 까지 어긋나 있었다.

  ① `exclusion_table.py` 는 「규칙이 코드가 아닌 데이터다」라고 적어 두고
     규칙을 **파이썬 튜플 상수**로 들고 있었다. 「`if` 문으로 옮기지 말 것」은
     지켜졌지만, 제도가 바뀌면 여전히 파이썬 파일을 고쳐 배포해야 했다.
  ② 조항은 *「선택 시 검증 오류로 **거부**한다」* 인데 저장소에는
     **감지·라벨링뿐**이었다. 리포트가 「배타제외」로 **표시**할 뿐 아무것도
     막지 않았다.

**검증의 핵심은 로더가 있는지가 아니다** (R15 요금표에서 배운 것):
같은 전제값·**같은 코드**에 **데이터만 바꿔** 결과가 달라지는 것을 고정한다.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.validation import ValidationError
from core.contracts.valuestream import Payer, ValueStream
from core.valuestream.exclusion_loader import (
    ExclusionRulesError,
    load_exclusion_rules,
    load_exclusion_rules_from_text,
)
from core.valuestream.exclusion_table import (
    DEFAULT_EXCLUSION_RULES,
    assert_no_exclusions,
    collect_exclusions,
)


def _stub(tag_name: str) -> ValueStream:
    """`tag` 만 다른 최소 편익 — 배타 판정은 `tag` 로만 이루어진다."""

    class _Stub(ValueStream):
        tag: ClassVar[str] = tag_name
        payer: ClassVar[Payer] = Payer.OPERATOR
        #: 이 스텁은 0원을 돌려주므로 창과 무관하다 (R34 계약).
        scales_with_dispatch_window = False

        def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
            return to_won(0)

        def formula(self, dispatch: DispatchResult, *, year: int) -> str:
            return "검사용 스텁 0원"

    return _Stub(name=f"stub:{tag_name}")


@pytest.mark.contract
@pytest.mark.req("FR-402-AC4")
def test_the_table_comes_from_the_data_file() -> None:
    """정본은 `docs/exclusion-rules.yaml` 이다 — 상수가 그것을 읽은 결과다."""
    from_file = load_exclusion_rules()
    assert from_file == DEFAULT_EXCLUSION_RULES
    # **건수를 못 박는다** — 규칙이 조용히 사라지는 것을 잡는다. 규칙을 더했으면
    # 이 수를 함께 고치는 것이 맞고, 고치지 않고 지나갈 수 없게 하는 것이 요점이다.
    # (R31 이 계약구조 축 규칙 하나를 더해 4 → 5, R32 가 집합 PPA 배타 둘을 더해
    #  5 → 7 이 됐다 — PPA 는 전량 판매이므로 잉여판매·자가소비 **둘 다** 막는다.)
    assert len(from_file) == 7


@pytest.mark.contract
@pytest.mark.req("FR-402-AC2.A")
def test_type_a_violation_is_refused_not_merely_labelled() -> None:
    """★ **거부한다.** 표시로 끝나지 않는다.

    `collect_exclusions` 는 위반을 «찾아» 돌려주고, `assert_no_exclusions`
    는 그것을 «막는다». 조항이 요구하는 것은 뒤쪽이다.
    """
    streams = [_stub("SelfConsumption"), _stub("SurplusSale")]

    found = collect_exclusions(streams)
    assert found, "감지 자체가 되지 않는다"

    with pytest.raises(ValidationError) as caught:
        assert_no_exclusions(streams)
    err = caught.value
    assert err.rule == "DV-12"
    assert "SelfConsumption" in err.reason
    assert err.action.strip()


@pytest.mark.contract
@pytest.mark.req("FR-402-AC1")
def test_types_b_to_d_are_not_refused() -> None:
    """**유형 B~D 는 막지 않는다** — 행마다 수용 수준이 반대다.

    `A` 는 차단 100%(음성 검증)이고 `B`~`D` 는 **오탐 0**(양성 검증)이다.
    여기서 함께 막으면 정당한 동시 계상을 지우게 되고, 그것은 FR-402-AC1 이
    명시로 금지한 방향이다 — *「동시 발생 효과는 중복이 아니다」*.
    """
    # 유형 B 쌍 — 증분만 계상해야 하는 관계이지 금지 관계가 아니다
    streams = [_stub("DistributedBenefit"), _stub("SelfConsumption")]
    assert collect_exclusions(streams), "유형 B 가 감지는 되어야 한다"
    assert_no_exclusions(streams)      # 예외가 나면 안 된다


@pytest.mark.contract
@pytest.mark.req("FR-402-AC4")
def test_changing_only_the_data_changes_the_verdict() -> None:
    """★★ **확장점 증명** — 같은 코드에 데이터만 바꿔 결과가 달라진다.

    R15 요금표가 쓴 검증 방식 그대로다. 「로더가 있다」는 아무것도 증명하지
    않는다 — 증명되는 것은 **제도 개정이 코드 변경 없이 반영되는가** 이며,
    그것이 FR-402-AC4 가 요구하는 바다.
    """
    streams = [_stub("PeakShaving"), _stub("HeatCostSaving")]

    # ① 정본 규칙표에는 이 쌍이 없다 → 통과한다
    assert_no_exclusions(streams)

    # ② **파이썬은 한 줄도 고치지 않고** 규칙표에만 한 쌍을 더한다
    amended = load_exclusion_rules_from_text(
        """
        version: 1
        rules:
          - benefit_a: PeakShaving
            benefit_b: HeatCostSaving
            type: A
            rationale: 증명용 — 같은 물리량을 두 번 판다고 가정한다
        """,
        source="<증명용>",
    )

    # ③ 같은 함수가 이제 거부한다
    with pytest.raises(ValidationError) as caught:
        assert_no_exclusions(streams, amended)
    assert "PeakShaving" in caught.value.reason


@pytest.mark.contract
@pytest.mark.req("FR-402-AC4")
def test_an_empty_table_is_an_error_not_a_pass() -> None:
    """빈 규칙표는 「배타 없음」이 아니라 **「검사 없음」**이다.

    조용히 통과시키면 배타 검사가 「위반 0건」을 내고, 그 결과는 정상
    결과와 구분되지 않는다.
    """
    with pytest.raises(ExclusionRulesError, match=r"검사 없음|비어 있습니다"):
        load_exclusion_rules_from_text("version: 1\nrules: []\n")


@pytest.mark.contract
@pytest.mark.req("FR-402-AC4")
def test_malformed_rules_are_refused_at_load() -> None:
    """유형 오타·중복 쌍·자기 자신과의 배타는 읽는 시점에 터진다."""
    base = "version: 1\nrules:\n"

    with pytest.raises(ExclusionRulesError, match="A~D"):
        load_exclusion_rules_from_text(
            base + "  - {benefit_a: X, benefit_b: Y, type: E, rationale: r}\n"
        )

    with pytest.raises(ExclusionRulesError, match="이미 선언된 쌍"):
        load_exclusion_rules_from_text(
            base
            + "  - {benefit_a: X, benefit_b: Y, type: A, rationale: r}\n"
            + "  - {benefit_a: Y, benefit_b: X, type: A, rationale: r}\n"
        )

    with pytest.raises(ExclusionRulesError, match="같은 편익끼리"):
        load_exclusion_rules_from_text(
            base + "  - {benefit_a: X, benefit_b: X, type: A, rationale: r}\n"
        )

    with pytest.raises(ExclusionRulesError, match="rationale"):
        load_exclusion_rules_from_text(
            base + "  - {benefit_a: X, benefit_b: Y, type: A}\n"
        )
