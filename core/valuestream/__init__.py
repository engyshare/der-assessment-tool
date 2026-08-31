"""core/valuestream — 구획 WP-4.

편익 흐름 6종 + 분산편익 + 배타 규칙 (FR-401·FR-402·FR-404).

편익 1종 = 파일 1개(§16.3). 새 편익을 추가해도 코어 엔진 수정이 일어나지
않는다 (FR-401-AC1). 여기서는 계약(``core.contracts.valuestream``)을 구현만
한다 — 계약 자체는 WP-0 소유.

소유 경로 밖 파일을 건드리지 않는다 (§16.1 W-1).
"""
from __future__ import annotations

from core.valuestream.aggregated_ppa import AggregatedPPA
from core.valuestream.capacity_payment import CapacityPayment
from core.valuestream.direct_trade import DirectTrade
from core.valuestream.distributed_benefit import (
    DistributedBenefit,
    DistributedSubItems,
)
from core.valuestream.heat_cost_saving import HeatCostSaving
from core.valuestream.nwa import NWAs
from core.valuestream.peak_shaving import PeakShaving
from core.valuestream.rec import REC
from core.valuestream.self_consumption import SelfConsumption
from core.valuestream.surplus_sale import SurplusSale

__all__ = (
    "REC",
    "AggregatedPPA",
    "CapacityPayment",
    "DirectTrade",
    "DistributedBenefit",
    "DistributedSubItems",
    "HeatCostSaving",
    "NWAs",
    "PeakShaving",
    "SelfConsumption",
    "SurplusSale",
)
