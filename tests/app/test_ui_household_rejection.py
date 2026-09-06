"""**거부가 화면에서 읽히는가** — 가구 수를 늘린 실행 (R64/WP-8b · `NFR-303-M1`).

## 무엇을 재는가

가구 수를 3호 이상으로 적으면 낮에도 부하가 태양광을 넘어 PV 잉여가 하루 종일
0 이 되고, 태양광 잉여로만 충전하는 ESS 가 **거부한다**
(`core/der/ess_schedule.py::check_pv_surplus_profile`).

⛔ **그 거부를 없애지 않는다.** 한 해 내내 PV 잉여가 없는 단지에 태양광 연계
ESS 를 놓는 것은 사업 설계의 오류일 수 있고, 조용히 통과시키면 **없는 충전으로
편익이 난다.** 재는 것은 *「거부가 사람이 읽을 수 있는 모양으로 화면에 오는가」*
하나다:

    ① `500` 이 아니라 **`400`** 이다 — 서버가 터진 것이 아니라 입력을 거부한 것
    ② 화면이 **필드·사유·조치 셋**을 글자로 싣는다 (`NFR-303`)
    ③ 그 조치가 **화면에 있는 손잡이**를 가리킨다 — 화면 사용자가 할 수 있는 일

## ⚠ 문턱을 이 파일이 정하지 않는다

몇 호부터 거부되는지는 **자산·대장이 정하는 사실**이며(발전 형상과 가구 부하의
크기), 그것을 여기 수로 박으면 자산이 바뀌는 날 이 검사가 조용히 낡는다. 그래서
`_REFUSING_COUNT` 는 *「거부가 나는 규모」* 를 찾아 쓰지 않고, **거부가 나든 안
나든 500 이 아니다**를 규모마다 함께 잰다 — 그 성질이 이 파일의 본론이다.

⚠ 조치 문면 자체는 `tests/der/test_ess_schedule_rejection_action.py` 가 정본으로
잰다. 여기서는 **그 문면이 화면까지 오는가**만 본다 — 두 곳에서 문면을 적으면
한쪽만 고쳐지는 날이 온다.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.main import create_app
from core.contracts.validation import ValidationError
from core.der.ess_schedule import check_pv_surplus_profile

#: 화면으로 태워 보는 규모. **1·2호는 통과하고 3호 이상은 거부되는 것이 착수
#: 시점의 실측**이지만(2026-09-06 · `.orch/R64/result_8b.md` ⑤), 이 파일은 그
#: 문턱을 단언하지 않는다 — 어느 규모에서도 **500 이 나오지 않는다**를 잰다.
#: ⚠ 규모를 더 늘리지 않는다 — 한 규모가 화면 한 번의 전체 실행이고, 재는 성질
#: (「500 이 아니다」)은 규모를 늘려도 더 세게 서지 않는다.
_COUNTS: tuple[str, ...] = ("2", "3", "10")

#: 거부가 확실히 나는 규모. 3호에서 이미 나므로 넉넉히 위를 쓴다 — 자산이
#: 바뀌어 여기서도 통과하게 되면 이 검사는 **건너뛰지 않고** 그 사실을 말한다.
_REFUSING_COUNT = "10"

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


def _rejection_action() -> str:
    """거부가 실제로 내는 조치 문면 — **정본에게 물어서** 얻는다.

    ⚠ 문면을 이 파일에 베껴 적지 않는다. 베끼면 문면을 다듬는 날 화면 검사가
    빨간불이 되고, 그때 고쳐지는 것은 **검사의 사본** 쪽이다.
    """
    try:
        check_pv_surplus_profile(None, uses_pv_surplus=True, name="탐침")
    except ValidationError as exc:
        return exc.action
    raise AssertionError("빈 PV 잉여가 거부되지 않았다 — 이 파일의 전제가 무너졌다")


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
    assert response.status_code == 400, (
        f"{_REFUSING_COUNT}호가 통과했다 — 자산이 바뀌어 이 검사의 전제가 "
        "무너졌다면 거부가 나는 규모를 다시 재라"
    )
    body = response.text
    assert "필드: ess.pv_surplus_profile_kwh" in body
    assert "잉여 시계열이 없거나 전부 0입니다" in body
    assert _rejection_action() in body, "조치 문면이 화면까지 오지 않았다"


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
