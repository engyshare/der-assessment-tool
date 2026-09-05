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
@pytest.mark.req("SC-2")
def test_scenario_router_api_endpoints() -> None:
    """FastAPI 라우터 HTTP 엔드포인트 통합 검증 (FR-902-AC1~AC3 / SC-2).

    ⚠ **`requesting_user_id` 를 더해 고쳤다** (R63/F1 · `result_R1.md` D-10).
    종전 이 시험은 `PUT`·`DELETE`·`GET /versions`·복원을 **인가 없이** 불렀고,
    그것이 통과했기 때문에 *「남이 내 시나리오를 덮고 지운다」* 가 초록불
    아래에서 살아 있었다 — 실측 `PUT (owner_id 인자 자체가 없다) -> 200` ·
    `주인이 다시 읽으면 -> 남이 덮어씀` · `DELETE -> 200` · `주인의 목록 -> []`.
    조항(`SC-2`)은 *「시나리오 접근은 소유자 또는 유효 공유 토큰 보유자로
    제한」* 이고, 「접근」에 수정·삭제가 들지 않는다고 읽을 근거가 없다.

    ⛔ 조항을 느슨하게 해서 이 시험을 살리지 않았다. **이 시험이 소유자로
    부르도록 고쳤다** — 소유자 경로가 그대로 도는 것(양성)을 재는 것이 이
    시험의 몫이고, 남이 막히는 것(음성)은 아래 `SC-2` 시험이 잰다.
    """
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
        params={
            "name": "API 시나리오 v2",
            "description": "업데이트됨",
            "requesting_user_id": 50,
        },
    )
    assert res_update.status_code == 200
    assert res_update.json()["version"] == 2

    # 버전 목록 조회 (AC2)
    res_versions = client.get(
        f"/scenarios/{scenario_id}/versions", params={"requesting_user_id": 50}
    )
    assert res_versions.status_code == 200
    assert len(res_versions.json()) == 2

    # v1 복원 (AC2)
    res_restore_v = client.post(
        f"/scenarios/{scenario_id}/restore_version",
        params={"version": 1, "requesting_user_id": 50},
    )
    assert res_restore_v.status_code == 200
    assert res_restore_v.json()["version"] == 3
    assert res_restore_v.json()["name"] == "API 시나리오"

    # 4. 삭제 및 복원 (AC3)
    res_del = client.delete(
        f"/scenarios/{scenario_id}", params={"requesting_user_id": 50}
    )
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "soft_deleted"

    res_restore = client.post(
        f"/scenarios/{scenario_id}/restore", params={"requesting_user_id": 50}
    )
    assert res_restore.status_code == 200
    assert res_restore.json()["status"] == "restored"

    # 만료 항목 정제 (AC3)
    res_purge = client.post("/scenarios/purge_expired")
    assert res_purge.status_code == 200
    assert "purged_count" in res_purge.json()


# ── `SC-2` — 남이 내 시나리오를 덮거나 지우지 못한다 ────────────────────
#
# `result_R1.md` D-10 의 재현이다. 종전에는 **`GET /{id}` 만**
# `assert_can_access` 를 지났고 `PUT` 은 `owner_id` 인자를 받지도 않았다.
# 실측:
#
#     GET  by user 2 -> 403 {'detail': '사용자 2 은(는) 리소스(소유자 1) 에
#                             접근할 권한이 없다 — 소유자가 아니며 유효 공유
#                             토큰도 없다 (SC-2)'}
#     PUT  (owner_id 인자 자체가 없다) -> 200 {'name': '남이 덮어씀', ...}
#     주인이 다시 읽으면 -> 남이 덮어씀
#     DELETE -> 200 {'status': 'soft_deleted'}   주인의 목록 -> []
#     이력 (인가 없이) -> [{... '내 사업'}, {... '남이 덮어씀'}]
#
# ⚠ **R63 이 만든 결함이 아니다.** 그래도 이 라운드가 고치는 사유는
# **R63/P3 가 저장을 파일로 옮겨 피해가 프로세스를 넘어 남게 되었기**
# 때문이다 — 실측에서 새 프로세스가 `[(1, '남이 덮어씀', 2)]` 를 읽었다.


#: 이 절의 시험들이 쓰는 소유자. 라우터의 저장소는 **모듈 수준에서 한 번**
#: 지어져(`app/routers/scenarios.py`) 한 프로세스의 모든 시험이 공유한다 —
#: 다른 시험과 같은 id 를 쓰면 목록 단언이 서로를 물려받는다.
_OWNER = 9_101
_STRANGER = 9_102


def _create_scenario(client: TestClient, name: str) -> int:
    """소유자 `_OWNER` 로 시나리오 하나를 짓고 그 id 를 준다."""
    created = client.post(
        "/scenarios", params={"name": name, "owner_id": _OWNER}
    )
    assert created.status_code == 200, created.text
    return int(created.json()["id"])


@pytest.mark.req("SC-2")
def test_a_stranger_cannot_overwrite_or_delete_someone_elses_scenario() -> None:
    """★★★ 남의 `PUT`·`DELETE` 가 **403** 이고, 주인의 것은 그대로 남는다.

    ⚠ 「거부되었다」만 재면 부족하다 — 거부하고도 고쳤을 수 있다. **주인이
    다시 읽었을 때 옛 값 그대로인지**를 함께 잰다. R1 이 실제로 잰 것이
    `주인이 다시 읽으면 -> 남이 덮어씀` 이었다.
    """
    client = TestClient(create_app())
    scenario_id = _create_scenario(client, "내 사업")

    denied_put = client.put(
        f"/scenarios/{scenario_id}",
        params={"name": "남이 덮어씀", "requesting_user_id": _STRANGER},
    )
    assert denied_put.status_code == 403, denied_put.text

    denied_delete = client.delete(
        f"/scenarios/{scenario_id}", params={"requesting_user_id": _STRANGER}
    )
    assert denied_delete.status_code == 403, denied_delete.text

    mine = client.get(
        f"/scenarios/{scenario_id}", params={"requesting_user_id": _OWNER}
    )
    assert mine.status_code == 200
    assert mine.json()["name"] == "내 사업", "거부하고도 값이 바뀌었다"
    assert mine.json()["version"] == 1, "거부한 수정이 버전을 올렸다"
    assert [row["id"] for row in client.get(
        "/scenarios", params={"owner_id": _OWNER}
    ).json()] == [scenario_id], "거부한 삭제가 목록에서 지웠다"


@pytest.mark.req("SC-2")
def test_a_stranger_cannot_read_or_roll_back_the_version_history() -> None:
    """★ 이력 조회·버전 복원·삭제 복원도 **소유자 확인을 지난다.**

    이력은 시나리오의 이전 내용을 그대로 담는다 — 상세 조회를 막고 이력을
    열어 두면 **같은 내용이 다른 문으로 나간다.** 복원 둘은 쓰기이므로 더
    말할 것이 없다.
    """
    client = TestClient(create_app())
    scenario_id = _create_scenario(client, "이력 있는 사업")
    assert client.put(
        f"/scenarios/{scenario_id}",
        params={"name": "이력 있는 사업 v2", "requesting_user_id": _OWNER},
    ).status_code == 200

    stranger = {"requesting_user_id": _STRANGER}
    assert client.get(
        f"/scenarios/{scenario_id}/versions", params=stranger
    ).status_code == 403
    assert client.post(
        f"/scenarios/{scenario_id}/restore_version",
        params={"version": 1, **stranger},
    ).status_code == 403
    assert client.post(
        f"/scenarios/{scenario_id}/restore", params=stranger
    ).status_code == 403

    still = client.get(
        f"/scenarios/{scenario_id}", params={"requesting_user_id": _OWNER}
    )
    assert still.json()["name"] == "이력 있는 사업 v2", "거부한 복원이 되돌렸다"


@pytest.mark.req("SC-2")
def test_every_scenario_route_denies_with_the_same_words_as_the_detail_route() -> None:
    """★★ 여섯 문의 거부 문면이 **한 곳에서 나온다** — 두 벌을 만들지 않는다.

    ⚠ 문면이 갈리면 표시 층과 로그가 문을 구별하지 못하고, 한 문에서 가드가
    빠져도 **이웃 문의 거부 메시지가 같아서** 공통 단언이 전부 통과한다
    (`app/security/authorization.py::can_edit_regulation_profile` 주석이 적은
    R22 실측 형태). 그래서 `GET /{id}` 가 쓰는 것과 **같은 함수**를 쓴다.
    """
    client = TestClient(create_app())
    scenario_id = _create_scenario(client, "문면 대조")
    stranger = {"requesting_user_id": _STRANGER}

    expected = client.get(f"/scenarios/{scenario_id}", params=stranger).json()["detail"]

    denials = {
        "PUT": client.put(
            f"/scenarios/{scenario_id}", params={"name": "x", **stranger}
        ),
        "DELETE": client.delete(f"/scenarios/{scenario_id}", params=stranger),
        "versions": client.get(f"/scenarios/{scenario_id}/versions", params=stranger),
        "restore_version": client.post(
            f"/scenarios/{scenario_id}/restore_version",
            params={"version": 1, **stranger},
        ),
        "restore": client.post(f"/scenarios/{scenario_id}/restore", params=stranger),
    }

    assert "SC-2" in expected
    for door, response in denials.items():
        assert response.status_code == 403, f"{door} 가 인가를 지나지 않는다"
        assert response.json()["detail"] == expected, f"{door} 의 거부 문면이 갈렸다"


@pytest.mark.req("SC-2")
def test_a_valid_share_token_is_still_not_invented_here() -> None:
    """양성 — **소유자는 여섯 문을 그대로 지난다.**

    거부만 재면 전부 막는 구현도 만점을 받는다
    (`app/security/authorization.py` 머리말의 규약). 공유 토큰 쪽은
    `valid_share_tokens=()` 라 지금 어느 문도 열지 않으며, 그것을 발급하는
    자리는 이 라운드가 세우지 않았다 — `GET /{id}` 와 같은 처지다.
    """
    client = TestClient(create_app())
    scenario_id = _create_scenario(client, "주인은 지난다")
    owner = {"requesting_user_id": _OWNER}

    assert client.put(
        f"/scenarios/{scenario_id}", params={"name": "주인이 고침", **owner}
    ).status_code == 200
    assert client.get(
        f"/scenarios/{scenario_id}/versions", params=owner
    ).status_code == 200
    assert client.post(
        f"/scenarios/{scenario_id}/restore_version",
        params={"version": 1, **owner},
    ).status_code == 200
    assert client.delete(
        f"/scenarios/{scenario_id}", params=owner
    ).status_code == 200
    assert client.post(
        f"/scenarios/{scenario_id}/restore", params=owner
    ).status_code == 200
