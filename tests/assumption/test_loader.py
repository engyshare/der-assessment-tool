import os

import pytest

from core.assumption.provider import AssumptionSet


@pytest.mark.req("FR-601-AC3", "FR-601-AC4")
def test_assumption_set_load_yaml() -> None:
    """대장에서 전제 집합 로드 — escalation.electricity_tariff 및 usage_terms 검증.

    오라클: 순위 3 (외부 공표 실적·대장값) — docs/assumptions.yaml 이 정본.
    대장이 곧 기대값이므로 자기충족이 아니다 — 값의 진위는 대장이 결정.
    """
    yaml_path = "docs/assumptions.yaml"
    assert os.path.exists(yaml_path), f"전제 대장 파일이 존재해야 합니다: {yaml_path}"

    aset = AssumptionSet.load_from_yaml(yaml_path)

    assert aset.set_name == "assumptions.yaml"
    assert len(aset.set_version) > 0

    # 4.8 전기요금 인상률을 물가상승률과 별도 항목으로 분리 (FR-601-AC3)
    escalation_electricity = aset.get("escalation.electricity_tariff")
    assert escalation_electricity is not None
    assert escalation_electricity.value_unit == "%/년 (명목)"

    # tax.vat_rate (대장 고정값)
    vat = aset.get("tax.vat_rate")
    assert vat is not None
    assert vat.value == 0.10
    assert vat.confidence == "확정"
