"""폼 값 → 시나리오 → 실행 → 결과 — `FR-705-AC2` 의 **고르는 쪽**.

## 왜 이 파일이 R62 에 생겼는가

엔진은 기준선 갈래 셋(ⓐ「자가용 없음」· ⓑ「자가용 유지」· ⓒ「자가용
집합자원화」)을 **이미 다 돈다.** 못 하던 것은 **사람이 고르는 것**이다 —
갈래를 바꾸려면 `fixtures/golden/*.yaml` 을 편집할 수 있어야 했고, 그것은
사업 설계자가 할 수 있는 일이 아니다. 사용자 요구(`docs/decisions-2026-09-05
-R61.md` §2 · `docs/decisions-2026-09-04-R59b.md` §1)가 그 자리를 가리킨다.

## ★★★ 통로는 **시나리오 필드 하나**다 — 새 통로를 내지 않는다

`core.report.case_report.build_case_report()` 는 **경로만** 받고 갈래를
시나리오 yaml 의 `baseline_arrangement` 필드에서 읽는다(그 함수 안의 ★★★
주석 둘이 정본이다). 그래서 이 서비스가 하는 일은 **시나리오를 짓는 것**이다:

    골든 시나리오 yaml 을 읽는다 → 거기에 갈래(+ⓒ 전제)를 얹은 매핑을 만든다
    → 임시 디렉터리에 yaml 로 쓴다 → 그 경로로 `build_case_report`

⚠⚠ **`build_case_report` 에 인자를 더하거나 `core/` 에 우회 통로를 내지
않는다.** 그것이 「통로가 둘」이고, 그때 산출물만 봐서는 어느 쪽이 이겼는지
알 수 없다 — 같은 판단을 `core/cba/baseline.py::POOL_METERING_FIELD` 주석이
이미 적어 두었다.

⚠ **골든 픽스처를 고치지 않는다.** 읽기만 한다.

## 화살표의 뒤 두 걸음은 **옆 파일**이 한다 (R64/WP-PERF)

임시 디렉터리에 쓰고 `build_case_report` 를 부르는 것은
`app/services/ui_run_cache.py::case_report_for` 다. 이 파일이 하던 그 절차를
한 글자도 바꾸지 않고 옮긴 것이며, 옮긴 뒤 달라진 것은 **같은 입력을 두 번
세우지 않는다**는 것뿐이다 — 화면 하나가 이것을 아홉 번 부르는 것이 실측이고
(HTML 1 + 그림 8), 그 아홉이 42초여서 e2e 의 30초 예산을 이미 넘겨 있었다.
사유의 정본은 그 파일 머리말이다.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.services.ui_run_cache import case_report_for
from core.assumption.scenario_overrides import ASSUMPTION_OVERRIDES_FIELD
from core.casegrid.appliance_load import (
    APPLIANCE_SEASON_SHARE_FIELD,
    EV_LOAD_FIELD,
    HEATPUMP_LOAD_FIELD,
)
from core.casegrid.household_scale import HOUSEHOLD_COUNT_FIELD
from core.casegrid.load_shift import (
    DR_SHIFTABLE_SHARE_LEDGER_KEY,
    resolve_shiftable_share,
)
from core.cba.baseline import POOL_METERING_FIELD, PoolMeteringDeclaration
from core.report.case_report import CaseReport

#: 저장소 뿌리 — `app/services/ui_run.py` 에서 두 단계 위.
#: `app/routers/reports.py` 가 같은 셈으로 같은 두 자리를 잡는다.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_DIR = _REPO_ROOT / "fixtures" / "golden"
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"

#: 갈래가 들어가는 **시나리오 yaml 필드 이름**.
#:
#: ⚠ 이 문자열의 정본은 `core/report/case_report.py::build_case_report` 의
#: `scenario.get("baseline_arrangement")` 다. `core/cba/baseline.py` 는 ⓒ 의
#: 계측 선언에만 이름 상수(`POOL_METERING_FIELD`)를 두었고 **갈래 쪽에는
#: 그런 상수가 없다** — 그래서 여기서 문면을 다시 적는다. 어긋나면 조용하지
#: 않다: 필드 이름이 바뀌면 갈래가 시나리오에 실리지 않고, 그때 아래
#: `test_choosing_an_arrangement_actually_moves_the_number` 가 「ⓐ 와 ⓑ 의
#: npv 가 같다」로 빨간불이 된다(`tests/app/test_ui_run.py`).
_ARRANGEMENT_FIELD = "baseline_arrangement"

#: 화면이 아무것도 고르지 않았을 때 여는 **골든 시나리오**.
#:
#: ⚠⚠ **문면을 이 저장소가 두 곳에 두고 있다.** `app/routers/ui.py::run_case`
#: 의 `scenario` 질의 기본값이 같은 글자를 리터럴로 적으며, 그 파일은 R63/S2 가
#: 고칠 수 있는 자리가 아니었다(다른 축이 같은 시간에 고치고 있었다). 상수를
#: 여기 두는 것은 **다음에 그 라우트가 이것을 집을 자리를 만드는 것**이고,
#: 그때까지 둘이 갈리지 않게 재는 검사가
#: `tests/app/test_ui_scenarios.py::test_the_settings_screen_defaults_to_the_
#: same_scenario_as_the_run_screen` 이다 — 두 라우트의 `openapi()` 질의 기본값을
#: 맞댄다. 갈리면 「오버라이드 안 건 실행의 결론축」이 화면마다 다른 수가 된다.
DEFAULT_UI_SCENARIO = "scenario_unsubsidized"

#: ⓐ 비율을 화면에서 바꿨을 때 오버라이드 줄이 싣는 **사유**(`FR-602-AC3`).
#:
#: ⚠ 비워 두지 않는다. 붙임 1 의 「기준 전제 대비 변경 항목」이 이 줄을
#: 인쇄하는데, 사유가 없으면 검토자는 *「누가 왜 10을 20으로 바꿨나」* 를
#: 산출물에서 알 수 없다 — 그 표가 생긴 이유가 그것이다.
SHIFTABLE_SHARE_OVERRIDE_REASON = "분석 실행 화면에서 지정한 값 (대장 값은 가정이다)"


def assumptions_path() -> Path:
    """실행 경로가 읽는 **그 전제 대장**의 자리.

    ⚠ 화면이 대장을 따로 열어야 할 때 경로를 스스로 짓지 않게 하려고 함수로
    내놓는다 — 두 곳이 각자 경로를 지으면 한쪽만 고쳐지는 날 화면과 실행이
    **서로 다른 대장**을 보고, 그때 화면은 사용자가 고칠 수 없는 값을 그린다.
    """
    return _ASSUMPTIONS


def golden_scenario_names() -> tuple[str, ...]:
    """실행할 수 있는 시나리오 이름 — **목록에 있는 것만 연다.**

    ⚠ **이름을 경로로 그대로 잇지 않는다.** `../` 이 섞이면 저장소 밖 파일을
    읽게 된다. 경로 정규화로 막지 않는 이유는 `app/routers/reports.py::
    _scenario_path` 와 `app/routers/ui.py::static_file` 이 이미 적어 두었다 —
    다음 사람이 형식을 늘릴 때 그 정규화를 다시 짜야 하고, 그 사이 어긋남은
    아무도 보지 못한다.
    """
    return tuple(sorted(path.stem for path in _GOLDEN_DIR.glob("scenario_*.yaml")))


@dataclass(frozen=True)
class UiRun:
    """화면이 그릴 것 — 리포트 **와** 실제로 넘긴 시나리오 문면.

    ⚠ **둘을 함께 나른다.** 심의에서 *「그 수가 어느 전제로 나왔나」* 를 묻는
    자리가 반드시 오고, 그때 화면이 답을 갖고 있어야 한다. 리포트만 나르면
    임시 파일은 이미 지워졌고 문면을 되지을 방법이 없다.
    """

    report: CaseReport
    #: 임시 디렉터리에 **실제로 쓴** yaml 텍스트. 골든 파일의 주석 수십 줄은
    #: 여기 들어 있지 않다 — 넘긴 필드만 직렬화한 것이다.
    scenario_text: str


def scenario_fields(
    name: str,
    *,
    arrangement: str | None = None,
    ownership_or_operation_transferred: bool = False,
    metering_separated: bool = False,
    assumption_overrides: object | None = None,
    household_count: str | int | None = None,
    heatpump_load_annual_kwh: str | float | None = None,
    ev_load_annual_kwh: str | float | None = None,
    appliance_load_season_shares: Mapping[str, str] | None = None,
    dr_shiftable_share_pct: str | float | None = None,
) -> dict[str, Any]:
    """골든 시나리오 + 화면이 고른 것 → 넘길 매핑.

    ⚠⚠ **`arrangement` 의 기본값을 여기 적지 않는다.** 안 골랐으면 필드를
    **넣지 않고**, 그러면 `resolve_baseline_arrangement` 가
    `DEFAULT_BASELINE_ARRANGEMENT` 로 답한다. 여기 리터럴을 두면 기본값이 두
    곳에 살고, 한쪽만 고쳐지는 날 같은 요청이 층마다 다른 갈래로 돌면서
    **아무 예외도 나지 않는다.**

    ⚠ **ⓒ 전제가 둘 다 거짓이면 `pool_metering` 키도 넣지 않는다.**
    「적지 않았다」와 「둘 다 아니라고 적었다」는 **다른 진술**이며
    (`resolve_pool_metering` 독스트링), 하나라도 참이면 두 필드를 **함께**
    적는다 — 둘은 함께 서야 성립하는 한 조건이다.

    ⚠ 선언의 필드 이름을 손으로 적지 않는다 — `PoolMeteringDeclaration` 을
    지어 `dataclasses.asdict()` 로 편다. 손으로 적으면 자료형이 필드를 늘리는
    날 화면이 그 필드를 영영 넘기지 못한다.

    ## ★★★ `assumption_overrides` — **안 주면 필드를 넣지 않는다**

    `None` 이면 키를 넣지 않으므로 `apply_scenario_overrides` 가 대장을
    **같은 객체로** 돌려주고(그 함수의 ★★★ 절), 기본값 실행은 이 통로가 생기기
    전과 같은 경로를 돈다 — **결론축(무보조 `npv`)의 불변은 그 동일성이
    근거다.** 빈 목록(`[]`)과 `None` 을 같게 다루지 않는 이유도 같다: 「적지
    않았다」와 「하나도 없다고 적었다」는 다른 진술이며, ⓒ 전제 둘이 이미 같은
    규약을 따른다.

    ⚠ **여기서 검증하지 않는다.** 모양·키를 판정하는 자리는
    `resolve_assumption_overrides` 하나이며(그 함수가 `build_case_report` 안에서
    불린다), 여기서 미리 걸러 내면 거부 문면이 두 곳에 생긴다 — 이 파일 머리말의
    ★★★ 가 갈래·ⓒ 전제에 대해 적은 것과 같은 판단이다.

    ## ★★ `household_count` — **빈 칸이면 필드를 넣지 않는다** (R64/WP-1)

    폼의 빈 칸(`""`)과 `None` 이 *「가구 수를 적지 않았다」*이고, 그때 필드가
    시나리오에 실리지 않아 `build_case_report` 가 `None` 으로 읽는다 — 러너는
    **가구 한 호 기준**으로 돌고 결과는 이 통로가 생기기 전과 같다.

    ⚠ **여기서 정수로 바꾸지 않는다.** 문면 그대로 실어 보내고 판정은
    `core/casegrid/household_scale.py::resolve_household_count` 하나가 한다 —
    위 갈래·오버라이드와 같은 자리이며, 여기서 미리 바꾸면 「40.5호」 같은
    입력의 거부 문면이 두 곳에 생긴다.

    ## ★★ 기기 부하 둘 — **빈 칸이면 필드를 넣지 않는다** (R64/WP-2)

    히트펌프·전기차 연간 소비전력량도 같은 규약이다. 빈 칸(`""`)과 `None` 이
    *「그 기기를 적지 않았다」*이고, 그때 필드가 시나리오에 실리지 않아
    `build_case_report` 가 `None` 으로 읽는다 — 더해지는 값은 0 이고 결과는
    이 통로가 생기기 전과 같다. 판정은
    `core/casegrid/appliance_load.py::resolve_appliance_load` 하나가 한다.

    ⚠ **둘을 하나로 합치지 않는다.** 러너가 받는 것은 합계 하나지만 화면과
    산출물은 기기별로 갈라야 한다 — 합치면 사용자가 따로 바꾸지 못한다.

    ## ★★ 부하의 **형상** 둘 — 통로가 서로 다르다 (R64/WP-WEB ⓐⓑ)

    ⓑ **계절 몫**(`appliance_load_season_shares`)은 위 기기 부하와 **같은
    규약**이다: 안 주면 필드를 넣지 않고, 그때 냉난방이 기본 부하와 같은 계절
    몫으로 돌아 출력이 이 통로가 생기기 전과 원소 하나까지 같다. ⚠ **빈 칸을
    버리지 않고 그대로 싣는다** — 전부 빈 것과 일부만 적은 것을 가르는 자리는
    `resolve_appliance_season_shares` 하나다.

    ⓐ **옮길 비율**(`dr_shiftable_share_pct`)은 다르다 — **대장이 값을 갖는
    항목**이므로 시나리오 필드를 새로 세우지 않고 **오버라이드 한 줄**로
    얹는다(`_overrides_with_shift`). 그 판단의 정본은
    `core/report/case_report.py` 의 ★★★ 절과 `.orch/R64/result_7.md` 판정 ㉳ 다.
    """
    available = golden_scenario_names()
    if name not in available:
        raise KeyError(
            f"시나리오 {name!r} 이(가) 없습니다. 사용할 수 있는 것: "
            f"{', '.join(available)}"
        )
    path = _GOLDEN_DIR / f"{name}.yaml"
    fields: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if arrangement:
        fields[_ARRANGEMENT_FIELD] = arrangement
    if ownership_or_operation_transferred or metering_separated:
        fields[POOL_METERING_FIELD] = dataclasses.asdict(
            PoolMeteringDeclaration(
                ownership_or_operation_transferred=ownership_or_operation_transferred,
                metering_separated=metering_separated,
            )
        )
    overrides = _overrides_with_shift(assumption_overrides, dr_shiftable_share_pct)
    if overrides is not None:
        fields[ASSUMPTION_OVERRIDES_FIELD] = overrides
    if appliance_load_season_shares is not None:
        fields[APPLIANCE_SEASON_SHARE_FIELD] = dict(appliance_load_season_shares)
    if household_count is not None and household_count != "":
        fields[HOUSEHOLD_COUNT_FIELD] = household_count
    for field, given in (
        (HEATPUMP_LOAD_FIELD, heatpump_load_annual_kwh),
        (EV_LOAD_FIELD, ev_load_annual_kwh),
    ):
        if given is not None and given != "":
            fields[field] = given
    return fields


def _overrides_with_shift(
    given: object | None, share_pct: str | float | None
) -> object | None:
    """ⓐ 비율을 **오버라이드 한 줄로** 얹는다 — 없으면 받은 것을 그대로.

    ## ⚠⚠ 왜 여기서 수로 낮추는가 — **오버라이드 통로가 형을 맞대기 때문이다**

    `resolve_assumption_overrides` 는 **키가 아니라 「키 → 값」**을 보고 대장
    값의 형 갈래와 맞댄다(그 함수의 ⚠⚠ 절 · R1 D-4). 대장은 이 항목을 수
    (`10`)로 갖는데 폼이 보내는 것은 글자(`"20"`)이므로, 글자를 그대로 실으면
    **정당한 입력이 「형이 다르다」로 거부된다.**

    ⚠ **그래도 판정은 한 자리다** — 여기서 형을 판정하지 않고
    `resolve_shiftable_share`(0~100 · `nan`·`bool` 거부 · 빈 칸은 미지정)를
    **부른다.** 그 함수가 이 비율의 유일한 판정자이며, 3요소 거부도 그 함수가
    짓는다(`core/casegrid/load_shift.py::_rejected`).

    ## ⚠ 빈 칸은 **0 이 아니다**

    `None` 을 돌려받으면 줄을 얹지 않고, 그러면 대장 값(지금 10)이 쓰인다.
    0 을 밀어 넣으면 *「옮기지 않는다」* 라는 **다른 실행**이 되어 결론축이
    움직인다 — 그 구별을 `tests/app/test_ui_load_shape.py` 가 잰다.

    ## ⚠ 같은 키가 두 번 실리면 **거부된다** (조용하지 않다)

    받은 오버라이드 목록에 이미 `load.dr_shiftable_share` 가 있으면 줄이 둘이
    되고, `resolve_assumption_overrides` 가 *「같은 대장 키를 두 번
    적었습니다」* 로 거부한다 — 뒤가 이기며 앞이 사라지는 것을 그 함수가
    막는다. 그래서 여기서 겹침을 판정하지 않는다(같은 사실을 두 곳에서 보면
    한쪽만 고쳐지는 날이 온다).

    ⚠ 받은 것이 **목록이 아니면 얹지 않고 그대로 보낸다.** 그 모양은
    `resolve_assumption_overrides` 가 *「목록이 아닙니다」* 로 거부하므로
    실행이 조용히 성공하는 일은 없다 — 여기서 모양을 고쳐 주면 거부가 사라지고
    사용자는 자기가 적은 오버라이드가 어디로 갔는지 알 수 없게 된다.
    """
    share = resolve_shiftable_share(share_pct)
    if share is None:
        return given
    row = {
        "key": DR_SHIFTABLE_SHARE_LEDGER_KEY,
        "value": share,
        "reason": SHIFTABLE_SHARE_OVERRIDE_REASON,
    }
    if given is None:
        return [row]
    if isinstance(given, Sequence) and not isinstance(given, (str, bytes)):
        return [*given, row]
    return given


def run_ui_case(
    name: str,
    *,
    arrangement: str | None = None,
    ownership_or_operation_transferred: bool = False,
    metering_separated: bool = False,
    assumption_overrides: object | None = None,
    household_count: str | int | None = None,
    heatpump_load_annual_kwh: str | float | None = None,
    ev_load_annual_kwh: str | float | None = None,
    appliance_load_season_shares: Mapping[str, str] | None = None,
    dr_shiftable_share_pct: str | float | None = None,
) -> UiRun:
    """화면이 고른 것으로 **한 번 돌린다.**

    ⚠ **갈래 문면을 여기서 검증하지 않는다.** 모르는 문면은 매핑에 그대로
    실려 `resolve_baseline_arrangement` 가 `ValidationError` 로 거부하고, ⓒ 를
    전제 없이 고르면 `get_baseline_branch` 가 `DV-15` 로 거부한다 — 판정하는
    자리를 하나로 두는 것이 이 파일 머리말의 ★★★ 이다. 여기서 미리 걸러
    내면 거부 문면이 두 곳에 생기고, 그때 둘이 갈려도 아무 검사도 걸리지
    않는다.

    ## ★★ 같은 입력을 **두 번 세우지 않는다** (R64/WP-PERF)

    리포트를 세우는 일은 `app/services/ui_run_cache.py::case_report_for` 가
    맡는다. 화면 하나(`/ui/run`)가 이 함수를 **아홉 번** 부르기 때문이다 —
    HTML 이 한 번, 그 안의 `<figure data-chart=…>` 여덟 장이 각각
    `/ui/chart/<태그>.png` 로 따로 와서 한 번씩. 실측으로 그 아홉이 42초였고,
    e2e 의 30초 예산을 이미 넘겨 **로컬에서 화면을 판정할 수 없는 상태**였다.

    ⚠ **절차는 한 글자도 바뀌지 않았다.** 임시 디렉터리에 yaml 을 쓰고 그
    경로로 `build_case_report` 를 부르는 것은 그 파일이 그대로 한다 — 옮겨
    간 것은 *그 절차를 몇 번 도는가* 뿐이다. 임시 파일 이름을 골든과 같게
    두는 이유(그 함수가 시나리오 이름이 매핑에 없을 때 `scenario_path.stem`
    을 표제로 쓴다)도 옮겨 간 자리에 함께 적혀 있다.

    ⚠ **`scenario_text` 는 계속 이 함수가 짓는다.** 캐시가 그것을 대신 지으면
    화면이 그리는 문면이 *캐시에 든 옛 실행의 것*이 될 수 있다.
    """
    fields = scenario_fields(
        name,
        arrangement=arrangement,
        ownership_or_operation_transferred=ownership_or_operation_transferred,
        metering_separated=metering_separated,
        assumption_overrides=assumption_overrides,
        household_count=household_count,
        heatpump_load_annual_kwh=heatpump_load_annual_kwh,
        ev_load_annual_kwh=ev_load_annual_kwh,
        appliance_load_season_shares=appliance_load_season_shares,
        dr_shiftable_share_pct=dr_shiftable_share_pct,
    )
    text = yaml.safe_dump(fields, allow_unicode=True, sort_keys=False)
    report = case_report_for(name, fields, text, assumptions_path=_ASSUMPTIONS)
    return UiRun(report=report, scenario_text=text)
