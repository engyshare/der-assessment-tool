"""실행 경로가 **계약구조를 지나는가** — `FR-205-AC1` / R31.

조립기(`core/valuestream/settlement.py::assemble`)와 그것을 붙드는 테스트는
`tests/valuestream/test_settlement.py` 에 촘촘하다. **그런데 그 테스트가 전부 그
함수를 직접 부른다.** 이 저장소가 R26 재검증에서 형태 하나로 모은 결함이 그것이다
— *「함수 층은 지어져 있는데 실행 경로가 부르지 않는다」*. `DV-12`(R27) ·
`DV-5`(R30) 가 같은 자리에서 같은 형태였고, 이 파일은 그 **셋째**다.

    구조 없이도 종전대로 돈다            ← 배선이 기존 케이스 실행을 막지 않는다
    구조를 주면 그 편익이 계산에 들어간다  ← 조립이 NPV 를 실제로 바꾼다
    ★ 미구현 구조는 **진입점이** 거부한다  ← 편익 0 짜리 결과가 만들어지지 않는다
    ★ 대장 없이 구조를 주면 거부한다      ← 단가를 지어내지 않는다

뒤 둘이 요점이다. 둘째만 두면 *「조립기가 불린다」* 는 알 수 있지만, **미구현
구조가 조용히 편익 0 을 내는 것**과 **단가가 어디선가 지어지는 것**은 여전히
아무도 막지 않는다.
"""

from __future__ import annotations

from datetime import date
from types import MappingProxyType

import pytest

from core.assumption.item import AssumptionItem, ConfidenceLevel
from core.assumption.provider import AssumptionSet
from core.casegrid.e2e_runner import run_single_case_e2e
from core.contracts.assumptions import AssumptionProvider, PriceBasis
from core.contracts.validation import ValidationError
from core.regulation.tariff import (
    MeterPoint,
    ResidentialBlock,
    ResidentialTariffTable,
    TariffCatalog,
    TariffEngine,
)
from core.valuestream.settlement import (
    MANAGER_FEE_KEY,
    NOT_YET_ASSEMBLED,
    TARIFF_KEY,
    TRADE_FEE_KEY,
    SettlementInputs,
)

#: 대장을 읽지 않는다 — 이 파일이 보는 것은 금액이 아니라 **배선**이다.
LEVEL_MAP = {
    "pv_unit_cost": MappingProxyType({"base": 1_600_000.0}),
    "ess_unit_cost": MappingProxyType({"base": 400_000.0}),
    "discount_rate": MappingProxyType({"base": 0.045}),
}

#: 분석기간 탐침값 — 소유자는 `AssumptionSet` 이고(§7.1 O-1) 이 파일의 관심이
#: 아니다. 대장값과 같을 필요가 없으므로 일부러 다른 수를 쓴다.
_PROBE_HORIZON = 18


def _provider() -> AssumptionProvider:
    def item(key: str, value: float) -> AssumptionItem:
        return AssumptionItem(
            key=key, value=value, value_unit="원/kWh", base_year="2026",
            applicable_scope="검사용", derivation_method="검사용",
            source=None, verified_at=None, confidence=ConfidenceLevel.ASSUMED,
        )

    return AssumptionSet(
        name="검사", version="1",
        items={TARIFF_KEY: item(TARIFF_KEY, 150.0), TRADE_FEE_KEY: item(TRADE_FEE_KEY, 5.0)},
        price_basis=PriceBasis.NOMINAL,
    )


#: 「단일계약+관리주체 경유」 — R32 에 조립기가 섰다. 여기서는 **수수료가
#: 프로포마에 닿는가**만 본다(조립 자체는
#: `tests/valuestream/test_settlement_manager_structure.py`).
_MANAGER_STRUCTURE = "단일계약+관리주체 경유"
_ENERGY_KEY = "manager.energy"
_BASIC_KEY = "manager.basic"


def _manager_provider(fee_pct: float = 3.0) -> AssumptionProvider:
    def item(key: str, value: float, unit: str) -> AssumptionItem:
        return AssumptionItem(
            key=key, value=value, value_unit=unit, base_year="2026",
            applicable_scope="검사용", derivation_method="검사용",
            source=None, verified_at=None, confidence=ConfidenceLevel.ASSUMED,
        )

    return AssumptionSet(
        name="검사", version="1",
        items={
            MANAGER_FEE_KEY: item(MANAGER_FEE_KEY, fee_pct, "%"),
            _ENERGY_KEY: item(_ENERGY_KEY, 100.0, "원/kWh"),
            _BASIC_KEY: item(_BASIC_KEY, 1_000.0, "원/월"),
        },
        price_basis=PriceBasis.NOMINAL,
    )


def _manager_engine() -> TariffEngine:
    table = ResidentialTariffTable(
        name="manager-2026",
        valid_from=date(2026, 1, 1),
        valid_to=None,
        blocks=(ResidentialBlock(None, _ENERGY_KEY, _BASIC_KEY),),
    )
    return TariffEngine(
        assumptions=_manager_provider(),
        catalog=TariffCatalog(residential=(table,), tou=(), direct_trade=()),
    )


def _manager_inputs() -> SettlementInputs:
    return SettlementInputs(
        baseline_meters=(MeterPoint.residential("101", 1_000.0),),
        new_meters=(MeterPoint.residential("101", 600.0),),
        billing_date=date(2026, 6, 1),
    )


@pytest.mark.req("FR-205-AC1.NetMetering")
def test_a_case_without_a_structure_still_runs() -> None:
    """양성 — 계약구조 없는 케이스는 종전대로 NPV 를 낸다.

    `ModelConfig.contract` 가 `| None` 이므로 「계약구조 없는 모델」은 정당한
    상태다. 거부만 검사하면 **무엇이든 거부하는** 구현도 통과한다.
    """
    outcome = run_single_case_e2e(
        {}, level_map=LEVEL_MAP, horizon_years=_PROBE_HORIZON
    )

    assert "npv" in outcome.metrics


@pytest.mark.req("FR-205-AC1.NetMetering")
def test_the_structure_changes_the_npv_through_the_entry_point() -> None:
    """★★ **구조가 계산을 바꾼다** — 조립이 검사 전용이 아니다.

    상계거래는 차감단가로 대장의 약관요금 150 원/kWh 를 쓰고, 구조를 주지 않은
    기본 경로는 종전 리터럴 120 원/kWh 를 쓴다. 단가가 다르므로 NPV 가 달라야
    한다.

    ★ **「예외가 안 났다」로는 배선을 확인할 수 없다.** 조립기를 부르고 그 결과를
    버리는 구현도 예외를 내지 않으며, 그 상태에서 위 양성 테스트와 조립기의 단위
    테스트는 **전부 초록불**이다 — R30 이 `horizon_years` 에서 만난 「재는 것과
    쓰는 것이 갈린다」와 같은 형태다.
    """
    plain = run_single_case_e2e(
        {}, level_map=LEVEL_MAP, horizon_years=_PROBE_HORIZON
    )
    net_metered = run_single_case_e2e(
        {},
        level_map=LEVEL_MAP,
        horizon_years=_PROBE_HORIZON,
        structure="상계거래",
        provider=_provider(),
    )

    assert plain.metrics["npv"] != net_metered.metrics["npv"], (
        "계약구조를 주었는데 NPV 가 같습니다 — 조립 결과가 계산에 들어가지 "
        "않고 버려지고 있습니다"
    )


@pytest.mark.req("FR-205-AC1.DistrictDirectTrade")
def test_direct_trade_reaches_the_calculation_with_its_negotiated_inputs() -> None:
    """직접거래도 진입점을 지나며, 계약단가가 결과를 바꾼다.

    구조 하나만 배선해 두면 「그 구조만 되는」 상태가 초록불이 된다. 갈래 A 는
    둘이므로 둘 다 진입점을 지나는 것을 본다.
    """
    cheap = run_single_case_e2e(
        {}, level_map=LEVEL_MAP, horizon_years=_PROBE_HORIZON,
        structure="분산특구 직접거래", provider=_provider(),
        settlement_inputs=SettlementInputs(
            trade_price_won_per_kwh=120.0, trade_volume_kwh=1_000.0
        ),
    )
    dear = run_single_case_e2e(
        {}, level_map=LEVEL_MAP, horizon_years=_PROBE_HORIZON,
        structure="분산특구 직접거래", provider=_provider(),
        settlement_inputs=SettlementInputs(
            trade_price_won_per_kwh=145.0, trade_volume_kwh=1_000.0
        ),
    )

    assert cheap.metrics["npv"] != dear.metrics["npv"], (
        "계약단가를 바꿨는데 NPV 가 같습니다 — `SettlementInputs` 가 조립기에 "
        "닿지 않고 있습니다"
    )


@pytest.mark.req("FR-205-AC1.ManagerEntity")
def test_the_manager_fee_reaches_the_proforma_as_a_cost() -> None:
    """★★ 관리 수수료가 **비용으로 프로포마에 닿는다** (R32 — `Q-14`).

    조립기가 수수료를 `SettlementCost` 로 내는 것과 **그것이 프로포마 행이 되는
    것**은 다른 층이다. 진입점이 `plan.costs` 를 버리면 조립기 단위 테스트는 전부
    초록불이고, 수수료는 어디에도 없는 채로 사업이 그만큼 유리해진다 —
    R26 이 형태 하나로 모은 「함수 층은 있는데 실행 경로가 부르지 않는다」다.

    수수료율만 0 → 8% 로 올리면 **NPV 가 작아져야** 한다. 방향까지 보는 이유:
    부호가 뒤집혀 수수료가 편익으로 들어가도 「달라진다」는 통과한다.
    """
    free = run_single_case_e2e(
        {}, level_map=LEVEL_MAP, horizon_years=_PROBE_HORIZON,
        structure=_MANAGER_STRUCTURE, provider=_manager_provider(fee_pct=0.0),
        settlement_inputs=_manager_inputs(), tariff_engine=_manager_engine(),
    )
    dear = run_single_case_e2e(
        {}, level_map=LEVEL_MAP, horizon_years=_PROBE_HORIZON,
        structure=_MANAGER_STRUCTURE, provider=_manager_provider(fee_pct=8.0),
        settlement_inputs=_manager_inputs(), tariff_engine=_manager_engine(),
    )

    assert dear.metrics["npv"] < free.metrics["npv"], (
        "수수료율을 8% 로 올렸는데 NPV 가 줄지 않았습니다 — `plan.costs` 가 "
        "프로포마에 닿지 않고 버려지고 있거나, 부호가 뒤집혀 편익으로 들어갔습니다"
    )


@pytest.mark.req("FR-205-AC1.ManagerEntity", "NFR-202-M1")
def test_the_manager_structure_is_refused_without_a_tariff_engine() -> None:
    """★ 요금엔진 없이 그 구조를 진입점에 넣으면 **거부**된다.

    조립기만 거부하고 진입점이 그것을 잡아 기본 경로로 내려가면, 그 케이스는
    「요금엔진을 안 쓴 단일계약」으로 그럴듯하게 계산된다.
    """
    with pytest.raises(ValidationError) as caught:
        run_single_case_e2e(
            {}, level_map=LEVEL_MAP, horizon_years=_PROBE_HORIZON,
            structure=_MANAGER_STRUCTURE, provider=_manager_provider(),
            settlement_inputs=_manager_inputs(),
        )

    assert caught.value.field == "model.contract.tariff_engine"


@pytest.mark.req("FR-205-AC1.VPP")
@pytest.mark.parametrize("structure", sorted(NOT_YET_ASSEMBLED))
def test_an_unassembled_structure_is_refused_by_the_execution_path(
    structure: str,
) -> None:
    """★★★ 미구현 구조는 **진입점이** 거부한다 — 편익 0 짜리 결과가 없다.

    조립기가 거부하는 것과 **진입점이 거부하는 것**은 다르다. 조립기만 거부하고
    진입점이 그것을 잡아 빈 목록으로 내려가면, 그 케이스는 「편익 0 인 사업」으로
    그럴듯하게 계산되어 케이스 표에 한 줄 남는다.
    """
    with pytest.raises(ValidationError) as caught:
        run_single_case_e2e(
            {}, level_map=LEVEL_MAP, horizon_years=_PROBE_HORIZON,
            structure=structure, provider=_provider(),
        )

    assert structure in caught.value.reason


@pytest.mark.req("FR-205-AC1.NetMetering", "NFR-202-M1")
def test_a_structure_without_a_ledger_is_refused() -> None:
    """★ 대장 없이 구조를 주면 거부한다 — 단가를 지어내지 않는다.

    통과시키면 조립기가 단가를 어디선가 만들어야 하고, 그 순간 `NFR-202`(정책
    수치를 소스에 두지 않는다)가 깨진다. 그리고 그 값은 결과에 그럴듯하게 실린다.
    """
    with pytest.raises(ValueError, match="전제 대장"):
        run_single_case_e2e(
            {}, level_map=LEVEL_MAP, horizon_years=_PROBE_HORIZON,
            structure="상계거래",
        )
