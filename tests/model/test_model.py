import pytest

from core.contracts.assumptions import AssumptionProvider, AssumptionValue
from core.der.pv import PV
from core.model.model import Model
from core.model.schemas import DERConfig, LoadConfig, ModelConfig


class _Assumptions(AssumptionProvider):
    @property
    def set_name(self) -> str:
        return "test"

    @property
    def set_version(self) -> str:
        return "1.0"

    def get(self, key: str) -> AssumptionValue | None:
        if key == "tax.vat_rate":
            return AssumptionValue(
                key=key,
                value=0.1,
                value_unit="소수",
                base_year="2026",
                applicable_scope="",
                derivation_method="가정",
                source="",
                verified_at=None,
                confidence="가정",
            )
        return None


@pytest.mark.req("FR-201-AC2")
def test_model_json_roundtrip() -> None:
    """모델 정의 JSON 왕복 테스트 — export -> import -> 동일 구성."""
    provider = _Assumptions()
    config = ModelConfig(
        name="테스트 모델",
        resources=[
            DERConfig(
                tag="PV",
                params={"name": "PV1", "capacity_kw": 100.0, "capacity_factor": 0.15},
            )
        ],
        common_load=LoadConfig(annual_kwh=3600.0),
    )

    model = Model(config, provider)

    json_str = model.to_json()
    model2 = Model.from_json(json_str, provider)

    assert model2.name == "테스트 모델"
    assert len(model2.resources) == 1
    assert model2.resources[0].name == "PV1"
    # 정책 파라미터가 모델 계층에서 생성 시 주입되었음을 확인
    assert model2.resources[0].vat_rate == 0.1


@pytest.mark.req("FR-201-AC1")
def test_uninjected_instance_caught() -> None:
    """심어 둔 미주입 인스턴스가 실제로 걸리는지 확인한다 (7.2 DoD).

    주입 없이 만들어진 인스턴스가 조용히 통과하지 않게 모델 계층에서 막는다.
    """
    provider = _Assumptions()

    # 1. 수동으로 생성하고 vat_rate=0.0(기본값)을 그대로 두었다 (미주입 상태)
    pv = PV(name="Uninjected", capacity_kw=10.0, capacity_factor=0.15)

    # 0.0 != 0.1 이므로 걸려야 한다
    with pytest.raises(ValueError, match="정책 파라미터가 주입되지 않았습니다"):
        Model.validate_injection([pv], provider)

    # 2. 올바르게 주입된 경우
    pv_injected = PV(name="Injected", capacity_kw=10.0, capacity_factor=0.15, vat_rate=0.1)
    Model.validate_injection([pv_injected], provider)  # 통과해야 함
