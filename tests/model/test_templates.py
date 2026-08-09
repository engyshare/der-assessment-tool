import pytest

from core.contracts.assumptions import AssumptionProvider, AssumptionValue
from core.model.templates import create_energy_independent_house


class _MockAssumptions(AssumptionProvider):
    @property
    def set_name(self) -> str:
        return "Mock"

    @property
    def set_version(self) -> str:
        return "v1"

    def get(self, key: str) -> AssumptionValue | None:
        values = {
            "capex.pv.rooftop": 1600000,
            "capex.ess.second_life": 300000,
            "capex.ev_charger.v2g": 10000000,
            "capex.heatpump": 1000000,
            "capex.modular_house.premium": 15,
        }
        if key in values:
            return AssumptionValue(
                key=key,
                value=values[key],
                value_unit="",
                base_year="",
                applicable_scope="",
                derivation_method="mock",
                source="",
                verified_at=None,
                confidence="가정",
            )
        return None


@pytest.mark.req("FR-204")
def test_energy_independent_house_template():
    """FR-204-AC1, AC2, AC3: 에너지자립가구 2변형 템플릿 검증."""
    provider = _MockAssumptions()

    # 기존주택형
    legacy_model = create_energy_independent_house(provider, is_modular=False)
    assert legacy_model.name == "에너지자립가구 (기존주택형)"
    assert len(legacy_model.resources) == 4
    tags = {r.tag for r in legacy_model.resources}
    assert tags == {"PV", "ESS", "EV_V2G", "HeatPump"}

    # 템플릿의 자원 설정값이 Assumptions 에서 왔는지 확인 (FR-204-AC3)
    pv_conf = next(r for r in legacy_model.resources if r.tag == "PV")
    assert pv_conf.params["unit_capex_won_per_kw"] == 1600000

    # 모듈러형
    modular_model = create_energy_independent_house(provider, is_modular=True)
    assert modular_model.name == "에너지자립가구 (모듈러형)"

    # 프리미엄 15% 적용 확인
    pv_conf_mod = next(r for r in modular_model.resources if r.tag == "PV")
    assert pv_conf_mod.params["unit_capex_won_per_kw"] == 1600000 * 1.15
