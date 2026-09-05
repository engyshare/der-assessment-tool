"""시나리오 라우터 — CRUD + 인가. SC-2 / FR-902-AC1~AC3.

## ★★ 여섯 문이 **모두** 소유자 확인을 지난다 (R63/F1 · `result_R1.md` D-10)

종전에는 **`GET /{id}` 만** 지났다. `PUT`·`DELETE`·`GET /versions`·복원 둘에는
소유자 확인이 없었고 `PUT` 은 `requesting_user_id` 를 **받지도 않았다.** 실측:

    GET  by user 2 -> 403 (SC-2)
    PUT  (인가 인자 자체가 없다) -> 200 {'name': '남이 덮어씀', 'version': 2}
    주인이 다시 읽으면 -> 남이 덮어씀
    DELETE -> 200 {'status': 'soft_deleted'}    주인의 목록 -> []
    이력 (인가 없이) -> [{... '내 사업'}, {... '남이 덮어씀'}]

조항 `SC-2` 는 *「시나리오 접근은 소유자 또는 유효 공유 토큰 보유자로 제한」*
이고, 「접근」에 수정·삭제가 들지 않는다고 읽을 근거가 없다.

⚠ **이 결함은 R63 이 만든 것이 아니다.** 그래도 이 라운드가 고친 사유는
**R63/P3 가 저장을 파일로 옮겨 피해가 프로세스를 넘어 남게 되었기** 때문이다 —
실측에서 새 프로세스가 `[(1, '남이 덮어씀', 2)]` 를 읽었다.

⚠ **거부는 한 함수(`_assert_may_touch`)가 진다.** 두 벌을 만들면 문면이 갈리고,
그러면 한 문에서 가드가 빠져도 이웃 문의 거부 메시지가 같아서 공통 단언이 전부
통과한다 (`app/security/authorization.py::can_edit_regulation_profile` 주석이
적은 R22 실측 형태).

## ⚠ `purge_expired` 는 인가를 세우지 않았다 — **판정 대기**

그 문에는 시나리오 id 가 없다(만료된 것 전부를 지운다). 소유자별로 나누면
조항 밖의 규칙을 여기서 새로 짓는 것이 되고, `admin` 으로 막으려면
`can_edit_regulation_profile` 처럼 **역할을 받는 자리**가 서야 하는데 그것을
정한 조항을 못 찾았다. `.orch/R63/result_F1.md` §6 에 적어 두었다.
"""
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


def _assert_may_touch(
    record: ScenarioRecord,
    *,
    requesting_user_id: int,
    share_token: str | None,
) -> None:
    """`SC-2` — 소유자이거나 유효 공유 토큰 보유자. **여섯 문이 이것을 쓴다.**

    ⚠ 거부 문면을 여기서 짓지 않는다. `app/security/authorization.py` 의
    `can_access_scenario` 가 사유를 적고, 이 함수는 그것을 HTTP 403 으로 옮길
    뿐이다 — 문면을 라우터가 다시 쓰면 인가 판정과 사용자가 보는 말이 갈린다.
    """
    try:
        assert_can_access(
            resource_owner_id=record.owner_id,
            requesting_user_id=requesting_user_id,
            share_token=share_token,
            valid_share_tokens=(),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _load_or_404(scenario_id: int, *, include_deleted: bool) -> ScenarioRecord:
    """레코드를 꺼내거나 404. **인가보다 먼저 부른다** — 없는 것은 없는 것이다.

    ⚠ 소프트 삭제된 것을 볼 것인가는 문마다 다르다. 상세·수정은 **활성만**
    보고(없는 것으로 답한다), 이력·복원 둘은 삭제된 것도 본다 — 삭제 복원은
    삭제된 레코드에만 뜻이 있기 때문이다.
    """
    record = _service.get(scenario_id)
    if record is None or (record.is_deleted and not include_deleted):
        raise HTTPException(status_code=404, detail="시나리오가 없습니다")
    return record


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
    rec = _load_or_404(scenario_id, include_deleted=False)
    _assert_may_touch(
        rec, requesting_user_id=requesting_user_id, share_token=share_token
    )
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
    # ⚠ 뒤는 **이름으로만** 받는다. 질의 인자는 어차피 이름으로 오고,
    # 자리로 받게 두면 인가 인자가 `description` 자리에 들어가는 호출을
    # 형 검사가 잡지 못한다 (`PLR0917` 도 그 자리를 가리켰다).
    *,
    requesting_user_id: int = Query(...),
    share_token: str | None = Query(None),
    description: str = "",
    tags: str = "",
    definition_json: str = "",
) -> dict[str, object]:
    """시나리오 수정 및 버전 업 (FR-902-AC1, FR-902-AC2 / SC-2).

    ⚠ **`requesting_user_id` 가 필수다.** 종전에는 인자 자체가 없어 누구든
    남의 시나리오를 덮을 수 있었다(머리말 실측). 이 인자를 선택으로 두면
    부르지 않는 호출부가 조용히 인가를 건너뛴다.
    """
    existing = _load_or_404(scenario_id, include_deleted=False)
    _assert_may_touch(
        existing, requesting_user_id=requesting_user_id, share_token=share_token
    )
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
def list_scenario_versions(
    scenario_id: int,
    requesting_user_id: int = Query(...),
    share_token: str | None = Query(None),
) -> list[dict[str, object]]:
    """시나리오 버전 이력 목록 조회 (FR-902-AC2 / SC-2).

    ⚠ 이력은 시나리오의 이전 내용을 그대로 담는다 — 상세 조회를 막고 이력을
    열어 두면 **같은 내용이 다른 문으로 나간다.**
    """
    existing = _load_or_404(scenario_id, include_deleted=True)
    _assert_may_touch(
        existing, requesting_user_id=requesting_user_id, share_token=share_token
    )
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
    scenario_id: int,
    version: int = Query(...),
    requesting_user_id: int = Query(...),
    share_token: str | None = Query(None),
) -> dict[str, object]:
    """이전 버전으로 복원 (FR-902-AC2 / SC-2)."""
    existing = _load_or_404(scenario_id, include_deleted=True)
    _assert_may_touch(
        existing, requesting_user_id=requesting_user_id, share_token=share_token
    )
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
def delete_scenario(
    scenario_id: int,
    requesting_user_id: int = Query(...),
    share_token: str | None = Query(None),
) -> dict[str, str]:
    """소프트 삭제 (FR-902-AC3 / SC-2)."""
    existing = _load_or_404(scenario_id, include_deleted=True)
    _assert_may_touch(
        existing, requesting_user_id=requesting_user_id, share_token=share_token
    )
    try:
        _service.delete(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "soft_deleted"}


@router.post("/{scenario_id}/restore")
def restore_scenario(
    scenario_id: int,
    requesting_user_id: int = Query(...),
    share_token: str | None = Query(None),
) -> dict[str, object]:
    """소프트 삭제 복원 (FR-902-AC3 / SC-2)."""
    existing = _load_or_404(scenario_id, include_deleted=True)
    _assert_may_touch(
        existing, requesting_user_id=requesting_user_id, share_token=share_token
    )
    try:
        restored = _service.restore(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": restored.id, "status": "restored"}


@router.post("/purge_expired")
def purge_expired_scenarios() -> dict[str, object]:
    """30일 이상 지난 소프트 삭제 시나리오 완전 영구 삭제 (FR-902-AC3).

    ⚠⚠ **여기에는 소유자 확인이 없다 — 판정 대기다** (R63/F1). 이 문에는
    시나리오 id 가 없고 만료된 것 **전부**를 지우므로 `SC-2` 의 「소유자」를
    그대로 걸 자리가 없다. 소유자별로 나누는 것도, `admin` 역할로 막는 것도
    **조항이 정한 것이 아니라 여기서 새로 짓는 규칙**이 된다 —
    `app/security/authorization.py::ADMIN_ROLE` 이 그 판단을 `FR-504-AC3`
    이라는 조항 위에 세웠던 것과 대비된다. 정하기 전에 세우지 않는다.
    """
    purged_count = _service.purge_expired()
    return {"purged_count": purged_count}
