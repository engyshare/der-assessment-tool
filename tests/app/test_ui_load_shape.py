"""화면에서 **부하의 형상**을 바꿀 수 있는가 — R64/WP-WEB ⓐⓑ (사용자 요구 2·3).

계산·판정·거부는 앞 WP 들이 세웠고(`core/casegrid/load_shift.py` ·
`core/casegrid/appliance_load.py`) **없던 것은 칸 하나씩**이었다. 이 파일이
재는 것은 그 구멍이다:

    ⓐ 하루 안에서 옮길 수 있는 가전 부하 비율 — 대장 오버라이드 통로
    ⓑ 냉난방 부하의 계절별 몫               — 시나리오 필드 통로

## ⚠⚠ 「200 을 냈다」로 만족하지 않는다

칸을 그리고 값을 되비추기만 해도 화면은 200 을 낸다. 그래서 재는 것은 넷이다 —
ⓐ 칸이 **있다** · ⓑ 넣은 값이 **러너까지 간다** · ⓒ 그 값이 **결과를 바꾼다** ·
ⓓ **비운 실행이 종전과 같다**. 특히 마지막이 이 WP 의 판정 ② 다.

## 하나도 `web.render` 를 직접 부르지 않는다

전부 `TestClient(create_app())` 를 지난다 — 문맥 함수를 직접 부르면 「배포
코드가 부르지 않는 함수가 초록불을 만든다」를 그대로 다시 밟는다
(`tests/app/test_ui_run.py` 머리말이 같은 판단을 적었다).

## 기댓값을 소스에 박지 않는다

계절 이름은 **자산**(`fixtures/profiles/representative-day.yaml`)에서, 기본
비율은 **대장**(`docs/assumptions.yaml`)에서, 결론축은 **골든 픽스처**에서
읽어 대조한다. 박으면 그 셋 중 하나가 바뀌는 날 이 검사가 조용히 낡는다.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import create_app
from core.assumption.provider import AssumptionSet
from core.casegrid.appliance_load import APPLIANCE_SEASON_SHARE_UNSPECIFIED
from core.casegrid.load_shift import DR_SHIFTABLE_SHARE_LEDGER_KEY
from core.casegrid.profiles import load_daily_shapes
from web.render_load_shape import SEASON_SHARE_PREFIX

#: 결과 화면이 **서식 이전의 날값**으로 함께 싣는 것들. 서식을 입힌 문면만
#: 보면 이 검사가 서식 문자열을 다시 짜 맞추게 되고, 그때 재는 것은 수가
#: 아니라 표기가 된다(`tests/app/test_ui_run.py::_NPV_ATTRIBUTE` 와 같은 규약).
_NPV = re.compile(r'data-npv="([^"]+)"')
_SHIFT_SHARE = re.compile(r'data-dr-shiftable-share="([^"]*)"')
_SEASON_SHARE = re.compile(r'data-season-share="([^"]*)"')

#: ① 걸음의 계절별 표 — 검증 화면이 계절을 갈라 그리는 자리
#: (`tests/app/test_ui_verify.py` 가 같은 정규식으로 그 표를 붙든다).
_SEASON_TABLE = re.compile(
    r'<table data-season="([^"]+)" data-season-days="\d+">(.*?)</table>', re.DOTALL
)
_SEASON_ROW = re.compile(r'<tr data-season-step="\d+">(.*?)</tr>', re.DOTALL)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL)

_SCENARIO = "scenario_unsubsidized"

#: 계절 몫이 실제로 갈리는 것을 보려면 **냉난방 부하가 있어야 한다.** 배포
#: 골든 실행에는 기기 부하가 없어 그 몫이 걸릴 분모가 0 이다 — 그때 계절
#: 몫을 아무리 바꿔도 아무것도 움직이지 않는 것이 **정상**이다
#: (`.orch/R64/result_3b1.md` ④ 가 같은 수치로 그것을 적었다).
_HEATPUMP_LOAD = "3000"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / f"{_SCENARIO}.yaml"
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _golden_npv() -> float:
    """골든 회귀가 대조하는 **바로 그 수**를 그 파일에서 읽는다."""
    case = yaml.safe_load(_GOLDEN.read_text(encoding="utf-8"))
    return float(case["expected_values"]["npv_won"])


def _ledger_share() -> float:
    """대장이 가진 **기본 비율**. ⚠ 「10」을 여기 적지 않는다."""
    item = AssumptionSet.load_from_yaml(str(_ASSUMPTIONS)).items()[
        DR_SHIFTABLE_SHARE_LEDGER_KEY
    ]
    return float(item.value)


def _season_names() -> tuple[str, ...]:
    """자산이 선언한 계절 이름. ⚠ 「봄·여름·가을·겨울」을 여기 적지 않는다."""
    return tuple(season.name for season in load_daily_shapes().load.seasons)


def _even_shares() -> dict[str, str]:
    """계절 전부에 **같은 몫** — 합이 1 이다 (계절 수가 변해도 성립한다)."""
    names = _season_names()
    shares = {name: f"{1 / len(names):.10f}" for name in names}
    # ⚠ 마지막 칸으로 나머지를 맞춘다 — 1/3 처럼 안 나누어지는 계절 수에서
    # 합이 1 에서 밀리면 이 검사가 「합 ≠ 1」 거부를 받고, 그것은 검사가
    # 재려던 것이 아니다.
    head = sum(float(shares[name]) for name in names[:-1])
    shares[names[-1]] = f"{1.0 - head:.10f}"
    return shares


def _winter_heavy_shares() -> dict[str, str]:
    """**마지막 계절에 몰아 준** 몫 — 자산의 차례에서 마지막이 겨울이다.

    ⚠ 「겨울」을 이름으로 박지 않는다. 이 검사가 재는 것은 *「몰아 준 계절이
    늘고 그 밖의 계절이 줄었는가」* 이며, 그것은 어느 계절이든 성립한다.
    """
    names = _season_names()
    rest = 0.3 / (len(names) - 1)
    shares = {name: f"{rest:.10f}" for name in names[:-1]}
    shares[names[-1]] = f"{1.0 - rest * (len(names) - 1):.10f}"
    return shares


def _as_query(shares: dict[str, str]) -> dict[str, str]:
    """`{계절: 몫}` → **폼이 보내는 칸 이름**으로.

    ⚠ 앞머리를 여기 적지 않고 배포 코드의 상수를 쓴다 — 이름 규칙이 두 곳에
    살면 한쪽만 고쳐지는 날 이 검사가 아무 칸도 못 채운 채 초록불을 낸다.
    칸 이름의 **문면 자체**는 위 `test_the_dashboard_draws_a_box_for_every_
    season_the_asset_declares` 가 리터럴로 붙든다.
    """
    return {f"{SEASON_SHARE_PREFIX}{season}": share for season, share in shares.items()}


def _npv_on_screen(body: str) -> float:
    match = _NPV.search(body)
    assert match is not None, "결과 화면이 결론 축을 날값으로 싣지 않았다"
    return float(match.group(1))


def _season_load(body: str) -> dict[str, float]:
    """검증 화면의 계절별 표에서 **계절마다 하루 부하 합**을 꺼낸다.

    ⚠ 열 번호를 박지 않는다 — 머리글에서 `e2e-load` 열을 찾아 그 열만 더한다.
    박으면 자원이 하나 늘어 열이 밀리는 날 이 검사가 다른 열을 재면서
    초록불을 낸다.
    """
    totals: dict[str, float] = {}
    for name, table in _SEASON_TABLE.findall(body):
        header = _CELL.findall(table[: table.index("</thead>")])
        column = next(
            index for index, cell in enumerate(header) if "e2e-load" in cell
        )
        totals[name] = sum(
            float(_CELL.findall(row)[column]) for row in _SEASON_ROW.findall(table)
        )
    assert totals, "검증 화면에 계절별 표가 없다 — 잴 것이 없다"
    return totals


# ── ⓐ 하루 안에서 옮기는 비율 ────────────────────────────────────────────────


def test_the_dashboard_lets_a_person_type_the_shift_share(client: TestClient) -> None:
    """★★ **요구 2 의 남은 절반이 화면에 선다** — 「AI 가전」이 옮기는 비율.

    ⚠⚠ **칸에 기본값이 박혀 있으면 안 된다.** 박으면 대장을 고쳐도 화면만 옛
    수를 밀어 넣고, 그때 실행되는 것은 **대장에 없는 값**이다.
    ⚠ 대신 **대장 값이 글자로** 있어야 한다(판정 ④) — 비우면 무엇이 쓰이는지
    모르면 사용자는 자기가 넣는 수가 무엇을 대신하는지 알 수 없다.
    """
    body = client.get("/").text
    marker = 'name="dr_shiftable_share_pct"'
    assert marker in body, "대시보드 실행 폼에 옮길 비율 칸이 없다"
    field = body[body.index(marker) :]
    field = field[: field.index(">") + 1]
    assert "value=" not in field, (
        f"비율 칸에 기본값이 박혀 있다 — 대장이 갖는 값이다: {field!r}"
    )
    assert f"{_ledger_share():g}" in body, (
        "화면이 대장의 기본 비율을 글자로 적지 않는다 — 비우면 무엇이 쓰이는지 "
        "사용자가 알 수 없다"
    )
    assert "가정" in body, "그 값이 가정이라는 것을 화면이 적지 않는다"


def test_an_empty_shift_share_runs_on_the_ledger_value_not_zero(
    client: TestClient,
) -> None:
    """★★★ **비우면 0 이 아니라 대장 값이다** (판정 ②).

    비운 칸을 0 으로 밀어 넣으면 *「하나도 옮기지 않는다」* 라는 **다른
    실행**이 되고 결론축이 움직인다 — 그때 골든 회귀가 빨간불이 되며 원인은
    화면이다. 그 구별을 여기서 붙든다.
    """
    body = client.get("/ui/run", params={"scenario": _SCENARIO}).text
    match = _SHIFT_SHARE.search(body)
    assert match is not None, "결과 화면이 옮긴 비율을 날값으로 싣지 않았다"
    assert float(match.group(1)) == _ledger_share(), (
        f"비운 실행이 대장 값({_ledger_share():g})이 아니라 "
        f"{match.group(1)} 로 돌았다"
    )
    assert _npv_on_screen(body) == pytest.approx(_golden_npv(), abs=1.0), (
        "비운 실행의 결론축이 골든 회귀의 수와 다르다 — 「비움 = 기본값」이 깨졌다"
    )


def test_typing_a_shift_share_reaches_the_runner_and_moves_the_number(
    client: TestClient,
) -> None:
    """★★★ 넣은 값이 **러너까지 가고 결론축을 움직인다** — 표시만이 아니다.

    ⚠ 두 방향을 함께 잰다. 날값만 보면 *「되비추기만 한다」* 로도 통과하고,
    수만 보면 *「엉뚱한 값으로 돌았다」* 를 구별하지 못한다.
    """
    typed = f"{_ledger_share() * 2:g}"
    body = client.get(
        "/ui/run", params={"scenario": _SCENARIO, "dr_shiftable_share_pct": typed}
    ).text
    assert float(_SHIFT_SHARE.search(body).group(1)) == float(typed), (
        f"화면이 넣은 비율({typed})이 러너까지 가지 않았다"
    )
    plain = _npv_on_screen(client.get("/ui/run", params={"scenario": _SCENARIO}).text)
    assert _npv_on_screen(body) != pytest.approx(plain, abs=1.0), (
        f"비율을 {typed}% 로 올렸는데 결론축이 그대로다({plain:,.0f}원)"
    )


def test_zero_is_a_different_run_from_an_empty_box(client: TestClient) -> None:
    """★★ **0 과 빈 칸이 다른 실행이다** (판정 ②의 ⚠).

    0 은 *「옮기지 않는다」* 이고 빈 칸은 *「대장 값으로 돈다」* 다. 둘이 같은
    수를 내면 화면은 0 을 밀어 넣고 있는 것이며, 그 상태는 아무 오류도 내지
    않는다 — 결론축만 조용히 움직인다.
    """
    empty = _npv_on_screen(client.get("/ui/run", params={"scenario": _SCENARIO}).text)
    zero = _npv_on_screen(
        client.get(
            "/ui/run", params={"scenario": _SCENARIO, "dr_shiftable_share_pct": "0"}
        ).text
    )
    assert zero != pytest.approx(empty, abs=1.0), (
        f"0 을 적은 실행과 비운 실행의 결론축이 같다({empty:,.0f}원) — 화면이 "
        "빈 칸을 0 으로 밀어 넣고 있다"
    )


def test_a_shift_share_above_a_hundred_is_refused_as_a_readable_screen(
    client: TestClient,
) -> None:
    """★★ **100 을 넘는 「비율」은 3요소로 거부한다** — JSON 이 아니라 화면이다.

    그 값을 받아 주면 옮길 몫이 그 시각 부하보다 커져 **부하가 음수**가 되고,
    음수 부하는 설비 없는 발전이다.
    """
    response = client.get(
        "/ui/run", params={"scenario": _SCENARIO, "dr_shiftable_share_pct": "500"}
    )
    assert response.status_code == 400, response.text[:200]
    assert "옮길 수 있는 가전 부하 비율" in response.text
    assert "조치" in response.text


# ── ⓑ 계절별 냉난방 몫 ──────────────────────────────────────────────────────


def test_the_dashboard_draws_a_box_for_every_season_the_asset_declares(
    client: TestClient,
) -> None:
    """★★ **요구 3 이 화면에 선다** — 자산이 선언한 계절마다 칸 하나.

    ⚠⚠ **계절 이름을 화면이 스스로 짓지 않는다.** 자산이 달력을 고치는 날
    화면만 옛 이름을 그리면 사용자가 받는 것은 「달력이 다르다」는 거부이고,
    왜 거부됐는지는 화면에 없다.
    """
    body = client.get("/").text
    for name in _season_names():
        assert f'name="season_share-{name}"' in body, (
            f"자산이 선언한 계절 {name!r} 의 몫 칸이 화면에 없다"
        )
    assert body.count('name="season_share-') == len(_season_names()), (
        "계절 칸 수가 자산의 계절 수와 다르다 — 한 계절이 두 번 그려졌거나 "
        "자산에 없는 계절이 그려졌다"
    )


def test_typing_season_shares_actually_splits_the_seasons(
    client: TestClient,
) -> None:
    """★★★ **계절마다 다른 값이 실제로 갈린다** — 검증 화면의 계절별 표로 잰다.

    ⚠⚠ **몰아 준 계절이 늘었다」만 재지 않는다.** 그것만 보면 *「부하를 더
    얹었다」* 와 구별되지 않는다 — 그래서 ⓐ 몰아 준 계절이 늘고 ⓑ **그 밖의
    계절이 줄고** ⓒ 합이 그대로임을 함께 잰다
    (`.orch/R64/result_3b1.md` ④ 가 같은 셋을 로직 층에서 잰다).
    """
    base = {"scenario": _SCENARIO, "heatpump_load_annual_kwh": _HEATPUMP_LOAD}
    flat = _season_load(client.get("/ui/verify", params=base).text)
    heavy = _season_load(
        client.get("/ui/verify", params={**base, **_as_query(_winter_heavy_shares())}).text
    )

    assert set(flat) == set(heavy)
    loaded = _season_names()[-1]
    assert abs(heavy[loaded]) > abs(flat[loaded]), (
        f"{loaded} 에 몫을 몰아 줬는데 그 계절의 하루 부하가 늘지 않았다: "
        f"{flat[loaded]} → {heavy[loaded]}"
    )
    lightened = [
        name for name in _season_names()[:-1] if abs(heavy[name]) < abs(flat[name])
    ]
    assert lightened, (
        "몰아 준 계절만 늘고 **줄어든 계절이 없다** — 그것은 계절을 가른 것이 "
        f"아니라 부하를 더 얹은 것이다: {flat} → {heavy}"
    )


def test_even_season_shares_keep_the_screen_running(client: TestClient) -> None:
    """★ 합이 1 인 **균등한 몫**은 거부되지 않는다 — 거부가 넓어지지 않았다.

    이 검사가 없으면 「합 ≠ 1 을 거부한다」가 **전부 거부한다**로 굳어도
    빨간불이 나지 않는다.
    """
    response = client.get(
        "/ui/run",
        params={
            "scenario": _SCENARIO,
            "heatpump_load_annual_kwh": _HEATPUMP_LOAD,
            **_as_query(_even_shares()),
        },
    )
    assert response.status_code == 200, response.text[:400]
    assert len(_SEASON_SHARE.findall(response.text)) == len(_season_names()), (
        "결과 화면이 계절 몫을 계절마다 싣지 않았다"
    )


def test_season_shares_that_do_not_sum_to_one_are_refused_as_a_readable_screen(
    client: TestClient,
) -> None:
    """★★ **합이 1 이 아니면 3요소로 거부한다** — 정규화해 주지 않는다.

    0.9 면 연간 에너지의 10%가 조용히 사라지고 1.1 이면 없던 것이 생긴다.
    정규화하면 「자산이 틀렸다」와 「이렇게 쓰기로 했다」가 구별되지 않는다.
    """
    broken = dict.fromkeys(_season_names(), "0.1")
    response = client.get(
        "/ui/run", params={"scenario": _SCENARIO, **_as_query(broken)}
    )
    assert response.status_code == 400, response.text[:200]
    assert "합이" in response.text and "조치" in response.text


def test_season_shares_only_partly_filled_are_refused_as_a_readable_screen(
    client: TestClient,
) -> None:
    """★★★ **일부만 적은 것을 거부한다** — 빈 칸을 0 으로 읽지 않는다.

    빈 칸을 0 으로 읽으면 그 계절의 냉난방이 통째로 사라지는데, 사용자는
    *「아직 안 적었다」* 를 뜻했을 수 있다. 둘을 가를 수 없으므로 묻는다.

    ⚠⚠ **화면이 빈 칸을 버리면 이 거부가 사라진다.** 폼은 빈 칸도 함께
    보내므로(HTML 규약) 거두는 쪽이 그것을 버리지 않아야 한다 —
    `web/render_load_shape.py::appliance_season_shares` 의 ⚠⚠ 절이 그 사유다.
    """
    names = _season_names()
    partly = {name: "" for name in names}
    partly[names[0]] = "1.0"
    response = client.get(
        "/ui/run", params={"scenario": _SCENARIO, **_as_query(partly)}
    )
    assert response.status_code == 400, response.text[:200]
    assert "일부만" in response.text, (
        "일부만 적은 제출이 「일부만 적었다」로 거부되지 않았다 — 빈 칸이 "
        f"버려졌을 수 있다: {response.status_code}"
    )


def test_a_season_the_asset_does_not_know_is_refused_as_a_readable_screen(
    client: TestClient,
) -> None:
    """★★ **자산의 달력과 다른 이름은 거부한다** — 짐작해 맞추지 않는다.

    이름이 다르면 같은 몫이 다른 날에 걸린다(겨울 몫이 봄에 걸린다).
    """
    response = client.get(
        "/ui/run", params={"scenario": _SCENARIO, "season_share-여름철": "1.0"}
    )
    assert response.status_code == 400, response.text[:200]
    assert "달력" in response.text and "조치" in response.text


# ── 결과 화면이 무엇으로 돌았는지 적는가 ────────────────────────────────────


def test_the_result_screen_says_what_shape_it_ran_on(client: TestClient) -> None:
    """★★★ 결과 화면이 **무엇으로 돌았는지**를 싣는다 — 안 준 실행도.

    바꿀 수 있게 해 놓고 결과가 그것을 안 적으면 확인할 방법이 없다. 특히
    계절 몫은 **안 준 실행도 글자로** 적어야 한다 — 빈칸이면 「기본 부하와
    같은 몫으로 돌았다」와 「그 축이 없다」가 화면에서 같아진다.
    """
    unspecified = client.get("/ui/run", params={"scenario": _SCENARIO}).text
    assert APPLIANCE_SEASON_SHARE_UNSPECIFIED in unspecified, (
        f"계절 몫을 안 준 실행이 「{APPLIANCE_SEASON_SHARE_UNSPECIFIED}」를 "
        "적지 않았다"
    )
    assert "총량은 그대로" in unspecified, (
        "이 두 축이 총량을 바꾸지 않는다는 것을 결과 화면이 적지 않는다 — "
        "검토자가 「부하가 늘었다」로 읽는다"
    )


def test_the_chart_url_carries_the_shape_so_the_picture_is_the_same_run(
    client: TestClient,
) -> None:
    """★★ 그림 주소가 **이 실행의 형상**을 달고 나간다.

    안 달면 화면의 수는 겨울에 몰아 준 것인데 그림은 균등한 것이 되고, **둘 다
    그럴듯해 보인다**(`web/render_run.py::chart_query` 가 갈래·가구 수·기기
    부하에 대해 같은 판단을 적었다).

    ⚠ 안 준 실행의 주소는 **종전과 한 글자도 달라지지 않아야** 한다 — 그
    주소는 심의에서 그대로 인용되는 자리다.
    """
    plain = client.get("/ui/run", params={"scenario": _SCENARIO}).text
    assert "dr_shiftable_share_pct" not in plain, (
        "안 준 실행의 그림 주소에 빈 형상 질의가 붙었다"
    )
    assert "season_share-" not in plain

    shaped = client.get(
        "/ui/run",
        params={
            "scenario": _SCENARIO,
            "dr_shiftable_share_pct": "20",
            **_as_query(_even_shares()),
        },
    ).text
    charts = shaped[shaped.index("visual-grid") :]
    assert "dr_shiftable_share_pct=20" in charts, (
        "그림 주소가 이 실행의 비율을 달고 있지 않다"
    )
    for name in _season_names():
        assert f"season_share-{quote(name)}" in charts, (
            f"그림 주소가 계절 {name!r} 의 몫을 달고 있지 않다"
        )
