"""모델 구성 계층 (WP-16 / FR-201)

자원 인스턴스 집합 + 부하 + 계약구조 + 제도조건의 조합을 구성한다.
자원 인스턴스 생성 시 정책 파라미터(vat_rate 등) 주입을 강제한다.
"""

from __future__ import annotations

from collections.abc import Sequence

import core.der
from core.contracts.assumptions import AssumptionProvider
from core.contracts.der import DER
from core.contracts.registry import discover
from core.model.schemas import DERConfig, ModelConfig


class Model:
    """모델 구성 (FR-201-AC1)"""

    def __init__(self, config: ModelConfig, provider: AssumptionProvider) -> None:
        self.config = config
        self.name = config.name

        self.resources = self._build_resources(config.resources, provider)

    def _build_resources(
        self, der_configs: list[DERConfig], provider: AssumptionProvider
    ) -> list[DER]:
        """설정을 기반으로 자원 인스턴스를 생성하며 정책 파라미터를 주입한다."""
        registry = discover(core.der, DER)  # type: ignore[type-abstract]
        built: list[DER] = []

        # 모델 계층에서 주입해야 할 정책 파라미터
        expected_vat_rate = provider.require_float("tax.vat_rate")

        for r_config in der_configs:
            if r_config.tag not in registry:
                raise ValueError(f"알 수 없는 자원 태그입니다: {r_config.tag}")
            cls = registry[r_config.tag]

            kwargs = r_config.params.copy()
            # 정책 파라미터 강제 주입
            kwargs["vat_rate"] = expected_vat_rate

            instance = cls(**kwargs)
            built.append(instance)

        return built

    def to_json(self) -> str:
        """모델 구성을 JSON으로 직렬화 (FR-201-AC2)"""
        return self.config.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, json_str: str, provider: AssumptionProvider) -> Model:
        """JSON으로부터 모델 구성을 역직렬화 (FR-201-AC2)"""
        config = ModelConfig.model_validate_json(json_str)
        return cls(config, provider)

    @staticmethod
    def validate_injection(instances: Sequence[DER], provider: AssumptionProvider) -> None:
        """심어 둔 미주입 인스턴스가 실제로 걸리는지 확인하기 위한 검증 함수.

        주입 없이 생성된 인스턴스가 조용히 통과하는 것을 막는다.
        """
        expected_vat_rate = provider.require_float("tax.vat_rate")
        for res in instances:
            if hasattr(res, "vat_rate"):
                actual = res.vat_rate
                if actual != expected_vat_rate:
                    raise ValueError(
                        f"자원 {res.name}에 정책 파라미터가 주입되지 않았습니다 "
                        f"(vat_rate: {actual}, 기대값: {expected_vat_rate}). "
                        "주입 없이 만들어진 인스턴스는 통과할 수 없습니다."
                    )
