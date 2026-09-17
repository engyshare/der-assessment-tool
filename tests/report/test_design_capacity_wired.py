"""**설계 변수(PV·ESS 용량) 오버라이드가 리포트까지 간다** — R71/WP-4.

`.orch/R71/result_3.md` 가 실측한 대로, `pv_capacity_kw`·`ess_capacity_kwh` 는
`core/casegrid/ledger_levels.py::_DESIGN_VARS` 의 케이스 변수일 뿐 대장 항목이
아니어서 사용자가 흔들 통로가 저장소에 전혀 없었다. 이 파일은 새로 연 통로
(`design_capacity` 시나리오 필드)가 실제로:

    ① `base` 값을 바꾸고 실행에 반영되는가(결론축이 움직이는가)
    ② `low`·`high` 탐색 구간은 그대로 두는가(`tests/casegrid/
       test_ledger_levels.py` 가 함수 단위로 이미 잰 것의 **배선** 확인)
    ③ 모르는 키·`ess_power_kw` 는 조용히 무시되지 않고 거부되는가

를 재는지 확인한다 — `tests/report/test_household_count_wired.py` 와 같은
모양이다(그 파일이 「시나리오 필드 하나가 어떻게 배선됐는지」의 템플릿이라고
`.orch/R71/WP-4.md` §1 이 지목했다).

## ⚠ 「안 준 실행이 종전과 같다」는 여기서 재지 않는다

그 동일성의 정본은 골든 회귀(`tests/golden/test_regression_scenarios.py`)와
`scripts/verify_ladder.py check --deep` 다 — 골든 셋에 `design_capacity` 필드가
없으므로 그 회귀가 통째로 이 축의 불변을 잰다. 여기서는 **필드를 준 실행**만
본다.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from core.casegrid.ledger_levels import DESIGN_CAPACITY_FIELD
from core.contracts.validation import ValidationError
from core.report.case_influences import CONCLUSION_METRIC
from core.report.case_report import CaseReport, build_case_report

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"


def _report(design_capacity: object | None = None) -> CaseReport:
    """골든 시나리오 + `design_capacity` → 리포트 하나.

    ⚠ **골든 픽스처를 고치지 않는다** — `test_household_count_wired.py::
    _report` 와 같은 모양으로 `tempfile` 안에만 쓴다.
    """
    fields: dict[str, Any] = yaml.safe_load(_GOLDEN.read_text(encoding="utf-8")) or {}
    if design_capacity is not None:
        fields[DESIGN_CAPACITY_FIELD] = design_capacity
    with tempfile.TemporaryDirectory() as workspace:
        path = Path(workspace) / _GOLDEN.name
        path.write_text(
            yaml.safe_dump(fields, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return build_case_report(path, assumptions_path=_ASSUMPTIONS)


def test_overriding_pv_capacity_moves_the_conclusion() -> None:
    """★★★ PV 용량을 바꾸면 **결론축이 실제로 움직인다.**

    이 단언이 없으면 아래 검사들은 *「필드를 나르기만 하고 계산에 안 쓴다」*
    로도 통과한다 — `test_household_count_wired.py::
    test_the_body_runs_on_the_bigger_site` 와 같은 이유로 두는 방어선이다.
    """
    baseline = float(_report().metrics[CONCLUSION_METRIC])
    overridden = float(
        _report({"pv_capacity_kw": 120.0}).metrics[CONCLUSION_METRIC]
    )
    assert overridden != pytest.approx(baseline, abs=1.0), (
        f"pv_capacity_kw 를 120.0(한 호분)으로 바꿔도 결론축이 {baseline:,.0f}원 "
        "그대로다 — design_capacity 가 계산에 들어가지 않았다"
    )


def test_overriding_ess_capacity_moves_the_conclusion() -> None:
    """★★★ ESS 용량을 바꿔도 **결론축이 실제로 움직인다.**"""
    baseline = float(_report().metrics[CONCLUSION_METRIC])
    overridden = float(
        _report({"ess_capacity_kwh": 400.0}).metrics[CONCLUSION_METRIC]
    )
    assert overridden != pytest.approx(baseline, abs=1.0), (
        f"ess_capacity_kwh 를 400.0(한 호분)으로 바꿔도 결론축이 "
        f"{baseline:,.0f}원 그대로다 — design_capacity 가 계산에 들어가지 않았다"
    )


def test_a_partial_override_only_touches_the_key_it_names() -> None:
    """★★ **키 단위 부분 지정** — PV 만 지정한 실행과 「PV+ESS 기본값 명시」가 같다.

    all-or-nothing 이면 이 둘이 달라진다(한쪽은 ESS 도 새로 굳고, 다른 쪽은
    ESS 가 대장 기본값으로 남는다는 차이가 없어야 한다 — 부분 지정 자체가
    「나머지는 기본값」이라는 뜻이므로).
    """
    pv_only = float(_report({"pv_capacity_kw": 90.0}).metrics[CONCLUSION_METRIC])
    pv_and_default_ess = float(
        _report({"pv_capacity_kw": 90.0, "ess_capacity_kwh": 10.0}).metrics[
            CONCLUSION_METRIC
        ]
    )
    assert pv_only == pytest.approx(pv_and_default_ess, abs=1.0), (
        "pv_capacity_kw 만 준 실행이 ess_capacity_kwh 의 대장 기본값(10.0, 한 "
        "호분)을 명시로 준 실행과 다르다 — 부분 지정이 다른 키에도 번졌다"
    )


def test_an_unknown_key_is_refused() -> None:
    """모르는 키는 조용히 무시되지 않고 **3요소로** 거부된다 (`NFR-303`)."""
    with pytest.raises(ValidationError, match="battery_capacity_kw"):
        _report({"battery_capacity_kw": 5.0})


def test_ess_power_kw_is_refused_as_not_yet_wired() -> None:
    """★ **ESS 정격출력은 이 라운드에서 거부된다** — 조용히 무시하지 않는다.

    `core/casegrid/seasonal_dispatch.py` 가 `NFR-206` 코드 줄 상한(500)에
    정확히 닿아 있어(`.orch/R71/result_4.md` §하지 않은 것) 이 라운드는 그
    통로를 배선하지 않았다. 값을 조용히 무시하면 「사용자가 적은 값이 안
    먹는다」가 되므로, 무시 대신 거부한다.
    """
    with pytest.raises(ValidationError, match="ess_power_kw"):
        _report({"ess_power_kw": 100.0})
