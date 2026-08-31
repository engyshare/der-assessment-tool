"""용량정산금 — FR-401-AC2.CP.

산식: **등록 용량(kW) × 용량정산금 단가(원/kW·월) × 12개월**.

## 왜 이 항목이 필요했나 (R48 §4)

`ESS.value_streams()` 가 계통 방전분을 받을 항목을 선언하지 않아 **ESS 가
내보낸 몫이 태양광 잉여판매 행에 얹혀** 있었다. `NWAs` 와 함께 그 자리를
만든다. 판정 정본은 `docs/decisions-2026-08-31-R48.md` §4·§6 이다.

**오라클**: 순위 1 (해석해) — 곱 두 번이므로 손계산 재현 가능.
"""
from __future__ import annotations

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.valuestream import ExclusionType, Payer, ValueStream

#: 활성화 시 리포트 상단에 뜨는 문구 (FR-404-AC1 과 같은 형식).
#:
#: ⚠ **`NWAs.POLICY_WARNING` 과 뭉뚱그리지 않는다** (R48 §6). `NWAs` 는 **제도
#: 자체가 없고**(설계 중), `CP` 는 **현행 제도이되 분산특구 내 ESS 에 적용할
#: 산정 기준이 없다** — CP 는 **등록 발전기 기준**으로 설정돼 있다. 하나는 제도
#: **신설**을, 다른 하나는 산정 기준 **보완**을 요구하므로 심의회에서 **다른
#: 답을 요구한다.**
POLICY_WARNING = (
    "용량정산금(CP)을 활성화했습니다 — **제도 보완 필요**: CP 는 현행 제도이나 "
    "분산특구 내 ESS 에 적용할 산정 기준이 부재하고, 현행 CP 는 등록 발전기 "
    "기준으로 설정돼 있습니다 (R48 판정 §6). 산정 기준이 보완되어야 성립하는 "
    "편익이므로 본편익과 분리해 표시하고, 회수기간은 CP 포함/제외 두 값으로 "
    "병기해야 합니다"
)


class CapacityPayment(ValueStream):
    """용량정산금 — 등록 용량 × 용량정산금 단가 × 12개월.

    `registered_capacity_kw` 는 준중앙급전 자원으로 **등록한 용량(kW)** 이고
    `capacity_price_won_per_kw_month` 는 용량정산금 단가(원/kW·월)다.

    ## ⚠ 기본값이 다른 편익과 **반대다** (`enabled=False`)

    다른 편익은 `enabled=True` 로 서는데 이 편익만 **기본 비활성**이다. 이유는
    `NWAs` 와 **다르다** — CP 는 **현행 제도이지만 이 사업에 적용할 산정 기준이
    없다**(R48 §6 — *「분산특구 내 ESS에 대해서 CP 산정 기준이 부재. CP는 등록
    발전기 기준으로 설정되어 있음」*). 기준이 없으면 단가를 고를 수 없고, 고른
    단가로 편익을 쌓으면 **필요 지원액을 과소 산정**하게 된다. 비활성일 때
    `annual_value()` 는 `to_won(0)` 이다.

    ## ⚠ 단가를 대장(`docs/assumptions.yaml`)에 등재하지 않는다

    `NFR-202` 에 따라 단가는 클래스에 박지 않고 **생성자 인자로 받는다.**
    그러나 대장에도 넣지 않는다 — **적용할 산정 기준이 없어서 값이 없기**
    때문이다. 값 없는 항목을 대장에 넣으면 「가정한 제도」가 되고, 기본 비활성
    이므로 **실행에 단가가 필요하지 않다.** 산정 기준이 보완되면 그때 등재한다.

    ## ⚠⚠ `payer` 가 **정확하지 않다** — 감추지 않고 적어 둔다

    `Payer.GRID_OPERATOR` 의 값은 **「배전사업자」** 인데 **CP 정산은 전력시장
    쪽**이다. 열거가 그 둘을 아직 구분하지 않으므로 이 값은 **근사**이며,
    관점별 귀속(FR-704)에서 배전사업자 부담으로 잡힌다. `Payer` 열거는 계약
    (`core/contracts/valuestream.py`)이고 그 변경은 spec §16.2 절차를 타야
    하므로 여기서 늘리지 않는다 — **다음 계약 개정 안건이다.** `payer` 를
    비우면 활성화 시 `ValidationError`(DV-13)로 거부되므로 비워 둘 수도 없다.
    """

    tag = "CP"
    #: 생성자의 **등록 용량**으로 계산한다 — 디스패치를 보지 않는다.
    scales_with_dispatch_window = False
    payer = Payer.GRID_OPERATOR

    MONTHS = 12

    def __init__(
        self,
        *,
        registered_capacity_kw: float,
        capacity_price_won_per_kw_month: float,
        enabled: bool = False,
    ) -> None:
        super().__init__(name="용량정산금", enabled=enabled)
        if registered_capacity_kw < 0:
            raise ValueError(
                f"등록 용량은 음수일 수 없습니다: {registered_capacity_kw}"
            )
        if capacity_price_won_per_kw_month < 0:
            raise ValueError(
                "용량정산금 단가는 음수일 수 없습니다: "
                f"{capacity_price_won_per_kw_month}. 음수 단가는 정산이 아니라 "
                "지불이며, 입력 부호가 바뀐 것인지 확인하십시오"
            )
        self._capacity_kw = registered_capacity_kw
        self._price = capacity_price_won_per_kw_month

    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        if not self.enabled:
            return to_won(0)
        return to_won(self._capacity_kw * self._price * self.MONTHS)

    def formula(self, dispatch: DispatchResult, *, year: int) -> str:
        """등록 용량 × 단가 × 12개월 — `ValueStream.formula` 계약.

        ⚠ **`× 12개월` 을 적는 것이 맞다.** `PeakShaving` 은 반대로 적지 말라고
        하는데, 거기서는 수량이 이미 **12개월 치의 합**(`kW·월`)이라 12를 한 번
        더 곱해 읽히기 때문이다. 여기 수량은 **용량(kW) 한 값**이고 단가가
        `원/kW·월` 이므로 **월수는 산식의 일부**다 — 빼면 검토자가 연액을
        월액으로 읽는다.

        ⚠ 이 12는 `scales_with_dispatch_window` 가 붙이는 **연간화(`× 365일`)와
        다르다.** 이 편익은 창을 읽지 않으므로 호출측이 곱하는 것이 없다.
        """
        return (
            f"등록 용량 {self._capacity_kw:,.2f}kW "
            f"× 용량정산금 단가 {self._price:,.0f}원/kW·월 "  # noqa: RUF001
            f"× {self.MONTHS}개월"  # noqa: RUF001
        )

    def exclusions(self) -> list[tuple[str, ExclusionType, str]]:
        """사용자 운전 편익과 **유형 E** 배타 (FR-402-AC2.E · R48 §2).

        준중앙급전으로 등록하면 방전 시점을 계통운영자가 정한다 — 사용자가
        원하는 시각에 방전할 수 없고 사용자의 전기사용량에 영향이 없다.
        **유형 A 가 아니다**(같은 kWh 를 두 번 파는 것이 아니다). **유형 D 도
        아니다**(제도가 바뀌어도 성립하지 않는다).

        ⚠ 선언은 아무것도 강제하지 않는다. 정본은 `docs/exclusion-rules.yaml`
        이며(FR-402-AC4) 이 선언이 그 표와 어긋나지 못하게
        `tests/contract/test_exclusion_declaration_matches_table.py` 가 붙든다.
        """
        return [
            (
                "SelfConsumption",
                ExclusionType.E,
                "준중앙급전 등록 자원은 방전 시점을 계통운영자가 정하므로 "
                "사용자의 전기사용량에 영향이 없다 — 자가소비가 아니다 (유형 E)",
            ),
            (
                "PeakShaving",
                ExclusionType.E,
                "준중앙급전 등록 자원은 사용자가 원하는 시각에 방전할 수 없다 — "
                "자가 피크 저감이 성립하지 않는다 (유형 E)",
            ),
        ]

    def policy_warnings(self) -> list[str]:
        """활성화했을 때만 경고한다 — 문면은 `POLICY_WARNING` 이 소유한다.

        ⚠ **`ValueStream` 계약이 아직 이 훅을 요구하지 않는다.** `policy_warnings()`
        는 R48 §7 이 `DER` 계약에 올렸고 편익 쪽 계약에는 없다 — 그 승격은
        spec §16.2 절차를 타야 하므로 여기서 하지 않는다. 지금은 **문구를 만들고
        밖에서 읽을 수 있게** 두는 데까지다(리포트 배선도 아직 없다).
        """
        return [POLICY_WARNING] if self.enabled else []
