"""화면 겉면이 대장을 **무슨 낱말로 부르는가** — R63b 낱말표의 「새 화면 셋」 판.

판정 정본: `docs/decisions-2026-09-05-R63b.md` §1 낱말표 · §0 의 가르는 물음
(*「사용자가 화면에서 이 낱말을 찾아야 하는가」*).

## ★★ 왜 이 파일이 따로 있나 — **낱말 축이 갈라진 뒤에 화면 셋이 생겼다**

낱말 축(R63/S1)은 `tests/web/test_dashboard.py` 에서 **대시보드만** 쟀다.
`/ui/scenarios`·`/ui/settings`·`/ui/verify` 는 **다른 축이 같은 시각에 다른
가지에서** 만들었고 그 지시문에는 낱말표가 없었다 — 그래서 병합된 화면 셋의
겉면 22곳이 대장을 아직 「전제」로 불렀다(`.orch/R63/result_V2.md` §2 `D11`,
브라우저 실측).

⇒ **이 파일은 대시보드가 아니라 「앱이 내놓는 화면 전건」을 훑는다.** 화면이
하나 늘 때 그 화면만 옛 낱말로 남는 것이 방금 밟은 사고이므로, 목록을 손으로
적지 않고 **앱 자신의 OpenAPI 문서**에서 얻는다.

## ⚠⚠ 「0 건」을 요구하지 않는다 — 남아야 하는 「전제」가 있다

§0 이 가르는 물음은 *「사용자가 화면에서 이 낱말을 찾아야 하는가」*이고, 그 답이
**아니오**인 갈래가 화면에 남는다. 남는 것은 셋이며 **가르는 방법이 셋 다 다르다**:

| 남는 것 | 어떻게 가르나 |
|---|---|
| 리포트 양식의 표 이름(`FR-602-AC2`) | `_ALLOWED_PHRASES` 에 **명시로** 적는다 |
| 검증 모드 **단계** — 렌더러가 낸 문면 | `<details class="verify-stage">` 를 **자리로** 걷어 낸다 |
| 대장이 **자료로** 갖는 글자(출처 인용 등) | `docs/assumptions.yaml` 의 값과 **대조**한다 |
| 이 축이 만질 수 없는 파일이 지은 문면 | 그 **상수를 직접 들여와** 대조한다 |

★ 셋째 줄이 필요한 이유: 대장의 출처 칸이
`docs/research-2026-09-02-R52-전제값.md` 라는 **파일 이름을 인용**한다. 그것은
화면이 고른 낱말이 아니라 **대장이 든 자료**이며, 낱말을 바꾸려면 그 문서를
개명해야 한다. 낱말 축(S1)이 `tests/infra/` 의 `AssumptionSet(name="전제 v1")`
에 대해 *「뜻이 아니라 **데이터**다 ⇒ 두어라」* 로 내린 판정과 같은 갈래다
(`docs/decisions-2026-09-05-R63b.md` §2 ⓐ 다섯째).

⚠⚠ **문면을 「렌더러 출력의 부분 문자열인가」로 가르지 마라.** 처음에 그렇게
쟀더니 화면이 손으로 적은 `<dt>전제 대장</dt>` 이 **렌더러 표의 행 이름과 우연히
같아서** 조용히 통과했다(실측). 짧은 문면일수록 우연히 겹치고, 그때 이 검사는
「화면이 안 지었다」와 「화면이 지었는데 말이 겹친다」를 구별하지 못한다.
⇒ **자리로 가른다** — 렌더러 문면이 실리는 자리는 `<details class="verify-stage">`
**하나뿐**이고(제목과 본문 둘 다 렌더러가 지었다), 그 안이 정말 렌더러의 글자인지는
`tests/app/test_ui_verify.py::test_stage_bodies_are_the_renderers_own_text` 가
문자 단위로 이미 단정한다.

## ⚠⚠⚠ 지운 것과 세운 것을 **함께** 잰다

옛 낱말만 세면 **가장 싼 통과 방법이 그 자리를 통째로 지우는 것**이다. 그때
사용자는 대장을 부르는 이름과 「기준 전제 대비 변경 항목」 표를 함께 잃고, 검사는
초록불이다. `tests/web/test_dashboard.py::test_the_new_words_stand_on_the_screen`
이 같은 사유로 같은 짝을 세워 두었다 — 여기서도 셋을 짝으로 둔다:

    옛 낱말이 없다  +  새 낱말이 선다  +  남겨야 할 리포트 문면이 그대로 있다

## `web.render_*` 를 직접 부르지 않는다

전부 `TestClient(create_app())` 를 지난다. 문맥 함수를 직접 부르면 「배포 코드가
부르지 않는 함수가 초록불을 만든다」를 그대로 다시 밟는다
(`tests/app/test_ui_run.py`·`test_ui_scenarios.py` 머리말이 그 형태를 적었다).

## ⚠ `@pytest.mark.req(...)` — **하나만 달았다**

`FR-602-AC2` 는 문면이 *「리포트에 "기준 전제 대비 변경 항목" 목록이 자동
생성된다」* 이므로 그 표 이름을 지키는 검사에 **그대로 맞는다**. 나머지 낱말
검사에는 달지 않았다 — 사용자 요구(*「동일한 내용에 대해서 단일 단어」*)를 받는
수용기준이 spec 에 없고, `UI-1-AC1`(마법사 + 고급 모드 병행)은 대시보드의
조항이라 이 화면 셋에 달면 `docs/traceability.md` 에 거짓 인용이 실린다.
`tests/app/test_ui_verify.py` 머리말이 같은 자리에서 같은 판정을 적었다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.ui_run import run_ui_case
from core.report.verification import render_verification_markdown
from tests.web.test_dashboard import human_text
from web.render_scenarios import _NOT_IN_LEDGER

#: 화면에서 물러난 낱말. **한 낱말**로 센다 — 「전제 대장」·「전제 항목」처럼
#: 이어 붙는 꼴을 목록으로 적으면 새로 생긴 조합이 조용히 빠져나간다.
_RETIRED = "전제"

#: 대조에 쓰는 골든 시나리오 — 검증 모드 화면과 **같은 것**이어야 렌더러 문면을
#: 맞댈 수 있다(`tests/app/test_ui_verify.py` 와 같은 값).
_SCENARIO = "scenario_unsubsidized"

#: ★★ **남아야 하는 「전제」 — 허용 목록.** 여기 없고 렌더러 출력도 아닌 것은
#: 전부 빨간불이다.
#:
#: ⓐ **「기준 전제 대비 변경 항목」** — `FR-602-AC2` 의 **문면 그대로**이고
#:    리포트 양식의 표 이름이다. R63 판정: 리포트 인쇄 문면은 이 라운드에서
#:    바꾸지 않는다(착수 목록 51번). 화면이 그 표를 리포트와 **다른 이름**으로
#:    부르면 검토자는 같은 표인지 알 수 없다.
#:    ⚠ 아래 `test_the_report_form_table_name_still_stands` 가 이 문면이
#:    **사라지지 않았는가**를 반대 방향에서 잰다.
#:
#: ⓑ **「ⓐ 전제한 수치」** — 검증 모드가 소개 문단에서 **렌더러의 칸 이름을
#:    그대로 인용**한 자리다. 정본은 `core/report/verification.py::_stage` 이고
#:    (`tests/app/test_ui_verify.py::_CELLS` 가 같은 넷을 갖는다) `core/` 는
#:    이 축이 만질 수 없는 파일이다. 화면에서만 낱말을 바꾸면 소개 문단이
#:    **바로 아래 단계 본문이 실제로 인쇄하는 칸 이름과 갈리고**, 그때 사람은
#:    소개가 가리키는 칸을 본문에서 찾지 못한다.
#:    ⚠ 아래 `test_the_allowed_verify_phrase_is_the_renderers_own_words` 가
#:    이 인용이 **아직 렌더러의 말인가**를 잰다 — 렌더러가 칸 이름을 바꾸는 날
#:    이 허용분은 근거를 잃는다.
#:
#: ⓒ ⚠⚠ **`web/render_scenarios.py::_NOT_IN_LEDGER`** — 판정이 아니라 **축 경계**다.
#:    설정 화면의 「사용자가 지목한 다섯」 표가 못 찾은 항목에 붙이는 주석이며,
#:    `.orch/R63/result_V2.md` 의 `D11` 표가 **놓친 스물세째 자리**다(그 표는
#:    템플릿 셋과 `verify_steps.py` 만 들었다 — 이 검사가 훑다가 찾았다).
#:    `web/render_scenarios.py` 는 `WP-FIX2` §B 가 이 축에 준 파일 목록에 없고,
#:    지시문 §5 는 *「네 절 밖의 파일을 만지지 마라 · 만져야 하면 적고 멈춰라」*
#:    다. ⇒ **고치지 않고 재서 드러낸다**(`.orch/R63/result_F5.md` §7).
#:    ★ 문면을 베껴 적지 않고 **그 상수를 직접 들여와** 대조한다 — 베껴 적으면
#:    그 파일이 문면을 고치는 날 이 예외가 조용히 넓어진다.
_ALLOWED_PHRASES: tuple[str, ...] = (
    "기준 전제 대비 변경 항목",
    "ⓐ 전제한 수치",
    _NOT_IN_LEDGER,
)

#: ★ **그 자리에 선 새 낱말** — 판정 정본 §1 낱말표.
#: ⚠ 화면마다 무엇이 서야 하는지를 **갈라서** 적는다. 합쳐서 「어딘가 하나 있다」로
#: 재면 한 화면이 통째로 낱말을 잃어도 초록불이다.
_NEW_WORDS_BY_SCREEN: dict[str, tuple[str, ...]] = {
    "/ui/settings": ("분석 설정 대장", "설정 항목"),
    "/ui/scenarios": ("분석 설정 대장", "계측 선언"),
    "/ui/verify": ("분석 설정 대장",),
}

#: 저장은 **303** 으로 되돌리고 그 주소에 방금 저장한 번호가 있다.
_APPLIED_ID = re.compile(r"applied=(\d+)")

#: 검증 모드가 **렌더러 문면을 그대로 싣는 자리** — 화면이 지은 글자가 아니다.
#: ⚠ `<pre class="stage-body">` **만** 걷어 내면 부족하다. 바로 위 `<summary>`
#: 가 「1단계 — 전제 대장에서 읽은 값」을 싣는데 그 제목도 렌더러가 지은 것이고
#: (`core/report/verification.py::_stage` · `verify_steps.split_stages` 가
#: 그 머리글을 갈라 담는다) `core/` 는 이 축의 금지 파일이다. ⇒ **`<details>`
#: 통째로** 걷어 낸다.
#: ⚠ 속성을 **열어 둔다**. 종전에 `tests/app/test_ui_verify.py` 의 같은 정규식이
#: `<pre>` 를 글자까지 고정하고 있었고, 접근성 위반을 고치려고 `tabindex="0"` 을
#: 더한 순간 **찾은 본문이 0개**가 되어 화면이 멀쩡한 채로 검사가 깨졌다. 그
#: 파일이 적어 둔 그 사유를 여기서도 따른다 — 재는 것은 **클래스 이름 하나**다.
_STAGE = re.compile(r'<details class="verify-stage"[^>]*>.*?</details>', re.DOTALL)

#: 대장 정본 — 화면의 출처·비고 칸이 **자료로** 싣는 글자의 원천.
_ASSUMPTIONS = Path(__file__).resolve().parents[2] / "docs" / "assumptions.yaml"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _served_screens(client: TestClient) -> list[str]:
    """앱이 내놓는 HTML 화면 전건 — **앱 자신의 OpenAPI 문서**에서 얻는다.

    ⚠ 목록을 소스에 박지 않는다. 박아 두면 화면이 하나 늘어도 이 검사는 그대로
    초록불이고, 그 상태가 바로 `D11` 이 생긴 경위다.
    ⚠ `app.routes` 를 파이썬으로 뒤지지 않는다 — 그 자료구조의 모양은 FastAPI
    판마다 다르다(R62/WP-1 이 CI 에서 실측했다).
    """
    spec = client.app.openapi()
    served = sorted(
        path
        for path, operations in spec["paths"].items()
        if "{" not in path
        and "text/html"
        in (
            (operations.get("get") or {})
            .get("responses", {})
            .get("200", {})
            .get("content", {})
        )
    )
    assert served, "앱이 내놓는 화면을 한 건도 찾지 못했다 — 훑을 것이 없다"
    return served


def _ledger_data() -> frozenset[str]:
    """대장이 **자료로** 갖는 글자 전건 — 화면이 고른 낱말이 아니다.

    출처 칸이 `docs/research-2026-09-02-R52-전제값.md` 라는 **파일 이름을
    인용**하고, 화면은 그것을 그대로 싣는다. 낱말을 여기서 바꾸려면 그 문서를
    개명해야 한다 — 그것은 낱말표가 시킨 일이 아니다.

    ⚠ **부분 문자열로 가르지 않는다.** 정규화한 값과 **같은가**만 본다 — 부분
    문자열로 재면 대장의 긴 각주 하나가 화면의 짧은 낱말을 통째로 사면한다.
    ⚠ 문면을 이 파일에 베껴 적지 않는다. 대장이 판을 올리면 그 베낀 목록이
    낡고, 낡은 목록은 「고쳤다」와 「검사가 못 본다」를 구별하지 못한다.
    """
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, str):
            normalized = " ".join(node.split())
            if normalized:
                found.add(normalized)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8")))
    assert found, f"{_ASSUMPTIONS} 에서 글자를 한 건도 읽지 못했다"
    return frozenset(found)


def _saved_settings_id(client: TestClient) -> int:
    """설정 폼을 **눌러** 한 건 저장하고 번호를 돌려준다.

    ⚠ 이것이 필요한 이유: 「기준 전제 대비 변경 항목」 표는 `{% if applied %}`
    안에 있다. 저장 없이 GET 만 하면 그 절이 아예 안 그려지고, 그때 허용 목록의
    ⓐ 는 **재지 않은 채** 통과한다.
    """
    response = client.post(
        "/ui/settings",
        data={"name": "낱말 검사용 설정", "description": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text[:400]
    match = _APPLIED_ID.search(response.headers["location"])
    assert match is not None, response.headers["location"]
    return int(match.group(1))


def _corpus(client: TestClient) -> dict[str, str]:
    """사람이 읽는 글자를 화면마다 모은다.

    ★ 「사람이 읽는 자리」의 정의는 낱말 축이 세운 것을 **그대로 쓴다**
    (`tests/web/test_dashboard.py::human_text` — 본문 글자 +
    `title`·`aria-label`·`alt`·`placeholder`). 여기서 새로 지으면 두 축이 다른
    자를 들고 같은 것을 재게 된다.

    ★ 화면 목록에 **`?applied=`·`?scenario=` 두 벌**을 더한다 — 조건부로만
    그려지는 절(적용 결과 표 · 검증 모드 본문)이 그때만 서기 때문이다.

    ★★ 그리고 **렌더러 문면이 실리는 자리를 걷어 낸다**(`_STAGE_BODY`). 걷어
    내는 것이 화면이 **지은** 글자만 남기는 유일한 방법이다 — 문자열 대조로
    가르면 짧은 문면이 우연히 겹쳐 빠져나간다(머리말 §「0 건을 요구하지 않는다」).
    """
    pages: dict[str, str] = {}
    paths = [
        *_served_screens(client),
        f"/ui/settings?applied={_saved_settings_id(client)}",
        f"/ui/verify?scenario={_SCENARIO}",
    ]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, (
            f"{path} 를 열지 못했다: {response.status_code}"
        )
        pages[path] = human_text(_STAGE.sub(" ", response.text))
    return pages


def _offending_chunks(corpus: str, ledger: frozenset[str]) -> list[str]:
    """사람이 읽는 글자 중 **허용되지 않은 「전제」**가 든 조각을 돌려준다."""
    offenders: list[str] = []
    for chunk in corpus.splitlines():
        normalized = " ".join(chunk.split())
        if _RETIRED not in normalized:
            continue
        if normalized in ledger:
            # 대장이 자료로 든 글자다 — 화면이 고른 낱말이 아니다
            continue
        stripped = normalized
        for phrase in _ALLOWED_PHRASES:
            stripped = stripped.replace(phrase, "")
        if _RETIRED in stripped:
            offenders.append(normalized)
    return offenders


def test_no_screen_calls_the_ledger_by_the_retired_word(client: TestClient) -> None:
    """★★ **앱이 내놓는 화면 전건에서, 허용분 밖의 「전제」가 0 건이다.**

    사용자 문면: *「'고급 모드'나 '전제'나 동일하게 설비 설정을 변경하는 것을
    가르키는데 **동일한 내용에 대해서 단일 단어**를 사용해야 함」*
    (`docs/decisions-2026-09-05-R63.md` §1 「용어」).

    ⚠ **화면 하나만 보지 않는다.** `D11` 은 대시보드가 깨끗한 채로 새 화면 셋에만
    남아 있었고, 그 상태는 대시보드만 재는 검사에서 초록불이었다.

    ⚠ **일괄 치환으로 통과시키지 마라.** 이 저장소에는 일반 국어의 「전제」가
    270줄 있고(`docs/decisions-2026-09-05-R63b.md` §2 ⓐ), 치환은 그것을 부순다.
    """
    ledger = _ledger_data()

    left = {
        path: chunks
        for path, corpus in _corpus(client).items()
        if (chunks := _offending_chunks(corpus, ledger))
    }

    assert not left, (
        "화면이 대장을 아직 「전제」로 부른다 — 허용 목록 밖이다:\n"
        + "\n".join(
            f"  {path}\n" + "\n".join(f"    · {chunk}" for chunk in chunks)
            for path, chunks in sorted(left.items())
        )
        + f"\n  허용 목록: {list(_ALLOWED_PHRASES)}"
    )


def test_the_new_words_stand_on_the_screens(client: TestClient) -> None:
    """★★ **새 낱말이 실제로 서 있다** — 지운 것과 세운 것을 함께 잰다.

    ⚠ 위 검사만 두면 「낱말을 지웠다」의 가장 싼 통과 방법이 **그 자리를 통째로
    지우는 것**이다. 그때 사용자는 대장을 부르는 이름을 화면에서 잃는다 —
    `tests/web/test_dashboard.py::test_the_new_words_stand_on_the_screen` 이
    대시보드에서 같은 사유로 같은 짝을 세웠다.
    """
    pages = _corpus(client)

    missing: dict[str, list[str]] = {}
    for path, words in _NEW_WORDS_BY_SCREEN.items():
        corpus = "\n".join(
            text for key, text in pages.items() if key.split("?")[0] == path
        )
        assert corpus, f"{path} 의 본문을 한 글자도 모으지 못했다"
        absent = [word for word in words if word not in corpus]
        if absent:
            missing[path] = absent

    assert not missing, f"새 낱말이 화면에 서지 않았다: {missing}"


@pytest.mark.req("FR-602-AC2")
def test_the_report_form_table_name_still_stands(client: TestClient) -> None:
    """★ **「기준 전제 대비 변경 항목」은 그대로 있다** — 허용분 ⓐ 의 반대 방향.

    `FR-602-AC2` 의 문면이 *「리포트에 "기준 전제 대비 변경 항목" 목록이 자동
    생성된다」* 이고, R63 판정은 **리포트 인쇄 문면을 이 라운드에서 바꾸지 않는
    것**이다(착수 목록 51번). 화면이 그 표를 리포트와 다른 이름으로 부르면
    검토자는 같은 표인지 알 수 없다.

    ⚠ 이 검사가 없으면 위 낱말 검사를 통과하는 가장 싼 길이 **이 표 이름을
    지우는 것**이 된다 — 그 길은 조항을 깬다.
    """
    body = client.get(
        "/ui/settings", params={"applied": _saved_settings_id(client)}
    ).text

    assert "기준 전제 대비 변경 항목" in human_text(body), (
        "적용 결과 절에서 리포트 표 이름이 사라졌다 — `FR-602-AC2` 의 문면이다"
    )


def test_the_allowed_verify_phrase_is_the_renderers_own_words() -> None:
    """★ **허용분 ⓑ 가 아직 렌더러의 말인가** — 허용 목록이 낡는 것을 막는다.

    검증 모드 소개 문단의 「ⓐ 전제한 수치」는 화면이 지은 말이 아니라 렌더러의
    칸 이름을 인용한 것이다. 렌더러가 그 이름을 바꾸는 날 이 허용분은 근거를
    잃고, 그때 이 검사가 빨간불로 알린다 — 알리지 않으면 화면에 근거 없는
    「전제」가 조용히 남는다.
    """
    renderer = render_verification_markdown(run_ui_case(_SCENARIO).report)

    assert "ⓐ 전제한 수치" in renderer, (
        "렌더러가 「ⓐ 전제한 수치」를 더는 인쇄하지 않는다 — "
        "허용 목록 ⓑ 의 근거가 사라졌으니 화면 문면과 함께 다시 판정하라"
    )
