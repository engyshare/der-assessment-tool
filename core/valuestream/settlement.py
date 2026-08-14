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

넷은 아직 조립되지 않는다. 조용히 빈 목록을 돌려주면 **편익 0 인 사업**이
그럴듯하게 나오고, 사용자는 그 구조가 미구현인지 정말 편익이 없는지 구별할 수
없다. `NOT_YET_ASSEMBLED` 가 **구조마다 무엇이 막고 있는지**를 들고 거부한다.

⚠ **그 사유를 R31 이 한 번 고쳐 썼다.** 초판은 넷 다 「대장에 값이 없다」로
적었는데, `Q-14`~`Q-16` 을 등재하고 보니 **값이 막고 있던 것은 하나뿐**이었다
(「잉여 직거래」 — 지금 조립된다). 나머지 셋은 값이 아니라 **정산 대상 미정 ·
요금엔진 통합 · 없는 편익 클래스**가 막고 있다. 사유를 낡은 채 두면 다음 사람이
값을 등재하고 「이제 되겠다」고 착수한 뒤에야 그것을 알게 된다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from core.contracts.assumptions import AssumptionProvider
from core.contracts.validation import ValidationError
from core.contracts.valuestream import CONTRACT_STRUCTURES, ValueStream
from core.valuestream.direct_trade import DirectTrade
from core.valuestream.exclusion_table import assert_no_exclusions
from core.valuestream.surplus_sale import SurplusSale

#: 약관요금(실효단가) — 상계 차감단가이자 직접거래 차익의 기준가.
#: Q-6 가정이며 `TU-6`(계량점 구성 확인) 해소 시 교체된다.
TARIFF_KEY = "tariff.hv_single_contract.avg"

#: 거래지원수수료 단가(원/kWh) — Q-7. 하단 0(면제 케이스)을 겸한다.
TRADE_FEE_KEY = "fee.direct_trade_support"

#: 잉여 직거래 판매단가(원/kWh) — Q-16. **약관요금보다 낮다**(도매 정산단가 계열).
SURPLUS_SALE_KEY = "tariff.surplus_direct_sale"


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


_Assembler = Callable[[AssumptionProvider, SettlementInputs], SettlementPlan]


def _net_metering(
    provider: AssumptionProvider, inputs: SettlementInputs
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
    provider: AssumptionProvider, inputs: SettlementInputs
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
    provider: AssumptionProvider, inputs: SettlementInputs
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


#: 구조 → 조립기. **선언표이고 `if structure == …` 가 아니다** —
#: 여덟 번째 구조가 생기면 여기 한 줄이 늘고 나머지 코드는 바뀌지 않는다
#: (`payer_by_structure` 를 선언표로 둔 것과 같은 근거).
ASSEMBLERS: Mapping[str, _Assembler] = MappingProxyType({
    "상계거래": _net_metering,
    "잉여 직거래": _surplus_direct_sale,
    "분산특구 직접거래": _distributed_direct_trade,
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
    "개별 세대 직접계약": (
        "값이 아니라 **정산 대상이 정해지지 않았습니다.** 조항은 「가구가 구매자와 "
        "직접 계약」만 적고, 정산 대상이 잉여 순액인지 자가소비 절감인지 spec 에 "
        "없습니다 — 둘은 배타 규칙표에서 유형 A 로 서로를 배제하므로 하나를 골라야 "
        "하고, 그 선택이 편익을 통째로 바꿉니다. 계약단가는 협상값이므로 "
        "`SettlementInputs` 로 받으면 되고 대장 등재 대상이 아닙니다"
    ),
    "단일계약+관리주체 경유": (
        "값은 갖췄습니다(단가 `tariff.hv_single_contract.avg` Q-6 · 수수료 "
        "`fee.manager_entity` Q-14). 남은 것은 **요금엔진 통합**입니다 — 이 구조의 "
        "편익은 `SelfConsumption`(기존 요금 빼기 신규 요금)이고 그 두 요금은 요금엔진"
        "(WP-3)이 누진·TOU 를 풀어서 내는 값이라 대장에도 협상값에도 없습니다. "
        "**그리고 수수료를 실을 자리가 없습니다** — `SelfConsumption` 에 차감항이 "
        "없고, 수수료는 편익이 아니라 비용이므로 비용 행으로 놓아야 합니다"
    ),
    "집합 PPA": (
        "값은 갖췄습니다(`tariff.aggregated_ppa.ratio` Q-15). 남은 것은 **편익 "
        "클래스**입니다 — PPA 는 잉여판매가 아니라 발전량 전량의 일괄 판매이고, "
        "`SurplusSale` 은 계통 역송분(잉여)만 봅니다. 잉여판매로 대신하면 자가소비분이 "
        "빠져 편익이 조용히 작아집니다. `FR-401-AC2` 에 대응 편익이 없으므로 spec "
        "개정이 함께 붙습니다"
    ),
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

    plan = assembler(provider, inputs or SettlementInputs())
    # ★ 자기 검사 — 선언표가 규칙표를 어기지 않는지 조립 시점에 본다
    assert_no_exclusions(list(plan.streams))
    return plan
