"""검증 3단계 ⓐ — **선언 열과 실제 배분 열**, 그리고 그 아래 세 줄 (R68/WP-2).

동반 대상은 `core/report/verification_dispatch.py` 다(NFR-105 · 파일명 규약).

## ⚠ 무엇을 재고 무엇을 재지 않는가

이 검사가 붙드는 것은 **가르는 규칙**과 **표 아래 세 줄의 판정**이다. 문서
전체가 그 표를 실제로 싣는지는 `tests/report/test_verification.py` 가 CLI
산출물로 재고, 계절 기여 표의 열 이름은 `test_verification_inputs.py` 가 잰다 —
같은 것을 세 곳에서 재지 않는다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.casegrid.models import ResourceLine
from core.engine.rule_based import DispatchRule
from core.report.case_report import CaseReport, build_case_report
from core.report.dispatch_notes import (
    NO_APPLIED_ALLOCATION,
    NO_OPERATING_MODE,
    DispatchNote,
    applied_allocation,
    declared_operating_mode,
)
from core.report.verification_dispatch import (
    declaration_lines,
    dispatch_note_rows,
    resource_label,
    resource_labels,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"


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
    되고, 그림에서는 사전 키가 겹쳐 계열 하나가 **사라진다.** `kind` 가 없는
    항목(부하)은 **키만** 인쇄한다 — 여기서 이름을 지으면 같은 항목을 부르는
    말이 두 곳에서 갈린다.
    """
    kinds = {line.name: line.kind for line in report.basis.resources}
    assert kinds, "픽스처 전제가 깨졌다 — 자원이 하나도 없다"
    for name, kind in kinds.items():
        label = resource_label(name, kinds)
        assert kind in label, f"{name!r} 의 사람용 이름이 라벨에 없다 — {label!r}"
        assert f"`{name}`" in label, f"{name!r} 의 조인 키가 사라졌다 — {label!r}"
    assert resource_label("없는-키", kinds) == "`없는-키`", (
        "`kind` 가 없는 항목에 이름을 지어냈다"
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
