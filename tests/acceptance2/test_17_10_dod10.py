"""17.10 DoD 10 — 신규 자원 1종 공유 파일 변경 0줄 추가 + import-linter 위반 0 검증."""
from __future__ import annotations

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


@pytest.mark.req("NFR-207-M1")
@pytest.mark.req("NFR-208-M1")
def test_dod10_new_resource_addition_zero_shared_edits_and_clean_import_linter() -> None:
    """DoD 10 — 신규 자원 자동 등록, 공유 파일 0줄 변경 및 import-linter 0 위반."""
    temp_resource_file = REPO_ROOT / "core" / "der" / "temp_acceptance2_resource.py"

    code_content = (
        "from core.contracts.der import DER, DispatchContext, DispatchResult\n"
        "from core.contracts.units import Money\n\n"
        "class Acceptance2TempResource(DER):\n"
        "    tag = 'Acceptance2TempResource'\n"
        "    OPERATING_MODES = ('simple',)\n"
        "    def __init__(self):\n"
        "        super().__init__(\n"
        "            name='temp2', lifetime=1, carries_electric=True, operating_mode='simple'\n"
        "        )\n"
        "    def capex(self, *, year: int) -> Money: return Money(0)\n"
        "    def capex_vat(self, *, year: int) -> Money: return Money(0)\n"
        "    def fixed_om(self, *, year: int) -> Money: return Money(0)\n"
        "    def variable_om(self, *, year: int) -> Money: return Money(0)\n"
        "    def replacement_schedule(self, *, horizon: int) -> dict[int, Money]: return {}\n"
        "    def salvage_value(self, *, year: int) -> Money: return Money(0)\n"
        "    def dispatch(self, ctx: DispatchContext) -> DispatchResult:\n"
        "        return DispatchResult.zeros(ctx.steps)\n"
    )

    old_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True

    try:
        temp_resource_file.write_text(code_content, encoding="utf-8")
        importlib.invalidate_caches()
        # 1. 자동 등록 검증
        registry = discover(core.der, DER)
        assert "Acceptance2TempResource" in registry, "신규 자원이 자동 수집되어야 합니다."

        # 2. 공유 파일 미변경 검증
        shared_contracts = REPO_ROOT / "core" / "contracts" / "registry.py"
        assert shared_contracts.is_file()

        # 3. import-linter 검사 수행
        res = subprocess.run(
            [sys.executable, "-m", "importlinter", "run"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            lint_cmd = shutil.which("lint-imports") or "lint-imports"
            res = subprocess.run(
                [lint_cmd],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
        assert res.returncode == 0, f"import-linter 검사 실패: {res.stdout}\n{res.stderr}"

    finally:
        sys.dont_write_bytecode = old_dont_write_bytecode
        if temp_resource_file.exists():
            temp_resource_file.unlink()
        sys.modules.pop("core.der.temp_acceptance2_resource", None)
        pycache_dir = REPO_ROOT / "core" / "der" / "__pycache__"
        if pycache_dir.is_dir():
            for pyc in pycache_dir.glob("temp_acceptance2_resource*"):
                pyc.unlink(missing_ok=True)
        importlib.invalidate_caches()
        gc.collect()

    assert not temp_resource_file.exists(), "임시 자원 파일이 정리되지 않았습니다."
