"""화면 라우터(`app/`) 시험을 **끈다** — 사용자 판정 2026-09-07 (R66).

사유·규약·다시 켜는 법은 **`tests/web/conftest.py` 머리말이 정본이다.**
여기 다시 적지 않는다 — 같은 판정을 두 곳에 쓰면 한쪽만 고쳐진다.

⚠ **`app/` 도 화면이다** — FastAPI 라우터가 `web/` 의 렌더러를 불러 HTML 을 낸다
(`app/routers/ui.py` · `ui_forms.py` · `ui_scenarios.py`). 사용자 판정의
*「웹시험을 모두」* 가 이 디렉터리를 포함한다.

★ 켜는 변수는 **같은 하나**다 — `DER_RUN_WEB_TESTS=1`. 둘을 따로 두면
「웹 시험을 켰는데 절반만 돈다」가 생긴다.

⚠⚠ **`tests/report` 는 끄지 않았다.** 그것은 화면이 아니라 **산출물(리포트)** 이고
**결론축을 인쇄**한다 — 배포 리포트의 수가 틀리는 것을 잡는 유일한 그물이다.
사용자 판정의 「웹」에 들지 않는다고 판정했다(`docs/decisions-2026-09-07-R66.md` §7).

⚠⚠⚠ **경로 필터가 필수다** — `pytest_collection_modifyitems` 는 수집된 **전건**을
받는다. 사유와 실측은 `tests/web/conftest.py` 의 같은 표제 절이 갖는다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.web.conftest import skip_items_under

#: 이 `conftest.py` 가 놓인 디렉터리. **이 밑의 항목만** 건드린다.
HERE = Path(__file__).resolve().parent


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    skip_items_under(HERE, items)
