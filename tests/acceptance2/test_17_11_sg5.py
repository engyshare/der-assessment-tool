"""17.11 SG-5 - a new resource class must flow through engine and CBA."""
from __future__ import annotations

import difflib
import gc
import importlib
import sys
from decimal import Decimal
from pathlib import Path

import pytest

import core.der
from core.cba.metrics import npv
from core.cba.proforma import (
    aggregate,
    assert_proforma_identity,
    benefit_row,
    capex_row,
    fixed_om_row,
    total_row,
)
from core.contracts.der import DER, DispatchContext, DispatchResult
from core.contracts.registry import discover
from core.contracts.units import ENERGY_TOLERANCE_KWH, Money
from core.engine.rule_based import RuleBasedEngine
from core.valuestream import SurplusSale

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_ENGINE_DIR = REPO_ROOT / "core" / "engine"
CORE_CBA_DIR = REPO_ROOT / "core" / "cba"
TEMP_GOOD_MODULE = REPO_ROOT / "core" / "der" / "temp_sg5_acceptance2.py"
TEMP_BAD_MODULE = REPO_ROOT / "core" / "der" / "temp_sg5_acceptance2_broken.py"


@pytest.mark.req("FR-105-AC2")
def test_sg5_new_resource_class_addition_runs_engine_and_cba_without_core_edits() -> None:
    """SG-5 - a new resource can run through engine and CBA without any core edits."""
    old_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True

    try:
        _cleanup_temp_module(TEMP_GOOD_MODULE, "core.der.temp_sg5_acceptance2")
        _cleanup_temp_module(TEMP_BAD_MODULE, "core.der.temp_sg5_acceptance2_broken")

        # Negative control: a broken resource should fail in the engine, proving the test is live.
        TEMP_BAD_MODULE.write_text(_broken_resource_source(), encoding="utf-8")
        importlib.invalidate_caches()
        broken_registry = discover(core.der, DER)
        broken = broken_registry["BrokenSG5TempResource"]()
        ctx = DispatchContext(steps=24, dt=3_600, year=1)
        with pytest.raises(RuntimeError, match="broken sg-5 probe"):
            RuleBasedEngine().run([broken], ctx)
        _cleanup_temp_module(TEMP_BAD_MODULE, "core.der.temp_sg5_acceptance2_broken")

        before_engine = _snapshot_dir(CORE_ENGINE_DIR)
        before_cba = _snapshot_dir(CORE_CBA_DIR)

        # Real resource: discover it, run it through the engine, then feed its output into CBA.
        TEMP_GOOD_MODULE.write_text(_good_resource_source(), encoding="utf-8")
        importlib.invalidate_caches()
        registry = discover(core.der, DER)
        resource = registry["SG5TempResource"]()
        assert resource.tag == "SG5TempResource"

        dispatch = RuleBasedEngine().run([resource], ctx)
        assert set(dispatch.per_resource) == {"sg5-temp"}
        assert max(abs(error) for error in dispatch.electric_balance_error()) < ENERGY_TOLERANCE_KWH
        assert sum(dispatch.grid_export) > 0.0

        export = DispatchResult(
            electric=list(dispatch.grid_export),
            heat=[0.0] * ctx.steps,
            cool=[0.0] * ctx.steps,
            fuel=[0.0] * ctx.steps,
        )
        annual_sale = SurplusSale(sale_price_won_per_kwh=100.0).annual_value(export, year=1)
        rows = [
            benefit_row("SG5Sale", {1: int(annual_sale)}),
            capex_row("SG5Capex", 1, -int(resource.capex(year=1))),
            fixed_om_row("SG5FixedOM", 1, 1, -int(resource.fixed_om(year=1))),
        ]
        assert_proforma_identity(rows)

        grand_total = total_row(rows)
        assert aggregate(rows) == grand_total.total()
        assert sum(grand_total.amounts.values(), Decimal(0)) == sum(row.total() for row in rows)

        project_npv = npv(resource.capex(year=1), [grand_total], discount_rate=0.045)
        assert isinstance(project_npv, Money)
        assert project_npv > Money(0)

        changed_engine_lines = _changed_lines(before_engine, CORE_ENGINE_DIR)
        changed_cba_lines = _changed_lines(before_cba, CORE_CBA_DIR)
        assert changed_engine_lines == 0, f"core/engine changed by {changed_engine_lines} lines"
        assert changed_cba_lines == 0, f"core/cba changed by {changed_cba_lines} lines"

    finally:
        sys.dont_write_bytecode = old_dont_write_bytecode
        _cleanup_temp_module(TEMP_GOOD_MODULE, "core.der.temp_sg5_acceptance2")
        _cleanup_temp_module(TEMP_BAD_MODULE, "core.der.temp_sg5_acceptance2_broken")
        importlib.invalidate_caches()
        gc.collect()

    assert not TEMP_GOOD_MODULE.exists(), "temporary SG-5 resource file was not cleaned up"
    assert not TEMP_BAD_MODULE.exists(), "temporary SG-5 probe file was not cleaned up"


def _good_resource_source() -> str:
    return (
        "from core.contracts.der import DER, DispatchContext, DispatchResult\n"
        "from core.contracts.units import Money\n"
        "\n"
        "\n"
        "class SG5TempResource(DER):\n"
        "    tag = 'SG5TempResource'\n"
        "    OPERATING_MODES = ('simple',)\n"
        "\n"
        "    def __init__(self) -> None:\n"
        "        super().__init__(\n"
        "            name='sg5-temp',\n"
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


def _broken_resource_source() -> str:
    return (
        "from core.contracts.der import DER, DispatchContext, DispatchResult\n"
        "from core.contracts.units import Money\n"
        "\n"
        "\n"
        "class BrokenSG5TempResource(DER):\n"
        "    tag = 'BrokenSG5TempResource'\n"
        "    OPERATING_MODES = ('simple',)\n"
        "\n"
        "    def __init__(self) -> None:\n"
        "        super().__init__(\n"
        "            name='broken-sg5-temp',\n"
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
        "        raise RuntimeError('broken sg-5 probe')\n"
    )


def _snapshot_dir(root: Path) -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in sorted(root.rglob("*.py"))}


def _changed_lines(before: dict[Path, str], root: Path) -> int:
    after = _snapshot_dir(root)
    all_paths = sorted(set(before) | set(after))
    total = 0
    for path in all_paths:
        before_text = before.get(path, "")
        after_text = after.get(path, "")
        total += _line_delta(before_text, after_text)
    return total


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
