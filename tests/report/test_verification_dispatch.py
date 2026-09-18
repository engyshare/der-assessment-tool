"""검증 3단계 ⓐ — **선언 열과 실제 배분 열**, 그리고 그 아래 세 줄 (R68/WP-2).

동반 대상은 `core/report/verification_dispatch.py` 다(NFR-105 · 파일명 규약).

## ⚠ 무엇을 재고 무엇을 재지 않는가

이 검사가 붙드는 것은 **가르는 규칙**과 **표 아래 세 줄의 판정**이다. 문서
전체가 그 표를 실제로 싣는지는 `tests/report/test_verification.py` 가 CLI
산출물로 재고, 계절 기여 표의 열 이름은 `test_verification_inputs.py` 가 잰다 —
같은 것을 세 곳에서 재지 않는다.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from pathlib import Path
from typing import TypeVar

import pytest

from core.casegrid.models import ResourceLine
from core.engine.rule_based import DispatchRule
from core.report.case_report import CaseReport, build_case_report
from core.report.dispatch_notes import (
    DEMAND_LABEL,
    NO_APPLIED_ALLOCATION,
    NO_OPERATING_MODE,
    DispatchNote,
    applied_allocation,
    build_hourly_profile,
    declared_operating_mode,
    split_three_ways,
)
from core.report.dispatch_sections import (
    GENERATION_HEAD,
    LOAD_HEAD,
    STORAGE_CHARGE_HEAD,
    STORAGE_DISCHARGE_HEAD,
)
from core.report.verification_dispatch import (
    APPLIANCE_SHAPE_NOT_CARRIED,
    SOC_NOT_CARRIED,
    declaration_lines,
    dispatch_note_rows,
    resource_label,
    resource_labels,
    season_step_tables,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"

_V = TypeVar("_V")


@pytest.fixture(scope="module")
def report() -> CaseReport:
    return build_case_report(_GOLDEN, assumptions_path=_ASSUMPTIONS)


def _note(name: str, mode: str) -> DispatchNote:
    return DispatchNote(
        resource_name=name,
        operating_mode=mode,
        dispatch_rule=DispatchRule.GRID_IMPORT,
        dispatch_priority=0,
        price_linked=False,
    )


def test_the_two_columns_come_from_two_fields_not_from_splitting_one_string(
    report: CaseReport,
) -> None:
    """★★★ **문자열을 쪼개 가르지 않는다** — 조각마다 칸이 하나씩 있다.

    합친 문면을 ` · ` 로 가르면 **조용히 틀린다**: 배분 문면 «안에도» 그
    구분자가 있다(저장장치의 「자가소비 우선 · 방전 배분: 부하 추종 (방전창
    18~21시 안)」 — 배분 조각 자체가 콜론과 괄호를 든다). 이 검사가 그 함정을
    실물로 붙든다 — 픽스처에 그런 자원이 **있다**는 사실까지 함께 잰다.
    """
    resources = report.basis.resources
    assert resources, "픽스처 전제가 깨졌다 — 자원이 하나도 없다"
    assert any(" · " in line.applied_allocation for line in resources) or any(
        ": " in line.applied_allocation for line in resources
    ), (
        "픽스처 전제가 깨졌다 — 배분 조각이 구분자를 품은 자원이 없어 「쪼개면 "
        "틀린다」를 이 검사가 증명하지 못한다"
    )
    allocations = {line.name: line.applied_allocation for line in resources}
    for line in resources:
        assert line.operating_mode.endswith(line.applied_allocation), (
            f"자원 {line.name} 의 합친 칸이 뒷조각으로 끝나지 않는다 — 두 칸이 "
            f"갈렸다: {line.operating_mode!r} / {line.applied_allocation!r}"
        )
    for note in report.dispatch_notes:
        if note.resource_name in allocations:
            assert applied_allocation(note, allocations) == (
                allocations[note.resource_name]
            ), f"{note.resource_name} 의 배분이 그 칸에서 오지 않았다"


def test_a_resource_without_an_operating_mode_states_it_once_not_twice(
    report: CaseReport,
) -> None:
    """★★ 운전 방법을 고르지 않는 자원은 **선언 칸이 문장을 갖고 실제 칸은 「—」**.

    두 칸에 같은 문장을 되풀이하면 표가 넓어지기만 하고 읽는 사람이 얻는 것이
    없다. 그렇다고 선언 칸을 비우면 「아직 안 적었다」와 구별되지 않는다 — 이
    저장소의 규약(「`None` 은 빈칸이 아니라 «진술»이다」)이 그것을 금지한다.
    """
    note = _note("어디에도-없는-자원", "")
    assert declared_operating_mode(note) == NO_OPERATING_MODE
    assert applied_allocation(note, {}) == NO_APPLIED_ALLOCATION
    assert NO_APPLIED_ALLOCATION != NO_OPERATING_MODE, (
        "두 문면이 같으면 「선언이 없다」와 「고를 배분이 없다」를 가릴 수 없다"
    )
    # 실물에서도 그 자원이 하나 있다 — 부하는 `basis.resources` 에 없다.
    named = {line.name for line in report.basis.resources}
    orphans = [n for n in report.dispatch_notes if n.resource_name not in named]
    assert orphans, "픽스처 전제가 깨졌다 — 자원 목록에 없는 운전 항목이 없다"
    for row in dispatch_note_rows(report):
        cells = [cell.strip() for cell in row.split("|")]
        if any(f"`{n.resource_name}`" == cells[1] for n in orphans):
            assert cells[3] == NO_APPLIED_ALLOCATION, (
                f"자원 목록에 없는 항목의 실제 칸이 「{NO_APPLIED_ALLOCATION}」이 "
                f"아니다 — 「{cells[3]}」"
            )


def test_the_label_pairs_the_human_name_with_the_join_key(report: CaseReport) -> None:
    """★★ **병기다 — 갈아 끼우기가 아니다.**

    키를 라벨로 갈아 끼우면 같은 종류 자원이 둘인 실행에서 두 줄이 한 이름이
    되고, 그림에서는 사전 키가 겹쳐 계열 하나가 **사라진다.**

    ## ★ R68/WP-3 — 갈래가 **둘에서 셋**이 됐다

    종전에는 「`kind` 가 있으면 병기 · 없으면 키만」 둘이었고 그래서 부하
    (`e2e-load` — `CaseBasis.resources` 에 **없다**)가 키만으로 서 있었다. 그
    낱말(`DEMAND_LABEL`)이 `app/` 에 있어 이 계층이 부를 수 없었기 때문이다.
    정본이 `core` 로 내려온 지금 갈래는 셋이다 — ⓐ 대장에 있고 `kind` 가 있으면
    병기 · ⓑ 대장에 **없으면** 수요 · ⓒ 대장에 있으나 `kind` 가 비면 **키만**.
    ⓒ 가 남아 있어야 하는 이유는 「이름을 짓지 않는다」이며, 그때 키를 인쇄하는
    것이 열을 이름 없이 세우거나 빼는 것보다 낫다.
    """
    kinds = {line.name: line.kind for line in report.basis.resources}
    assert kinds, "픽스처 전제가 깨졌다 — 자원이 하나도 없다"
    for name, kind in kinds.items():
        label = resource_label(name, kinds)
        assert kind in label, f"{name!r} 의 사람용 이름이 라벨에 없다 — {label!r}"
        assert f"`{name}`" in label, f"{name!r} 의 조인 키가 사라졌다 — {label!r}"
    # ⓑ 대장에 없는 키는 **수요**다 — 그 글자를 이 검사에 박지 않는다(정본이
    # 바뀌면 리포트가 아니라 이 검사가 틀린 것이 되어야 한다).
    orphan = resource_label("없는-키", kinds)
    assert orphan == f"{DEMAND_LABEL} (`없는-키`)", (
        f"대장에 없는 키가 수요로 적히지 않았다 — {orphan!r}"
    )
    # ⓒ 대장에 있으나 `kind` 가 빈 자원은 **키만** — 이름을 지어내지 않는다.
    nameless = dataclasses.replace(report.basis.resources[0], kind="")
    only_key = resource_label(nameless.name, {nameless.name: nameless.kind})
    assert only_key == f"`{nameless.name}`", (
        f"`kind` 가 빈 자원에 이름을 지어냈다 — {only_key!r}"
    )
    same_kind = (
        ResourceLine(
            name="a",
            kind="같은 종류",
            capacity="—",
            operating_mode="—",
            applied_allocation="—",
            lifetime_years=1,
            unit_capex="—",
            capex_won=0,
            fixed_om_won_per_year=0,
            produces=(),
            policy_warnings=(),
        ),
        ResourceLine(
            name="b",
            kind="같은 종류",
            capacity="—",
            operating_mode="—",
            applied_allocation="—",
            lifetime_years=1,
            unit_capex="—",
            capex_won=0,
            fixed_om_won_per_year=0,
            produces=(),
            policy_warnings=(),
        ),
    )
    labels = resource_labels(["a", "b"], same_kind)
    assert len(set(labels)) == 2, (
        f"종류가 같은 자원 둘이 한 이름이 됐다 — 열 하나가 사라진다: {labels}"
    )


def test_the_realization_line_reads_the_export_from_the_run_not_a_literal(
    report: CaseReport,
) -> None:
    """★★★ **「0」을 리터럴로 박지 않는다** — 송전이 있는가를 실행의 수가 판정한다.

    같은 리포트에 서로 다른 송전 합계를 넣어 부르면 그 줄이 **뒤집혀야** 한다.
    뒤집히지 않으면 그 문장은 실행을 읽지 않고 있으며, 송전이 생기는 실행에서
    조용히 거짓이 된다.
    """
    zero = declaration_lines(report, grid_export_kwh=0.0)
    some = declaration_lines(report, grid_export_kwh=1234.0)
    assert len(zero) == len(some) == 4, "표 아래 줄 수가 셋(+빈 줄)이 아니다"
    assert "실현되지 않았다" in zero[2], f"송전 0 인데 그 사실을 적지 않았다 — {zero[2]}"
    assert "실현되지 않았다" not in some[2], (
        f"송전이 있는데도 「실현되지 않았다」를 적었다 — {some[2]}"
    )
    assert "1,234" in some[2], f"실행의 수를 인쇄하지 않았다 — {some[2]}"


def test_the_realization_line_does_not_accuse_a_storage_declaration(
    report: CaseReport,
) -> None:
    """★★★ **계통 송전이 재는 것은 «내보내는» 자원의 선언뿐이다.**

    저장장치는 「자가소비 우선」을 선언하고 이 실행에서 그대로 자가소비했다 —
    계통 송전이 0 이어도 **그 선언은 실현된 것**이다. 갈린 자원 전부를 이 줄에
    끌어들이면 *「자가소비 우선 선언이 실현되지 않았다」* 라는 **거짓**이
    인쇄된다. 가름은 `split_by_direction()` 하나가 한다.
    """
    modes = {line.name: line.operating_mode for line in report.basis.resources}
    storage = [
        name
        for name, mode in modes.items()
        if "자가소비" in mode and "판매" not in mode
    ]
    assert storage, "픽스처 전제가 깨졌다 — 자가소비를 선언한 자원이 없다"
    line = declaration_lines(report, grid_export_kwh=0.0)[2]
    for name in storage:
        declared = next(
            n.operating_mode for n in report.dispatch_notes if n.resource_name == name
        )
        assert f"「{declared}」" not in line, (
            f"내보내지 않는 자원의 선언 「{declared}」 이 「실현되지 않았다」 줄에 "
            f"끌려 들어왔다 — {line}"
        )


# ── 3단계 ⓑ — 계절마다 하루 스텝 전건 (R68/WP-3 · 검토서 §3.4) ─────────────────
#
# 검토서 문면: *「계절별 연간 수전량은 있으나 … 계절마다 24스텝 표가 필요하다.
# 표 아래에 «하루 합계 × 계절 일수 = 계절 연간값» 을 대조해야 한다」*.
# 아래가 그 자리를 붙든다 — **인쇄된 표에서 읽는다.**


def _step_rows(lines: list[str]) -> list[list[str]]:
    """계절마다 그 표의 **데이터 행**만 — 표 하나가 한 묶음이다.

    ⚠ 머리글로 표를 가른다(`| 시각 |`). 합계 행과 대조 표는 걷는다 — 이 함수가
    세는 것은 「그 계절 하루의 스텝이 전건 실렸는가」다.
    """
    tables: list[list[str]] = []
    for line in lines:
        if line.startswith("| 시각 |"):
            tables.append([])
        elif tables and line.startswith("| ") and "시 |" in line:
            tables[-1].append(line)
    return tables


def _reconciliation_cells(lines: list[str], label: str) -> list[list[str]]:
    """대조 표에서 그 항목의 행 — 계절마다 하나씩."""
    return [
        [cell.strip() for cell in line.strip("|").split("|")]
        for line in lines
        if line.startswith(f"| {label} |")
    ]


def test_every_season_carries_its_own_day_step_by_step(report: CaseReport) -> None:
    """★★★ **계절마다 하루가 스텝 전건으로 실린다** — 표본이 아니다.

    ⚠ 표 개수와 스텝 수를 리터럴로 박지 않는다 — `report.seasons` 와 그 계절의
    운전이 정본이다. 박으면 자산이 계절이나 해상도를 바꾸는 날 이 검사가
    「리포트가 틀렸다」로 빨간불이 된다.

    ⚠⚠ **계절을 이어 붙이지 않았는가**를 함께 잰다. 표 하나에 96행이 서면 그것은
    「96시간이 이어졌다」를 주장하는 것이며, 같은 하루를 네 번 그린 사실이
    사라진다.
    """
    lines = season_step_tables(report)
    assert len(report.seasons) >= 2, "이 시나리오가 계절을 갈라 돌지 않았다"

    tables = _step_rows(lines)
    assert len(tables) == len(report.seasons), (
        f"스텝 표가 {len(tables)}개다 — 계절 {len(report.seasons)}개여야 한다"
    )
    for season, rows in zip(report.seasons, tables, strict=True):
        steps = len(build_hourly_profile(season.dispatch))
        assert len(rows) == steps, (
            f"{season.name} 표의 행이 {len(rows)}개다 — 스텝 {steps}개여야 한다"
        )
        assert f"**{season.name} — 대표일 {steps}스텝** (연 {season.days}일" in "\n".join(
            lines
        ), f"{season.name} 표의 제목이 계절 이름·스텝 수·일수를 함께 적지 않았다"


def test_the_reconciliation_reads_the_annual_value_from_the_runner(
    report: CaseReport,
) -> None:
    """★★★ **오른쪽 연간값을 표시 층이 다시 곱해 만들지 않는다.**

    다시 곱하면 왼쪽과 오른쪽이 **같은 계산의 두 사본**이 되어 대조가 아무것도
    재지 않는다 — 그때도 전건 「같다」로 인쇄되므로 산출물만 봐서는 알 수 없다.
    그래서 러너가 실어 온 연간값 하나를 **일부러 틀리게** 바꿔 넣고 그 칸이
    **어긋남으로 뒤집히는지** 본다. 뒤집히지 않으면 오른쪽은 `SeasonRun` 을 읽지
    않고 있다.

    ⚠ 계절 몫·일수는 건드리지 않는다 — 바꾼 것은 「러너가 말한 연간값」 하나다.
    """
    intact = season_step_tables(report)
    for cells in _reconciliation_cells(intact, "한전 수전"):
        assert cells[-1] == "같다", f"손대지 않은 실행에서 대조가 어긋났다 — {cells}"

    first = report.seasons[0]
    tampered = dataclasses.replace(
        report,
        seasons=(
            dataclasses.replace(
                first, grid_import_annual_kwh=first.grid_import_annual_kwh + 1.0
            ),
            *report.seasons[1:],
        ),
    )
    cells = _reconciliation_cells(season_step_tables(tampered), "한전 수전")
    assert cells[0][-1].startswith("**어긋남"), (
        f"러너의 연간값을 1kWh 틀리게 바꿨는데 대조가 「{cells[0][-1]}」이다 — "
        "오른쪽 값을 표시 층이 다시 곱해 만들고 있다"
    )
    assert all(row[-1] == "같다" for row in cells[1:]), (
        f"손대지 않은 계절까지 어긋남으로 인쇄됐다 — {cells[1:]}"
    )


def test_the_reconciliation_shows_all_three_numbers(report: CaseReport) -> None:
    """★★ **세 수를 다 보인다** (검토서 §3.4 마지막 문단).

    하루 합계·계절 일수·그 계절 연간값이 한 행에 함께 서야 독자가 곱을 눈으로
    따라갈 수 있다. 결과만 「같다」로 적으면 그 판정을 검토자가 재현할 수 없다.
    """
    lines = season_step_tables(report)
    for season, cells in zip(
        report.seasons, _reconciliation_cells(lines, "한전 수전"), strict=True
    ):
        day = sum(
            hour.grid_import for hour in build_hourly_profile(season.dispatch)
        )
        assert cells[1] == f"{day:,.2f}", f"하루 합계가 인쇄되지 않았다 — {cells}"
        assert cells[2] == str(season.days), f"계절 일수가 없다 — {cells}"
        assert cells[4] == f"{season.grid_import_annual_kwh:,.2f}", (
            f"그 계절 연간값이 인쇄되지 않았다 — {cells}"
        )


def test_the_soc_column_is_stated_as_absent_and_never_drawn(
    report: CaseReport,
) -> None:
    """★★★ **SOC 를 지어내지 않고 「없다」를 «글자로» 적는다** (판정 §4-4).

    검토서 §3.4 의 표는 일곱째 열로 SOC 를 요구하는데 이 층에 SOC 시계열이
    도착하지 않는다(`DispatchResult` 에 그 계열이 없다). 충·방전에서 역산하면
    초기 SOC 와 효율 배분을 **가정**하는 것이고 그것은 지어낸 수다. 빈 열을
    세우면 「0% 였다」로 읽히므로 열이 아니라 문장이어야 한다.
    """
    lines = season_step_tables(report)
    assert SOC_NOT_CARRIED in lines, "SOC 가 없다는 사실을 적지 않았다"
    for line in lines:
        if line.startswith("| 시각 |"):
            assert "SOC" not in line, f"SOC 열을 세웠다 — {line}"


def test_the_appliance_time_shape_is_stated_as_absent(report: CaseReport) -> None:
    """★★★ **일반용·히트펌프·전기차를 비율로 쪼개 그리지 않고 그렇게 적는다.**

    러너가 그 셋을 합계 하나(`extra_appliance_load_kwh`)로 받으므로 하루 안에서
    되돌릴 수 없다. 비율로 쪼개면 판정 §4-4 가 금한 「만들어 낸 결과」다.
    """
    lines = season_step_tables(report)
    assert APPLIANCE_SHAPE_NOT_CARRIED in lines, (
        "기기별 시간 형상이 없다는 사실을 적지 않았다"
    )


def test_the_columns_are_paired_by_sign_and_the_pairing_is_printed(
    report: CaseReport,
) -> None:
    """★★★ **가름은 이름이 아니라 부호가 하고, 그 짝짓기가 인쇄된다.**

    이름으로 가르면 자원이 늘 때마다 표시 층을 고쳐야 하고 고치지 않으면 그
    자원이 **조용히 0** 이 된다. 그리고 가름이 어긋난 날(저장장치가 부하 열에
    섞이는 등) 짝짓기 줄이 없으면 그 사실이 산출물에서 **보이지 않는다.**

    ⚠ 자원 이름을 이 검사에 박지 않는다 — `split_three_ways()` 가 정본이다.
    """
    generation, storage, load = split_three_ways(report.dispatch_hours)
    assert generation and storage and load, (
        f"픽스처 전제가 깨졌다 — 셋 중 빈 갈래가 있다: {generation} {storage} {load}"
    )
    pairing = next(
        (line for line in season_step_tables(report) if "열과 자원의 짝짓기" in line),
        None,
    )
    assert pairing is not None, "어느 열이 어느 자원인지 적은 줄이 없다"
    for head in (LOAD_HEAD, GENERATION_HEAD, STORAGE_CHARGE_HEAD):
        assert f"「{head}" in pairing or f"·{head}" in pairing, (
            f"짝짓기 줄이 「{head}」 열을 가리키지 않는다 — {pairing}"
        )
    for name in (*generation, *storage, *load):
        assert f"`{name}`" in pairing, (
            f"자원 {name!r} 이 어느 열에 들었는지 적히지 않았다 — {pairing}"
        )


def _pruned(mapping: Mapping[str, _V], key: str) -> dict[str, _V]:
    return {name: value for name, value in mapping.items() if name != key}


def _without_resource(report: CaseReport, key: str) -> CaseReport:
    """그 자원이 **아예 없는** 실행을 만든다 — 값을 0 으로 두는 것과 다르다.

    ⚠ 세 자리를 함께 걷어야 한다 — 연간등가 하루(가름의 근거) · 계절 하루(표의
    값) · 계절 연간값(대조의 오른쪽). 하나만 걷으면 「없는 실행」이 아니라
    **어긋난 실행**을 만들게 되고, 그러면 이 검사가 다른 것을 재게 된다.
    """
    hours = tuple(
        dataclasses.replace(hour, per_resource=_pruned(hour.per_resource, key))
        for hour in report.dispatch_hours
    )
    seasons = tuple(
        dataclasses.replace(
            season,
            dispatch=dataclasses.replace(
                season.dispatch,
                per_resource=_pruned(season.dispatch.per_resource, key),
            ),
            per_resource_annual_kwh=_pruned(season.per_resource_annual_kwh, key),
        )
        for season in report.seasons
    )
    return dataclasses.replace(report, dispatch_hours=hours, seasons=seasons)


def test_a_run_without_storage_omits_the_columns_and_says_why(
    report: CaseReport,
) -> None:
    """★★★ **없는 설비의 열을 0 으로 스물넷 인쇄하지 않는다** — 그리고 사유를 적는다.

    「저장장치 충전 0.00」이 하루 종일 서 있으면 *「저장장치가 있는데 안
    움직였다」* 로 읽힌다. 그렇다고 조용히 빼면 「열이 빠졌다」와 「그 설비가
    없다」가 산출물에서 같아진다 — **둘을 함께** 한다.

    ⚠ 저장장치가 **있으면서 하루 종일 0 인** 계절(겨울)에는 열이 그대로 서야
    한다 — 그때 0 은 「안 움직였다」라는 사실이고, 그 갈래를 이 검사가 함께 잰다.
    """
    _generation, storage, _load = split_three_ways(report.dispatch_hours)
    assert len(storage) == 1, f"이 픽스처의 저장장치가 하나가 아니다 — {storage}"

    with_storage = season_step_tables(report)
    assert any(
        STORAGE_CHARGE_HEAD in line and line.startswith("| 시각 |")
        for line in with_storage
    ), "저장장치가 있는 실행인데 그 열이 없다"
    idle = [
        line
        for line in with_storage
        if line.startswith("| **합계** |") and "**0.00**" in line
    ]
    assert idle, "하루 종일 0 인 계절이 없어 「있는데 안 움직였다」 갈래를 못 잰다"

    lines = season_step_tables(_without_resource(report, storage[0]))
    for line in lines:
        if line.startswith("| 시각 |"):
            assert STORAGE_CHARGE_HEAD not in line, f"없는 설비의 열을 세웠다 — {line}"
            assert STORAGE_DISCHARGE_HEAD not in line, (
                f"없는 설비의 열을 세웠다 — {line}"
            )
    assert any(
        STORAGE_CHARGE_HEAD in line and "세우지 않았다" in line for line in lines
    ), "열을 세우지 않은 사유를 글자로 적지 않았다"


def test_a_run_without_seasons_prints_nothing_here(report: CaseReport) -> None:
    """★★ **계절이 없으면 아무것도 세우지 않는다** — 사유는 부르는 쪽이 갖는다.

    `core/report/verification_inputs.py::season_lines` 가 이미 그 문장을 적었다
    (*「계절이 서지 않았다 — 형상 자산 없이 도는 실행이라 대표일 한 벌뿐이다」*).
    여기서 같은 사유를 다시 지으면 산출물이 한 사실을 두 번 말하고, 문면이
    갈리는 날 어느 쪽이 정본인지 알 수 없다.
    """
    assert season_step_tables(dataclasses.replace(report, seasons=())) == []


def test_a_season_with_no_steps_is_told_not_drawn_as_an_empty_table(
    report: CaseReport,
) -> None:
    """★★ **스텝이 0 인 계절에 빈 표를 세우지 않는다** — 사유를 적고 멈춘다.

    빈 표를 세우면 *「그 계절은 아무 일도 하지 않았다」* 로 인쇄된다. 붙임 7 의
    계절 절(`core/report/dispatch_sections.py::_season_sections`)이 같은 판단을
    이미 적었고, 이 절도 같은 갈래를 가져야 한다 — 산출물 둘이 같은 결손을 다르게
    말하면 검토자가 어느 쪽을 믿을지 정해야 한다.
    """
    first = report.seasons[0]
    hollow = dataclasses.replace(
        report,
        seasons=(
            dataclasses.replace(
                first,
                dispatch=dataclasses.replace(
                    first.dispatch, per_resource={}, grid_import=[], grid_export=[]
                ),
            ),
            *report.seasons[1:],
        ),
    )
    lines = season_step_tables(hollow)
    assert not any(line.startswith("| 시각 |") for line in lines), (
        "스텝이 0 인 계절이 있는데 표를 세웠다"
    )
    assert any(
        "미산출" in line and first.name in line for line in lines
    ), f"어느 계절이 비었는지 적지 않았다 — {lines}"
