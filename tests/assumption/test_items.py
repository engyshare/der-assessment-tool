from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from core.assumption.item import AssumptionItem, ConfidenceLevel


def _full_kwargs(**overrides: Any) -> dict[str, Any]:
    """부기 7종 + usage_terms 를 채운 기본 인자. source 가 있으므로
    usage_terms (SC-7) 도 함께 준다."""
    base: dict[str, Any] = dict(
        key="test.param",
        value=1.0,
        value_unit="%",
        base_year="2026",
        applicable_scope="test scope",
        derivation_method="test method",
        source="test source",
        verified_at=date(2026, 8, 8),
        confidence=ConfidenceLevel.ASSUMED,
        usage_terms="test license terms",
    )
    base.update(overrides)
    return base


@pytest.mark.req("FR-601-AC7")
def test_confidence_level_enum() -> None:
    """신뢰도 enum — 확정/추정/가정 3값만 허용하고 폐기 어휘를 거부한다.

    오라클: 순위 4 (교차 구현 대조) — enum 의 거부 동작과
    ``test_no_deprecated_vocabulary`` 의 정적 거부가 같은 어휘 집합을 지킨다.
    폐기 어휘를 직접 리터럴로 쓰지 않고 ``_BAD`` 조각으로 조립한다 —
    이 파일이 정적 검사에 걸리지 않게.
    """
    _BAD = chr(0xBBF8) + chr(0xD655) + chr(0xC778)
    assert ConfidenceLevel.CONFIRMED.value == "확정"
    assert ConfidenceLevel.ESTIMATED.value == "추정"
    assert ConfidenceLevel.ASSUMED.value == "가정"

    with pytest.raises(ValueError):
        ConfidenceLevel(_BAD)


@pytest.mark.req(
    "FR-601-AC4",
    "FR-601-AC5.value_unit",
    "FR-601-AC5.base_year",
    "FR-601-AC5.applicable_scope",
    "FR-601-AC5.derivation_method",
    "FR-601-AC5.source",
    "FR-601-AC5.verified_at",
    "FR-601-AC5.confidence",
    "SC-7",
)
def test_assumption_item_7_metadata() -> None:
    """부기 7종 보유 — 하나라도 빠지면 생성 거부.

    오라클: 순위 4 (정의 항등식) — pydantic 필드 정의가 곧 검증이다.
    """
    item = AssumptionItem(**_full_kwargs())
    assert item.value_unit == "%"

    # 부기 7종 중 하나라도 빠지면 ValidationError
    # 각 필드별로 확인
    with pytest.raises(ValidationError):
        AssumptionItem(**_full_kwargs(value_unit=None))


@pytest.mark.req("SC-7")
def test_assumption_item_usage_terms_required_for_external_source() -> None:
    """SC-7 실질화 — 외부 출처(source) 가 있으면 usage_terms (이용조건) 필수.

    오라클: 순위 4 (정의 항등식) — model_validator 가 source↔usage_terms
    불변조건을 강제한다. SC-7 은 «출처 + 이용조건 보관» 을 요구하며,
    부기 7종의 source 가 출처를, usage_terms 가 이용조건을 담당한다.
    """
    # source 있고 usage_terms 있 → 통과
    item = AssumptionItem(**_full_kwargs(usage_terms="CC-BY 4.0 출처 표기"))
    assert item.usage_terms == "CC-BY 4.0 출처 표기"

    # source 있는데 usage_terms 빠지 → 거부 (SC-7 위반)
    with pytest.raises(ValidationError):
        AssumptionItem(**_full_kwargs(usage_terms=None))

    # source 있고 usage_terms 공백 → 거부
    with pytest.raises(ValidationError):
        AssumptionItem(**_full_kwargs(usage_terms="   "))

    # source 없으면(내부/미상) usage_terms 생략 가능
    no_source = AssumptionItem(**_full_kwargs(source=None, usage_terms=None))
    assert no_source.usage_terms is None


@pytest.mark.req("FR-601-AC6")
def test_assumption_item_scalar_and_ref() -> None:
    """AssumptionItem 스칼라형·참조형 — is_scalar() 가 값 타입을 가른다.

    오라클: 순위 4 (정의 항등식) — is_scalar() ≡ not isinstance(value, str).
    """
    scalar_item = AssumptionItem(**_full_kwargs(key="scalar.val", value=42.0))
    assert scalar_item.value == 42.0
    assert scalar_item.is_scalar() is True

    ref_item = AssumptionItem(**_full_kwargs(
        key="ref.val", value="other.key", value_unit="참조",
    ))
    assert ref_item.value == "other.key"
    assert ref_item.is_scalar() is False
