"""케이스 변형 레지스트리 — FR-607-AC1 · FR-801.

**변형을 더하는 방법은 파일 하나를 놓는 것이다.**

    core/casegrid/variants/minimum_support.py     ← FR-608 역산 결과 케이스
      class MinimumSupport(CaseVariant):
          tag = "minimum_support"
          order = 20
          ...

    이 파일은 바뀌지 않는다 — `core/der/__init__.py` 를 고치지 않고 자원을
    더하는 것과 같은 근거다 (§16.1 W-3).
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from functools import lru_cache

from core.contracts.casevariant import CaseVariant, ordered_variants
from core.contracts.registry import discover

#: 튜플이다 — 모듈 수준 가변 컨테이너 금지 (`test_ci_gates`)
__all__ = ("CaseVariant", "run_order", "variant_registry")


@lru_cache(maxsize=1)
def variant_registry() -> Mapping[str, type[CaseVariant]]:
    """등록된 변형 — `{tag: 클래스}`."""
    return discover(sys.modules[__name__], CaseVariant)  # type: ignore[type-abstract]


def run_order() -> Sequence[type[CaseVariant]]:
    """한 번의 실행이 산출할 케이스들 — **기준선이 맨 위다** (FR-607-AC1).

    파이프라인이 이 순서를 그대로 쓴다. 호출자가 기준선을 «기억해서» 넣는
    구조가 아니므로 빠뜨릴 수 없고, 빠뜨리려면 파일을 지워야 하는데 그러면
    `ordered_variants()` 가 빨간불을 낸다.
    """
    return ordered_variants(variant_registry())
