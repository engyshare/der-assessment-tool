import pytest

from core.model.model import Model
from core.model.schemas import ContractConfig, DERConfig, ModelConfig
from tests.model.test_model import _Assumptions


@pytest.mark.req("FR-103")
def test_financial_isolation_between_instances():
    """FR-103: 동일 유형 자원의 인스턴스별 속성 분리 확인.

    AC1. 동일 유형 자원(PV) 인스턴스가 2개 이상일 때 각각 다른 재무 속성을 가져야 함.
    AC2. 클래스 속성이 아닌 인스턴스 단위 속성.
    AC3. 수명, Capex, Opex 등의 입력값을 받아야 함.
    """
    provider = _Assumptions()

    # PV#1(햇빛소득마을 조건), PV#2(자가용 조건)을 동시에 생성
    pv1_config = DERConfig(
        tag="PV",
        params={
            "name": "PV#1",
            "capacity_kw": 10.0,
            "unit_capex_won_per_kw": 1500000,
            "lifetime": 20,
            "capacity_factor": 0.15,
        },
    )
    pv2_config = DERConfig(
        tag="PV",
        params={
            "name": "PV#2",
            "capacity_kw": 3.0,
            "unit_capex_won_per_kw": 1800000,
            "lifetime": 25,
            "capacity_factor": 0.15,
        },
    )

    config = ModelConfig(
        name="테스트 모델",
        resources=[pv1_config, pv2_config],
        contract=ContractConfig(structure="개별 직접계약"),
    )

    model = Model(config, provider)

    # 두 인스턴스가 독립적으로 재무 속성을 갖는지 확인
    assert len(model.resources) == 2
    pv1, pv2 = model.resources

    assert pv1.name == "PV#1"
    assert pv1.lifetime == 20
    assert pv2.name == "PV#2"
    assert pv2.lifetime == 25
    assert pv1.unit_capex_won_per_kw == 1500000
    assert pv2.unit_capex_won_per_kw == 1800000
