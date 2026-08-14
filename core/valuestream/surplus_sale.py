"""잉여전력 판매 — FR-401-AC2.SurplusSale.

산식: 잉여량 × 판매단가(직거래/상계/SMP). 잉여는 계통으로 내보낸 전력
(``DispatchResult.electric`` 의 양수 합)이다.

**오라클**: 순위 1 (해석해) — 총량 × 단가의 곱으로 손계산 재현 가능.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import ClassVar

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.valuestream import ExclusionType, Payer, ValueStream


class SurplusSale(ValueStream):
    """잉여전력 판매 — 계통으로 내보낸 양 × 단가.

    판매단가는 판매 경로(직거래·상계·SMP)에 따라 다르다. 단일 단가를
    생성자에서 받고, 여러 경로가 섞이면 인스턴스를 여러 개 둔다 (FR-401-AC1).
    """

    tag = "SurplusSale"
    payer = Payer.OPERATOR
    #: **`docs/domain-rules.md` 관점 분리표의 「계약구조에 따름」 칸을 채운다.**
    #: 그 표는 *잉여판매·직접거래 수익*의 참여 주민 칸을 「계약구조에 따름」으로
    #: 두었고, 기본값(사업자)만으로는 그것을 표현할 수 없었다.
    #:
    #: **상계거래에서 주민인 근거**: 상계(net metering)는 판매가 아니라 **가구
    #: 계량점의 요금 차감**이다. 차감은 그 계량점 명의자에게 귀속되므로 수익이
    #: 사업자를 거치지 않는다. 사업자로 두면 관점별 NPV 에서 주민 편익이
    #: 통째로 사라지고, 그 어긋남은 합계가 맞아 드러나지 않는다.
    #:
    #: **개별 세대 직접계약에서 주민인 근거 (R32)**: 조항이 *「가구가 구매자와
    #: **직접** 계약」* 이라 적으므로 **판매 주체가 가구**다 — 사업자를 거치지
    #: 않는 것이 그 구조의 정의이며, 사업자로 두면 관점별 NPV 에서 주민 수익이
    #: 통째로 사라진다(상계거래와 같은 형태의 오류다). spec `FR-205-AC1` 아래
    #: v0.16 결정을 근거로 하고, **그 결정은 잠정이다**(계약서 실물이 오면 대상이
    #: 넓어질 수 있다 — `docs/decisions-2026-08-14-R32.md` §3).
    #:
    #: ⚠ **나머지 네 구조의 칸은 비어 있다** — 갈래 B·C 이며 단가·수수료
    #: 근거가 `docs/assumptions.yaml` 에 등재된 뒤에 채운다. 지금 채우면
    #: 도메인 규칙 발명이 된다.
    payer_by_structure: ClassVar[MappingProxyType[str, Payer]] = MappingProxyType({
        "상계거래": Payer.RESIDENT,
        "개별 세대 직접계약": Payer.RESIDENT,
    })

    def __init__(
        self,
        *,
        sale_price_won_per_kwh: float,
        enabled: bool = True,
        structure: str | None = None,
    ) -> None:
        super().__init__(name="잉여전력 판매", enabled=enabled, structure=structure)
        if sale_price_won_per_kwh < 0:
            raise ValueError(
                f"판매단가는 음수일 수 없습니다: {sale_price_won_per_kwh}. "
                "음수 단가는 판매가 아닌 지불이며, 입력 부호가 바뀐 것인지 확인하십시오"
            )
        self._price = sale_price_won_per_kwh

    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        if not self.enabled:
            return to_won(0)
        # electric 양수 = 계통으로 내보낸 전력(잉여). 음수(소비)는 0으로 클램프.
        surplus_kwh = sum(max(0.0, e) for e in dispatch.electric)
        return to_won(surplus_kwh * self._price)

    def exclusions(self) -> list[tuple[str, ExclusionType, str]]:
        # 자가소비한 kWh 와 잉여 kWh 는 같은 1 kWh 를 두 용도로 쓸 수 없다 (유형 A).
        return [(
            "SelfConsumption",
            ExclusionType.A,
            "잉여로 판 매 kWh 는 자가소비가 아님 — 동일 물리량 이중 판매 (유형 A)",
        )]
