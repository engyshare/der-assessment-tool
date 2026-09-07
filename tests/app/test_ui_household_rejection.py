"""**거부가 화면에서 읽히는가** — 가구 수 칸이 낸 거부 (R64/WP-8b · `NFR-303-M1`).

## ⚠⚠ R65/WP-2c — **재던 거부가 사라졌다. 재는 성질은 그대로 둔다**

이 파일이 태우던 거부는 *「가구 수를 3호 이상으로 적으면 낮에도 부하가 태양광을
넘어 PV 잉여가 하루 종일 0 이 되고, 태양광 잉여로만 충전하는 ESS 가 거부한다」*
(`core/der/ess_schedule.py::check_pv_surplus_profile`)였다.

**그 거부는 R65 에 사라졌다** — 없앤 것이 아니라 **원인이 없어졌다.** 부하만
단지 규모로 커지고 설비는 한 호분이던 것이 어긋남이었고, 설계 변수 셋(태양광
용량·ESS 용량·ESS 정격출력)이 같은 배수를 타면서 20호 단지에서도 낮에 잉여가
남는다. ⛔ **검사를 풀어 통과시킨 것이 아니다** — `check_pv_surplus_profile` 은
한 자도 바뀌지 않았고, 잉여가 정말 없는 구성에서는 그대로 거부한다.

⇒ 그래서 **태우는 입력을 바꿨다.** 화면의 같은 칸이 내는 거부 중 지금도 확실히
서는 것은 `load.household.count` 의 3요소 거부다(`0` 호 · `core/casegrid/
household_scale.py::resolve_household_count`). 재는 성질 셋은 한 자도 바뀌지
않았다:

## 무엇을 재는가

    ① `500` 이 아니라 **`400`** 이다 — 서버가 터진 것이 아니라 입력을 거부한 것
    ② 화면이 **필드·사유·조치 셋**을 글자로 싣는다 (`NFR-303`)
    ③ 그 조치가 **화면에 있는 손잡이**를 가리킨다 — 화면 사용자가 할 수 있는 일

## ⚠ 문턱을 이 파일이 정하지 않는다

몇 호부터 무엇이 거부되는지는 **자산·대장·설비 구성이 정하는 사실**이며, 그것을
여기 수로 박으면 그쪽이 바뀌는 날 이 검사가 조용히 낡는다(R65 가 정확히 그 일을
겪었다). 그래서 `_COUNTS` 는 **거부가 나든 안 나든 500 이 아니다**를 규모마다
함께 잰다 — 그 성질이 이 파일의 본론이다. `_REFUSING_COUNT` 는 자산·설비가
아니라 **규칙 하나**(1 이상의 정수)가 거부하는 값이라 그쪽이 움직여도 낡지 않는다.

⚠ 조치 문면 자체는 그 거부를 내는 자리
(`core/casegrid/household_scale.py::resolve_household_count`)가 정본으로 갖는다.
여기서는 **그 문면이 화면까지 오는가**만 본다 — 두 곳에서 문면을 적으면 한쪽만
고쳐지는 날이 온다.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.main import create_app
from core.casegrid.household_scale import resolve_household_count
from core.contracts.validation import ValidationError

#: 화면으로 태워 보는 규모. **1·2호는 통과하고 3호 이상은 거부되는 것이 착수
#: 시점의 실측**이지만(2026-09-06 · `.orch/R64/result_8b.md` ⑤), 이 파일은 그
#: 문턱을 단언하지 않는다 — 어느 규모에서도 **500 이 나오지 않는다**를 잰다.
#: ⚠ 규모를 더 늘리지 않는다 — 한 규모가 화면 한 번의 전체 실행이고, 재는 성질
#: (「500 이 아니다」)은 규모를 늘려도 더 세게 서지 않는다.
_COUNTS: tuple[str, ...] = ("2", "3", "10")

#: 거부가 확실히 나는 값. **`0` 은 규칙이 거부한다** — *「가구 수는 1 이상의
#: 정수여야 합니다」*(`resolve_household_count`). ⚠ 종전에는 `"10"`(잉여가
#: 사라져 ESS 가 거부하는 규모)이었고, R65 가 설비에 배수를 걸면서 그 규모가
#: 통과하게 됐다 — 머리말 ⚠⚠ 참조. 이 값은 **자산·설비 구성과 무관**하다.
_REFUSING_COUNT = "0"

_SCENARIO = "scenario_unsubsidized"
_SCREENS: tuple[str, ...] = ("/ui/run", "/ui/verify")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(scope="module")
def refusals(client: TestClient) -> dict[str, Response]:
    """화면마다 **거부 응답 하나** — 모듈에서 한 번만 태운다.

    ⚠ 검사마다 다시 태우지 않는다. 한 번의 요청이 한 번의 전체 실행이고, 세
    검사가 각자 태우면 같은 수를 세 번 만드느라 시간만 늘어난다.
    """
    return {
        screen: client.get(
            screen, params={"scenario": _SCENARIO, "household_count": _REFUSING_COUNT}
        )
        for screen in _SCREENS
    }


def _rejection() -> ValidationError:
    """거부가 실제로 내는 셋 — **정본에게 물어서** 얻는다.

    ⚠ 문면을 이 파일에 베껴 적지 않는다. 베끼면 문면을 다듬는 날 화면 검사가
    빨간불이 되고, 그때 고쳐지는 것은 **검사의 사본** 쪽이다.
    """
    try:
        resolve_household_count(int(_REFUSING_COUNT))
    except ValidationError as exc:
        return exc
    raise AssertionError(
        f"{_REFUSING_COUNT}호가 거부되지 않았다 — 이 파일의 전제가 무너졌다"
    )


@pytest.mark.req("NFR-303-M1")
@pytest.mark.parametrize("screen", _SCREENS)
@pytest.mark.parametrize("count", _COUNTS)
def test_no_household_count_ever_makes_the_screen_a_server_error(
    client: TestClient, screen: str, count: str
) -> None:
    """★★★ **500 이 나오지 않는다** — 사용자는 가구 수를 적었을 뿐이다.

    500 은 *「서버가 터졌다」* 이고 거부는 *「입력을 받아들일 수 없다」* 다. 둘을
    같은 코드로 내면 검토자가 **저장소의 결함**과 **자기 입력의 문제**를 가릴 수
    없다.
    """
    params = {"scenario": _SCENARIO}
    if count:
        params["household_count"] = count
    response = client.get(screen, params=params)
    assert response.status_code in {200, 400}, (
        f"{screen} · {count!r}호 → {response.status_code}"
    )


@pytest.mark.req("NFR-303-M1")
@pytest.mark.parametrize("screen", _SCREENS)
def test_the_refusal_reaches_the_screen_as_three_readable_parts(
    refusals: dict[str, Response], screen: str
) -> None:
    """★★ 필드·사유·조치 셋이 **글자로** 화면에 온다 (`NFR-303`).

    JSON 으로 내리면 브라우저가 그것을 사람이 읽을 모양으로 그리지 못한다 —
    R62/WP-5 가 브라우저로 잡은 **D3** 이 그 상태였다.
    """
    response = refusals[screen]
    refusal = _rejection()
    assert response.status_code == 400, (
        f"{_REFUSING_COUNT}호가 통과했다 — 규칙이 바뀌어 이 검사의 전제가 "
        "무너졌다면 거부가 나는 값을 다시 고르라"
    )
    body = response.text
    assert f"필드: {refusal.field}" in body
    assert refusal.reason in body, "사유 문면이 화면까지 오지 않았다"
    assert refusal.action in body, "조치 문면이 화면까지 오지 않았다"


@pytest.mark.req("NFR-303-M1")
@pytest.mark.parametrize("screen", _SCREENS)
def test_the_action_on_screen_points_at_a_knob_the_screen_has(
    refusals: dict[str, Response], screen: str
) -> None:
    """★★★ 화면에 온 조치가 **그 화면에 있는 칸**을 가리킨다.

    「분석 실행」 폼이 가진 칸은 가구 수 · 히트펌프 부하 · 전기차 부하다. 조치가
    `pv_surplus_profile_kwh` 를 지정하라고 말하면 사용자가 할 수 있는 일이 0개다.
    """
    body = refusals[screen].text
    assert "가구 수" in body
    assert "조치: pv_surplus_profile_kwh" not in body
