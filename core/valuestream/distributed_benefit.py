"""분산편익 크레딧 — FR-401-AC2.DistributedBenefit · FR-404.

하위 항목: 송배전 회피 + 손실 감소 + 계통서비스 + 온실가스 + 회복력.

**기본 0** (FR-404-AC1~AC3). 제도 근거가 확인되지 않은 분산편익은 크기를
추정하지 않는다 (spec A-11). 추정하면 «없는 제도 위에 편익을 쌓고» 필요
지원액이 과소 산정된다.

하위 항목 중 송배전 회피·손실 감소는 FR-402 유형 B (인과 하류)에 해당 —
현행 요금에 이미 반영된 부분을 제외한 «미래 증설 회피 증분»만 계상한다
(도메인 원칙 2-1).

**오라클**: 순위 1 (해석해) — 기본 0과 명시적 값의 차이를 단정적으로 검증.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.contracts.der import DispatchResult
from core.contracts.units import ZERO, Money, to_won
from core.contracts.valuestream import ExclusionType, Payer, ValueStream


@dataclass(frozen=True)
class DistributedSubItems:
    """분산편익 하위 항목 — 기본 전부 0.

    각 항목이 0이 아가 위해선 제도 근거(출처)와 화폐화 방법이 확인되어야 한다.
    확인되지 않은 값을 0이 아닌 추정치로 두면 «없는 제도 위에 편익을 쌓는»
    과소 지원 산정의 원인이 된다 (FR-404-AC3, spec A-11).
    """

    transmission_avoidance_won: float = 0.0
    loss_reduction_won: float = 0.0
    grid_service_won: float = 0.0
    ghg_reduction_won: float = 0.0
    resilience_won: float = 0.0


class DistributedBenefit(ValueStream):
    """분산편익 크레딧 — 기본 0, 분리 표시.

    `enabled=True` 여도 하위 항목이 전부 0이면 연간 편익은 0이다. 활성화 자체는
    «정책 가정 편익 — 현행 제도 미반영» 경고를 리포트 상단에 띄우기 위함이다
    (FR-404-AC1).
    """

    tag = "DistributedBenefit"
    payer = Payer.SOCIETY

    def __init__(
        self,
        *,
        sub_items: DistributedSubItems | None = None,
        enabled: bool = True,
        structure: str | None = None,
    ) -> None:
        super().__init__(name="분산편익 크레딧", enabled=enabled, structure=structure)
        self._items = sub_items or DistributedSubItems()

    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        if not self.enabled:
            return ZERO
        total = (
            self._items.transmission_avoidance_won
            + self._items.loss_reduction_won
            + self._items.grid_service_won
            + self._items.ghg_reduction_won
            + self._items.resilience_won
        )
        return to_won(total)

    def is_policy_assumed(self) -> bool:
        """활성화됐고 합계가 0이 아니면 정책 가정 편익 — 리포트 상단 경고 대상.

        활성화됐고 합계 0이면 «제도 미확인» 표시만 하고 경고는 아니다
        (FR-404-AC1 은 «미반영» 경고이므로 값이 있을 때만 의미).
        """
        if not self.enabled:
            return False
        return self.annual_value(DispatchResult.zeros(1), year=1) > ZERO

    def exclusions(self) -> list[tuple[str, ExclusionType, str]]:
        # 송배전 회피·손실 감소는 현행 요금에 이미 반영된 부분이 겹친다 (유형 B).
        # SelfConsumption 의 증분에 일부 포함되므로, «미래 증설 회피 증분만»
        # 계상하지 않으면 이중 계상이다 (도메인 원칙 2-1).
        return [(
            "SelfConsumption",
            ExclusionType.B,
            "송배전 회피·손실 감소는 현행 망이용요금에 이미 반영 — "
            "미래 증설 회피 증분만 계상 (유형 B, 원칙 2-1)",
        )]
