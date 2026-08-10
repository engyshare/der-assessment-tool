from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


def _load_script(stem: str) -> ModuleType:
    scripts = str(SCRIPTS)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    name = f"_traceability_gate_{stem}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{stem}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


@pytest.mark.req("NFR-107-AC1.auto")
def test_traceability_collects_executed_req_markers_as_auto(tmp_path: Path) -> None:
    gen = _load_script("gen_traceability")
    _write(
        tmp_path / "test_auto.py",
        "import pytest\n\n"
        "@pytest.mark.req('FR-101-AC1')\n"
        "def test_real_mapping():\n"
        "    assert True\n",
    )

    mapping, defects = gen.collect_test_markers(tmp_path)

    assert defects == []
    assert mapping["FR-101-AC1"] == [(str(tmp_path / "test_auto.py"), False)]


@pytest.mark.req("NFR-107-AC1.manual")
def test_traceability_collects_manual_stub_markers_without_executing_them(
    tmp_path: Path,
) -> None:
    gen = _load_script("gen_traceability")
    _write(
        tmp_path / "test_manual.py",
        "import pytest\n\n"
        "@pytest.mark.manual\n"
        "@pytest.mark.req('NFR-302-M1')\n"
        "def test_manual_stub():\n"
        "    pytest.skip('manual record lives in docs/manual-checks.yaml')\n",
    )

    mapping, defects = gen.collect_test_markers(tmp_path)

    assert defects == []
    assert mapping["NFR-302-M1"] == [(str(tmp_path / "test_manual.py"), True)]


@pytest.mark.req("NFR-107-AC2")
@pytest.mark.req("NFR-107-M1")
def test_traceability_render_reports_unmapped_must_have_criteria() -> None:
    gen = _load_script("gen_traceability")
    specparse = _load_script("_specparse")
    req = specparse.Requirement(
        rid="FR-X",
        title="sample",
        priority="Must-have",
        phase="1",
        criteria=[specparse.Criterion("FR-X-AC1", "must be mapped", "ac")],
    )

    _content, unmapped, stub_only = gen.render([req], {}, {}, [], "spec.md")

    assert unmapped == ["FR-X-AC1 — must be mapped"]
    assert stub_only == []


@pytest.mark.req("NFR-107-AC3")
def test_traceability_rejects_manual_stub_without_execution_record() -> None:
    gen = _load_script("gen_traceability")
    specparse = _load_script("_specparse")
    req = specparse.Requirement(
        rid="FR-X",
        title="sample",
        priority="Must-have",
        phase="1",
        criteria=[specparse.Criterion("FR-X-AC1", "manual item", "ac")],
    )

    _content, unmapped, stub_only = gen.render(
        [req],
        {"FR-X-AC1": [("test_manual.py", True)]},
        {},
        [],
        "spec.md",
    )

    assert unmapped == []
    assert stub_only == ["FR-X-AC1 — test_manual.py"]


@pytest.mark.req("NFR-107-AC4")
def test_traceability_render_distinguishes_auto_and_manual_mappings() -> None:
    gen = _load_script("gen_traceability")
    specparse = _load_script("_specparse")
    req = specparse.Requirement(
        rid="FR-X",
        title="sample",
        priority="Must-have",
        phase="1",
        criteria=[
            specparse.Criterion("FR-X-AC1", "auto item", "ac"),
            specparse.Criterion("FR-X-AC2", "manual item", "ac"),
        ],
    )

    content, unmapped, stub_only = gen.render(
        [req],
        {
            "FR-X-AC1": [("test_auto.py", False)],
            "FR-X-AC2": [("test_manual.py", True)],
        },
        {"FR-X-AC2": {"id": "MC-X", "status": "미수행", "verdict": None}},
        [],
        "spec.md",
    )

    assert unmapped == []
    assert stub_only == []
    assert "| `FR-X-AC1` | auto item | 자동 | test_auto.py |" in content
    assert "| `FR-X-AC2` | manual item | 수동 | test_manual.py" in content


@pytest.mark.req("NFR-107-AC5")
def test_traceability_rejects_gate_self_reference_in_manual_ledger(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    manual = _write(
        tmp_path / "manual.yaml",
        "version: 1\n"
        "checks:\n"
        "  - id: MC-X\n"
        "    requirement: NFR-107\n"
        "    criterion_id: NFR-107-AC1.manual\n"
        "    why_manual: self reference\n"
        "    blocking_dod: false\n"
        "    status: '수행'\n"
        "    performed_at: '2026-08-10'\n"
        "    performed_by: 'x'\n"
        "    result_note: 'x'\n",
    )
    out = tmp_path / "traceability.md"
    spec = next((REPO_ROOT / "rslt").glob("spec-*.md"))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "gen_traceability.py"),
            "--spec",
            str(spec),
            "--tests",
            str(tests_dir),
            "--manual",
            str(manual),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 2
    assert "게이트 자신을 수동 대장에 등재" in (result.stdout + result.stderr)


# ── blocking_dod — 「죽은 깃발」을 읽는 코드가 하나도 없었다 (WP-24C) ────
#
# 사람이 `blocking_dod: true` 라고 적어도 그것을 읽는 코드가 없으면 기계에는
# 주석과 같다. 아래는 대장 전건에 그 칸을 강제하고, `수행` 기록의 완전성을
# 확인하며, 미수행 차단 검사를 「판정불가」로 표기하는 동작을 검증한다.


@pytest.mark.req("NFR-107-M1")
def test_collect_manual_flags_missing_blocking_dod_field(tmp_path: Path) -> None:
    gen = _load_script("gen_traceability")
    manual = _write(
        tmp_path / "manual.yaml",
        "version: 1\n"
        "checks:\n"
        "  - id: MC-Z\n"
        "    requirement: FR-101\n"
        "    criterion_id: FR-101-AC1\n"
        "    why_manual: x\n"
        "    status: '미수행'\n",
    )

    _manual, _orphan, missing_blocking, incomplete = gen.collect_manual(manual)

    assert missing_blocking == [
        "MC-Z — blocking_dod 칸이 없음 (requirement: FR-101)"
    ]
    assert incomplete == []


@pytest.mark.req("NFR-107-AC3")
def test_collect_manual_flags_performed_status_without_full_record(
    tmp_path: Path,
) -> None:
    gen = _load_script("gen_traceability")
    manual = _write(
        tmp_path / "manual.yaml",
        "version: 1\n"
        "checks:\n"
        "  - id: MC-Z\n"
        "    requirement: FR-101\n"
        "    criterion_id: FR-101-AC1\n"
        "    why_manual: x\n"
        "    blocking_dod: false\n"
        "    status: '수행'\n"
        "    performed_at: null\n"
        "    performed_by: '홍길동'\n"
        "    result_note: '통과'\n",
    )

    _manual, _orphan, missing_blocking, incomplete = gen.collect_manual(manual)

    assert missing_blocking == []
    assert incomplete == ["MC-Z — status=수행인데 performed_at 기록 없음"]


@pytest.mark.req("NFR-107-M1")
def test_render_marks_blocking_unperformed_checks_as_undetermined() -> None:
    gen = _load_script("gen_traceability")
    specparse = _load_script("_specparse")
    req = specparse.Requirement(
        rid="FR-X",
        title="sample",
        priority="Must-have",
        phase="1",
        criteria=[specparse.Criterion("FR-X-AC1", "manual item", "ac")],
    )
    chk = {"id": "MC-Z", "status": "미수행", "blocking_dod": True}

    content, unmapped, stub_only = gen.render(
        [req],
        {"FR-X-AC1": [("test_manual.py", True)]},
        {"FR-X-AC1": chk},
        [],
        "spec.md",
        blocking_unperformed=[("FR-X-AC1", chk)],
    )

    assert unmapped == []
    assert stub_only == []
    assert "판정불가" in content
    assert "MC-Z" in content


@pytest.mark.req("NFR-107-M1")
def test_traceability_rejects_manual_ledger_missing_blocking_dod(
    tmp_path: Path,
) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    manual = _write(
        tmp_path / "manual.yaml",
        "version: 1\n"
        "checks:\n"
        "  - id: MC-Z\n"
        "    requirement: FR-101\n"
        "    criterion_id: FR-101-AC1\n"
        "    why_manual: x\n"
        "    status: '미수행'\n",
    )
    out = tmp_path / "traceability.md"
    spec = next((REPO_ROOT / "rslt").glob("spec-*.md"))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "gen_traceability.py"),
            "--spec",
            str(spec),
            "--tests",
            str(tests_dir),
            "--manual",
            str(manual),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 2
    assert "blocking_dod 칸 누락" in (result.stdout + result.stderr)


@pytest.mark.req("NFR-107-AC3")
def test_traceability_rejects_incomplete_performed_record(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    manual = _write(
        tmp_path / "manual.yaml",
        "version: 1\n"
        "checks:\n"
        "  - id: MC-Z\n"
        "    requirement: FR-101\n"
        "    criterion_id: FR-101-AC1\n"
        "    why_manual: x\n"
        "    blocking_dod: false\n"
        "    status: '수행'\n"
        "    performed_at: null\n"
        "    performed_by: '홍길동'\n"
        "    result_note: '통과'\n",
    )
    out = tmp_path / "traceability.md"
    spec = next((REPO_ROOT / "rslt").glob("spec-*.md"))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "gen_traceability.py"),
            "--spec",
            str(spec),
            "--tests",
            str(tests_dir),
            "--manual",
            str(manual),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 2
    assert "수행 기록 불완전" in (result.stdout + result.stderr)

