"""무지원 기준선 — FR-607-AC1 · FR-607-AC3 · FR-611.

**「지원 0」은 «본 사업의 지원이 0» 이다** (FR-607-AC3). 타 사업으로 **확정**
지원된 설비는 기준선에 **포함된 소여(given)** 로 보고, **지원 예정**(미확정)만
제외한다. 이미 받기로 확정된 ESS 를 없는 셈 치고 산출한 보조율은 실제로
필요한 금액이 아니기 때문이다.

그래서 이 변형이 끄는 것은 **본 사업 지원**뿐이며, 타 사업 확정분을 나타내는
값은 건드리지 않는다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from core.contracts.casevariant import CaseVariant


class Unsupported(CaseVariant):
    """본 사업 지원이 0 인 케이스. **모든 실행에 자동 포함되고 맨 위에 온다.**"""

    tag: ClassVar[str] = "unsupported"
    label: ClassVar[str] = "무지원 기준선"
    order: ClassVar[int] = 0
    baseline: ClassVar[bool] = True
    clauses: ClassVar[tuple[str, ...]] = ("FR-607-AC1", "FR-607-AC3")

    def overrides(self, base: Mapping[str, Any]) -> dict[str, Any]:
        """본 사업 지원 항목만 0 으로 덮어쓴다.

        `prefunded_*`(타 사업 확정 지원)은 **건드리지 않는다** — FR-607-AC3
        가 그것을 기준선에 포함된 소여로 규정한다.
        """
        return {
            "subsidy_rate": 0.0,
            "subsidy_fixed_won": 0,
            "loan_rate": 0.0,
        }
