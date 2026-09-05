"""등록된 차트가 **화면으로 나오는가** — `FR-1004-AC1` · `FR-803-AC2` · `UI-6-AC1`.

`core/report/charts/` 의 7종은 진작 서 있었고 전부 실제 PNG 를 냈다. 못 하던
것은 **배포 코드가 그것을 부르는 것**이다 —
`grep -rn "render_charts\\|chart_registry" core/ app/ web/` 이 레지스트리 자신과
주석 한 줄만 냈고 호출자는 전부 `tests/` 안이었다. 조항 `FR-1004-AC1`·
`FR-803-AC1`·`FR-803-AC2` 가 그 위에 얹혀 있었다. 이 파일이 재는 것이 그
구멍이며, `test_ui_router.py`(화면이 HTTP 로 안 나갔다)·`test_ui_run.py`(폼이
실행에 안 닿았다)와 같은 형태다.

## 하나도 `core.report.charts` 를 직접 부르지 않는다 — 레지스트리 **열거**만 한다

`render_charts(SAMPLE)` 를 직접 부르는 검사는 `tests/contract/`·`tests/report/`
에 이미 있고 초록불이었다. 그 초록불이 말하지 못한 것이 *「배포 코드가 부르는가」*
다. 그래서 여기서는 그림을 **`TestClient(create_app())` 를 지나서만** 받는다.

## 수를 박지 않는다

「차트가 몇 종인가」·「어느 것이 배선됐나」를 소스에 적지 않는다. 등록 목록은
`chart_registry()` 가, 배선 여부는 `app.services.ui_charts.unwired_reason()` 이
정본이다 — 박으면 차트가 하나 늘 때 이 검사가 조용히 낡는다.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.ui_charts import chart_data, unwired_reason
from app.services.ui_run import run_ui_case
from core.report.charts import chart_registry

#: PNG 파일 서명. **이것으로 「그렸다」와 「200 을 냈다」가 갈린다** —
#: `tests/contract/test_chart_contract.py` 가 같은 상수를 같은 이유로 쓴다.
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

#: 재료가 없어 못 그리는 차트에 쓰는 상태 코드. **500 도 404 도 아니다** —
#: 근거는 `app/routers/ui.py::chart_png` 의 표에 있다.
UNWIRED_STATUS = 501

#: 대조에 쓰는 골든 시나리오. `test_ui_run.py` 와 같은 것을 쓴다.
_SCENARIO = "scenario_unsubsidized"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.mark.req("FR-1004-AC1")
def test_every_registered_chart_answers_over_http(client: TestClient) -> None:
    """★ **등록된 차트가 전건** 화면에서 나온다 — 열거해서 돈다.

    ⚠ 「6종이 나온다」처럼 수를 박지 않는다. 박으면 차트가 하나 늘 때 이 검사가
    통과한 채로 낡고, 그 상태에서 새 그림은 아무 데도 안 나온다.

    재료가 없는 차트도 **말을 해야 한다.** 조용히 404 나 빈 응답으로 두면
    「그릴 수 없다」와 「그런 그림이 없다」가 같아진다 — `render_charts` 가
    입력이 모자란 차트를 건너뛰지 않는 것과 같은 판단이다.
    """
    registry = chart_registry()
    assert registry, "등록된 차트가 없다 — 대조할 것이 없다"

    for tag in sorted(registry):
        response = client.get(f"/ui/chart/{tag}.png", params={"scenario": _SCENARIO})
        reason = unwired_reason(tag)
        if reason is None:
            assert response.status_code == 200, f"{tag}: {response.text}"
            continue
        assert response.status_code == UNWIRED_STATUS, (
            f"{tag}: 재료가 없는 차트가 {response.status_code} 로 답했다. "
            f"{UNWIRED_STATUS} 이어야 한다 — 「아직 배선되지 않았다」와 "
            "「그런 차트가 없다」·「서버가 깨졌다」는 다른 진술이다"
        )
        body = response.json()["detail"]
        assert body["field"] == f"chart.{tag}"
        assert reason in body["reason"], f"{tag}: 응답이 사유를 싣지 않았다"
        assert body["action"], f"{tag}: 조치가 비어 있다 (NFR-303)"


@pytest.mark.req("FR-1004-AC1")
def test_what_comes_back_is_a_real_png(client: TestClient) -> None:
    """**나온 것이 진짜 PNG 다** — 200 만 재면 빈 응답도 통과한다.

    이 저장소가 실제로 겪은 자리다: `generate_charts()` 가 `"Cumulative Cash
    Flow Chart with BEP"` 라는 영어 문자열을 돌려주는 동안 그것을 검증하던
    테스트는 dict 에 키가 있는지만 보았고, 그 위에 `FR-1001`~`FR-1005` 가
    얹혀 있었다 (`core/contracts/chart.py` 머리말).
    """
    drawn = 0
    for tag in sorted(chart_registry()):
        if unwired_reason(tag) is not None:
            continue
        response = client.get(f"/ui/chart/{tag}.png", params={"scenario": _SCENARIO})

        assert response.status_code == 200, f"{tag}: {response.text}"
        assert response.headers["content-type"] == "image/png", (
            f"{tag}: {response.headers['content-type']}"
        )
        assert response.content.startswith(PNG_MAGIC), f"{tag}: PNG 가 아니다"
        assert len(response.content) > 1000, f"{tag}: 그림이라기에 너무 작다"
        drawn += 1

    assert drawn, "PNG 로 나온 차트가 한 건도 없다"


@pytest.mark.req("FR-1004-AC1")
def test_the_dashboard_lays_the_grid_out_from_the_registry(client: TestClient) -> None:
    """★ **대시보드가 레지스트리로 편다** — 라벨을 소스에 박지 않는다.

    종전 `visual-grid` 는 `<h3>` 여섯 개를 박아 두었고 그림은 하나도 없었다.
    여기서 재는 것은 「그림이 있다」가 아니라 **「목록이 레지스트리에서 온다」**
    이며, 그래야 차트가 늘 때 화면이 따라온다.

    ⚠ 못 그리는 칸도 **있어야 한다.** 빠지면 화면이 조용히 줄고, 줄어든 것은
    사람이 없는 칸을 찾을 때까지 드러나지 않는다.
    """
    body = client.get("/").text

    for tag, chart in sorted(chart_registry().items()):
        assert f'data-chart="{tag}"' in body, f"{tag}: 화면에 칸이 없다"
        if unwired_reason(tag) is None:
            assert f'src="/ui/chart/{tag}.png' in body, f"{tag}: 그림 주소가 없다"
        else:
            assert "아직 배선되지 않았다" in body, f"{tag}: 사유 표시가 없다"
        assert chart.label in body, f"{tag}: 라벨이 화면에 없다"


@pytest.mark.req("UI-6-AC1")
def test_every_drawn_figure_carries_a_real_alt(client: TestClient) -> None:
    """**`alt` 가 비어 있지 않고 라벨보다 길다** — WCAG 2.1 AA.

    `UI-6` 은 *「색상 단독 정보전달 금지」* 이고 **그림은 색으로만 말한다** —
    토네이도의 붉은 막대가 「결론이 뒤집히는 인자」라는 것, 모델 비교의 붉은
    막대가 「회수하지 못한 변형」이라는 것은 그림 안 어디에도 글자로 없다.
    `alt` 가 라벨만 갖고 있으면 그림을 못 보는 사람에게 남는 것이 제목뿐이다.
    """
    body = client.get("/").text
    figures = re.findall(r'<img src="/ui/chart/([^.]+)\.png[^"]*" alt="([^"]*)"', body)
    assert figures, "대시보드에 그림이 한 장도 없다"

    registry = chart_registry()
    for tag, alt in figures:
        label = registry[tag].label
        assert alt.strip(), f"{tag}: alt 가 비어 있다"
        assert len(alt) > len(label), (
            f"{tag}: alt 가 라벨보다 길지 않다 — 설명이 없다는 뜻이다: {alt!r}"
        )


def test_an_unknown_chart_tag_is_a_404_that_lists_the_registered_ones(
    client: TestClient,
) -> None:
    """모르는 태그는 **404** 이고 문면에 등록 태그가 있다.

    ⚠ 목록을 여기 박지 않는다 — `chart_registry()` 로 대조한다. 등록 태그를
    문면에 싣는 것은 `render_charts` 가 이미 쓰는 관용구이며, 없으면 받는
    사람에게 「무엇을 부를 수 있는가」가 도달하지 않는다.
    """
    response = client.get("/ui/chart/없는차트.png")

    assert response.status_code == 404, response.text
    detail = response.json()["detail"]
    for tag in chart_registry():
        assert tag in detail, f"{tag} 이(가) 오류 문면에 없다"


@pytest.mark.req("FR-803-AC2")
def test_the_tornado_draws_the_same_influences_the_report_ranks() -> None:
    """★ **토네이도가 리포트의 영향도와 같은 것을 그린다.**

    그림이 별도의 순위를 그리면 화면의 「영향도 순위」 목록과 그림이 갈릴 수
    있고, 갈려도 **둘 다 그럴듯해 보인다.** 그래서 이름·폭·전환 여부 셋을
    `CaseReport.influences` 와 **순서까지** 맞대고 본다.

    ⚠ 기댓값을 박지 않는다 — 대장 판이 오르면 폭이 움직이는데, 박으면 그날
    이 검사가 「그림이 틀렸다」로 빨간불이 된다.
    """
    report = run_ui_case(_SCENARIO).report
    passed = chart_data(report, "tornado")["influences"]

    assert passed, "리포트가 영향도를 한 건도 내지 않았다 — 대조할 것이 없다"
    assert [item["name"] for item in passed] == [
        entry.variable for entry in report.influences
    ]
    assert [item["delta"] for item in passed] == [
        entry.delta_won for entry in report.influences
    ]
    assert [item["flips_conclusion"] for item in passed] == [
        entry.flips_conclusion for entry in report.influences
    ]


@pytest.mark.req("FR-1004-AC1")
def test_the_picture_follows_the_arrangement_the_screen_chose(
    client: TestClient,
) -> None:
    """**고른 갈래가 그림에도 간다** — 화면의 수와 그림이 같은 실행이어야 한다.

    결과 화면이 그림 주소에 질의를 달지 않으면 위의 NPV 는 고른 갈래의 것인데
    아래 그림은 기본 갈래의 것이 되고, **그 어긋남은 아무 오류도 내지 않는다.**

    ⚠ 어느 갈래인지 박지 않는다 — 화면이 그린 라디오 값 중 전제를 요구하지
    않아 그대로 도는 것을 골라 쓴다.
    """
    body = client.get("/").text
    chosen = next(
        value
        for value in re.findall(r'name="arrangement" value="([^"]*)"', body)
        if value
        and client.get(
            "/ui/run", params={"scenario": _SCENARIO, "arrangement": value}
        ).status_code
        == 200
    )

    result = client.get(
        "/ui/run", params={"scenario": _SCENARIO, "arrangement": chosen}
    )
    assert result.status_code == 200, result.text

    sources = re.findall(r'<img src="(/ui/chart/[^"]+)"', result.text)
    assert sources, "결과 화면에 그림이 한 장도 없다"
    for source in sources:
        assert "arrangement=" in source, f"그림 주소에 갈래가 없다: {source}"
        answer = client.get(source.replace("&amp;", "&"))
        assert answer.status_code == 200, f"{source}: {answer.text}"
        assert answer.content.startswith(PNG_MAGIC), f"{source}: PNG 가 아니다"
