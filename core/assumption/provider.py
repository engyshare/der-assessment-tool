import os
from collections.abc import Mapping
from datetime import date
from types import MappingProxyType
from typing import Any

import yaml  # type: ignore

from core.assumption.item import AssumptionItem, ConfidenceLevel
from core.contracts.assumptions import AssumptionProvider, AssumptionValue


class AssumptionSet(AssumptionProvider):
    def __init__(
        self,
        name: str,
        version: str,
        items: Mapping[str, AssumptionItem],
        overrides: Mapping[str, Any] | None = None,
    ):
        self._name = name
        self._version = version
        self._items = items
        self._overrides = overrides or {}

    @classmethod
    def load_from_yaml(cls, filepath: str) -> "AssumptionSet":
        with open(filepath, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        version = str(data.get("version", "unknown"))
        name = os.path.basename(filepath)
        items = {}

        for item_data in data.get("assumptions", []):
            if item_data.get("track") == "blocked":
                continue # Skip items that have no value yet

            conf_str = item_data.get("confidence", "가정")
            try:
                conf = ConfidenceLevel(conf_str)
            except ValueError:
                conf = ConfidenceLevel.ASSUMED

            v_date = item_data.get("verified_at")
            if isinstance(v_date, str):
                v_date = date.fromisoformat(v_date)

            items[item_data["key"]] = AssumptionItem(
                key=item_data["key"],
                value=item_data["value"],
                value_unit=item_data.get("value_unit", ""),
                base_year=str(item_data.get("base_year", "")),
                applicable_scope=item_data.get("applicable_scope", ""),
                derivation_method=item_data.get("derivation_method", ""),
                source=item_data.get("source"),
                verified_at=v_date,
                confidence=conf,
                usage_terms=item_data.get("usage_terms"),
            )

        return cls(name=name, version=version, items=items)

    @property
    def set_name(self) -> str:
        return self._name

    @property
    def set_version(self) -> str:
        return self._version

    def get(self, key: str) -> AssumptionValue | None:
        if key not in self._items:
            return None

        item = self._items[key]
        val = self._overrides.get(key, item.value)

        return AssumptionValue(
            key=item.key,
            value=val,
            value_unit=item.value_unit,
            base_year=item.base_year,
            applicable_scope=item.applicable_scope,
            derivation_method=item.derivation_method,
            source=item.source or "",
            verified_at=item.verified_at,
            confidence=item.confidence.value,
            usage_terms=item.usage_terms,
            set_name=self._name,
            set_version=self._version,
        )

    def diff(self, other: "AssumptionSet") -> dict[str, Any]:
        """두 버전 간의 차이를 반환한다."""
        new_keys = set(self._items.keys()) - set(other._items.keys())
        old_keys = set(other._items.keys()) - set(self._items.keys())

        changed_keys = set()
        changes = {}
        for k in set(self._items.keys()) & set(other._items.keys()):
            if self._items[k].value != other._items[k].value:
                changed_keys.add(k)
                changes[k] = {
                    "old": other._items[k].value,
                    "new": self._items[k].value,
                }

        return {
            "new_keys": new_keys,
            "old_keys": old_keys,
            "changed_keys": changed_keys,
            "changes": changes,
        }

    def override(self, overrides: Mapping[str, Any]) -> "AssumptionSet":
        """현재 셋을 복제하되, 오버라이드를 추가/덮어쓴다."""
        new_overrides = dict(self._overrides)
        new_overrides.update(overrides)

        return AssumptionSet(
            name=self._name,
            version=self._version,
            items=self._items,
            overrides=new_overrides
        )

    def get_overrides(self) -> Mapping[str, Any]:
        """적용된 오버라이드 내역 반환."""
        return self._overrides

    def items(self) -> Mapping[str, AssumptionItem]:
        """항목 전체를 읽기 전용으로 내놓는다.

        가변 dict 를 그대로 내주면 밖에서 대장을 고칠 수 있고, 그것은
        NFR-205 가 막으려는 전역 가변 상태와 같은 결과가 된다.
        """
        return MappingProxyType(dict(self._items))
