"""8.6 — 편익 계상 내역 리포트 (FR-402-AC6).

네 부류로 분류: 계상 / 배타제외 / 증분만 / 미화폐화0. **오탐 0** — 정당한
동시 편익이 «배타제외»로 분류되지 않는지를 함께 검증한다.
"""
from __future__ import annotations

import pytest

from core.contracts.der import DispatchResult
from core.contracts.validation import ValidationError
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


def test_type_a_combination_is_refused_not_labelled() -> None:
    """유형 A 는 **분류되지 않고 거부된다** (FR-402-AC2.A · DV-12).

    > ### ★ R17: 이 테스트는 **조항의 반대를 고정하고 있었다**
    >
    > 원래 이름은 `test_report_separates_accounted_from_excluded` 였고,
    > 독스트링이 *「SelfConsumption + SurplusSale 이 같이 활성화되면 유형 A
    > 배타로 한 쌍이 «배타제외» 로 분류된다」* 고 적었다. 그런데 조항은
    > *「선언적 배타 규칙 테이블로 금지하고, **선택 시 검증 오류로 거부**
    > 한다」* 이다. **표시와 거부는 다르고, 이 테스트는 표시 쪽을 고정했다** —
    > 즉 거부가 구현되면 빨간불이 나는 형태였다. WP-28B 가 거부를 배선하자
    > 실제로 그렇게 됐다.
    >
    > 되돌리지 않았다. **조항이 정본이고 테스트가 따라간다.**
    """
    sc = SelfConsumption(baseline_annual_bill_won=300, new_annual_bill_won=120)
    ss = SurplusSale(sale_price_won_per_kwh=100)
    heat = HeatCostSaving(
        baseline_fuel_cost_won_per_year=200, hp_electricity_cost_won_per_year=80
    )
    with pytest.raises(ValidationError) as caught:
        build_report([sc, ss, heat], _dispatch_zeros(), year=1)
    assert caught.value.rule == "DV-12"
    assert "SelfConsumption" in caught.value.reason
    assert "SurplusSale" in caught.value.reason


def test_report_separates_accounted_from_excluded() -> None:
    """계상된 편익과 배타 제외된 편익이 분리된다 — **배타제외는 이제 C·D 다.**

    유형 A 가 거부로 바뀌었으므로 «배타제외» 버킷에 도달하는 것은 `C`·`D`
    뿐이다. 그 버킷이 살아 있는지를 **유형 D**(제도적 배타 — 상계거래 참여
    설비의 REC 발급 제한)로 확인한다.

    오라클: 순위 4 (검사 정합). `REC ↔ SurplusSale` 은 `applies_to_profile:
    net_metering` 이므로 **그 프로파일에서만** 발동한다 — 프로파일을 주지
    않으면 제도 한정 규칙이 빠진다(보수적). HeatCostSaving 은 어느 규칙에도
    없으므로 «계상됨» 이다.
    """
    rec = REC(weight=1.0, rec_price_won_per_unit=50_000)
    ss = SurplusSale(sale_price_won_per_kwh=100)
    heat = HeatCostSaving(
        baseline_fuel_cost_won_per_year=200, hp_electricity_cost_won_per_year=80
    )
    report = build_report(
        [rec, ss, heat], _dispatch_zeros(), year=1, profile="net_metering"
    )

    accounted_tags = {line.tag for line in report.accounted}
    excluded_tags = {line.tag for line in report.excluded}
    # 유형 D — 양쪽 다 «배타제외» (구현 단순화)
    assert "REC" in excluded_tags
    assert "SurplusSale" in excluded_tags
    # HeatCostSaving 은 정상 계상 — 오탐 0
    assert "HeatCostSaving" in accounted_tags
    assert "HeatCostSaving" not in excluded_tags


def test_type_d_rule_does_not_fire_without_its_profile() -> None:
    """제도 한정 규칙은 **그 프로파일이 아니면 발동하지 않는다** (FR-402-AC2.D).

    같은 세 편익을 프로파일 없이 넘기면 `REC ↔ SurplusSale` 이 빠지므로
    셋 다 계상된다. **오탐 0 이 이 조항의 수용 수준이다** — 제도 근거가 없는
    배타를 걸면 정당한 편익이 지워진다.
    """
    rec = REC(weight=1.0, rec_price_won_per_unit=50_000)
    ss = SurplusSale(sale_price_won_per_kwh=100)
    heat = HeatCostSaving(
        baseline_fuel_cost_won_per_year=200, hp_electricity_cost_won_per_year=80
    )
    report = build_report([rec, ss, heat], _dispatch_zeros(), year=1)
    assert {line.tag for line in report.excluded} == set()


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
