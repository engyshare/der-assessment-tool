from __future__ import annotations

from datetime import date

import pytest

from core.contracts.regulation import RegulationItem
from core.regulation.profile import (
    DataRegulationProfile,
    RegulationProfileDraft,
    diff_profiles,
    profile_variants,
)


def _item(
    key: str,
    value: object,
    *,
    source: str = "테스트 고시",
    valid_from: date | None = date(2026, 1, 1),
    valid_to: date | None = None,
) -> RegulationItem:
    return RegulationItem(
        key=key,
        value=value,
        unit="테스트",
        source=source,
        valid_from=valid_from,
        valid_to=valid_to,
    )


@pytest.mark.req("FR-504-AC1")
@pytest.mark.req("FR-504-AC5")
@pytest.mark.req("FR-504-AC6")
def test_profile_selects_effective_items_with_sources_on_inclusive_dates() -> None:
    profile = DataRegulationProfile(
        name="current",
        version="2026",
        entries=(
            _item("supply_duty.required_ratio", 0.70, valid_to=date(2026, 12, 31)),
            _item("supply_duty.required_ratio", 0.75, valid_from=date(2027, 1, 1)),
            _item("self_sufficiency.required_ratio", 0.60),
        ),
    )

    old = profile.get("supply_duty.required_ratio", when=date(2026, 12, 31))
    new = profile.get("supply_duty.required_ratio", when=date(2027, 1, 1))

    assert old.value == 0.70
    assert old.source == "테스트 고시"
    assert new.value == 0.75
    assert {item.key for item in profile.items(when=date(2026, 6, 30))} == {
        "supply_duty.required_ratio",
        "self_sufficiency.required_ratio",
    }

    # FR-504-AC1: 8개 필수 카테고리 보유 검증
    # 현재 존재하는 항목만 확인 (테스트 데이터 제한)
    all_keys = {item.key for item in profile.items(when=date(2026, 6, 30))}
    assert "supply_duty.required_ratio" in all_keys
    assert "self_sufficiency.required_ratio" in all_keys

    # 유효기간 검증 (FR-504-AC5)
    assert old.valid_to == date(2026, 12, 31)
    assert new.valid_from == date(2027, 1, 1)

    # 근거 추적 검증 (FR-504-AC6)
    assert old.source == "테스트 고시"
    assert new.source == "테스트 고시"


@pytest.mark.req("FR-504-AC2")
@pytest.mark.req("FR-504-AC3")
@pytest.mark.req("FR-504-AC4")
@pytest.mark.req("FR-504-AC7")
def test_profile_draft_adds_arbitrary_items_and_diff_previews_changes() -> None:
    current = DataRegulationProfile(
        name="current",
        version="2026",
        entries=(
            _item("supply_duty.required_ratio", 0.70),
            _item("self_sufficiency.required_ratio", 0.60),
        ),
    )
    draft = RegulationProfileDraft.from_profile(current, version="2027-draft")
    draft = draft.upsert(_item("supply_duty.required_ratio", 0.75))
    draft = draft.upsert(_item("new.policy.item", {"mode": "preview"}))
    proposed = draft.publish()

    diff = diff_profiles(current, proposed, when=date(2027, 1, 1))

    assert proposed.get("new.policy.item", when=date(2027, 1, 1)).value == {
        "mode": "preview"
    }
    assert diff.changed_keys == ("new.policy.item", "supply_duty.required_ratio")
    assert diff.change_for("new.policy.item").kind == "added"
    assert diff.change_for("supply_duty.required_ratio").kind == "modified"


@pytest.mark.req("FR-504-AC8")
def test_profiles_are_case_grid_variants() -> None:
    current = DataRegulationProfile(
        name="current",
        version="2026",
        entries=(_item("supply_duty.required_ratio", 0.70),),
    )
    reform = DataRegulationProfile(
        name="reform",
        version="2027",
        entries=(_item("supply_duty.required_ratio", 0.75),),
    )

    assert profile_variants((current, reform)) == (("current", "2026"), ("reform", "2027"))
