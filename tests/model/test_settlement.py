import pytest

from core.model.schemas import ContractConfig
from core.model.settlement import SettlementEngine


@pytest.mark.req("FR-205")
def test_settlement_structures():
    """FR-205-AC1: 지원하는 거래 구조(7종)가 명세되어야 하고 각 구조별 정산식이 적용되어야 함."""
    engine = SettlementEngine()

    structures = [
        "개별 직접계약",
        "단일계약+관리주체",
        "분산특구 직접거래",
        "상계",
        "잉여 직거래",
        "집합 PPA",
        "VPP 경유",
    ]

    for s in structures:
        config = ContractConfig(structure=s)
        result = engine.calculate(config)
        assert result["structure"] == s
