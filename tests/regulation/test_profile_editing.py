"""FR-504-AC3 편집 연산 — 생성·복제·수정 (WP-3).

조항의 세 낱말 중 **「수정」만 있었다** — `RegulationProfileDraft.upsert` 다.
「생성」(없던 프로파일을 만든다)과 「복제」(현행에서 개정안을 뜬다)는 초안 연산이
없었고, 그래서 웹 편집 화면을 놓을 자리가 비어 있었다.

여기서 붙드는 것은 연산 셋과 **그 셋이 서로 섞이지 않는 것**이다. 복제가 원본과
같은 이름을 내면 그것은 복제가 아니라 새 버전이고, 그 둘을 한 함수가 하면
「현행」이 조용히 사라진다.
"""

from __future__ import annotations

from datetime import date

import pytest

from core.contracts.regulation import RegulationItem
from core.contracts.validation import ValidationError
from core.regulation.profile import (
    ProfileHistory,
    RegulationProfileDraft,
    diff_profiles,
)

_WHEN = date(2026, 6, 30)


def _item(key: str, value: object, *, source: str = "테스트 고시") -> RegulationItem:
    return RegulationItem(key=key, value=value, unit=None, source=source)


@pytest.mark.req("FR-504-AC3")
def test_create_makes_an_empty_named_profile() -> None:
    """「생성」 — 없던 프로파일을 이름과 버전으로 만든다."""
    draft = RegulationProfileDraft.create(name="현행", version="v2026.1")
    published = draft.publish()

    assert published.name == "현행"
    assert published.version == "v2026.1"
    assert published.items(when=_WHEN) == []


@pytest.mark.req("FR-504-AC3")
def test_clone_carries_the_items_into_a_differently_named_profile() -> None:
    """「복제」 — 항목을 물려받고 이름은 달라진다.

    「현행」을 복제해 「개정안」을 만드는 것이 조항이 겨냥한 쓰임이다
    (FR-504-AC8 비교 실행의 입력).
    """
    current = (
        RegulationProfileDraft.create(name="현행", version="v2026.1")
        .upsert(_item("supply_duty.required_ratio", 0.70))
        .upsert(_item("exemption.years", 3))
    )

    revised = current.clone(name="개정안", version="v2027.0").publish()

    assert revised.name == "개정안"
    assert revised.version == "v2027.0"
    assert {i.key for i in revised.items(when=_WHEN)} == {
        "supply_duty.required_ratio",
        "exemption.years",
    }
    # 원본은 그대로다 — 복제가 원본을 소모하면 「현행」을 잃는다
    assert current.publish().name == "현행"
    assert current.publish().version == "v2026.1"


@pytest.mark.req("FR-504-AC3")
def test_clone_refuses_the_source_name() -> None:
    """복제본이 원본과 같은 이름이면 거부한다 — 그것은 새 버전이지 복제가 아니다."""
    current = RegulationProfileDraft.create(name="현행", version="v2026.1")

    with pytest.raises(ValidationError) as caught:
        current.clone(name="현행", version="v2027.0")

    assert caught.value.field == "regulation.profile_name"
    assert "같은 이름" in caught.value.reason
    assert caught.value.action.strip()


@pytest.mark.req("FR-504-AC3")
def test_edits_are_refused_without_a_name_or_a_version() -> None:
    """이름 없는 프로파일도, 버전 없는 프로파일도 만들 수 없다.

    버전이 없으면 FR-504-AC4 의 「이전 버전으로 복원」이 성립하지 않는다.
    """
    with pytest.raises(ValidationError, match="이름이 비어"):
        RegulationProfileDraft.create(name="  ", version="v1")

    with pytest.raises(ValidationError, match="버전이 비어"):
        RegulationProfileDraft.create(name="현행", version="")

    base = RegulationProfileDraft.create(name="현행", version="v1")
    with pytest.raises(ValidationError, match="버전이 비어"):
        base.clone(name="개정안", version="   ")


@pytest.mark.req("FR-504-AC3")
def test_update_publishes_a_new_version_that_diffs_against_the_old_one() -> None:
    """「수정」이 새 버전을 낳고, 두 버전의 차이를 짚을 수 있다.

    제자리에서 고치면 FR-504-AC4 의 「이전 버전으로 복원」과 「diff 뷰」가 볼
    대상이 남지 않는다.
    """
    first = (
        RegulationProfileDraft.create(name="현행", version="v2026.1")
        .upsert(_item("supply_duty.required_ratio", 0.70))
        .publish()
    )
    history = ProfileHistory((first,))

    second = (
        RegulationProfileDraft.from_profile(first, version="v2026.2")
        .upsert(_item("supply_duty.required_ratio", 0.75))
        .publish()
    )
    history = history.record(second)

    assert second.get("supply_duty.required_ratio", when=_WHEN).value == 0.75
    # 이전 버전이 살아 있다
    restored = history.restore("v2026.1")
    assert restored.get("supply_duty.required_ratio", when=_WHEN).value == 0.70

    changed = diff_profiles(restored, second, when=_WHEN)
    assert changed.changed_keys == ("supply_duty.required_ratio",)
    assert changed.change_for("supply_duty.required_ratio").kind == "modified"


@pytest.mark.req("FR-504-AC3")
def test_update_adds_an_item_the_schema_never_declared() -> None:
    """새 제도 항목을 **스키마 변경 없이** 넣는다 (FR-504-AC2 와 같은 자리).

    편집 경로가 고정 컬럼을 요구하면 제도 신설 항목마다 코드 배포가 필요해지고,
    그것이 조항이 금지하는 「재배포」의 실물이다.
    """
    # 값이 목록인 항목 — 수치로 좁힌 스키마라면 여기서 걸린다
    exclusive_rules = ["REC-상계 배타", "DR-요금 중복 금지"]
    profile = (
        RegulationProfileDraft.create(name="현행", version="v2026.1")
        .upsert(_item("benefit.exclusive_rules", exclusive_rules))
        .publish()
    )

    stored = profile.get("benefit.exclusive_rules", when=_WHEN)
    assert stored.value == exclusive_rules
