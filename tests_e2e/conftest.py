"""브라우저와 **실제로 뜬 서버**를 준비한다.

## 서버를 시험이 띄운다

`TestClient` 는 ASGI 를 직접 부르므로 브라우저가 붙을 주소가 없다. 여기서 재는
것은 *「사람이 브라우저로 눌렀을 때」* 이므로 **진짜 소켓**이 있어야 한다.

⚠ **`sleep` 으로 얼버무리지 않는다.** 준비될 때까지 `/health` 를 폴링한다 —
`sleep` 은 느린 기계에서 「아직 안 떴다」를 「화면이 깨졌다」로 둔갑시키고, 그때
빨간불의 원인은 시험 자신이다.

⚠ **못 띄우면 `skip` 하지 않고 실패한다.** 건너뛴 검사는 초록불과 구별되지
않는다(§13.0.1 ④). 서버 로그를 파일로 받아 실패 메시지에 그대로 싣는다 —
「서버가 안 떴다」만 적으면 왜 안 떴는지는 아무 데도 남지 않는다.

⚠ 서버 로그를 `PIPE` 로 받지 않는다. 폴링하는 동안 아무도 읽지 않으므로 파이프가
차면 uvicorn 이 그 자리에서 멈추고, 그 멈춤은 「기동이 느리다」와 구별되지 않는다.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

#: 저장소 뿌리 — `tests_e2e/conftest.py` 에서 한 단계 위.
_REPO_ROOT = Path(__file__).resolve().parents[1]

#: 기동을 기다리는 한도(초). 넉넉하게 두는 이유: CI 러너의 첫 import 는
#: matplotlib·pydantic 을 끌어오느라 로컬보다 오래 걸린다.
_STARTUP_TIMEOUT_SECONDS = 90.0

#: 폴링 간격(초).
_POLL_INTERVAL_SECONDS = 0.25


def _free_port() -> int:
    """비어 있는 포트 하나 — **박지 않는다.**

    포트를 소스에 박으면 그 포트를 쓰는 다른 것이 있을 때 「화면이 안 뜬다」로
    빨간불이 되고, 원인은 화면이 아니다.
    """
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_healthy(base_url: str, process: subprocess.Popen[bytes],
                        log_path: Path) -> None:
    """`/health` 가 200 을 낼 때까지 기다린다 — 그 라우트가 `app/routers/health.py` 다."""
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    last_error: str = "아직 한 번도 응답하지 않았다"
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
                last_error = f"/health 가 {response.status} 를 냈다"
        except (urllib.error.URLError, OSError) as exc:  # 아직 소켓이 안 열렸다
            last_error = repr(exc)
        time.sleep(_POLL_INTERVAL_SECONDS)
    raise RuntimeError(
        f"{_STARTUP_TIMEOUT_SECONDS} 초 안에 서버가 뜨지 않았다 — 마지막 사유: {last_error}\n"
        f"--- 서버 로그 ---\n{log_path.read_text(encoding='utf-8', errors='replace')}"
    )


@pytest.fixture(scope="session")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """`uvicorn` 을 서브프로세스로 띄우고 **주소**를 준다."""
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    log_path = tmp_path_factory.mktemp("uvicorn") / "server.log"

    # ⚠ `PYTHONUTF8` 을 넘긴다. 이 저장소의 문면은 한국어이고, 윈도우 기본
    # 코드페이지에서 uvicorn 이 라우트 설명을 찍다가 죽는 자리가 있다.
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    with log_path.open("wb") as log_file:
        process = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", "app.main:app",
                "--host", "127.0.0.1", "--port", str(port),
                "--log-level", "warning",
            ],
            cwd=_REPO_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
        )
        try:
            _wait_until_healthy(base_url, process, log_path)
            yield base_url
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=15)


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    """헤드리스 크로미움 한 벌 — 세션에 하나만 띄운다.

    ⚠ 브라우저가 없으면 **여기서 실패한다.** `skip` 으로 넘기면 「브라우저가
    없어서 안 돌았다」가 「통과」로 보인다.
    """
    playwright = sync_playwright().start()
    try:
        instance = playwright.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()
    finally:
        playwright.stop()


@pytest.fixture()
def page(browser: Browser) -> Iterator[Page]:
    """검사 하나마다 **새 문맥**. 앞 검사가 남긴 쿠키·저장소를 물려받지 않는다."""
    context = browser.new_context()
    try:
        yield context.new_page()
    finally:
        context.close()
