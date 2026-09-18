"""격자가 **넓은 그림에 온 줄을 주는가** — R64/WP-WEB ⓒ.

## 왜 이 파일이 생겼는가

CI 의 `tests_e2e/test_e2e_flows.py::
test_charts_render_at_a_readable_share_of_their_source_width` 가 브라우저로
재서 잡은 것이 이것이다 — `seasonal_operation` 만 원본이 1440px 이라 651px
칸에서 **0.452** 로 그려졌고(그 밖 11건은 0.678), 그 상태에서 「그림이
있다」를 재던 검사들은 전부 초록불이었다.

**고친 자리는 CSS 한 규칙**(`.visual-grid figure[data-chart="…"]` →
`grid-column: 1 / -1`)이며, 이 파일은 그 규칙이 **조용히 낡는 것**을 막는다:
폭이 기본값보다 넓은 차트가 새로 서는 날 브라우저 없이도 여기서 먼저 멈춘다.

⚠ **비율을 여기서 재지 않는다.** 실제 렌더 폭은 브라우저가 정하므로 그
판정은 위 e2e 가 갖는다(그 시험은 화면 전건 x 그림 전건을 잰다). 이 파일이
재는 것은 **「넓은 차트의 목록」과 「온 줄을 받는 차트의 목록」이 같은가**다.

⚠ **`web/static/wp12.css` 를 파일로 열지 않는다.** 앱이 실제로 내보내는
`/static/wp12.css` 를 받는다 — 파일을 직접 읽으면 「정적 라우트가 그 파일을
안 내보낸다」와 「규칙이 없다」가 구별되지 않는다.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from core.report.charts import chart_registry
from core.report.charts._render import new_figure

#: 온 줄을 받는 규칙. 선택자 안의 `data-chart` 이름을 전부 꺼낸다 —
#: 한 규칙에 여러 차트가 실릴 수 있으므로 **규칙이 아니라 이름을 센다.**
_FULL_ROW_RULE = re.compile(
    r"\.visual-grid\s+figure\[data-chart=\"([^\"]+)\"\]\s*\{[^}]*"
    r"grid-column:\s*1\s*/\s*-1"
)

#: 차트가 자기 그림의 폭을 적는 자리. `new_figure(width=12.0, height=5.0)`.
#: 안 적으면 서명의 기본값이며, 그 기본값도 여기 박지 않고 서명에서 읽는다.
_FIGURE_CALL = re.compile(r"new_figure\(([^)]*)\)")
_WIDTH_ARG = re.compile(r"width\s*=\s*([0-9.]+)")

#: 그림이 그려지는 화면 둘. e2e 가 재는 그 둘이며, `data-chart` 속성을
#: **둘 다** 갖고 있어야 위 선택자가 물 자리가 있다.
_SCREENS = ("/", "/ui/run")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _default_width() -> float:
    """기본 그림 폭 — **`new_figure` 의 서명이 정본이다.**

    숫자를 여기 적으면 그 기본값이 바뀌는 날 이 검사가 「전부 넓다」 또는
    「하나도 넓지 않다」로 조용히 낡는다.
    """
    default = inspect.signature(new_figure).parameters["width"].default
    return float(default)


def _figure_width(chart: type) -> float:
    """이 차트가 그리는 그림의 **가로 인치** — 차트 자신의 소스에서 읽는다.

    ⚠ 그림을 실제로 그려서 재지 않는다. 차트마다 재료(`CaseReport`)가 다르고
    일부는 아직 배선되지 않아(`501`) 그릴 수 없다 — 그런데 **폭은 재료와
    무관한 그 차트의 성질**이므로 선언을 읽는 것으로 족하다.

    ⚠ 폭을 안 적은 차트는 서명의 기본값이다(`tornado` 는 높이만 적는다).
    """
    source_file = inspect.getsourcefile(chart)
    assert source_file is not None, f"{chart!r} 의 소스 파일을 찾지 못했다"
    call = _FIGURE_CALL.search(Path(source_file).read_text(encoding="utf-8"))
    assert call is not None, (
        f"{chart!r} 가 `new_figure(...)` 를 부르지 않는다 — 이 검사가 폭을 "
        "읽을 자리가 없다"
    )
    given = _WIDTH_ARG.search(call.group(1))
    return float(given.group(1)) if given else _default_width()


def test_every_chart_wider_than_the_default_gets_a_full_row(
    client: TestClient,
) -> None:
    """★★★ **넓은 차트의 목록 == 온 줄을 받는 차트의 목록.**

    ⚠ 두 방향을 함께 잰다. 한쪽만 재면 ⓐ 넓은 차트가 새로 서도 규칙이 없는
    상태(= CI 가 잡은 그 회귀)나 ⓑ 없어진 차트의 이름이 규칙에 남아 있는
    상태가 통과한다 — 뒤쪽은 「규칙이 있다」로 보이면서 아무것도 넓히지 않는다.
    """
    css = client.get("/static/wp12.css")
    assert css.status_code == 200, css.text[:200]

    full_row = set(_FULL_ROW_RULE.findall(css.text))
    wide = {
        tag
        for tag, chart in chart_registry().items()
        if _figure_width(chart) > _default_width()
    }

    assert wide == full_row, (
        f"기본 폭({_default_width()}in)보다 넓은 차트 {sorted(wide)} 와 격자에서 "
        f"온 줄을 받는 차트 {sorted(full_row)} 가 다르다.\n"
        "  넓은 그림은 한 칸(최소 뷰포트에서 651px)에 넣으면 원본의 0.5 에 "
        "못 미치게 그려진다 — 축 눈금을 읽을 수 없고 그것이 "
        "`test_charts_render_at_a_readable_share_of_their_source_width` 가 "
        "막는 것이다.\n"
        "  ⛔ 원본 폭을 줄여 맞추지 마십시오. `web/static/wp12.css` 의 "
        "`grid-column: 1 / -1` 규칙에 그 이름을 더하십시오."
    )
    assert wide, "넓은 차트가 하나도 없다 — 이 검사가 아무것도 재지 않는다"


def test_both_chart_screens_name_their_figures_with_data_chart(
    client: TestClient,
) -> None:
    """★★ 격자 규칙이 **물 자리**가 두 화면에 다 있다.

    위 규칙의 선택자는 `figure[data-chart="…"]` 다. 템플릿 한쪽에서 그 속성이
    빠지면 그 화면에서만 그림이 좁아지고, CSS 는 여전히 「규칙이 있다」로
    보인다 — 한쪽만 고쳐지는 그 상태를 여기서 잡는다.
    """
    missing: list[str] = []
    for path in _SCREENS:
        body = client.get(path).text
        grid = body[body.index("visual-grid") :]
        for figure in re.findall(r"<figure[^>]*>", grid):
            if "data-chart=" not in figure:
                missing.append(f"{path}: {figure}")
    assert not missing, (
        "격자 안의 `figure` 가 `data-chart` 를 갖지 않는다 — 그러면 폭 규칙도 "
        "e2e 의 그림 이름 읽기도 함께 죽는다:\n  " + "\n  ".join(missing)
    )
