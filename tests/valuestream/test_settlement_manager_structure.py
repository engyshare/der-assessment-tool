"""「단일계약+관리주체 경유」 조립 — `FR-205-AC1` / R32.

R31 이 이 구조를 `NOT_YET_ASSEMBLED` 에 남긴 사유는 **값이 아니라 둘**이었다:

    ⓐ 요금엔진 통합    편익이 「기존 요금 − 신규 요금」이고 그 두 요금은
                       요금엔진이 누진·TOU 를 풀어야 나온다
    ⓑ 수수료를 실을 자리  `SelfConsumption` 에 차감항이 없고, **넣어서도 안 된다**
                       — 수수료는 편익이 아니라 비용이다

붙드는 것 여섯:

    ① 요금엔진이 없으면 **거부**한다        요금을 금액으로 받지 않는다
    ② ★ 요금표가 결과를 바꾼다              엔진을 지난다는 것의 실증
    ③ ★★ 수수료가 **편익에서 빠지지 않는다**  절감액이 온전하다
    ④ ★★ 수수료가 **비용 행**으로 나간다     진입점의 NPV 가 그만큼 준다
    ⑤ 계량점 전·후가 어긋나면 거부한다
    ⑥ 기준일이 없으면 거부한다              「오늘」로 떨어지지 않는다

**③과 ④를 함께 두는 것이 요점이다.** ③만 두면 수수료가 **어디에도** 없는
구현이 통과하고(편익은 온전하니까), ④만 두면 편익에서 빼서 만든 차액도 통과한다
— 그 상태의 NPV 는 사업자 관점에서 같은 수이고, **갈리는 것은 관점별·B/C 계정**
이라 이 두 검사가 각각 다른 층을 붙든다.
"""

from __future__ import annotations

from datetime import date

import pytest

from core.assumption.item import AssumptionItem, ConfidenceLevel
from core.assumption.provider import AssumptionSet
from core.contracts.assumptions import AssumptionProvider, PriceBasis
from core.contracts.der import DispatchResult
from core.contracts.units import Money
from core.contracts.validation import ValidationError
from core.regulation.tariff import (
    MeterPoint,
    ResidentialBlock,
    ResidentialTariffTable,
    TariffCatalog,
    TariffEngine,
    TaxAndFundScheme,
)
from core.valuestream.settlement import (
    MANAGER_FEE_KEY,
    SettlementInputs,
    assemble,
)

STRUCTURE = "단일계약+관리주체 경유"

#: 손계산 오라클용 요금표 — **1구간 단일 단가**로 둔다. 이 파일이 보는 것은
#: 누진 구조의 정확성이 아니라 **엔진을 지나는가**이며, 누진 자체는
#: `tests/regulation/test_tariff.py` 가 붙든다.
_ENERGY_KEY = "manager.energy"
_BASIC_KEY = "manager.basic"
_VAT_KEY = "tax.vat_rate"
_FUND_KEY = "tax.power_fund_rate"

#: 수수료율 — **%다**(대장 `value_unit` 이 「% (세대 배분 요금 대비)」). 3.0 을
#: 소수로 착각해 그대로 곱하면 수수료가 300% 가 된다.
FEE_PCT = 3.0

_BILLING_DATE = date(2026, 6, 1)


def _provider(
    fee_pct: float = FEE_PCT, energy_rate_won: float = 100.0
) -> AssumptionProvider:
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
            _ENERGY_KEY: item(_ENERGY_KEY, energy_rate_won, "원/kWh"),
            _BASIC_KEY: item(_BASIC_KEY, 1_000.0, "원/월"),
            _VAT_KEY: item(_VAT_KEY, 0.0, "소수"),
            _FUND_KEY: item(_FUND_KEY, 0.0, "소수"),
        },
        price_basis=PriceBasis.NOMINAL,
    )


def _engine(energy_rate_won: float = 100.0) -> TariffEngine:
    """단일 구간 주택용 요금표 하나짜리 엔진.

    단가를 인자로 받는 이유는 **요금표를 바꿔 결과가 따라 바뀌는지**를 보기
    위해서다(②). 대장 항목을 바꾸는 것과 요금표를 바꾸는 것이 여기서는 같은
    일이다 — 요금표가 단가를 **키로** 가리키므로.
    """
    table = ResidentialTariffTable(
        name="manager-2026",
        valid_from=date(2026, 1, 1),
        valid_to=None,
        blocks=(ResidentialBlock(None, _ENERGY_KEY, _BASIC_KEY),),
        tax_and_fund=TaxAndFundScheme(
            vat_rate_key=_VAT_KEY, power_fund_rate_key=_FUND_KEY
        ),
    )
    return TariffEngine(
        assumptions=_provider(energy_rate_won=energy_rate_won),
        catalog=TariffCatalog(residential=(table,), tou=(), direct_trade=()),
    )


def _inputs(baseline_kwh: float = 1_000.0, new_kwh: float = 600.0) -> SettlementInputs:
    """세대 하나 — 설비 전 1,000 kWh, 설비 후 600 kWh (자가소비 400 kWh)."""
    return SettlementInputs(
        baseline_meters=(MeterPoint.residential("101", baseline_kwh),),
        new_meters=(MeterPoint.residential("101", new_kwh),),
        billing_date=_BILLING_DATE,
    )


def _dispatch() -> DispatchResult:
    """`SelfConsumption` 은 디스패치를 보지 않는다 — 두 요금의 차액이 전부다."""
    return DispatchResult(electric=[0.0], heat=[0.0], cool=[0.0], fuel=[0.0])


# ── ① 요금엔진이 없으면 거부한다 ─────────────────────────────────────

@pytest.mark.req("FR-205-AC1.ManagerEntity", "NFR-202-M1")
def test_the_structure_is_refused_without_a_tariff_engine() -> None:
    """요금엔진 없이 조립하지 않는다 — **요금을 금액으로 받지 않는다.**

    통과시키면 두 요금이 어디선가 지어져야 하고, 그 순간 누진 구조가 결과에
    반영되지 않는다. 숫자는 그럴듯하고 「요금엔진 통합」은 이름만 남는다.
    """
    with pytest.raises(ValidationError) as caught:
        assemble(STRUCTURE, provider=_provider(), inputs=_inputs())

    assert caught.value.field == "model.contract.tariff_engine"
    assert (caught.value.action or "").strip()


# ── ② 요금표가 결과를 바꾼다 ─────────────────────────────────────────

@pytest.mark.req("FR-205-AC1.ManagerEntity")
def test_the_tariff_table_changes_the_benefit() -> None:
    """★★ **요금표를 바꾸면 절감액이 바뀐다** — 엔진을 실제로 지난다.

    조립기가 엔진을 부르고 그 결과를 버려도 ①은 통과한다(예외가 나지 않으므로).
    단가를 두 배인 키로 갈아 끼우면 절감액도 두 배가 되어야 한다 — 400 kWh ×
    100원 = 40,000원 → 400 kWh × 200원 = 80,000원.

    ★ **기본요금은 차액에서 사라진다**(전·후 같은 계량점 하나이므로) — 그래서
    이 오라클은 사용량 차이 × 단가로 닫힌다.
    """
    cheap = assemble(
        STRUCTURE, provider=_provider(), inputs=_inputs(),
        tariff_engine=_engine(energy_rate_won=100.0),
    )
    dear = assemble(
        STRUCTURE, provider=_provider(), inputs=_inputs(),
        tariff_engine=_engine(energy_rate_won=200.0),
    )

    cheap_saving = cheap.streams[0].annual_value(_dispatch(), year=1)
    dear_saving = dear.streams[0].annual_value(_dispatch(), year=1)

    assert cheap_saving == Money(40_000), "손계산 오라클: 400 kWh 에 100원"
    assert dear_saving == Money(80_000), (
        "단가를 두 배로 한 요금표가 결과를 바꾸지 않았습니다 — 조립기가 엔진을 "
        "부르고 그 값을 버리고 있습니다"
    )


# ── ③ 수수료가 편익에서 빠지지 않는다 ────────────────────────────────

@pytest.mark.req("FR-205-AC1.ManagerEntity", "FR-402-AC1")
def test_the_fee_is_not_subtracted_from_the_benefit() -> None:
    """★★ 절감액이 **온전하다** — 수수료를 편익에서 빼지 않았다.

    편익에서 빼면 **관점별 NPV 에서 그 지출이 사라진다** — 편익 계정만 줄고
    비용 계정에는 한 줄도 남지 않으므로 정부·사회 관점에서 그 비용이 아예 없는
    사업이 된다. B/C 분모도 그만큼 작아져 비율이 좋아진다.

    수수료율을 0 과 8% 로 두어도 **절감액은 같아야** 한다.
    """
    free = assemble(
        STRUCTURE, provider=_provider(fee_pct=0.0), inputs=_inputs(),
        tariff_engine=_engine(),
    )
    dear = assemble(
        STRUCTURE, provider=_provider(fee_pct=8.0), inputs=_inputs(),
        tariff_engine=_engine(),
    )

    assert free.streams[0].annual_value(_dispatch(), year=1) == Money(40_000)
    assert dear.streams[0].annual_value(_dispatch(), year=1) == Money(40_000), (
        "수수료율을 올리자 절감액이 줄었습니다 — 수수료가 편익의 차감항으로 "
        "들어가 있으며, 그러면 관점별 NPV 에서 그 비용이 사라집니다"
    )


@pytest.mark.req("FR-205-AC1.ManagerEntity")
def test_the_fee_leaves_as_a_cost_with_the_percent_unit_converted() -> None:
    """★ 수수료가 **비용으로** 나오고, 단위가 %에서 소수로 바뀌었다.

    손계산 오라클: 신규 요금 = 600 kWh × 100원 + 기본 1,000원 = **61,000원**.
    수수료 3% = **1,830원**. 3.0 을 소수로 착각해 곱하면 183,000원이 되어
    **요금보다 큰 수수료**가 나오는데, 그 수는 커도 「비율이니 그럴 수 있다」로
    읽히기 쉽다.
    """
    plan = assemble(
        STRUCTURE, provider=_provider(), inputs=_inputs(), tariff_engine=_engine()
    )

    assert len(plan.costs) == 1
    cost = plan.costs[0]
    assert cost.tag == "ManagerEntityFee"
    assert cost.annual_amount_won == Money(1_830), (
        f"수수료 손계산 오라클 1,830원(61,000원의 3%)과 다릅니다: "
        f"{cost.annual_amount_won} — % 를 소수로 착각하면 183,000원이 됩니다"
    )


@pytest.mark.req("FR-205-AC1.ManagerEntity")
def test_a_zero_fee_still_carries_a_cost_entry() -> None:
    """수수료 0(면제)도 **비용 항목 자체는 남는다.**

    대장 항목의 하단 0 은 「수수료 면제」 케이스를 겸한다. 항목을 없애면 면제와
    **미구현**이 구별되지 않는다 — 표에 행이 없는 것은 「0원」이 아니라
    「계산하지 않았다」로 읽힌다(`MissingAssumption` 에서 내린 판단과 같다).
    """
    plan = assemble(
        STRUCTURE, provider=_provider(fee_pct=0.0), inputs=_inputs(),
        tariff_engine=_engine(),
    )

    assert len(plan.costs) == 1
    assert plan.costs[0].annual_amount_won == Money(0)


# ── ⑤⑥ 거부 ──────────────────────────────────────────────────────────

@pytest.mark.req("FR-205-AC1.ManagerEntity", "NFR-303-M1")
def test_mismatched_meter_sets_are_refused() -> None:
    """★★ 전·후 계량점이 다르면 거부한다 — 다른 사업장 둘을 비교한 것이다.

    세대 하나를 빼먹은 신규 구성은 **그 세대의 요금 전액**이 절감으로 잡히고,
    그 금액은 정상 범위 안에 있어 눈으로 걸러지지 않는다.
    """
    mismatched = SettlementInputs(
        baseline_meters=(
            MeterPoint.residential("101", 1_000.0),
            MeterPoint.residential("102", 1_000.0),
        ),
        new_meters=(MeterPoint.residential("101", 600.0),),
        billing_date=_BILLING_DATE,
    )

    with pytest.raises(ValidationError) as caught:
        assemble(
            STRUCTURE, provider=_provider(), inputs=mismatched,
            tariff_engine=_engine(),
        )

    assert "102" in (caught.value.reason or "")


@pytest.mark.req("FR-205-AC1.ManagerEntity", "NFR-303-M1")
def test_a_missing_meter_configuration_is_refused() -> None:
    """계량점 구성이 없으면 거부한다 — 한쪽이 비면 요금 전액이 절감이 된다."""
    with pytest.raises(ValidationError) as caught:
        assemble(
            STRUCTURE,
            provider=_provider(),
            inputs=SettlementInputs(billing_date=_BILLING_DATE),
            tariff_engine=_engine(),
        )

    assert caught.value.field == "model.contract.settlement_inputs"


@pytest.mark.req("FR-205-AC1.ManagerEntity")
def test_a_missing_billing_date_is_refused() -> None:
    """★ 기준일이 없으면 거부한다 — **「오늘」로 떨어지지 않는다.**

    `date.today()` 로 기본값을 주면 같은 시나리오가 실행한 날에 따라 **다른
    요금표**를 타고(`DV-6` 유효기간 판정), 그 차이는 아무 예외도 내지 않는다.
    재현되지 않는 결과가 그럴듯하게 나온다.
    """
    inputs = SettlementInputs(
        baseline_meters=(MeterPoint.residential("101", 1_000.0),),
        new_meters=(MeterPoint.residential("101", 600.0),),
    )

    with pytest.raises(ValidationError) as caught:
        assemble(
            STRUCTURE, provider=_provider(), inputs=inputs, tariff_engine=_engine()
        )

    assert "billing_date" in (caught.value.reason or "")
