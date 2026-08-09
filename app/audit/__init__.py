"""app.audit — 감사 로그 기록 대상 정의 (SC-4)."""
from __future__ import annotations

from app.audit.recorder import AuditAction, record

__all__ = ("AuditAction", "record")
