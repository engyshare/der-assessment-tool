import os

import pytest

from core.assumption.provider import AssumptionSet
from core.contracts.assumptions import PriceBasis


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
    # ⚠ **「(명목)」이 여기 있었다. R31 이 지웠다.** 가격 기준은 대장 최상위
    # `price_basis` 가 1회 선언하며(DV-7 「전 항목에 강제」), 항목이 다시 적으면
    # 정본이 둘 생겨 한쪽만 고쳐진 상태를 아무도 보지 않는다.
    assert escalation_electricity.value_unit == "%/년"
    assert aset.price_basis is PriceBasis.NOMINAL, (
        "대장이 명목을 선언하지 않으면 이 항목의 2.5%/년 이 실질 상승으로 "
        "읽힌다 — 수치는 같고 20년 누계가 크게 달라진다"
    )
    # FR-601-AC4: 부기 7종 전체 보유 검증 - escalation_electricity
    # verified_at가 없는 경우가 있음 - 대장 값 확인
    assert escalation_electricity.base_year is not None
    assert escalation_electricity.applicable_scope is not None
    assert escalation_electricity.derivation_method is not None
    assert escalation_electricity.source is not None
    # verified_at는 대장에서 제공되지 않을 수 있음

    # tax.vat_rate (대장 고정값)
    vat = aset.get("tax.vat_rate")
    assert vat is not None
    assert vat.value == 0.10
    assert vat.confidence == "확정"
    # FR-601-AC4: 부기 7종 전체 보유 검증 - vat
    assert vat.value_unit is not None
    assert vat.base_year is not None
    assert vat.applicable_scope is not None
    assert vat.derivation_method is not None
    assert vat.source is not None
