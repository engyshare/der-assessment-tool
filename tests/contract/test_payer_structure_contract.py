"""지불 주체가 **계약구조에 따라 갈리는** 것을 계약이 표현하는가 — FR-205 · FR-402-AC5.

**R15 까지 이것은 표현할 방법이 아예 없었다.** `payer` 가 `ClassVar` 하나였고,
같은 잉여 판매라도 상계거래에서는 주민 지갑이고 집합 PPA 에서는 사업자
지갑인데 클래스에 하나로 고정돼 있으니 **둘 중 하나는 반드시 틀린 값**이었다.
`R13-WP24G-설계서` 가 `FR-205` 정산엔진을 「빈 구현이 아니라 빈 조립도」라
부른 자리가 여기다.

이 파일이 붙드는 것 셋:
  ① 구조에 따라 실제로 다른 주체가 나오는가
  ② 그 값을 **판정·리포트가 함께** 쓰는가 (`payer` 를 직접 읽는 곳이 남으면
     선언이 무시된다)
  ③ 오타 난 구조 이름이 **기동 시점에** 터지는가
"""

from __future__ import annotations

from types import MappingProxyType
from typing import ClassVar

import pytest

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.validation import ValidationError
from core.contracts.valuestream import CONTRACT_STRUCTURES, Payer, ValueStream
from core.valuestream.payer_gate import assess


class _StructureBound(ValueStream):
    """구조에 따라 지갑이 갈리는 편익 — 이 계약이 새로 표현하게 된 것."""

    tag: ClassVar[str] = "_TestStructureBound"
    payer_by_structure: ClassVar[dict[str, Payer]] = MappingProxyType(  # type: ignore[assignment]
        {
            "상계거래": Payer.RESIDENT,
            "집합 PPA": Payer.OPERATOR,
        }
    )

    def __init__(self, *, enabled: bool = True, structure: str | None = None) -> None:
        super().__init__(name="구조 종속 편익", enabled=enabled, structure=structure)

    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        return to_won(0)


@pytest.mark.contract
@pytest.mark.req("FR-205-AC1")
def test_same_benefit_different_structure_different_payer() -> None:
    """★ 같은 편익이 구조에 따라 다른 지갑을 가리킨다."""
    assert _StructureBound(structure="상계거래").effective_payer is Payer.RESIDENT
    assert _StructureBound(structure="집합 PPA").effective_payer is Payer.OPERATOR


@pytest.mark.contract
@pytest.mark.req("FR-402-AC5")
def test_structure_absent_falls_back_and_is_refused_when_unspecified() -> None:
    """구조를 모르면 클래스 기본값으로 떨어지고, 그것이 미특정이면 거부한다.

    **조용히 아무 주체나 고르지 않는다.** 고르면 그 편익은 틀린 지갑에
    계상되고 관점별 합계(FR-704)가 어긋나는데, 어디서 어긋났는지는
    드러나지 않는다.
    """
    with pytest.raises(ValidationError) as caught:
        _StructureBound(structure=None)
    assert caught.value.rule == "DV-13"
    assert "지불 주체" in caught.value.reason
    assert caught.value.action.strip()

    # 선언에 없는 구조도 같다 — 매치되지 않으면 기본값(미특정)이다
    with pytest.raises(ValidationError):
        _StructureBound(structure="분산특구 직접거래")


@pytest.mark.contract
@pytest.mark.req("FR-402-AC5")
def test_existing_callers_still_catch_valueerror() -> None:
    """DV-13 거부가 `ValidationError` 가 됐지만 **`ValueError` 로 계속 잡힌다.**

    `tests/valuestream/test_formulas.py` 가 `pytest.raises(ValueError)` 로
    받고 있다. 기반 예외를 갈아 끼웠다면 그 자리가 조용히 통과했을 것이다.
    """
    with pytest.raises(ValueError, match="지불 주체"):
        _StructureBound(structure=None)


@pytest.mark.contract
@pytest.mark.req("FR-402-AC5")
def test_the_four_question_gate_reads_the_resolved_payer() -> None:
    """★ **판정이 같은 통로를 지난다.**

    `assess()` 가 `stream.payer` 를 직접 읽으면, 구조를 지정해 정상
    활성화된 편익이 Q1 실패로 잡힌다 — 클래스 기본값은 미특정이기 때문이다.
    """
    verdict = assess(_StructureBound(structure="상계거래"))
    assert verdict.q1_payer_specified is True
    assert verdict.passed is True


@pytest.mark.contract
@pytest.mark.req("FR-205-AC1")
def test_unknown_structure_in_the_table_fails_at_class_definition() -> None:
    """★ 오타는 **기동 시점에** 터진다.

    매치되지 않는 키는 영영 쓰이지 않으므로 그 편익이 조용히 기본 `payer`
    로 떨어진다. 지불 주체가 틀린 채 계산이 끝나고 결과는 그럴듯하다 —
    `discover()` 가 `tag` 중복을 늦게 발견하면 안 되는 것과 같은 이유다.
    """
    with pytest.raises(ValueError, match="FR-205-AC1"):

        class _Typo(ValueStream):
            tag = "_TestTypo"
            payer_by_structure = MappingProxyType({"상계 거래": Payer.RESIDENT})

            def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
                return to_won(0)


@pytest.mark.contract
@pytest.mark.req("FR-205-AC1")
def test_structure_vocabulary_is_the_spec_literal() -> None:
    """구조 이름은 spec `FR-205-AC1` 이 적은 리터럴 일곱이다."""
    assert len(CONTRACT_STRUCTURES) == 7
    assert "상계거래" in CONTRACT_STRUCTURES
    assert "VPP 경유" in CONTRACT_STRUCTURES
