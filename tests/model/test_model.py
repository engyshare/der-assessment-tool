import pytest

from core.contracts.assumptions import (
    AssumptionProvider,
    AssumptionValue,
    PriceBasis,
)
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

    @property
    def price_basis(self) -> PriceBasis:
        """DV-7 — 스텁도 기준을 **선언해야** 한다. 그것이 강제의 실질이다."""
        return PriceBasis.NOMINAL

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


# ✔ **R23 에 `FR-201-AC1` 마커를 여기서 뗐다 — R20 이 적어 둔 닫는 조건대로다.**
# 그 조항은 *「**GUI** 에서 자원을 추가·삭제·복제하되 엔진 코드는 바뀌지 않는다」*
# 이고 아래 검사는 **정책 파라미터 미주입 방어**를 본다 — 겹치지 않는다. R20 은
# 「GUI 자체가 없어 대체 검증을 만들 수 없으니 무관한 채로 유지한다」고 판정하고
# **닫는 조건**으로 *「GUI 를 구현하고 그것을 보는 테스트로 마커를 옮긴 뒤 여기서
# 지운다」* 를 적었다. R23 이 그 GUI 를 놓았으므로 마커는 이제 세 층에 있다:
#
#   core   tests/model/test_composition.py            편집 연산 + 엔진 무변경
#   app    tests/app/test_model_composition_router.py GUI 가 도달하는 경로
#   web    tests/web/test_model_composer_view.py      화면의 세 조작
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
