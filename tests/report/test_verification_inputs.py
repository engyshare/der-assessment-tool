"""검증 보고서에 **빠져 있던 다섯 자리**가 실제로 실렸는가 (R64/WP-TXT).

## 이 파일이 붙드는 것

사용자 요구 여섯(`docs/decisions-2026-09-06-R64.md` §0) 중 검증 보고서
379줄이 **말하지 않던** 다섯이다. 착수 실측: 「히트펌프」·「전기차」·
「적정」·「역산」·「미반영」이 **0건**이었고 계절은 낱말 하나뿐이었다.

    요구 1 가구 수      요구 2 히트펌프·전기차·「AI 가전」
    요구 3·6 계절별 운전  요구 4 적정 용량 역산      미반영 항목

★★★ **「문자열이 비어 있지 않다」로 재지 않는다.** 항목마다 따로 잰다 —
한 낱말이라도 빠지면 그 줄만 빨간불이 되어야 *무엇이* 사라졌는지 알 수 있다.

## ⚠ CLI 를 지나서 잰다

`scripts/dump_verification.py` 를 통과해 **파일로 뽑은** 문면을 본다.
렌더러 함수만 직접 부르면 CLI 배선이 끊겨도 초록불이다 —
`tests/report/test_verification.py` 머리말이 같은 자리에서 같은 판정을 적었고,
`status.md` 의 함정 「검사가 배포 코드가 부르지 않는 함수를 직접 불러
통과한다」가 그 형태다.

⚠ **`@pytest.mark.req(...)` 를 달지 않았다.** spec 을 훑어 이 산출물(검증
보고서)에 대응하는 수용기준을 찾지 못했다 — `tests/report/test_verification.py`
가 같은 사유로 마커를 달지 않은 전례를 그대로 따른다. 맞지 않는 조항을 달면
`docs/traceability.md` 에 거짓 인용이 실린다.
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.services.verify_steps import STAGE_COUNT, split_stages
from core.casegrid.appliance_load import (
    APPLIANCE_LOAD_UNIT,
    APPLIANCE_LOAD_UNSPECIFIED,
    APPLIANCE_SEASON_SHARE_FIELD,
    APPLIANCE_SEASON_SHARE_UNSPECIFIED,
    EV_LOAD_FIELD,
    EV_LOAD_LEDGER_KEY,
    EV_LOAD_TITLE,
    HEATPUMP_LOAD_FIELD,
    HEATPUMP_LOAD_LEDGER_KEY,
    HEATPUMP_LOAD_TITLE,
)
from core.casegrid.household_scale import (
    HOUSEHOLD_COUNT_FIELD,
    HOUSEHOLD_COUNT_LEDGER_KEY,
    HOUSEHOLD_COUNT_UNSPECIFIED,
)
from core.casegrid.ledger_levels import LEVEL_NAMES
from core.casegrid.profiles import load_daily_shapes
from core.report.capacity import (
    ECONOMIC_SENSITIVITY_TITLE,
    binding_constraint_text,
)
from core.report.case_report import CaseReport, build_case_report
from core.report.dispatch_notes import (
    DEMAND_LABEL,
    NO_APPLIED_ALLOCATION,
    NO_OPERATING_MODE,
)
from core.report.ess_sizing_section import (
    ADOPTED_HEAD,
    ADOPTED_TERM,
    CAPACITY_KIND_APPLIED,
    CAPACITY_KIND_DIAGNOSTIC,
    CAPACITY_KIND_RUNNING,
    PER_HOUSEHOLD_HEAD,
    PER_HOUSEHOLD_SCALED,
    SELF_SUFFICIENT_HEAD,
    adopted_value_note,
    binding_season,
    ess_daily_sizing_section,
    relaxation_reach_note,
    within_range_head,
)
from core.report.verification import render_verification_markdown
from core.report.verification_dispatch import dispatch_note_rows
from core.report.verification_inputs import (
    ESTATE_LOAD_UNIT,
    HOUSEHOLD_LOAD_LEDGER_KEY,
    estate_load_kwh,
    execution_input_lines,
    household_total_load_kwh,
    run_used_values,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"

#: 시험용 기기 부하. 참고자료의 값을 박지 않는 사유는
#: `tests/casegrid/test_appliance_load.py::_HEATPUMP` 가 갖는다.
_HEATPUMP = 900.0
_EV = 600.0
#: 시험용 가구 수 — **2 호다.** 3 호부터는 낮에도 부하가 발전을 넘어
#: 태양광 잉여가 사라지고, 그러면 이 골든 구성의 ESS(충전원 = 태양광 잉여)가
#: `ValidationError` 로 거부한다(실측 2026-09-06: 3·4·5·8 호 모두 거부).
#: ⚠ 그 거부는 **결함이 아니라 옳은 판정**이므로 여기서 큰 수를 우겨 넣지
#: 않는다 — 이 검사가 재는 것은 「가구 수가 산출물에 실리는가」 하나다.
_HOUSEHOLDS = 2


def _cli():
    """`scripts/` 는 패키지가 아니므로 경로로 불러온다.

    `tests/ci/test_ci_gates.py::_script` 와 같은 통로다 — 거기 머리말이
    `sys.modules` 에 먼저 등록해야 하는 사유를 갖는다.
    """
    import importlib.util

    name = "_wp_txt_dump_verification"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, _REPO_ROOT / "scripts" / "dump_verification.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _scenario_file(workspace: Path, **fields_given: object) -> Path:
    """골든 시나리오 + 준 필드 → **임시** 시나리오 파일.

    ⚠ **골든 픽스처를 고치지 않는다** — 읽기만 하고 쓰는 곳은 임시 디렉터리
    안이다(`tests/report/test_appliance_load_wired.py::_report` 와 같은 모양).
    """
    fields: dict[str, Any] = yaml.safe_load(_GOLDEN.read_text(encoding="utf-8")) or {}
    fields.update(fields_given)
    path = workspace / _GOLDEN.name
    path.write_text(
        yaml.safe_dump(fields, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


def _blocked_ledger_text() -> str:
    """★ 가구 수·기기 부하를 **아무 통로도 갖지 않는 대장** (R65/WP-2c).

    R65 가 그 셋을 `track: blocked` → 값 있음으로 세우면서 *「안 적은 실행」*
    의 뜻이 달라졌다 — 시나리오에 안 적어도 **대장이 답한다.** 「미지정」 갈래를
    재려면 그 항목들이 답하지 않는 대장이 있어야 하고, 이 함수가 R65 이전과
    같은 모양으로 되돌린 사본을 만든다.

    ⛔ `docs/assumptions.yaml` 을 고치는 것이 아니다 — 사본은 임시 디렉터리
    안에서만 산다. ⚠ 값을 지어내지 않는다 — 지우는 것뿐이다.
    """
    doc = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))
    for item in doc["assumptions"]:
        if item.get("key") in {
            HOUSEHOLD_COUNT_LEDGER_KEY,
            HEATPUMP_LOAD_LEDGER_KEY,
            EV_LOAD_LEDGER_KEY,
        }:
            item["track"] = "blocked"
            item["value"] = None
            item["sensitivity"] = None
    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)


def _dumped(
    tmp_path: Path, *, ledger_answers: bool = True, **fields_given: object
) -> str:
    """CLI 를 지나 **파일로 뽑은** 검증 보고서 문면.

    `ledger_answers=False` 면 대장 통로까지 닫은 사본으로 돈다
    (`_blocked_ledger_text`).
    """
    with tempfile.TemporaryDirectory() as workspace:
        scenario = _scenario_file(Path(workspace), **fields_given)
        ledger = _ASSUMPTIONS
        if not ledger_answers:
            ledger = Path(workspace) / "assumptions.yaml"
            ledger.write_text(_blocked_ledger_text(), encoding="utf-8")
        target = tmp_path / "verification.md"
        rc = _cli().main(
            [
                "--scenario", str(scenario),
                "--assumptions", str(ledger),
                "--out", str(target),
            ]
        )
        assert rc == 0, f"CLI 가 rc={rc} 로 끝났다"
        assert target.is_file(), "CLI 가 rc=0 을 냈는데 파일이 없다"
        return target.read_text(encoding="utf-8")


def _report(**fields_given: object) -> CaseReport:
    with tempfile.TemporaryDirectory() as workspace:
        return build_case_report(
            _scenario_file(Path(workspace), **fields_given),
            assumptions_path=_ASSUMPTIONS,
        )


def _season_names() -> list[str]:
    """자산이 선언한 계절 이름 — **개수를 4로 박지 않는다**(자산 머리말 ★)."""
    return [season.name for season in load_daily_shapes().load.seasons]


def _season_heavy() -> dict[str, float]:
    """마지막 계절에 몰아 준 몫 — 합이 1 이다."""
    names = _season_names()
    rest = (1.0 - 0.7) / (len(names) - 1)
    return {name: (0.7 if name == names[-1] else rest) for name in names}


# ── ① 내용 — 빠졌던 다섯이 «항목마다» 실렸는가 ──────────────────────────────


def test_the_household_count_is_printed_as_a_number_when_given(tmp_path: Path) -> None:
    """요구 1 — 몇 호로 돌았는지 **수로** 읽힌다."""
    text = _dumped(tmp_path, **{HOUSEHOLD_COUNT_FIELD: _HOUSEHOLDS})
    assert f"{_HOUSEHOLDS:,}호" in text, "가구 수가 검증 보고서에 없다"
    assert HOUSEHOLD_COUNT_UNSPECIFIED not in text, (
        "가구 수를 적었는데 「미지정」이 함께 실렸다"
    )


def test_the_two_appliance_loads_each_have_their_own_name(tmp_path: Path) -> None:
    """요구 2 — 히트펌프와 전기차가 **각자 이름과 값**을 갖는다.

    뭉뚱그린 칸 하나면 검토자가 어느 기기가 얼마인지 알 수 없다.
    """
    text = _dumped(
        tmp_path, **{HEATPUMP_LOAD_FIELD: _HEATPUMP, EV_LOAD_FIELD: _EV}
    )
    assert HEATPUMP_LOAD_TITLE in text, "히트펌프 칸이 없다"
    assert EV_LOAD_TITLE in text, "전기차 칸이 없다"
    assert f"{_HEATPUMP:,.0f}" in text
    assert f"{_EV:,.0f}" in text


def test_the_shiftable_share_is_printed(tmp_path: Path) -> None:
    """요구 2 「AI 가전」 — 옮길 수 있는 부하 비율이 실린다.

    ⚠ 값을 여기 박지 않는다 — 대장이 정하는 수이므로 리포트에서 읽어 맞댄다.
    """
    text = _dumped(tmp_path)
    assert "AI 가전" in text, "「AI 가전」축이 검증 보고서에 없다"
    assert f"{_report().dr_shiftable_share_pct:,.1f}" in text


def test_the_capacity_review_and_the_two_back_calculations_are_printed(
    tmp_path: Path,
) -> None:
    """요구 4 — 「적정 용량」과 **역산 둘**(자립 PV · 하루 결손 ESS)이 실린다."""
    text = _dumped(tmp_path)
    assert "적정 용량 검토" in text, "적정 용량 검토가 검증 보고서에 없다"
    assert "역산" in text, "역산이 검증 보고서에 없다"
    report = _report()
    for finding in report.capacity_review:
        assert finding.label in text, f"설계 변수 {finding.label} 이 빠졌다"
    for point in report.self_sufficiency.points:
        assert point.source_label in text, f"자립 역산의 {point.source_label} 이 빠졌다"


# ── R67/WP-③ — **1가구를 먼저, 20호 확대를 그 뒤에** ─────────────────────
#
# 사용자 판정 `docs/decisions-2026-09-08-R67.md` §4-3: *「2단계는 1가구 적정
# 용량을 먼저 제시한 뒤 20가구 확대 구성을 설명한다. 진단값과 실제 실행값을
# 구분한다」*. 착수 실측: ② 표가 **20호 값만** 실어 심의자가 「가구 하나에
# 얼마가 필요한가」를 읽으려면 **표의 수를 20으로 나눠야** 했다.


def _capacity_section(text: str) -> str:
    """② 표가 있는 구획만 — 다른 절의 낱말이 이 판정에 섞이지 않게 자른다."""
    head = "② **수요 기반 적정 용량**"
    start = text.index(head)
    return text[start : text.index("③ **수요 기반 적정 용량**", start)]


def test_the_self_sufficiency_table_puts_the_single_household_before_the_estate(
    tmp_path: Path,
) -> None:
    """★★★ ② 표에 **1가구 열이 있고 20호 열보다 «앞에» 선다** (판정 §4-3).

    ⚠ **「있다」로 재지 않는다 — «순서»를 잰다.** 사용자 문면이 *「먼저
    제시한 뒤」* 이므로 두 열이 다 있어도 뒤에 서면 요구가 만족되지 않는다.
    표를 훑는 눈은 왼쪽부터 읽고, 그 순서가 곧 *무엇이 답인가* 로 읽힌다.

    ⚠ 가구 수를 리터럴로 적지 않는다 — 이 실행이 몇 호인지는 시나리오·대장이
    정하므로 `report` 에서 읽어 열 이름을 짓는다.
    """
    text = _dumped(tmp_path)
    report = _report()
    sizing = report.self_sufficiency
    assert sizing.scales_to_estate, (
        f"이 골든이 단지로 확대되지 않았다(가구 수 {sizing.household_count}) — "
        "두 열을 견줄 자리가 없다. 확대 없는 실행의 갈래는 아래 "
        "`test_a_single_household_run_folds_the_estate_columns` 가 잰다"
    )
    section = _capacity_section(text)

    household_head, estate_head = "연간 부하(1가구)", f"연간 부하({sizing.estate_label})"
    assert household_head in section, (
        f"② 표에 「{household_head}」 열이 없다 — 심의자가 가구 하나에 얼마가 "
        "필요한지를 표의 수를 나눠서 얻어야 한다"
    )
    assert estate_head in section, f"② 표에서 「{estate_head}」 열이 사라졌다"
    assert section.index(household_head) < section.index(estate_head), (
        f"「{estate_head}」 가 「{household_head}」 보다 앞에 선다 — 사용자 문면은 "
        "*「1가구 적정 용량을 먼저 제시한 뒤 20가구 확대 구성을 설명한다」* 다"
    )
    # ★ 필요 용량 쪽도 같은 순서다 — 부하만 앞에 오고 용량이 뒤면 표가 갈린다.
    assert section.index("필요 태양광(1가구)") < section.index(
        f"필요 태양광({sizing.estate_label})"
    ), "부하는 1가구가 먼저인데 필요 태양광은 단지가 먼저다 — 두 쌍이 갈렸다"


def test_the_single_household_capacity_times_the_count_is_the_estate_capacity(
    tmp_path: Path,
) -> None:
    """★★★ **1가구 × 가구 수 = 20호 값** — 두 벌이 같은 사업을 말한다.

    ⚠⚠ **이 단언이 없으면 1가구 열이 «아무 수나» 실어도 통과한다.** 두 벌은
    같은 산식(`required_pv_capacity_kw`)을 각자의 부하로 돈 결과이므로 그
    산식이 부하에 **비례**하는 한 이 항등식이 성립한다 — 깨지면 한쪽이 다른
    부하를 쓴 것이다.

    ⚠ **리터럴을 쓰지 않는다** — 가구 수도 두 벌의 수도 `report` 에서 읽는다
    (지시문 §4-2). 대장 부하가 바뀌어도 이 검사가 재는 성질은 그대로다.

    ⚠ 산출물에도 **두 수가 다 인쇄돼 있는지**를 함께 본다 — 자료구조만 맞고
    표가 한쪽을 싣지 않으면 심의자는 여전히 못 읽는다.
    """
    report = _report()
    sizing = report.self_sufficiency
    count = sizing.household_count
    assert count is not None and count > 1, (
        f"이 골든의 가구 수가 {count} 다 — 배수를 잴 자리가 없다"
    )
    section = _capacity_section(_dumped(tmp_path))

    for point in sizing.points:
        assert point.household_load_kwh * count == pytest.approx(
            point.annual_load_kwh
        ), (
            f"{point.source_label}: 1가구 부하 {point.household_load_kwh:,.4f} × "  # noqa: RUF001
            f"{count}호 가 단지 부하 {point.annual_load_kwh:,.4f} 와 다르다"
        )
        assert point.household_capacity_kw * count == pytest.approx(
            point.required_capacity_kw
        ), (
            f"{point.source_label}: 1가구 필요 용량 "
            f"{point.household_capacity_kw:,.6f}kW × {count}호 가 단지 값 "  # noqa: RUF001
            f"{point.required_capacity_kw:,.6f}kW 와 다르다 — 두 벌이 다른 부하로 "
            "돌았다"
        )
        assert f"{point.household_capacity_kw:,.2f}kW" in section, (
            f"{point.source_label}: 1가구 필요 용량이 ② 표에 인쇄되지 않았다"
        )
        assert f"{point.required_capacity_kw:,.2f}kW" in section, (
            f"{point.source_label}: 단지 필요 용량이 ② 표에서 사라졌다"
        )


def test_a_single_household_run_folds_the_estate_columns(tmp_path: Path) -> None:
    """★★ 가구 한 호 실행에서는 **같은 수를 두 번 인쇄하지 않는다.**

    두 벌이 같은 수인데 열이 둘이면 검토자는 *「둘이 다른 것을 재는가」* 로
    읽는다. ⇒ 단지 열을 **접고** 「확대 없음」을 글자로 적는다 — 접었다는
    사실이 없으면 단지 값을 **싣지 못한** 것과 구별되지 않는다.
    """
    section = _capacity_section(_dumped(tmp_path, **{HOUSEHOLD_COUNT_FIELD: 1}))
    assert "연간 부하(1가구)" in section, "1가구 열은 접지 않는다"
    assert "연간 부하(1호)" not in section, (
        "가구 한 호 실행인데 단지 열이 그대로 섰다 — 같은 수가 두 번 인쇄된다"
    )
    assert "단지 확대 — **없다**" in section, (
        "단지 열을 접었는데 그 사실이 표 아래에 없다 — 「싣지 못했다」와 "
        "구별되지 않는다"
    )


def test_the_section_head_separates_the_run_configuration_from_the_diagnosis(
    tmp_path: Path,
) -> None:
    """★★★ 절 머리가 **지금 도는 구성**을 역산값과 갈라 «수로» 적는다 (§4-3).

    *「진단값과 실제 실행값을 구분한다」* 는 낱말만으로 성립하지 않는다 —
    **지금 무엇으로 도는지가 수로 없으면** 검토자는 아래 역산값을 이 실행의
    구성으로 읽는다. 그 수는 설계 변수의 사용값과 배터리 정격출력이다.

    ⛔ **「채택」이라 적지 않는다** (판정 §4-4 *「적용 전이면 결과를 만들어 낸
    것처럼 표시하지 않는다」*). 실행 구성은 역산의 결과가 아니다.

    ⚠ 수를 리터럴로 적지 않는다 — `report` 에서 읽는다.
    """
    text = _dumped(tmp_path)
    report = _report()
    head = text[: text.index("① **" + ECONOMIC_SENSITIVITY_TITLE + "**")]

    assert "지금 도는 구성" in head, (
        "역산 표 위에 「지금 도는 구성」이 없다 — 진단값과 견줄 대상이 산출물에 "
        "없으면 검토자가 역산값을 실행 구성으로 읽는다"
    )
    for finding in report.capacity_review:
        assert f"{finding.used_value:g} {finding.unit}" in head, (
            f"{finding.label} 의 실행 사용값 {finding.used_value:g}"
            f"{finding.unit} 가 절 머리에 없다"
        )
    power_kw = report.ess_sizing.run_power_kw
    assert power_kw is not None, "이 골든에 배터리가 있는데 정격출력이 None 이다"
    assert f"{power_kw:g} kW" in head, (
        f"배터리 정격출력 {power_kw:g}kW 가 절 머리에 없다 — 용량만 적으면 "
        "출력 쪽 역산값(정격출력)과 견줄 실행값이 없다"
    )
    assert "역산의 결과가 아니다" in head, (
        "실행 구성이 역산의 결과가 아니라는 진술이 없다 — 그 줄이 없으면 "
        "「역산대로 세웠다」로 읽힌다"
    )


# ── R67/WP-③-fix — ③(ESS)의 1가구 열은 **환산이고, 표가 그렇게 말한다** ────
#
# ## 왜 ② 와 다르게 재는가
#
# ②(자립 PV)의 1가구 값은 산식을 **1호분 부하로 다시 돈** 것이고, ③의 1가구 값은
# 단지 값을 **나눈** 것이다. ③의 역산 입력이 **20호로 돈 운전의 스텝별 시계열**이라
# 1호분 운전이 저장소에 없기 때문이다(오케스트레이터 판정 R67/WP-③-fix §1 —
# *「지시가 틀렸다」*). ⇒ 나누는 것을 **허락받았고**, 대신 **그 성질을 표가 글자로
# 말해야** 한다. 아래 둘이 그 둘을 각각 붙든다.


def _ess_section(text: str) -> str:
    """③ 표가 있는 구획만 — 다른 절의 낱말이 이 판정에 섞이지 않게 자른다."""
    start = text.index("③ **수요 기반 적정 용량**")
    return text[start : text.index("- 점별 결론 축과", start)]


def test_the_ess_per_household_column_times_the_count_is_the_estate_value(
    tmp_path: Path,
) -> None:
    """★★★ ③ 표의 **1가구 값 × 가구 수 = 20호 값**(정확히).

    ⚠⚠ **이 단언이 없으면 그 열이 «아무 수나» 실어도 통과한다.** 환산이므로
    항등식이 **정확히** 성립해야 한다 — 어긋나면 나눈 분모가 가구 수가 아니다.

    ⚠ **리터럴을 쓰지 않는다** — 가구 수도 두 수도 `report` 에서 읽는다.
    ⚠ **채택값만 환산한다**(렌더러 독스트링 ⚠) — 완전 자립분은 견줌이라 단지 값
    하나로 족하고, 환산하면 열이 열셋이 되어 읽히지 않는다. 그래서 이 검사도
    채택값 두 칸만 잰다.
    """
    report = _report()
    count = report.household_count
    assert count is not None and count > 1, (
        f"이 골든의 가구 수가 {count} 다 — 환산을 잴 자리가 없다"
    )
    review = report.ess_sizing
    assert review.unmeasurable_reason is None, (
        f"이 골든에서 역산이 안 됐다 — {review.unmeasurable_reason}"
    )
    section = _ess_section(_dumped(tmp_path))

    for season in review.seasons:
        adopted = season.relaxed
        for value, unit in (
            (adopted.required_capacity_kwh, "kWh"),
            (adopted.required_power_kw, "kW"),
        ):
            printed = f"{value / count:,.2f}{unit}"
            assert printed in section, (
                f"{season.season_name}: 1가구 환산값 {printed} 가 ③ 표에 없다 — "
                f"단지 값 {value:,.2f}{unit} ÷ {count}호 다"
            )
            # ★ 단지 값도 함께 서 있어야 한다 — 환산값만 실으면 「무엇을 나눈
            #   수인가」가 표에서 사라진다.
            assert f"{value:,.2f}{unit}" in section, (
                f"{season.season_name}: 단지 채택값 {value:,.2f}{unit} 가 ③ 표에서 "
                "사라졌다 — 환산의 분자가 표에 없으면 1가구 열을 확인할 수 없다"
            )


def test_the_ess_per_household_column_says_it_is_a_conversion(
    tmp_path: Path,
) -> None:
    """★★★ 그 열이 **「환산」임을 표가 말한다** — 낱말·사유·근거·②와의 차이.

    ⚠⚠ **수만 맞으면 안 된다.** 환산값을 역산값과 같은 표 모양으로 실으면서
    성질을 적지 않으면, 다음 사람은 이 열을 **역산 결과로 읽는다** — 그것이
    오케스트레이터 판정 §2-2·§2-3 이 못 박은 자리다.

    ⚠ **낱말을 이 시험이 갖지 않는다** — `PER_HOUSEHOLD_SCALED` ·
    `PER_HOUSEHOLD_HEAD` 를 렌더러와 **나눠 갖는다**(지시문 §4-2). 리터럴로
    적으면 문면을 고치는 날 한쪽만 고쳐지고, 그때 이 시험은 **옛 낱말을 찾아
    초록불**이다.
    """
    section = _ess_section(_dumped(tmp_path))

    assert PER_HOUSEHOLD_HEAD in section, (
        f"③ 표의 열 이름에 「{PER_HOUSEHOLD_HEAD}」 가 없다 — 열 이름이 성질을 "
        "말하지 않으면 ②의 1가구 열과 같은 것으로 읽힌다"
    )
    assert PER_HOUSEHOLD_SCALED in section, (
        f"「{PER_HOUSEHOLD_SCALED}」 이라는 낱말이 ③ 표에 없다"
    )
    # ⓐ **왜** 환산인가 — 1호분 운전이 없다는 사실.
    assert "1호분 운전이 없다" in section, (
        "왜 환산인지가 표에 없다 — 「나눴다」만 적으면 그것이 게으름인지 "
        "불가피함인지 구별되지 않는다"
    )
    # ⓑ 환산이 **정당한 근거** — 실측 하나뿐이다.
    assert "20.0000" in section, (
        "환산의 근거(가구 수 1 로 따로 돌려 네 계절 전부 비 20.0000)가 표에 없다 — "
        "그 문장이 이 환산이 정당한 유일한 근거다"
    )
    # ⓒ ② 와 **성질이 다르다**는 것.
    assert "다시 돈" in section and "나눈" in section, (
        "②(다시 돈 값)와 ③(나눈 값)의 차이가 표에 없다 — 같은 표 모양이 두 "
        "성질을 숨긴다"
    )


def test_a_single_household_run_folds_the_ess_per_household_column(
    tmp_path: Path,
) -> None:
    """★★ 가구 한 호 실행에서는 ② 와 **같은 규칙**으로 열을 접는다 (§2-5)."""
    section = _ess_section(_dumped(tmp_path, **{HOUSEHOLD_COUNT_FIELD: 1}))
    assert PER_HOUSEHOLD_HEAD not in section, (
        "가구 한 호 실행인데 1가구 환산 열이 그대로 섰다 — 같은 수가 두 번 "
        "인쇄된다"
    )
    assert "1가구 열을 접었다" in section, (
        "열을 접었는데 그 사실이 표 아래에 없다 — 「싣지 못했다」와 구별되지 않는다"
    )


# ── R67/WP-N2 — ①표는 **경제성 민감도**이지 적정값을 정하는 표가 아니다 ─────
#
# 사용자가 산출물을 읽고 그 표를 반려했다 — *「적정용량 산정은 전력수요에 맞는
# 설비용량을 산출하는 것이고, 용량 범위 제한이 없어야 하며, 경제성으로 평가하는
# 것이 아님」*(`docs/decisions-2026-09-08-R67b.md` §1). 아래 둘이 그 판정을
# 산출물에서 붙든다.


def test_the_capacity_sweep_table_does_not_claim_to_decide_the_right_capacity(
    tmp_path: Path,
) -> None:
    """★★★ ①표에 **「적정값이 이 모델 안에서 정해지는가」 칸이 없다** (판정 §2-3).

    그 칸은 경제성 스윕이 적정용량을 정한다고 주장했다. 사용자 판정은 적정용량을
    **경제성으로 평가하지 않는다**고 정했으므로, 그 칸은 이 표가 질 물음이
    아니다. ⚠ **표를 없앤 것이 아니다** — 이름이 「경제성 민감도」로 서 있는지도
    함께 본다(민감도로서는 값이 있다).
    """
    text = _dumped(tmp_path)

    assert "적정값이 이 모델 안에서 정해지는가" not in text, (
        "①표가 여전히 「적정값이 이 모델 안에서 정해지는가」를 인쇄한다 — "
        "경제성 스윕이 적정용량을 정한다는 주장이며 사용자 판정 R67b §2-3 이 "
        "그것을 반려했다"
    )
    assert ECONOMIC_SENSITIVITY_TITLE in text, (
        f"①표가 자기 이름({ECONOMIC_SENSITIVITY_TITLE})을 말하지 않는다 — "
        "표를 지우라는 판정이 아니라 「무엇을 묻는 표인지 말하라」는 판정이다"
    )


def test_the_capacity_sweep_table_prints_the_constraint_that_bound_it(
    tmp_path: Path,
) -> None:
    """★★ ①표가 **「걸린 제약」**을 인쇄한다 — 「예 / 아니오」가 갈린 사유 (판정 §2-4).

    실측(골든 무보조): 태양광은 구간 하단 20 kW 점에서
    `ess.pv_surplus_profile_kwh` 에 걸려 `bounded` 가 참이었고 저장장치는
    걸리지 않아 거짓이었다 — 같은 조건의 두 자원이 「예 / 아니오」로 갈려
    인쇄되면 검토자는 그것을 결함으로 읽는다. **답이 틀린 것이 아니라 판정
    근거가 표에 없었다.**

    ⚠ **필드 이름을 이 파일에 베끼지 않는다** — 실행이 실제로 걸린
    `CapacityFinding.binding_fields` 를 읽어 대조한다. 베끼면 제약이 다른 자리로
    옮겨간 날 이 검사만 옛 이름을 기대한다.
    ⚠ **걸린 축이 없는 실행에서는 「없음」의 갈래를 본다** — 「없음」 한 말로
    뭉개면 *내부 최적점이 있어서 없는 것*과 *구간 끝까지 단조여서 없는 것*이
    구별되지 않고, 그 둘은 검토자에게 반대의 뜻이다.
    """
    text = _dumped(tmp_path)
    report = _report()

    assert "걸린 제약" in text, "①표에 「걸린 제약」 칸이 없다"
    bound = [f for f in report.capacity_review if f.binding_constraint is not None]
    assert bound, (
        "이 골든 실행에서 제약에 걸린 설계 변수가 0 건이다 — 이 검사가 "
        "아무것도 붙들지 않는다. 걸리는 구성으로 재야 한다"
    )
    for finding in bound:
        for field in finding.binding_fields:
            assert field in text, (
                f"{finding.label}: 거부 필드 {field!r} 가 ①표에 없다 — "
                "「예/아니오」가 갈린 사유가 여전히 화면에서 사라진다"
            )
    for finding in report.capacity_review:
        if finding.binding_constraint is None:
            assert binding_constraint_text(finding) in text, (
                f"{finding.label}: 제약이 없는 축의 「없음」 갈래가 표에 없다"
            )


def test_the_unreflected_items_are_printed_with_their_direction(
    tmp_path: Path,
) -> None:
    """미반영 — 항목과 **방향**이 함께 실린다.

    방향 없이 이름만 실으면 검토자가 그것을 한 방향의 여유로 읽는다.
    """
    text = _dumped(tmp_path)
    assert "미반영 항목" in text, "미반영 절이 검증 보고서에 없다"
    from core.report.unreflected import build_unreflected

    items = build_unreflected(_report())
    assert items, "픽스처 전제가 깨졌다 — 미반영 항목이 하나도 없다"
    for item in items:
        assert item.label in text, f"미반영 항목 {item.label} 이 빠졌다"
        assert item.direction in text


# ── ①-2 가구 수요 — 세 항목과 «이름이 다른» 두 합계 (R67/WP-2) ──────────────


def _general_load_kwh(report: CaseReport) -> float:
    """일반용 전력 — 리포트가 읽은 대장 행(이 절 검사들의 대조값)."""
    return next(
        float(row.value)
        for row in report.assumptions
        if row.key == HOUSEHOLD_LOAD_LEDGER_KEY
    )


def test_the_three_household_demand_items_are_each_printed(tmp_path: Path) -> None:
    """일반용·히트펌프·전기차가 **각각** 이름과 값으로 실린다 (판정 §4-2).

    합 하나로 뭉뚱그리면 어느 항목이 얼마인지 보고서가 말하지 않는다.
    값은 리포트에서 읽어 대조한다 — 참고자료의 수를 여기 박지 않는다.
    단계 수는 이 표의 행이 늘어도 그대로다(아래 ③ 과 같은 경계).
    """
    report = _report()
    text = _dumped(tmp_path)
    loads = report.appliance_loads
    assert loads.heatpump_kwh is not None and loads.ev_kwh is not None, (
        "픽스처 전제가 깨졌다 — 대장이 기기 부하에 답하지 않는다"
    )
    assert "| 일반용 전력 |" in text, "일반용 전력 행이 없다"
    assert f"{_general_load_kwh(report):,.0f}" in text, "일반용 전력의 값이 없다"
    assert HEATPUMP_LOAD_TITLE in text, "히트펌프 행이 없다"
    assert EV_LOAD_TITLE in text, "전기차 행이 없다"
    assert f"{loads.heatpump_kwh:,.0f}" in text
    assert f"{loads.ev_kwh:,.0f}" in text
    assert len(split_stages(text)) == STAGE_COUNT, "표가 늘어 단계가 갈렸다"


def test_the_subtotal_and_the_total_have_different_names_and_values(
    tmp_path: Path,
) -> None:
    """★★ 소계(HP+EV)와 총계(일반+HP+EV)가 «다른 이름·다른 값»으로 실린다.

    종전의 「한 호에 더해진 합계」는 HP+EV 뿐인데 이름이 «합계»라서 일반용이
    계산에서 빠졌다고 읽혔다(판정 §4-2). 총계는 **일반 + 소계** 로 대조한다 —
    값을 여기 박지 않는다.
    """
    report = _report()
    text = _dumped(tmp_path)
    loads = report.appliance_loads
    assert loads.heatpump_kwh is not None and loads.ev_kwh is not None, (
        "픽스처 전제가 깨졌다 — 대장이 기기 부하에 답하지 않는다"
    )
    subtotal = loads.total_kwh
    total = _general_load_kwh(report) + subtotal
    assert total != subtotal, "픽스처 전제가 깨졌다 — 일반용이 0 이다"
    row_subtotal = next(
        line for line in text.splitlines() if line.startswith("| **추가 부하 소계")
    )
    row_total = next(
        line for line in text.splitlines() if line.startswith("| **가구 총 전력")
    )
    assert "**추가 부하 소계 (HP+EV)**" in row_subtotal
    assert "**가구 총 전력 (일반+HP+EV)**" in row_total
    assert f"{subtotal:,.0f} {APPLIANCE_LOAD_UNIT}" in row_subtotal
    assert f"{total:,.0f} {APPLIANCE_LOAD_UNIT}" in row_total
    assert f"{total:,.0f}" not in row_subtotal, "소계 칸에 총계 값이 함께 실렸다"


def test_the_estate_total_multiplies_the_household_total_by_count(
    tmp_path: Path,
) -> None:
    """단지 총 전력 = 가구 총 전력 × 가구 수 — **더한 뒤에 곱한다**."""
    report = _report(**{HOUSEHOLD_COUNT_FIELD: _HOUSEHOLDS})
    text = _dumped(tmp_path, **{HOUSEHOLD_COUNT_FIELD: _HOUSEHOLDS})
    loads = report.appliance_loads
    assert loads.heatpump_kwh is not None and loads.ev_kwh is not None, (
        "픽스처 전제가 깨졌다 — 대장이 기기 부하에 답하지 않는다"
    )
    row = next(
        line for line in text.splitlines() if line.startswith("| 단지 총 전력 |")
    )
    expected = (_general_load_kwh(report) + loads.total_kwh) * _HOUSEHOLDS
    assert f"{expected:,.0f} {ESTATE_LOAD_UNIT}" in row, "단지 총 전력이 곱한 값이 아니다"


def test_the_estate_total_is_multiplied_in_one_place_only(tmp_path: Path) -> None:
    """★★ **단지 총부하를 곱하는 자리가 하나다** (R68/WP-4).

    같은 수를 1단계의 「단지 총 전력」 칸과 2단계의 확대 규칙 표가 함께 싣는다.
    두 자리에서 각자 곱하면 한쪽만 고쳐지고, 그때 같은 문서가 단지 총부하를 두
    수로 말한다 — 그래서 곱은 `core/report/verification_scaleup.py::
    estate_load_kwh` 하나가 갖고 두 표가 그것을 부른다.

    ⚠ 값을 여기 박지 않는다 — 리포트가 읽은 대장 값과 기기 부하로 대조한다.
    """
    fields = {HOUSEHOLD_COUNT_FIELD: _HOUSEHOLDS}
    report = _report(**fields)
    stages = split_stages(_dumped(tmp_path, **fields))
    assert len(stages) == STAGE_COUNT, "표가 늘어 단계가 갈렸다"
    per_household = household_total_load_kwh(report)
    assert per_household == pytest.approx(
        _general_load_kwh(report) + report.appliance_loads.total_kwh
    ), "가구 총 전력이 «더한 뒤에 곱한다» 순서를 벗어났다"
    estate = estate_load_kwh(report)
    assert estate == pytest.approx(per_household * _HOUSEHOLDS)
    cell = f"{estate:,.0f} {ESTATE_LOAD_UNIT}"
    assert cell in stages[0].body, "1단계의 단지 총 전력 칸이 그 수가 아니다"
    assert cell in stages[1].body, "2단계 확대 규칙 표가 그 수를 싣지 않았다"


def test_unspecified_heatpump_prints_differently_from_zero_heatpump(
    tmp_path: Path,
) -> None:
    """★★ 히트펌프가 `None`(적지 않았다)일 때와 `0.0`(없다고 적었다)일 때
    인쇄가 «다르다» — 합계 칸도 그 둘을 가른다 (`ApplianceLoads` 머리말).

    둘 다 더해지는 값은 0 이지만 진술이 다르고, 합계 칸이 그것을 확정값
    하나로 묻으면 검토자가 «반영됐다»로 읽는다.
    """
    zero = _dumped(tmp_path, **{HEATPUMP_LOAD_FIELD: 0.0})
    unspecified = _dumped(tmp_path, ledger_answers=False)
    row_zero = next(
        line for line in zero.splitlines() if line.startswith("| **가구 총 전력")
    )
    row_unspecified = next(
        line for line in unspecified.splitlines()
        if line.startswith("| **가구 총 전력")
    )
    assert APPLIANCE_LOAD_UNSPECIFIED in row_unspecified, (
        "미지정이 합계 칸에 문장으로 실리지 않았다"
    )
    assert APPLIANCE_LOAD_UNSPECIFIED not in row_zero, (
        "0 이라고 적었는데 «미지정»이 함께 실렸다"
    )
    assert row_zero != row_unspecified


# ── ② `None` 은 빈칸이 아니라 진술이다 ──────────────────────────────────────


def test_unspecified_inputs_print_a_sentence_not_a_blank(tmp_path: Path) -> None:
    """★★ 가구 수·기기 부하·계절 몫을 **안 적은** 실행 (판정 ③).

    빈칸으로 두면 검토자가 「반영됐다」로 읽고, 그 오독이 단지 총부하를 수십 배
    틀리게 만든다. 세 문면의 정본은 `core/casegrid/` 의 상수 셋이며 여기서
    베껴 적지 않고 들여와 대조한다.

    ## ⚠⚠ 「안 적은 실행」의 뜻이 R65 에 달라졌다 — **통로가 늘었다**

    시나리오에 안 적어도 **대장·자산이 답한다**(가구 수 20 · 히트펌프 2,675 ·
    전기차 2,784 · 계절 몫은 형상 자산의 `appliance_season_shares:` 절).
    그래서 앞의 둘은 **대장 통로까지 닫은 사본**으로 돌려 재고
    (`_blocked_ledger_text`), 계절 몫은 통로가 **자산**이라 그 자산을 지우면
    다른 것(형상 없는 실행)을 재게 되므로 **인쇄 자리에서** 직접 잰다.
    ⚠ 재는 성질은 셋 다 그대로다: *「값이 없으면 빈칸이 아니라 문장이 선다」*.
    """
    text = _dumped(tmp_path, ledger_answers=False)
    for sentence in (HOUSEHOLD_COUNT_UNSPECIFIED, APPLIANCE_LOAD_UNSPECIFIED):
        assert sentence in text, f"「미지정」 문장이 빠졌다: {sentence!r}"
    assert "| — |" not in text.split("### 미반영")[0].split("## 1단계")[1].split(
        "## 2단계"
    )[0].split("**ⓑ")[0], "1단계 실행 입력 표에 빈칸(`—`)이 있다"

    # ★ 계절 몫 — 자산이 답하지 않는 실행을 **인쇄 자리에서** 만든다.
    report = _report()
    without = replace(
        report, appliance_loads=replace(report.appliance_loads, season_shares=None)
    )
    printed = "\n".join(execution_input_lines(without))
    assert APPLIANCE_SEASON_SHARE_UNSPECIFIED in printed, (
        f"「미지정」 문장이 빠졌다: {APPLIANCE_SEASON_SHARE_UNSPECIFIED!r}"
    )
    assert "| — |" not in printed, "실행 입력 표에 빈칸(`—`)이 있다"


def test_the_season_shares_are_printed_when_given(tmp_path: Path) -> None:
    """★ 계절 몫을 **적었으면** 계절마다의 몫이 실린다 (요구 3).

    ⚠ 「시나리오에서도 못 바꾼다」로 적으면 거짓이다 — 이 검사가 그 통로가
    실제로 산출물까지 오는 것을 붙든다.
    """
    text = _dumped(tmp_path, **{APPLIANCE_SEASON_SHARE_FIELD: _season_heavy()})
    assert APPLIANCE_SEASON_SHARE_UNSPECIFIED not in text, (
        "계절 몫을 적었는데 「미지정」이 실렸다"
    )
    for name, share in _season_heavy().items():
        assert f"{name} {share:.1%}" in text, f"계절 {name} 의 몫이 빠졌다"


# ── ③ 단계 수 — 웹을 깨뜨리지 않았다는 증거 ─────────────────────────────────


def test_the_report_still_splits_into_nine_stages(tmp_path: Path) -> None:
    """★★★ `split_stages` 가 **여전히 9단계**로 가른다 (판정 ①).

    화면(`app/services/verify_steps.py`)은 `STAGE_COUNT` 를 기대하고, 어긋나면
    `VerificationStageError` 로 멈춘다. 단계를 늘리면 웹 코드와 e2e 가 딸려
    오는데 사용자가 그것을 미뤘다 — 이 검사가 그 경계를 지킨다.
    """
    stages = split_stages(_dumped(tmp_path))
    assert len(stages) == STAGE_COUNT
    assert [stage.number for stage in stages] == list(range(1, STAGE_COUNT + 1))


def test_the_new_sections_do_not_add_stage_headings(tmp_path: Path) -> None:
    """보탠 절이 `## N단계 —` 머리글을 늘리지 않았다.

    ⚠ 미반영 절은 `###` 이며 9단계 본문의 끝으로 실린다 — 그것이 위 검사가
    통과하는 이유다. 여기서는 그 사실을 **자리로** 확인한다.
    """
    text = _dumped(tmp_path)
    assert text.count("## 9단계 — ") == 1
    ninth = split_stages(text)[-1]
    assert "### 미반영 항목" in ninth.body, (
        "미반영 절이 9단계 본문 안에 있지 않다 — 새 단계가 됐을 수 있다"
    )


# ── ④ 계절 — 넷이 «각각» 나오는가 ───────────────────────────────────────────


def test_every_season_appears_with_its_own_days_and_yearly_share(
    tmp_path: Path,
) -> None:
    """요구 3·6 — 계절이 **각각** 이름·일수·연간 기여로 실린다.

    ⚠ 계절 개수를 박지 않는다 — 자산이 선언한 만큼을 그대로 요구한다.
    """
    text = _dumped(tmp_path)
    seasons = _report().seasons
    assert seasons, "픽스처 전제가 깨졌다 — 계절이 서지 않았다"
    assert [s.name for s in seasons] == _season_names()
    for season in seasons:
        assert season.name in text, f"계절 {season.name} 이 빠졌다"
        assert f"{season.days}일" in text, f"계절 {season.name} 의 일수가 빠졌다"
    assert f"**{sum(s.days for s in seasons)}일**" in text, "계절 일수 합이 빠졌다"


def test_the_seasonal_table_does_not_replace_the_representative_day(
    tmp_path: Path,
) -> None:
    """★ 계절 표가 대표일 표를 **대신하지 않는다.**

    결론(프로포마)이 선 하루는 연간등가 하루이며, 그것이 보고서에서 사라지면
    검토자가 「무엇 위에 결론이 섰는가」를 잃는다.
    """
    body = split_stages(_dumped(tmp_path))[2].body
    assert "대표일" in body
    assert "계절별 운전" in body


# ── ⑤ 검증이 찾은 결함 셋 — 각각 «따로» 잰다 (R64/WP-FIX) ───────────────────


def test_the_discount_rate_is_in_stage_one_where_stage_eight_points(
    tmp_path: Path,
) -> None:
    """★★ 결함 1 — 8단계의 **「1단계 할인율」이 실제로 1단계에 있다.**

    종전에는 그 교차참조가 거짓이었다: 할인율은 대장 항목이 아니라 케이스
    수준표의 모형 파라미터라 1단계 대장 표에 행이 없었고, 검토자가 1단계에서
    찾으면 없었다. 「손계산으로 따라올 수 있게 한다」는 이 문서의 목적에
    정면으로 어긋나는 끊김이다.

    ⚠ 값을 여기 박지 않는다 — 리포트가 읽는 그 칸에서 가져와 맞댄다.
    """
    assert "discount" not in _ASSUMPTIONS.read_text(encoding="utf-8"), (
        "전제가 깨졌다 — 대장에 할인율 항목이 생겼다면 이 행의 「대장에 없다」가 "
        "거짓이 된다(`core/casegrid/ledger_levels.py` 머리말이 그날을 예고한다)"
    )
    stages = split_stages(_dumped(tmp_path))
    rate = f"{_report().basis.discount_rate:.1%}"
    first, eighth = stages[0].body, stages[7].body
    assert "할인율" in first, "1단계에 할인율 행이 없다 — 8단계의 참조가 거짓이 된다"
    assert rate in first, f"1단계 할인율 행에 값({rate})이 없다"
    assert f"1단계 할인율 {rate}" in eighth, (
        "8단계가 1단계 할인율을 가리키지 않는다 — 두 자리가 갈렸다"
    )


def test_the_resource_table_carries_the_allocation_not_only_the_label(
    tmp_path: Path,
) -> None:
    """★★★ 결함 2 — 3단계에 **본 실행의 배분**이 실린다 (요구 5).

    종전에는 `dispatch_notes` 의 짧은 선언 라벨(「전량 판매」)만 실렸고, 그래서
    *「ESS 가 가구 부하를 보고 방전한다」* 를 이 문서 어디에서도 가릴 수 없었다
    (`부하 추종` 0건). 3단계 「전량 판매」와 2단계 「자가소비율」의 병치도 그
    때문에 초독자에게 모순으로 읽혔다.

    ## ⚠⚠ R68/WP-2 가 **모양을 바꿨다 — 요구는 그대로다**

    종전 이 검사는 *합친 긴 문면(`ResourceLine.operating_mode`)이 3단계에
    «통째로» 있는가* 를 쟀다. 두 열로 가른 뒤 통째로는 없으므로 **그 잼은
    반드시 빨간불이 된다 — 결함이 아니라 WP-2 가 한 일이다**(검토서 §3.3:
    선언된 운영모드와 실제 적용된 운영모드를 별도 열로 둔다).

    ⛔ **그렇다고 잼을 느슨하게 하지 않는다.** 이 검사가 지키던 것은
    *「이 실행이 실제로 무엇을 배분했는지가 3단계에 인쇄된다」* 이고 **그 요구는
    두 열로 갈라도 그대로다.** 그래서 셋을 잰다 — 선언이 있는가 · 실제 배분이
    있는가 · 둘이 **다른 열**에 있는가. 셋째가 빠지면 합쳐 인쇄해도 통과하고,
    그러면 WP-2 가 무의미하다.
    """
    stage3 = split_stages(_dumped(tmp_path))[2].body
    resources = _report().basis.resources
    assert resources, "픽스처 전제가 깨졌다 — 자원이 하나도 없다"
    assert any(line.applied_allocation for line in resources), (
        "픽스처 전제가 깨졌다 — 배분을 적는 자원이 하나도 없다"
    )
    # ⚠ 「선언」 열의 정본은 `DispatchNote.operating_mode` 다 — 합친 문면을 이
    # 검사가 쪼개 되짓지 않는다(쪼개는 것이 WP-2 가 금지한 바로 그 형태다).
    notes = {n.resource_name: n.operating_mode for n in _report().dispatch_notes}
    # ⚠ 행을 **디스패치 규칙 칸으로** 고른다 — 그 칸만 백틱으로 싸인 규칙
    # 이름을 갖는다(`_stage3_dispatch` 의 표 머리). 「백틱이 있는 줄」로 고르면
    # 계절 기여 표의 머리(조인 키를 병기한다)가 함께 걸린다.
    rules = {n.dispatch_rule.value for n in _report().dispatch_notes}
    table = [
        [cell.strip() for cell in row.split("|")]
        for row in stage3.splitlines()
        if row.startswith("| ") and any(f"`{rule}`" in row for rule in rules)
    ]
    for line in resources:
        cells = next(
            (cells for cells in table if f"`{line.name}`" in cells[1]), None
        )
        assert cells is not None, (
            f"자원 {line.name} 의 행이 3단계 ⓐ 표에 없다 — 조인 키로 찾는다"
        )
        declared, applied = cells[2], cells[3]
        assert declared == notes[line.name], (
            f"자원 {line.name} 의 **선언** 라벨이 선언 열에 없다 — "
            f"「{declared}」 ≠ 「{notes[line.name]}」"
        )
        assert applied == line.applied_allocation, (
            f"자원 {line.name} 이 **실제로 배분한 것**이 실제 열에 없다 — "
            f"「{applied}」 ≠ 「{line.applied_allocation}」"
        )
        assert declared != applied, (
            f"자원 {line.name} 의 선언과 실제가 **같은 글자로** 실렸다 — 두 열로 "
            "가른 뜻이 없다"
        )
        assert line.operating_mode not in stage3, (
            f"자원 {line.name} 의 **합친** 문면이 3단계에 그대로 남아 있다 — "
            f"두 열로 갈랐으면 한 칸에 함께 서 있을 수 없다: 「{line.operating_mode}」"
        )


def test_a_resource_only_in_the_notes_falls_back_instead_of_going_blank() -> None:
    """★ 결함 2 의 뒷면 — `basis.resources` 에 **없는** 자원의 칸.

    ⚠ 이름으로 맞추므로 두 목록의 길이가 다를 수 있다. 못 찾았을 때 빈칸을
    인쇄하면 「운전 방법을 안 적었다」로 읽히므로, 종전 값으로 떨어지고 그
    값마저 비면 **문장**을 적는다(이 모듈 ★★ 「빈칸이 아니라 진술」).
    """
    report = _report()
    named = {line.name for line in report.basis.resources}
    orphans = [n for n in report.dispatch_notes if n.resource_name not in named]
    assert orphans, "픽스처 전제가 깨졌다 — `dispatch_notes` 에만 있는 자원이 없다"
    rows = dispatch_note_rows(report)
    for note in orphans:
        row = next(r for r in rows if f"`{note.resource_name}`" in r.split("|")[1])
        declared, applied = row.split("|")[2].strip(), row.split("|")[3].strip()
        assert declared, f"{note.resource_name} 의 선언 칸이 빈칸이다 — 「{row}」"
        assert declared == (str(note.operating_mode) or NO_OPERATING_MODE), (
            f"{note.resource_name} 이 종전 값으로 떨어지지 않았다 — 「{declared}」"
        )
        # ★ **두 칸에 같은 문장을 되풀이하지 않는다** (R68/WP-2 §2ⓐ). 운전
        # 방법을 고르지 않는 자원은 선언 칸이 그 문장을 갖고 실제 칸은 「—」다.
        assert applied == NO_APPLIED_ALLOCATION, (
            f"{note.resource_name} 의 실제 배분 칸이 「{NO_APPLIED_ALLOCATION}」이 "
            f"아니다 — 「{applied}」"
        )


def test_the_item_count_says_what_those_items_are(tmp_path: Path) -> None:
    """★ 결함 3 — 「항목 N건」이 **그 N 이 무엇인지** 말한다.

    그 수는 대장 파일의 항목 수가 아니라 **provider 를 지나 값이 실린** 항목
    수다. 그렇게 적지 않으면 항목 수를 세는 검토자가 파일에서 다른 수를 얻는다.

    ⛔ 그렇다고 여기서 파일을 새로 세어 싣지 않는다 — 정본이 둘이 되고,
    그러면 provider 를 지나지 않은 수가 보고서에 실린다. 이 검사가 그 둘을
    **함께** 붙든다.
    """
    printed = len(_report().assumptions)
    ledger = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))["assumptions"]
    assert len(ledger) > printed, (
        "픽스처 전제가 깨졌다 — 값이 비어 있는 대장 항목이 하나도 없다"
    )
    text = _dumped(tmp_path)
    first = split_stages(text)[0].body
    assert f"항목 {printed}건" in first, f"1단계에 「항목 {printed}건」이 없다"
    assert "값을 읽어 온" in first, (
        "그 40이 무엇인지 말하지 않는다 — 검토자는 대장 파일의 항목 수로 읽는다"
    )
    assert f"항목 {len(ledger)}건" not in text, (
        "대장 파일을 새로 세어 그 수를 실었다 — 정본이 둘이 됐다"
    )


# ── ⑥ CLI — 인자를 주면 파일이 실제로 생긴다 ────────────────────────────────


def test_the_cli_help_explains_all_three_arguments() -> None:
    """`--help` 가 인자 셋을 설명한다 (판정 ⑤)."""
    text = _cli().build_parser().format_help()
    for flag in ("--scenario", "--assumptions", "--out"):
        assert flag in text, f"{flag} 가 --help 에 없다"
    assert "검증 보고서" in text


def test_the_cli_refuses_a_missing_scenario_with_a_sentence(
    tmp_path: Path, capsys
) -> None:
    """없는 경로는 **역추적이 아니라 한 줄**로 거부한다.

    역추적을 뱉으면 사람이 자기 오타인지 프로그램 결함인지 가릴 수 없다.
    """
    rc = _cli().main(
        [
            "--scenario", str(tmp_path / "없다.yaml"),
            "--out", str(tmp_path / "out.md"),
        ]
    )
    assert rc == 2
    assert "시나리오 파일이 없습니다" in capsys.readouterr().err
    assert not (tmp_path / "out.md").exists(), "거부했는데 파일을 만들었다"


def test_the_cli_writes_the_same_text_the_renderer_makes(tmp_path: Path) -> None:
    """★★ CLI 가 **서식을 짓지 않는다** (판정 ⑤).

    파일 안의 글자가 `render_verification_markdown()` 의 것과 한 자도 다르지
    않아야 한다 — 다르면 화면과 파일의 표기가 갈린다.
    """
    with tempfile.TemporaryDirectory() as workspace:
        scenario = _scenario_file(Path(workspace), **{HOUSEHOLD_COUNT_FIELD: _HOUSEHOLDS})
        target = tmp_path / "verification.md"
        assert (
            _cli().main(
                [
                    "--scenario", str(scenario),
                    "--assumptions", str(_ASSUMPTIONS),
                    "--out", str(target),
                ]
            )
            == 0
        )
        expected = render_verification_markdown(
            build_case_report(scenario, assumptions_path=_ASSUMPTIONS)
        )
    assert target.read_text(encoding="utf-8") == expected


# ── R67/WP-N3-fix — **검증 리포트에도 채택값이 실린다** ──────────────────────
#
# WP-N3 가 완화분(채택값)을 세우고 **심의 리포트 붙임 10 에만** 실었다. 그 사이
# 이 산출물은 완전 자립분만 실어 **두 문서가 같은 물음에 다르게 답했다** —
# 실측: 붙임 10 은 겨울 채택 642.07kWh, 검증 리포트는 917.25kWh 하나.
# 검증 리포트는 **사용자가 지금 읽는 산출물**이므로 그 상태는 *「ESS 적정용량이
# 917 kWh 다」* 로 읽힌다. 아래 둘이 그 어긋남을 붙든다.


def test_the_verification_ess_table_carries_the_adopted_value(tmp_path: Path) -> None:
    """★★★ 검증 리포트 2단계 ESS 표에 **채택값이 있다.**

    ⚠ **기대값을 리터럴로 적지 않는다** — `report.ess_sizing` 에서 읽어 짓는다.
    박으면 대장의 허용 비율이 바뀌는 날 이 검사가 조용히 낡은 수를 지킨다.
    ⚠ **완전 자립분도 함께 있어야 한다** — 채택값만 실으면 *「저녁 피크를 전량
    배터리로 덮으려면 얼마인가」* 를 검토자가 읽을 자리가 사라진다.
    """
    text = _dumped(tmp_path)
    review = _report().ess_sizing
    assert review.unmeasurable_reason is None, review.unmeasurable_reason
    assert review.seasons, "계절이 서지 않아 잴 것이 없다"

    assert ADOPTED_HEAD in text, "채택값 열이 없다"
    assert SELF_SUFFICIENT_HEAD in text, "완전 자립분 열이 없다"
    assert within_range_head(sweep_where="①의") in text, (
        "구간 칸이 「채택값을 판정한다」고 말하지 않는다"
    )
    for season in review.seasons:
        assert f"{season.relaxed.required_capacity_kwh:,.2f}kWh" in text, (
            f"{season.season_name} 의 채택 정격용량이 빠졌다"
        )
        assert f"{season.relaxed.required_power_kw:,.2f}kW" in text, (
            f"{season.season_name} 의 채택 정격출력이 빠졌다"
        )
        assert f"{season.sizing.required_capacity_kwh:,.2f}kWh" in text, (
            f"{season.season_name} 의 완전 자립 정격용량이 빠졌다"
        )

    # ★ 비율의 **출처**를 잃지 않는다 — 문면의 정본은 그 함수다.
    assert adopted_value_note(review) in text, (
        "완화 비율이 어디서 왔는지(대장 `policy.grid_supply_allowance` · 근거 "
        "법령·고시 미확인)가 검증 리포트에 없다"
    )
    assert relaxation_reach_note(review) in text
    # ⚠ 「진단이지 채택 구성이 아니다」를 지우지 않는다 — 실행은 여전히 수준표의
    #   용량으로 돈다(`core/report/ess_sizing_section.py` 머리말 ★★★).
    assert "진단이지 결론이 아니다" in text


def test_both_reports_say_the_same_adopted_winter_capacity(tmp_path: Path) -> None:
    """★★★ **심의 붙임 10 과 검증 2단계가 같은 채택값을 말한다.**

    이 교정이 막으려는 어긋남을 바로 이 검사가 붙든다 — 한쪽 렌더러만 고치면
    여기서 빨간불이 된다. ⛔ 두 렌더러를 하나로 합치지 않았으므로(표기 관례와
    절 번호가 다르다) **문면이 아니라 «수»를 대조한다.**

    ⚠ 「겨울」이라는 낱말을 박지 않는다 — 매는 하루를 채택값으로 골라 그 계절의
    수를 두 문서에서 찾는다(자산의 계절 이름은 `load_daily_shapes()` 것이다).
    """
    review = _report().ess_sizing
    binding = max(review.seasons, key=lambda s: s.relaxed.required_capacity_kwh)
    adopted_capacity = f"{binding.relaxed.required_capacity_kwh:,.2f}"
    adopted_power = f"{binding.relaxed.required_power_kw:,.2f}"

    verification = _dumped(tmp_path)
    appraisal = "\n".join(ess_daily_sizing_section(review))

    for where, text in (("검증 리포트", verification), ("심의 붙임 10", appraisal)):
        assert adopted_capacity in text, (
            f"{where} 에 매는 하루({binding.season_name})의 채택 저장용량 "
            f"{adopted_capacity}kWh 가 없다 — 두 산출물이 같은 물음에 다르게 답한다"
        )
        assert adopted_power in text, (
            f"{where} 에 매는 하루({binding.season_name})의 채택 정격출력 "
            f"{adopted_power}kW 가 없다"
        )
        assert ADOPTED_HEAD in text, f"{where} 에 채택값 표시가 없다"


# ── R68/WP-1 — 「채택」이 **두 가지를 가리켰다.** 2단계 머리가 셋을 갈라 세운다 ─
#
# ③ 표의 열 이름이 「★ 채택 정격용량」이고 겨울 값이 642.07kWh 였는데, 이 실행이
# 실제로 돌린 저장장치는 200kWh / 100kW 다 — 검토서
# `docs/verification-report-improvement-2026-09-09.md` §3.2 가 그것을 지적하고
# 진단 용량 · 실행 용량 · 채택 용량 셋으로 갈라 세울 것을 요구했다.
# ⛔ **사용자 판정(완화분이 역산의 답)은 뒤집지 않는다** — 낱말을 가른다.


def test_the_capacity_review_head_carries_the_three_kinds_of_capacity(
    tmp_path: Path,
) -> None:
    """★★★ **구분 표가 배포 산출물에 실린다** — 렌더러만 초록불이면 뜻이 없다.

    ⚠ CLI 를 지나 파일로 뽑은 문면을 본다(모듈 머리말 ⚠).
    ⚠ **수를 리터럴로 적지 않는다** — `report` 에서 읽어 짓는다.
    """
    text = _dumped(tmp_path)
    report = _report()
    review = report.ess_sizing
    binding = binding_season(review)

    for kind in (
        CAPACITY_KIND_DIAGNOSTIC,
        CAPACITY_KIND_RUNNING,
        CAPACITY_KIND_APPLIED,
    ):
        assert f"| **{kind}** |" in text, (
            f"2단계에 「{kind}」 행이 없다 — 「채택」이 두 뜻으로 읽히는 자리가 "
            "그대로다"
        )
    assert "**없음 — 이 실행은 진단값을 반영하지 않았다**" in text, (
        f"「{CAPACITY_KIND_APPLIED}」 칸이 「없음」이라고 말하지 않는다"
    )
    assert "사람 판단 자리다" in text, (
        "실행 용량이 진단 용량과 다른 사유를 이 리포트가 갖고 있지 않다는 "
        "진술이 없다"
    )
    # ★ 진단 용량 칸의 두 수 — 태양광(대장 기준 수준)과 매는 하루의 저장장치.
    base_point = report.self_sufficiency.points[LEVEL_NAMES.index("base")]
    assert f"{base_point.required_capacity_kw:,.2f}kW" in text, (
        "진단 용량 칸의 태양광 역산값이 없다"
    )
    for value in (
        binding.sizing.required_capacity_kwh,
        binding.relaxed.required_capacity_kwh,
    ):
        assert f"{value:,.2f}kWh" in text, f"진단 용량 칸에 {value:,.2f}kWh 가 없다"
    # ★ 실행 용량 칸은 **설계 변수의 사용값**에서 온다 — 리터럴이 아니다.
    for piece in run_used_values(report):
        assert piece in text, f"실행 용량 칸에 「{piece}」 가 없다"


def test_the_three_kinds_stand_before_the_tables_that_use_them(
    tmp_path: Path,
) -> None:
    """★★ **구분 표가 ①②③ «앞에» 선다** — 뒤에 서면 읽는 순서가 뜻을 못 고친다.

    독자는 표를 위에서 아래로 읽는다. 셋을 가르는 표가 ③ 뒤에 있으면 그 낱말을
    이미 **자기가 아는 뜻으로** 읽은 뒤다.
    """
    text = _dumped(tmp_path)
    first_table = text.index("① **" + ECONOMIC_SENSITIVITY_TITLE + "**")
    assert text.index(f"| **{CAPACITY_KIND_DIAGNOSTIC}** |") < first_table, (
        "구분 표가 ① 뒤에 섰다"
    )
    assert text.index(f"| **{CAPACITY_KIND_APPLIED}** |") < first_table


def test_the_ess_table_column_names_say_what_kind_of_adoption(tmp_path: Path) -> None:
    """★★★ ③ 표의 열 이름이 **무엇의 채택인지** 말한다 (검토서 §6 의 1번).

    ⚠ 「채택」이 통째로 사라져야 하는 것은 아니다 — *「채택한 것이 아니다」*
    처럼 **실행 반영**의 뜻으로 옳게 쓴 자리는 그대로 둔다(지시문 §2-ⓐ).
    재는 것은 **열 이름 쪽 낱말**이다.
    """
    text = _dumped(tmp_path)
    assert f"{ADOPTED_HEAD} 정격용량" in text, "③ 표에 역산 채택안 열이 없다"
    assert "★ 채택 정격용량" not in text, (
        "열 이름이 여전히 맨 「★ 채택」이다 — 그 낱말이 실제로 「이 용량으로 "
        "돌렸다」로 읽혔다"
    )
    assert f"{PER_HOUSEHOLD_HEAD} {ADOPTED_HEAD} 정격용량" in text, (
        "1가구 열의 이름이 함께 가지 않았다"
    )
    assert within_range_head(sweep_where="①의").startswith(ADOPTED_TERM), (
        "구간 칸이 판정 대상을 「역산 채택안」이라 부르지 않는다"
    )


def test_the_season_columns_carry_the_human_name_beside_the_join_key(
    tmp_path: Path,
) -> None:
    """★★★ **계절 기여 표의 열이 조인 키만으로 서 있지 않다** (검토서 §3.3 마지막).

    `e2e-pv`·`e2e-ess`·`e2e-load` 는 리포트·귀속 행·시험이 서로를 맞추는 **조인
    키**이고 심의자가 읽을 이름이 아니다. 그렇다고 키를 **갈아 끼우면** 같은
    종류 자원이 둘인 실행에서 두 열이 한 이름이 되고 계열 하나가 사라진다
    (`core/report/charts/seasonal_operation.py` 독스트링). ⇒ **병기**다.

    ⚠ 이름을 이 검사에 박지 않는다 — `ResourceLine.kind` 가 정본이다. 박으면
    자원 제원이 바뀌는 날 이 검사가 「리포트가 틀렸다」로 빨간불이 된다.
    """
    stage3 = split_stages(_dumped(tmp_path))[2].body
    header = next(
        (row for row in stage3.splitlines() if row.startswith("| 계절 | ") and "`" in row),
        None,
    )
    assert header is not None, (
        "계절 기여 표의 머리를 찾지 못했다 — 조인 키를 병기하는 그 표다"
    )
    for line in _report().basis.resources:
        assert line.kind, f"자원 {line.name!r} 의 kind 가 비어 있다"
        assert line.kind in header, (
            f"자원 {line.name!r} 의 사람용 이름 {line.kind!r} 이 열 이름에 없다: "
            f"{header}"
        )
        assert f"`{line.name}`" in header, (
            f"조인 키 {line.name!r} 가 열 이름에서 사라졌다 — 갈아 끼우지 않고 "
            f"병기해야 한다: {header}"
        )
    # ★ R68/WP-3 — 부하 열도 사람 말을 얻었다. 대장에 **없는** 키(`e2e-load`)라
    # `kind` 가 없고, 그래서 WP-2 뒤에도 그 한 열만 조인 키였다.
    assert DEMAND_LABEL in header, (
        f"대장에 없는 키(부하)가 아직 사람 말을 못 얻었다: {header}"
    )


def test_the_seasonal_day_tables_reach_stage_three(tmp_path: Path) -> None:
    """★★★ **계절마다 하루 스텝 표가 3단계에 실제로 실린다** (검토서 §3.4).

    검토서 문면: *「계절별 연간 수전량은 있으나 … 계절마다 24스텝 표가
    필요하다」*. 그 표를 짓는 자리는 `core/report/verification_dispatch.py` 이고
    (성질은 `tests/report/test_verification_dispatch.py` 가 잰다) **이 검사가
    붙드는 것은 그것이 이 문서의 3단계에 닿았는가**다 — R33 이 여섯 번 만난
    「계산은 있는데 읽는 쪽이 없다」의 반대 방향이다.

    ⚠ 계절 개수·스텝 수를 리터럴로 박지 않는다 — 자산이 정본이다.
    """
    stage3 = split_stages(_dumped(tmp_path))[2].body
    for name in _season_names():
        assert f"**{name} — 대표일 " in stage3, (
            f"3단계에 {name} 의 하루 스텝 표가 없다"
        )
        assert f"{name} 대조 — " in stage3, f"3단계에 {name} 의 대조 줄이 없다"
    assert "| 시각 |" in stage3, "사람용 스텝 표의 머리가 3단계에 없다"
    # ⚠ 문면을 찾지 않고 **표 칸**을 본다 — 「어긋나면 그대로 인쇄한다」는 안내
    # 줄이 그 낱말을 품고 있어, 글자로 찾으면 이 검사가 조용히 뒤집힌다.
    diverged = [
        line
        for line in stage3.splitlines()
        if line.startswith("| ") and "**어긋남" in line
    ]
    assert not diverged, (
        f"이 실행의 대조가 어긋났다 — 하루 표와 계절 연간값이 다른 실행을 보고 "
        f"있다: {diverged}"
    )
