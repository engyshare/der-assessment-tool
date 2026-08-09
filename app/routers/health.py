"""헬스 라우터 — 단순 조회. 14.7 성능 측정의 기준 엔드포인트."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health() -> dict[str, str]:
    """헬스 체크 — 200 OK 만으로 충분. p95 500ms 측정의 기준."""
    return {"status": "ok"}
