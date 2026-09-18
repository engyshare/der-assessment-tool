"""화면(`web/`) 시험을 **끈다** — 사용자 판정 2026-09-07 (R66).

## 왜 껐는가

사용자 판정: *「웹시험을 모두 꺼줘. 웹 구현은 가장 마지막에 하는 것으로 우선순위
조정해줘」* (정본 `docs/decisions-2026-09-07-R66.md` §7).

⇒ 웹 구현이 **가장 마지막**으로 밀렸으므로, 그 사이에 화면 시험이 도는 것은
**아직 오지 않은 구현을 기다리는 비용**이다. 실측(2026-09-07 R66): `tests/report` +
`tests/web` 직렬 **1,709초(28분)** · CI 의 `tests` 잡 **39분 20초**.

## ⛔ 지우지 않고 «끈» 이유 — 셋이다

1. **`NFR-105` 게이트(테스트 동반)가 시험의 «존재»를 본다.** 지우면 `web/` 을 고치는
   커밋이 그 게이트에서 막힌다 — 끄는 것과 지우는 것이 여기서 갈린다.
2. **다시 켜는 것이 환경변수 하나여야 한다.** 지우면 되살리는 것이 라운드 하나다.
3. **`@pytest.mark.slow` 를 쓸 수 없다.** `addopts` 에 `--strict-markers` 가 걸려 있어
   새 마커는 `pyproject.toml` 에 등록해야 하는데, 그 파일은 명세 **§16.4** 가 WP-15
   **단독 소유·append-only** 로 못 박아 이 라운드가 열 수 없다. ⇒ 내장 `skip` 으로 간다.

## ★ 다시 켜는 법 — 코드를 안 고친다

```bash
DER_RUN_WEB_TESTS=1 ./.venv/Scripts/python.exe -m pytest tests/web tests/app
```

`.github/workflows/tests.yml` 의 `env:` 에 `DER_RUN_WEB_TESTS: "1"` 을 주면 CI 에서 돈다.

⚠⚠ **웹 구현을 시작하는 라운드는 «맨 먼저» 이것을 켜라.** 끈 채로 화면을 고치면
회귀를 아무도 못 잡는다 — 이 저장소는 그 형태를 실물로 겪었다(`tests_e2e/` 가 로컬
전건에 없어 **e2e 회귀 둘을 여섯 커밋 동안 아무도 몰랐다** · 2026-09-06 실측).
착수 목록에 항목으로 세워 두었다(`status.md` 「다음에 집을 것」).

## ⚠⚠⚠ 이 훅은 수집된 «전건»을 받는다 — **경로로 걸러야 한다**

`pytest_collection_modifyitems` 는 그 `conftest.py` 가 놓인 디렉터리의 항목만 받는
것이 **아니다.** 어느 `conftest.py` 에 있든 **수집된 시험 전부**가 `items` 로 온다.

⚠ 2026-09-07 R66 이 실물로 밟았다 — 경로 필터 없이 붙였더니 **`2319 skipped` ·
`290 skipped` 로 저장소 전건이 건너뛰어지고 `rc=0`(「전건 통과」)** 이 나왔다.
**아무것도 돌지 않았는데 초록불**이었다. 이 저장소가 반복해 잡아 온 「조용한 거짓
초록불」이며, `pytest` 가 import 오류 파일을 건너뛰고 `rc=0` 을 내던 것과 같은 형태다.

⚠ **`pytest tests/web tests/app` 로만 재면 이 결함이 보이지 않는다** — 그 범위에서는
전건이 곧 화면 시험이다. **반드시 전건으로 재라.**
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

#: 이 값이 `"1"` 이면 화면 시험이 돈다. 없으면 건너뛴다.
RUN_WEB_TESTS_ENV = "DER_RUN_WEB_TESTS"

#: 이 `conftest.py` 가 놓인 디렉터리. **이 밑의 항목만** 건드린다 (위 ⚠⚠⚠).
HERE = Path(__file__).resolve().parent

SKIP_REASON = (
    "화면 시험 비활성 — 사용자 판정 2026-09-07 (R66): 웹 구현을 가장 마지막으로 "
    f"미뤘다. 켜려면 {RUN_WEB_TESTS_ENV}=1 . 웹 구현 라운드는 맨 먼저 이것을 켜라 "
    "(docs/decisions-2026-09-07-R66.md §7)"
)


def skip_items_under(directory: Path, items: list[pytest.Item]) -> None:
    """`directory` **밑의** 시험에만 `skip` 을 붙인다.

    ⚠ 수집은 그대로 둔다 — `--collect-only` 로 세는 검사와
    `scripts/gen_traceability.py`(마커를 훑어 매핑표를 만든다)가 **수집 결과를
    읽는다.** 수집 자체를 막으면 그 둘이 조용히 낡는다. 그래서 `ignore` 가 아니라
    `skip` 이다.
    """
    if os.environ.get(RUN_WEB_TESTS_ENV) == "1":
        return
    marker = pytest.mark.skip(reason=SKIP_REASON)
    for item in items:
        try:
            path = Path(str(item.fspath)).resolve()
        except (AttributeError, OSError):  # pragma: no cover - 방어
            continue
        if path.is_relative_to(directory):
            item.add_marker(marker)


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    skip_items_under(HERE, items)
