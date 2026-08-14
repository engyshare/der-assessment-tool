from typing import Any

import pytest

from core.assumption.item import AssumptionItem, ConfidenceLevel
from core.assumption.provider import AssumptionSet
from core.contracts.assumptions import PriceBasis


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
        price_basis=PriceBasis.NOMINAL,
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
        price_basis=PriceBasis.NOMINAL,
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

    AC1(시나리오 수준 개별 오버라이드)·AC2(기준 전제 대비 변경 목록 자동
    생성)·AC3(오버라이드 사유는 권장 필드) 를 각각 별도 단언으로 본다 —
    하나만 통과해도 나머지가 통과처럼 보이지 않게.
    """
    aset = AssumptionSet(
        name="TestSet", version="v1",
        items={
            "base.key": _item("base.key", 1.0),
            "untouched.key": _item("untouched.key", 9.0),
        },
        price_basis=PriceBasis.NOMINAL,
    )

    # ── AC1: 시나리오 수준에서 특정 항목만 덮어쓸 수 있다 ──────────────
    overridden = aset.override({"base.key": 2.0})

    over_val = overridden.get("base.key")
    assert over_val is not None
    assert over_val.value == 2.0
    assert overridden.get_overrides() == {"base.key": 2.0}
    # 건드리지 않은 항목은 그대로다
    assert overridden.get("untouched.key") is not None
    assert overridden.get("untouched.key").value == 9.0  # type: ignore[union-attr]
    # 원본은 불변
    orig_val = aset.get("base.key")
    assert orig_val is not None
    assert orig_val.value == 1.0

    # ── AC2: 기준 전제 대비 변경 항목 목록이 자동 생성된다 ─────────────
    changed = overridden.overridden_items()
    assert set(changed) == {"base.key"}
    assert changed["base.key"]["base"] == 1.0
    assert changed["base.key"]["override"] == 2.0
    # 오버라이드하지 않은 항목은 "변경 목록"에 나타나지 않는다
    assert "untouched.key" not in changed

    # ── AC3: 오버라이드 시 사유 입력은 "권장" 필드다 ───────────────────
    # 사유 없이도 오버라이드가 성립해야 한다 (필수화하면 조항을 넘어선다)
    assert overridden.get_override_reasons() == {}

    with_reason = aset.override(
        {"base.key": 2.0}, reasons={"base.key": "실증단지 견적 반영"}
    )
    assert with_reason.get_override_reasons() == {"base.key": "실증단지 견적 반영"}
    assert with_reason.overridden_items()["base.key"]["reason"] == "실증단지 견적 반영"
