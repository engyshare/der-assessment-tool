"""시나리오 라우터 — CRUD + 인가. SC-2 / FR-902-AC1~AC3."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.security.authorization import assert_can_access
from app.services import (
    ScenarioRecord,
    ScenarioService,
    build_scenario_store,
    resolve_scenario_store_dir,
)

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

#: 저장 자리는 **배포가 정한다** (`DER_SCENARIO_STORE`). 자리를 정하면 저장이
#: 프로세스를 넘어 살고(`JsonFileScenarioStore`), 정하지 않으면 인메모리다 —
#: 그 되돌림의 사유는 `app/deps.py::DEFAULT_DB_URL` 주석이 갖는다.
#:
#: ⚠ **경로를 여기 적지 않는다.** 적으면 배포마다 이 파일을 고쳐야 하고,
#: 검사는 자기 `tmp_path` 를 줄 수 없다.
_store = build_scenario_store(resolve_scenario_store_dir())
_service = ScenarioService(_store)


@router.post("")
def create_scenario(
    name: str,
    owner_id: int = Query(...),
    description: str = "",
    tags: str = "",
    definition_json: str = "",
) -> dict[str, object]:
    """시나리오 생성 (FR-902-AC1)."""
    tag_tuple = (
        tuple(t.strip() for t in tags.split(",") if t.strip()) if tags else ()
    )
    rec = ScenarioRecord(
        id=0,
        name=name,
        owner_id=owner_id,
        description=description,
        tags=tag_tuple,
        definition_json=definition_json,
    )
    saved = _service.create(rec)
    return {
        "id": saved.id,
        "name": saved.name,
        "description": saved.description,
        "tags": list(saved.tags),
        "version": saved.version,
        "updated_at": saved.updated_at.isoformat(),
    }


@router.get("")
def list_scenarios(owner_id: int = Query(...)) -> list[dict[str, object]]:
    """사용자의 활성 시나리오 목록 조회 (FR-902-AC1)."""
    records = _service.list_for_owner(owner_id)
    return [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "tags": list(r.tags),
            "version": r.version,
            "owner_id": r.owner_id,
            "updated_at": r.updated_at.isoformat(),
        }
        for r in records
    ]


@router.get("/{scenario_id}")
def get_scenario(
    scenario_id: int,
    requesting_user_id: int = Query(...),
    share_token: str | None = Query(None),
) -> dict[str, object]:
    """시나리오 상세 조회 (FR-902-AC1 / SC-2)."""
    rec = _service.get(scenario_id)
    if rec is None or rec.is_deleted:
        raise HTTPException(status_code=404, detail="시나리오가 없습니다")
    try:
        assert_can_access(
            resource_owner_id=rec.owner_id,
            requesting_user_id=requesting_user_id,
            share_token=share_token,
            valid_share_tokens=(),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {
        "id": rec.id,
        "name": rec.name,
        "description": rec.description,
        "tags": list(rec.tags),
        "definition_json": rec.definition_json,
        "owner_id": rec.owner_id,
        "version": rec.version,
        "updated_at": rec.updated_at.isoformat(),
    }


@router.put("/{scenario_id}")
def update_scenario(
    scenario_id: int,
    name: str,
    description: str = "",
    tags: str = "",
    definition_json: str = "",
) -> dict[str, object]:
    """시나리오 수정 및 버전 업 (FR-902-AC1, FR-902-AC2)."""
    existing = _service.get(scenario_id)
    if existing is None or existing.is_deleted:
        raise HTTPException(status_code=404, detail="시나리오가 없습니다")
    tag_tuple = (
        tuple(t.strip() for t in tags.split(",") if t.strip()) if tags else ()
    )
    rec = ScenarioRecord(
        id=scenario_id,
        name=name,
        description=description,
        tags=tag_tuple,
        definition_json=definition_json,
        owner_id=existing.owner_id,
    )
    updated = _service.update(rec)
    return {
        "id": updated.id,
        "name": updated.name,
        "version": updated.version,
        "updated_at": updated.updated_at.isoformat(),
    }


@router.get("/{scenario_id}/versions")
def list_scenario_versions(scenario_id: int) -> list[dict[str, object]]:
    """시나리오 버전 이력 목록 조회 (FR-902-AC2)."""
    existing = _service.get(scenario_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="시나리오가 없습니다")
    versions = _service.list_versions(scenario_id)
    return [
        {
            "id": v.id,
            "version": v.version,
            "name": v.name,
            "description": v.description,
            "updated_at": v.updated_at.isoformat(),
        }
        for v in versions
    ]


@router.post("/{scenario_id}/restore_version")
def restore_scenario_version(
    scenario_id: int, version: int = Query(...)
) -> dict[str, object]:
    """이전 버전으로 복원 (FR-902-AC2)."""
    try:
        restored = _service.restore_version(scenario_id, version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "id": restored.id,
        "version": restored.version,
        "name": restored.name,
        "updated_at": restored.updated_at.isoformat(),
    }


@router.delete("/{scenario_id}")
def delete_scenario(scenario_id: int) -> dict[str, str]:
    """소프트 삭제 (FR-902-AC3)."""
    try:
        _service.delete(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "soft_deleted"}


@router.post("/{scenario_id}/restore")
def restore_scenario(scenario_id: int) -> dict[str, object]:
    """소프트 삭제 복원 (FR-902-AC3)."""
    try:
        restored = _service.restore(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": restored.id, "status": "restored"}


@router.post("/purge_expired")
def purge_expired_scenarios() -> dict[str, object]:
    """30일 이상 지난 소프트 삭제 시나리오 완전 영구 삭제 (FR-902-AC3)."""
    purged_count = _service.purge_expired()
    return {"purged_count": purged_count}
