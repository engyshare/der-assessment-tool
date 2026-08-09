from core.model.schemas import ContractConfig


class SettlementEngine:
    SUPPORTED_STRUCTURES = frozenset(
        {
            "개별 직접계약",
            "단일계약+관리주체",
            "분산특구 직접거래",
            "상계",
            "잉여 직거래",
            "집합 PPA",
            "VPP 경유",
        }
    )

    def calculate(self, contract: ContractConfig) -> dict[str, float | str]:
        if contract.structure not in self.SUPPORTED_STRUCTURES:
            raise ValueError(f"지원하지 않는 계약 구조입니다: {contract.structure}")
        # 임시 정산식 적용 (스텁)
        return {"structure": contract.structure, "amount": 0.0}
