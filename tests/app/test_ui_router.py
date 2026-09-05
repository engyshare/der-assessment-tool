"""화면이 **HTTP 를 거쳐** 나오는가 — UI-1-AC1 · FR-201-AC1 · FR-504-AC3 · NFR-207-AC1.

`web/render.py` 는 세 화면을 다 그려 놓고도 **시험에서만** 불렸다
(`grep -rn "HTMLResponse" app/` 이 0건이었다). 그 상태에서 「화면이 있다」를
말하던 검사들은 **배포 코드가 부르지 않는 함수**를 직접 불러 통과했다 — 이
저장소가 R26·R51·R52b 에 세 번 밟은 형태다.

그래서 이 파일의 검사는 **하나도 `web.render` 의 함수를 직접 부르지 않는다.**
전부 `TestClient(create_app())` 를 지난다. 여기서 `render_dashboard()` 를 직접
부르면 붙들려던 것을 그대로 놓친다.

**기댓값을 소스에 박지 않는다.** 파라미터 이름은 `core.model.parameters`
카탈로그가, 자원 종류는 레지스트리가 정본이므로 그쪽에서 가져와 대조한다 —
박으면 카탈로그가 늘 때 이 검사가 조용히 낡는다.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from core.model.composition import available_resource_tags
from web.render import DEMO_MODEL, equipment_setting_fields


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.mark.req("UI-1-AC1")
def test_root_serves_the_dashboard_with_every_equipment_setting_field(
    client: TestClient,
) -> None:
    """`GET /` 가 **대시보드**를 낸다 — 200 만으로는 성립하지 않는다.

    「전체 파라미터 단일 화면이 전체 파라미터를 그린다」가 조항이므로, 카탈로그가 펴는
    필드가 **전부** 나오는지 본다. 하나라도 있으면 통과로 두면 화면이 앞의 몇
    개만 그려도 초록불이다.
    """
    response = client.get("/")

    assert response.status_code == 200, response.text
    assert "text/html" in response.headers["content-type"]

    body = response.text
    assert 'id="main"' in body, "받은 것이 대시보드가 아니다 — 본문 랜드마크가 없다"

    fields = equipment_setting_fields(DEMO_MODEL)
    assert fields, "카탈로그가 파라미터를 한 건도 펴지 않았다 — 대조할 것이 없다"
    missing = [
        field["parameter"]
        for field in fields
        if f'data-parameter="{field["parameter"]}"' not in body
    ]
    assert not missing, f"설비 설정 화면에 빠진 파라미터: {missing}"


@pytest.mark.req("FR-201-AC1")
def test_model_composer_screen_is_served_over_http(client: TestClient) -> None:
    """`GET /ui/model-composer` 가 자원 구성 화면을 낸다 — FR-201-AC1 「GUI에서」.

    자원 종류는 **레지스트리에서 가져와** 대조한다. 화면이 종류를 자기 안에
    적어 두면 자원 1종 추가가 화면 수정을 부르고, 조항의 「구성 변경 시 엔진
    코드 변경이 발생하지 않는다」가 서버에서만 성립하고 화면에서 깨진다.
    """
    response = client.get("/ui/model-composer")

    assert response.status_code == 200, response.text
    assert "text/html" in response.headers["content-type"]

    body = response.text
    tags = available_resource_tags()
    assert tags, "레지스트리가 자원 종류를 한 건도 내지 않았다 — 대조할 것이 없다"
    missing = [tag for tag in tags if f'<option value="{tag}">' not in body]
    assert not missing, f"자원 구성 화면에 빠진 자원 종류: {missing}"


@pytest.mark.req("FR-504-AC3")
def test_regulation_admin_screen_is_served_over_http(client: TestClient) -> None:
    """`GET /ui/regulation-admin` 가 제도 편집 화면을 낸다 — FR-504-AC3 「웹 UI 에서」.

    조항은 *「admin 권한 사용자가 **웹 UI 에서** 프로파일을 생성·복제·수정할 수
    있다」* 다. 프로파일 이름만 보면 「화면이 떴다」와 「편집할 수 있다」가
    구별되지 않으므로 **세 조작이 화면에 있는지**까지 본다.
    """
    response = client.get("/ui/regulation-admin")

    assert response.status_code == 200, response.text
    assert "text/html" in response.headers["content-type"]

    body = response.text
    assert "현행" in body, "제도 편집 화면에 프로파일 이름이 없다"
    for operation in ("create", "clone", "update"):
        assert f'value="{operation}"' in body, (
            f"웹 UI 에 {operation} 조작이 없다 — 조항의 세 낱말 중 하나가 빠졌다"
        )


@pytest.mark.req("NFR-207-AC1")
def test_ui_routes_are_collected_without_touching_a_registry_file() -> None:
    """`app/routers/ui.py` 를 **놓기만 해서** 라우트가 늘었다 — NFR-207-AC1.

    ⚠ **총 경로 수를 박지 않는다.** 다른 구획이 라우트를 하나 더하면 박은 수가
    틀리고, 그때 사람은 이 검사를 「수를 고쳐 통과시키는」 것으로 다룬다.
    이 파일이 들고 온 경로가 **실제로 앱에 있는지**를 본다.

    ⚠⚠ **`app.routes` 를 훑지 않는다 — 그 목록의 모양이 FastAPI 판마다 다르다.**
    0.141 은 `include_router` 가 넣은 것을 `_IncludedRouter` 한 겹으로 감싸
    `route.path` 가 없고, 0.136 은 그것을 평평하게 편다. 로컬(0.136)에서
    초록불이던 이 검사가 **CI(0.141)에서만 빨간불**이었고, 그때 보이는 것은
    「라우터가 수집되지 않았다」라는 **틀린 진술**이었다 — 라우터는 수집돼
    있었고 응답도 정상이었다.
    ⇒ **앱이 공표하는 경로 목록(OpenAPI)을 본다.** 그것이 판을 건너 같은
    뜻을 갖는 유일한 자리이며, 내부 자료구조가 아니라 **앱의 대외 계약**이다.
    """
    paths = set(create_app().openapi()["paths"])

    for path in ("/", "/ui/model-composer", "/ui/regulation-admin", "/static/{filename}"):
        assert path in paths, (
            f"{path} 가 수집되지 않았다 — `app/main.py` 를 고치지 않고 파일만 "
            "놓으면 라우트가 는다는 것이 NFR-207-AC1 이다"
        )


def test_static_css_is_served_as_text_css(client: TestClient) -> None:
    """`/static/wp12.css` 가 **`text/css`** 로 나간다.

    ⚠ **`req()` 마커를 달지 않았다.** 정적 파일 서빙에 대응하는 수용기준이
    spec 에 없다. 없는 조항을 지어 붙이면 매핑표가 거짓 진술을 싣는다.

    `text/plain` 으로 나가면 브라우저가 스타일시트를 적용하지 않는다 — 상태
    코드 200 은 그대로이므로 **화면이 무너진 채로 초록불**이 된다.
    """
    response = client.get("/static/wp12.css")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/css"), (
        response.headers["content-type"]
    )
    assert response.text.strip(), "빈 파일을 내보냈다"


def test_static_route_does_not_reach_outside_the_static_directory(
    client: TestClient,
) -> None:
    """목록 밖 이름은 열리지 않는다 — 인코딩한 형태도 마찬가지다.

    ⚠ **`req()` 마커를 달지 않았다** — 위와 같은 사유다.

    두 형태를 함께 재는 이유: `/static/../pyproject.toml` 은 클라이언트가 점
    구간을 정규화해 **라우터에 닿지도 못하고**, `/static/..%2Fpyproject.toml`
    은 **화이트리스트에서 걸린다.** 앞의 것만 재면 화이트리스트를 지워도
    초록불이다.
    """
    for target in ("/static/../pyproject.toml", "/static/..%2Fpyproject.toml"):
        response = client.get(target)
        assert response.status_code == 404, (
            f"{target} 이(가) {response.status_code} 로 응답했다 — "
            "정적 경로가 `web/static/` 밖에 닿는다"
        )
        assert "[project]" not in response.text, f"{target} 이 저장소 파일을 냈다"
