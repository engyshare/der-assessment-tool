from datetime import date

import pytest

from core.assumption.catalog import TechCatalogItem
from core.assumption.item import ConfidenceLevel


@pytest.mark.req("FR-603-AC1", "FR-603-AC2", "FR-603-AC3")
def test_tech_catalog_item() -> None:
    """기술 카탈로그 — 부기 7종 + usage_terms 보유 및 물가조정(escalation).

    오라클: 순위 1 (해석해) — escalation 은 닫힌 형태 산식으로 손계산 가능.
        1,600,000 × (1 + 0.02)^2 = 1,600,000 × 1.0404 = 1,664,640.
    속성·필수 필드 부분은 순위 4 (정의 항등식).
    """
    item = TechCatalogItem(
        resource_type="PV",
        specification="주택용 3~10kW급 옥상 고정형",
        value=1600000,
        value_unit="원/kW",
        base_year="2026",
        applicable_scope="test",
        derivation_method="test",
        source="test source",
        verified_at=date(2026, 8, 8),
        confidence=ConfidenceLevel.ASSUMED,
        usage_terms="test license terms",
    )

    # 부기 7종 보유
    assert item.value_unit == "원/kW"
    assert item.base_year == "2026"
    assert item.applicable_scope == "test"
    assert item.derivation_method == "test"
    assert item.source == "test source"
    assert item.verified_at == date(2026, 8, 8)
    assert item.confidence == ConfidenceLevel.ASSUMED
    # SC-7 이용조건
    assert item.usage_terms == "test license terms"

    # 카탈로그 고유 필드
    assert item.resource_type == "PV"
    assert item.specification == "주택용 3~10kW급 옥상 고정형"

    # 물가조정 (해석해 순위 1)
    escalated = item.escalate(target_year=2028, inflation_rate=0.02)
    assert escalated == 1664640
