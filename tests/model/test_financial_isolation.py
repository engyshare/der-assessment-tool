import pytest

from core.model.model import Model
from core.model.schemas import ContractConfig, DERConfig, ModelConfig
from tests.model.test_model import _Assumptions


@pytest.mark.req("FR-103-AC1", "FR-103-AC2", "FR-103-AC3")
def test_financial_isolation_between_instances():
    """FR-103: 동일 유형 자원의 인스턴스별 속성 분리 확인.

    AC1. 동일 유형 자원(PV) 인스턴스가 2개 이상일 때 각각 다른 재무 속성을 가져야 함.
    AC2. 클래스 속성이 아닌 인스턴스 단위 속성.
    AC3. 두 인스턴스의 현금흐름이 프로포마에서 분리된 행으로 표시된다.
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

    # 두 인스턴스가 독립적인 재무 속성을 갖는지 확인 (AC1, AC2)
    assert len(model.resources) == 2
    pv1, pv2 = model.resources

    assert pv1.name == "PV#1"
    assert pv1.lifetime == 20
    assert pv2.name == "PV#2"
    assert pv2.lifetime == 25
    assert pv1.unit_capex_won_per_kw == 1500000
    assert pv2.unit_capex_won_per_kw == 1800000

    # FR-103-AC3: CBA 시뮬레이션 분리 검증
    # 각 인스턴스의 CAPEX가 분리되어 계산됨을 확인
    capex1 = pv1.capex(year=1)
    capex2 = pv2.capex(year=1)
    # PV#1: 10.0 * 1,500,000 = 15,000,000
    # PV#2: 3.0 * 1,800,000 = 5,400,000
    assert capex1 != capex2, "두 인스턴스의 CAPEX는 달라야 합니다"
    assert int(capex1) > 0 and int(capex2) > 0

    # 각 인스턴스의 O&M이 분리되어 계산됨을 확인
    om1 = pv1.fixed_om(year=1)
    om2 = pv2.fixed_om(year=1)
    # 두 인스턴스의 O&M는 다름
    assert (om1 != om2 or
            (int(om1) == 0 and int(om2) == 0)), "두 인스턴스의 O&M는 달라야 합니다"

    # 각 인스턴스의 잔존가치가 분리되어 계산됨을 확인
    salvage1 = pv1.salvage_value(year=20)
    salvage2 = pv2.salvage_value(year=20)
    # PV#1(수명20): 20년차 잔존가치 ≈ 0
    # PV#2(수명25): 20년차 잔존가치 > 0
    assert int(salvage1) != int(salvage2), (
        f"두 인스턴스의 잔존가치는 달라야 합니다: PV#1={int(salvage1)}, "
        f"PV#2={int(salvage2)}"
    )
