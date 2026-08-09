"""17.9 DoD 9 - Must-have acceptance criteria traceability status."""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TRACEABILITY_MD = REPO_ROOT / "docs" / "traceability.md"


def _read_musthave_unmapped_rows() -> list[dict[str, str]]:
    assert TRACEABILITY_MD.is_file(), "traceability.md file must exist."

    rows: list[dict[str, str]] = []
    content = TRACEABILITY_MD.read_text(encoding="utf-8")
    current_requirement = ""
    current_priority = ""
    current_phase = ""
    for line in content.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 7:
            continue

        requirement, priority, phase, criterion, description, status, tests = cells[:7]
        if requirement:
            current_requirement = requirement
        if priority:
            current_priority = priority
        if phase:
            current_phase = phase

        requirement = current_requirement
        priority = current_priority
        phase = current_phase
        if priority != "Must-have" or status != "**미매핑**":
            continue

        rows.append(
            {
                "requirement": requirement,
                "priority": priority,
                "phase": phase,
                "criterion": criterion.strip("`"),
                "description": description,
                "status": status,
                "tests": tests,
            }
        )

    return rows


def _phase_1_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row["phase"] == "1"]


@pytest.mark.req("NFR-107-M1")
def test_dod9_traceability_status_report(capsys: pytest.CaptureFixture[str]) -> None:
    """Print the current Must-have unmapped status and its list."""
    rows = _read_musthave_unmapped_rows()
    phase1_rows = _phase_1_rows(rows)
    phase2_or_3_rows = [row for row in rows if row["phase"] != "1"]

    with capsys.disabled():
        print(
            f"Must-have 미매핑 {len(rows)}건 "
            f"(Phase 1: {len(phase1_rows)}건, Phase 2/3: {len(phase2_or_3_rows)}건)"
        )
        for row in rows:
            print(
                f"- {row['criterion']} [Phase {row['phase']}] "
                f"{row['requirement']} :: {row['description']}"
            )


@pytest.mark.req("NFR-107-M1")
def test_dod9_phase_1_musthave_unmapped_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """Phase 1 DoD 9 is satisfied when no Phase 1 Must-have criteria remain unmapped."""
    rows = _read_musthave_unmapped_rows()
    phase1_rows = _phase_1_rows(rows)
    phase1_summary = ", ".join(
        f"{row['criterion']} ({row['requirement']})" for row in phase1_rows
    ) or "none"

    with capsys.disabled():
        if phase1_rows:
            print(
                "Phase 1 Must-have 미매핑이 남아 있습니다: "
                f"{len(phase1_rows)}건 -> {phase1_summary}"
            )
        else:
            print(
                "Phase 1 Must-have 미매핑 0건. "
                f"남은 {len(rows)}건은 Phase 2/3 항목입니다."
            )

    assert not phase1_rows, (
        "Phase 1 Must-have 미매핑이 0건이어야 합니다. "
        f"남은 항목: {phase1_summary}"
    )
