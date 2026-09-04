"""R54/WP-4 — `GAP_MARGIN`(흑자 렌더 경로) 코드 경로 프로브. **정확도 시험이
아니라 회귀 시험이다** — 아래가 붙드는 것은 「이 값이 사업 전망이다」가
아니라 「이 분기가 실행되면 이 문면이 난다」다.

## 왜 이 파일이 필요한가

`core/report/narrative.py` 는 결손·흑자 두 갈래를 적는다:

    direction = GAP_MARGIN if report.recovers_within_horizon else GAP_SHORTFALL

`tests/golden/test_regression_scenarios.py` 가 도는 골든 3종
(`fixtures/golden/scenario_*.yaml`)은 전부 `payback_years == .inf`(미회수)
이고 결론축이 결손이다 — 그 모듈 독스트링 ④가 그 사실을 스스로 적는다.
즉 **`GAP_MARGIN` 쪽은 이 저장소에서 한 번도 실행된 적이 없었다.**

진짜 대장(`docs/assumptions.yaml`)으로는 이 분기를 열 수 없다 — 전환지원율이
117.7%(전액 지원으로도 20년 안에 미회수, `docs/assumptions.yaml` 의
`benefit.rec_price` 항목 `impact_note` 참조)다. 그래서 이 파일은 **시험용
파생 대장**(`fixtures/probe/assumptions_probe_gap_margin.yaml`)을 만들어
`build_case_report(scenario_path, *, assumptions_path=...)` 의
`assumptions_path` 인자로 넘긴다 — `core/` 조립기 코드는 한 줄도 고치지
않는다. 그 파생 대장은 `docs/assumptions.yaml` 을 그대로 복제한 뒤
`benefit.rec_price` 「한 항목의 `value` 한 칸만」 70 → 320원/kWh 로
올렸다(그 파일 머리말이 실측 경위를 갖는다) — **나머지 전 항목은 진짜
대장과 바이트 단위로 같다.**

## ⚠⚠⚠ 이 320원/kWh 은 사업 전망이 아니다

실제 REC 시세(2026-09-02 KPX·haezoom 조사, `docs/assumptions.yaml` 참조)의
**4.6배**에 달하는 비현실적인 시험 값이며, 오직 이 코드 경로를 실행시키기
위해서만 골랐다. 이 사업이 흑자라는 주장이 전혀 아니다.

## 대조군 (판정 ④)

같은 시나리오(`subsidy_rate=0.80`)를 **진짜 대장**으로 돌리면
`recovers_within_horizon` 이 `False` 이고 `GAP_SHORTFALL` 쪽이 실려야
한다 — 그렇지 않으면 「흑자 경로가 돈다」와 「늘 그 문면이 나온다」가
구별되지 않는다. 그 대조군은 `fixtures/golden/scenario_subsidy_80.yaml`
(기존 골든, 여기서 건드리지 않는다)이 이미 매 회귀에서 실측하는 값
(`npv_won: -3712270`)과 같아야 하므로, 이 실측이 그 골든과 어긋나면 이
파일이 아니라 진짜 대장이나 `core/` 가 움직인 것이다.

## `fixtures/golden/` 의 자동 수집을 피한 자리 (판정 ③)

`tests/golden/test_regression_scenarios.py` 는
`GOLDEN_DIR.glob("scenario_*.yaml")`(`GOLDEN_DIR = fixtures/golden`)로
**자동 수집**한다. 이 프로브의 시나리오·대장 파일을 `fixtures/golden/` 에
두면 그 회귀가 시험용 파생 대장이 아니라 **진짜 대장**으로 그 파일들을
돌리게 되어(그 테스트는 `ASSUMPTIONS_PATH` 를 하드코딩한다) 수가 어긋나고
시험용 대장이 아예 쓰이지 않는다. 그래서 새 픽스처는 형제 디렉터리
`fixtures/probe/` 에 둔다 — 그 glob 은 `fixtures/golden/` 만 보므로 걸리지
않는다(아래 상수 두 파일의 실제 존재로 실측한다).

`tests/ci/test_performance_and_golden.py::
test_repo_golden_files_are_readable_and_declare_an_oracle_rank_and_source`
도 `GOLDEN_DIR.glob("scenario_*.yaml")` 로 같은 디렉터리만 보므로 이 프로브
시나리오의 `oracle_rank`·`oracle_source` 결여는 그 검사에 걸리지 않는다 —
그 파일의 골든 3종 개수 단언(`len(paths) == 3`)도 `fixtures/golden/` 안의
개수만 세므로 이 프로브가 그 수를 바꾸지 않는다.
"""

from __future__ import annotations

import math
from pathlib import Path

from core.report.case_report import build_case_report
from core.report.narrative import GAP_MARGIN, GAP_SHORTFALL, render_markdown

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_ASSUMPTIONS_PATH = REPO_ROOT / "docs" / "assumptions.yaml"
PROBE_DIR = REPO_ROOT / "fixtures" / "probe"
PROBE_SCENARIO_PATH = PROBE_DIR / "scenario_probe_gap_margin.yaml"
PROBE_LEDGER_PATH = PROBE_DIR / "assumptions_probe_gap_margin.yaml"


def _gap_direction_line(rendered: str, direction: str) -> bool:
    """`_gap_lines()`(`core/report/narrative.py` 120·390행)가 낸 그 줄인지 본다.

    리터럴 「여유」·「결손」을 검사에 직접 박지 않는다 — 상수(`GAP_MARGIN`·
    `GAP_SHORTFALL`)가 바뀌면 이 검사가 조용히 거짓이 되기 때문이다.
    대신 그 상수를 import 해 `_gap_lines()` 가 실제로 만드는 문형
    (`f"({direction} · 총사업비"`)으로 좁혀 찾는다 — 「없음 (검토 범위 내)」
    같은 무관한 자리에 같은 글자(「결손」)가 리터럴로 다시 나오므로
    (`_flip_names()`), `in rendered` 만으로는 두 분기를 가르지 못한다.
    """
    return f"({direction} · 총사업비" in rendered


def test_gap_margin_branch_renders_when_the_probe_ledger_flips_the_conclusion() -> None:
    """★★ 판정 ④-1·④-2 — 시험용 대장에서 `recovers_within_horizon` 이 `True`이고
    렌더 문면에 `GAP_MARGIN` 쪽이 실린다. **이 분기는 저장소에서 처음 실행된다**
    (모듈 독스트링 참조).
    """
    report = build_case_report(PROBE_SCENARIO_PATH, assumptions_path=PROBE_LEDGER_PATH)

    assert report.recovers_within_horizon is True
    assert math.isfinite(report.metrics["payback_years"]), (
        "흑자면 할인 회수기간이 유한해야 한다 — .inf 는 결손 쪽 값이다"
    )

    rendered = render_markdown(report)
    assert _gap_direction_line(rendered, GAP_MARGIN), (
        "GAP_MARGIN(흑자) 문형이 렌더 문면에 없다 — GAP_MARGIN 분기가 "
        "실제로는 실행되지 않았을 수 있다"
    )
    assert not _gap_direction_line(rendered, GAP_SHORTFALL), (
        "같은 렌더에 GAP_SHORTFALL(결손) 문형도 함께 실렸다 — 두 분기가 "
        "동시에 서는 것은 direction 이 한 값이어야 한다는 불변을 어긴다"
    )


def test_control_group_the_real_ledger_still_shows_a_shortfall() -> None:
    """★★★ 판정 ④-3 대조군 — **같은 시나리오**를 진짜 대장으로 돌리면
    `recovers_within_horizon` 이 `False` 이고 `GAP_SHORTFALL` 쪽이 실린다.

    이 대조군이 없으면 「흑자 경로가 돈다」와 「늘 그 문면이 나온다」가
    구별되지 않는다(모듈 독스트링 참조). `fixtures/golden/
    scenario_subsidy_80.yaml`(기존 골든)이 같은 `subsidy_rate=0.80` 을
    진짜 대장으로 매 회귀에서 재는 값(`npv_won: -3712270`)과 일치해야
    한다 — 이 실측이 그 값과 어긋나면 이 파일이 아니라 진짜 대장이나
    `core/` 가 움직인 것이다.
    """
    report = build_case_report(PROBE_SCENARIO_PATH, assumptions_path=REAL_ASSUMPTIONS_PATH)

    assert report.recovers_within_horizon is False
    assert report.metrics["npv"] == -3712270.0, (
        "대조군의 순현재가치가 fixtures/golden/scenario_subsidy_80.yaml 의 "
        "실측(-3712270)과 어긋난다 — 진짜 대장이나 core/ 가 움직였다는 뜻이다"
    )

    rendered = render_markdown(report)
    assert _gap_direction_line(rendered, GAP_SHORTFALL), (
        "GAP_SHORTFALL(결손) 문형이 대조군 렌더 문면에 없다"
    )
    assert not _gap_direction_line(rendered, GAP_MARGIN), (
        "대조군(진짜 대장)에서 GAP_MARGIN(흑자) 문형이 실렸다 — 대조군이 "
        "성립하지 않는다"
    )


def test_probe_fixtures_are_not_collected_by_the_golden_regression_glob() -> None:
    """★ 판정 ③ — 이 프로브 픽스처가 `fixtures/golden/` 의 자동 수집
    (`GOLDEN_DIR.glob("scenario_*.yaml")`)에 걸리지 않는 자리(`fixtures/
    probe/`)에 있는지를 **경로 그 자체로** 확인한다.
    """
    golden_dir = REPO_ROOT / "fixtures" / "golden"

    assert PROBE_SCENARIO_PATH.is_file()
    assert PROBE_LEDGER_PATH.is_file()
    assert golden_dir not in PROBE_SCENARIO_PATH.parents
    assert golden_dir not in PROBE_LEDGER_PATH.parents
    assert sorted(golden_dir.glob("scenario_*.yaml")) == sorted(
        p for p in golden_dir.glob("scenario_*.yaml")
        if p != PROBE_SCENARIO_PATH
    ), "프로브 시나리오가 골든 glob 에 잡혔다"
