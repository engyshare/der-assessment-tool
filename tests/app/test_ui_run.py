"""화면에서 **갈래를 고르고 실행할 수 있는가** — `FR-705-AC2` · `NFR-303-M1`.

엔진은 갈래 셋을 이미 다 돌았다. 못 하던 것은 **사람이 고르는 것**이고, 이
파일이 재는 것은 그 구멍이다 — `GET /ui/run` 이 실제로 돌고, 고른 것이
**결과를 실제로 바꾸는가**.

## 하나도 `web.render` 를 직접 부르지 않는다

전부 `TestClient(create_app())` 를 지난다. 문맥 함수를 직접 부르면 「배포
코드가 부르지 않는 함수가 초록불을 만든다」를 그대로 다시 밟는다 —
`tests/app/test_ui_router.py` 머리말이 그 형태를 적어 두었다.

## 기댓값을 소스에 박지 않는다

갈래 목록은 `BaselineArrangement` 에서, 수는 **다른 경로의 응답**
(`GET /reports/golden/...?fmt=json`)에서 가져와 대조한다. 박으면 갈래가
늘거나 대장 판이 오르는 날 이 검사가 조용히 낡는다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.ui_run import scenario_fields
from core.assumption.scenario_overrides import ASSUMPTION_OVERRIDES_FIELD
from core.cba.baseline import BaselineArrangement, get_baseline_branch
from core.contracts.validation import ValidationError
from core.report.case_report import REC_PRICE_LEDGER_KEY, build_case_report

#: 결과 화면이 **서식 이전의 날값**으로 함께 싣는 결론 축. 서식을 입힌 문면만
#: 보면 이 검사가 서식 문자열을 다시 짜 맞추게 되고, 그때 재는 것은 수가
#: 아니라 표기가 된다.
_NPV_ATTRIBUTE = re.compile(r'data-npv="([^"]+)"')

#: 대조에 쓰는 골든 시나리오. 셋 중 무엇이든 되지만 **`/reports` 와 같은 것**을
#: 써야 두 응답의 수를 맞댈 수 있다.
_SCENARIO = "scenario_unsubsidized"

#: 저장소 뿌리 — `tests/app/test_ui_run.py` 에서 두 단계 위.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / f"{_SCENARIO}.yaml"
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"


def _golden_npv() -> float:
    """골든 회귀가 대조하는 **바로 그 수**를 그 파일에서 읽는다.

    ⚠ **수를 소스에 박지 않는다.** `tests/golden/test_regression_scenarios.py`
    가 읽는 자리와 **같은 자리**(`expected_values.npv_won`)를 읽는다 — 자기
    사본을 두면 어느 날 둘이 갈리고, 그때 무엇이 정본인지 산출물에서 알 수 없다.
    """
    case = yaml.safe_load(_GOLDEN.read_text(encoding="utf-8"))
    return float(case["expected_values"]["npv_won"])


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _npv_on_screen(body: str) -> float:
    match = _NPV_ATTRIBUTE.search(body)
    assert match is not None, "결과 화면이 결론 축을 날값으로 싣지 않았다"
    return float(match.group(1))


def _needs_declaration(arrangement: BaselineArrangement) -> bool:
    """이 갈래가 **계측 전제 선언을 요구하는가** — 저장소에 물어서 안다.

    ⚠ 「ⓒ 만 그렇다」를 여기 적지 않는다. 요구하는 갈래가 둘이 되는 날 그
    문장만 참인 채로 남고, 그때 이 파일은 새 갈래를 전제 없이 눌러 보며
    「고를 수 없다」로 빨간불이 된다 — 원인은 검사가 낡은 것이다.
    """
    try:
        get_baseline_branch(arrangement)
    except ValidationError:
        return True
    return False


def _params(arrangement: BaselineArrangement | None) -> dict[str, str | bool]:
    """질의 파라미터 한 벌 — 전제는 **요구하는 갈래에만** 실는다."""
    params: dict[str, str | bool] = {"scenario": _SCENARIO}
    if arrangement is None:
        return params
    params["arrangement"] = arrangement.value
    if _needs_declaration(arrangement):
        params["ownership_or_operation_transferred"] = True
        params["metering_separated"] = True
    return params


def test_the_number_on_the_screen_is_the_number_in_the_report(
    client: TestClient,
) -> None:
    """★★★ **화면의 수가 리포트의 수와 같다.**

    ⚠ **`req()` 마커를 달지 않았다.** 이것은 조항 검증이 아니라 **정합
    검사**다 — 두 출구가 같은 실행 경로를 지나는데 다른 수를 인쇄하면 그것이
    새 결함이라는 것뿐이고, 대응하는 수용기준은 없다. 없는 조항을 지어 붙이면
    매핑표가 거짓 진술을 싣는다.

    ⚠ **수를 소스에 박지 않는다.** 두 응답을 서로 대조한다 — 박으면 대장 판이
    오르는 날 「화면이 틀렸다」가 아니라 「검사가 낡았다」로 빨간불이 된다.
    """
    screen = client.get("/ui/run", params={"scenario": _SCENARIO})
    assert screen.status_code == 200, screen.text
    assert "text/html" in screen.headers["content-type"]

    report = client.get(f"/reports/golden/{_SCENARIO}", params={"fmt": "json"})
    assert report.status_code == 200, report.text

    assert _npv_on_screen(screen.text) == json.loads(report.text)["metrics"]["npv"]


@pytest.mark.req("FR-705-AC2")
def test_every_arrangement_can_be_chosen_from_the_screen(client: TestClient) -> None:
    """갈래 **셋을 다** 고를 수 있고, 결과가 어느 갈래로 돌았는지 적는다.

    ⚠ 목록을 소스에 박지 않고 `BaselineArrangement` 를 **열거해서** 돈다.
    박으면 여덟 번째 갈래가 서는 날 이 검사가 셋만 눌러 보고 초록불이 된다.

    갈래 문면이 화면에 없으면 **고르게 해 놓고 결과가 그것을 안 적는** 것이며,
    그 상태에서는 어느 기준선 대비 증분인지 확인할 방법이 없다.
    """
    for arrangement in BaselineArrangement:
        response = client.get("/ui/run", params=_params(arrangement))

        assert response.status_code == 200, (
            f"「{arrangement.value}」 를 고를 수 없다: {response.text}"
        )
        assert f'data-arrangement="{arrangement.value}"' in response.text, (
            f"결과 화면이 「{arrangement.value}」 로 돌았다고 적지 않았다"
        )


@pytest.mark.req("FR-705-AC2")
@pytest.mark.req("NFR-303-M1")
def test_an_arrangement_that_needs_a_declaration_is_refused_without_one(
    client: TestClient,
) -> None:
    """★ 전제를 요구하는 갈래를 **전제 없이** 고르면 400 이고 3요소가 다 있다.

    거부가 이 화면의 **정상 동작**이다 — 소유·운영권 인계와 구분 계측은
    자료가 아니라 사업 설계이며 저장소가 채울 수 없다(가정하지 말고 물어라).

    ⚠ 3요소를 **셋 다** 본다. 하나라도 빠지면 사람에게 남는 선택은 값을
    하나씩 바꿔 보는 것이고, 그때 가장 쉬운 선택이 「그냥 참으로 두기」다.
    """
    refused = [item for item in BaselineArrangement if _needs_declaration(item)]
    assert refused, "전제를 요구하는 갈래가 없다 — 잴 것이 없다"

    for arrangement in refused:
        response = client.get(
            "/ui/run", params={"scenario": _SCENARIO, "arrangement": arrangement.value}
        )

        assert response.status_code == 400, (
            f"「{arrangement.value}」 가 전제 없이 {response.status_code} 로 돌았다"
        )
        for element in ("필드:", "사유:", "조치:"):
            assert element in response.text, (
                f"거부 화면에 {element} 가 없다 — NFR-303 의 3요소 중 하나가 빠졌다"
            )


@pytest.mark.req("FR-705-AC2")
def test_an_arrangement_that_needs_a_declaration_runs_once_it_is_given(
    client: TestClient,
) -> None:
    """★ 전제 둘을 화면에서 적으면 그 갈래가 **돈다.**

    거부만 재고 여기를 안 재면 「영영 고를 수 없는 갈래」와 「전제를 요구하는
    갈래」가 구별되지 않는다.
    """
    for arrangement in BaselineArrangement:
        if not _needs_declaration(arrangement):
            continue
        response = client.get("/ui/run", params=_params(arrangement))

        assert response.status_code == 200, response.text
        assert f'data-arrangement="{arrangement.value}"' in response.text


@pytest.mark.req("FR-705-AC2")
def test_choosing_an_arrangement_actually_moves_the_number(client: TestClient) -> None:
    """★ 고른 갈래가 **결과를 실제로 바꾼다.**

    ⚠⚠ 같은 수가 나오면 그것은 *「골랐는데 안 먹었다」* 이고 **그 상태는 200
    초록불로 조용하다** — 화면은 고른 갈래를 그대로 인쇄하고 수만 옛것이다.
    이 검사가 그것을 몬다.

    ⚠ 어느 두 갈래를 맞대는지도 **열거에서** 얻는다. 전제를 요구하지 않는
    갈래 둘을 앞에서부터 잡는다 — 이름을 박으면 갈래표가 바뀌는 날 이 검사가
    없는 갈래를 부른다.
    """
    plain = [item for item in BaselineArrangement if not _needs_declaration(item)]
    assert len(plain) >= 2, "맞댈 갈래가 둘이 안 된다"

    first, second = plain[0], plain[1]
    one = client.get("/ui/run", params=_params(first))
    other = client.get("/ui/run", params=_params(second))
    assert one.status_code == 200, one.text
    assert other.status_code == 200, other.text

    assert _npv_on_screen(one.text) != _npv_on_screen(other.text), (
        f"「{first.value}」 와 「{second.value}」 가 같은 수를 냈다 — "
        "갈래를 골랐는데 실행에 닿지 않았을 수 있다"
    )


@pytest.mark.req("FR-705-AC2")
def test_the_dashboard_lets_a_person_pick_an_arrangement(client: TestClient) -> None:
    """대시보드에 **갈래 전건**과 실행 폼이 있다.

    라우트만 있고 화면에 폼이 없으면 「선택할 수 있다」는 URL 을 손으로 짓는
    사람에게만 참이다 — 조항이 말하는 사람은 사업 설계자다.
    """
    response = client.get("/")

    assert response.status_code == 200, response.text
    body = response.text
    assert 'action="/ui/run"' in body, "대시보드에 실행 폼이 없다"
    missing = [item.value for item in BaselineArrangement if item.value not in body]
    assert not missing, f"대시보드에서 고를 수 없는 갈래: {missing}"


def test_an_unknown_scenario_name_is_a_404(client: TestClient) -> None:
    """목록 밖 이름은 **없는 것**이다.

    ⚠ **`req()` 마커를 달지 않았다** — 시나리오 화이트리스트에 대응하는
    수용기준이 spec 에 없다(`tests/app/test_ui_router.py` 의 정적 파일 검사와
    같은 사유다).
    """
    response = client.get("/ui/run", params={"scenario": "scenario_없는것"})

    assert response.status_code == 404, response.text


# ── 전제 오버라이드 통로 — 기본값은 안 움직이고, 실으면 움직인다 ────────


def test_the_default_run_does_not_move_the_conclusion_axis(client: TestClient) -> None:
    """★★★ **기본값 실행의 결론축이 움직이지 않는다.**

    전제 오버라이드 통로가 생겼다고 해서 아무것도 안 적은 실행이 달라지면
    그것은 개선이 아니라 **새 결함**이다. 필드가 없으면
    `apply_scenario_overrides` 가 `provider` 를 **그대로**(같은 객체로)
    돌려주므로 기본값 실행은 같은 경로를 돈다 —
    `tests/assumption/test_scenario_overrides.py` 가 그 동일성을 잰다.

    ⚠ **수를 소스에 박지 않는다.** 골든 회귀가 쓰는 같은 원천
    (`fixtures/golden/scenario_unsubsidized.yaml` 의 `expected_values.npv_won`)
    과 대조한다.

    ⚠ **`req()` 마커를 달지 않았다** — 조항 검증이 아니라 **회귀 불변** 단언이다
    (`test_the_number_on_the_screen_is_the_number_in_the_report` 와 같은 사유).
    """
    screen = client.get("/ui/run", params={"scenario": _SCENARIO})
    assert screen.status_code == 200, screen.text

    assert _npv_on_screen(screen.text) == _golden_npv()


@pytest.mark.req("FR-602-AC1", "FR-602-AC2")
def test_a_scenario_that_carries_overrides_runs_on_the_changed_values(
    tmp_path: Path,
) -> None:
    """★★ 오버라이드를 실은 시나리오는 **다른 수**를 내고 붙임이 그것을 적는다.

    ⚠⚠ 수만 보면 부족하다. 수가 움직였는데 `overrides` 가 비어 있으면 검토자는
    **왜 다른지 알 수 없고**, 그 상태는 「기준 전제 그대로 돌렸다」와 산출물에서
    구별되지 않는다 (`CaseReport.overrides` 주석이 그 사유를 적는다).

    ⚠ **화면을 지나지 않는다.** 결과 화면에 오버라이드 폼을 다는 것은 뒤 축
    (R63/S2)이고 이 검사가 재는 것은 **통로가 실행에 닿는가**다. 그래서
    `scenario_fields()` 가 짓는 매핑에 필드를 얹어 `build_case_report()` 로
    바로 돌린다 — `app/services/ui_run.py::run_ui_case` 가 하는 것과 같은 절차다.

    ⚠ **골든 픽스처를 고치지 않는다** — 읽기만 하고 쓰는 곳은 `tmp_path` 다.
    """
    fields = scenario_fields(_SCENARIO)
    fields[ASSUMPTION_OVERRIDES_FIELD] = [
        {
            "key": REC_PRICE_LEDGER_KEY,
            "value": 300.0,
            "reason": "검사 — 대장(70원/kWh)과 다른 값을 시나리오가 적는다",
        }
    ]
    path = tmp_path / f"{_SCENARIO}.yaml"
    path.write_text(
        yaml.safe_dump(fields, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    report = build_case_report(path, assumptions_path=_ASSUMPTIONS)

    assert float(report.metrics["npv"]) != _golden_npv(), (
        "오버라이드를 실었는데 결론축이 그대로다 — 통로가 실행에 닿지 않았다"
    )
    assert report.overrides, "붙임의 「기준 전제 대비 변경 항목」이 비어 있다"
    changed = {row.key: row for row in report.overrides}
    assert changed[REC_PRICE_LEDGER_KEY].base_value == 70
    assert changed[REC_PRICE_LEDGER_KEY].override_value == 300.0
    assert changed[REC_PRICE_LEDGER_KEY].reason is not None
