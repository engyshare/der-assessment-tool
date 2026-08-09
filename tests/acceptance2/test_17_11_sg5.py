"""17.11 SG-5 — 신규 자원 클래스 1종 추가에 코어 코드 수정 0줄 실증."""
from __future__ import annotations

import gc
import importlib
import sys
from pathlib import Path

import pytest

import core.der
from core.contracts.der import DER
from core.contracts.registry import discover

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.req("FR-105-AC2")
def test_sg5_new_resource_class_addition_zero_core_edits() -> None:
    """SG-5 — 신규 자원 클래스 1종 추가 시 코어 엔진/CBA/계약 코드 수정 0줄 실증."""
    temp_sg5_file = REPO_ROOT / "core" / "der" / "temp_sg5_acceptance2.py"

    code_content = (
        "from core.contracts.der import DER, DispatchContext, DispatchResult\n"
        "from core.contracts.units import Money\n\n"
        "class SG5TempResource(DER):\n"
        "    tag = 'SG5TempResource'\n"
        "    OPERATING_MODES = ('simple',)\n"
        "    def __init__(self):\n"
        "        super().__init__(\n"
        "            name='sg5temp', lifetime=1, carries_electric=True, operating_mode='simple'\n"
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
        temp_sg5_file.write_text(code_content, encoding="utf-8")
        importlib.invalidate_caches()
        registry = discover(core.der, DER)
        assert "SG5TempResource" in registry, "SG-5 신규 자원이 발견기에 자동 수집되어야 합니다."

        # 코어 엔진/CBA 전용 모듈에 신규 자원을 위한 개별 수정 파일이 없어야 함
        assert not (REPO_ROOT / "core" / "engine" / "temp_sg5_acceptance2.py").exists()
        assert not (REPO_ROOT / "core" / "cba" / "temp_sg5_acceptance2.py").exists()

    finally:
        sys.dont_write_bytecode = old_dont_write_bytecode
        if temp_sg5_file.exists():
            temp_sg5_file.unlink()
        sys.modules.pop("core.der.temp_sg5_acceptance2", None)
        pycache_dir = REPO_ROOT / "core" / "der" / "__pycache__"
        if pycache_dir.is_dir():
            for pyc in pycache_dir.glob("temp_sg5_acceptance2*"):
                pyc.unlink(missing_ok=True)
        importlib.invalidate_caches()
        gc.collect()

    assert not temp_sg5_file.exists(), "SG-5 임시 자원 파일이 정리되지 않았습니다."
