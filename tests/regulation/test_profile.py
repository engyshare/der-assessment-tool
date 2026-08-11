from __future__ import annotations

from datetime import date

import pytest

from core.contracts.regulation import RegulationItem
from core.regulation.profile import (
    DataRegulationProfile,
    ProfileHistory,
    RegulationProfileDraft,
    VerifiedRegulationItem,
    diff_profiles,
    highlight_profile_changes,
    preview_profile_switch,
    profile_case_variable,
    profile_variants,
    require_traceable,
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

    # FR-504-AC6: 근거 링크(source)에 더해 최종확인일(verified_at)도 있어야
    # 하고, 둘 중 하나라도 없으면 require_traceable() 이 잡아야 한다.
    verified = VerifiedRegulationItem(
        key="supply_duty.required_ratio",
        value=0.70,
        unit="테스트",
        source="테스트 고시",
        valid_from=date(2026, 1, 1),
        verified_at=date(2026, 8, 1),
    )
    assert require_traceable(verified) is verified

    missing_verified_at = _item("supply_duty.required_ratio", 0.70)
    with pytest.raises(ValueError, match="최종확인일"):
        require_traceable(missing_verified_at)

    missing_source = VerifiedRegulationItem(
        key="supply_duty.required_ratio",
        value=0.70,
        unit="테스트",
        source=None,
        valid_from=date(2026, 1, 1),
        verified_at=date(2026, 8, 1),
    )
    with pytest.raises(ValueError, match="출처"):
        require_traceable(missing_source)


@pytest.mark.req("FR-504-AC2")
# ⚠ 아래 `FR-504-AC3` 은 **조항을 붙들지 못한다. 그래도 유지한다** (R20 판정).
# `AC3` 은 *「**admin 권한** 사용자가 **웹 UI** 에서 프로파일을 생성·복제·수정한다.
# 파일 수정이나 재배포를 요구하지 않는다」* 인데, 아래 검사는 `RegulationProfileDraft`
# 의 **순수 파이썬 객체 조작**을 본다. 웹 UI 도 권한 검사도 지나지 않는다.
#
# **그런데 지우면 안 된다.** 이 마커가 `FR-504-AC3`(Must-have·Phase 1)의 **유일한
# 매핑**이고, 웹 UI·admin 권한 검사가 저장소 어디에도 없다. 지우면 조항이
# 미매핑이 되어 `test_17_9_dod9` 가 빨간불이 되며 대체 검증도 만들 수 없다.
#
# **닫는 조건**: 웹 UI 의 프로파일 편집 화면과 admin 권한 검사를 구현하고,
# 그것을 보는 테스트로 이 마커를 옮긴 뒤 여기서 지운다. `FR-901`(인증)이 선행이다.
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

    # FR-504-AC4 「버전」: 두 버전은 서로 다른 version 을 갖는다
    assert current.version == "2026"
    assert proposed.version == "2027-draft"

    # FR-504-AC4 「복원」: 이력에 기록해 두면 이전 버전으로 되짚을 수 있다
    history = ProfileHistory((current,)).record(proposed)
    assert history.restore("2026") is current
    assert history.restore("2027-draft") is proposed
    with pytest.raises(KeyError):
        history.restore("no-such-version")

    # FR-504-AC7 「미리보기」: 재실행 없이 diff 로 변경 항목을 미리 본다
    preview = preview_profile_switch(current, proposed, when=date(2027, 1, 1))
    assert preview.changed_keys == diff.changed_keys

    # FR-504-AC7 「강조」: 재실행 결과 차이를 항목별로 강조 표시할 수 있다
    highlights = highlight_profile_changes(diff)
    by_key = {h.key: h for h in highlights}
    assert by_key["new.policy.item"].kind == "added"
    assert by_key["new.policy.item"].relative_change is None
    supply = by_key["supply_duty.required_ratio"]
    assert supply.kind == "modified"
    assert supply.before_value == 0.70
    assert supply.after_value == 0.75
    # (0.75 - 0.70) / 0.70 = 0.05 / 0.70 = 1/14 손계산
    assert supply.relative_change == pytest.approx(1 / 14)


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

    # 함수 이름은 "케이스 그리드 변형" 이라 하면서 단언이 튜플 하나뿐이면
    # 이름만 조항이 된다. 케이스 그리드 축(이름 + 값들)까지 실제로 만든다.
    axis = profile_case_variable("regulation_profile", (current, reform))
    assert axis.name == "regulation_profile"
    assert axis.values == (("current", "2026"), ("reform", "2027"))
    assert len(axis.values) == 2
