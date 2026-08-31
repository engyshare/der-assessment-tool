"""계통 기여 보상 (비망대안) — FR-401-AC2.NWAs.

산식: **계통으로 방전한 kWh × 계통 기여 보상 단가(원/kWh)**.

## 왜 이 항목이 필요했나 (R48 §4)

`ESS.value_streams()` 가 계통 방전분을 받을 항목을 선언하지 않는데
`SurplusSale` 은 **시스템 총 역송량**으로 계산된다 — 그래서 **ESS 가 내보낸
몫이 태양광 잉여판매 행에 얹혀** 있었다. 두 번 센 것이 아니라 **받을 자리가
없어서 남의 자리에 얹힌 것**이며, 이 항목이 그 자리를 만든다. 판정 정본은
`docs/decisions-2026-08-31-R48.md` §4 다.

**오라클**: 순위 1 (해석해) — 총량 × 단가의 곱으로 손계산 재현 가능.
"""
from __future__ import annotations

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.valuestream import ExclusionType, Payer, ValueStream

#: 활성화 시 리포트 상단에 뜨는 문구 (FR-404-AC1 과 같은 형식).
#:
#: ⚠ **`CapacityPayment.POLICY_WARNING` 과 뭉뚱그리지 않는다** (R48 §6). 여기서
#: 없는 것은 **제도 자체**이고 저기서 없는 것은 **이 사업에 적용할 산정 기준**
#: 이다 — 하나는 제도 **신설**을, 다른 하나는 산정 기준 **보완**을 요구하므로
#: 심의회에서 **다른 답을 요구한다.** 한 문구로 뭉치면 답할 수 없는 것을 물은
#: 것이 된다.
POLICY_WARNING = (
    "계통 기여 보상(NWAs)을 활성화했습니다 — **제도 필요**: 이 보상은 현행 "
    "제도가 아니며 현재 설계 중입니다 (R48 판정 §6). 제도가 신설되어야 성립하는 "
    "편익이므로 본편익과 분리해 표시하고, 회수기간은 NWAs 포함/제외 두 값으로 "
    "병기해야 합니다"
)


class NWAs(ValueStream):
    """계통 기여 보상 — 계통으로 방전한 kWh × 계통 기여 보상 단가.

    ## ⚠ 기본값이 다른 편익과 **반대다** (`enabled=False`)

    다른 편익은 `enabled=True` 로 서는데 이 편익만 **기본 비활성**이다. 이유는
    **제도 자체가 없기 때문**이다(R48 §6 — *「NWAs는 현행이 아님. 현재 설계중」*).
    제도가 없으면 편익은 작은 것이 아니라 **0** 이며, 보상단가를 추정해 넣으면
    존재하지 않는 제도 위에 편익을 쌓아 **필요 지원액을 과소 산정**하게 된다.
    비활성일 때 `annual_value()` 는 `to_won(0)` 이다.

    ## ⚠ 단가를 대장(`docs/assumptions.yaml`)에 등재하지 않는다

    `NFR-202` 에 따라 단가는 클래스에 박지 않고 **생성자 인자로 받는다.**
    그러나 대장에도 넣지 않는다 — **적용할 산정 기준이 없어서 값이 없기**
    때문이다. 값 없는 항목을 대장에 넣으면 「가정한 제도」가 되고, 기본 비활성
    이므로 **실행에 단가가 필요하지 않다.** 제도가 서면 그때 등재한다.

    ## ⚠ `payer` 가 정확하지 않다 — 감추지 않고 적어 둔다

    `Payer.GRID_OPERATOR` 의 값은 **「배전사업자」** 이고, 비망대안(NWA)은
    배전망 증설 회피가 근거이므로 이 자리가 `CapacityPayment` 보다는 가깝다.
    그래도 **정산 주체가 배전사업자로 확정된 것은 아니다** — 제도가 설계 중
    이므로 누가 지불하는지가 아직 정해지지 않았다. `Payer` 열거는 계약
    (`core/contracts/valuestream.py`)이고 그 변경은 spec §16.2 절차를 타야
    하므로 여기서 늘리지 않는다. `payer` 를 비우면 활성화 시
    `ValidationError`(DV-13)로 거부되므로 비워 둘 수도 없다.
    """

    tag = "NWAs"
    #: 창에서 읽는다 — `dispatch.electric` 의 양수 합(계통 방전 kWh)이 수량이다.
    scales_with_dispatch_window = True
    payer = Payer.GRID_OPERATOR

    def __init__(
        self,
        *,
        contribution_price_won_per_kwh: float,
        enabled: bool = False,
    ) -> None:
        super().__init__(name="계통 기여 보상 (비망대안)", enabled=enabled)
        if contribution_price_won_per_kwh < 0:
            raise ValueError(
                "계통 기여 보상 단가는 음수일 수 없습니다: "
                f"{contribution_price_won_per_kwh}. 음수 단가는 보상이 아니라 "
                "지불이며, 입력 부호가 바뀐 것인지 확인하십시오"
            )
        self._price = contribution_price_won_per_kwh

    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        if not self.enabled:
            return to_won(0)
        return to_won(self._grid_discharge_kwh(dispatch) * self._price)

    def formula(self, dispatch: DispatchResult, *, year: int) -> str:
        """계통 방전 × 계통 기여 보상 단가 — `ValueStream.formula` 계약.

        ⚠ **수량을 `annual_value` 와 같은 함수에서 읽는다**(`_grid_discharge_kwh`).
        여기서 클램프를 다시 적으면 사본이 되고, 음수 처리 규칙이 한쪽만 바뀌면
        산식과 금액이 조용히 갈린다.
        """
        return (
            f"계통 방전 {self._grid_discharge_kwh(dispatch):,.2f}kWh "
            f"× 계통 기여 보상 단가 {self._price:,.0f}원/kWh"  # noqa: RUF001
        )

    @staticmethod
    def _grid_discharge_kwh(dispatch: DispatchResult) -> float:
        """계통으로 내보낸 전력 — 음수(수전)는 0으로 클램프."""
        return sum(max(0.0, e) for e in dispatch.electric)

    def exclusions(self) -> list[tuple[str, ExclusionType, str]]:
        """사용자 운전 편익과 **유형 E** 배타 (FR-402-AC2.E · R48 §2).

        방전 시점을 계통운영자가 정하면 사업자가 원하는 시각에 방전할 수 없다.
        **유형 A 가 아니다** — 같은 kWh 를 두 번 파는 것이 아니라 애초에 같은
        운전에 함께 존재할 수 없다. **유형 D 도 아니다** — 제도가 바뀌어도
        성립하지 않는다.

        ⚠ 선언은 아무것도 강제하지 않는다. 정본은 `docs/exclusion-rules.yaml`
        이며(FR-402-AC4) 이 선언이 그 표와 어긋나지 못하게
        `tests/contract/test_exclusion_declaration_matches_table.py` 가 붙든다.
        """
        return [
            (
                "SelfConsumption",
                ExclusionType.E,
                "방전 시점을 계통운영자가 정하므로 사용자의 전기사용량에 영향이 "
                "없다 — 자가소비가 성립하지 않는다 (유형 E)",
            ),
            (
                "PeakShaving",
                ExclusionType.E,
                "방전 시점을 계통운영자가 정하므로 사용자가 원하는 시각에 방전할 "
                "수 없다 — 자가 피크 저감이 성립하지 않는다 (유형 E)",
            ),
        ]

    def policy_warnings(self) -> list[str]:
        """활성화했을 때만 경고한다 — 문면은 `POLICY_WARNING` 이 소유한다.

        ⚠ **`ValueStream` 계약이 아직 이 훅을 요구하지 않는다.** `policy_warnings()`
        는 R48 §7 이 `DER` 계약에 올렸고 편익 쪽 계약(`core/contracts/valuestream.py`)
        에는 없다 — 그 승격은 spec §16.2 절차를 타야 하므로 여기서 하지 않는다.
        지금은 **문구를 만들고 밖에서 읽을 수 있게** 두는 데까지다(리포트 배선도
        아직 없다). `EV_V2G.policy_warnings()` 와 같은 형태로 적어 두어, 계약이
        올라오면 그대로 맞물린다.
        """
        return [POLICY_WARNING] if self.enabled else []
