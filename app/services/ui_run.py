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

⚠ **골든 픽스처를 고치지 않는다.** 읽기만 하고, 쓰는 곳은
`tempfile.TemporaryDirectory()` 안이다 — 요청이 끝나면 지워진다.
"""
from __future__ import annotations

import dataclasses
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.assumption.scenario_overrides import ASSUMPTION_OVERRIDES_FIELD
from core.cba.baseline import POOL_METERING_FIELD, PoolMeteringDeclaration
from core.report.case_report import CaseReport, build_case_report

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
    if assumption_overrides is not None:
        fields[ASSUMPTION_OVERRIDES_FIELD] = assumption_overrides
    return fields


def run_ui_case(
    name: str,
    *,
    arrangement: str | None = None,
    ownership_or_operation_transferred: bool = False,
    metering_separated: bool = False,
    assumption_overrides: object | None = None,
) -> UiRun:
    """화면이 고른 것으로 **한 번 돌린다.**

    ⚠ **갈래 문면을 여기서 검증하지 않는다.** 모르는 문면은 매핑에 그대로
    실려 `resolve_baseline_arrangement` 가 `ValidationError` 로 거부하고, ⓒ 를
    전제 없이 고르면 `get_baseline_branch` 가 `DV-15` 로 거부한다 — 판정하는
    자리를 하나로 두는 것이 이 파일 머리말의 ★★★ 이다. 여기서 미리 걸러
    내면 거부 문면이 두 곳에 생기고, 그때 둘이 갈려도 아무 검사도 걸리지
    않는다.

    ⚠ 임시 파일 이름을 골든과 같게 두는 이유: `build_case_report` 는 시나리오
    이름이 매핑에 없을 때 `scenario_path.stem` 을 표제로 쓴다. 임의의 이름을
    두면 리포트 표제가 실행마다 달라진다.
    """
    fields = scenario_fields(
        name,
        arrangement=arrangement,
        ownership_or_operation_transferred=ownership_or_operation_transferred,
        metering_separated=metering_separated,
        assumption_overrides=assumption_overrides,
    )
    text = yaml.safe_dump(fields, allow_unicode=True, sort_keys=False)
    with tempfile.TemporaryDirectory() as workspace:
        path = Path(workspace) / f"{name}.yaml"
        path.write_text(text, encoding="utf-8")
        report = build_case_report(path, assumptions_path=_ASSUMPTIONS)
    return UiRun(report=report, scenario_text=text)
