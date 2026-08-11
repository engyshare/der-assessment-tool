"""R17/WP-28B — `build_report()` 배선 확인: 유형 A 실제 거부 (FR-402-AC2.A).

거부 함수(`assert_no_exclusions`)는 이미 있었으나 `build_report()` 가 부르지
않아 유형 A 위반으로도 리포트가 정상 생성됐다 (표시와 거부는 다르다). 이
파일은 배선 이후 두 방향을 모두 고정한다.

- 유형 A (음성 검증, 차단 100%): 위반 조합 → `ValidationError(rule="DV-12")`.
- 유형 A 가 아닌 조합 (양성 검증, 오탐 0): 예외 없이 정상 계상/라벨링.
  특히 FR-402-AC1 은 자가소비+피크저감+망회피+CO2 의 동시 계상을 **거부하지
  않는다**고 명시하므로, 그 경로가 거부되지 않음을 반드시 함께 고정한다.
"""
from __future__ import annotations

import pytest

from core.contracts.der import DispatchResult
from core.contracts.validation import ValidationError
from core.valuestream import (
    REC,
    DistributedBenefit,
    DistributedSubItems,
    PeakShaving,
    SelfConsumption,
    SurplusSale,
)
from core.valuestream.report import build_report


def _dispatch_zeros(steps: int = 4) -> DispatchResult:
    z = [0.0] * steps
    return DispatchResult(electric=list(z), heat=list(z), cool=list(z), fuel=list(z))


@pytest.mark.req("FR-402-AC2.A")
def test_type_a_combination_rejects_with_dv12() -> None:
    """자가소비+잉여판매(유형 A) 동시 활성화 → `build_report()` 가 거부한다.

    오라클: 순위 4 (§13.0.1 ④ — 검사가 실제로 붙드는가). 리포트가 생성되면
    틀린 것이다 — 배선 전에는 이 조합도 "배타제외" 라벨을 달고 정상 생성됐다.
    """
    sc = SelfConsumption(baseline_annual_bill_won=300, new_annual_bill_won=120)
    ss = SurplusSale(sale_price_won_per_kwh=100)

    with pytest.raises(ValidationError) as exc_info:
        build_report([sc, ss], _dispatch_zeros(), year=1)

    err = exc_info.value
    assert err.rule == "DV-12"
    assert err.field
    assert err.action
    # 문구 전체를 고정하지 않는다 — 위반한 두 편익 이름이 들어 있는지만 본다.
    assert "SelfConsumption" in err.reason
    assert "SurplusSale" in err.reason


@pytest.mark.req("FR-402-AC2.D")
def test_type_d_combination_labeled_excluded_without_rejection() -> None:
    """제도 한정 유형 D(REC↔잉여판매, net_metering) → 거부 없이 "배타제외" 라벨.

    유형 A 만 거부 대상이다 (COMMON.md §2③ 확인용 반대 사례). D 는 수용 수준이
    "오탐 0" 쪽이므로 예외 없이 리포트가 만들어지고, 배타 표시만 남아야 한다.
    """
    rec = REC(weight=1.0, rec_price_won_per_unit=100)
    ss = SurplusSale(sale_price_won_per_kwh=100)
    z = [0.0, 0.0, 0.0, 1000.0]
    dispatch = DispatchResult(electric=z, heat=z, cool=z, fuel=z)

    report = build_report([rec, ss], dispatch, year=1, profile="net_metering")

    excluded_states = {line.tag: line.state for line in report.excluded}
    assert excluded_states.get("REC") == "배타제외"
    assert excluded_states.get("SurplusSale") == "배타제외"


@pytest.mark.req("FR-402-AC1")
def test_self_consumption_peak_shaving_network_avoidance_co2_not_rejected() -> None:
    """FR-402-AC1 핵심 — 자가소비+피크저감+망회피+CO2 동시 활성화는 거부 안 됨.

    조항 원문: 「시스템은 자가소비+피크저감+망회피+CO2 저감의 동시 계상을
    거부하지 않는다」. 망회피·CO2 저감은 `DistributedBenefit` 의 하위 항목
    (`transmission_avoidance_won`·`ghg_reduction_won`)으로 함께 담긴다. 이
    조합은 유형 B(인과 하류)이므로 거부가 아니라 "증분만" 분류로 남아야
    한다 — 배선이 B 까지 막으면 이 테스트가 빨간불이 된다.
    """
    sc = SelfConsumption(baseline_annual_bill_won=300, new_annual_bill_won=120)
    peak = PeakShaving(
        monthly_peak_reduction_kw=[1.0] * 12, demand_charge_won_per_kw_month=5000
    )
    dist = DistributedBenefit(
        sub_items=DistributedSubItems(
            transmission_avoidance_won=1000.0, ghg_reduction_won=500.0
        )
    )

    report = build_report([sc, peak, dist], _dispatch_zeros(8760), year=1)

    accounted_tags = {line.tag for line in report.accounted}
    increment_tags = {line.tag for line in report.increment_only}
    assert "SelfConsumption" in accounted_tags
    assert "PeakShaving" in accounted_tags
    assert "DistributedBenefit" in increment_tags
    assert report.excluded == []
