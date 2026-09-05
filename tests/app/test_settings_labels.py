"""설정 화면이 대장 항목을 **무엇으로 부르는가** — 착수 목록 54.

## ★★ 이 파일이 가르는 것은 「사람이 읽는 자리」와 「기계가 읽는 자리」다

낱말 축(R63/S1)이 **대시보드**에서 세운 방식을 그대로 쓴다
(`tests/web/test_dashboard.py` 의 `human_text`·`machine_attribute_text` ·
`test_no_parameter_variable_name_is_printed_where_people_read` 와 그 짝).
대장 키(`capex.pv.rooftop` 꼴)는 **폼 제출의 키**이므로
`id`·`for`·`name`·`data-ledger-key`·`href` 에는 **있어야 한다** — 지우면 폼이
아무 값도 받지 못한 채 303 을 낸다. 없어야 하는 곳은 `<label>` 글자·`<td>` 본문
· `aria-label` 처럼 **사람이 눈으로 읽는 자리**다.

⚠ **한쪽만 재면 「변수명을 지웠다」와 「폼을 부쉈다」가 검사에서 같아진다.**
그래서 두 방향을 짝으로 둔다.

## ⚠ 왜 대시보드 검사로 충분하지 않았나

`tests/web/test_dashboard.py` 가 재는 모집단은 **자원 파라미터 이름**
(`resource_parameters` 가 펴는 것)이다. 대장 키는 그 모집단에 없다. 그래서
대시보드가 「사람이 읽는 자리 0건」인 채로, 설정 화면 본문에는 대장 키 꼴이
**159건** 서 있었다(브라우저 실측 `.orch/R63/result_V2.md` §0). 모집단이 다르면
검사도 따로 서야 한다 — `tests/app/test_screen_words.py` 가 「화면이 하나 늘
때 그 화면만 옛 낱말로 남는다」에 대해 같은 판단을 적었다.

## `web.render_*` 를 직접 부르지 않는다

전부 `TestClient(create_app())` 를 지난다. 문맥 함수를 직접 부르면 「배포 코드가
부르지 않는 함수가 초록불을 만든다」를 그대로 다시 밟는다.

## ⚠ `@pytest.mark.req(...)` — **달지 않았다**

사용자 요구(*「변수명을 병기하지 않음」*)를 받는 수용기준이 spec 에 없다.
`UI-1-AC1`(마법사 + 고급 모드 병행)은 **대시보드**의 조항이라 이 화면에 달면
`docs/traceability.md` 가 거짓 인용을 싣는다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from core.assumption.provider import AssumptionSet
from tests.web.test_dashboard import human_text, machine_attribute_text

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"

#: 저장은 **303** 으로 되돌리고 그 주소에 방금 저장한 번호가 있다.
_APPLIED_ID = re.compile(r"applied=(\d+)")

#: 설정 이름 — ⚠ **대장 키를 닮은 글자를 넣지 않는다.** 이 이름은 「저장한 설정」
#: 목록에 사람이 읽는 글자로 실리므로, 키를 넣으면 이 파일이 심어 둔 글자 때문에
#: 검사가 빨간불이 된다.
_SETTINGS_NAME = "라벨 검사용 설정"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _ledger() -> AssumptionSet:
    return AssumptionSet.load_from_yaml(str(_ASSUMPTIONS))


def _keys() -> tuple[str, ...]:
    """모집단은 **대장이 정한다** — 수를 이 파일에 박지 않는다."""
    keys = tuple(_ledger().items())
    assert keys, "대장에서 항목을 하나도 읽지 못했다 — 잴 것이 없다"
    return keys


def _titles() -> tuple[str, ...]:
    return tuple(item.title for item in _ledger().items().values())


def _a_key_with_a_numeric_value() -> str:
    """고쳐 볼 대장 항목 하나 — **수치 항목**이어야 폼이 받는다.

    ⚠ 어느 키인지는 여기 적지 않고 대장에 물어서 고른다. 박아 두면 그 항목이
    이름을 바꾸는 날 이 검사가 「화면이 틀렸다」로 빨간불이 된다.
    """
    for key, item in _ledger().items().items():
        if isinstance(item.value, (int, float)) and not isinstance(item.value, bool):
            return key
    raise AssertionError("대장에 수치 항목이 하나도 없다")


def _saved_settings(client: TestClient, *, key: str, value: str) -> int:
    response = client.post(
        "/ui/settings",
        data={"name": _SETTINGS_NAME, "description": "", f"val-{key}": value},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text[:400]
    match = _APPLIED_ID.search(response.headers["location"])
    assert match is not None, response.headers["location"]
    return int(match.group(1))


def test_no_ledger_key_is_printed_where_people_read(client: TestClient) -> None:
    """★★★ **설정 화면의 사람이 읽는 자리에 대장 키가 0 건이다.**

    사용자 문면: *「"옥상 태양광 · azimuth_deg" 와 같이 coding 상의 변수명을
    병기하지 않음」*(`docs/decisions-2026-09-05-R63.md` §1 「용어」).

    ⚠ **「하나만 확인」으로 두지 않는다 — 전건을 센다.** 한 칸을 고치고 나머지
    마흔 칸에 키가 남은 상태가 초록불이 되면, 그것이 R63 착수 시점의 실측과
    같은 상태다(설정 화면 본문 변수명 꼴 159건).
    """
    screen = client.get("/ui/settings")
    assert screen.status_code == 200, screen.text[:400]

    corpus = human_text(screen.text)
    leaked = sorted(key for key in _keys() if key in corpus)

    assert not leaked, (
        f"사람이 읽는 자리에 대장 키가 {len(leaked)}건 남아 있다: {leaked}"
    )


def test_the_ledger_key_is_still_in_the_places_the_form_reads(
    client: TestClient,
) -> None:
    """★★ **그런데 기계가 읽는 자리에는 전건 남아 있다** — 폼 제출이 그것으로 된다.

    ⚠ 위 검사만 두면 「키를 지웠다」의 가장 싼 통과 방법이 **`id`·`name`·
    `data-ledger-key` 까지 지우는 것**이고, 그때 설정 폼은 아무 값도 못 받은 채
    303 을 낸다. 두 방향을 짝으로 두는 것이 이 저장소가 세운 방식이다.
    """
    screen = client.get("/ui/settings")
    assert screen.status_code == 200, screen.text[:400]

    corpus = machine_attribute_text(screen.text)
    missing = sorted(key for key in _keys() if key not in corpus)

    assert not missing, (
        f"기계가 읽는 자리에서 대장 키 {len(missing)}건이 사라졌다: {missing} — "
        "폼이 그 항목의 값을 받지 못한다"
    )


def test_every_ledger_item_label_stands_on_the_screen(client: TestClient) -> None:
    """★★ **라벨이 실제로 서 있다** — 지운 것과 세운 것을 함께 잰다.

    ⚠ 위 두 검사만 두면 통과의 가장 싼 길이 **그 칸을 통째로 비우는 것**이다.
    그때 사용자는 항목을 부르는 이름을 화면에서 잃고 검사는 초록불이다.
    """
    corpus = human_text(client.get("/ui/settings").text)

    missing = sorted(title for title in _titles() if title not in corpus)

    assert not missing, f"화면에 서지 않은 라벨 {len(missing)}건: {missing}"


def test_the_group_heading_is_not_a_key_fragment(client: TestClient) -> None:
    """★ **묶음 머리도 사람의 말이다** — 키의 첫 마디를 그대로 인쇄하지 않는다.

    묶음은 대장 키의 첫 마디(`capex`·`capacity_factor` …)로 짓는다. 그 조각은
    **온전한 키가 아니라서** 위 검사가 못 본다 — 그런데 사람이 읽는
    `<legend>` 에 서면 화면은 여전히 변수명을 인쇄한다.
    """
    corpus = human_text(client.get("/ui/settings").text)
    heads = sorted({key.split(".")[0] for key in _keys()})

    leaked = [head for head in heads if head in corpus]

    assert not leaked, (
        f"묶음 머리에 키 조각이 남아 있다: {leaked} — 한국어 이름은 "
        "docs/assumptions.yaml 의 `group_titles:` 가 정본이다"
    )


def test_the_applied_override_table_names_items_by_label(client: TestClient) -> None:
    """★★ **「기준 전제 대비 변경 항목」 표도 라벨로 부른다.**

    ⚠ 이 절은 `{% if applied %}` 안에 있어 **설정을 저장해 적용해야** 그려진다.
    GET 만 하면 재지 않은 채 통과한다 — `tests/app/test_screen_words.py` 가 같은
    자리에서 같은 함정을 적었다.

    ⚠ 여기서도 키는 `data-override-key` 에 남는다 — 검토자가 산출물과 화면을
    기계로 대조하는 자리이며, `tests/app/test_ui_scenarios.py` 가 그것을 잰다.
    """
    key = _a_key_with_a_numeric_value()
    base = _ledger().items()[key].value
    assert isinstance(base, (int, float))
    settings_id = _saved_settings(client, key=key, value=str(base * 2 + 1))

    applied = client.get("/ui/settings", params={"applied": settings_id})
    assert applied.status_code == 200, applied.text[:400]

    corpus = human_text(applied.text)
    title = _ledger().items()[key].title

    assert f'data-override-key="{key}"' in applied.text, (
        "변경 항목 표가 기계 자리에 키를 싣지 않았다"
    )
    assert title in corpus, f"변경 항목 표가 {key} 를 라벨({title!r})로 부르지 않는다"
    assert key not in corpus, (
        f"변경 항목 표가 사람이 읽는 자리에 {key} 를 인쇄한다"
    )


#: 브라우저 검수(`.orch/R63/result_V2.md` §0)가 「변수명 꼴」을 센 자.
#: `^[a-z][a-z0-9]*(_[a-z0-9]+)+$` — 소문자와 밑줄로 이어 붙인 식별자.
_VARIABLE_NAME = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")


def test_no_variable_name_shaped_token_is_printed_where_people_read(
    client: TestClient,
) -> None:
    """★★ **변수명 꼴이 사람이 읽는 자리에 0 건이다** — 실측이 쓴 자를 그대로 쓴다.

    ⚠ 위 「대장 키」 검사만으로는 부족하다는 것을 이 축이 실물로 밟았다: 대장 키를
    전부 라벨로 바꾼 뒤에도 「사용자가 지목한 다섯」 표의 비고 칸이
    `PV · generation_profile_kwh` 를 인쇄하고 있었다 — 그 꼴은 온전한 대장 키가
    아니라 **자원 파라미터 이름**이라 키 검사의 모집단 밖이었고, 그러면서
    사용자 문면이 금지한 **병기**(*「"옥상 태양광 · azimuth_deg" 와 같이」*) 바로
    그 모양이었다.

    ⇒ 모집단을 「대장이 아는 이름」으로 좁히지 않고 **꼴로** 잰다. 브라우저 검수가
    쓴 자와 같은 것이어야 그 실측(설정 화면 159건)과 이 검사가 같은 것을 센다.
    """
    corpus = human_text(client.get("/ui/settings").text)
    tokens = sorted(
        {
            token
            for token in re.split(r"[^A-Za-z0-9_.]+", corpus)
            if _VARIABLE_NAME.match(token)
        }
    )

    assert not tokens, (
        f"사람이 읽는 자리에 변수명 꼴 {len(tokens)}종이 남아 있다: {tokens}"
    )
