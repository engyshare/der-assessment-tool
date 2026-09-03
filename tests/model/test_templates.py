import pytest

from core.contracts.assumptions import (
    AssumptionProvider,
    AssumptionValue,
    PriceBasis,
)
from core.model.templates import create_energy_independent_house


class _MockAssumptions(AssumptionProvider):
    @property
    def set_name(self) -> str:
        return "Mock"

    @property
    def set_version(self) -> str:
        return "v1"

    @property
    def price_basis(self) -> PriceBasis:
        """DV-7 — 스텁도 기준을 **선언해야** 한다. 그것이 강제의 실질이다."""
        return PriceBasis.NOMINAL

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


@pytest.mark.req("FR-204-AC1", "FR-204-AC3")
def test_energy_independent_house_template():
    """FR-204-AC1, AC3: 에너지자립가구 2변형 템플릿 검증.

    ⚠⚠ **`FR-204-AC2` 마커를 뗐다 (R59/WP-7).** 그 조항은
    *「마을단위 분산특구 6개 모델, 아파트 마이크로그리드 모델 **[Phase 2]**」*
    이고, 이 시험은 **에너지자립가구 2변형**(= `AC1` 문면)과 파라미터 출처
    (`AC3`)만 잰다 — **`AC2` 를 재는 단언이 한 줄도 없다.**

    ★ **떼면 `AC2` 가 미매핑이 되는데 그것이 옳다.** `AC2` 는 Phase 2 이고
    구현이 없다. `tests/acceptance2/test_17_9_dod9.py` 는 **Phase 1** Must-have
    미매핑만 0 을 요구하므로 이 항목은 그 게이트에 걸리지 않는다 — 종전
    미매핑 9건도 전부 Phase 2/3 이다.
    ⚠ **미매핑을 0 으로 만들려고 다른 것을 재는 시험에 마커를 얹지 않는다** —
    R59 가 내내 고친 결함이 그 형태다(판정 전문은
    `docs/decisions-2026-09-04-R59.md` §5).
    """
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
