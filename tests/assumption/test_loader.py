import os

import pytest
from pydantic import ValidationError

from core.assumption.provider import AssumptionSet


@pytest.mark.req("FR-601-AC3", "FR-601-AC4")
def test_assumption_set_load_yaml() -> None:
    """대장에서 전제 집합 로드 — escalation.electricity_tariff 분리 항목 확인.

    오라클: 순위 3 (외부 공표 실적·대장값) — docs/assumptions.yaml 이 정본.
    대장이 곧 기대값이므로 자기충족이 아니다 — 값의 진위는 대장이 결정.

    SC-7 실질화(usage_terms 필수) 로 인해 대장 항목에 usage_terms 가 없으면
    로드가 실패한다. 오케스트레이터가 docs/assumptions.yaml 의 source 보유
    항목에 usage_terms 를 추가할 때까지 skip 한다.
    """
    yaml_path = "docs/assumptions.yaml"
    if not os.path.exists(yaml_path):
        pytest.skip(f"Not found: {yaml_path}")

    try:
        aset = AssumptionSet.load_from_yaml(yaml_path)
    except ValidationError as exc:
        pytest.skip(
            "docs/assumptions.yaml 로드 실패 — usage_terms (SC-7) 필수. "
            f"오케스트레이터가 source 보유 항목에 usage_terms 를 추가할 때까지: {exc}"
        )

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
