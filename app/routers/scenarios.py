"""시나리오 라우터 — CRUD + 인가. SC-2."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.security.authorization import assert_can_access
from app.services import InMemoryScenarioStore, ScenarioRecord, ScenarioService

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

#: 인메모리 저장 — 운영은 DB. 여기서는 CRUD 흐름과 인가(14.3)를 고정한다.
_store = InMemoryScenarioStore()
_service = ScenarioService(_store)


@router.post("")
def create_scenario(
    name: str,
    owner_id: int = Query(...),
    description: str = "",
) -> dict[str, object]:
    rec = ScenarioRecord(id=0, name=name, owner_id=owner_id, description=description)
    saved = _service.create(rec)
    return {"id": saved.id, "name": saved.name}


@router.get("/{scenario_id}")
def get_scenario(
    scenario_id: int,
    requesting_user_id: int = Query(...),
    share_token: str | None = Query(None),
) -> dict[str, object]:
    rec = _service.get(scenario_id)
    if rec is None or rec.is_deleted:
        raise HTTPException(status_code=404, detail="시나리오가 없습니다")
    # SC-2 인가 — 소유자 또는 유효 공유 토큰. 유효 토큰 목록은 단순화: 빈 튜플.
    # 운영에서는 Scenario.valid_share_tokens 에서 읽는다.
    try:
        assert_can_access(
            resource_owner_id=rec.owner_id,
            requesting_user_id=requesting_user_id,
            share_token=share_token,
            valid_share_tokens=(),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"id": rec.id, "name": rec.name, "owner_id": rec.owner_id}


@router.delete("/{scenario_id}")
def delete_scenario(scenario_id: int) -> dict[str, str]:
    try:
        _service.delete(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "soft_deleted"}
