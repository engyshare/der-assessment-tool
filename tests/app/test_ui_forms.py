"""화면의 단추가 **실제로 먹는가** — FR-201-AC1 · FR-504-AC3 · NFR-303-M1.

R62/WP-5 가 브라우저로 눌러 보고 잡은 것이 여기 있다. 자원 구성 화면의 단추
셋과 제도 관리 화면의 폼 셋은 **눌리면 영어 `422`** 를 냈다 — 템플릿이
urlencoded 를 보내는데 `action` 이 가리키던 것은 JSON API 였다. 「화면이 있다」
를 재던 검사들은 그 상태에서 전부 초록불이었다. **화면을 여는 것과 화면이
먹는 것은 다른 사실**이고, 이 파일이 재는 것은 뒤쪽이다.

## 하나도 `web.render`·서비스를 직접 부르지 않는다

전부 `TestClient(create_app())` 를 지난다. 여기서 `ModelCompositionService` 를
직접 만들어 재면 붙들려던 것(**HTTP 를 지나 화면까지 닿는가**)을 그대로 놓친다
— `tests/app/test_ui_router.py` 머리말이 같은 판단을 적어 두었다.

## ⚠⚠ 절대 수를 박지 않는다 — **전후를 비교한다**

`app/routers/models.py`·`regulation.py` 의 `_service` 는 **모듈 수준 인스턴스**다.
같은 프로세스 안에서 상태가 남으므로 「자원이 둘이다」를 박으면 이 파일이
어느 순서로 도는가에 결과가 매인다. 재는 것은 늘 **이 조작이 무엇을 바꿨는가**
이며, 조작 전에 세고 조작 뒤에 다시 세어 그 차이를 본다.

같은 이유로 **이름을 겹치지 않게 짓는다.** 구성 안에서 이름이 겹치면 복제·추가가
거부되는 것이 조항의 동작이고(`_reject_duplicate_name`), 그 거부는 「단추가 안
먹는다」와 화면에서 구별되지 않는다.

## 앱 내부 자료구조를 훑지 않는다

FastAPI 판이 로컬(0.136)과 CI(3.11 · 0.141)에서 다르다. 라우트 표를 뒤지는
검사는 그 차이로 빨간불이 되고, 그 빨간불은 화면이 멀쩡할 때도 난다. 보는
것은 **응답**뿐이다.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from core.model.composition import available_resource_tags

#: 3요소 — `run_result.html` 의 `#validation` 절이 싣는 말머리 그대로다.
_THREE_PARTS = ("필드:", "사유:", "조치:")

_COMPOSER = "/ui/model-composer"
_REGULATION = "/ui/regulation-admin"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _resource_names(client: TestClient) -> tuple[str, ...]:
    """자원 구성 **화면이 실제로 그린** 자원 이름들.

    ⚠ 서비스에 물어보지 않는다. 서비스가 들고 있는데 화면이 안 그리는 상태가
    이 라운드가 붙들려는 것 중 하나이며, 서비스에 물으면 그 상태가 초록불이다.
    """
    response = client.get(_COMPOSER)
    assert response.status_code == 200, response.text
    return tuple(re.findall(r'data-resource-name="([^"]*)"', response.text))


def _item_keys(client: TestClient, profile: str) -> tuple[str, ...]:
    """제도 관리 **화면이 실제로 그린** 항목키들."""
    response = client.get(_REGULATION, params={"profile": profile})
    assert response.status_code == 200, response.text
    return tuple(re.findall(r'data-item-key="([^"]*)"', response.text))


def _assert_three_parts(body: str) -> None:
    """거부가 **필드·사유·조치 셋을 화면으로** 냈다 (`NFR-303`).

    ⚠ 셋을 **셋 다** 본다. 하나라도 빠지면 사람에게 남는 선택은 값을 하나씩
    바꿔 보는 것이고, 그때 가장 쉬운 선택이 「그냥 참으로 두기」다.
    """
    missing = [part for part in _THREE_PARTS if part not in body]
    assert not missing, f"거부 화면에 빠진 3요소: {missing}\n문면: {body[:400]}"


# ── 자원 구성 화면의 단추 셋 (FR-201-AC1) ──────────────────────────────────


@pytest.mark.req("FR-201-AC1")
def test_duplicating_a_resource_from_the_screen_actually_adds_one(
    client: TestClient,
) -> None:
    """★ **자원 복제가 실제로 먹는다** — 303 을 받고 화면의 자원이 는다.

    ⚠ 303 만 재면 안 된다. 리다이렉트는 조작이 **일어났다**를 말하지 않는다 —
    WP-5 이전의 화면은 `422` 였으므로 303 만으로도 개선이지만, 그 다음 화면이
    편집 전 구성을 그대로 그리면 사용자에게는 아무것도 안 바뀐 것과 같다.
    """
    before = _resource_names(client)
    assert before, "화면에 복제할 자원이 없다 — 잴 것이 없다"
    source = before[0]
    clone = f"{source}-복제-{len(before)}"

    posted = client.post(
        f"{_COMPOSER}/resources/{source}/duplicate",
        data={"new_name": clone},
        follow_redirects=False,
    )

    assert posted.status_code == 303, (
        f"복제 폼이 {posted.status_code} 를 냈다 — 303 이 아니면 새로고침이 "
        f"같은 복제를 다시 한다.\n본문: {posted.text[:400]}"
    )
    assert posted.headers["location"] == _COMPOSER, (
        f"복제 뒤 되돌아간 곳이 화면이 아니다: {posted.headers.get('location')!r}"
    )

    after = _resource_names(client)
    assert len(after) == len(before) + 1, (
        f"복제했는데 화면의 자원 수가 {len(before)} → {len(after)} 다"
    )
    assert clone in after, f"복제본 {clone!r} 이 화면에 없다 — 그린 것: {after}"


@pytest.mark.req("FR-201-AC1")
def test_adding_and_deleting_a_resource_from_the_screen_actually_works(
    client: TestClient,
) -> None:
    """★ **자원 추가·삭제도 먹는다** — 늘었다가 다시 준다.

    ⚠ 추가할 종류를 소스에 박지 않는다. 레지스트리(`available_resource_tags`)가
    정본이며, 박으면 자원 1종이 늘거나 이름이 바뀌는 날 이 검사가 없는 종류를
    고르면서 「화면이 틀렸다」로 빨간불이 된다.

    ⚠ 추가와 삭제를 **함께** 잰다. 추가만 재면 「늘기만 하는 화면」이 초록불이고,
    삭제만 재면 지울 것을 이 검사가 만들 수 없다.
    """
    tags = available_resource_tags()
    assert tags, "레지스트리가 자원 종류를 한 건도 내지 않았다 — 고를 것이 없다"

    before = _resource_names(client)
    name = f"검사용 자원-{len(before)}"

    added = client.post(
        f"{_COMPOSER}/resources",
        data={"tag": tags[0], "name": name},
        follow_redirects=False,
    )
    assert added.status_code == 303, f"추가 폼이 {added.status_code}: {added.text[:400]}"

    grown = _resource_names(client)
    assert len(grown) == len(before) + 1, (
        f"추가했는데 화면의 자원 수가 {len(before)} → {len(grown)} 다"
    )
    assert name in grown, f"추가한 {name!r} 이 화면에 없다 — 그린 것: {grown}"

    removed = client.post(f"{_COMPOSER}/resources/{name}/delete", follow_redirects=False)
    assert removed.status_code == 303, (
        f"삭제 폼이 {removed.status_code}: {removed.text[:400]}"
    )

    shrunk = _resource_names(client)
    assert len(shrunk) == len(grown) - 1, (
        f"삭제했는데 화면의 자원 수가 {len(grown)} → {len(shrunk)} 다"
    )
    assert name not in shrunk, f"삭제한 {name!r} 이 아직 화면에 있다"


@pytest.mark.req("NFR-303-M1")
def test_a_rejected_resource_form_answers_with_html_and_three_parts(
    client: TestClient,
) -> None:
    """**틀린 입력은 400 + 3요소를 화면으로** — JSON 이 아니다.

    등록되지 않은 자원 종류를 보낸다. 브라우저가 JSON 을 받으면 사람이 읽는
    것은 영어 대괄호이며, 그 상태가 R62/WP-5 가 잡은 D1 이다.
    """
    response = client.post(
        f"{_COMPOSER}/resources",
        data={"tag": "그런 자원 없음", "name": "검사용"},
        follow_redirects=False,
    )

    assert response.status_code == 400, (
        f"등록 안 된 종류가 {response.status_code} 로 응답했다: {response.text[:400]}"
    )
    assert "text/html" in response.headers["content-type"], (
        f"거부가 화면이 아니다: {response.headers['content-type']}"
    )
    _assert_three_parts(response.text)


# ── 제도 관리 화면의 폼 셋 (FR-504-AC3) ────────────────────────────────────


@pytest.mark.req("FR-504-AC3")
def test_creating_cloning_and_revising_a_profile_from_the_screen_shows_up(
    client: TestClient,
) -> None:
    """★ **제도 프로파일 생성·복제·항목 개정이 먹는다** — 화면에 나타난다.

    셋을 한 검사에 묶는 이유: 복제할 것과 개정할 것을 **생성이 만든다**. 갈라
    두면 서로의 상태를 물려받아야 하고, 그것이 이 파일 머리말이 금지한
    「순서에 기댄 검사」다.

    ⚠ 이름을 겹치지 않게 짓는다. `_service` 가 모듈 수준이라 같은 프로세스
    안에서 앞선 검사의 프로파일이 남아 있다.
    """
    stem = f"검사용 제도-{id(client) % 100000}"
    created = client.post(
        f"{_REGULATION}/profiles?role=admin",
        data={"name": stem, "version": "v1"},
        follow_redirects=False,
    )
    assert created.status_code == 303, f"생성 폼이 {created.status_code}: {created.text[:400]}"

    screen = client.get(_REGULATION, params={"profile": stem})
    assert screen.status_code == 200, screen.text
    assert stem in screen.text, f"생성한 프로파일 {stem!r} 이 화면에 없다"

    # ── 항목 개정 — 없던 항목키가 화면에 나타나고 버전이 새것이 된다 ──
    before_keys = _item_keys(client, stem)
    key = "supply_duty.검사용"
    revised = client.post(
        f"{_REGULATION}/profiles/{stem}/items?role=admin",
        data={
            "key": key,
            "value": "0.85",
            "unit": "비율",
            "source": "검사용 근거",
            "valid_from": "",
            "version": "v2",
        },
        follow_redirects=False,
    )
    assert revised.status_code == 303, f"개정 폼이 {revised.status_code}: {revised.text[:400]}"

    after_keys = _item_keys(client, stem)
    assert len(after_keys) == len(before_keys) + 1, (
        f"개정했는데 화면의 항목 수가 {len(before_keys)} → {len(after_keys)} 다"
    )
    assert key in after_keys, f"개정한 항목 {key!r} 이 화면에 없다 — 그린 것: {after_keys}"
    assert "v2" in client.get(_REGULATION, params={"profile": stem}).text, (
        "개정이 새 버전으로 발행되지 않았다 — FR-504-AC4 의 「이전 버전으로 복원」이 "
        "성립하려면 제자리 수정이 아니어야 한다"
    )

    # ── 복제 — 원본의 항목을 그대로 든 새 프로파일이 화면에 선다 ──
    copy_name = f"{stem}-사본"
    cloned = client.post(
        f"{_REGULATION}/profiles/{stem}/clone?role=admin",
        data={"name": copy_name, "version": "v2-사본"},
        follow_redirects=False,
    )
    assert cloned.status_code == 303, f"복제 폼이 {cloned.status_code}: {cloned.text[:400]}"

    assert _item_keys(client, copy_name) == after_keys, (
        f"복제본의 항목이 원본과 다르다: {_item_keys(client, copy_name)} vs {after_keys}"
    )


@pytest.mark.req("NFR-303-M1")
def test_a_rejected_profile_form_answers_with_html_and_three_parts(
    client: TestClient,
) -> None:
    """**권한 없는 편집도 3요소를 화면으로** — 영어 JSON 이 아니다.

    ⚠ 여기서 재는 것은 **거부의 형식**이다. admin 가드 자체는
    `tests/app/test_regulation_admin_router.py` 가 JSON 출구에서 잰다 — 같은
    가드를 두 곳에서 다시 재면 한쪽이 빠져도 다른 쪽이 초록불로 덮는다.
    """
    response = client.post(
        f"{_REGULATION}/profiles?role=viewer",
        data={"name": "권한 없이 만든 것", "version": "v1"},
        follow_redirects=False,
    )

    assert response.status_code == 403, (
        f"권한 없는 생성이 {response.status_code} 로 응답했다: {response.text[:400]}"
    )
    assert "text/html" in response.headers["content-type"], (
        f"거부가 화면이 아니다: {response.headers['content-type']}"
    )
    _assert_three_parts(response.text)


# ── D3 — 목록 밖 시나리오 (NFR-303-M1) ─────────────────────────────────────


@pytest.mark.req("NFR-303-M1")
def test_an_unknown_scenario_answers_with_a_screen_not_json(
    client: TestClient,
) -> None:
    """★ **D3 — 목록 밖 시나리오가 화면으로 온다.**

    전에는 `{"detail":"\\"시나리오 'nope' 이(가) 없습니다…\\""}` 였다. 셋이
    한꺼번에 틀려 있었다 — ① 화면이 아니라 JSON 이고, ② 3요소가 없고,
    ③ `str(KeyError)` 가 `repr` 이라 **문면에 겹따옴표가 덧씌워졌다.**

    ⚠ 겹따옴표를 **본문 전체**에서 찾지 않는다. HTML 속성이 겹따옴표를 쓰므로
    본문에는 늘 있다. 보는 것은 **사유 문면 안**이다.
    """
    response = client.get("/ui/run", params={"scenario": "그런 시나리오 없음"})

    assert response.status_code == 404, (
        f"목록 밖 이름이 {response.status_code} 로 응답했다: {response.text[:400]}"
    )
    assert "text/html" in response.headers["content-type"], (
        f"목록 밖 이름이 화면으로 오지 않았다: {response.headers['content-type']}"
    )
    _assert_three_parts(response.text)

    reason = re.search(r"사유:\s*(.*?)</span>", response.text, re.DOTALL)
    assert reason is not None, f"사유 칸을 찾지 못했다: {response.text[:400]}"
    body = reason.group(1)
    assert "&#34;" not in body and "&quot;" not in body and '"' not in body, (
        f"사유 문면에 겹따옴표가 실렸다 — `str(KeyError)` 를 쓴 흔적이다: {body!r}"
    )


# ── D6 — 화면 셋이 이어져 있다 ─────────────────────────────────────────────


def test_the_three_screens_link_to_each_other(client: TestClient) -> None:
    """**D6 — 화면 셋이 이어져 있다.**

    ⚠ `req()` 마커를 달지 않았다. 화면 사이 탐색을 문면으로 요구하는 조항이
    없다 — 이것은 WP-5 가 브라우저로 잡은 결함(D6)이고, 없는 조항을 여기
    붙이면 추적표가 그 조항을 이 검사로 덮인 것으로 센다.

    ⚠ 대시보드의 `#` 앵커 다섯을 이 검사가 요구하지 않는다. 지우지 않기로 한
    것이지 세기로 한 것이 아니며, 세면 앵커 하나를 옮기는 일이 이 검사를
    깨뜨린다.
    """
    root = client.get("/")
    assert root.status_code == 200, root.text
    for target in (_COMPOSER, _REGULATION):
        assert f'href="{target}"' in root.text, (
            f"대시보드에 {target} 로 가는 링크가 없다 — 주소를 손으로 쳐야 간다"
        )

    for screen in (_COMPOSER, _REGULATION):
        page = client.get(screen)
        assert page.status_code == 200, page.text
        assert 'href="/"' in page.text, f"{screen} 에서 대시보드로 돌아갈 링크가 없다"
