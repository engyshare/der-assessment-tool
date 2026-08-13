"""GUI 자원 구성 편집의 앱 계층 — FR-201-AC1.

편집 **연산**은 `core/model/composition.py` (WP-16 소유)에 있고 여기 있는 것은
**보관과 상태 반영**뿐이다. 연산을 여기로 옮기면 조항 소유 구획 밖에 판정이
생기고, GUI 를 거치지 않는 경로(JSON import 등)가 다른 규칙을 갖게 된다.

**편집 결과를 즉시 보관하는 것이 조항의 「구성 가능」이다.** 돌려주기만 하고
보관하지 않으면 GUI 는 매 요청마다 편집 전 구성을 다시 보게 되고, 사용자
입장에서는 편집이 일어나지 않은 것과 같다.
"""
from __future__ import annotations

from typing import Any

from core.model.composition import (
    add_resource,
    available_resource_tags,
    duplicate_resource,
    remove_resource,
    resource_names,
)
from core.model.schemas import ModelConfig


class ModelCompositionService:
    """모델 구성 보관 + 자원 추가·삭제·복제 (FR-201-AC1)."""

    def __init__(self) -> None:
        self._models: dict[str, ModelConfig] = {}

    def register(self, config: ModelConfig) -> ModelConfig:
        """구성을 보관한다 — GUI 가 편집할 대상이 된다."""
        self._models[config.name] = config
        return config

    def get(self, model_name: str) -> ModelConfig | None:
        return self._models.get(model_name)

    def resource_names(self, model_name: str) -> tuple[str, ...]:
        return resource_names(self._require(model_name))

    def available_tags(self) -> tuple[str, ...]:
        """추가할 수 있는 자원 종류 — 레지스트리가 정본이다 (NFR-207-AC1)."""
        return available_resource_tags()

    def add(self, model_name: str, *, tag: str, params: dict[str, Any]) -> ModelConfig:
        edited = add_resource(self._require(model_name), tag=tag, params=params)
        return self.register(edited)

    def remove(self, model_name: str, name: str) -> ModelConfig:
        edited = remove_resource(self._require(model_name), name)
        return self.register(edited)

    def duplicate(self, model_name: str, name: str, *, new_name: str) -> ModelConfig:
        edited = duplicate_resource(self._require(model_name), name, new_name=new_name)
        return self.register(edited)

    def _require(self, model_name: str) -> ModelConfig:
        config = self._models.get(model_name)
        if config is None:
            raise KeyError(f"보관된 모델 구성이 없습니다: {model_name!r}")
        return config
