"""화면에서 **시나리오와 설정을 저장·불러오기·적용할 수 있는가** — `FR-902` · `FR-602`.

저장 계층(`ScenarioStore`·`JsonFileScenarioStore`)과 오버라이드 통로
(`core/assumption/scenario_overrides.py`)는 앞 축이 이미 세웠다. 못 하던 것은
**사람이 화면에서 그것을 쓰는 것**이고, 이 파일이 재는 것은 그 구멍이다.

## 하나도 `web.render_scenarios` 를 직접 부르지 않는다

전부 `TestClient(create_app())` 를 지난다. 문맥 함수를 직접 부르면 「배포 코드가
부르지 않는 함수가 초록불을 만든다」를 그대로 다시 밟는다 —
`tests/app/test_ui_run.py` 머리말이 그 형태를 적어 두었다.

## 앱 내부 자료구조를 훑지 않는다

CI 는 Python 3.11 · FastAPI 0.141 이고 로컬은 3.13 · 0.136 이다. `app.routes` 같은
내부 구조는 판이 바뀌면 모양이 달라지므로, 보는 것은 **응답**과
**`openapi()["paths"]`** 둘뿐이다.

## 기댓값을 소스에 박지 않는다

대장 항목 수는 `AssumptionSet.load_from_yaml` 로 세고, 결론축은 골든 회귀가 읽는
같은 자리(`expected_values.npv_won`)에서 읽는다. 박으면 대장 판이 오르는 날
이 검사가 조용히 낡는다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import create_app
from app.routers.ui_scenarios import DEMO_OWNER_ID
from core.assumption.provider import AssumptionSet
from core.report.case_report import REC_PRICE_LEDGER_KEY

#: 결과 화면이 **서식 이전의 날값**으로 함께 싣는 결론 축 — `run_result.html` 의
#: `data-npv` 다. 서식을 입힌 문면만 보면 이 검사가 서식 문자열을 다시 짜 맞추게
#: 되고, 그때 재는 것은 수가 아니라 표기다.
_NPV_ATTRIBUTE = re.compile(r'data-npv="([^"]+)"')

#: 설정 화면이 「이 설정으로 돌린 결과」에 싣는 오버라이드 건수.
_OVERRIDE_COUNT = re.compile(r'data-override-count="([^"]+)"')

#: 방금 저장한 레코드의 번호 — 저장은 **303** 으로 되돌리고 그 주소에 번호가 있다.
_APPLIED_ID = re.compile(r"applied=(\d+)")

_SCENARIO = "scenario_unsubsidized"

#: 저장소 뿌리 — `tests/app/test_ui_scenarios.py` 에서 두 단계 위.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / f"{_SCENARIO}.yaml"
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"

#: 대장에 **없는 것이 확실한** 키 하나 — 거부를 재는 자리다. 대장에 이런 이름의
#: 항목이 서면 이 검사가 「화면이 거부하지 않았다」로 빨간불이 되는데, 그때
#: 원인은 화면이 아니라 이 이름이다. 점을 낀 한국어라 대장 관례
#: (`<도메인>.<항목>` ASCII)와 충돌하지 않는다.
_UNKNOWN_KEY = "없는.전제.키"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _ledger() -> AssumptionSet:
    return AssumptionSet.load_from_yaml(str(_ASSUMPTIONS))


def _golden_npv() -> float:
    """골든 회귀가 대조하는 **바로 그 수**를 그 파일에서 읽는다.

    ⚠ **수를 소스에 박지 않는다.** `tests/golden/test_regression_scenarios.py`
    가 읽는 자리와 **같은 자리**(`expected_values.npv_won`)를 읽는다.
    """
    case = yaml.safe_load(_GOLDEN.read_text(encoding="utf-8"))
    return float(case["expected_values"]["npv_won"])


def _npv_on_screen(body: str) -> float:
    match = _NPV_ATTRIBUTE.search(body)
    assert match is not None, "화면이 결론 축을 날값으로 싣지 않았다"
    return float(match.group(1))


def _a_ledger_key() -> str:
    """고쳐 볼 대장 항목 하나 — **실행 경로가 실제로 읽는** 것이어야 한다.

    ⚠ 키를 소스에 박지 않고 `core.report.case_report.REC_PRICE_LEDGER_KEY` 를
    쓴다. 저장소가 그 이름을 상수로 갖고 있고 `tests/app/test_ui_run.py` 가
    **같은 사유로 같은 것**을 쓴다 — 오버라이드가 결론축을 움직이는지 재려면
    그 계산이 실제로 읽는 항목이어야 한다.

    ★ 「대장에 있는 아무 수치 항목」으로는 부족하다는 것을 이 라운드가 실물로
    밟았다: `capex.pv.rooftop` 을 두 배로 고쳐도 이 골든 케이스의 `npv` 는
    **한 원도 움직이지 않았다**(붙임의 「변경 항목」에는 떴다). 그 케이스의 PV
    설비비가 그 대장 항목에서 오지 않기 때문이며, 붙임(`CaseReport.assumptions`)
    이 대장 **전건**을 싣기 때문에 「실렸다」와 「읽혔다」의 차이가 산출물에
    나타나지 않는다. 그 관찰은 `.orch/R63/result_S2.md` §7 이 갖는다.
    """
    assert REC_PRICE_LEDGER_KEY in _ledger().items(), (
        f"{REC_PRICE_LEDGER_KEY} 가 대장에서 사라졌다 — 이 검사가 낡았다"
    )
    return REC_PRICE_LEDGER_KEY


def _changed_text(base: object) -> str:
    """대장 값과 **다른 값**을 그 항목의 형식 그대로 적는다.

    ⚠ 정수 항목에 `"3200001.0"` 을 넣지 않는다 — 폼이 보낸 글자를 카탈로그가
    말하는 형으로 되돌리는 것이 화면의 일이고(`app/routers/ui_forms.py::
    _value_of` 와 같은 규약), 정수 칸에 실수 문면을 넣으면 이 검사가 재는 것이
    「오버라이드가 실렸는가」가 아니라 「형 변환이 관대한가」가 된다.
    """
    assert isinstance(base, (int, float)) and not isinstance(base, bool), base
    return str(base * 2 + 1)


def _saved_scenario(
    client: TestClient,
    *,
    name: str,
    description: str = "",
    tags: str = "",
    settings_id: int = 0,
    arrangement: str = "",
    scenario_id: int = 0,
) -> int:
    """화면의 저장 폼을 **그대로 눌러** 한 건 저장하고 번호를 돌려준다."""
    response = client.post(
        "/ui/scenarios",
        data={
            "scenario_id": str(scenario_id),
            "name": name,
            "description": description,
            "tags": tags,
            "scenario": _SCENARIO,
            "arrangement": arrangement,
            "settings_id": str(settings_id),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    match = re.search(r"saved=(\d+)", response.headers["location"])
    assert match is not None, response.headers["location"]
    return int(match.group(1))


def _saved_settings(client: TestClient, *, name: str, key: str, value: str) -> int:
    """설정 폼을 눌러 **오버라이드 한 줄**을 담은 설정을 저장하고 번호를 돌려준다."""
    response = client.post(
        "/ui/settings",
        data={"name": name, "description": "", f"val-{key}": value},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    match = _APPLIED_ID.search(response.headers["location"])
    assert match is not None, response.headers["location"]
    return int(match.group(1))


# ── 시나리오 화면 — 목록·저장·불러오기·버전·삭제 (`FR-902`) ────────────────


@pytest.mark.req("FR-902-AC1")
def test_a_saved_scenario_appears_on_the_list_screen(client: TestClient) -> None:
    """저장한 이름이 **목록 본문에 있다** — 저장이 화면에 닿는가."""
    name = "목록에 뜨는지 보는 시나리오"
    scenario_id = _saved_scenario(client, name=name)

    screen = client.get("/ui/scenarios")

    assert screen.status_code == 200, screen.text
    assert "text/html" in screen.headers["content-type"]
    assert name in screen.text, "저장한 시나리오가 목록에 없다"
    assert f'data-scenario-id="{scenario_id}"' in screen.text


@pytest.mark.req("FR-902-AC1")
def test_the_list_carries_all_four_metadata_fields(client: TestClient) -> None:
    """★ `FR-902-AC1` 의 넷이 **전건** 본문에 있다.

    ⚠ 「하나 이상」으로 두지 않는다 — 그러면 이름 하나만 그려도 초록불이다.
    최종수정일시는 사람이 읽는 칸과 별개로 `data-updated-at` 에 날값으로 싣는다.
    """
    name = "부기 넷을 보는 시나리오"
    description = "설명 칸이 화면에 그려지는지 본다"
    tags = "제주,vpp"
    scenario_id = _saved_scenario(
        client, name=name, description=description, tags=tags
    )

    body = client.get("/ui/scenarios").text

    row = re.search(
        rf'<tr[^>]*data-scenario-id="{scenario_id}".*?</tr>', body, re.DOTALL
    )
    assert row is not None, "목록에 그 시나리오의 행이 없다"
    drawn = row.group(0)
    missing = [
        label
        for label, text in (
            ("이름", name),
            ("설명", description),
            ("태그", "제주"),
            ("태그", "vpp"),
        )
        if text not in drawn
    ]
    assert not missing, f"목록 행이 빠뜨린 것: {missing}"
    assert "data-updated-at=" in drawn, "최종수정일시가 행에 없다"


@pytest.mark.req("FR-902-AC1")
def test_loading_a_saved_scenario_fills_the_run_screen(client: TestClient) -> None:
    """★★ **왕복** — 저장 → 목록 → 불러오기 → 실행 화면이 그 값으로 채워진다.

    갈래를 고르고 저장했으면, 불러온 실행 화면이 **그 갈래로 돌았다**고 적어야
    한다. 안 적으면 「저장됐다」와 「저장된 값이 실행에 안 실렸다」가 화면에서
    구별되지 않는다.
    """
    arrangements = client.get("/ui/scenarios").text
    choice = re.search(r'<option value="([^"]+)"[^>]*data-arrangement-choice', arrangements)
    assert choice is not None, "시나리오 화면이 고를 갈래를 그리지 않았다"

    scenario_id = _saved_scenario(
        client, name="왕복 시나리오", arrangement=choice.group(1)
    )

    listing = client.get("/ui/scenarios").text
    assert f'href="/ui/scenarios/{scenario_id}/run"' in listing, (
        "목록에 불러오기 통로가 없다"
    )

    loaded = client.get(f"/ui/scenarios/{scenario_id}/run")

    assert loaded.status_code == 200, loaded.text
    assert f'data-arrangement="{choice.group(1)}"' in loaded.text, (
        "불러온 실행이 저장한 갈래로 돌지 않았다"
    )


@pytest.mark.req("FR-902-AC2")
def test_a_previous_version_can_be_restored_from_the_screen(
    client: TestClient,
) -> None:
    """버전 이력이 화면에 있고, 이전 버전으로 **화면에서** 되돌릴 수 있다."""
    scenario_id = _saved_scenario(client, name="1판", description="처음")
    _saved_scenario(
        client, name="2판", description="고친 뒤", scenario_id=scenario_id
    )

    versions = client.get("/ui/scenarios", params={"versions": scenario_id})
    assert versions.status_code == 200, versions.text
    assert 'data-version="1"' in versions.text, "버전 1 이 이력에 없다"
    assert 'data-version="2"' in versions.text, "버전 2 가 이력에 없다"

    restored = client.post(
        f"/ui/scenarios/{scenario_id}/restore_version",
        data={"version": "1"},
        follow_redirects=False,
    )
    assert restored.status_code == 303, restored.text

    body = client.get("/ui/scenarios").text
    row = re.search(
        rf'<tr[^>]*data-scenario-id="{scenario_id}".*?</tr>', body, re.DOTALL
    )
    assert row is not None
    assert "1판" in row.group(0), "복원했는데 목록이 옛 이름을 그리지 않는다"


@pytest.mark.req("FR-902-AC3")
def test_a_deleted_scenario_leaves_the_list_and_can_be_restored(
    client: TestClient,
) -> None:
    """소프트 삭제 뒤 **목록에서 사라지고**, 되돌릴 수 있다는 것이 화면에 보인다.

    ⚠ 「사라졌다」를 이름의 부재로 재지 않는다 — 삭제 알림이 이름을 싣기 때문이다.
    목록 행의 식별자(`data-scenario-id`)가 사라졌는가로 잰다.
    """
    scenario_id = _saved_scenario(client, name="지울 시나리오")

    deleted = client.post(
        f"/ui/scenarios/{scenario_id}/delete", follow_redirects=False
    )
    assert deleted.status_code == 303, deleted.text

    after = client.get("/ui/scenarios", params={"deleted": scenario_id})
    assert after.status_code == 200, after.text
    assert f'data-scenario-id="{scenario_id}"' not in after.text, (
        "삭제했는데 목록에 그대로 있다"
    )
    assert f'action="/ui/scenarios/{scenario_id}/restore"' in after.text, (
        "되돌릴 수 있다는 것이 화면에 없다"
    )
    assert "30일" in after.text, "보관 기간이 화면에 없다"

    restored = client.post(
        f"/ui/scenarios/{scenario_id}/restore", follow_redirects=False
    )
    assert restored.status_code == 303, restored.text
    assert f'data-scenario-id="{scenario_id}"' in client.get("/ui/scenarios").text


# ── 설정 화면 — 대장 전건·수정·저장·적용 (`FR-602`) ────────────────────────


def test_the_settings_screen_draws_every_ledger_item(client: TestClient) -> None:
    """설정 화면이 **대장 항목 전건**을 그린다.

    ⚠ 수를 박지 않고 `AssumptionSet.load_from_yaml` 로 세어 대조한다. 줄여
    그리면 화면이 「전체」라고 적은 채 일부만 보여 주고, 그 상태는 사용자가
    없는 칸을 찾을 때까지 드러나지 않는다.

    ⚠ **`req()` 마커를 달지 않았다** — 「대장 항목 전건을 화면에 그린다」에
    대응하는 수용기준이 spec 에 없다. 없는 조항을 지어 붙이면 매핑표가 거짓
    진술을 싣는다 (`tests/app/test_ui_run.py` 가 같은 사유를 적는다).
    """
    screen = client.get("/ui/settings")
    assert screen.status_code == 200, screen.text

    keys = tuple(_ledger().items())
    missing = [key for key in keys if f'data-ledger-key="{key}"' not in screen.text]

    assert not missing, f"설정 화면이 그리지 않은 대장 항목 {len(missing)}건: {missing}"


def test_the_settings_screen_defaults_to_the_same_scenario_as_the_run_screen(
    client: TestClient,
) -> None:
    """★ 두 화면의 **기본 시나리오가 같다.**

    갈리면 「오버라이드 안 건 실행의 결론축」이 두 화면에서 다른 수가 되고, 그때
    어느 쪽이 회귀인지 산출물에서 알 수 없다. `/ui/run` 의 기본값은 그 라우트의
    질의 기본값이며 **앱 내부 구조가 아니라 `openapi()` 로 읽는다**.
    """
    paths = create_app().openapi()["paths"]

    def _default(path: str) -> str:
        parameters = paths[path]["get"]["parameters"]
        found = [p for p in parameters if p["name"] == "scenario"]
        assert found, f"{path} 에 scenario 질의가 없다"
        return str(found[0]["schema"]["default"])

    assert _default("/ui/settings") == _default("/ui/run")


def test_a_run_without_overrides_does_not_move_the_conclusion_axis(
    client: TestClient,
) -> None:
    """★★★ **오버라이드를 하나도 안 건 실행의 결론축이 움직이지 않는다.**

    화면에 오버라이드 폼이 생겼다고 해서 아무것도 안 고친 실행이 달라지면 그것은
    개선이 아니라 **새 결함**이다.

    ⚠ **수를 소스에 박지 않는다** — 골든 회귀가 읽는 같은 자리와 대조한다.
    ⚠ **`req()` 마커를 달지 않았다** — 조항 검증이 아니라 **회귀 불변** 단언이다.
    """
    scenario_id = _saved_scenario(client, name="아무것도 안 고친 시나리오")

    screen = client.get(f"/ui/scenarios/{scenario_id}/run")

    assert screen.status_code == 200, screen.text
    assert _npv_on_screen(screen.text) == _golden_npv()


@pytest.mark.req("FR-602-AC1", "FR-602-AC2")
def test_a_changed_value_shows_up_in_the_report_overrides(client: TestClient) -> None:
    """★★ 값을 고쳐 제출하면 **그 실행의 리포트 `overrides` 가 비어 있지 않다.**

    ⚠⚠ 수만 보면 부족하다. 수가 움직였는데 `overrides` 가 비어 있으면 검토자는
    **왜 다른지 알 수 없고**, 그 상태는 「기준 전제 그대로 돌렸다」와 산출물에서
    구별되지 않는다. 화면이 그리는 것은 `CaseReport.overrides` 그것이다.
    """
    key = _a_ledger_key()
    base = _ledger().items()[key].value
    settings_id = _saved_settings(
        client, name="값을 고친 설정", key=key, value=_changed_text(base)
    )

    applied = client.get("/ui/settings", params={"applied": settings_id})

    assert applied.status_code == 200, applied.text
    count = _OVERRIDE_COUNT.search(applied.text)
    assert count is not None, "설정 화면이 오버라이드 건수를 싣지 않았다"
    assert int(count.group(1)) >= 1, "값을 고쳤는데 리포트의 변경 항목이 비어 있다"
    assert f'data-override-key="{key}"' in applied.text
    assert _npv_on_screen(applied.text) != _golden_npv(), (
        "오버라이드를 실었는데 결론축이 그대로다 — 통로가 실행에 닿지 않았다"
    )


@pytest.mark.req("FR-602-AC3")
def test_the_settings_screen_offers_a_reason_box_for_each_override(
    client: TestClient,
) -> None:
    """오버라이드마다 **사유를 적을 칸**이 있다 — 권장 필드이므로 비워도 통과다."""
    key = _a_ledger_key()

    screen = client.get("/ui/settings")

    assert f'name="reason-{key}"' in screen.text, "사유 칸이 없다"

    settings_id = _saved_settings(
        client, name="사유 없이 저장한 설정", key=key, value="1"
    )
    assert client.get("/ui/settings", params={"applied": settings_id}).status_code == 200


# ── 거부 — 삼키지 않고, 사람이 읽을 문면으로, 값을 잃지 않고 ────────────────


@pytest.mark.req("NFR-303-M1")
def test_a_key_outside_the_ledger_is_refused_in_words_people_read(
    client: TestClient,
) -> None:
    """대장에 없는 키는 **거부되고 그 거부가 화면에 글자로 뜬다** — 500 이 아니다.

    ⚠ 화면이 그 거부를 삼키면 사용자가 고친 값은 계산에도 안 먹고 붙임에도 안
    뜬다 — `core/assumption/scenario_overrides.py` 머리말이 그 상태를 「가장
    나쁘다」로 적었다.
    """
    response = client.post(
        "/ui/settings",
        data={"name": "대장 밖 키를 넣은 설정", f"val-{_UNKNOWN_KEY}": "123"},
        follow_redirects=False,
    )

    assert response.status_code == 400, response.text
    assert "text/html" in response.headers["content-type"]
    body = response.text
    for part in ("필드", "사유", "조치"):
        assert part in body, f"거부 화면에 {part} 가 없다 (NFR-303 3요소)"
    assert _UNKNOWN_KEY in body, "무엇이 거부됐는지 화면이 적지 않는다"


@pytest.mark.req("NFR-303-M1")
def test_a_refused_submission_keeps_what_the_person_typed(client: TestClient) -> None:
    """★ **거부돼도 사람이 넣은 값이 폼에 남아 있다.**

    착수 목록 44번 ⓑ 가 적은 것이 이 자리다 — 거부될 때마다 고치던 값을 잃으면
    사람은 「고칠 수 없다」로 읽는다.
    """
    key = _a_ledger_key()
    typed = "424242"
    name = "값을 잃지 않는지 보는 설정"

    response = client.post(
        "/ui/settings",
        data={
            "name": name,
            f"val-{key}": typed,
            f"val-{_UNKNOWN_KEY}": "123",
            f"reason-{key}": "이 사유도 남아야 한다",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400, response.text
    assert typed in response.text, "거부되면서 사람이 넣은 값이 사라졌다"
    assert "이 사유도 남아야 한다" in response.text, "사유가 사라졌다"
    assert name in response.text, "설정 이름이 사라졌다"


def _malformed(kind: str, key: str) -> str:
    """앞 축이 거부하게 만든 **넷**을 각각 담은 정의 문면."""
    rows = {
        # ⓐ 대장에 없는 키
        "unknown_key": f'[{{"key": "{_UNKNOWN_KEY}", "value": 1}}]',
        # ⓑ 모양이 틀린 입력 — 값이 스칼라가 아니다
        "not_a_scalar": f'[{{"key": "{key}", "value": [1, 2]}}]',
        # ⓒ 모르는 필드 — `reason` 의 오타
        "unknown_field": f'[{{"key": "{key}", "value": 1, "resaon": "오타"}}]',
        # ⓓ 같은 키 중복 — 뒤가 이기고 앞 줄은 흔적 없이 사라진다
        "duplicate_key": f'[{{"key": "{key}", "value": 1}}, {{"key": "{key}", "value": 2}}]',
    }
    return f'{{"kind": "settings", "assumption_overrides": {rows[kind]}}}'


@pytest.mark.req("NFR-303-M1")
@pytest.mark.parametrize(
    ("kind", "must_say"),
    [
        ("unknown_key", "대장에 없는 키"),
        ("not_a_scalar", "스칼라가 아닙니다"),
        ("unknown_field", "resaon"),
        ("duplicate_key", "두 번 적었습니다"),
    ],
)
def test_every_refusal_reaches_the_screen_as_words(
    client: TestClient, kind: str, must_say: str
) -> None:
    """★★ 앞 축이 거부하게 만든 **넷 다** 화면에 글자로 나온다 — 500 이 아니다.

    ⓐ 대장에 없는 키 · ⓑ 모양이 틀린 입력 · ⓒ 모르는 필드(`resaon` 오타) ·
    ⓓ 같은 키 중복. 설정 폼에서 날 수 있는 것은 ⓐⓑ 뿐이지만(칸이 대장 키마다
    하나다), **JSON API 로 저장된 정의**는 넷 다 그 모양으로 들어올 수 있다.
    그때 화면이 500 으로 떨어지면 결함이며, 사용자가 받는 것은 「무엇을 하라」가
    없는 영어 한 줄이다.

    ⚠ 거부 문면을 이 검사가 새로 짓지 않는다 — `resolve_assumption_overrides` 가
    적은 그 문장의 **조각**을 찾는다. 새로 지으면 그 함수가 문면을 고치는 날
    화면은 멀쩡한데 이 검사만 빨간불이 된다.
    """
    key = _a_ledger_key()
    created = client.post(
        "/scenarios",
        params={
            "name": f"거부 {kind} 를 담은 설정",
            "owner_id": DEMO_OWNER_ID,
            "definition_json": _malformed(kind, key),
        },
    )
    assert created.status_code == 200, created.text
    settings_id = created.json()["id"]

    applied = client.get("/ui/settings", params={"applied": settings_id})

    assert applied.status_code == 400, applied.text
    assert "text/html" in applied.headers["content-type"]
    for part in ("필드", "사유", "조치"):
        assert part in applied.text, f"거부 화면에 {part} 가 없다 (NFR-303 3요소)"
    assert must_say in applied.text, "무엇이 거부됐는지 화면이 적지 않는다"


# ── 사용자가 든 다섯과 시계열 자리 — **못 그리는 칸을 지우지 않는다** ────────


def test_the_five_items_the_user_named_are_drawn_first(client: TestClient) -> None:
    """사용자가 든 다섯이 화면 **앞쪽**에 있고, 대장에 없는 것은 「없다」로 적힌다.

    ⚠ **`req()` 마커를 달지 않았다** — 사용자 문면(`docs/decisions-2026-09-05
    -R63.md` §1)이지 조항이 아니다.

    ⚠ 지어내지 않는다. 대장에 없는 항목은 **칸을 남기고 사유를 글자로** 적는
    것이 이 저장소의 규약이다(§13.0.1 ④ — 「없다」와 「안 그렸다」를 같게 읽지
    않는다).
    """
    body = client.get("/ui/settings").text

    for word in ("전기요금", "태양광 발전 프로파일", "전기사용자 부하", "설비별 단가", "이용률"):
        assert f'data-user-item="{word}"' in body, f"사용자가 든 「{word}」 칸이 없다"

    assert "시계열" in body, "시계열 항목의 자리가 화면에 없다"
    assert "이 라운드 범위 밖" in body, (
        "시계열 편집기가 왜 없는지가 화면에 글자로 적히지 않았다"
    )
