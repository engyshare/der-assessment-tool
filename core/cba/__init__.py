"""core/cba — 구획 WP-7.

프로포마·NPV·IRR·회수기간·LCOE·잔존가치·관점 분리 (FR-701, FR-703~705)

소유 경로 밖 파일을 건드리지 않는다 (§16.1 W-1). 엔진·편익 계층을 import 하지
않고 ``CashFlowRow``(계약)로 입력을 받는다 (§16.1 W-6).
"""
from __future__ import annotations

from core.cba.baseline import (
    BaselineComparison,
    assert_baseline_displayed,
    compare_baseline_vs_new,
    compute_incremental,
)
from core.cba.metrics import (
    BCResult,
    bcr,
    fiscal_pv,
    household_saving,
    irr,
    lcoe_mixed,
    lcoe_resource,
    mirr,
    mirr_preferred_over_irr,
    npv,
    payback_discounted,
    payback_simple,
    self_consumption_rate,
    supply_duty_rate,
)
from core.cba.perspective import (
    Perspective,
    PerspectiveInclusions,
    PerspectiveResult,
    society_excludes_subsidy,
)
from core.cba.proforma import (
    aggregate,
    assert_proforma_identity,
    benefit_row,
    capex_row,
    fixed_om_row,
    loan_repayment_row,
    replacement_row,
    salvage_row,
    tax_row,
    total_row,
)
from core.cba.salvage import salvage_value

__all__ = (  # noqa: RUF022
    # metrics
    "BCResult",
    "npv",
    "bcr",
    "irr",
    "mirr",
    "mirr_preferred_over_irr",
    "payback_simple",
    "payback_discounted",
    "lcoe_resource",
    "lcoe_mixed",
    "household_saving",
    "self_consumption_rate",
    "supply_duty_rate",
    "fiscal_pv",
    # proforma
    "capex_row",
    "fixed_om_row",
    "replacement_row",
    "salvage_row",
    "loan_repayment_row",
    "benefit_row",
    "tax_row",
    "total_row",
    "aggregate",
    "assert_proforma_identity",
    # salvage
    "salvage_value",
    # baseline
    "BaselineComparison",
    "compare_baseline_vs_new",
    "compute_incremental",
    "assert_baseline_displayed",
    # perspective
    "Perspective",
    "PerspectiveInclusions",
    "PerspectiveResult",
    "society_excludes_subsidy",
)
