"""계약구조가 켜는 편익을 조립하는가 — `FR-205-AC1` / R31 (결정 §2).

`R13-WP24G` 설계서가 이 조항을 *「빈 구현이 아니라 **빈 조립도**」* 라 불렀다.
종전 `core/model/settlement.py::SettlementEngine` 은 구조 하나 → 금액 하나를
돌려주려 했고 **그 금액은 어느 구조에서도 `0.0`** 이었으며, 유일한 테스트는
구조명이 되돌아오는지만 보고 **금액을 단언하지 않았다**(spec §FR-205 주석이
그것을 지적해 두었다). 이 파일이 그 자리를 대체한다.

붙드는 것 다섯:

    ① 구조가 편익을 고른다              같은 잉여를 다르게 화폐화한다
    ② 인자가 대장에서 온다              단가를 소스에 적지 않는다 (NFR-202)
    ③ 지불 주체가 구조에 따라 갈린다     관점별 NPV 가 실제로 달라진다
    ④ 미구현 구조를 빈 목록으로 내지 않는다
    ⑤ 조립 결과가 배타 규칙을 지난다     선언표가 규칙표를 어기지 못한다

**④·⑤가 요점이다.** ①~③만 두면 「지금 둘이 된다」를 고정할 뿐이고, 나머지
다섯 구조가 조용히 편익 0 을 내는 것도, 선언표가 유형 A 조합을 켜는 것도 아무도
막지 않는다.
"""

from __future__ import annotations

import pytest

from core.assumption.item import AssumptionItem, ConfidenceLevel
from core.assumption.provider import AssumptionSet
from core.contracts.assumptions import AssumptionProvider, PriceBasis
from core.contracts.der import DispatchResult
from core.contracts.validation import ValidationError
from core.contracts.valuestream import CONTRACT_STRUCTURES, Payer
from core.valuestream.settlement import (
    ASSEMBLERS,
    NOT_YET_ASSEMBLED,
    SURPLUS_SALE_KEY,
    TARIFF_KEY,
    TRADE_FEE_KEY,
    SettlementInputs,
    assemble,
)

#: 손계산에 쓰는 대장값. **오라클을 손으로 적는다** — 대장에서 읽어 와 대장과
#: 비교하면 무엇을 넣어도 통과한다(R29 가 걷어낸 항진의 형태).
TARIFF = 150.0
FEE_RATE = 5.0
#: 잉여 직거래 판매단가 — **약관요금보다 낮다**(도매 계열). 그 관계가 뜻이다.
DIRECT_SALE_PRICE = 110.0


def _provider() -> AssumptionProvider:
    def item(key: str, value: float, unit: str) -> AssumptionItem:
        return AssumptionItem(
            key=key, value=value, value_unit=unit, base_year="2026",
            applicable_scope="검사용", derivation_method="검사용",
            source=None, verified_at=None, confidence=ConfidenceLevel.ASSUMED,
        )

    return AssumptionSet(
        name="검사", version="1",
        items={
            TARIFF_KEY: item(TARIFF_KEY, TARIFF, "원/kWh"),
            TRADE_FEE_KEY: item(TRADE_FEE_KEY, FEE_RATE, "원/kWh"),
            SURPLUS_SALE_KEY: item(SURPLUS_SALE_KEY, DIRECT_SALE_PRICE, "원/kWh"),
        },
        price_basis=PriceBasis.NOMINAL,
    )


def _dispatch(surplus_kwh: float) -> DispatchResult:
    """잉여 한 스텝짜리 디스패치 — 잉여판매 산식이 보는 것은 양수 합이다."""
    return DispatchResult(
        electric=[surplus_kwh], heat=[0.0], cool=[0.0], fuel=[0.0]
    )


# ── ① 구조가 편익을 고른다 ───────────────────────────────────────────

@pytest.mark.req("FR-205-AC1")
def test_each_structure_activates_a_different_benefit() -> None:
    """★ **구조가 서로 다른 편익을 켠다** — 그것이 「정산 로직에 반영」의 실질이다.

    같은 잉여를 상계로 차감하느냐 직접거래로 파느냐는 **다른 산식**이고, 둘은
    배타 규칙표에서 유형 A(동일 물리량 이중 판매)로 서로를 배제한다. 그러면
    「무엇이 그 하나를 고르는가」가 비어 있었던 것이고, 답이 계약구조다.
    """
    net = assemble("상계거래", provider=_provider())
    direct = assemble(
        "분산특구 직접거래",
        provider=_provider(),
        inputs=SettlementInputs(trade_price_won_per_kwh=120.0, trade_volume_kwh=1_000.0),
    )

    assert [type(s).tag for s in net.streams] == ["SurplusSale"]
    assert [type(s).tag for s in direct.streams] == ["DirectTrade"]
    # 구조 이름이 계획에 남는다 — 표시 층이 「어느 구조로 계산했는가」를 말한다
    assert net.structure == "상계거래"
    assert direct.structure == "분산특구 직접거래"


# ── ② 인자가 대장에서 온다 ───────────────────────────────────────────

@pytest.mark.req("FR-205-AC1", "NFR-202-M1")
def test_net_metering_uses_the_ledger_tariff_as_the_offset_price() -> None:
    """상계 차감단가가 **대장의 약관요금**이다 — 손계산으로 확인한다.

    오라클: 순위 1(해석해). 잉여 500 kWh × 150 원/kWh = 75,000 원.

    ★ **판매단가(SMP)를 쓰지 않는 근거를 값으로 고정한다** — SMP 는 도매가라
    소매 요금보다 낮고, 상계에 그것을 쓰면 회피한 요금보다 적게 계상되어
    상계거래가 늘 불리하게 나온다.
    """
    plan = assemble("상계거래", provider=_provider())
    (stream,) = plan.streams

    assert stream.annual_value(_dispatch(500.0), year=1) == 500 * TARIFF
    # 어느 대장 키를 읽었는지 함께 나른다 — 리포트가 출처를 말할 수 있게
    assert plan.assumption_keys == (TARIFF_KEY,)


@pytest.mark.req("FR-205-AC1", "NFR-202-M1")
def test_direct_trade_spread_and_fee_come_from_the_ledger() -> None:
    """직접거래 차익 = (약관요금 − 계약단가) × 거래량 − 수수료.

    오라클: 순위 1(해석해). (150 − 120) × 1,000 − 5 × 1,000
            = 30,000 − 5,000 = **25,000 원**.

    ★ **수수료가 단가 × 거래량인 것을 값으로 고정한다** — 대장의
    `fee.direct_trade_support` 는 원/kWh 이고, 그것을 총액으로 잘못 읽으면
    거래량이 커질수록 수수료가 상대적으로 사라진다.
    """
    plan = assemble(
        "분산특구 직접거래",
        provider=_provider(),
        inputs=SettlementInputs(trade_price_won_per_kwh=120.0, trade_volume_kwh=1_000.0),
    )
    (stream,) = plan.streams

    assert stream.annual_value(_dispatch(0.0), year=1) == 25_000
    assert plan.assumption_keys == (TARIFF_KEY, TRADE_FEE_KEY)


@pytest.mark.req("FR-205-AC1")
def test_direct_trade_without_the_negotiated_inputs_is_refused() -> None:
    """★ 계약단가·거래량이 없으면 거부한다 — 0 으로 메우지 않는다.

    0 으로 두면 차익이 **약관요금 전액**이 되어 큰 가짜 편익이 생기고, 거래량
    0 이면 편익이 0 이 되어 「거래가 없는 사업」과 구별되지 않는다. 둘 다 아무
    예외 없이 그럴듯한 숫자를 낸다 — `MissingAssumption` 이 값에 대해 하는
    판단과 같은 형태다.
    """
    for inputs in (
        SettlementInputs(),
        SettlementInputs(trade_price_won_per_kwh=120.0),
        SettlementInputs(trade_volume_kwh=1_000.0),
    ):
        with pytest.raises(ValidationError) as caught:
            assemble("분산특구 직접거래", provider=_provider(), inputs=inputs)
        assert caught.value.field == "model.contract.settlement_inputs"
        assert caught.value.action.strip()


# ── ③ 지불 주체가 구조에 따라 갈린다 ─────────────────────────────────

@pytest.mark.req("FR-205-AC1", "FR-402-AC5")
def test_the_payer_follows_the_structure() -> None:
    """★★ **같은 `SurplusSale` 이 구조에 따라 다른 지갑을 가리킨다.**

    `docs/domain-rules.md` 관점 분리표는 *잉여판매·직접거래 수익*의 참여 주민
    칸을 「계약구조에 따름」으로 둔다. 상계는 판매가 아니라 **가구 계량점의 요금
    차감**이므로 그 계량점 명의자에게 귀속된다 — 사업자로 두면 관점별 NPV 에서
    주민 편익이 통째로 사라지고, 합계가 맞아 드러나지 않는다.

    **구조를 주지 않은 인스턴스와 대조한다** — 대조 없이 한쪽만 보면 클래스
    기본값이 우연히 같은 경우와 구별되지 않는다.
    """
    (net,) = assemble("상계거래", provider=_provider()).streams
    assert net.effective_payer is Payer.RESIDENT

    from core.valuestream import SurplusSale

    assert SurplusSale(sale_price_won_per_kwh=1.0).effective_payer is Payer.OPERATOR

    (direct,) = assemble(
        "분산특구 직접거래",
        provider=_provider(),
        inputs=SettlementInputs(trade_price_won_per_kwh=1.0, trade_volume_kwh=1.0),
    ).streams
    assert direct.effective_payer is Payer.OPERATOR


# ── ④ 미구현 구조를 빈 목록으로 내지 않는다 ──────────────────────────

@pytest.mark.req("FR-205-AC1")
@pytest.mark.parametrize("structure", sorted(NOT_YET_ASSEMBLED))
def test_a_structure_without_an_assembler_is_refused_with_a_reason(
    structure: str,
) -> None:
    """★★★ 조립 규칙이 없는 구조는 **사유를 들고 거부**한다.

    빈 목록을 돌려주면 **편익 0 인 사업**이 그럴듯하게 나오고, 사용자는 그
    구조가 미구현인지 정말 편익이 없는지 구별할 수 없다. 이 저장소가
    `MissingAssumption`·`RegistryError` 에서 반복해 내린 판단과 같다.
    """
    with pytest.raises(ValidationError) as caught:
        assemble(structure, provider=_provider())

    assert structure in caught.value.reason
    # 사유가 **무엇이 선행해야 하는가**를 말한다 — 「미구현」만으로는 다음 사람이
    # 무엇을 해야 하는지 모른다
    assert len(NOT_YET_ASSEMBLED[structure]) > 40
    assert NOT_YET_ASSEMBLED[structure] in caught.value.reason


@pytest.mark.req("FR-205-AC1")
def test_the_seven_structures_are_partitioned_with_no_gap_and_no_overlap() -> None:
    """★★ **일곱이 「조립된다」와 「아직」으로 정확히 갈린다.**

    래칫이다. 여덟 번째 구조가 `CONTRACT_STRUCTURES` 에 들어오면 두 표 어느
    쪽에도 없으므로 빨간불이 되고, 그때 `assemble()` 은 `NOT_YET_ASSEMBLED` 를
    조회하다 `KeyError` 로 죽는다 — **이 검사가 없으면 그 죽음이 사용자 앞에서
    일어난다.** `test_dv_rule_enforcement.py` 가 대장 14규칙에 쓴 것과 같은 형태.
    """
    assembled = set(ASSEMBLERS)
    pending = set(NOT_YET_ASSEMBLED)

    assert assembled | pending == set(CONTRACT_STRUCTURES), (
        "두 표의 합집합이 spec 의 일곱과 다릅니다. "
        f"빠짐: {set(CONTRACT_STRUCTURES) - assembled - pending}, "
        f"지어냄: {assembled | pending - set(CONTRACT_STRUCTURES)}"
    )
    assert not (assembled & pending), (
        f"두 표에 겹치는 구조가 있습니다: {sorted(assembled & pending)} — "
        "어느 쪽이 정본인지 실행 시점에 갈립니다"
    )
    # 조립되는 구조 수를 적어 둔다 — 늘면 이 수를 함께 고치게 되고, 그때
    # `NOT_YET_ASSEMBLED` 에서 무엇이 빠졌는지 위 합집합 단언이 함께 말한다
    assert len(assembled) == 3


@pytest.mark.req("FR-205-AC1")
def test_an_unknown_structure_is_refused_before_the_lookup() -> None:
    """열거 밖의 이름은 조립 전에 거부된다.

    통과시키면 `NOT_YET_ASSEMBLED[structure]` 가 `KeyError` 를 내고, 그것은
    사용자에게 아무것도 말해 주지 않는다.
    """
    with pytest.raises(ValidationError) as caught:
        assemble("상계", provider=_provider())

    assert caught.value.field == "model.contract.structure"
    assert "상계거래" in caught.value.reason


# ── ⑤ 조립 결과가 배타 규칙을 지난다 ─────────────────────────────────

@pytest.mark.req("FR-205-AC1", "FR-402-AC2.A")
def test_the_assembler_checks_its_own_output_against_the_exclusion_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★★★ **선언표가 규칙표를 어기면 조립 시점에 거부된다.**

    `SelfConsumption`·`SurplusSale`·`DirectTrade` 는 서로 유형 A 배타다 —
    같은 잉여를 화폐화하는 세 갈래이므로 동시에 켤 수 없다. 조립기가 그것을
    스스로 확인하지 않으면 규칙표는 정본인데 조립기가 그것을 어기는 상태가
    만들어지고, **그 조합은 케이스 실행까지 내려가서야 잡힌다** — 그때는 이미
    자원·디스패치가 한 번 돈 뒤다.

    선언표에 금지 조합을 켜는 조립기를 심어 확인한다.
    """
    from core.valuestream import SelfConsumption, SurplusSale
    from core.valuestream.settlement import SettlementPlan

    def _both(provider: AssumptionProvider, inputs: SettlementInputs) -> SettlementPlan:
        return SettlementPlan(
            structure="상계거래",
            streams=(
                SurplusSale(sale_price_won_per_kwh=1.0, structure="상계거래"),
                SelfConsumption(
                    baseline_annual_bill_won=100.0, new_annual_bill_won=50.0
                ),
            ),
        )

    # `MappingProxyType` 은 항목을 갈 수 없으므로 모듈 속성을 갈아 끼운다
    import core.valuestream.settlement as settlement_module

    monkeypatch.setattr(settlement_module, "ASSEMBLERS", {"상계거래": _both})

    with pytest.raises(ValidationError) as caught:
        assemble("상계거래", provider=_provider())

    assert caught.value.rule == "DV-12"


@pytest.mark.req("FR-205-AC1", "NFR-202-M1")
def test_surplus_direct_sale_uses_a_different_price_than_net_metering() -> None:
    """★★ **같은 산식, 다른 단가** — 그것이 두 구조를 가르는 전부다.

    `surplus_sale.py` 독스트링이 *「판매단가는 판매 경로(직거래·상계·SMP)에 따라
    다르다 … 경로가 섞이면 인스턴스를 여러 개 둔다」* 고 스스로 적고 있었다.
    두 조립기가 그 「여러 개」의 실물이며 **구조가 경로를 고른다.**

    ⚠ **같은 단가를 쓰면 두 구조가 수치까지 같아진다** — 그러면 `FR-202`(구조
    비교)의 표에 같은 줄이 두 번 나오고, 조립기는 둘인데 결과는 하나인 상태가
    아무 예외 없이 만들어진다. 그래서 「다르다」를 단언한다.

    오라클: 순위 1(해석해). 잉여 500 kWh × 110 원/kWh = 55,000 원.
    """
    (direct_sale,) = assemble("잉여 직거래", provider=_provider()).streams
    (net,) = assemble("상계거래", provider=_provider()).streams

    surplus = _dispatch(500.0)
    assert direct_sale.annual_value(surplus, year=1) == 500 * DIRECT_SALE_PRICE
    assert direct_sale.annual_value(surplus, year=1) != net.annual_value(surplus, year=1)

    # **도매가가 소매 요금보다 낮다**는 관계까지 고정한다 — 뒤집히면 「잉여를
    # 팔면 사는 것보다 이득」이 되어 상계거래가 원리상 열등해지고, 그 결론은
    # 단가 가정이 만든 것이지 사업의 성질이 아니다
    assert DIRECT_SALE_PRICE < TARIFF
