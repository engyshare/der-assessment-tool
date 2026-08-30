"""8.3 — 배타 유형 판정. **A 차단 100%(음성)** 와 **B~E 오탐 0(양성)** 를
별도 테스트로 쪼갰다 (판단 ① 결론).

쪼갠 이유: 검사 방향이 반대다.
- A (동일 물리량 이중 판매): 위반을 심어 «잡히는가» 본다 — 음성.
- B~E: 정당한 동시 편익을 «안 지워지는가» 본다 — 양성.
한 테스트에 섞이면 A 의 음성 케이스가 B~E 의 양성 검증을 망가뜨린다.

**FR-402-AC1 핵심**: 동시 발생하는 정당한 편익(자가소비+피크저감+망회피+CO2)
을 «정상 계상» 함을 반드시 확인 — 배타를 넓게 잡으면 그것들이 지워지고,
지워진 편익은 결과에 나타나지 않아 스스로 드러나지 않는다.
"""
from __future__ import annotations

import pytest

from core.contracts.valuestream import ExclusionType
from core.valuestream import (
    REC,
    DirectTrade,
    DistributedBenefit,
    HeatCostSaving,
    PeakShaving,
    SelfConsumption,
    SurplusSale,
)
from core.valuestream.exclusion_loader import load_exclusion_rules_from_text
from core.valuestream.exclusion_table import (
    DEFAULT_EXCLUSION_RULES,
    collect_exclusions,
    find_rule,
    rules_for_profile,
)


def _all_active(*streams: object) -> list[object]:
    return list(streams)


# ── 유형 A — 동일 물리량 이중 판매, 차단 100% (음성) ─────────────────────
# FR-402-AC2.A: 위반을 심었을 때 반드시 잡혀야 한다.

@pytest.mark.req("FR-402-AC2.A")
def test_type_a_self_consumption_vs_surplus_sale_is_caught() -> None:
    """자가소비 + 잉여판매 동시 활성 → 배타 쌍이 잡혀야 한다.

    오라클: 순위 4 (§13.0.1 ④ — 검사가 무언가를 검사했는가). 같은 kWh 를
    두 용도로 쓸 수 없으므로(유형 A) collect_exclusions 가 반드시 반환.
    """
    sc = SelfConsumption(baseline_annual_bill_won=300, new_annual_bill_won=120)
    ss = SurplusSale(sale_price_won_per_kwh=100)
    pairs = collect_exclusions(_all_active(sc, ss))
    assert any(
        (
            (a == "SelfConsumption" and b == "SurplusSale")
            or (a == "SurplusSale" and b == "SelfConsumption")
        )
        and t is ExclusionType.A
        for a, b, t, _ in pairs
    ), f"유형 A 배타가 잡히지 않았다: {pairs}"


@pytest.mark.req("FR-402-AC2.A")
def test_type_a_surplus_vs_direct_trade_is_caught() -> None:
    """잉여판매(상계) + 직접거래 동시 → 같은 잉여량 두 제도 정산 불가 (유형 A)."""
    ss = SurplusSale(sale_price_won_per_kwh=100)
    dt = DirectTrade(
        tariff_won_per_kwh=200, trade_price_won_per_kwh=150,
        trade_volume_kwh=100,
    )
    pairs = collect_exclusions(_all_active(ss, dt))
    assert any(t is ExclusionType.A for _, _, t, _ in pairs)


def test_type_a_symmetric_lookup_works_both_directions() -> None:
    """find_rule 은 양방향 대칭 — (A,B) 나 (B,A) 나 같은 규칙."""
    r1 = find_rule("SelfConsumption", "SurplusSale")
    r2 = find_rule("SurplusSale", "SelfConsumption")
    assert r1 is not None and r2 is not None
    assert r1 is r2  # 같은 객체


# ── 유형 B~D — 오탐 0 (양성). 정당한 동시 편익이 지워지지 않는다 ─────────
# FR-402-AC1: 동시 발생 효과는 중복이 아니다 — 정상 계상한다.

@pytest.mark.req("FR-402-AC1")
def test_simultaneous_distinct_payer_benefits_are_not_excluded() -> None:
    """**핵심 케이스** — 자가소비(RESIDENT) + REC(OPERATOR) + 피크저감(RESIDENT) +
    열비용절감(RESIDENT) 동시 계상은 정상이다.

    오라클: 순위 4 (검사 정합 — §13.0.1 ④). 지불 주체가 같아도 **물리량이 다르면**
    중복이 아니다 (도메인 원칙 §2). 이 네 편익이 동시에 발생하는 것은 «정상 계상»
    되어야 한다 — 그것이 FR-402-AC1 이다. 배타 규칙이 넓으면 이것들이 지워진다.

    자가소비(kWh·전력량요금) 와 피크저감(kW·기본요금) 은 물리량이 다르다.
    REC(발전량·REC단가) 와 자가소비(소비량·요금단가) 는 같은 발전을 다른 용도로.
    열비용절감(열·연료비) 은 전기와 매체가 다르다.

    `FR-402-AC2.C` 마커는 R37 에서 뗐다 — 이 테스트에는 `tCO2`·배출권 수익·사회적
    탄소비용·관점 전환이 없다. `AC2.C` 는 *같은 tCO2 를 관점을 바꿔가며 두 산식으로
    화폐화하는 것*을 막는 조항(위임: `FR-704`)이고, 여기서 재는 것은 위 독스트링이
    스스로 적은 대로 `FR-402-AC1` 이다. **다시 붙이지 마라** — ID 가 실재하면
    `gen_traceability` 는 「검증됨」으로 세므로, 재지 않는 인용은 조용히 매핑표를
    부풀린다.
    """
    sc = SelfConsumption(baseline_annual_bill_won=300, new_annual_bill_won=120)
    rec = REC(weight=1.0, rec_price_won_per_unit=50_000)
    peak = PeakShaving(
        monthly_peak_reduction_kw=[1.0] * 12, demand_charge_won_per_kw_month=5000
    )
    heat = HeatCostSaving(
        baseline_fuel_cost_won_per_year=200, hp_electricity_cost_won_per_year=80
    )
    pairs = collect_exclusions(_all_active(sc, rec, peak, heat))
    # 이 네 쌍에는 배타 규칙이 없다 — collect_exclusions 는 빈 목록을 돌려야.
    assert pairs == [], (
        f"정당한 동시 편익이 배타로 잡혔다 — 오탐이다 (FR-402-AC1 위반): {pairs}. "
        "배타 규칙이 넓으면 동시 발생하는 정당한 편익이 지워지고, 지워진 편익은 "
        "결과에 나타나지 않아 스스로 드러나지 않는다"
    )


@pytest.mark.req("FR-402-AC2.B")
def test_type_b_distributed_benefit_vs_self_consumption_is_caught() -> None:
    """유형 B — 분산편익(망회피) ↔ 자가소비(요금절감). 둘 다 활성이면 잡힌다.

    오라클: 순위 4. 망 비용은 현행 망이용요금에 이미 반영되어 있으므로,
    SelfConsumption 의 절감액 안에 망 비용 회피가 일부 들어 있다. 유형 B 는
    «전액» 이 아니라 «미래 증설 회피 증분만» 계상한다 (원칙 2-1).
    """
    sc = SelfConsumption(baseline_annual_bill_won=300, new_annual_bill_won=120)
    dist = DistributedBenefit()  # 값은 0이지만 활성화됨 — 규칙 매칭은 enabled 로
    pairs = collect_exclusions(_all_active(sc, dist))
    assert any(t is ExclusionType.B for _, _, t, _ in pairs), (
        f"유형 B 배타가 잡히지 않았다: {pairs}"
    )


@pytest.mark.req("FR-402-AC2.D")
def test_profile_scoped_rule_d_applies_only_with_profile() -> None:
    """유형 D — 제도 한정 규칙(REC↔SurplusSale, profile=net_metering).

    오라클: 순위 4. profile=None 이면 제도 한정 규칙은 빠진다 (보수적 —
    모르면 적용 안 함이 아니라, FR-402-AC1 오탐 회피를 위해 «모든 프로파일»
    규칙만 돈다). profile=net_metering 이면 잡힌다.
    """
    rec = REC(weight=1.0, rec_price_won_per_unit=100)
    ss = SurplusSale(sale_price_won_per_kwh=100)

    # profile=None → net_metering 규칙 제외 → REC↔SurplusSale 배타 없음
    pairs_no_profile = collect_exclusions(
        _all_active(rec, ss), rules_for_profile(None)
    )
    assert not any(
        (a == "REC" and b == "SurplusSale") or (a == "SurplusSale" and b == "REC")
        for a, b, _, _ in pairs_no_profile
    )

    # profile=net_metering → 규칙 포함 → 잡힘
    pairs_with_profile = collect_exclusions(
        _all_active(rec, ss), rules_for_profile("net_metering")
    )
    assert any(
        t is ExclusionType.D
        for a, b, t, _ in pairs_with_profile
        if {a, b} == {"REC", "SurplusSale"}
    )


def test_inactive_stream_does_not_trigger_exclusion() -> None:
    """비활성 편익은 배타 쌍에서 빠진다 — 한 쪽이 꺼졌으면 충돌 아니다.

    오라클: 순위 4. SurplusSale(enabled=False) + SelfConsumption(enabled=True)
    → 잉여판매가 없으므로 자가소비와 경쟁하지 않는다.
    """
    sc = SelfConsumption(baseline_annual_bill_won=300, new_annual_bill_won=120)
    ss = SurplusSale(sale_price_won_per_kwh=100, enabled=False)
    pairs = collect_exclusions(_all_active(sc, ss))
    assert pairs == []


def test_default_rules_are_a_tuple_immutable() -> None:
    """DEFAULT_EXCLUSION_RULES 는 tuple — 가변 list 면 런타임에 규칙이 바뀐다 (NFR-205).

    오라클: 순위 4 (NFR-205 정합).
    """
    assert isinstance(DEFAULT_EXCLUSION_RULES, tuple)


# ── 유형 E — 동시에 성립할 수 없는 운전 (R48 §2) ─────────────────────────


@pytest.mark.req("FR-402-AC2.E")
def test_type_e_exists_and_is_not_borrowed_from_a_or_d() -> None:
    """배타 유형에 `E`(동시에 성립할 수 없는 운전)가 **선다**.

    R48 사용자 판정 §2 가 세운 축은 **계통 급전(CP·NWAs) × 사용자 운전
    (SelfConsumption·PeakShaving)** 이며, 그것은 A~D 중 어느 것도 아니다:

        A 가 아니다   같은 kWh 를 두 번 파는 것이 아니다 — 물리량이 겹치지
                      않아도 성립하지 않는다
        D 가 아니다   제도가 금지하는 것이 아니다 — 제도가 바뀌어도 성립하지
                      않는다

    유형을 빌려 쓰면 근거 문장이 거짓이 되고, 제도 개정 때 *「제도가 바뀌었으니
    풀린다」* 로 잘못 읽힌다.

    ⚠ **규칙 행은 여기서 재지 않는다** — `docs/exclusion-rules.yaml` 이 규칙의
    정본이고(FR-402-AC4) 그 행은 별도 작업이 넣는다. 이 검사가 재는 것은
    **유형이 있고 로더가 그것을 받는가**다.
    """
    assert "E" in {t.value for t in ExclusionType}, (
        "ExclusionType 에 유형 E 가 없습니다 (R48 §2). 값은 spec 조항 키 "
        "`FR-402-AC2.E`·`docs/exclusion-rules.yaml` 의 `type:`·DB enum 이 함께 "
        "쓰는 리터럴이므로 한 글자 «E» 여야 합니다"
    )
    assert ExclusionType("E") is ExclusionType.E


@pytest.mark.req("FR-402-AC2.E")
def test_loader_accepts_type_e_rows() -> None:
    """로더가 `type: E` 행을 **읽는다** — 유형만 세우고 로더를 안 고치면

    규칙을 넣는 쪽이 「배타 유형이 A~E 가 아닙니다」로 막힌다. 유형과 그것을
    받는 문(門)은 같은 변경에 있어야 한다 (spec §16.2).
    """
    rules = load_exclusion_rules_from_text(
        "version: 1\n"
        "rules:\n"
        "  - {benefit_a: X, benefit_b: Y, type: E, rationale: 운전 주체가 다르다}\n"
    )
    assert len(rules) == 1
    assert rules[0].exclusion_type is ExclusionType.E
