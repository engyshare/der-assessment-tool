"""FR-902 시나리오·전제 저장/불러오기 테스트 (FR-902-AC1~AC3)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import ScenarioService
from app.services.scenario_store import (
    SOFT_DELETE_RETENTION_DAYS,
    InMemoryScenarioStore,
    ScenarioRecord,
)


@pytest.mark.req("FR-902-AC1")
def test_scenario_metadata_ac1() -> None:
    """FR-902-AC1 — 이름·설명·태그·최종수정일시 부여 및 목록 조회."""
    store = InMemoryScenarioStore()
    service = ScenarioService(store)

    rec = ScenarioRecord(
        id=0,
        name="제주 VPP 시나리오",
        description="VPP 경제성 평가 시나리오",
        tags=("vpp", "jeju"),
        definition_json='{"asset": "pv"}',
        owner_id=101,
    )
    saved = service.create(rec)
    assert saved.id == 1
    assert saved.name == "제주 VPP 시나리오"
    assert saved.description == "VPP 경제성 평가 시나리오"
    assert saved.tags == ("vpp", "jeju")
    assert saved.version == 1
    assert isinstance(saved.updated_at, datetime)

    active = service.list_for_owner(101)
    assert len(active) == 1
    assert active[0].id == 1


@pytest.mark.req("FR-902-AC2")
def test_scenario_versioning_and_restoration_ac2() -> None:
    """FR-902-AC2 — 저장 시 버전 이력 남음 및 이전 버전 복원."""
    store = InMemoryScenarioStore()
    service = ScenarioService(store)

    # 1. v1 생성
    rec1 = ScenarioRecord(
        id=0,
        name="초기 시나리오",
        description="버전 1",
        owner_id=10,
    )
    v1 = service.create(rec1)
    assert v1.version == 1

    # 2. v2 수정
    rec2 = ScenarioRecord(
        id=v1.id,
        name="수정된 시나리오",
        description="버전 2",
        owner_id=10,
    )
    v2 = service.update(rec2)
    assert v2.version == 2
    assert v2.name == "수정된 시나리오"

    # 3. 버전 이력 확인
    versions = service.list_versions(v1.id)
    assert len(versions) == 2
    assert [v.version for v in versions] == [1, 2]

    # 4. v1 으로 복원 → v3 생성 (v1 내용 복원)
    restored = service.restore_version(v1.id, version=1)
    assert restored.version == 3
    assert restored.name == "초기 시나리오"

    all_versions = service.list_versions(v1.id)
    assert len(all_versions) == 3


@pytest.mark.req("FR-902-AC3")
def test_scenario_soft_delete_and_retention_ac3() -> None:
    """FR-902-AC3 — 소프트 삭제 (30일 보관) 및 복원/만료 정제."""
    store = InMemoryScenarioStore()
    service = ScenarioService(store)

    rec = ScenarioRecord(id=0, name="삭제 테스트", owner_id=20)
    saved = service.create(rec)

    # 소프트 삭제
    service.delete(saved.id)
    retrieved = service.get(saved.id)
    assert retrieved is not None
    assert retrieved.is_deleted is True
    assert len(service.list_for_owner(20)) == 0

    # 소프트 삭제 복원
    restored = service.restore(saved.id)
    assert restored.is_deleted is False
    assert len(service.list_for_owner(20)) == 1

    # 30일 경과 및 미경과 정제 테스트
    now = datetime.now(UTC)
    # rec_old: 31일 전 삭제됨
    rec_old = service.create(
        ScenarioRecord(id=0, name="31일전 삭제 시나리오", owner_id=20)
    )
    store.soft_delete(rec_old.id)
    old_rec = store.load(rec_old.id)
    assert old_rec is not None
    old_rec.deleted_at = now - timedelta(days=SOFT_DELETE_RETENTION_DAYS + 1)

    # rec_recent: 10일 전 삭제됨
    rec_recent = service.create(
        ScenarioRecord(id=0, name="10일전 삭제 시나리오", owner_id=20)
    )
    store.soft_delete(rec_recent.id)
    recent_rec = store.load(rec_recent.id)
    assert recent_rec is not None
    recent_rec.deleted_at = now - timedelta(days=10)

    # 30일 지난 항목만 완전 정제
    purged = service.purge_expired(now=now)
    assert purged == 1
    assert store.load(rec_old.id) is None
    assert store.load(rec_recent.id) is not None


@pytest.mark.req("FR-902-AC1")
@pytest.mark.req("FR-902-AC2")
@pytest.mark.req("FR-902-AC3")
def test_scenario_router_api_endpoints() -> None:
    """FastAPI 라우터 HTTP 엔드포인트 통합 검증 (FR-902-AC1~AC3)."""
    client = TestClient(create_app())

    # 1. 생성 (AC1)
    res_create = client.post(
        "/scenarios",
        params={
            "name": "API 시나리오",
            "owner_id": 50,
            "description": "API 테스트",
            "tags": "pv,ess",
        },
    )
    assert res_create.status_code == 200
    data = res_create.json()
    scenario_id = int(data["id"])
    assert data["name"] == "API 시나리오"
    assert data["description"] == "API 테스트"  # FR-902-AC1: description 확인
    assert data["tags"] == ["pv", "ess"]
    assert data["version"] == 1
    assert "updated_at" in data  # FR-902-AC1: updated_at 확인

    # 2. 목록 및 상세 조회 (AC1)
    res_list = client.get("/scenarios", params={"owner_id": 50})
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1

    res_get = client.get(
        f"/scenarios/{scenario_id}", params={"requesting_user_id": 50}
    )
    assert res_get.status_code == 200
    data = res_get.json()
    assert data["id"] == scenario_id
    assert "description" in data  # FR-902-AC1: description 확인
    assert "updated_at" in data  # FR-902-AC1: updated_at 확인

    # 3. 수정 및 버전 업데이트 (AC2)
    res_update = client.put(
        f"/scenarios/{scenario_id}",
        params={"name": "API 시나리오 v2", "description": "업데이트됨"},
    )
    assert res_update.status_code == 200
    assert res_update.json()["version"] == 2

    # 버전 목록 조회 (AC2)
    res_versions = client.get(f"/scenarios/{scenario_id}/versions")
    assert res_versions.status_code == 200
    assert len(res_versions.json()) == 2

    # v1 복원 (AC2)
    res_restore_v = client.post(
        f"/scenarios/{scenario_id}/restore_version", params={"version": 1}
    )
    assert res_restore_v.status_code == 200
    assert res_restore_v.json()["version"] == 3
    assert res_restore_v.json()["name"] == "API 시나리오"

    # 4. 삭제 및 복원 (AC3)
    res_del = client.delete(f"/scenarios/{scenario_id}")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "soft_deleted"

    res_restore = client.post(f"/scenarios/{scenario_id}/restore")
    assert res_restore.status_code == 200
    assert res_restore.json()["status"] == "restored"

    # 만료 항목 정제 (AC3)
    res_purge = client.post("/scenarios/purge_expired")
    assert res_purge.status_code == 200
    assert "purged_count" in res_purge.json()
