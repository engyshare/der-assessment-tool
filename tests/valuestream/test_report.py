"""8.6 — 편익 계상 내역 리포트 (FR-402-AC6).

네 부류로 분류: 계상 / 배타제외 / 증분만 / 미화폐화0. **오탐 0** — 정당한
동시 편익이 «배타제외»로 분류되지 않는지를 함께 검증한다.
"""
from __future__ import annotations

from core.contracts.der import DispatchResult
from core.valuestream import (
    REC,
    DistributedBenefit,
    HeatCostSaving,
    PeakShaving,
    SelfConsumption,
    SurplusSale,
)
from core.valuestream.report import build_report


def _dispatch_zeros(steps: int = 4) -> DispatchResult:
    z = [0.0] * steps
    return DispatchResult(electric=list(z), heat=list(z), cool=list(z), fuel=list(z))


def test_report_separates_accounted_from_excluded() -> None:
    """계상된 편익과 배타 제외된 편익이 분리된다.

    오라클: 순위 4 (정합). SelfConsumption + SurplusSale 이 같이 활성화되면
    유형 A 배타로 한 쌍이 «배타제외» 로 분류된다 (구현 단순화로 양쪽 다 제외).
    HeatCostSaving 은 배타 규칙이 없으므로 «계상됨».
    """
    sc = SelfConsumption(baseline_annual_bill_won=300, new_annual_bill_won=120)
    ss = SurplusSale(sale_price_won_per_kwh=100)
    heat = HeatCostSaving(
        baseline_fuel_cost_won_per_year=200, hp_electricity_cost_won_per_year=80
    )
    report = build_report([sc, ss, heat], _dispatch_zeros(), year=1)

    accounted_tags = {line.tag for line in report.accounted}
    excluded_tags = {line.tag for line in report.excluded}
    # SelfConsumption + SurplusSale 은 유형 A 로 양쪽 제외
    assert "SelfConsumption" in excluded_tags
    assert "SurplusSale" in excluded_tags
    # HeatCostSaving 은 정상 계상
    assert "HeatCostSaving" in accounted_tags
    assert "HeatCostSaving" not in excluded_tags


def test_report_unmonetized_zero_for_distributed_benefit() -> None:
    """활성화됐지만 값 0인 분산편익은 «미화폐화0» 분류 (FR-404-AC1).

    REC 는 발전량이 있어 계상됨 — 분산편익만 0 인 것과 대비된다.
    """
    dist = DistributedBenefit()  # sub_items 전부 0
    rec = REC(weight=1.0, rec_price_won_per_unit=100)
    # electric=[0,0,0,1000] → REC 발전량 1000 kWh × 1.0 × 100 = 100,000 원
    z = [0.0, 0.0, 0.0, 1000.0]
    report = build_report(
        [dist, rec],
        DispatchResult(electric=z, heat=z, cool=z, fuel=z),
        year=1,
    )
    zero_tags = {line.tag for line in report.unmonetized_zero}
    accounted_tags = {line.tag for line in report.accounted}
    assert "DistributedBenefit" in zero_tags
    assert "REC" in accounted_tags


def test_report_total_accounted_excludes_zero_and_excluded() -> None:
    """total_accounted 는 계상된 것만 합 — 배타제외·미화폐화0 제외.

    오라클: 순위 1 (합산 산식).
    """
    sc = SelfConsumption(baseline_annual_bill_won=300, new_annual_bill_won=120)
    # SelfConsumption 혼자 → 배타 쌍이 없으므로 «계상됨»
    report = build_report([sc], _dispatch_zeros(), year=1)
    assert report.total_accounted() == report.accounted[0].annual_value


def test_report_increment_only_for_type_b() -> None:
    """유형 B 배타(분산편익↔자가소비)는 «증분만» 분류.

    SelfConsumption + DistributedBenefit(값 0) → DistributedBenefit 이 «증분만»
    분류되어야 한다. 전액이 아닌 미래 증설 회피 증분만 계상 (원칙 2-1).
    """
    sc = SelfConsumption(baseline_annual_bill_won=300, new_annual_bill_won=120)
    dist = DistributedBenefit()  # 활성화, 값 0
    report = build_report([sc, dist], _dispatch_zeros(), year=1)
    inc_tags = {line.tag for line in report.increment_only}
    assert "DistributedBenefit" in inc_tags


def test_peak_shaving_simultaneous_with_self_consumption_is_accounted() -> None:
    """**FR-402-AC1 핵심** — 자가소비 + 피크저감 동시 계상은 «정상 계상».

    오라클: 순위 4 (검사 정합 — §13.0.1 ④). 물리량(kWh vs kW)이 다르므로
    배타가 아니다. 둘 다 «계상됨» 이어야 한다 — 배타 규칙이 넓으면 둘 중 하나가
    «배타제외»로 지워지고 그것은 결과에 나타나지 않는다.
    """
    sc = SelfConsumption(baseline_annual_bill_won=300, new_annual_bill_won=120)
    peak = PeakShaving(
        monthly_peak_reduction_kw=[1.0] * 12, demand_charge_won_per_kw_month=5000
    )
    report = build_report([sc, peak], _dispatch_zeros(8760), year=1)
    accounted_tags = {line.tag for line in report.accounted}
    assert "SelfConsumption" in accounted_tags
    assert "PeakShaving" in accounted_tags
    assert report.excluded == []
