"""TOU 차익거래 편익 — FR-401-AC2.TouArbitrage.

산식: **연간 방전 kWh × 피크단가 − 연간 충전 kWh × 경부하단가**.
`ESS.tou_arbitrage_benefit()`(`RC-ESS-B1`)과 **같은 산식**이며 같은 수가 나와야
한다 — 사용자가 말한 「충방전요금차이」가 그것이다.

## 왜 이 항목이 필요했나 (R48 §4 · R50)

R48 이 **오매핑을 뗐다.** 종전에는 `ESSOperatingMode.TOU_ARBITRAGE` 가
`SelfConsumption` 을 냈는데, TOU 차익거래는 **계통에 파는 운전**이므로 자가소비
편익이 붙을 자리가 아니었다. 떼면서 **그 자리를 비워 두었고**, 그래서
`ESS.value_streams()` 가 이 모드에서 **빈 튜플**을 돌려주고 `RC-ESS-B1` 산식은
**호출자가 단위시험 하나뿐**이었다.

**「TOU 차익거래는 편익이 없다」가 아니었다 — 받을 항목이 없었던 것이다.**
이 파일이 그 자리를 만든다. 판정 정본은 `docs/decisions-2026-08-31-R48.md` §4
(산정식 표의 「⚠⚠ 차익거래 편익 함수가 호출자 0곳이다」)다.

**오라클**: 순위 1 (해석해) — 곱 둘의 차이라 손계산으로 재현 가능하며,
`ESS.tou_arbitrage_benefit()` 과 **대조**할 수 있다.
"""
from __future__ import annotations

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won, won_sum
from core.contracts.valuestream import ExclusionType, Payer, ValueStream


class TouArbitrage(ValueStream):
    """TOU 차익거래 — 방전 kWh × 피크단가 − 충전 kWh × 경부하단가.

    `discharge_kwh`·`charge_kwh` 는 **연간** 수량(kWh)이고 단가는 원/kWh 다.

    ## ⚠⚠ 수량을 **생성자로 받는다** — 창에서 다시 읽지 않는다

    `scales_with_dispatch_window = False` 이며 `PeakShaving` 과 같은 형태다.
    `ESS.tou_arbitrage_benefit()` 이 이미 `ESS.annual_discharge_kwh()` /
    `ESS.annual_charge_kwh()` 로 **연간값**을 쓴다 — 창에서 다시 읽으면 같은
    수량에 자가 둘이 되고, 러너의 연간화(`core/casegrid/operating_lines.py` 의
    `annualise`)가 365를 곱해 **365배**가 된다. 그 실측이 이미 있다: 집합 PPA
    502,605원/년이 183,450,825원으로 실린 R34 자리다
    (`ValueStream.scales_with_dispatch_window` 주석).

    ## ⚠ `ESS.tou_arbitrage_benefit()` 을 부르지 않는다 — 구획 경계다

    `core.valuestream` 이 `core.der` 를 import 하면 구획 경계를 넘는다
    (`NFR-208-AC1` · `lint-imports` 가 잡는다). `PeakShaving` ↔
    `ESS.peak_shaving_benefit()` 이 **이미 같은 관계**이며 그것이 이 저장소의
    선례다 — 자원 쪽 메서드는 `RC-ESS-B*` 오라클이고 편익 클래스는 프로포마
    행이다. **두 산식이 갈리지 못하게 붙드는 것은 시험**이며
    (`tests/valuestream/test_tou_arbitrage.py`) 그 시험이 두 값을 대조한다.

    ## ⚠ `payer` 는 `Payer.OPERATOR` 다

    사업자가 계통·시장에 파는 편익이므로 `SurplusSale`·`AggregatedPPA`·
    `DirectTrade` 와 같은 자리다. **`Payer` 열거를 늘리지 않는다** — 계약
    (`core/contracts/valuestream.py`)이고 그 변경은 spec §16.2 절차 대상이다.

    ## ⚠ 값이 **음수일 수 있다** — 막지 않는다

    충전 비용이 방전 수익을 넘으면 편익이 음수다. 그것이 이 편익의 실제 성질
    이므로 0으로 클램프하지 않는다 — 클램프하면 「차익이 나지 않는 요금 구조」가
    「편익 0」으로 보이고, 검토자는 그 운전을 **손해 없는 선택**으로 읽는다.
    """

    tag = "TouArbitrage"
    #: 생성자의 **연간** 수량으로 계산한다 — 이미 연간값이므로 곱하면 365배다.
    scales_with_dispatch_window = False
    payer = Payer.OPERATOR

    def __init__(
        self,
        *,
        discharge_kwh: float,
        charge_kwh: float,
        peak_price_won_per_kwh: float,
        offpeak_price_won_per_kwh: float,
        enabled: bool = True,
        quantity_id: str | None = None,
    ) -> None:
        # ★ 표찰의 임자는 몫이며 편익 종류가 아니다
        # (core/casegrid/ess_share.py::ESSShare.quantity_id).
        super().__init__(name="TOU 차익거래", enabled=enabled, quantity_id=quantity_id)
        # ⚠ 수량은 **크기**로 받는다 — 방전·충전 둘 다 양수다. 부호로 방향을
        # 나르게 두면 산식의 뺄셈과 부호가 겹쳐 이중 부정이 되고, 그때 금액은
        # 그럴듯한 양수로 남는다.
        if discharge_kwh < 0:
            raise ValueError(
                f"연간 방전량은 음수일 수 없습니다: {discharge_kwh}. 방전·충전은 "
                "둘 다 크기로 받으며 방향은 산식이 나릅니다"
            )
        if charge_kwh < 0:
            raise ValueError(
                f"연간 충전량은 음수일 수 없습니다: {charge_kwh}. 방전·충전은 "
                "둘 다 크기로 받으며 방향은 산식이 나릅니다"
            )
        if peak_price_won_per_kwh < 0:
            raise ValueError(
                f"피크단가는 음수일 수 없습니다: {peak_price_won_per_kwh}. "
                "음수 단가는 판매가 아니라 지불이며, 입력 부호가 바뀐 것인지 "
                "확인하십시오"
            )
        if offpeak_price_won_per_kwh < 0:
            raise ValueError(
                f"경부하단가는 음수일 수 없습니다: {offpeak_price_won_per_kwh}. "
                "음수 단가는 매입이 아니라 수취이며, 입력 부호가 바뀐 것인지 "
                "확인하십시오"
            )
        self._discharge_kwh = discharge_kwh
        self._charge_kwh = charge_kwh
        self._peak_price = peak_price_won_per_kwh
        self._offpeak_price = offpeak_price_won_per_kwh

    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        """`won_sum` 을 쓴다 — `NFR-103-M1`.

        ⚠ **`to_won(a - b)` 로 한 번에 하지 않는다.** 항별로 반올림한 뒤 더해야
        프로포마의 행별 값과 총계가 맞고, `ESS.tou_arbitrage_benefit()` 과도
        같은 수가 난다. 한 번에 하면 1원 어긋나는 자리가 생기고 그 1원은
        「검토자가 손으로 더한 값과 표가 다르다」로 나타난다.
        """
        if not self.enabled:
            return to_won(0)
        return won_sum(
            (
                self._discharge_kwh * self._peak_price,
                -self._charge_kwh * self._offpeak_price,
            )
        )

    def formula(self, dispatch: DispatchResult, *, year: int) -> str:
        """방전 × 피크단가 − 충전 × 경부하단가 — `ValueStream.formula` 계약.

        ⚠ **뺄셈을 산식에 남긴다.** 차액만 적으면 「무엇에서 무엇을 뺐는가」가
        사라지고, 값이 음수일 때 검토자가 그것을 오류로 읽는다.
        """
        return (
            f"방전 {self._discharge_kwh:,.2f}kWh "
            f"× 피크단가 {self._peak_price:,.0f}원/kWh "  # noqa: RUF001
            f"− 충전 {self._charge_kwh:,.2f}kWh "  # noqa: RUF001
            f"× 경부하단가 {self._offpeak_price:,.0f}원/kWh"  # noqa: RUF001
        )

    def exclusions(self) -> list[tuple[str, ExclusionType, str]]:
        """더는 `SurplusSale` 과 배타가 아니다 (R51/WP-5 · 사용자 판정 §4).

        R50 은 여기서 `SurplusSale` 과 유형 `A`(동일 물리량 이중 판매)를
        선언했다 — TOU 차익거래는 계통으로 방전하고 `SurplusSale` 은 시스템
        총 역송량으로 계산되므로 같은 kWh 가 두 항목에 각각 판매로 들어간다는
        근거였다(R48 §4). **방향은 맞았지만 답이 틀렸다.**

        사용자 판정 §4(`docs/decisions-2026-09-01-R51.md`)는 그것을 *「두 번
        센 것」*이 아니라 *「같은 전력이 길을 돌아간 것」*으로 다시 읽는다 —
        ESS 의 충전원이 태양광 잉여면 그 방전분은 태양광 판매로 세는 것이
        맞고, 계통이면 세면 안 된다. **답은 배타(둘 중 하나를 끄라)가 아니라
        `SurplusSale` 의 수량에서 그 몫을 빼는 것**이다 — `core/valuestream/
        surplus_sale.py::SurplusSale` 의 `non_pv_ess_discharge_kwh` 인자.
        배타로 남겨 두면 ESS 는 계통 충전으로 차익거래를 하고 태양광 잉여는
        따로 파는 **정당한 동시 운전**을 지운다.

        ## ⚠⚠ `SelfConsumption`·`PeakShaving` 과도 **배타가 아니다**

        셋 다 **운전 주체가 사업자**이고 `ESS.mode_weights` 가 혼합 모드를
        **명시로 허용**한다. 배타로 적으면 **정당한 동시 계상을 지운다** —
        `FR-402-AC1`(동시 발생하는 다중 효과는 중복이 아니다)이 명시로 금지한
        방향이다.

        ⚠ 선언은 아무것도 강제하지 않는다. 정본은 `docs/exclusion-rules.yaml`
        이며(FR-402-AC4) 이 선언이 그 표와 어긋나지 못하게
        `tests/contract/test_exclusion_declaration_matches_table.py` 가 붙든다
        — 그래서 정본에서 뗀 규칙은 여기서도 함께 뗀다(안 떼면 「선언은
        하는데 표에는 없다」로 그 검사가 잡는다).
        """
        return []
