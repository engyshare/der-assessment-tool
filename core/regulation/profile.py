"""Data-backed regulation profile implementation for WP-3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from core.contracts.regulation import RegulationItem, RegulationProfile


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


@dataclass(frozen=True)
class RegulationProfileDraft:
    name: str
    version: str
    entries: tuple[RegulationItem, ...]

    @classmethod
    def from_profile(cls, profile: DataRegulationProfile,
                     *, version: str) -> RegulationProfileDraft:
        return cls(name=profile.name, version=version, entries=profile.entries)

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
