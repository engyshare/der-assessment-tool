from core.contracts.assumptions import AssumptionProvider
from core.model.schemas import ContractConfig, DERConfig, ModelConfig


def create_energy_independent_house(
    provider: AssumptionProvider, is_modular: bool = False
) -> ModelConfig:
    """에너지자립가구 템플릿 2변형 (기존주택형 / 모듈러형) (FR-204-AC1).

    태양광, ESS, EV V2G, 히트펌프 4종의 자원만 인용한다 (FR-204-AC2).
    자원 설정값은 docs/assumptions.yaml 에 기재된 가정/출처 기반 (FR-204-AC3).
    """
    # 기본 가정 조회
    pv_capex = provider.require_float("capex.pv.rooftop")
    ess_capex = provider.require_float("capex.ess.second_life")
    v2g_capex = provider.require_float("capex.ev_charger.v2g")
    hp_capex = provider.require_float("capex.heatpump")

    if is_modular:
        # 모듈러형 변형: Q-9 모듈러 주택 설치비 증분 15% (FR-204-AC1)
        premium = provider.require_float("capex.modular_house.premium") / 100.0
        pv_capex *= 1 + premium
        ess_capex *= 1 + premium
        v2g_capex *= 1 + premium
        hp_capex *= 1 + premium
        name = "에너지자립가구 (모듈러형)"
    else:
        name = "에너지자립가구 (기존주택형)"

    resources = [
        DERConfig(
            tag="PV",
            params={"name": "주택용 태양광", "capacity_kw": 3.0, "unit_capex_won_per_kw": pv_capex},
        ),
        DERConfig(
            tag="ESS",
            params={
                "name": "사용후배터리 ESS",
                "capacity_kwh": 10.0,
                "power_kw": 3.0,
                "capex_unit_won_per_kwh": ess_capex,
            },
        ),
        DERConfig(
            tag="EV_V2G",
            params={
                "name": "양방향 충전기",
                "vehicle_count": 1,
                "battery_kwh": 60.0,
                "max_charge_kw": 7.0,
                "max_discharge_kw": 7.0,
                "connect_start_hour": 18,
                "connect_end_hour": 8,
                "participation": 1.0,
                "available_dod": 0.5,
                "charger_unit_cost_won": v2g_capex,
            },
        ),
        DERConfig(
            tag="HeatPump",
            params={
                "name": "공기열 히트펌프",
                "rated_heat_kw": 10.0,
                "heat_load_kwh": 1000.0,
                "cop_curve": "MockCopCurve",
                "capex_unit_won_per_kw": hp_capex,
            },
        ),
    ]

    return ModelConfig(name=name, resources=resources, contract=ContractConfig(structure="상계"))
