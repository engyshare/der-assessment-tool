"""작업 R63/V2 — **사용자 문면 여섯을 브라우저로 눌러 찾은 것을 굳힌다.**

## 이 파일의 두 시험은 지금 빨간불이다 — 그것이 목적이다

WP-V2 판정 ①: 이 축은 **판정자**라 소스를 고치지 않는다. 그래서 찾은 결함은
**고친 뒤 초록불이 될 시험**으로만 남긴다 — 시험 없이 result 파일에만 적으면,
고치는 날 그 결함이 다시 살아나도 아무 검사가 걸리지 않는다.

- **D10** — `test_an_override_of_an_equipment_price_key_moves_the_run`
- **D11** — `test_form_screens_do_not_call_the_ledger_by_the_old_word_in_chrome`

## 재-띄우기 검사는 저장 자리를 `tmp_path` 로 준다

`app/routers/scenarios.py` 는 `DER_SCENARIO_STORE` 가 있을 때만 파일 저장소를
쓴다. 주지 않고 「앱을 다시 띄워도 남아 있나」를 재면 인메모리 저장을
「안 남는다」로 적게 되어 **거짓 결함**이다 — 그래서 아래 `store_server` 픽스처는
반드시 그 환경변수를 `tmp_path` 로 주고 앱을 띄운다(사용자 홈에 쓰레기를
남기지 않는다). 서버를 여는 방법 자체는 `tests_e2e/conftest.py` 와 같다.
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Page

from app.services.verify_steps import GAP_TAGS, STAGE_COUNT
from web.render import DEMO_MODEL, equipment_setting_groups

#: 저장소 뿌리 — `tests_e2e/` 에서 한 단계 위 (`conftest.py` 와 같은 셈).
_REPO_ROOT = Path(__file__).resolve().parents[1]

#: 실행 결과 주소 — 폼이 `method="get" action="/ui/run"` 이므로 제출은 이리로 간다.
_RUN_URL = re.compile(r"/ui/run\?")

#: 제출 단추의 접근 가능한 이름 — `test_e2e_flows.py` 와 같은 문면.
_SUBMIT = "분석 실행"

#: 무보조 골든 시나리오 — 결론축 대조의 기준 (`app/services/ui_run.py` 와 같은 사유로
#: 여기 박지 않고 화면의 목록에서 골라야 하지만, 「무보조」라는 뜻 자체가 이름에
#: 있으므로 화면이 낸 목록에서 이 낱말을 찾는다.
_UNSUBSIDIZED = "unsubsidized"


# ─────────────────────────────────────────────────────────────────────────────
# 재-띄우기 검사용 서버 — `DER_SCENARIO_STORE` 를 준 채 띄운다
# ─────────────────────────────────────────────────────────────────────────────


def _free_port() -> int:
    """비어 있는 포트 하나 — `conftest.py::_free_port` 와 같은 판단."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_healthy(
    base_url: str, process: subprocess.Popen[bytes], log_path: Path
) -> None:
    """`/health` 가 200 을 낼 때까지 기다린다 — `sleep` 으로 얼버무리지 않는다."""
    deadline = time.monotonic() + 90.0
    last = "아직 한 번도 응답하지 않았다"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"서버가 기동 중 종료했다 (종료 코드 {process.returncode}).\n"
                f"--- 서버 로그 ---\n{log_path.read_text(encoding='utf-8', errors='replace')}"
            )
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2) as response:
                if response.status == 200:
                    return
                last = f"/health 가 {response.status} 를 냈다"
        except (urllib.error.URLError, OSError) as exc:
            last = repr(exc)
        time.sleep(0.25)
    raise RuntimeError(f"90 초 안에 서버가 뜨지 않았다 — 마지막 사유: {last}")


@pytest.fixture()
def store_server(tmp_path: Path) -> Iterator[Callable[[Path], str]]:
    """저장 자리를 받아 **앱 주소**를 내놓는 개시자 — 띄운 서버는 다 정리한다.

    ⚠ 다시 부르면 **앞서 띄운 서버를 먼저 끊는다** — 재-띄우기 검사에서
    「내리고 다시 띄웠다」가 「하나 더 띄웠다」가 되면 인메모리 저장과
    구별되지 않는다(바로 이 시험의 요점이다).
    """
    started: list[subprocess.Popen[bytes]] = []

    def _stop_all() -> None:
        for process in started:
            process.terminate()
        for process in started:
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=15)
        started.clear()

    def _launch(store: Path) -> str:
        _stop_all()
        store.mkdir(parents=True, exist_ok=True)
        base_url = f"http://127.0.0.1:{_free_port()}"
        log_path = tmp_path / f"store-server-{len(started)}.log"
        env = {
            **os.environ,
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "DER_SCENARIO_STORE": str(store),
        }
        with log_path.open("wb") as log_file:
            process = subprocess.Popen(
                [
                    sys.executable, "-m", "uvicorn", "app.main:app",
                    "--host", "127.0.0.1", "--port", base_url.rsplit(":", 1)[-1],
                    "--log-level", "warning",
                ],
                cwd=_REPO_ROOT,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
            )
        started.append(process)
        _wait_until_healthy(base_url, process, log_path)
        return base_url

    try:
        yield _launch
    finally:
        _stop_all()


# ─────────────────────────────────────────────────────────────────────────────
# 공통 동작
# ─────────────────────────────────────────────────────────────────────────────


def _run_default(page: Page, live_server: str, scenario: str) -> float:
    """대시보드 폼으로 시나리오 하나를 돌리고 **날값 npv** 를 읽는다.

    ⚠ 서식 문면이 아니라 `run_result.html` 의 `data-npv` 를 읽는다
    (`test_e2e_flows.py::_npv_on_screen` 과 같은 판단).
    """
    page.goto(live_server)
    page.locator("#run-scenario").select_option(value=scenario)
    page.get_by_role("button", name=_SUBMIT).click()
    page.wait_for_url(_RUN_URL)
    page.wait_for_load_state("networkidle")
    return _npv(page)


def _npv(page: Page) -> float:
    raw = page.locator("dd.npv").get_attribute("data-npv")
    assert raw is not None, "결론 축을 날값으로 실지 않았다"
    return float(raw)


def _save_settings_and_read_npv(
    page: Page, live_server: str, name: str, key: str, value: str
) -> float:
    """설정 화면에서 대장 키 하나를 고쳐 저장하고, **적용 실행의 npv** 를 읽는다.

    칸 이름이 `val-<대장 키>` 인데 대장 키에 마침표가 있어 CSS 선택자로 잡으면
    클래스로 읽힌다 — 속성 선택자로 잡는다.
    """
    page.goto(f"{live_server}/ui/settings")
    page.fill("#settings-name", name)
    page.fill(f'[name="val-{key}"]', value)
    page.get_by_role("button", name="설정 저장").click()
    page.wait_for_url(re.compile(r"/ui/settings\?.*applied=\d+"))
    page.wait_for_load_state("networkidle")
    return _npv(page)


def _html_screens(page: Page, live_server: str) -> tuple[str, ...]:
    """앱이 내놓는 화면 전부 — OpenAPI 문서가 정본이다 (`test_e2e_flows.py` 와 같다)."""
    spec = page.request.get(f"{live_server}/openapi.json")
    assert spec.ok, f"OpenAPI 문서를 받지 못했다: {spec.status}"
    return tuple(sorted(
        path
        for path, operations in spec.json()["paths"].items()
        if "{" not in path
        and "text/html"
        in ((operations.get("get") or {}).get("responses", {}).get("200", {})
            .get("content", {}))
    ))


# ─────────────────────────────────────────────────────────────────────────────
# 결론축 — 화면의 수와 골든 리포트를 원 단위로 대조한다 (판정 ⑤)
# ─────────────────────────────────────────────────────────────────────────────


def test_the_run_screen_conclusion_appears_in_the_golden_report(
    page: Page, live_server: str
) -> None:
    """**화면이 낸 결론축이 골든 리포트 본문에 원 단위로 있다** — 골든 셋 전건.

    수를 여기 박지 않는다(`test_e2e_flows.py` 머리말과 같은 판단). 재는 것은
    **두 산출물의 일치**다: 같은 시나리오를 폼으로 돌린 화면의 `data-npv` 와
    `/reports/golden/<이름>` 의 문면. 골든이 판을 올리면 둘이 함께 움직여야 하며,
    화면만 움직이면 이 시험이 잡는다.
    """
    page.goto(live_server)
    values = page.eval_on_selector_all(
        "#run-scenario option", "els => els.map(e => e.value)"
    )
    assert values, "실행 폼의 시나리오 목록이 비었다"

    mismatches: list[str] = []
    for scenario in values:
        npv = _run_default(page, live_server, scenario)
        golden = page.request.get(f"{live_server}/reports/golden/{scenario}")
        assert golden.ok, f"{scenario} 골든 리포트가 {golden.status} 를 냈다"
        formatted = f"{npv:,.0f}원"
        if formatted not in golden.text():
            mismatches.append(f"{scenario}: 화면 {formatted} 이 골든 본문에 없다")
    assert not mismatches, "\n  ".join(mismatches)


# ─────────────────────────────────────────────────────────────────────────────
# 나 · 다 — 고친 설정 값이 실행에 닿는가 (FR-602-AC1)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("FR-602-AC1")
def test_an_override_of_a_ledger_price_key_moves_the_run(
    page: Page, live_server: str
) -> None:
    """★ **대장 단가를 고치면 결론축이 움직인다** — `benefit.rec_price` 갈래.

    이 키는 `core/report/case_report.py` 가 **오버라이드된 대장(provider)에서**
    직접 읽는 갈래다(`required_scalar`). 그래서 화면에서 고친 값이 실행에 닿는
    통로가 **살아 있음을** 이 시험이 붙든다 — 아래 `capex` 갈래 시험(D10)과
    짝을 이뤄, 어느 쪽이 고장인지를 갈라 본다.
    """
    page.goto(live_server)
    unsubsidized = next(v for v in
                        page.eval_on_selector_all(
                            "#run-scenario option", "els => els.map(e => e.value)")
                        if _UNSUBSIDIZED in v)
    baseline = _run_default(page, live_server, unsubsidized)

    applied = _save_settings_and_read_npv(
        page, live_server, "e2e-rec-140", "benefit.rec_price", "140"
    )
    assert applied != baseline, (
        f"REC 단가 오버라이드(70→140)가 결론축을 움직이지 않았다: {baseline} → "
        f"{applied}. 대장에서 직접 읽는 갈래마저 죽었다면 통로 전체가 끊긴 것이다"
    )


@pytest.mark.req("FR-602-AC1")
def test_an_override_of_an_equipment_price_key_moves_the_run(
    page: Page, live_server: str
) -> None:
    """★★ **D10 재현 — 설비 단가를 고쳐도 결론축이 1원도 안 움직인다.**

    사용자 문면 「설정」: *「설비별 단가, 이용률 등」* 을 고쳐 저장하고 그 값으로
    실행되는지를 요구했다. 화면은 `capex.pv.rooftop` 칸을 내놓고, 저장하면
    「기준 전제 대비 변경 항목」 표에 대장 값과 내 값을 나란히 보여주며, 심지어
    *「시나리오에 붙이면 같은 값으로 돈다」* 고 적는다 — 그런데 실행은
    `core/casegrid/e2e_runner.py` 가 이 키를 **파일에서 지어지는 수준표**
    (`build_level_map`, `core/report/case_report.py`)에서 읽으므로 오버라이드가
    닿지 않고, 200 초록불인 채 같은 수를 낸다.

    위 `benefit.rec_price` 시험과 같은 폼·같은 저장·같은 적용 경로다 — 갈래만
    다르다. 이 시험이 빨간불인 동안 「설정을 고쳐 실행한다」는 문면에서
    단가·요금 축은 성립하지 않는다.
    """
    page.goto(live_server)
    unsubsidized = next(v for v in
                        page.eval_on_selector_all(
                            "#run-scenario option", "els => els.map(e => e.value)")
                        if _UNSUBSIDIZED in v)
    baseline = _run_default(page, live_server, unsubsidized)

    applied = _save_settings_and_read_npv(
        page, live_server, "e2e-capex-150", "capex.pv.rooftop", "1500000"
    )
    assert applied != baseline, (
        f"설비 단가 오버라이드(1,600,000→1,500,000 원/kW, 12kW 를 곱하면 "
        "약 120만원)가 "
        f"결론축을 움직이지 않았다: {baseline} → {applied}. 화면의 변경 표는 "
        "값이 바뀌었다고 인쇄하므로, 이 상태는 「골랐는데 안 먹었다」다"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 가+ — 앱을 다시 띄워도 남아 있나 (FR-902-AC1)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("FR-902-AC1")
def test_scenarios_and_settings_survive_an_app_restart(
    page: Page, store_server: Callable[[Path], str], tmp_path: Path
) -> None:
    """★★ **가+ — 시나리오·설정을 저장하고 앱 프로세스를 내려 다시 띄운다.**

    같은 프로세스에서 읽으면 인메모리 저장과 파일 저장이 구별되지 않는다
    (WP-V2 판정 ② ⚠⚠⚠). 그래서 서버를 **끄고** 같은 `DER_SCENARIO_STORE` 로
    **새 프로세스**를 띄워 목록을 다시 읽는다. 저장 자리는 `tmp_path` 다.
    """
    store = tmp_path / "store"

    first = store_server(store)
    page.goto(f"{first}/ui/scenarios")
    page.fill("#save-name", "e2e-재시작-시나리오")
    page.select_option("#save-arrangement", "자가용 없음")
    page.get_by_role("button", name="시나리오 저장").click()
    page.wait_for_url(re.compile(r"/ui/scenarios\?saved=\d+"))

    page.goto(f"{first}/ui/settings")
    page.fill("#settings-name", "e2e-재시작-설정")
    page.fill('[name="val-benefit.rec_price"]', "140")
    page.get_by_role("button", name="설정 저장").click()
    page.wait_for_url(re.compile(r"/ui/settings\?.*applied=\d+"))

    second = store_server(store)
    page.goto(f"{second}/ui/scenarios")
    expect_saved = page.locator(
        'tr[data-scenario-id] td.scenario-name', has_text="e2e-재시작-시나리오"
    )
    assert expect_saved.count() == 1, "다시 띄운 앱에 저장한 시나리오가 없다"

    page.goto(f"{second}/ui/settings")
    kept = page.locator("li[data-settings-id]", has_text="e2e-재시작-설정")
    assert kept.count() == 1, "다시 띄운 앱에 저장한 설정이 없다"


# ─────────────────────────────────────────────────────────────────────────────
# 마 — 설비 설정은 자원 인스턴스마다 한 묶음 (UI-1-AC1)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("UI-1-AC1")
def test_equipment_settings_are_grouped_per_resource_instance(
    page: Page, live_server: str
) -> None:
    """★ **그루핑이 자원마다 한 묶음이고 칸을 하나도 잃지 않는다** (덧붙임 ⓔ).

    묶음의 기댓값을 여기 박지 않는다 — `web.render::equipment_setting_groups`
    가 정본이고 화면은 그 출력을 그린다. 잴 것은 **화면이 실제로 배치한**
    `<fieldset class="resource-group">` 이다(마크업을 읽지 않는다).
    """
    page.goto(live_server)
    expected = equipment_setting_groups(DEMO_MODEL)
    groups = page.locator("fieldset.resource-group")
    assert groups.count() == len(expected), (
        f"데모 구성의 묶음은 {len(expected)} 인데 화면이 {groups.count()} 개를 "
        "그렸다 — 종(種) 단위로 접혔거나 묶음을 잃었다"
    )
    for index, wanted in enumerate(expected):
        drawn = groups.nth(index)
        assert drawn.locator("legend").inner_text() == wanted["name"]
        assert drawn.locator(".field").count() == len(wanted["fields"]), (
            f"묶음 「{wanted['name']}」 의 칸이 "
            f"{len(wanted['fields'])} 개에서 {drawn.locator('.field').count()} "
            "개로 변했다 — 묶으며 칸을 잃으면 「전체 파라미터」가 아니다"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 바 — 검증 모드: 네 걸음 × 아홉 단계, 빈 칸에는 사유가 글자로
# ─────────────────────────────────────────────────────────────────────────────


def test_the_verify_screen_carries_four_steps_nine_stages_and_reasoned_gaps(
    page: Page, live_server: str
) -> None:
    """★ **검증 모드 화면의 뼈대** — 사용자의 네 걸음 · 렌더러 아홉 단계 · 빈 칸 다섯.

    ⚠⚠ `@pytest.mark.req(...)` 를 달지 않았다 — `tests/app/test_ui_verify.py`
    머리말과 같은 판정이다. 검증 모드를 요구하는 조항이 spec 에 아직 없고,
    없는 조항을 지어 붙이면 추적표가 거짓 진술을 싣는다.

    단계 수는 `app/services/verify_steps.py::STAGE_COUNT` 에서, 빈 칸 목록은
    `GAP_TAGS` 에서 얻는다 — 렌더러가 단계를 늘리는 날 이 시험이 먼저 바뀌는
    것이 아니라 그 모듈의 「멈춘다」 판정이 먼저 선다. 네 걸음(4)만 사용자
    판정 문면이 정한 수다.
    """
    page.goto(f"{live_server}/ui/verify")
    page.wait_for_load_state("networkidle")

    assert page.locator(".verify-group[data-group]").count() == 4, (
        "사용자 판정 「결과」 의 네 걸음이 네 묶음으로 서지 않았다"
    )
    assert page.locator(".verify-group[data-group]").evaluate_all(
        "els => els.map(e => Number(e.dataset.group)).join(',')"
    ) == "1,2,3,4", "네 걸음이 1..4 순서로 서지 않았다 — 「순차적으로」가 깨진다"
    assert page.locator("[data-stage]").count() == STAGE_COUNT
    # ⚠ 단계의 **문서 순서**가 1..N 이기를 바라지 않는다 — `_GROUP_PLAN` 이
    # 4단계(편익 화폐화)를 ④ 묶음에 실으므로 화면 순서는 1,2,3,5,4,6,… 이
    # 정상이다. 재는 것은 **전건이 한 번씩** 서고 **묶음 안에서 오름차순**인가다.
    stages = page.locator("[data-stage]").evaluate_all(
        "els => els.map(e => Number(e.dataset.stage))"
    )
    assert sorted(stages) == list(range(1, STAGE_COUNT + 1)), (
        f"아홉 단계가 한 번씩 서지 않았다: {stages}"
    )
    for group in page.locator(".verify-group[data-group]").all():
        numbers = group.locator("[data-stage]").evaluate_all(
            "els => els.map(e => Number(e.dataset.stage))"
        )
        assert numbers == sorted(numbers), (
            f"묶음 안의 단계가 오름차순이 아니다: {numbers} — 따라가며 읽기가 깨진다"
        )

    silent: list[str] = []
    for tag in GAP_TAGS:
        gap = page.locator(f'[data-gap="{tag}"]')
        if gap.count() != 1:
            silent.append(f"{tag}: 칸 자체가 없다 ({gap.count()}건)")
            continue
        text = gap.inner_text().strip()
        if len(text) < 20:
            silent.append(f"{tag}: 사유가 글자로 있어야 하는데 {text!r} 뿐이다")
    assert not silent, "\n  ".join(silent)

    # 순수요 표 — 24행(대표일 24스텝)과 「대표일 하루」 캡션(착수 순서 36번 인용).
    rows = page.locator('[data-net-demand] tbody tr, .net-demand tbody tr')
    assert rows.count() == 24, (
        f"순수요 표가 24행이 아니다: {rows.count()}행 — 대표일 해상도가 바뀌었다"
    )
    caption = page.evaluate("() => document.body.innerText")
    assert "대표일 하루" in caption and "착수 순서 36" in caption, (
        "순수요 표의 캡션이 「대표일 하루」임과 착수 순서 36번을 말하지 않는다 — "
        "24행짜리 표가 「계절 변동이 없다」를 결과로 주장하게 된다"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 라 — 낱말: 옛 말은 없어야 하고, 대장을 부르는 말은 하나여야 한다
# ─────────────────────────────────────────────────────────────────────────────


def test_no_screen_prints_the_old_equipment_settings_word(
    page: Page, live_server: str
) -> None:
    """**「고급 모드」가 화면 전건에서 0건** — 사용자 문면 「용어」 · R63b §1.

    `@pytest.mark.req(...)` 를 달지 않았다 — 화면 낱말을 정하는 조항이 spec 에
    없고(판정 정본이 `docs/decisions-2026-09-05-R63b.md` 다), 조항을 지어
    붙이지 않는다.
    """
    leftover: list[str] = []
    for path in _html_screens(page, live_server):
        page.goto(f"{live_server}{path}")
        body = page.evaluate("() => document.body.innerText")
        count = body.count("고급 모드")
        if count:
            leftover.append(f"{path}: {count}건")
    assert not leftover, f"「고급 모드」가 남아 있다:\n  {'  '.join(leftover)}"


def test_form_screens_do_not_call_the_ledger_by_the_old_word_in_chrome(
    page: Page, live_server: str
) -> None:
    """★★ **D11 재현 — 시나리오·설정·검증 화면의 사람 자리에 「전제」가 있다.**

    판정 정본 R63b §1 이 대장을 부르는 말을 「분석 설정 대장」으로 못 박았고
    WP-V2 덧붙임 ⓒ 가 「사람이 읽는 자리의 「전제」는 0건」으로 재라고 했다.
    재는 자리는 **화면 겉면**(제목·`<legend>`·`<label>`·표 머리·정의 목록)으로
    한정한다 — 리포트 인쇄 문면(검증 화면의 단계 본문)과 문서 이름·대장 키는
    데이터이며 결함이 아니다.

    지금 이 시험은 빨간불이다: `scenarios.html` · `settings.html` ·
    `verify.html` 의 겉면이 아직 「전제」로 부른다(D11 — 자리는 result_V2.md).
    """
    leftover: list[str] = []
    for path in ("/ui/scenarios", "/ui/settings", "/ui/verify"):
        page.goto(f"{live_server}{path}")
        found = page.eval_on_selector_all(
            "h1, h2, h3, legend, label, th, dt, nav a",
            "els => els.filter(e => e.textContent.includes('전제'))"
            ".map(e => e.tagName.toLowerCase() + ': ' + e.textContent.trim())",
        )
        leftover.extend(f"{path} · {text}" for text in found)
    assert not leftover, (
        "사람이 읽는 자리가 대장을 아직 「전제」로 부른다 — 낱말이 둘이면 "
        "사용자가 지적한 그 갈림이 그대로다:\n  " + "\n  ".join(leftover)
    )
