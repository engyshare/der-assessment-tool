"""FR-504-AC3 「admin 권한 사용자가 웹 UI 에서」의 서버 경로.

조항 문장 하나에 요구가 넷이다.

    생성·복제·수정   세 경로가 각각 있다
    admin 권한       admin 아닌 역할은 **세 경로 모두** 거부된다
    파일 수정 불요    편집이 저장소 파일을 건드리지 않는다
    재배포 불요      **같은 앱 인스턴스**의 다음 조회에 편집이 보인다

거부 검사를 「403 이 난다」로만 적으면 **한 경로에서 가드가 빠져도 이웃 경로의
같은 메시지에 묻힌다** — R22 에 실제로 그 형태를 만났다(가드를 지웠는데 이웃
분기가 같은 예외를 던져 공통 단언이 전부 통과했다). 그래서 거부 사유가 **그
경로의 조작 이름**을 싣는지까지 본다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: 편집이 파일을 건드렸는지 볼 자리 — 제도 값이 놓일 수 있는 곳 전부.
_WATCHED_TREES = ("docs", "fixtures", "core/regulation")

_ADMIN = "admin"
_VIEWER = "viewer"


def _snapshot() -> dict[str, tuple[int, int]]:
    """감시 대상 트리의 (크기, 수정시각) — 편집이 파일을 쓰면 달라진다."""
    snapshot: dict[str, tuple[int, int]] = {}
    for tree in _WATCHED_TREES:
        for path in sorted((_REPO_ROOT / tree).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            stat = path.stat()
            snapshot[str(path.relative_to(_REPO_ROOT))] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def _create(client: TestClient, name: str, *, role: str = _ADMIN):
    return client.post(
        "/regulation/profiles", params={"role": role}, json={"name": name, "version": "v1"}
    )


@pytest.mark.req("FR-504-AC3")
def test_admin_can_create_clone_and_update_through_the_web_paths() -> None:
    """세 조작이 각각 경로를 갖고, admin 이 지나면 성공한다."""
    client = TestClient(create_app())

    created = _create(client, "현행-라우터")
    assert created.status_code == 200, created.text
    assert created.json()["name"] == "현행-라우터"
    assert created.json()["version"] == "v1"

    updated = client.patch(
        "/regulation/profiles/현행-라우터/items",
        params={"role": _ADMIN},
        json={
            "key": "supply_duty.required_ratio",
            "value": 0.7,
            "unit": "비율",
            "source": "분산법 시행령",
            "valid_from": "2026-01-01",
            "version": "v2",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == "v2"
    assert [i["key"] for i in updated.json()["items"]] == ["supply_duty.required_ratio"]

    cloned = client.post(
        "/regulation/profiles/현행-라우터/clone",
        params={"role": _ADMIN},
        json={"name": "개정안-라우터", "version": "v2027"},
    )
    assert cloned.status_code == 200, cloned.text
    assert cloned.json()["name"] == "개정안-라우터"
    assert [i["key"] for i in cloned.json()["items"]] == ["supply_duty.required_ratio"]


@pytest.mark.req("FR-504-AC3")
def test_each_edit_path_refuses_a_non_admin_and_names_its_own_operation() -> None:
    """세 경로가 **각각** 거부하며, 사유가 그 경로의 조작을 말한다."""
    client = TestClient(create_app())
    _create(client, "권한검사-원본")

    refusals = {
        "생성": client.post(
            "/regulation/profiles",
            params={"role": _VIEWER},
            json={"name": "권한없는생성", "version": "v1"},
        ),
        "복제": client.post(
            "/regulation/profiles/권한검사-원본/clone",
            params={"role": _VIEWER},
            json={"name": "권한없는복제", "version": "v1"},
        ),
        "수정": client.patch(
            "/regulation/profiles/권한검사-원본/items",
            params={"role": _VIEWER},
            json={"key": "x.y", "value": 1, "version": "v2"},
        ),
    }

    for operation, response in refusals.items():
        assert response.status_code == 403, (operation, response.text)
        detail = response.json()["detail"]
        assert operation in detail, (
            f"{operation} 경로의 거부 사유가 조작을 말하지 않는다: {detail!r}. "
            "사유가 같으면 한 경로에서 가드가 빠져도 이웃 경로에 묻힌다"
        )
        assert _VIEWER in detail

    # 거부된 편집이 하나도 남지 않았다
    assert client.get("/regulation/profiles/권한없는생성").status_code == 404
    assert client.get("/regulation/profiles/권한없는복제").status_code == 404
    survivor = client.get("/regulation/profiles/권한검사-원본")
    assert survivor.status_code == 200
    assert survivor.json()["items"] == []


@pytest.mark.req("FR-504-AC3")
def test_editing_requires_neither_a_file_change_nor_a_redeploy() -> None:
    """편집이 저장소 파일을 건드리지 않고, **같은 앱**의 다음 조회에 보인다."""
    client = TestClient(create_app())
    _create(client, "무파일-프로파일")

    before = _snapshot()
    assert before, "감시 대상 트리가 비었으면 이 검사는 아무것도 붙들지 않는다"

    response = client.patch(
        "/regulation/profiles/무파일-프로파일/items",
        params={"role": _ADMIN},
        json={
            "key": "exemption.years",
            "value": 5,
            "unit": "년",
            "source": "개정안 제3조",
            "valid_from": "2026-01-01",
            "version": "v2",
        },
    )
    assert response.status_code == 200, response.text

    after = _snapshot()
    assert after == before, (
        "편집이 저장소 파일을 바꿨다 — 조항은 「파일 수정이나 재배포를 요구하지 "
        f"않는다」고 정한다. 달라진 것: {sorted(set(after.items()) ^ set(before.items()))}"
    )

    # **재배포 없이** — 앱을 다시 만들지 않고 같은 클라이언트로 다시 읽는다
    reread = client.get("/regulation/profiles/무파일-프로파일", params={"when": "2026-06-30"})
    assert reread.status_code == 200, reread.text
    assert [i["key"] for i in reread.json()["items"]] == ["exemption.years"]
    assert reread.json()["items"][0]["value"] == 5
    assert reread.json()["version"] == "v2"


@pytest.mark.req("FR-504-AC3")
def test_reading_a_profile_does_not_require_admin() -> None:
    """조회는 권한을 요구하지 않는다 — 편집만 admin 이다.

    읽기까지 막으면 조항이 요구하지 않은 것을 막는 것이고, 그러면 일반 사용자가
    「지금 어떤 제도가 적용되는가」를 볼 수 없다.
    """
    client = TestClient(create_app())
    _create(client, "읽기전용-프로파일")

    read = client.get("/regulation/profiles/읽기전용-프로파일")
    assert read.status_code == 200, read.text
    assert read.json()["name"] == "읽기전용-프로파일"


@pytest.mark.req("FR-504-AC3")
def test_cloning_a_missing_profile_is_not_confused_with_a_permission_problem() -> None:
    """없는 프로파일 복제는 404 — 403(권한)과 구분한다."""
    client = TestClient(create_app())
    missing = client.post(
        "/regulation/profiles/없는프로파일/clone",
        params={"role": _ADMIN},
        json={"name": "사본", "version": "v1"},
    )
    assert missing.status_code == 404, missing.text
