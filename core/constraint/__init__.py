"""core/constraint — 구획 WP-5.

제약 합성·사전 충돌 검출 (FR-403)

소유 경로 밖 파일을 건드리지 않는다 (§16.1 W-1).
"""
from __future__ import annotations

from core.constraint.registry import (
    ConflictAt,
    ConstraintRegistry,
)

__all__ = (
    "ConflictAt",
    "ConstraintRegistry",
)
