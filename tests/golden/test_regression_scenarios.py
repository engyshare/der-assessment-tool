"""골든 3종 회귀 스냅숏 — **이 파일이 무엇을 재고 무엇을 못 재는가.**

정본은 작업목록 16.4 다: *「가정값 위의 골든은 회귀 테스트이지 정확도 테스트가
아니다. … 이 3종이 통과한다는 것은 «계산이 어제와 같다» 는 뜻이지 «계산이 맞다»
는 뜻이 아니다.」* 아래 대조가 초록불인 것은 그 뜻이며, 그 이상을 주장하지 않는다.

## ① 이 골든이 재는 모양 — **실행 경로 그대로** (R39-F 가 옮겼다)

`_scenario_metrics()` 는 `core.report.case_report.build_case_report()` 를 부른다.
그것이 대장에서 수준표를 만들고, 분석기간을 전제 층에서 받고, 시나리오의
`subsidy_rate` 로 지원안을 세우고, 일사 곡선을 실어 `run_single_case_e2e()` 를
돌리는 **하나뿐인 조립기**다. 즉 이 회귀는 **실물 산출물이 내는 수**를 붙든다 —
편익 1행 + 부호를 뒤집은 비용 여러 행(고정 O&M 둘 · 전력 구매 · 정산 수수료 ·
**교체비 · 잔존가치**)이 전부 들어간다.

**손으로 행을 세우지 않는다.** 여기서 현금흐름을 흉내내면 실행 경로가 바뀔 때
또 갈리고, 그 갈림을 아무도 못 본다 — 아래 ②가 그 상태였다.

## ② 종전에는 갈려 있었다 — **다섯 라운드가 미룬 이동이고 R39 에 조건이 갖춰졌다**

R38-C2 까지 이 파일은 `benefit_row` **한 행**만 세웠다(비용 행 없음). 한 해에 행이
하나뿐이라 **행 단위 순회와 연 단위 순회가 같은 목록을 냈고**, 그래서
`payback_simple` 이 한 해의 행을 합치지 않고 세고 있었는데도 세 시나리오가 전건
초록불이었다 — **이 골든은 그 결함의 파수꾼이 아니었다.**

옮기는 조건은 *「비용 행 구성이 확정된 뒤에 **한 번**」* 이었다(R38 판정 ·
당시 `todo.md` 1번 — 그 파일은 R45 에 `status.md` 「다음에 집을 것」 절로
합쳐졌다). R39-E 가 교체비·잔존가치를 배선해 그 조건이 갖춰졌고, 이동으로
여섯 값이 전부 바뀌었다 — **무보조 `npv` 는 부호가 뒤집혔다**(+2,270,362 →
−6,066,881). 그 크기는 「기준값이 틀렸었다」가 아니라 **재는 대상이 달라졌다**
는 뜻이다.

⚠ **R40 이 셋을 한 번 더 옮겼다** — 「모양」이 또 바뀐 것이 아니라 **그 모양 안의
값**이 바뀌었다. `ESS._acquisitions()` 가 배터리 재취득분에 물가 계수를 곱하지
않고 있었고(R39 가 부채로 남긴 한 줄), 고치니 세 `npv_won` 이 **각각 −222,794원**
내려갔다(무보조 **−6,289,675**). `payback_period_years` 는 셋 다 그대로다 — 움직인
두 흐름(18년차 교체비 · 20년차 잔존가치)이 전부 회수 시점 **뒤**에 있다.

## ③ ★ 주 지표의 **정체가 바뀌었다** — 같은 이름, 다른 수

`payback_period_years` 는 종전에 `payback_simple`(할인 없음)이었고, 지금은 실행
경로가 내는 `payback_years` = **`payback_discounted`** 다. 이름 칸은 같지만 **다른
지표**이므로 옛 값과 새 값을 견주면 안 된다. 실행 경로의 지표를 그대로 싣는 것이
이 이동의 목적이다 — 골든이 자기만의 지표를 갖고 있으면 그것이 또 하나의 정본이
된다.

## ④ 미회수는 `.inf` 로 싣는다 — `null` 로 두면 **조용히 검사에서 빠진다**

무보조·보조 20% 는 20년 안에 회수되지 않아 `payback_years` 가 `inf` 다. `null` 로
적으면 `_expected_values()` 가 숫자가 아닌 값을 걸러 **그 지표가 대조 목록에서
사라지고**, 회귀는 초록불인 채 한 지표를 잃는다. 실측으로 확인했다 —
`yaml.safe_load(".inf")` 는 `float('inf')` 이고 `pytest.approx(inf)` 는 `inf` 에만
참이다(유한값에는 거짓). 그래서 **`.inf` 는 대조되는 값**이며, 어느 날 회수가
되기 시작하면 이 회귀가 빨간불이 된다.

## ⑤ 세 yaml 이 선언한 출처는 별개 축이며 **고치지 않았다**

세 yaml 은 오라클 순위 3(외부 공표 실적)과 출처 파일
`tests/integration/test_wave2_end_to_end.py` 를 선언한다. 그 파일은 **회수기간을
아예 계산하지 않고** `npv` 에도 수치 단언이 없다 — 즉 **선언된 출처는 이 두 수를
낼 수 없다.** 이것은 ①~④의 「모양」 축과 다른 **정박** 축이고, 정본이 이미
유예해 둔 자리다(작업목록 16.1b ④ — `Q-4`·`Q-5` 회신이 §13.3 판정을 연다).
**R39-F 도 그 유예를 풀지 않았다** — 순위·출처 필드는 주석이 아니라 파서가 읽는
값이므로 값을 고치지 않고 사실만 남긴다. 기계로 적어 둔 자리는
`tests/ci/test_performance_and_golden.py` 의
`test_repo_golden_files_are_readable_and_declare_an_oracle_rank_and_source`
독스트링이다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from core.report.case_report import build_case_report

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "fixtures" / "golden"
ASSUMPTIONS_PATH = REPO_ROOT / "docs" / "assumptions.yaml"

#: 골든 yaml 의 지표 이름 → 실행 경로가 내는 지표 이름.
#:
#: **이름을 맞추려고 어느 한쪽을 고치지 않았다.** yaml 쪽은 2026-08-09 부터
#: 세 파일에 적혀 있고 CI·DoD 7 검사가 그 이름으로 읽으며, 실행 경로 쪽은
#: `core/casegrid/case_metrics.py::metrics_for` 가 케이스와 변형에 함께 쓰는
#: 이름이다(R57/WP-9 가 러너에서 옮겼다). 어느 쪽을 고쳐도
#: **이 파일 밖이 함께 움직인다** — 대신 그 대응을 여기 한 곳에 적는다.
#:
#: ⚠ `payback_period_years` 는 이제 **`payback_discounted`** 다(모듈 독스트링 ③).
_METRIC_KEYS: tuple[tuple[str, str], ...] = (
    ("npv_won", "npv"),
    ("payback_period_years", "payback_years"),
)


def _load_case(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"{path.name} is not a mapping"
    return loaded


def _expected_values(case: dict[str, Any]) -> dict[str, float]:
    expected = case.get("expected_values")
    if not isinstance(expected, dict):
        return {}
    return {
        key: float(value)
        for key, value in expected.items()
        if isinstance(value, (int, float))
    }


def _scenario_metrics(scenario_path: Path) -> dict[str, float]:
    """시나리오 하나를 **실행 경로로 돌려** 골든이 대조할 지표를 낸다.

    `build_case_report()` 하나만 부른다 — 그것이 대장 → 수준표 → 분석기간 →
    지원안 → 일사 곡선 → `run_single_case_e2e()` 를 잇는 **유일한 조립기**이고,
    출구(라우터·CLI)도 같은 함수를 부른다. 여기서 그 조립을 다시 쓰면 **골든이
    출구와 다른 것을 재게 된다.**

    ⚠ **지원(`subsidy_rate`)은 `metrics` 에 이미 반영돼 있다** — 실측으로
    확인했다(R40 에 다시 쟀다): 보조 20% 는 `−4,329,675원`, 80% 는
    `+1,550,325원`이며 `variants["as_planned"]` 와 같은 수다
    (`variants["unsupported"]` 는 세 시나리오 모두 무보조 값 `−6,289,675원`).
    그러므로 여기서 지원을 **다시 계산하지 않는다** — 계산하면 두 번 반영되거나,
    조립기가 바뀔 때 갈린다.

    ⚠ 시나리오 **경로**를 받는다(종전에는 `subsidy_rate` 숫자였다). 조립기가
    파일에서 읽는 것이 지원율만이 아니기 때문이며, 지원율만 넘기면 같은 율을
    가진 시나리오 둘을 구별할 수 없다.
    """
    report = build_case_report(scenario_path, assumptions_path=ASSUMPTIONS_PATH)
    return {
        golden_key: float(report.metrics[metric_key])
        for golden_key, metric_key in _METRIC_KEYS
    }


def _compare(path: Path, expected: dict[str, float], actual: dict[str, float]) -> None:
    for key, expected_value in expected.items():
        assert key in actual, f"{path.name}: missing actual value for {key}"
        if key == "npv_won":
            assert actual[key] == expected_value, (
                f"{path.name}: {key} expected {expected_value}, actual {actual[key]}"
            )
        else:
            assert actual[key] == pytest.approx(expected_value, rel=1e-3, abs=1e-3), (
                f"{path.name}: {key} expected {expected_value}, actual {actual[key]}"
            )


# `FR-1103-AC1` 을 함께 붙인 이유 (R17):
#
# 조항은 *「GitHub Actions 에서 pytest·ruff·**골든 시나리오 3종 수치 회귀**
# 통과 시에만 머지」* 다. **그 「수치 회귀」를 실제로 하는 것이 이 테스트다** —
# 계산값을 `expected_values` 와 대조한다. 그런데 마커가 `NFR-104-M1` 뿐이어서
# `FR-1103-AC1` 은 `tests/acceptance2/test_17_7_dod7.py` 의 **간접 확인**들로만
# 매핑돼 있었고, 그중 여럿이 *「파일이 있는지」·「필드가 있는지」* 수준이었다.
# 즉 **조항이 요구한 실검증은 존재했는데 그 조항이 그것을 가리키지 않았다.**
@pytest.mark.req("NFR-104-M1", "FR-1103-AC1")
@pytest.mark.parametrize("path", sorted(GOLDEN_DIR.glob("scenario_*.yaml")))
def test_golden_scenarios_match_current_regression_snapshot(path: Path) -> None:
    case = _load_case(path)
    expected = _expected_values(case)
    if not expected:
        print(f"SKIP {path.name}: expected_values are all null")
        pytest.skip(f"{path.name}: expected_values are all null")

    actual = _scenario_metrics(path)
    _compare(path, expected, actual)
