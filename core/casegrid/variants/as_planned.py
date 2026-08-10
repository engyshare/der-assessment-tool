"""입력된 지원안 그대로 — FR-607-AC1 · FR-606-AC1.

사용자가 입력한 확정 지원안(예: ESS 50%·MG 70%)의 조건 하 경제성이다.
`FR-606-AC1` 이 *「이 모드에서도 무지원 기준선(FR-607)은 **함께 표시**된다」*
고 적는데, 그 「함께」가 `run_order()` 로 표현된다 — 두 변형이 한 목록에
있으므로 하나만 도는 경로가 없다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from core.contracts.casevariant import CaseVariant


class AsPlanned(CaseVariant):
    """입력값을 하나도 바꾸지 않는 케이스."""

    tag: ClassVar[str] = "as_planned"
    label: ClassVar[str] = "입력 지원안"
    order: ClassVar[int] = 10
    clauses: ClassVar[tuple[str, ...]] = ("FR-607-AC1", "FR-606-AC1")

    def overrides(self, base: Mapping[str, Any]) -> dict[str, Any]:
        """덮어쓰는 것이 없다.

        **빈 사전을 돌려주는 것과 「변형이 아니다」는 다르다.** 이 케이스는
        기준선과 나란히 표시되어야 하는 독립 케이스이며, 목록에 없으면
        무지원 결과만 남는다.
        """
        return {}
