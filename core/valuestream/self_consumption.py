"""자가소비 전기요금 절감 — FR-401-AC2.SelfConsumption.

산식: (기존요금 − 신규요금). 누진·TOU 구조는 요금 엔진(WP-3)이 해석하며,
여기서는 그 결과를 받아 증분만 계상한다 (도메인 원칙 1-1).

**오라클**: 이 산식 자체가 닫힌 형태(순위 1, 해석해)다 — 뺄셈 한 번이므로
손계산으로 완전 재현 가능. 요금 엔진의 내부(누진 구간 해석 등)는 별도 검증.
"""
from __future__ import annotations

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.valuestream import ExclusionType, Payer, ValueStream


class SelfConsumption(ValueStream):
    """자가소비 절감 — 기존 요금에서 신규 요금을 뺀 증분.

    `baseline_annual_bill_won` 은 «설비 없을 때의 연간 요금» 이고
    `new_annual_bill_won` 은 «설비 설치 후 연간 요금» 이다. 둘 다 요금 엔진이
    누진·TOU 를 풀어서 낸 값이며, 여기서는 그 값을 그대로 받는다 (5.0 선행).
    """

    tag = "SelfConsumption"
    #: 생성자의 **연간** 요금 두 값의 차다 — 디스패치를 보지 않는다.
    scales_with_dispatch_window = False
    payer = Payer.RESIDENT

    def __init__(
        self,
        *,
        baseline_annual_bill_won: float,
        new_annual_bill_won: float,
        enabled: bool = True,
        structure: str | None = None,
    ) -> None:
        super().__init__(
            name="자가소비 전기요금 절감", enabled=enabled, structure=structure
        )
        self._baseline = baseline_annual_bill_won
        self._new = new_annual_bill_won

    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        if not self.enabled:
            return to_won(0)
        # 절감 = 기존 − 신규. 신규가 더 크면 음수(비용 증가)도 허용 —
        # 편익이 아닌 것을 «0» 으로 가두면 역방향 케이스가 숨는다.
        saving = self._baseline - self._new
        return to_won(saving)

    def formula(self, dispatch: DispatchResult, *, year: int) -> str:
        """기존 요금 − 신규 요금 — `ValueStream.formula` 계약.

        ★ **차를 그대로 적는다.** 절감액만 적으면 「요금이 얼마에서 얼마로
        내렸는가」가 사라지고, 그 두 값은 요금 엔진이 낸 것이라 이 편익이
        아니라 **그쪽을 확인해야** 검산이 된다.
        """
        return (
            f"기존 연간 요금 {self._baseline:,.0f}원 "
            f"− 신규 연간 요금 {self._new:,.0f}원"  # noqa: RUF001
        )

    def exclusions(self) -> list[tuple[str, ExclusionType, str]]:
        # 자가소비한 kWh 는 잉여판매(SurplusSale)와 동일 물리량을 공유 — 유형 A.
        # 동일 kWh 를 두 곳에 쓸 수 없으므로 배타 규칙으로 등록 (FR-402-AC2.A).
        return [(
            "SurplusSale",
            ExclusionType.A,
            "자가소비한 kWh 는 잉여가 아님 — 동일 물리량 이중 판매 (유형 A)",
        )]
