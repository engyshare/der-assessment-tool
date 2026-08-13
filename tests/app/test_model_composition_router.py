"""FR-201-AC1 「GUI에서」의 서버 경로 — 자원 추가·삭제·복제.

`tests/model/test_composition.py` 가 편집 **연산**을 붙들고, 여기서는 그 연산에
**GUI 가 도달할 수 있는가**를 붙든다. 연산만 있고 경로가 없으면 조항의 「GUI에서
구성 가능하며」가 성립하지 않는다.

**응답에 `available_tags` 를 함께 요구한다.** 화면이 종류 목록을 자기 안에 적어
두면 자원 1종 추가가 화면 수정을 부르고, 조항 후반부가 서버에서만 성립한다.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import core.der
from app.main import create_app
from core.contracts.der import DER
from core.contracts.registry import discover


def _client() -> TestClient:
    return TestClient(create_app())


def _register(client: TestClient, model_name: str) -> dict[str, object]:
    response = client.post(
        "/models",
        json={
            "name": model_name,
            "resources": [
                {
                    "tag": "PV",
                    "params": {
                        "name": "옥상PV",
                        "capacity_kw": 100.0,
                        "capacity_factor": 0.15,
                    },
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _names(payload: dict[str, object]) -> list[str]:
    resources = payload["resources"]
    assert isinstance(resources, list)
    return [r["params"]["name"] for r in resources]


@pytest.mark.req("FR-201-AC1")
def test_gui_can_add_duplicate_and_delete_resources() -> None:
    """세 조작이 각각 경로를 갖고, 편집 결과가 다음 조회에 남는다."""
    client = _client()
    model = "GUI편집모델"
    _register(client, model)

    added = client.post(
        f"/models/{model}/resources",
        json={"tag": "ESS", "params": {"name": "지하ESS", "capacity_kwh": 200.0}},
    )
    assert added.status_code == 200, added.text
    assert _names(added.json()) == ["옥상PV", "지하ESS"]

    duplicated = client.post(
        f"/models/{model}/resources/옥상PV/duplicate",
        json={"new_name": "차양PV"},
    )
    assert duplicated.status_code == 200, duplicated.text
    assert _names(duplicated.json()) == ["옥상PV", "차양PV", "지하ESS"]

    deleted = client.delete(f"/models/{model}/resources/지하ESS")
    assert deleted.status_code == 200, deleted.text
    assert _names(deleted.json()) == ["옥상PV", "차양PV"]

    # **편집이 보관됐는가** — 돌려주기만 하고 보관하지 않으면 GUI 는 매 요청마다
    # 편집 전 구성을 다시 보게 되고, 사용자에게는 편집이 없던 일이 된다
    listed = client.get(f"/models/{model}/resources")
    assert listed.status_code == 200, listed.text
    assert _names(listed.json()) == ["옥상PV", "차양PV"]


@pytest.mark.req("FR-201-AC1")
def test_response_carries_registry_tags_so_the_view_need_not_know_them() -> None:
    """추가 가능한 종류를 서버가 응답에 싣고, 그 목록이 레지스트리와 같다."""
    client = _client()
    model = "종류목록모델"
    payload = _register(client, model)

    registry_tags = sorted(discover(core.der, DER))  # type: ignore[type-abstract]
    assert payload["available_tags"] == registry_tags
    assert len(registry_tags) > 1, "레지스트리가 비면 이 검사는 아무것도 붙들지 않는다"


@pytest.mark.req("FR-201-AC1")
def test_unknown_tag_is_refused_with_the_three_elements_structured() -> None:
    """등록되지 않은 종류는 400 이고, 3요소가 **구조로** 내려온다 (NFR-303).

    문자열 한 줄로 내리면 화면이 그것을 다시 파싱해 「어느 칸이 틀렸는가」를
    찾아야 하고, 메시지 형식이 바뀌면 표시가 조용히 깨진다.
    """
    client = _client()
    model = "거부모델"
    _register(client, model)

    refused = client.post(
        f"/models/{model}/resources",
        json={"tag": "가상자원", "params": {"name": "X"}},
    )
    assert refused.status_code == 400, refused.text
    detail = refused.json()["detail"]
    assert detail["field"] == "model.resource_tag"
    assert "가상자원" in detail["reason"]
    assert detail["action"].strip()

    # 거부된 편집이 구성에 남지 않았다
    listed = client.get(f"/models/{model}/resources")
    assert _names(listed.json()) == ["옥상PV"]


@pytest.mark.req("FR-201-AC1")
def test_missing_model_is_not_confused_with_a_bad_edit() -> None:
    """보관되지 않은 모델은 404 — 400(잘못된 편집)과 구분한다."""
    client = _client()
    missing = client.get("/models/없는모델/resources")
    assert missing.status_code == 404, missing.text

    edit = client.post(
        "/models/없는모델/resources",
        json={"tag": "PV", "params": {"name": "X", "capacity_kw": 1.0}},
    )
    assert edit.status_code == 404, edit.text
