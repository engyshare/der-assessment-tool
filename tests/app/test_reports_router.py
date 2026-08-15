"""리포트가 **밖으로 나가는가** — FR-1003 · FR-1001-AC5 의 산출물 경로.

`app/routers/` 에 리포트·내보내기 엔드포인트가 0건이었다. 이 파일이 붙드는
것은 형식이 아니라 **구멍이 뚫려 있는가**다 — 조립기가 아무리 완전해도 밖으로
나갈 자리가 없으면 `MC-1` 은 시작될 수 없다.

    자동 수집에 걸린다                 ← 등록 파일을 고치지 않아도 라우트가 는다
    받은 것이 리포트다                 ← 200 과 「본문이 있다」를 구별한다
    목록 밖 이름은 거부한다            ← 경로가 저장소 밖으로 새지 않는다
    JSON 이 표준 파서로 읽힌다         ← `Infinity` 를 내지 않는다
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_report_endpoint_is_collected_and_returns_a_report(client: TestClient) -> None:
    """받은 것이 **리포트**다 — 200 만으로는 성립하지 않는다.

    ⚠ **`req()` 마커를 달지 않았다.** `FR-1003` 이 열거하는 내보내기 형식은
    XLSX·PDF·JSON·CSV 넷이며 **마크다운은 거기 없다.** `FR-1003-AC2`(PDF)를
    달아 보았고, 그것은 「PDF 를 냈다」는 거짓 진술이 된다 — 이 저장소가
    반복해서 경계해 온 «검사를 통과시키려고 인용을 맞추는» 형태다.

    조항이 비어 있는 것이 사실이다: `MC-1` 이 요구하는 **사람이 읽는 산출물**
    형식을 spec 이 열거하지 않는다. 이것은 `status-human.md` 7단계(spec 개정
    판단)로 올릴 사항이며, 조항이 생기면 여기에 마커를 단다.
    """
    names = client.get("/reports/golden").json()
    assert names, "리포트를 낼 수 있는 시나리오가 하나도 없다"

    response = client.get(f"/reports/golden/{names[0]}")
    assert response.status_code == 200
    assert "markdown" in response.headers["content-type"]

    body = response.text
    for heading in (
        "## 2. 평가 개요",
        "## 3. 평가 방법",
        "### 5.1 불확실 인자",
        "## 붙임 5. 재현 절차",
    ):
        assert heading in body, f"리포트에 «{heading}» 절이 없다"


@pytest.mark.req("FR-1003-AC3")
def test_json_export_is_parseable_by_a_standard_parser(client: TestClient) -> None:
    """`FR-1003-AC3` 재현용 JSON. **`Infinity` 를 내지 않는다.**

    파이썬은 `float('inf')` 를 `Infinity` 로 직렬화하지만 그것은 JSON 표준이
    아니다 — 받는 쪽이 파이썬이 아니면 파싱에서 멈추고, 그 실패는 「미회수인
    시나리오에서만」 나타나 재현이 어렵다.
    """
    response = client.get(
        "/reports/golden/scenario_unsubsidized", params={"fmt": "json"}
    )
    assert response.status_code == 200
    parsed = json.loads(response.text)  # strict 파서 — Infinity 면 여기서 멈춘다
    assert "Infinity" not in response.text
    assert parsed["influences"], "JSON 에 영향도 순위가 없다"
    assert parsed["assumptions"], "JSON 에 가정 부록이 없다"
    assert parsed["manifest_hash"]


def test_unknown_scenario_name_is_refused(client: TestClient) -> None:
    """목록에 없는 이름은 404 다 — 이름을 경로로 그대로 잇지 않는다.

    ⚠ **`req()` 마커를 달지 않았다.** 이 검사가 지키는 것은 `SC` 표(보안)인데
    그 표의 행은 수용기준 파서가 읽는 형식이 아니라 `req("SC-2")` 를 달면
    `gen_traceability` 가 **실재하지 않는 인용**으로 잡는다. 「SC 표를 수용기준
    으로 승격할 것인가」는 `status-human.md` 7단계의 판단 대기 항목이며,
    승격되면 여기에 마커를 단다.
    """
    assert client.get("/reports/golden/nope").status_code == 404
    assert client.get("/reports/golden/..%2f..%2fdocs").status_code == 404
