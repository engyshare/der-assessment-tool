"""R64/WP-5 — 계절별 시간대별 운전 그림이 **실제로 계절을 그리는가** (사용자 요구 6).

사용자 문면: *「계절별로 가구의 전력 수요, 발전, ESS 운전 등을 시간대별로 수치와
도표를 확인할 수 있어야 함」*. 수치는 붙임 7 의 계절별 표가 싣고
(`tests/report/test_operation_appendices.py`), 이 파일이 재는 것은 **도표**다.

## 「PNG 가 나왔다」에서 멈추지 않는다

계절 넷을 받아 **첫 계절만 그려도 PNG 는 나온다.** 그러면 검사는 초록불이고
심의 자료에는 봄 하루가 「계절별 운전」이라는 제목으로 실린다 — 이 저장소가
반복해 만난 *「검사는 있었는데 아무것도 붙들지 않았다」* 가 정확히 그 형태다
(`tests/report/test_charts_feasible_region.py` 머리말이 같은 자리에서 같은
판단을 적었다).

그래서 **층마다 따로 붙든다** — 입력의 한 층만 바꿔 바이트가 달라지는지 본다.

| 무엇을 바꾸나 | 무엇이 붙들리나 |
|---|---|
| **뒤쪽 계절**의 하루만 바꾼다 | 첫 계절만 그리면 바이트가 같다 |
| 계절의 **이름**만 바꾼다 | 계절 축의 라벨을 안 그리면 바이트가 같다 |
| 자원 하나의 **부호**를 뒤집는다 | 0 아래로 쌓지 않으면(절댓값으로 그리면) 같다 |

## ⚠ `@pytest.mark.req(...)` 를 달지 않았다

`FR-1004-AC1` 은 차트 여섯을 **이름으로** 나열하고 그 목록에 계절별 그림이
없다. 이 그림이 그 조항의 첫 항목(*「일간 대표일 디스패치 스택」*)을 계절마다
그린 것이라는 판단으로 `clauses` 는 그 조항을 가리키지만, 그 판단을 **매핑표에
「이 조항이 검증됐다」로 실을 만큼** 조항 문면이 계절을 말하지는 않는다 —
`tests/app/test_ui_verify.py` 머리말이 같은 자리에서 같은 판정을 적었다.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.contracts.validation import ValidationError
from core.report.charts import chart_registry, render_charts
from core.report.charts.seasonal_operation import _DEMAND_LABEL, SeasonalOperation
from core.report.dispatch_notes import DEMAND_LABEL

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

#: 계절 둘 · 하루 네 스텝. **그림을 재기 위한 표본**이며 사업 전망이 아니다 —
#: 계절 이름·일수는 배포 경로에서 자산(`fixtures/profiles/representative-day.
#: yaml`)이 정한다. 이 수를 리포트·검토서에 인용하지 마라.
_SPRING: dict[str, Any] = {
    "name": "봄",
    "days": 92,
    "resource_dispatch": {"PV": [0.0, 3.0, 5.0, 2.0], "ESS": [1.0, -2.0, 0.0, 1.0]},
    "load": [4.0, 5.0, 6.0, 3.0],
}
_WINTER: dict[str, Any] = {
    "name": "겨울",
    "days": 90,
    "resource_dispatch": {"PV": [0.0, 1.5, 2.5, 1.0], "ESS": [0.5, -1.0, 0.0, 0.5]},
    "load": [5.0, 6.0, 7.0, 4.0],
}


def _data(*seasons: dict[str, Any]) -> dict[str, Any]:
    return {"seasons": [dict(season) for season in seasons]}


def _png(data: dict[str, Any]) -> bytes:
    return SeasonalOperation().render(data).payload


def test_the_chart_is_registered_and_draws_real_bytes() -> None:
    """**파일 하나를 놓았더니 레지스트리가 늘었고 진짜 PNG 가 나온다.**

    `core/report/charts/__init__.py` 를 한 줄도 고치지 않았다는 것이 이
    레지스트리의 확장점 규약이며(그 파일 머리말), 등록만 되고 그리지 않는
    상태를 막는 것이 PNG 서명 대조다.
    """
    registry = chart_registry()
    assert registry[SeasonalOperation.tag] is SeasonalOperation

    artifact = render_charts(_data(_SPRING, _WINTER), tags=(SeasonalOperation.tag,))[
        SeasonalOperation.tag
    ]
    assert artifact.payload.startswith(PNG_MAGIC)
    assert len(artifact.payload) > 1000, "그림이라기에 너무 작다"
    assert artifact.clauses, "조항을 가리키지 않는다"


def test_a_later_season_actually_reaches_the_picture() -> None:
    """★★★ **뒤쪽 계절을 그린다** — 첫 계절만 그리면 여기서 갈린다.

    계절 넷을 받아 하나만 그려도 PNG 는 나오고 제목은 「계절별」이다. 그
    상태가 심의 자료에 실리면 검토자는 봄 하루를 한 해로 읽는다.
    """
    moved = dict(_WINTER)
    moved["resource_dispatch"] = {
        "PV": [0.0, 4.5, 1.0, 0.5],   # 봉우리를 옮겼다
        "ESS": _WINTER["resource_dispatch"]["ESS"],
    }

    assert _png(_data(_SPRING, _WINTER)) != _png(_data(_SPRING, moved)), (
        "둘째 계절의 하루를 바꿨는데 그림이 같다 — 첫 계절만 그리고 있다"
    )


def test_the_season_name_and_days_reach_the_picture() -> None:
    """★★ **계절 축의 이름·일수가 그림에 닿는다.**

    이름을 안 그리면 네 구간이 무엇인지 그림 안에 없고, 그때 남는 것은
    「막대가 네 무리다」뿐이다. 일수를 함께 재는 이유는 계절 몫이 **일수로**
    연간에 곱해지기 때문이다 — 90일과 92일은 다른 계절이다.
    """
    renamed = dict(_WINTER, name="한겨울")
    assert _png(_data(_SPRING, _WINTER)) != _png(_data(_SPRING, renamed)), (
        "계절 이름을 바꿨는데 그림이 같다 — 축에 이름을 그리지 않는다"
    )

    relabelled = dict(_WINTER, days=31)
    assert _png(_data(_SPRING, _WINTER)) != _png(_data(_SPRING, relabelled)), (
        "계절 일수를 바꿨는데 그림이 같다 — 그림이 일수를 말하지 않는다"
    )


def test_charging_is_drawn_below_the_zero_line() -> None:
    """★★★ **받아들인 전력이 0 아래로 간다** — 절댓값으로 그리면 여기서 갈린다.

    저장장치의 충전은 음수다(`DispatchHour` 부호 규약). 절댓값으로 쌓으면
    「그 시각에 방전했다」와 「충전했다」가 그림에서 같아지고, 그 그림은
    ESS 운전을 **거꾸로** 말한다.
    """
    flipped = dict(_SPRING)
    flipped["resource_dispatch"] = {
        "PV": _SPRING["resource_dispatch"]["PV"],
        "ESS": [-v for v in _SPRING["resource_dispatch"]["ESS"]],
    }

    assert _png(_data(_SPRING, _WINTER)) != _png(_data(flipped, _WINTER)), (
        "저장장치의 부호를 뒤집었는데 그림이 같다 — 충전과 방전이 같은 자리에 "
        "그려지고 있다"
    )


def test_a_run_without_seasons_is_refused_in_three_parts() -> None:
    """★★★ **재료가 없으면 빈 그림이 아니라 거부다** (`NFR-303` · 판정 ⑥).

    조용히 빈 그림을 내면 「그렸다」로 집계되고 그 빈자리는 심의자료가 인쇄된
    뒤에 발견된다 — `render_charts` 독스트링과 `ChartArtifact.__post_init__`
    가 같은 판단을 이미 두 번 적었다.
    """
    with pytest.raises(ValidationError) as caught:
        _png({"seasons": []})

    err = caught.value
    assert err.field.startswith(f"chart.{SeasonalOperation.tag}")
    assert err.reason, "사유가 비어 있다"
    assert err.action, "조치가 비어 있다 (NFR-303)"


@pytest.mark.parametrize(
    ("broken", "what"),
    [
        ({"name": "여름", "days": 92, "load": [1.0, 2.0]}, "칸이 없다"),
        (
            {
                "name": "여름", "days": 92,
                "resource_dispatch": {"PV": [1.0, 2.0, 3.0]},
                "load": [1.0, 2.0],
            },
            "스텝 수가 다르다",
        ),
        (
            {
                "name": "여름", "days": 92,
                "resource_dispatch": {"태양광": [0.0, 1.0, 2.0, 1.0]},
                "load": [1.0, 2.0, 3.0, 2.0],
            },
            "자원 목록이 다르다",
        ),
    ],
)
def test_a_malformed_season_is_refused_not_patched(
    broken: dict[str, Any], what: str
) -> None:
    """★★ **모자란 계절을 메우지 않고 거부한다.**

    빠진 칸을 0 으로 채우거나 짧은 배열을 늘려 그리면 그림은 정상으로 보이고
    심의에서 그것이 실제 결과로 읽힌다 (`app/services/ui_charts.py` 머리말의
    *「수를 지어내지 않는다 — 그림도 수다」*).

    ⚠ 문면을 리터럴로 박지 않는다 — **3요소가 서는가**와 그 사유가 어느 계절을
    가리키는가만 본다.
    """
    with pytest.raises(ValidationError) as caught:
        _png(_data(_SPRING, broken))

    err = caught.value
    assert err.field.startswith(f"chart.{SeasonalOperation.tag}"), what
    assert err.action, f"{what}: 조치가 비어 있다 (NFR-303)"


def test_the_demand_legend_uses_the_canonical_word_not_a_copy() -> None:
    """★★★ **수요 곡선의 범례가 정본 상수를 «가리킨다»** (R68/WP-3).

    이 글자는 그림·화면 표·검증 보고서 표 **셋**이 함께 쓴다. 종전에는 그림과
    화면이 각자 적어 두고 검사가 두 글자를 맞댔는데(`tests/app/
    test_ui_charts.py`), 자리가 셋이 되면서 그 방식이 버티지 못했다. 정본은
    `core/report/dispatch_notes.py::DEMAND_LABEL` 이며 **이 모듈이 그것을 갖지
    않는 이유는 계층이 아니라 의존성**이다 — 이 파일은 `matplotlib` 을 끄는
    `_render` 를 모듈 수준에서 import 하므로, 글자를 여기 두면 «표»를 짓는
    텍스트 층이 그림 묶음을 끌어오게 된다.

    ⚠ `is` 로 잰다 — 값이 같은 사본을 다시 적어 넣으면 그때부터 한쪽만 고쳐질 수
    있고, 값 비교는 그 순간을 잡지 못한다.
    """
    assert _DEMAND_LABEL is DEMAND_LABEL, (
        f"그림이 정본 상수를 쓰지 않는다 — {_DEMAND_LABEL!r}"
    )
