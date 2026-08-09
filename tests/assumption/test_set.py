from typing import Any

import pytest

from core.assumption.item import AssumptionItem, ConfidenceLevel
from core.assumption.provider import AssumptionSet


def _item(key: str, value: float, **overrides: Any) -> AssumptionItem:
    """source=None (내부/미상) — usage_terms 생략 가능한 기본 항목."""
    base: dict[str, Any] = dict(
        key=key,
        value=value,
        value_unit="%",
        base_year="2026",
        applicable_scope="t",
        derivation_method="t",
        source=None,
        verified_at=None,
        confidence=ConfidenceLevel.ASSUMED,
    )
    base.update(overrides)
    return AssumptionItem(**base)


@pytest.mark.req("FR-601-AC8", "FR-601-AC9")
def test_assumption_set_version_and_diff() -> None:
    """AssumptionSet 버전·diff — 같은 key 의 값 변화와 key 증감을 가른다.

    오라클: 순위 4 (정의 항등식) — diff(new_keys ∪ old_keys ∪ changed_keys)
    가 set 대칭차와 값 불일치의 합성임을 손계산으로 확인.
    """
    aset = AssumptionSet(
        name="TestSet", version="v1",
        items={"test.key": _item("test.key", 10.0)},
    )
    assert aset.set_name == "TestSet"
    assert aset.set_version == "v1"

    val = aset.get("test.key")
    assert val is not None
    assert val.value == 10.0

    aset2 = AssumptionSet(
        name="TestSet", version="v2",
        items={
            "test.key": _item("test.key", 20.0),
            "new.key": _item("new.key", 1.0, value_unit="원"),
        },
    )

    diff = aset2.diff(aset)
    assert diff["new_keys"] == {"new.key"}
    assert diff["changed_keys"] == {"test.key"}
    assert diff["changes"]["test.key"]["old"] == 10.0
    assert diff["changes"]["test.key"]["new"] == 20.0


@pytest.mark.req("FR-602-AC1", "FR-602-AC2", "FR-602-AC3")
def test_assumption_set_override() -> None:
    """AssumptionSet override — 원본 불변, 사본에 오버라이드 적용.

    오라클: 순위 4 (정의 항등식) — override 가 순수 복제+덮어쓰기임을 확인.
    """
    aset = AssumptionSet(
        name="TestSet", version="v1",
        items={"base.key": _item("base.key", 1.0)},
    )

    overridden = aset.override({"base.key": 2.0})

    over_val = overridden.get("base.key")
    assert over_val is not None
    assert over_val.value == 2.0
    assert overridden.get_overrides() == {"base.key": 2.0}
    # 원본은 불변
    orig_val = aset.get("base.key")
    assert orig_val is not None
    assert orig_val.value == 1.0
