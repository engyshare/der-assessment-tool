"""작업 15.12 — **브라우저로 실제로 눌러 본다** (핵심 3 시나리오).

## 조항 문면과 어긋나는 것을 여기 적는다 — 숨기지 않는다

조항은 *「로그인 → 마법사 → 실행 → 내보내기」* 다. **「로그인」 단계는 지금 화면에
없다.** `app/routers/auth.py` 는 API 이고 UI 라우트에는 인증이 걸려 있지 않다
(`app/routers/ui.py` 머리말의 *「데모 값을 여기 두는 이유」* 가 같은 사실을 적는다 —
역할이 아직 요청에서 오지 않는다). 없는 화면에 로그인 단계를 **지어내지 않는다** —
지어내면 이 시험이 통과하는 것은 조항이 아니라 시험 자신이 만든 허구다.

**「마법사」도 R62/WP-7 전에는 눌러 넘길 것이 없었다.** `web/templates/dashboard.html`
의 `#wizard` 는 네 걸음을 **글자로** 싣고 「다음 단계」 단추는 `type="button"` 이며
아무 데도 가지 않았다. 그래서 아래 시나리오 1 은 마법사의 네 걸음이 화면에 **있는지**
까지만 보고, 실제 진행은 실행 폼으로 한다 — **그 판단은 지금도 그대로다.**
WP-7 이 네 걸음을 링크로 만들었지만(D7) 그 링크가 실제로 갈 곳을 갖는지는
`tests/web/test_dashboard.py` 가 렌더 결과에서 재고, 여기서 그것을 다시 누르면
같은 것을 두 곳에서 재게 된다.

## 화면이 **읽히는가**도 여기서 잰다 (R62/WP-7)

시나리오 넷 아래에 레이아웃 실측 둘이 붙어 있다 — 1366×768 에서 가로 스크롤이
생기는가(`NFR-304`)와 그림이 원본 대비 읽을 만한 폭으로 그려지는가(D4). 둘 다
**브라우저가 실제로 배치한 결과**를 재며, CSS 문면을 읽지 않는다.

## 셀렉터를 자리로 잡지 않는다

`nth-child` 같은 자리로 잡으면 화면을 조금만 고쳐도 깨지고, 깨진 이유가 「기능이
망가졌다」와 구별되지 않는다. 접근 가능한 이름(`get_by_role`)이나 `id`·`name` 으로만
잡는다.

## 수를 박지 않는다

NPV 값을 여기 적지 않는다. **두 값을 서로 비교**하거나, 수로 읽히는지만 본다 —
박으면 대장 판이 오르는 날 「화면이 틀렸다」가 아니라 「시험이 낡았다」로 빨간불이
된다 (`tests/app/test_ui_run.py` 머리말이 같은 판단을 적어 두었다).

## 고를 갈래를 소스에 박지 않는다

무엇을 클릭할지는 `BaselineArrangement` 열거와 `get_baseline_branch` 에 **물어서**
정한다. 기댓값을 가져오는 것이 아니라 **누를 것**을 가져오는 것이며, 박으면 갈래가
늘거나 이름이 바뀌는 날 이 시험이 없는 라디오를 누른다.
"""
from __future__ import annotations

import dataclasses
import math
import re

import pytest
from playwright.sync_api import Page, expect

from core.cba.baseline import (
    BaselineArrangement,
    PoolMeteringDeclaration,
    get_baseline_branch,
)
from core.contracts.validation import ValidationError

#: 실행 결과 주소. 폼이 `method="get" action="/ui/run"` 이므로 제출은 이리로 간다.
_RUN_URL = re.compile(r"/ui/run\?")

#: 제출 단추의 접근 가능한 이름 — `dashboard.html` 의 `<button type="submit">`.
_SUBMIT = "분석 실행"

#: 마법사가 실어야 하는 걸음 수 — 조항 문면 「로그인 → 마법사 → 실행 → 내보내기」가
#: 아니라 화면의 `#wizard` 가 적은 네 걸음(시나리오 선택·전제 확인·실행·내보내기)이다.
_WIZARD_STEPS = 4


def _needs_declaration(arrangement: BaselineArrangement) -> bool:
    """이 갈래가 **계측 전제 선언을 요구하는가** — 저장소에 물어서 안다.

    ⚠ 「ⓒ 만 그렇다」를 여기 적지 않는다. 요구하는 갈래가 둘이 되는 날 그 문장만
    참인 채로 남고, 그때 이 파일은 새 갈래를 전제 없이 눌러 보며 「고를 수 없다」로
    빨간불이 된다 — 원인은 시험이 낡은 것이다.
    """
    try:
        get_baseline_branch(arrangement)
    except ValidationError:
        return True
    return False


def _plain_arrangements() -> list[BaselineArrangement]:
    """전제를 요구하지 **않는** 갈래들 — 그냥 골라서 돌아가는 것들."""
    return [item for item in BaselineArrangement if not _needs_declaration(item)]


def _declaring_arrangements() -> list[BaselineArrangement]:
    """전제를 **요구하는** 갈래들 — 전제 없이 고르면 거부되어야 한다."""
    return [item for item in BaselineArrangement if _needs_declaration(item)]


def _prerequisite_field_names() -> tuple[str, ...]:
    """ⓒ 전제 체크박스의 `name` — `PoolMeteringDeclaration` 이 정본이다.

    ⚠ 손으로 적지 않는다. 자료형이 필드를 늘리는 날 이 시험이 옛 둘만 켜고
    「전제를 다 줬는데 거부된다」로 빨간불이 된다 — 원인은 화면이 아니다
    (`web/render.py::pool_prerequisite_fields` 가 화면 쪽에서 같은 판단을 한다).
    """
    return tuple(field.name for field in dataclasses.fields(PoolMeteringDeclaration))


def _submit_run_form(page: Page) -> None:
    """실행 폼을 제출하고 결과 주소로 넘어갈 때까지 기다린다."""
    page.get_by_role("button", name=_SUBMIT).click()
    page.wait_for_url(_RUN_URL)


def _npv_on_screen(page: Page) -> float:
    """결과 화면의 **서식 이전 날값**을 읽는다.

    ⚠ 서식을 입힌 문면(`{{ npv }}`)을 읽지 않는다 — 그러면 재는 것이 수가 아니라
    표기가 되고, 천단위 구분이 바뀌는 날 「수가 틀렸다」로 빨간불이 된다.
    `run_result.html` 의 `data-npv` 가 그 목적으로 실려 있다.
    """
    raw = page.locator("dd.npv").get_attribute("data-npv")
    assert raw is not None, "결과 화면이 결론 축을 날값으로 싣지 않았다"
    return float(raw)


def _choose_arrangement(page: Page, arrangement: BaselineArrangement) -> None:
    """갈래 라디오를 **접근 가능한 이름으로** 고른다."""
    page.get_by_role("radio", name=arrangement.value, exact=True).check()


def _arrangement_on_screen(page: Page) -> str | None:
    """결과 화면이 **어느 갈래로 돌았다고 적는가**."""
    return page.locator(".arrangement").get_attribute("data-arrangement")


@pytest.mark.req("UI-1-AC1")
def test_scenario_1_open_pick_run_and_export(page: Page, live_server: str) -> None:
    """**시나리오 1 — 기본 흐름.** 뿌리를 열고 → 시나리오를 고르고 → 제출하고 →
    결과에서 NPV 가 실제 수로 찍혔는지 보고 → 리포트 내보내기가 본문을 내는지 본다.

    ⚠ 「로그인」은 이 흐름에 없다 — 화면에 그 단계가 없기 때문이며, 그 사실은 이
    파일 머리말에 적었다. 마법사는 네 걸음이 **있는지**까지만 본다.

    ⚠ 내보내기를 `page.goto()` 로 열지 않는다. `/reports/golden/<이름>` 은
    `text/markdown` 을 내고 크로미움은 그것을 **그리지 않고 내려받는다** — 그러면
    「본문을 냈다」를 브라우저에서 확인할 수 없다. 같은 브라우저 문맥의 요청
    통로(`page.request`)로 받아 본문을 직접 본다.
    """
    page.goto(live_server)

    # 마법사가 네 걸음을 **글자로** 싣는지. 눌러 넘길 것은 아직 없다(머리말 참조).
    expect(page.locator("#wizard")).to_be_visible()
    steps = page.locator("#wizard .steps li")
    assert steps.count() >= _WIZARD_STEPS, (
        f"마법사가 걸음을 {steps.count()} 개만 싣는다 — 화면이 적은 것은 네 걸음이다"
    )

    # 시나리오를 **화면이 내놓은 목록에서** 고른다. 이름을 박으면 골든이 늘거나
    # 이름이 바뀌는 날 이 시험이 없는 시나리오를 고른다.
    options = page.locator("#run-scenario option")
    assert options.count() > 0, "실행 폼의 시나리오 목록이 비었다 — 고를 것이 없다"
    scenario = options.first.get_attribute("value")
    assert scenario, "시나리오 선택지에 값이 없다"
    page.locator("#run-scenario").select_option(value=scenario)

    _submit_run_form(page)

    # ★ 결과 화면에 NPV 가 **실제 수**로 찍혔다. 값을 박지 않고 수로 읽히는지만 본다.
    npv = _npv_on_screen(page)
    assert math.isfinite(npv), f"NPV 가 수가 아니다: {npv}"
    expect(page.locator("#conclusion")).to_be_visible()

    # 내보내기 — 같은 브라우저 문맥으로 리포트를 받는다.
    exported = page.request.get(f"{live_server}/reports/golden/{scenario}")
    assert exported.ok, f"내보내기가 {exported.status} 를 냈다: {exported.text()}"
    body = exported.text()
    assert body.strip(), "내보낸 리포트의 본문이 비었다"
    assert body.lstrip().startswith("#"), (
        f"내보낸 것이 리포트 본문으로 보이지 않는다 — 첫 줄: {body.splitlines()[:1]}"
    )


@pytest.mark.req("FR-705-AC2")
def test_scenario_2_changing_the_arrangement_moves_the_number(
    page: Page, live_server: str
) -> None:
    """★ **시나리오 2 — 갈래를 바꾸면 수가 바뀐다.**

    이것이 사용자 요구(*「분석 시 선택할 수 있어야」*)가 **브라우저에서** 성립하는가다.
    같은 수가 나오면 그것은 *「골랐는데 안 먹었다」* 이고, **그 상태는 200 초록불로
    조용하다** — 화면은 고른 갈래를 그대로 인쇄하고 수만 옛것이다.
    """
    plain = _plain_arrangements()
    assert len(plain) >= 2, "맞댈 갈래가 둘이 안 된다"
    first, second = plain[0], plain[1]

    page.goto(live_server)
    _choose_arrangement(page, first)
    _submit_run_form(page)
    assert _arrangement_on_screen(page) == first.value
    one = _npv_on_screen(page)

    page.goto(live_server)
    _choose_arrangement(page, second)
    _submit_run_form(page)
    assert _arrangement_on_screen(page) == second.value
    other = _npv_on_screen(page)

    assert one != other, (
        f"「{first.value}」 와 「{second.value}」 가 같은 수({one})를 냈다 — "
        "화면에서 갈래를 골랐는데 실행에 닿지 않았을 수 있다"
    )


@pytest.mark.req("FR-705-AC2", "NFR-303-M1")
def test_scenario_3_refused_without_prerequisites_then_runs_with_them(
    page: Page, live_server: str
) -> None:
    """★ **시나리오 3 — 전제를 요구하는 갈래가 거부되고, 전제를 주면 돈다.**

    거부가 이 화면의 **정상 동작**이다 — 소유·운영권 인계와 구분 계측은 자료가
    아니라 사업 설계이며 저장소가 채울 수 없다.

    ⚠ 거부만 재고 「전제를 주면 돈다」를 안 재면 **「영영 고를 수 없는 갈래」와
    「전제를 요구하는 갈래」가 구별되지 않는다.**

    ⚠ 3요소를 **셋 다** 본다. 하나라도 빠지면 사람에게 남는 선택은 값을 하나씩
    바꿔 보는 것이고, 그때 가장 쉬운 선택이 「그냥 참으로 두기」다 (`NFR-303`).
    """
    declaring = _declaring_arrangements()
    assert declaring, "전제를 요구하는 갈래가 없다 — 잴 것이 없다"
    arrangement = declaring[0]

    # ① 전제 없이 제출 → 거부 화면. 필드·사유·조치 셋이 **화면에** 보인다.
    page.goto(live_server)
    _choose_arrangement(page, arrangement)
    _submit_run_form(page)

    refusal = page.locator("#validation .error-message")
    expect(refusal).to_be_visible()
    refusal_text = refusal.inner_text()
    for element in ("필드:", "사유:", "조치:"):
        assert element in refusal_text, (
            f"거부 화면에 {element} 가 없다 — NFR-303 의 3요소 중 하나가 빠졌다.\n"
            f"화면 문면: {refusal_text}"
        )
    assert page.locator("dd.npv").count() == 0, (
        "거부됐는데 결론 축이 함께 그려졌다 — 돌지 않은 것과 돈 것이 화면에서 같아진다"
    )

    # ② 체크박스를 켜고 다시 제출 → 결과가 나온다.
    page.goto(live_server)
    _choose_arrangement(page, arrangement)
    for name in _prerequisite_field_names():
        page.locator(f'input[name="{name}"]').check()
    _submit_run_form(page)

    assert _arrangement_on_screen(page) == arrangement.value, (
        f"전제를 줬는데 「{arrangement.value}」 로 돌지 않았다"
    )
    assert math.isfinite(_npv_on_screen(page))


@pytest.mark.req("FR-201-AC1")
def test_scenario_4_duplicating_a_resource_in_the_browser_grows_the_list(
    page: Page, live_server: str
) -> None:
    """★ **시나리오 4 — 자원 구성 화면에서 「자원 복제」를 실제로 클릭한다.**

    R62/WP-5 가 브라우저로 눌러 보고 잡은 것이 이것이다. 그때 이 단추는 눌리면
    **영어 `422`** 를 냈다 — 폼이 urlencoded 를 보내는데 `action` 이 가리키던
    것은 JSON 본문을 받는 API 였다. 「화면이 있다」를 재던 검사들은 그 상태에서
    전부 초록불이었다.

    ⚠ **수를 박지 않는다.** 화면의 자원 수는 같은 프로세스 안 앞선 조작에 따라
    다르다(`_service` 가 모듈 수준 인스턴스다). 재는 것은 **이 클릭이 목록을
    늘렸는가**뿐이다.

    ⚠ 셀렉터를 자리로 잡지 않는다. 복제할 행은 `data-resource-name` 으로,
    누를 단추는 **접근 가능한 이름**으로 잡는다.
    """
    page.goto(f"{live_server}/ui/model-composer")

    rows = page.locator("tr[data-resource-name]")
    before = rows.count()
    assert before > 0, "자원 구성 화면에 복제할 자원이 없다 — 누를 것이 없다"

    row = rows.first
    source = row.get_attribute("data-resource-name")
    assert source, "자원 행이 이름을 싣지 않았다"
    clone = f"{source}-브라우저복제-{before}"

    # 복제본 이름 칸은 그 행 **안**의 것이다. 기본값을 그대로 두면 앞선 검사가
    # 만든 이름과 겹칠 수 있고, 겹침 거부는 「단추가 안 먹는다」와 화면에서
    # 구별되지 않는다.
    row.locator('input[name="new_name"]').fill(clone)
    row.get_by_role("button", name="자원 복제").click()

    # PRG — 303 을 따라 화면으로 되돌아온다. 주소가 그대로여야 새로고침이
    # 같은 복제를 다시 하지 않는다.
    page.wait_for_url(re.compile(r"/ui/model-composer$"))

    after = page.locator("tr[data-resource-name]")
    assert after.count() == before + 1, (
        f"「자원 복제」를 눌렀는데 목록이 {before} → {after.count()} 다"
    )
    expect(page.locator(f'tr[data-resource-name="{clone}"]')).to_be_visible()


# ─────────────────────────────────────────────────────────────────────────────
# R62/WP-7 — **레이아웃을 브라우저에서 잰다** (D4 · `NFR-304`)
# ─────────────────────────────────────────────────────────────────────────────

#: 조항 문면이 정한 최소 화면 — *「주요 화면이 1366×768 이상에서 가로 스크롤 없이
#: 표시된다」* (`NFR-304-AC1` · `docs/manual-checks.yaml` 의 `MC-5`). **이상**이므로
#: 이 크기가 가장 빡빡한 자리이고, 여기서 서면 더 넓은 화면에서도 선다.
_MINIMUM_VIEWPORT = {"width": 1366, "height": 768}

#: 그림이 원본 대비 가져야 하는 **최소 폭 비율**. 절대 px 를 박지 않는다 —
#: 박으면 그림 크기나 화면 여백이 바뀌는 날 「화면이 틀렸다」가 아니라 「시험이
#: 낡았다」로 빨간불이 된다.
#:
#: 0.5 를 고른 근거(2026-09-05 실측): 고치기 전 `.visual-grid` 가
#: `minmax(14rem, 1fr)` 이라 1366px 에서 다섯 칸이 서고 비율이 **0.178** 이었다
#: (그 폭에서는 축 눈금과 범례를 못 읽는다 — 그것이 D4 다). 고친 뒤는 두 칸이
#: 서고 **0.678** 이다. 0.5 는 그 사이의 넉넉한 자리이며, 다시 세 칸으로
#: 되돌아가면(0.45) 걸린다.
_MINIMUM_RENDER_SHARE = 0.5


def _html_screens(page: Page, live_server: str) -> tuple[str, ...]:
    """앱이 내놓는 **화면 전부** — 앱 자신의 OpenAPI 문서에서 얻는다.

    ⚠ **목록을 여기 박지 않는다.** 박으면 화면이 늘어도 이 목록만 넷인 채로
    남고, 그 상태는 「전건 통과」와 구별되지 않는다 (§13.0.1 ④).
    `tests_e2e/test_axe_accessibility.py` 가 자기 목록을 같은 문서와 대조하는
    것과 같은 판단이며, 여기서는 아예 문서를 정본으로 쓴다.
    """
    spec = page.request.get(f"{live_server}/openapi.json")
    assert spec.ok, f"OpenAPI 문서를 받지 못했다: {spec.status}"
    screens = tuple(sorted(
        path
        for path, operations in spec.json()["paths"].items()
        if "{" not in path
        and "text/html"
        in ((operations.get("get") or {}).get("responses", {}).get("200", {})
            .get("content", {}))
    ))
    assert screens, "앱이 내놓는 화면을 한 건도 찾지 못했다 — 잴 것이 없다"
    return screens


def test_no_screen_scrolls_sideways_at_the_minimum_viewport(
    page: Page, live_server: str
) -> None:
    """★★ **1366×768 에서 가로 스크롤이 0건이다** — 화면 넷 전건.

    ## ⚠⚠ 이 검사에 `NFR-304-AC1` 마커를 **일부러 달지 않았다**

    그 기준은 `docs/manual-checks.yaml` 의 `MC-5` 로 **수동 검증에 등재돼 있다**.
    자동 검사에 같은 마커를 달면 수동 대장과 자동 매핑이 **같은 기준을 두고
    갈리고**, 그때 어느 쪽이 그 기준을 지고 있는지 아무 데도 적혀 있지 않게 된다.
    (R62/WP-7 오케스트레이터 판정.)

    ⇒ **`MC-5` 의 사람 몫은 「레이아웃 붕괴 0건」 쪽에 그대로 남는다.** 이 검사는
    그 수용기준의 **앞 절반**(「가로 스크롤 0건」)만 기계로 재며, 겹쳐 보이는
    글자·잘린 표·읽을 수 없는 대비처럼 **붕괴**로 불리는 것은 여전히 사람이 본다.
    `docs/manual-checks.yaml` 은 이 WP 가 고치지 않았다.

    ## 왜 `scrollWidth == clientWidth` 인가

    가로 스크롤바가 **보이는지**를 눈으로 찾지 않는다. 브라우저는 화면 밖으로
    1px 만 넘쳐도 스크롤을 허용하고, 그 1px 은 스크린샷에서 보이지 않는다.
    문서가 **자기 뷰포트보다 넓은가**를 직접 묻는 것이 그 상태를 붙든다.
    """
    page.set_viewport_size(_MINIMUM_VIEWPORT)
    overflowing: list[str] = []
    for path in _html_screens(page, live_server):
        response = page.goto(f"{live_server}{path}")
        assert response is not None and response.ok, f"{path} 를 열지 못했다"
        page.wait_for_load_state("networkidle")
        scroll_width, client_width = page.evaluate(
            "() => [document.documentElement.scrollWidth,"
            " document.documentElement.clientWidth]"
        )
        if scroll_width != client_width:
            overflowing.append(
                f"{path}: scrollWidth {scroll_width} ≠ clientWidth {client_width} "
                f"({scroll_width - client_width}px 넘친다)"
            )

    assert not overflowing, (
        f"{_MINIMUM_VIEWPORT['width']}x{_MINIMUM_VIEWPORT['height']} 에서 가로로 "
        f"넘치는 화면 {len(overflowing)}건:\n  " + "\n  ".join(overflowing)
    )


def test_charts_render_at_a_readable_share_of_their_source_width(
    page: Page, live_server: str
) -> None:
    """★ **그림이 읽을 만한 폭으로 그려진다** — D4 (R62/WP-7).

    R62/WP-5 가 브라우저로 재서 잡은 것이 이것이다: `.visual-grid` 가
    `minmax(14rem, 1fr)` 이라 1366px 에서 **다섯 칸**이 서고, 960×540 원본이
    **171px**(0.178배)로 줄어 축 눈금과 범례를 읽을 수 없었다. **그 상태에서
    「그림이 있다」를 재던 검사들은 전부 초록불이었다** — 그림은 있었다.

    ⚠ **절대 px 를 박지 않는다.** 원본 폭은 그림 자신에게 묻고(`naturalWidth`),
    비교하는 것은 **비율**이다.

    ⚠ 그림이 `loading="lazy"` 라 화면 밖에 있으면 아직 안 실린다. 안 실린 그림의
    `naturalWidth` 는 0 이고 그것을 그대로 나누면 이 검사는 「그림이 작다」가
    아니라 `ZeroDivisionError` 로 죽는다 — 스크롤해 넣고 실릴 때까지 기다린다.
    """
    page.set_viewport_size(_MINIMUM_VIEWPORT)
    too_small: list[str] = []
    measured = 0
    for path in _html_screens(page, live_server):
        page.goto(f"{live_server}{path}")
        images = page.locator(".visual-grid img")
        for index in range(images.count()):
            image = images.nth(index)
            image.scroll_into_view_if_needed()
            page.wait_for_function(
                "element => element.complete && element.naturalWidth > 0",
                arg=image.element_handle(),
            )
            box = image.bounding_box()
            assert box is not None, f"{path} 의 그림이 배치되지 않았다"
            source_width = image.evaluate("element => element.naturalWidth")
            share = box["width"] / source_width
            measured += 1
            if share < _MINIMUM_RENDER_SHARE:
                tag = image.evaluate(
                    "element => element.closest('figure').dataset.chart"
                )
                too_small.append(
                    f"{path} · {tag}: 렌더 {box['width']:.0f}px / 원본 "
                    f"{source_width}px = {share:.3f}"
                )

    assert measured, (
        "그린 그림이 한 건도 없다 — 잴 것이 없다. 이것은 「그림이 크다」가 아니다"
    )
    assert not too_small, (
        f"원본의 {_MINIMUM_RENDER_SHARE:.0%} 에 못 미치는 폭으로 그려진 그림 "
        f"{len(too_small)}건 (전체 {measured}건):\n  " + "\n  ".join(too_small)
    )
