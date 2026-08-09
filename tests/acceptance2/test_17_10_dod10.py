"""17.10 DoD 10 - new resource addition must not edit shared files."""
from __future__ import annotations

import difflib
import gc
import importlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import core.der
from core.contracts.der import DER
from core.contracts.registry import discover

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_FILES = [
    REPO_ROOT / "core" / "der" / "__init__.py",
    REPO_ROOT / "core" / "asset" / "__init__.py",
    REPO_ROOT / "core" / "contracts" / "__init__.py",
    REPO_ROOT / "core" / "contracts" / "registry.py",
]
TEMP_BAD_MODULE = REPO_ROOT / "core" / "der" / "temp_acceptance2_bad_import.py"
TEMP_GOOD_MODULE = REPO_ROOT / "core" / "der" / "temp_acceptance2_resource.py"


@pytest.mark.req("NFR-207-M1")
@pytest.mark.req("NFR-208-M1")
def test_dod10_new_resource_addition_zero_shared_edits_and_clean_import_linter() -> None:
    """DoD 10 - a new resource must scan in and keep shared files untouched."""
    old_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True

    try:
        # Negative control: a deliberately bad module should make import-linter red.
        TEMP_BAD_MODULE.write_text(
            "from core.engine.rule_based import RuleBasedEngine\n"
            "\n"
            "class BadImportProbe:\n"
            "    pass\n",
            encoding="utf-8",
        )
        importlib.invalidate_caches()
        bad_result = _run_import_linter()
        assert bad_result.returncode != 0, (
            "import-linter stayed green even after introducing a forbidden core.engine import. "
            f"stdout={bad_result.stdout}\nstderr={bad_result.stderr}"
        )

        # Remove the violation before checking the real scenario.
        _cleanup_temp_module(TEMP_BAD_MODULE, "core.der.temp_acceptance2_bad_import")

        # Snapshot shared files before the actual resource is added.
        before = _snapshot(SHARED_FILES)

        # Real resource addition: discover must pick up the new file without shared edits.
        TEMP_GOOD_MODULE.write_text(_good_resource_source(), encoding="utf-8")
        importlib.invalidate_caches()

        registry = discover(core.der, DER)
        assert "Acceptance2TempResource" in registry, (
            "The new resource was not discovered by scanning core.der."
        )

        changed_lines = _changed_lines(before, SHARED_FILES)
        assert changed_lines == 0, (
            "Shared files changed while adding a new resource. "
            f"Changed lines: {changed_lines}"
        )

        good_result = _run_import_linter()
        assert good_result.returncode == 0, (
            "import-linter should be green after the temporary violation is removed. "
            f"stdout={good_result.stdout}\nstderr={good_result.stderr}"
        )

        # Second negative control: the helper must notice a changed shared file.
        probe_before = before[SHARED_FILES[-1]]
        probe_after = probe_before + "\n# acceptance2 probe\n"
        assert _line_delta(probe_before, probe_after) > 0, (
            "The shared-file line-delta helper did not detect a forced edit."
        )

    finally:
        sys.dont_write_bytecode = old_dont_write_bytecode
        _cleanup_temp_module(TEMP_GOOD_MODULE, "core.der.temp_acceptance2_resource")
        _cleanup_temp_module(TEMP_BAD_MODULE, "core.der.temp_acceptance2_bad_import")
        importlib.invalidate_caches()
        gc.collect()

    assert not TEMP_GOOD_MODULE.exists(), "temporary resource file was not cleaned up"
    assert not TEMP_BAD_MODULE.exists(), "temporary violation file was not cleaned up"


def _good_resource_source() -> str:
    return (
        "from core.contracts.der import DER, DispatchContext, DispatchResult\n"
        "from core.contracts.units import Money\n"
        "\n"
        "\n"
        "class Acceptance2TempResource(DER):\n"
        "    tag = 'Acceptance2TempResource'\n"
        "    OPERATING_MODES = ('simple',)\n"
        "\n"
        "    def __init__(self) -> None:\n"
        "        super().__init__(\n"
        "            name='acceptance2-temp',\n"
        "            lifetime=20,\n"
        "            carries_electric=True,\n"
        "            operating_mode='simple',\n"
        "        )\n"
        "\n"
        "    def capex(self, *, year: int) -> Money:\n"
        "        return Money(1_000)\n"
        "\n"
        "    def capex_vat(self, *, year: int) -> Money:\n"
        "        return Money(0)\n"
        "\n"
        "    def fixed_om(self, *, year: int) -> Money:\n"
        "        return Money(0)\n"
        "\n"
        "    def variable_om(self, *, year: int) -> Money:\n"
        "        return Money(0)\n"
        "\n"
        "    def replacement_schedule(self, *, horizon: int) -> dict[int, Money]:\n"
        "        return {}\n"
        "\n"
        "    def salvage_value(self, *, year: int) -> Money:\n"
        "        return Money(0)\n"
        "\n"
        "    def dispatch(self, ctx: DispatchContext) -> DispatchResult:\n"
        "        return DispatchResult(\n"
        "            electric=[1.0] * ctx.steps,\n"
        "            heat=[0.0] * ctx.steps,\n"
        "            cool=[0.0] * ctx.steps,\n"
        "            fuel=[0.0] * ctx.steps,\n"
        "        )\n"
    )


def _run_import_linter() -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-m", "importlinter", "run"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        lint_cmd = shutil.which("lint-imports") or "lint-imports"
        result = subprocess.run(
            [lint_cmd],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    return result


def _snapshot(paths: list[Path]) -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in paths}


def _changed_lines(before: dict[Path, str], paths: list[Path]) -> int:
    after = _snapshot(paths)
    return sum(_line_delta(before[path], after[path]) for path in paths)


def _line_delta(before: str, after: str) -> int:
    matcher = difflib.SequenceMatcher(a=before.splitlines(), b=after.splitlines())
    return sum(
        max(i2 - i1, j2 - j1)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    )


def _cleanup_temp_module(path: Path, module_name: str) -> None:
    if path.exists():
        path.unlink()
    sys.modules.pop(module_name, None)
    pycache_dir = path.parent / "__pycache__"
    if pycache_dir.is_dir():
        for pyc in pycache_dir.glob(f"{path.stem}*"):
            pyc.unlink(missing_ok=True)
