"""계약·거래 구조 → 활성 편익 조립 — `FR-205-AC1` / R31 (결정 문서 §2).

조항 문면: *「다음이 정산 로직에 반영된다 — 개별 세대 직접계약 / 단일계약+관리주체
경유 / 분산특구 직접거래 / 상계거래 / 잉여 직거래 / 집합 PPA / VPP 경유」*

`R13-WP24G` 설계서가 이 조항을 *「빈 구현이 아니라 **빈 조립도**」* 라 불렀다.
계산은 `core/valuestream/` 에 이미 전부 있고, 없던 것은 **구조마다 어느 편익을
켜고 그 인자를 어디서 가져오는가**다.

## 왜 금액 하나가 아니라 편익 목록인가 (결정 §2-1)

종전 `SettlementEngine` 은 구조 하나 → 금액 하나(`amount`)를 돌려주려 했고 그
금액은 늘 `0.0` 이었다. **그 형태를 버렸다.** `core/cba/` 가 이미 편익 목록을
모아 프로포마를 만드는데 정산이 별도 금액을 만들면 **같은 화폐 흐름을 두 번
계산하는 길이 열린다** — 도메인 원칙 「중복」과 정면으로 부딪치고, 그 상태는
결과가 그럴듯해서 스스로 드러나지 않는다.

조립기는 기존 파이프라인에 그대로 얹히고, 새 편익·새 구조가 늘 때 **선언만 늘고
계산 코드는 그대로다.**

## ★ 배타 규칙표가 이미 「구조가 하나를 고른다」를 말하고 있었다

`docs/exclusion-rules.yaml` 은 `SelfConsumption ↔ SurplusSale` 과
`SurplusSale ↔ DirectTrade` 를 **유형 A**(동일 물리량 이중 판매)로 둔다. 즉 이
셋은 **같은 잉여를 화폐화하는 세 갈래이고 동시에 켤 수 없다.** 그러면 「무엇이
그 하나를 고르는가」가 비어 있었던 것이고, **그 답이 계약구조다.**

그래서 이 파일은 규칙표를 다시 적지 않는다 — 조립한 결과를
`assert_no_exclusions()` 에 **스스로 통과시킨다**(아래 §자기 검사). 선언표에
금지 조합을 적으면 조립 시점에 거부된다.

## 아직 조립기가 없는 구조를 **빈 목록으로 돌려주지 않는다**

**R32 기준 남은 것은 「VPP 경유」 하나**이며 그것은 조항 쪽이 막고 있다(Phase 2).
조용히 빈 목록을 돌려주면 **편익 0 인 사업**이 그럴듯하게 나오고, 사용자는 그
구조가 미구현인지 정말 편익이 없는지 구별할 수 없다. `NOT_YET_ASSEMBLED` 가
**구조마다 무엇이 막고 있는지**를 들고 거부한다.

⚠ **그 사유를 R31 이 한 번 고쳐 썼다.** 초판은 넷 다 「대장에 값이 없다」로
적었는데, `Q-14`~`Q-16` 을 등재하고 보니 **값이 막고 있던 것은 하나뿐**이었다
(「잉여 직거래」). 나머지 셋은 값이 아니라 **정산 대상 미정 · 요금엔진 통합 ·
없는 편익 클래스**가 막고 있었고, **R32 가 그 셋을 각각 그 자리에서 풀었다** —
정산 대상은 조항으로(spec v0.16), 요금엔진은 `TariffEngine` 배선으로, 편익
클래스는 `aggregated_ppa.py` 신설로. 사유를 낡은 채 두면 다음 사람이 값을
등재하고 「이제 되겠다」고 착수한 뒤에야 그것을 알게 된다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType

from core.contracts.assumptions import AssumptionProvider
from core.contracts.units import Money, pct_to_fraction, to_won
from core.contracts.validation import ValidationError
from core.contracts.valuestream import CONTRACT_STRUCTURES, ValueStream
from core.regulation.tariff import MeterPoint, TariffEngine
from core.valuestream.aggregated_ppa import AggregatedPPA
from core.valuestream.direct_trade import DirectTrade
from core.valuestream.exclusion_table import assert_no_exclusions
from core.valuestream.self_consumption import SelfConsumption
from core.valuestream.surplus_sale import SurplusSale

#: 약관요금(실효단가) — 상계 차감단가이자 직접거래 차익의 기준가.
#: Q-6 가정이며 `TU-6`(계량점 구성 확인) 해소 시 교체된다.
TARIFF_KEY = "tariff.hv_single_contract.avg"

#: 거래지원수수료 단가(원/kWh) — Q-7. 하단 0(면제 케이스)을 겸한다.
TRADE_FEE_KEY = "fee.direct_trade_support"

#: 잉여 직거래 판매단가(원/kWh) — Q-16. **약관요금보다 낮다**(도매 정산단가 계열).
SURPLUS_SALE_KEY = "tariff.surplus_direct_sale"

#: 관리주체 경유 수수료율(**%**, 세대 배분 요금 대비) — Q-14. 하단 0(면제)을 겸한다.
#:
#: ⚠ **단위가 %다.** 대장 항목의 `value_unit` 이 *「% (세대 배분 요금 대비)」* 이며
#: 다른 두 키(원/kWh)와 단위가 다르다 — 소수로 착각해 3.0 을 그대로 곱하면
#: 수수료가 **300%** 가 된다. 경계에서 `pct_to_fraction()` 으로 바꾼다(§7.5).
MANAGER_FEE_KEY = "fee.manager_entity"

#: 집합 PPA 계약단가 — **약관요금 대비 비율**(소수) — Q-15.
#:
#: ⚠ **절대 단가가 아니다.** 절대 단가를 대장에 두면 약관요금 개정 때 둘이
#: 어긋나고 그 어긋남은 아무 예외도 내지 않는다 — PPA 단가가 약관요금을 넘는
#: 상태도 조용히 성립한다.
PPA_RATIO_KEY = "tariff.aggregated_ppa.ratio"


@dataclass(frozen=True)
class SettlementInputs:
    """구조가 요구하는 **사용자 입력** — 대장에 없는 것만 여기 있다.

    **대장 값과 가르는 기준**: 대장은 「조사해서 알 수 있는 값」이고 여기는
    「당사자가 협상해서 정하는 값」이다. 직접거래단가는 특구 안 두 당사자의
    계약 결과이므로 조사 대상이 아니다 — 대장에 넣으면 「가정한 협상 결과」가
    되고, 그것은 민감도로 드러나지 않는 종류의 허구다.
    """

    #: 직접거래 계약단가(원/kWh). 「분산특구 직접거래」에 필수다.
    trade_price_won_per_kwh: float | None = None
    #: 연간 직접거래량(kWh). 없으면 디스패치 잉여를 쓰라는 뜻이 아니라 **거부**다
    #: — 거래량은 계약이 정하는 상한이고 발전량과 같지 않다.
    trade_volume_kwh: float | None = None

    #: 「집합 PPA」의 연간 **전량** 발전량(kWh) — R32. 잉여가 아니다.
    annual_generation_kwh: float | None = None

    #: 「개별 세대 직접계약」의 가구–구매자 계약단가(원/kWh) — R32.
    #:
    #: ⚠ **`trade_price_won_per_kwh` 와 나누어 둔다.** 둘 다 협상값이지만 **서로 다른
    #: 협상의 결과**이고, 한 필드를 공유하면 「특구 직접거래용으로 준 단가가 개별세대
    #: 구조에 쓰인다」가 조용히 일어난다. 거부 메시지도 어느 단가가 없는지 말할 수
    #: 없게 된다.
    household_contract_price_won_per_kwh: float | None = None

    #: 「단일계약+관리주체 경유」 — **설비 전** 계량점 구성 (R32).
    #: 두 요금은 요금엔진이 누진·TOU 를 풀어 내므로 대장에도 협상값에도 없다.
    #: 여기 있는 것은 **금액이 아니라 계량점**이다 — 금액을 사용자에게 받으면
    #: 요금엔진을 지나지 않고, 그러면 누진 구조가 결과에 반영되지 않는다.
    baseline_meters: tuple[MeterPoint, ...] = ()
    #: **설비 후** 계량점 구성 (자가소비로 줄어든 사용량).
    new_meters: tuple[MeterPoint, ...] = ()
    #: 요금 산정 기준일. **기본값을 두지 않는다** — `date.today()` 로 떨어지면
    #: 같은 시나리오가 **실행한 날에 따라 다른 요금표**를 타고(`DV-6`), 그 차이는
    #: 아무 예외도 내지 않는다. 재현되지 않는 결과가 그럴듯하게 나온다.
    billing_date: date | None = None


@dataclass(frozen=True)
class SettlementCost:
    """구조가 만드는 **비용** — 편익에서 빼지 않는다 (`FR-205-AC1` / R32).

    수수료를 편익의 차감항으로 넣으면 **관점별 NPV 에서 그 지출이 사라진다**
    (`core/cba/proforma.py::fee_row` 독스트링에 근거를 적었다). 그래서 조립기는
    비용을 **비용으로** 내고, 프로포마 행을 짓는 것은 상위 계층이다 —
    `core.cba` 는 `core.valuestream` 보다 **위**여서 여기서 부를 수 없다
    (`NFR-208-AC1`). 이 자료형이 그 경계를 건너는 형태다.
    """

    tag: str
    label: str
    #: 연간 금액(원, 양수). 연도별로 다른 비용이 생기면 그때 자료형을 늘린다 —
    #: 지금 `Mapping[int, Money]` 로 두면 **소비자가 없는 일반화**가 된다.
    annual_amount_won: Money


@dataclass(frozen=True)
class SettlementPlan:
    """조립 결과 — 활성 편익과 **그 인자가 어디서 왔는가**.

    `assumption_keys` 를 함께 나르는 이유: `FR-1001` 은 산식과 출처 표시를
    요구하고, 리포트가 나중에 출처를 따로 찾아 붙이는 구조라면 반드시 빠진다
    (`AssumptionValue` 가 부기 7종을 함께 나르는 것과 같은 이유).
    """

    structure: str
    streams: tuple[ValueStream, ...]
    assumption_keys: tuple[str, ...] = field(default=())
    #: 이 구조가 만드는 비용. 비어 있는 것이 정상이다 — 수수료가 붙는 구조만 채운다
    costs: tuple[SettlementCost, ...] = field(default=())


#: 조립기 셋째 인자가 요금엔진이다. **`| None` 인 것이 요점**이며, 요금엔진을
#: 요구하는 구조는 없을 때 **거부한다**(지어낸 요금으로 계산하지 않는다).
_Assembler = Callable[
    [AssumptionProvider, SettlementInputs, "TariffEngine | None"], SettlementPlan
]


def _net_metering(
    provider: AssumptionProvider,
    inputs: SettlementInputs,
    engine: TariffEngine | None,
) -> SettlementPlan:
    """상계거래 — 잉여를 **판매하지 않고 요금에서 차감**한다.

    차감단가를 약관요금(실효단가)으로 둔다: 상계는 그만큼의 구입을 회피한 것이고,
    회피한 것의 값은 그 시점에 실제로 냈어야 할 요금이다. **판매단가(SMP)를
    쓰지 않는 이유가 여기 있다** — SMP 는 도매가라 소매 요금보다 낮고, 상계에
    SMP 를 쓰면 회피한 요금보다 적게 계상되어 상계거래가 늘 불리하게 나온다.
    """
    structure = "상계거래"
    tariff = provider.require_float(TARIFF_KEY)
    return SettlementPlan(
        structure=structure,
        streams=(
            SurplusSale(sale_price_won_per_kwh=tariff, structure=structure),
        ),
        assumption_keys=(TARIFF_KEY,),
    )


def _surplus_direct_sale(
    provider: AssumptionProvider,
    inputs: SettlementInputs,
    engine: TariffEngine | None,
) -> SettlementPlan:
    """잉여 직거래 — 잉여를 **판매**한다. 상계와 같은 산식, **다른 단가**.

    `surplus_sale.py` 독스트링이 *「판매단가는 판매 경로(직거래·상계·SMP)에 따라
    다르다 … 경로가 섞이면 인스턴스를 여러 개 둔다」* 고 스스로 적고 있었다.
    이 조립기와 `_net_metering` 이 그 「여러 개」의 실물이며, **구조가 어느
    경로인지를 고른다.**

    ⚠ **상계와 단가가 다른 것이 이 구조의 전부다.** 같은 단가를 쓰면 두 구조가
    수치까지 같아지고, 그러면 `FR-202`(구조 비교)의 표에 같은 줄이 두 번 나온다 —
    조립기는 둘인데 결과는 하나인 상태이며 아무 예외도 나지 않는다.
    """
    structure = "잉여 직거래"
    price = provider.require_float(SURPLUS_SALE_KEY)
    return SettlementPlan(
        structure=structure,
        streams=(SurplusSale(sale_price_won_per_kwh=price, structure=structure),),
        assumption_keys=(SURPLUS_SALE_KEY,),
    )


def _distributed_direct_trade(
    provider: AssumptionProvider,
    inputs: SettlementInputs,
    engine: TariffEngine | None,
) -> SettlementPlan:
    """분산특구 직접거래 — (약관요금 − 계약단가) × 거래량 − 지원수수료.

    ⚠ **계약단가·거래량이 없으면 거부한다.** 0 으로 두면 차익이 **약관요금
    전액**이 되어 큰 가짜 편익이 생기고, 거래량 0 이면 편익이 0 이 되어
    「거래가 없는 사업」과 구별되지 않는다. 둘 다 아무 예외 없이 그럴듯한
    숫자를 낸다.
    """
    structure = "분산특구 직접거래"
    missing = [
        name
        for name, value in (
            ("trade_price_won_per_kwh", inputs.trade_price_won_per_kwh),
            ("trade_volume_kwh", inputs.trade_volume_kwh),
        )
        if value is None
    ]
    if missing:
        raise ValidationError(
            field="model.contract.settlement_inputs",
            reason=(
                f"«{structure}» 정산에 필요한 사용자 입력이 없습니다: "
                f"{', '.join(missing)}"
            ),
            action=(
                "`SettlementInputs` 에 계약단가와 연간 거래량을 주십시오. "
                "0 으로 두면 차익이 약관요금 전액이 되거나 편익이 0 이 되고, "
                "둘 다 오류로 보이지 않습니다"
            ),
        )
    assert inputs.trade_price_won_per_kwh is not None  # 위에서 거부했다
    assert inputs.trade_volume_kwh is not None
    tariff = provider.require_float(TARIFF_KEY)
    fee_rate = provider.require_float(TRADE_FEE_KEY)
    return SettlementPlan(
        structure=structure,
        streams=(
            DirectTrade(
                tariff_won_per_kwh=tariff,
                trade_price_won_per_kwh=inputs.trade_price_won_per_kwh,
                trade_volume_kwh=inputs.trade_volume_kwh,
                support_fee_won=fee_rate * inputs.trade_volume_kwh,
                structure=structure,
            ),
        ),
        assumption_keys=(TARIFF_KEY, TRADE_FEE_KEY),
    )


def _aggregated_ppa(
    provider: AssumptionProvider,
    inputs: SettlementInputs,
    engine: TariffEngine | None,
) -> SettlementPlan:
    """집합 PPA — **발전량 전량** × (약관요금 × 비율) (R32).

    조항: *「집합 PPA」* (`FR-205-AC1`). R31 이 남긴 사유는 **없는 편익 클래스**
    였다 — `SurplusSale` 은 잉여만 보므로 전량 판매를 표현할 수 없고, 대신 쓰면
    **자가소비분이 빠져 편익이 조용히 작아진다.** R32 가
    `core/valuestream/aggregated_ppa.py` 를 신설하고 `FR-401-AC2.AggregatedPPA`
    조항을 함께 세웠다(spec v0.16).

    ## 단가를 비율로 두는 이유

    대장 항목은 **약관요금 대비 비율**(`Q-15`, 기본 0.85)이고 절대 단가가 아니다.
    절대 단가를 대장에 두면 약관요금이 개정될 때 둘이 어긋나고, **그 어긋남은
    아무 예외도 내지 않는다** — PPA 단가가 약관요금을 넘는 상태도 조용히 성립한다.

    ## 발전량이 없으면 거부한다

    전량 발전량은 디스패치 결과에서 복원할 수 없다(순 계통 흐름이라 자가소비분이
    이미 상계돼 있다). 0 으로 두면 편익이 0 이 되어 **「PPA 가 없는 사업」과
    구별되지 않는다.**
    """
    structure = "집합 PPA"
    generation = inputs.annual_generation_kwh
    if generation is None:
        raise ValidationError(
            field="model.contract.settlement_inputs",
            reason=(
                f"«{structure}» 정산에 필요한 사용자 입력이 없습니다: "
                "annual_generation_kwh"
            ),
            action=(
                "연간 **전량** 발전량(kWh)을 주십시오. 디스패치 결과에서 뽑지 "
                "않습니다 — 그것은 순 계통 흐름이라 자가소비분이 이미 상계돼 있고, "
                "그 값을 쓰면 이 구조가 잉여판매와 같아집니다"
            ),
        )
    tariff = provider.require_float(TARIFF_KEY)
    ratio = provider.require_float(PPA_RATIO_KEY)
    return SettlementPlan(
        structure=structure,
        streams=(
            AggregatedPPA(
                ppa_price_won_per_kwh=tariff * ratio,
                annual_generation_kwh=generation,
                structure=structure,
            ),
        ),
        assumption_keys=(TARIFF_KEY, PPA_RATIO_KEY),
    )


def _household_direct_contract(
    provider: AssumptionProvider,
    inputs: SettlementInputs,
    engine: TariffEngine | None,
) -> SettlementPlan:
    """개별 세대 직접계약 — 가구가 파는 **잉여** × 계약단가 (R32 결정).

    조항: *「개별 세대 직접계약」* (`FR-205-AC1`). R31 이 이 구조를
    `NOT_YET_ASSEMBLED` 에 남긴 사유는 **값이 아니라 「정산 대상 미정」**이었다 —
    잉여 순액인지 자가소비 절감인지 spec 이 적지 않았고, 배타 규칙표가 둘을 유형 A
    로 두므로 **하나를 골라야** 했다.

    ## 정한 것과 근거

    **정산 대상은 계통 역송 전력(잉여)이고 판매 주체는 가구다.** 조항이 *「가구가
    구매자와 **직접** 계약」* 이라 적으므로 파는 쪽이 가구이며, 「직접계약」의 대상이
    될 수 있는 전력은 **계량점 밖으로 나가는 것**뿐이다 — 자가소비분은 계약 상대에게
    인도되지 않으므로 매매의 대상이 아니다. 그래서 `SurplusSale` 이고,
    `payer_by_structure` 가 이 구조에서 `RESIDENT` 를 낸다(사업자를 거치지 않는 것이
    이 구조의 정의다).

    spec `FR-205-AC1` 아래 v0.16 결정으로 **조항에 적어 두었다** — 여기서만 정하면
    구현이 조항을 대신 판단한 상태로 남고, 다음 사람은 그것이 결정인지 편의인지
    알 수 없다.

    ⚠ **잠정이다.** 부지·설비 임대 결합형처럼 자가소비분까지 계약에 넣는 실물
    계약서가 나타나면 대상이 넓어진다. 바뀌는 것은 조항 문면과 이 함수 하나이며,
    계약단가는 협상값이라 대장 개정이 붙지 않는다
    (`docs/decisions-2026-08-14-R32.md` §3).

    ## 단가가 없으면 거부한다

    `_distributed_direct_trade` 와 같은 이유다 — 0 으로 두면 편익이 0 이 되어
    **「계약이 없는 사업」과 구별되지 않고**, 그 결과는 아무 예외 없이 그럴듯하다.
    """
    structure = "개별 세대 직접계약"
    price = inputs.household_contract_price_won_per_kwh
    if price is None:
        raise ValidationError(
            field="model.contract.settlement_inputs",
            reason=(
                f"«{structure}» 정산에 필요한 사용자 입력이 없습니다: "
                "household_contract_price_won_per_kwh"
            ),
            action=(
                "가구와 구매자가 합의한 계약단가(원/kWh)를 주십시오. **대장에서 "
                "읽지 않습니다** — 협상 결과이므로 조사 대상이 아니고, 대장에 넣으면 "
                "「가정한 협상 결과」가 되어 민감도로 드러나지 않습니다. "
                "0 으로 두면 편익이 0 이 되어 계약이 없는 사업과 구별되지 않습니다"
            ),
        )
    return SettlementPlan(
        structure=structure,
        streams=(
            SurplusSale(sale_price_won_per_kwh=price, structure=structure),
        ),
        # 대장 항목을 하나도 쓰지 않는다 — 계약단가가 협상값이기 때문이다.
        # **빈 튜플이 「출처를 빠뜨렸다」가 아니라 「대장 밖 값이다」임을 뜻한다.**
        assumption_keys=(),
    )


def _single_contract_via_manager(
    provider: AssumptionProvider,
    inputs: SettlementInputs,
    engine: TariffEngine | None,
) -> SettlementPlan:
    """단일계약+관리주체 경유 — **요금엔진이 두 요금을 내고, 수수료는 비용이다**.

    조항: *「단일계약+관리주체 경유」* (`FR-205-AC1`). 편익은
    `SelfConsumption`(기존 요금 − 신규 요금)이고, 그 두 요금은 **요금엔진이 누진·
    TOU 를 풀어서 내는 값**이라 대장에도 협상값에도 없다 — R31 이 이 구조를
    `NOT_YET_ASSEMBLED` 에 남긴 사유가 그것이었다.

    ## ★ 금액이 아니라 계량점을 받는다

    사용자에게 두 요금을 **금액으로** 받으면 요금엔진을 지나지 않는다. 그러면
    누진 구조가 결과에 반영되지 않고, **그 사실은 어디에도 나타나지 않는다** —
    숫자는 그럴듯하고 「요금엔진 통합」은 이름만 남는다. 단일계약의 요점이
    *「세대별 누진을 관리주체 하나로 묶어 낮춘다」* 인데, 누진을 풀지 않으면 그
    구조의 이득 자체가 계산에서 사라진다.

    ## ★★ 두 계량점 구성의 **계량점 집합이 같아야 한다**

    다르면 「설비 전후」가 아니라 **서로 다른 사업장 둘**을 비교한 것이다. 세대
    하나를 빼먹은 신규 구성은 그 세대의 요금만큼 절감으로 잡히고, 그것은 설비가
    낸 절감이 아니다. 이 어긋남은 금액만 보면 정상 범위 안에 있다.

    ## 수수료(`Q-14`)는 **비용 행**으로 나간다

    `SelfConsumption` 에 차감항을 넣지 않는다 — 편익에서 빼면 관점별 NPV 에서 그
    지출이 사라지고 B/C 분모도 줄어 사업이 유리해진다
    (`core/cba/proforma.py::fee_row`).

    기준은 **신규(설비 후) 세대 배분 요금**이다. 관리주체가 해마다 실제로 배분하는
    금액이 그것이므로 수수료의 모수도 그것이다. ⚠ **잠정 판단이며 관리규약
    표본이 오면 바뀔 수 있다**(`docs/decisions-2026-08-14-R32.md` §2) — 기존 요금을
    모수로 두면 설비를 넣을수록 수수료율이 실효적으로 커지는데, 그 방향이 옳은지는
    규약이 정한다.
    """
    structure = "단일계약+관리주체 경유"
    if engine is None:
        raise ValidationError(
            field="model.contract.tariff_engine",
            reason=(
                f"«{structure}» 정산은 요금엔진이 필요합니다 — 이 구조의 편익은 "
                "「기존 요금 빼기 신규 요금」이고 그 두 요금은 누진·TOU 를 풀어야 "
                "나옵니다"
            ),
            action=(
                "요금표 카탈로그로 `TariffEngine` 을 만들어 넘기십시오. "
                "**요금을 금액으로 받지 않습니다** — 받으면 누진 구조가 결과에 "
                "반영되지 않고 그 사실이 어디에도 나타나지 않습니다"
            ),
        )
    if not inputs.baseline_meters or not inputs.new_meters:
        raise ValidationError(
            field="model.contract.settlement_inputs",
            reason=(
                f"«{structure}» 정산에 계량점 구성이 없습니다: "
                f"baseline_meters {len(inputs.baseline_meters)}개 · "
                f"new_meters {len(inputs.new_meters)}개"
            ),
            action=(
                "설비 전·후 계량점을 각각 주십시오. 한쪽이 비면 그쪽 요금이 0 이 "
                "되어 **요금 전액이 절감으로** 잡히거나 절감이 음수가 됩니다"
            ),
        )
    if inputs.billing_date is None:
        raise ValidationError(
            field="model.contract.settlement_inputs",
            reason=f"«{structure}» 정산에 요금 산정 기준일(billing_date)이 없습니다",
            action=(
                "시나리오의 기준일을 주십시오. **오늘 날짜로 떨어뜨리지 않습니다** "
                "— 같은 시나리오가 실행한 날에 따라 다른 요금표를 타게 되고"
                "(`DV-6`), 그 차이는 아무 예외도 내지 않습니다"
            ),
        )

    baseline_ids = [meter.meter_id for meter in inputs.baseline_meters]
    new_ids = [meter.meter_id for meter in inputs.new_meters]
    if sorted(baseline_ids) != sorted(new_ids):
        raise ValidationError(
            field="model.contract.settlement_inputs",
            reason=(
                f"«{structure}» 의 설비 전·후 계량점이 서로 다릅니다: "
                f"전 {sorted(baseline_ids)} · 후 {sorted(new_ids)}"
            ),
            action=(
                "같은 계량점 구성으로 전·후를 주십시오. 다르면 「설비 전후」가 "
                "아니라 서로 다른 사업장 둘을 비교한 것이며, 빠진 계량점의 요금이 "
                "설비가 낸 절감으로 잡힙니다"
            ),
        )

    baseline_bill = engine.bill_scenario(
        inputs.baseline_meters, when=inputs.billing_date
    ).total
    new_bill = engine.bill_scenario(inputs.new_meters, when=inputs.billing_date).total
    fee_fraction = pct_to_fraction(provider.require_float(MANAGER_FEE_KEY))

    return SettlementPlan(
        structure=structure,
        streams=(
            SelfConsumption(
                baseline_annual_bill_won=float(baseline_bill),
                new_annual_bill_won=float(new_bill),
                structure=structure,
            ),
        ),
        assumption_keys=(MANAGER_FEE_KEY,),
        costs=(
            SettlementCost(
                tag="ManagerEntityFee",
                label="관리주체 경유 수수료",
                annual_amount_won=to_won(float(new_bill) * fee_fraction),
            ),
        ),
    )


#: 구조 → 조립기. **선언표이고 `if structure == …` 가 아니다** —
#: 여덟 번째 구조가 생기면 여기 한 줄이 늘고 나머지 코드는 바뀌지 않는다
#: (`payer_by_structure` 를 선언표로 둔 것과 같은 근거).
ASSEMBLERS: Mapping[str, _Assembler] = MappingProxyType({
    "상계거래": _net_metering,
    "잉여 직거래": _surplus_direct_sale,
    "분산특구 직접거래": _distributed_direct_trade,
    "단일계약+관리주체 경유": _single_contract_via_manager,
    "개별 세대 직접계약": _household_direct_contract,
    "집합 PPA": _aggregated_ppa,
})

#: 아직 조립기가 없는 구조 → **왜 없는가**. 사유가 산출물이다 (결정 §2-3·§2-5).
#:
#: **빈 목록을 돌려주지 않기 위해 존재한다.** 조용히 편익 0 을 내면 사용자는
#: 미구현과 「정말 편익이 없다」를 구별할 수 없다.
#:
#: ★ **R31 이 이 표의 사유를 한 번 고쳐 썼다.** 초판은 넷 다 「대장에 값이 없다」로
#: 적었는데, `Q-14`~`Q-16` 을 등재하고 보니 **값이 막고 있던 것은 하나뿐**이었다
#: (「잉여 직거래」 — 지금 조립된다). 나머지 셋은 값이 아니라 **구조가 요구하는
#: 자료형이나 조항 자체**가 막고 있다. 사유를 낡은 채 두면 다음 사람이 값을
#: 등재하고 「이제 되겠다」고 착수한 뒤에야 그것을 알게 된다.
NOT_YET_ASSEMBLED: Mapping[str, str] = MappingProxyType({
    "VPP 경유": (
        "값 문제가 아니라 **Phase 불일치**였습니다 — `FR-401-AC2.VPPMarket`(VPP "
        "시장참여 수익)은 v0.1부터 `[Phase 2]` 인데 `FR-205`(VPP 경유 포함)는 Phase 1 "
        "Must-have 입니다. **아직 조항 쪽은 그대로입니다** — `FR-205-AC1` 이 일곱을 "
        "한 수용기준에 열거하므로 VPP 만 옮기려면 `FR-801-AC7` 처럼 AC 를 쪼개야 하고 "
        "수용기준 총수가 바뀝니다. spec §16.5 개정 대상으로 등재했습니다"
    ),
})


def assemble(
    structure: str,
    *,
    provider: AssumptionProvider,
    inputs: SettlementInputs | None = None,
    tariff_engine: TariffEngine | None = None,
) -> SettlementPlan:
    """계약구조가 켜는 편익을 조립한다 — `FR-205-AC1`.

    ## 자기 검사 — 조립 결과가 배타 규칙을 지나야 한다

    조립한 편익 목록을 `assert_no_exclusions()` 에 그대로 넘긴다. 선언표에
    유형 A 조합을 적으면 **조립 시점에 거부된다** — 그러지 않으면 규칙표는
    정본인데 조립기가 그것을 어기는 상태가 만들어지고, 그 조합은 케이스
    실행까지 내려가서야 잡힌다(그때는 이미 자원·디스패치가 한 번 돈 뒤다).
    """
    if structure not in CONTRACT_STRUCTURES:
        raise ValidationError(
            field="model.contract.structure",
            reason=(
                f"지원하지 않는 계약·거래 구조입니다: {structure!r}. "
                f"spec FR-205-AC1 이 열거한 일곱: {', '.join(CONTRACT_STRUCTURES)}"
            ),
            action=(
                "열거된 구조 이름을 **문면 그대로** 주십시오. 비슷한 이름은 "
                "거부되는 편이 낫습니다 — 통과시키면 그 구조가 편익의 "
                "`payer_by_structure` 어느 키와도 맞지 않아 지불 주체가 "
                "기본값으로 조용히 떨어집니다"
            ),
        )

    assembler = ASSEMBLERS.get(structure)
    if assembler is None:
        raise ValidationError(
            field="model.contract.structure",
            reason=f"«{structure}» 의 정산 조립 규칙이 아직 없습니다. "
                   + NOT_YET_ASSEMBLED[structure],
            action=(
                "조립 규칙이 선 구조로 분석하거나, 위 사유가 가리키는 선행 "
                "작업을 먼저 하십시오. **빈 편익 목록으로 진행하지 않습니다** — "
                "편익 0 인 결과는 미구현과 구별되지 않습니다"
            ),
        )

    plan = assembler(provider, inputs or SettlementInputs(), tariff_engine)
    # ★ 자기 검사 — 선언표가 규칙표를 어기지 않는지 조립 시점에 본다
    assert_no_exclusions(list(plan.streams))
    return plan
