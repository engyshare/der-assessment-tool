"""작업 15.10 — **axe-core 자동 접근성 스캔** (`UI-6-AC1`).

## 도구를 왜 `axe-playwright-python` 으로 골랐나

이 저장소에는 **노드가 아예 없다** (`grep -rn "node\\|npm\\|npx" .github/workflows/`
→ 0건). `@axe-core/cli` 를 쓰면 CI 에 `setup-node` 와 `npm` 캐시가 처음 들어오고,
그 뒤로 「의존성이 어디에 적혀 있나」가 `pyproject.toml` 과 `package.json` 둘이 된다.
`axe-playwright-python` 은 **휠 안에 `axe.min.js` 를 담아** 오므로 파이썬 쪽 그룹
하나로 끝나고, 스캔이 도는 브라우저도 15.12 가 이미 띄운 그 크로미움이다.

## 기준 — WCAG 2.1 AA

조항 문면이 *「WCAG 2.1 AA 목표 (색상 단독 정보전달 금지, 명암비 4.5:1 이상,
키보드 내비게이션)」* 다. 그래서 `runOnly` 로 **그 범위의 태그만** 돌린다 — 태그를
안 주면 axe 의 실험 규칙·모범사례까지 섞여 들어와 「조항이 요구한 것」과 「도구가
덤으로 본 것」이 한 덩어리가 된다.

## ★ 차단이다 — 경고가 아니다. 그 근거

이 저장소에는 **경고**를 택한 전례가 둘 있다(`NFR-206`·`NFR-405`). 근거는 *「통과할
수 없는 검사는 꺼진다」* 였고, 그 둘은 **우리가 고칠 수 없는 상류**(미수정 취약점)를
본다. 여기는 다르다:

  ① **지금 통과한다** — 화면 넷 전건 위반 0건 (2026-09-05 실측 · 아래 출력이 증거).
  ② **원인이 전부 우리 HTML 안에 있다.** 상류가 안 고쳐 주는 것이 아니다.
  ③ `UI-6` 은 **Phase 1** 이고, 조항이 「목표」라 적었더라도 그 목표를 지금 이미
     충족하고 있다. 충족한 상태를 경고로 걸면 지키는 장치가 없다.
  ④ ★ **`::warning::` 은 상태를 갖지 않는다.** 어제의 한 건과 오늘 새로 생긴 두
     건이 같은 노란 줄로 보인다 — 실제로 `PYSEC-2026-3447` 이 그렇게 두 라운드를
     지났고, 그 경위는 `.github/workflows/tests.yml` 의 「R42」 절이 적어 두었다.

⚠ 그래서 **위반이 생기면 CI 가 멈춘다.** 그때 할 일은 이 검사를 무르게 만드는 것이
아니라 화면을 고치는 것이다. 무르게 만들어야 할 사유가 생기면 그것은 판단이므로
**여기 주석으로 남기고** 사유를 적어라 — 조용히 `xfail` 을 달지 마라.

## ⚠⚠ 「스캔이 돌지 않았다」와 「깨끗하다」를 같게 만들지 않는다

위반 0건은 *「깨끗하다」* 일 수도 *「아무 규칙도 이 화면에 닿지 않았다」* 일 수도
있고 결과만 보면 같다 (§13.0.1 ④). 그래서 아래 셋을 함께 단언한다 —
**평가된 규칙 수 > 0** · **엔진이 axe-core** · **돌아온 규칙이 전부 우리가 지정한
태그를 달고 있다**. 그리고 위반이 0건이어도 **평가된 규칙 목록을 찍는다** — 로그가
비면 그 자체가 「돌지 않았다」의 증거이고, CI 잡이 그 표식 줄을 세어 확인한다.
"""
from __future__ import annotations

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page

#: 훑을 화면. **출처는 `app/routers/ui.py` 의 화면 라우트** — 경로 인자가 없고
#: `response_class=HTMLResponse` 인 것들(`dashboard`·`model_composer`·
#: `regulation_admin`·`run_case`)이다.
#:
#: ⚠ 박아 두었지만 **낡으면 시끄럽다** — 아래
#: `test_the_scanned_list_is_every_html_screen_the_app_serves` 가 앱의 OpenAPI
#: 문서와 대조해 어긋나면 빨간불을 낸다. 대조 없이 박아 두면 화면이 늘어도 이
#: 목록만 셋인 채로 남고, 그 상태는 「스캔이 깨끗하다」로 보인다.
_SCREENS: tuple[str, ...] = (
    "/",
    "/ui/model-composer",
    "/ui/regulation-admin",
    # ⚠ WP 지시문이 든 화면은 앞의 셋이다. `/ui/run` 을 **더한** 이유: 그것도
    # 사람이 보는 화면이고, 빼 두면 아래 대조 검사가 「훑지 않은 화면이 있다」로
    # 빨간불이 된다 — 빼려면 그 사유를 여기 적어야 한다.
    "/ui/run",
)

#: 조항 문면(WCAG 2.1 AA)이 정하는 태그 범위. `wcag2*` 는 2.0 의 A·AA,
#: `wcag21*` 는 2.1 이 더한 것 — **2.1 AA 는 2.0 AA 를 포함한다.**
_WCAG_21_AA_TAGS: tuple[str, ...] = ("wcag2a", "wcag2aa", "wcag21a", "wcag21aa")

#: CI 잡이 세는 **표식 줄**의 머리. 이 줄이 화면 수만큼 로그에 없으면 스캔이
#: 돌지 않은 것이고, 그때 잡은 실패한다 (`.github/workflows/tests.yml` 의 `e2e`).
#: ⚠ 문면을 바꾸면 그 잡의 확인도 함께 고쳐야 한다.
_MARKER = "=== axe 스캔"


def _describe_nodes(nodes: list[dict], limit: int = 5) -> list[str]:
    """걸린 요소를 사람이 찾아갈 수 있는 모양으로 편다."""
    lines = []
    for node in nodes[:limit]:
        target = ", ".join(str(item) for item in node.get("target", []))
        snippet = " ".join(str(node.get("html", "")).split())[:160]
        lines.append(f"        요소 {target} · {snippet}")
    if len(nodes) > limit:
        lines.append(f"        … 외 {len(nodes) - limit}건")
    return lines


@pytest.mark.req("UI-6-AC1")
@pytest.mark.parametrize("path", _SCREENS)
def test_screen_has_no_wcag_21_aa_violation(
    page: Page, live_server: str, path: str
) -> None:
    """화면 하나를 WCAG 2.1 AA 로 훑는다 — **위반이 있으면 멈춘다.**

    ⚠ 위반을 세기만 하지 않는다. **규칙 id · 영향도 · 걸린 요소**를 그대로 찍는다 —
    개수만 남으면 다음 사람이 로그를 열고도 무엇을 고쳐야 하는지 알 수 없다.
    """
    response = page.goto(f"{live_server}{path}")
    assert response is not None and response.ok, (
        f"{path} 를 열지 못했다 — 스캔할 화면이 없다"
    )

    results = Axe().run(
        page,
        options={
            # ⚠ `resultTypes` 를 좁히지 않는다. `passes` 를 함께 받아야
            # 「규칙이 실제로 평가되었다」를 말할 수 있다.
            "runOnly": {"type": "tag", "values": list(_WCAG_21_AA_TAGS)},
        },
    )
    report = results.response

    violations = report["violations"]
    incomplete = report["incomplete"]
    passes = report["passes"]
    engine = report["testEngine"]
    evaluated = len(violations) + len(incomplete) + len(passes)

    print(
        f"{_MARKER} · {path} · {engine['name']} {engine['version']}"
        f" · 평가 {evaluated}건 · 위반 {len(violations)}건"
        f" · 검토필요 {len(incomplete)}건 ==="
    )
    for item in violations:
        print(f"    위반 {item['id']} ({item['impact']}) · 태그 {item['tags']}")
        print("\n".join(_describe_nodes(item["nodes"])))
    for item in incomplete:
        # ★ 「검토필요」는 axe 가 **판정하지 못한** 것이다. 위반으로 세지 않지만
        #   숨기지도 않는다 — 숨기면 사람이 봐야 할 것이 사라진다.
        print(f"    검토필요 {item['id']} ({item['impact']}) · 태그 {item['tags']}")
        print("\n".join(_describe_nodes(item["nodes"])))
    if not violations:
        # ⚠ 0건일 때 **무엇이 평가되었는지**를 찍는다. 안 찍으면 로그에서
        #   「깨끗하다」와 「돌지 않았다」가 같은 침묵이 된다.
        print(f"    위반 0건 — 통과한 규칙: {sorted(item['id'] for item in passes)}")

    # ── 스캔이 실제로 돌았는가 ─────────────────────────────────────────
    assert engine["name"] == "axe-core", f"스캔 엔진이 axe-core 가 아니다: {engine}"
    assert evaluated > 0, (
        f"{path} 에서 평가된 규칙이 0건이다 — 스캔이 화면에 닿지 않았다. "
        "이것은 「깨끗하다」가 아니다"
    )
    stray = sorted(
        item["id"]
        for item in violations + incomplete + passes
        if not set(item["tags"]) & set(_WCAG_21_AA_TAGS)
    )
    assert not stray, (
        f"지정한 WCAG 2.1 AA 태그 밖의 규칙이 섞였다: {stray} — "
        "`runOnly` 가 먹지 않았다면 이 스캔의 범위는 조항의 범위가 아니다"
    )

    # ── 판정 ───────────────────────────────────────────────────────────
    assert not violations, (
        f"{path} 에 WCAG 2.1 AA 위반 {len(violations)}건: "
        + "; ".join(f"{item['id']}({item['impact']}) {len(item['nodes'])}건"
                    for item in violations)
        + " — 위 출력에 걸린 요소가 있다"
    )


def test_the_scanned_list_is_every_html_screen_the_app_serves(
    page: Page, live_server: str
) -> None:
    """★ **훑지 않은 화면이 남아 있으면 빨간불이다.**

    `_SCREENS` 를 소스에 박은 대가를 여기서 치른다. 앱이 실제로 내놓는
    화면(경로 인자가 없고 `text/html` 을 내는 `GET`)을 **앱 자신의 OpenAPI
    문서에서** 얻어 대조한다 — 박아만 두면 화면이 늘어도 목록은 그대로이고,
    그 상태는 「스캔이 깨끗하다」와 구별되지 않는다 (§13.0.1 ④).

    ⚠ `app.routes` 를 파이썬으로 뒤지지 않는다. 그 자료구조의 모양은 FastAPI
    판마다 다르고(R62/WP-1 이 CI 에서 실측했다), 여기서 재려는 것은 **밖으로
    나가는 것**이므로 HTTP 로 묻는 편이 재는 대상과도 맞는다.
    """
    spec = page.request.get(f"{live_server}/openapi.json")
    assert spec.ok, f"OpenAPI 문서를 받지 못했다: {spec.status}"

    served = {
        path
        for path, operations in spec.json()["paths"].items()
        if "{" not in path
        and "text/html"
        in ((operations.get("get") or {}).get("responses", {}).get("200", {})
            .get("content", {}))
    }
    assert served, "앱이 내놓는 화면을 한 건도 찾지 못했다 — 대조할 것이 없다"
    assert served == set(_SCREENS), (
        f"훑는 목록과 앱이 내놓는 화면이 다르다.\n"
        f"  훑지 않은 화면: {sorted(served - set(_SCREENS))}\n"
        f"  없는데 훑으려는 화면: {sorted(set(_SCREENS) - served)}"
    )
