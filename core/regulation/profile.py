"""Data-backed regulation profile implementation for WP-3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

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
