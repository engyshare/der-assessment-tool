"""Focused FR-105 acceptance mapping tests.

The numeric expectations below are manual/spec expectations, not values copied
from implementation output.
"""

from __future__ import annotations

import pytest

from core.der.ev_v2g import EV_V2G
from core.der.pv import PV, OperatingMode
from tests.der.test_ev_v2g import make_ev
from tests.der.test_pv import make_pv_1kw


@pytest.mark.req("FR-105-AC1")
def test_selected_mode_changes_reportable_value_streams() -> None:
    """Spec logic: unidirectional EV has no V2G benefit; bidirectional can report DemandResponse."""
    one_way = make_ev(
        operating_mode=EV_V2G.MODE_UNIDIRECTIONAL,
        discharge_benefit_enabled=True,
        daily_charge_kwh=10.0,
    )
    bidirectional = make_ev(
        operating_mode=EV_V2G.MODE_BIDIRECTIONAL,
        discharge_benefit_enabled=True,
    )

    assert one_way.value_streams() == ()
    assert bidirectional.value_streams() == ("DemandResponse",)


@pytest.mark.req("FR-105-AC5")
def test_operating_mode_accepts_case_grid_serialized_value() -> None:
    """Case grids serialize enum choices as strings; "full export" must round-trip to the enum."""
    pv = make_pv_1kw(operating_mode=OperatingMode.FULL_EXPORT.value)

    assert pv.operating_mode is OperatingMode.FULL_EXPORT
    assert tuple(OperatingMode) == PV.OPERATING_MODES
