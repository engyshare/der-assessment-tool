from datetime import date

import pytest
from pydantic import ValidationError

from core.assumption.catalog import (
    CatalogValueResolution,
    EscalationDetail,
    TechCatalogItem,
    resolve_catalog_value,
)
from core.assumption.item import ConfidenceLevel


def _item(**overrides: object) -> TechCatalogItem:
    base: dict[str, object] = dict(
        resource_type="PV",
        specification="주택용 3~10kW급 옥상 고정형",
        value=1600000,
        value_unit="원/kW",
        as_of_date=date(2026, 6, 1),
        base_year="2026",
        version="v1",
        applicable_scope="test",
        condition="옥상 고정형 시공에 한함",
        derivation_method="test",
        sample="업계 견적 3건 평균",
        source="test source",
        verified_at=date(2026, 8, 8),
        confidence=ConfidenceLevel.ASSUMED,
        usage_terms="test license terms",
    )
    base.update(overrides)
    return TechCatalogItem(**base)


@pytest.mark.req("FR-603-AC1")
def test_tech_catalog_item_field_set() -> None:
    """기술 카탈로그 — 부기 7종 + usage_terms + v0.5 추가 4종 보유.

    오라클: 순위 4 (정의 항등식) — pydantic 필드 정의가 곧 검증이다.
    v0.5 정정으로 늘어난 (기준일·버전·조건·표본) 이 v0.4 시절처럼
    누락돼도 통과하지 않는지를, 하나씩 없앤 생성이 거부되는지로 본다.
    """
    item = _item()

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

    # v0.5 정정 4종 — 기준일·버전·조건·표본
    assert item.as_of_date == date(2026, 6, 1)
    assert item.version == "v1"
    assert item.condition == "옥상 고정형 시공에 한함"
    assert item.sample == "업계 견적 3건 평균"

    # 하나라도 빠지면(v0.4 상태로 되돌아가면) 생성 거부 — 필수 필드다
    with pytest.raises(ValidationError):
        _item(version=None)


@pytest.mark.req("FR-603-AC2")
def test_catalog_value_vs_user_override_are_distinguishable() -> None:
    """카탈로그 값과 사용자 변경값을 리포트가 구분할 근거 — ``is_overridden``.

    오라클: 순위 4 (정의 항등식) — ``resolve_catalog_value`` 는 오버라이드
    존재 여부를 그대로 반영하는 순수 판정이다.
    """
    item = _item(value=1600000)

    catalog_only = resolve_catalog_value(item)
    assert isinstance(catalog_only, CatalogValueResolution)
    assert catalog_only.is_overridden is False
    assert catalog_only.effective_value == 1600000
    assert catalog_only.catalog_value == 1600000

    overridden = resolve_catalog_value(item, override=1_800_000)
    assert overridden.is_overridden is True
    assert overridden.effective_value == 1_800_000
    # 카탈로그 원값은 오버라이드 후에도 보존된다 — 그래야 "구분"이 성립한다
    assert overridden.catalog_value == 1600000

    # 일부러 망가뜨려 확인: is_overridden 을 값 비교로 바꾸면(예: 우연히
    # 카탈로그 값과 같은 override) 이 케이스가 놓친다 — override 존재
    # 자체로 판정해야 하는 이유
    same_value_override = resolve_catalog_value(item, override=1600000)
    assert same_value_override.is_overridden is True


@pytest.mark.req("FR-603-AC3")
def test_catalog_escalation_shows_adjustment_detail() -> None:
    """기준연도 ≠ 분석연도 — 물가 조정 후 사용 + 조정 내역 표시.

    오라클: 순위 1 (해석해) — escalation 은 닫힌 형태 산식으로 손계산 가능.
        1,600,000 × (1 + 0.02)^2 = 1,600,000 × 1.0404 = 1,664,640.
    """
    item = _item(value=1600000, base_year="2026")

    # 값만 조정 (기존 경로 유지)
    escalated = item.escalate(target_year=2028, inflation_rate=0.02)
    assert escalated == 1664640

    # 조정 내역 — AC3 후단 "조정 내역을 표시한다"
    detail = item.escalate_with_detail(target_year=2028, inflation_rate=0.02)
    assert isinstance(detail, EscalationDetail)
    assert detail.base_year == 2026
    assert detail.target_year == 2028
    assert detail.diff_years == 2
    assert detail.base_value == 1600000
    assert detail.escalated_value == 1664640
    assert detail.factor == pytest.approx(1.0404)
    assert "2026" in detail.describe()
    assert "2028" in detail.describe()
    assert "1664640" in detail.describe()

    # 기준연도와 분석연도가 같으면 조정하지 않는다 — 그 사실도 내역에 남는다
    no_change = item.escalate_with_detail(target_year=2026, inflation_rate=0.02)
    assert no_change.diff_years == 0
    assert no_change.escalated_value == 1600000
