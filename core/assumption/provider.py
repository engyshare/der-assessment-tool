import os
from collections.abc import Mapping
from datetime import date
from types import MappingProxyType
from typing import Any

import yaml  # type: ignore

from core.assumption.item import AssumptionItem, ConfidenceLevel
from core.contracts.assumptions import (
    AssumptionProvider,
    AssumptionValue,
    PriceBasis,
    assert_basis_is_declared_once,
)
from core.contracts.validation import ValidationError


class AssumptionSet(AssumptionProvider):
    """전제 대장 1판.

    **`price_basis` 는 위치인자 뒤에 오지만 기본값이 없다** (`DV-7`). 기본값을
    주면 아무도 선언하지 않은 상태가 유효한 상태가 되고, 그때 실질과 명목이
    같은 수치로 섞여 들어간다 — 수치는 같고 뜻이 정반대에 가깝다.
    """

    def __init__(
        self,
        name: str,
        version: str,
        items: Mapping[str, AssumptionItem],
        overrides: Mapping[str, Any] | None = None,
        reasons: Mapping[str, str] | None = None,
        *,
        price_basis: PriceBasis,
    ):
        self._name = name
        self._version = version
        self._items = items
        self._overrides = overrides or {}
        #: 오버라이드 사유 — 권장 필드 (FR-602-AC3). 값이 없어도 된다.
        self._reasons = reasons or {}
        self._price_basis = price_basis
        # ★ **「전 항목에 강제」를 여기서 강제한다** (DV-7). 집합이 서는 순간
        # 보아야 한다 — 나중에 보면 그 사이에 이미 계산이 돌 수 있고, 그때는
        # 어느 기준으로 계산했는지 결과만 보고는 알 수 없다.
        assert_basis_is_declared_once(
            price_basis=price_basis,
            items=[(key, item.value_unit) for key, item in items.items()],
        )

    @classmethod
    def load_from_yaml(cls, filepath: str) -> "AssumptionSet":
        with open(filepath, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        version = str(data.get("version", "unknown"))
        name = os.path.basename(filepath)
        # ★ **대장이 기준을 선언하지 않으면 멈춘다** (DV-7). 기본값으로 메우면
        # 「선언하지 않았다」가 「명목이라고 선언했다」와 구별되지 않는다 —
        # `MissingAssumption` 이 값에 대해 하는 것과 같은 판단이다.
        declared = data.get("price_basis")
        if declared is None:
            raise ValidationError(
                field="assumption_set.price_basis",
                reason=(
                    f"대장 {name} 에 최상위 `price_basis` 선언이 없습니다. "
                    "DV-7 은 실질/명목 구분을 AssumptionSet 수준에서 1회 "
                    "선언하라고 요구합니다"
                ),
                action=(
                    "대장 최상위에 `price_basis: 명목` 또는 `price_basis: 실질` 을 "
                    "적으십시오 — 기본값을 두지 않는 이유는 선언하지 않은 상태와 "
                    "명목이라고 선언한 상태를 구별해야 하기 때문입니다"
                ),
                rule="DV-7",
            )
        try:
            price_basis = PriceBasis(str(declared))
        except ValueError:
            raise ValidationError(
                field="assumption_set.price_basis",
                reason=f"알 수 없는 가격 기준입니다: {declared!r}",
                action="`실질` 또는 `명목` 중 하나로 적으십시오",
                rule="DV-7",
            ) from None
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

        return cls(
            name=name, version=version, items=items, price_basis=price_basis
        )

    @property
    def set_name(self) -> str:
        return self._name

    @property
    def set_version(self) -> str:
        return self._version

    @property
    def price_basis(self) -> PriceBasis:
        """집합이 1회 선언한 가격 기준 (`DV-7`)."""
        return self._price_basis

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

    def override(
        self,
        overrides: Mapping[str, Any],
        reasons: Mapping[str, str] | None = None,
    ) -> "AssumptionSet":
        """현재 셋을 복제하되, 오버라이드를 추가/덮어쓴다.

        ``reasons`` 는 **권장 필드**다 (FR-602-AC3) — 키별 오버라이드 사유를
        선택적으로 함께 남긴다. 사유를 넣지 않아도 오버라이드는 그대로
        성립한다. 필수로 만들면 조항("권장")을 넘어서고 기존 호출부(사유
        없이 ``override()`` 를 쓰던 자리)를 깨뜨린다.
        """
        new_overrides = dict(self._overrides)
        new_overrides.update(overrides)

        new_reasons = dict(self._reasons)
        if reasons:
            new_reasons.update(reasons)

        return AssumptionSet(
            name=self._name,
            version=self._version,
            items=self._items,
            overrides=new_overrides,
            reasons=new_reasons,
            # ★ **오버라이드는 가격 기준을 바꾸지 않는다.** 기준은 규약이고
            # 오버라이드는 값이다 — 시나리오가 기준을 바꿀 수 있으면 두 시나리오의
            # 금액이 서로 다른 뜻을 갖게 되고, FR-202(같은 전제 위 비교)가 깨진다.
            price_basis=self._price_basis,
        )

    def get_overrides(self) -> Mapping[str, Any]:
        """적용된 오버라이드 내역 반환."""
        return self._overrides

    def get_override_reasons(self) -> Mapping[str, str]:
        """오버라이드별 사유 (FR-602-AC3). 사유를 넣지 않은 키는 없다."""
        return MappingProxyType(dict(self._reasons))

    def overridden_items(self) -> Mapping[str, dict[str, Any]]:
        """기준 전제 대비 변경 항목 목록 (FR-602-AC2).

        리포트가 "무엇을 바꿨는지" 를 표시하려면 오버라이드 값만으로는
        부족하다 — **바뀌기 전 값**과 나란히 있어야 "변경"이 성립한다.
        ``get_overrides()`` 는 새 값만 주므로, 이 메서드가 대장의 원래
        값을 함께 붙여 리포트가 그대로 표에 얹을 수 있게 한다.
        """
        return MappingProxyType({
            key: {
                "base": self._items[key].value,
                "override": override_value,
                "reason": self._reasons.get(key),
            }
            for key, override_value in self._overrides.items()
            if key in self._items
        })

    def items(self) -> Mapping[str, AssumptionItem]:
        """항목 전체를 읽기 전용으로 내놓는다.

        가변 dict 를 그대로 내주면 밖에서 대장을 고칠 수 있고, 그것은
        NFR-205 가 막으려는 전역 가변 상태와 같은 결과가 된다.
        """
        return MappingProxyType(dict(self._items))
