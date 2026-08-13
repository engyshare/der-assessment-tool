"""Data-backed regulation profile implementation for WP-3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from core.contracts.regulation import RegulationItem, RegulationProfile
from core.contracts.validation import ValidationError


@dataclass(frozen=True)
class DataRegulationProfile(RegulationProfile):
    name: str
    version: str
    entries: tuple[RegulationItem, ...]

    def get(self, key: str, *, when: date) -> RegulationItem:
        candidates = [
            item for item in self.entries
            if item.key == key and item.applies_on(when)
        ]
        if not candidates:
            raise KeyError(key)
        return max(candidates, key=lambda item: item.valid_from or date.min)

    def items(self, *, when: date) -> list[RegulationItem]:
        selected: dict[str, RegulationItem] = {}
        for item in self.entries:
            if item.applies_on(when):
                previous = selected.get(item.key)
                if previous is None or _later(item, previous):
                    selected[item.key] = item
        return [selected[key] for key in sorted(selected)]


def _later(left: RegulationItem, right: RegulationItem) -> bool:
    return (left.valid_from or date.min) > (right.valid_from or date.min)


def _checked_name(name: str) -> str:
    """프로파일 이름 — 비면 거부한다. 이름 없는 프로파일은 지목할 수 없다."""
    if not isinstance(name, str) or not name.strip():
        raise ValidationError(
            field="regulation.profile_name",
            reason="프로파일 이름이 비어 있습니다",
            action="「현행」·「개정안」처럼 사람이 고를 수 있는 이름을 주십시오",
        )
    return name


def _checked_version(version: str) -> str:
    """프로파일 버전 — 비면 거부한다. 버전이 없으면 이력·복원이 성립하지 않는다."""
    if not isinstance(version, str) or not version.strip():
        raise ValidationError(
            field="regulation.profile_version",
            reason="프로파일 버전이 비어 있습니다",
            action=(
                "`v2026.1` 처럼 버전을 주십시오 — 버전이 없으면 개정 이력과 "
                "복원(FR-504-AC4)이 성립하지 않습니다"
            ),
        )
    return version


@dataclass(frozen=True)
class RegulationProfileDraft:
    name: str
    version: str
    entries: tuple[RegulationItem, ...]

    @classmethod
    def from_profile(cls, profile: DataRegulationProfile,
                     *, version: str) -> RegulationProfileDraft:
        return cls(name=profile.name, version=version, entries=profile.entries)

    @classmethod
    def create(cls, *, name: str, version: str) -> RegulationProfileDraft:
        """빈 프로파일 초안 — FR-504-AC3 「생성」.

        `from_profile` 은 기존 프로파일의 **다음 버전**을 만드는 것이고, 이것은
        **없던 프로파일**을 만드는 것이다. 둘을 한 함수로 두면 「원본 없이
        만든다」가 `None` 을 넘기는 특수 경우가 되고, 그 경우를 잊은 호출부가
        빈 이름의 프로파일을 만들어 낸다.
        """
        return cls(name=_checked_name(name), version=_checked_version(version), entries=())

    def clone(self, *, name: str, version: str) -> RegulationProfileDraft:
        """항목을 물려받은 **별개** 프로파일 — FR-504-AC3 「복제」.

        「현행」을 복제해 「개정안」을 만드는 것이 이 조항이 겨냥한 쓰임이다
        (FR-504-AC8 비교 실행의 입력). 원본과 **이름이 같으면 복제가 아니라
        새 버전**이므로 거부한다 — 그것은 `from_profile` 의 일이다.
        """
        new_name = _checked_name(name)
        if new_name == self.name:
            raise ValidationError(
                field="regulation.profile_name",
                reason=(
                    f"복제본이 원본과 같은 이름입니다: {new_name!r}. 같은 이름의 "
                    "다음 버전을 만드는 것은 복제가 아닙니다"
                ),
                action=(
                    "복제본에 다른 이름을 주십시오. 같은 프로파일의 다음 버전이라면 "
                    "`from_profile` 로 버전을 올리십시오"
                ),
            )
        return RegulationProfileDraft(
            name=new_name, version=_checked_version(version), entries=self.entries
        )

    def upsert(self, item: RegulationItem) -> RegulationProfileDraft:
        kept = tuple(entry for entry in self.entries if entry.key != item.key)
        return RegulationProfileDraft(self.name, self.version, (*kept, item))

    def publish(self) -> DataRegulationProfile:
        return DataRegulationProfile(
            name=self.name,
            version=self.version,
            entries=self.entries,
        )


@dataclass(frozen=True)
class ProfileChange:
    key: str
    kind: Literal["added", "removed", "modified"]
    before: RegulationItem | None
    after: RegulationItem | None


@dataclass(frozen=True)
class ProfileDiff:
    changes: tuple[ProfileChange, ...]

    @property
    def changed_keys(self) -> tuple[str, ...]:
        return tuple(change.key for change in self.changes)

    def change_for(self, key: str) -> ProfileChange:
        for change in self.changes:
            if change.key == key:
                return change
        raise KeyError(key)


def diff_profiles(left: RegulationProfile, right: RegulationProfile,
                  *, when: date) -> ProfileDiff:
    left_items = {item.key: item for item in left.items(when=when)}
    right_items = {item.key: item for item in right.items(when=when)}
    changes: list[ProfileChange] = []

    for key in sorted(set(left_items) | set(right_items)):
        before = left_items.get(key)
        after = right_items.get(key)
        if before is None and after is not None:
            changes.append(ProfileChange(key, "added", None, after))
        elif before is not None and after is None:
            changes.append(ProfileChange(key, "removed", before, None))
        elif before != after:
            changes.append(ProfileChange(key, "modified", before, after))

    return ProfileDiff(tuple(changes))


def profile_variants(
    profiles: tuple[RegulationProfile, ...],
) -> tuple[tuple[str, str], ...]:
    return tuple((profile.name, profile.version) for profile in profiles)


@dataclass(frozen=True)
class ProfileHistory:
    """FR-504-AC4 「복원」: 버전 이력 보관 및 이름으로 되짚기.

    버전 자체는 `DataRegulationProfile.version`이 이미 갖고 있다(FR-504-AC1).
    남는 것은 지나간 버전을 잃지 않고 이름으로 다시 꺼내는 것뿐이다.
    """

    versions: tuple[DataRegulationProfile, ...]

    def record(self, profile: DataRegulationProfile) -> ProfileHistory:
        return ProfileHistory((*self.versions, profile))

    def restore(self, version: str) -> DataRegulationProfile:
        for profile in self.versions:
            if profile.version == version:
                return profile
        raise KeyError(version)


def preview_profile_switch(
    current: RegulationProfile, proposed: RegulationProfile, *, when: date
) -> ProfileDiff:
    """FR-504-AC7 「미리보기」: 시나리오 프로파일 참조 교체 영향을 재실행 없이 본다."""
    return diff_profiles(current, proposed, when=when)


@dataclass(frozen=True)
class ProfileChangeHighlight:
    key: str
    kind: Literal["added", "removed", "modified"]
    before_value: Any
    after_value: Any
    relative_change: float | None


def highlight_profile_changes(diff: ProfileDiff) -> tuple[ProfileChangeHighlight, ...]:
    """FR-504-AC7 「강조」: 재실행 결과에서 항목별 변화 크기를 강조 표시한다."""
    highlights: list[ProfileChangeHighlight] = []
    for change in diff.changes:
        before_value = change.before.value if change.before is not None else None
        after_value = change.after.value if change.after is not None else None
        relative_change = _relative_change(before_value, after_value)
        highlights.append(
            ProfileChangeHighlight(change.key, change.kind, before_value, after_value,
                                   relative_change)
        )
    return tuple(highlights)


def _relative_change(before_value: Any, after_value: Any) -> float | None:
    if (
        isinstance(before_value, (int, float)) and not isinstance(before_value, bool)
        and isinstance(after_value, (int, float)) and not isinstance(after_value, bool)
        and before_value != 0
    ):
        return (after_value - before_value) / before_value
    return None


@dataclass(frozen=True)
class ProfileCaseVariable:
    """FR-504-AC8: 케이스 그리드가 프로파일을 탐색 변수로 다루기 위한 축.

    `profile_variants()`는 (이름, 버전) 식별자만 낸다. 케이스 그리드 변수로
    쓰려면 축 이름(name)이 더 필요하다 — 이름 없이는 여러 프로파일 축을
    구분할 수 없다.
    """

    name: str
    values: tuple[tuple[str, str], ...]


def profile_case_variable(
    name: str, profiles: tuple[RegulationProfile, ...]
) -> ProfileCaseVariable:
    return ProfileCaseVariable(name=name, values=profile_variants(profiles))


@dataclass(frozen=True)
class VerifiedRegulationItem(RegulationItem):
    """FR-504-AC6: 근거 고시·조문(source)에 더해 최종확인일을 갖는 항목.

    `RegulationItem.source`가 이미 "근거 조문·고시" 필드다(근거 표기 기준).
    남는 것은 최종확인일(verified_at)뿐이므로 계약(`core/contracts/`)을
    고치지 않고 이 모듈 안에서 하위 클래스로 확장한다.
    """

    verified_at: date | None = None


def require_traceable(item: RegulationItem) -> VerifiedRegulationItem:
    """근거 출처와 최종확인일이 모두 있는지 검증한다. 없으면 `ValueError`."""
    if not item.source:
        raise ValueError(f"제도 항목 {item.key!r} 에 근거 출처가 없습니다")
    if not isinstance(item, VerifiedRegulationItem) or item.verified_at is None:
        raise ValueError(f"제도 항목 {item.key!r} 에 최종확인일이 없습니다")
    return item
