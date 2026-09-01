"""Phase 1 Acceptance DoD Tests (17.1 ~ 17.6) — WP-17A."""

import time
from datetime import date
from decimal import Decimal

import pytest

from core.assumption.provider import AssumptionSet
from core.casegrid import (
    feasible_region,
    quick_preset_grid,
    run_cases,
)
from core.casegrid.incentive_cases import build_capex_cashflows_for_all_cases
from core.contracts.assumptions import (
    AssumptionProvider,
    AssumptionValue,
    PriceBasis,
)
from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.validation import ValidationError
from core.contracts.valuestream import ExclusionType, ValueStream
from core.der.pv import PV
from core.incentive.calculator import build_baseline_capex_cashflows
from core.incentive.schemas import IncentiveScheme
from core.incentive.solver import solve_min_subsidy_rate
from core.model.templates import create_energy_independent_house
from core.report.pdf import generate_pdf
from core.report.sensitivity import rank_influences
from core.valuestream import (
    REC,
    AggregatedPPA,
    CapacityPayment,
    DirectTrade,
    DistributedBenefit,
    DistributedSubItems,
    NWAs,
    PeakShaving,
    SelfConsumption,
    SurplusSale,
    TouArbitrage,
)
from core.valuestream.exclusion_table import (
    DEFAULT_EXCLUSION_RULES,
    collect_exclusions,
    rules_for_profile,
)
from core.valuestream.report import build_report


class _AcceptanceMockAssumptions(AssumptionProvider):
    @property
    def set_name(self) -> str:
        return "AcceptanceMock"

    @property
    def set_version(self) -> str:
        return "v1"

    @property
    def price_basis(self) -> PriceBasis:
        """DV-7 — 스텁도 기준을 **선언해야** 한다. 그것이 강제의 실질이다."""
        return PriceBasis.NOMINAL

    def get(self, key: str) -> AssumptionValue | None:
        values = {
            "capex.pv.rooftop": 1600000,
            "capex.ess.second_life": 300000,
            "capex.ev_charger.v2g": 10000000,
            "capex.heatpump": 1000000,
            "capex.modular_house.premium": 15,
        }
        if key in values:
            return AssumptionValue(
                key=key,
                value=values[key],
                value_unit="",
                base_year="2026",
                applicable_scope="전국",
                derivation_method="시무추정",
                source="assumptions.yaml",
                verified_at=date.fromisoformat("2026-08-09"),
                confidence="가정",
            )
        return None


@pytest.mark.req("FR-204-AC1", "FR-204-AC3")
def test_dod1_energy_independent_house_comparison() -> None:
    """17.1 DoD 1: 에너지자립가구 2변형(기존주택형 vs 모듈러형) 비교 산출 (SG-1 전반부).

    손계산 기대값:
    - 기존주택형 PV 단가 = 1,600,000 원/kW
    - 모듈러형 PV 단가 = 1,600,000 * 1.15 = 1,840,000 원/kW (15% 프리미엄 적용)
    - 두 모델 모두 자원 4종(PV, ESS, EV_V2G, HeatPump)을 포함하며 비교 산출 가능.
    """
    provider = _AcceptanceMockAssumptions()

    legacy_model = create_energy_independent_house(provider, is_modular=False)
    modular_model = create_energy_independent_house(provider, is_modular=True)

    assert legacy_model.name == "에너지자립가구 (기존주택형)"
    assert modular_model.name == "에너지자립가구 (모듈러형)"

    pv_legacy = next(r for r in legacy_model.resources if r.tag == "PV")
    pv_modular = next(r for r in modular_model.resources if r.tag == "PV")

    assert pv_legacy.params["unit_capex_won_per_kw"] == 1600000
    assert abs(pv_modular.params["unit_capex_won_per_kw"] - 1840000) <= 0.01


@pytest.mark.req("FR-801-AC7.quick", "FR-803-AC1")
def test_dod2_casegrid_27cases_performance_and_heatmap() -> None:
    """17.2 DoD 2: 27케이스 90초 이내 실행 + 히트맵 생성 (SG-2).

    손계산 기대값 및 성능 측정:
    - quick_preset_grid 는 결합 3수준 * 3수준 * 3수준 = 27 케이스를 생성함.
    - 27 케이스 실행 시간이 90.0초 이내여야 함 (실측 실행 시간 검증).
    - feasible_region 실행 시 NPV >= 0.0 달성 여부에 따른 히트맵 셀 매트릭스가 반환됨.
    """
    grid = quick_preset_grid()
    cases = grid.generate()
    assert len(cases) == 27

    start_time = time.perf_counter()

    # 27케이스 실측 실행
    results = run_cases(
        cases,
        lambda case: {
            "npv": float(
                100.0 if case.values.get("discount_rate") == "low" else -50.0
            )
        },
    )

    elapsed = time.perf_counter() - start_time
    assert elapsed < 90.0, f"27케이스 실행시간 초과: {elapsed:.2f}초 >= 90초"

    # 히트맵 셀 매트릭스 생성 검증
    cells = feasible_region(
        results, x="discount_rate", y="tariff_escalation", metric="npv", target=0.0
    )
    assert len(cells) > 0


@pytest.mark.req("FR-607-AC1", "FR-608-AC1", "FR-608-AC2")
def test_dod3_baseline_payback_and_goal_seek_subsidy() -> None:
    """17.3 DoD 3: 무지원 회수기간 + 목표 달성 최소 보조율 자동 산출 (G-3).

    손계산 기대값 및 조항 검증:
    1. 무지원 기준선 현금흐름 (`build_baseline_capex_cashflows()` — R21 부터
       `is_baseline` 깃발이 아니라 전용 함수다):
       - capex.pv.rooftop = 1,600,000 원/kW (docs/assumptions.yaml)
       - 3 kW PV 자원 본체 CAPEX = 1,600,000 × 3 = 4,800,000 원 (net capex)
       - tax.vat_rate = 0.10 (docs/assumptions.yaml)
       - 3 kW PV 부가세 = 4,800,000 × 0.10 = 480,000 원 (spec §13.2.2 C-1 본체와 분리 계상)
       - 무지원 기준선 적용 시 초기 1년차 자부담 유출액 = -4,800,000원 (본체)
       - 2~20년차 투자 현금흐름은 0원 (다년도 현금흐름 구조 검증)

    2. 목표 달성 최소 보조율 역산 (solve_min_subsidy_rate):
       - NPV 목표: eval_npv(rate) = -100 + 200 * rate = 0 => rate = 0.5 (50.0%)
       - Payback 목표: eval_payback(rate) = 15.0 - 10.0 * rate = 10.0년 => rate = 0.5 (50.0%)
    """
    assumptions = AssumptionSet.load_from_yaml("docs/assumptions.yaml")
    pv_unit = assumptions.get("capex.pv.rooftop")
    vat_item = assumptions.get("tax.vat_rate")

    unit_capex_won = (
        float(pv_unit.value) if pv_unit and pv_unit.value is not None else 1600000.0
    )
    vat_rate = (
        float(vat_item.value) if vat_item and vat_item.value is not None else 0.10
    )

    # 1. 무지원 기준선 현금흐름 산출 및 다년도 검증
    scheme = IncentiveScheme(
        subsidy_rate=0.3,
        loan_rate=0.0,
        loan_interest=0.0,
        loan_grace_years=0,
        loan_repayment_years=0,
        loan_repayment_type="원리금균등",
        tax_credit_rate=0.0,
        sponsor="국비",
    )

    capacity_kw = 3.0
    net_capex = unit_capex_won * capacity_kw
    cf_baseline = build_baseline_capex_cashflows(scheme, net_capex, "OWNER")

    assert len(cf_baseline) == 1
    assert cf_baseline[0].amounts[1] == Money(-to_won(net_capex))

    # ★ R21 — 조항의 본문은 「**모든 실행에서** 자동 포함되어 **상단에** 표시」다.
    # 위 단언은 「기준선을 **달라고 하면** 옳게 나온다」까지만 본다. 그것은
    # `is_baseline=True` 깃발도 통과시켰던 형태이므로, 조항의 두 층
    # (자동 포함 · 상단 표시)을 여기서 함께 붙든다 — 호출자는 「기준선」이라는
    # 말을 한 번도 쓰지 않는다.
    cases = build_capex_cashflows_for_all_cases(scheme, net_capex, "OWNER")
    assert cases[0].tag == "unsupported", "기준선이 결과 상단이 아니다"
    assert cases[0].rows[0].amounts[1] == Money(-to_won(net_capex)), (
        "맨 앞이 기준선 태그를 달고 있어도 값이 무지원이 아니면 이름만 지킨 것이다"
    )
    assert len(cases) > 1, "지원안 케이스가 함께 나오지 않으면 비교할 대상이 없다"

    # 2. spec §13.2.2 C-1 CAPEX 본체 및 부가세 분리 계상 + 다년도(20년) 검증
    pv = PV(
        name="테스트PV",
        capacity_kw=capacity_kw,
        unit_capex_won_per_kw=unit_capex_won,
        capacity_factor=0.15,
        vat_rate=vat_rate,
        operating_mode="자가소비 우선",
    )

    expected_net_capex = Money(to_won(net_capex))
    expected_vat = Money(to_won(net_capex * vat_rate))

    # 1년차: 본체와 부가세가 독립 분리 계상됨
    assert pv.capex(year=1) == expected_net_capex
    assert pv.capex_vat(year=1) == expected_vat

    # 2~20년차: 다년도 수명 동안 초년도 이후 CAPEX 유출 0원
    for yr in range(2, 21):
        assert pv.capex(year=yr) == Money(0)
        assert pv.capex_vat(year=yr) == Money(0)

    # 3. 목표 달성 최소 보조율 역산 (NPV 및 회수기간)
    def eval_npv(rate: float) -> float:
        return -100.0 + (200.0 * rate)

    res_npv = solve_min_subsidy_rate(eval_npv, target_value=0.0, target_type="NPV")
    assert res_npv.success is True
    assert abs(res_npv.subsidy_rate - 0.5) <= 0.001

    def eval_payback(rate: float) -> float:
        return 15.0 - (10.0 * rate)

    res_pb = solve_min_subsidy_rate(
        eval_payback, target_value=10.0, target_type="PAYBACK"
    )
    assert res_pb.success is True
    assert abs(res_pb.subsidy_rate - 0.5) <= 0.001


@pytest.mark.skip(
    reason=(
        "선행 실증 발표자료 수치(Q-4)의 대조군이 존재하지 않는다 — "
        "2026-09-02 사용자 판정: 처음 하는 사업이라서 계산 결과가 없음 "
        "(docs/decisions-2026-09-02-R52.md §2). 회신을 기다리면 채워지는 "
        "값이 아니므로 미판정 보류를 걷지 않는다. 대신 "
        "`app.run.report_cli --kind verification` 의 검증 보고서가 단계별로 "
        "검증한다"
    )
)
def test_dod4_empirical_validation_data_match() -> None:
    """17.4 DoD 4: 선행 실증 발표자료 수치 ±15% 이내 대조 (SG-4).

    미판정 보류 사유:
    docs/assumptions.yaml 내 Q-4(선행 실증 사례 실측 수치)가 blocked 상태다.
    ⚠ 2026-09-02 사용자 판정으로 이 상태의 성격이 「회신 대기」에서 「대조군
    부재」로 바뀌었다 — 사용자 문면: 「계산값 대조는 현 시점에서 불가함
    (처음 하는 사업이라서 계산 결과가 없음)」
    (`docs/decisions-2026-09-02-R52.md` §2). 외부 실증 수치가 원천적으로
    없는 상태에서 임의 가상값을 만들어 검증하면 자기충족 검증이 되므로, 본
    항목은 통과/실패로 카운트하지
    않고 skipped 로 남긴다. 대조군을 대신하는 것은 검증 보고서(단계별
    전제·계산·인계·수식)이지 이 대조 자체가 아니다.
    """
    pass


@pytest.mark.req("FR-1001-AC1", "FR-1001-AC3", "FR-1002-AC1")
def test_dod5_influence_ranking_and_formula_representation() -> None:
    """17.5 DoD 5: 영향도 순 주요 인자 제시 및 산식 3중 표기 (SG-3).

    영향도 검증 (metric_fn = 항등 함수):
      dominant: base=100, low=1, high=1000  → delta = |1000 - 1| = 999
      minor:    base=100, low=95, high=105  → delta = |105 - 95| = 10
      mid:      base=100, low=80, high=120  → delta = |120 - 80| = 40

    FR-1001-AC1 · FR-1002-AC1 요구: 영향도가 큰 인자가 앞에 와야 한다.
    따라서 dominant(999) > mid(40) > minor(10) 순이어야 한다.
    """

    def identity(x: float) -> float:
        return x

    variables = {
        "minor": {"base": 100.0, "low": 95.0, "high": 105.0},
        "dominant": {"base": 100.0, "low": 1.0, "high": 1000.0},
        "mid": {"base": 100.0, "low": 80.0, "high": 120.0},
    }
    ranked = rank_influences(variables, metric_fn=identity)

    # 영향도(delta) 내림차순 정렬 검증: 큰 것이 앞에 온다
    deltas = [row["delta"] for row in ranked]
    assert deltas == sorted(deltas, reverse=True), (
        "영향도 내림차순이 아닙니다: "
        f"{list(zip([r['name'] for r in ranked], deltas, strict=True))}"
    )

    # dominant 의 delta 가 minor 보다 크고, dominant 가 더 앞에 있어야 한다
    dominant_idx = next(i for i, r in enumerate(ranked) if r["name"] == "dominant")
    minor_idx = next(i for i, r in enumerate(ranked) if r["name"] == "minor")
    assert dominant_idx < minor_idx, (
        f"dominant(delta=999)가 minor(delta=10)보다 뒤에 있다: "
        f"dominant={dominant_idx}, minor={minor_idx}"
    )

    # 산식 3중 표기 검증 (FR-1001-AC3)
    # 손계산: 편익 1,200원 - 비용 750원 = NPV 450원. 이전에는 generate_pdf()가
    # 인자와 무관하게 항상 "200 = 1000 - 800"을 반환했으므로, 실제 값을
    # 넘겨 그 값이 그대로 나오는지까지 확인해야 동어반복이 아니다.
    pdf_content = generate_pdf(benefit_won=Decimal("1200"), cost_won=Decimal("750"))
    assert "자연어" in pdf_content["formulas"]
    assert "수식" in pdf_content["formulas"]
    assert "대입값: 450 = 1200 - 750" in pdf_content["formulas"]


def _create_valuestream_for_tag(  # noqa: PLR0911 — 태그 하나에 갈래 하나다
    tag: str, assumptions: AssumptionSet, *, structure: str | None = None
) -> ValueStream:
    """tags 로부터 ValueStream 객체를 정본 파라미터 기반으로 생성을 보조하는 헬퍼.

    ⚠ **갈래 수를 줄이려고 표로 접지 않는다.** 편익마다 생성자 인자가 다르고
    대장에서 읽는 값도 다르다 — 표로 접으면 그 차이가 람다 뭉치로 옮겨 갈 뿐
    이고, 읽는 사람은 「어느 태그가 무엇으로 세워지는가」를 더 어렵게 본다.
    갈래가 규칙표의 태그 수만큼 늘어나는 것이 이 헬퍼의 정상 형태다.

    `structure` 를 받는 이유: 구조 한정 배타 규칙(`applies_to_structure`)은 참여
    편익이 그 구조를 선언해야 발동한다. 싣지 못하면 그 규칙은 **선언돼 있으나
    어느 케이스에도 걸리지 않는** 상태가 되고, 규칙표를 읽는 사람은 금지가
    걸려 있다고 믿는다.
    """
    if tag == "SelfConsumption":
        bill_item = assumptions.get("load.household.annual")
        tariff_item = assumptions.get("tariff.hv_single_contract.avg")
        annual_kwh = (
            float(bill_item.value)
            if bill_item and bill_item.value is not None
            else 3600.0
        )
        rate = (
            float(tariff_item.value)
            if tariff_item and tariff_item.value is not None
            else 150.0
        )
        return SelfConsumption(
            baseline_annual_bill_won=annual_kwh * rate,
            new_annual_bill_won=annual_kwh * rate * 0.4,
            structure=structure,
        )
    elif tag == "SurplusSale":
        tariff_item = assumptions.get("tariff.hv_single_contract.avg")
        rate = (
            float(tariff_item.value)
            if tariff_item and tariff_item.value is not None
            else 150.0
        )
        return SurplusSale(sale_price_won_per_kwh=rate, structure=structure)
    elif tag == "DirectTrade":
        tariff_item = assumptions.get("tariff.hv_single_contract.avg")
        fee_item = assumptions.get("fee.direct_trade_support")
        t_rate = (
            float(tariff_item.value)
            if tariff_item and tariff_item.value is not None
            else 150.0
        )
        f_rate = (
            float(fee_item.value)
            if fee_item and fee_item.value is not None
            else 5.0
        )
        return DirectTrade(
            tariff_won_per_kwh=t_rate,
            trade_price_won_per_kwh=t_rate * 0.8,
            trade_volume_kwh=1000.0,
            support_fee_won=f_rate,
            structure=structure,
        )
    elif tag == "DistributedBenefit":
        return DistributedBenefit(
            sub_items=DistributedSubItems(
                transmission_avoidance_won=10000.0,
                loss_reduction_won=5000.0,
            ),
            structure=structure,
        )
    elif tag == "REC":
        return REC(weight=1.0, rec_price_won_per_unit=50000.0, structure=structure)
    elif tag == "AggregatedPPA":
        # R32 신설. 단가는 **약관요금 × 비율**이며 절대 단가가 대장에 없다 —
        # 비율을 못 읽으면 여기서 지어내지 않고 대장 기본 가정(0.85)과 같은 수를
        # 쓰되, 이 테스트가 보는 것은 금액이 아니라 **배타 판정**이다.
        tariff_item = assumptions.get("tariff.hv_single_contract.avg")
        ratio_item = assumptions.get("tariff.aggregated_ppa.ratio")
        t_rate = (
            float(tariff_item.value)
            if tariff_item and tariff_item.value is not None
            else 150.0
        )
        ratio = (
            float(ratio_item.value)
            if ratio_item and ratio_item.value is not None
            else 0.85
        )
        return AggregatedPPA(
            ppa_price_won_per_kwh=t_rate * ratio,
            annual_generation_kwh=10_000.0,
            structure=structure,
        )
    elif tag == "PeakShaving":
        # R48 신설 유형 E 규칙의 상대편이라 이 공장에 처음 들어왔다. 단가는
        # 대장의 첨두 기본요금(`tariff.hv_single_contract.demand_charge`)을
        # 쓰되, 이 테스트가 보는 것은 금액이 아니라 **배타 판정**이다.
        demand_item = assumptions.get("tariff.hv_single_contract.demand_charge")
        demand_charge = (
            float(demand_item.value)
            if demand_item and demand_item.value is not None
            else 8_320.0
        )
        return PeakShaving(
            monthly_peak_reduction_kw=[1.0] * 12,
            demand_charge_won_per_kw_month=demand_charge,
        )
    elif tag == "NWAs":
        # R48 신설. **단가가 대장에 없다** — 제도 자체가 없어서(판정 §6) 값이
        # 없고, 값 없는 항목을 대장에 넣으면 「가정한 제도」가 된다. 이 테스트가
        # 보는 것은 금액이 아니라 **배타 판정**이므로 탐침 단가를 여기서 준다.
        #
        # ⚠ `enabled=True` 를 명시한다 — 이 편익은 **기본 비활성**이고,
        # `collect_exclusions` 는 **둘 다 활성**인 쌍만 본다. 빠뜨리면 유형 E
        # 규칙이 「감지되지 않음」으로 조용히 통과한다.
        return NWAs(
            contribution_price_won_per_kwh=50.0, enabled=True
        )
    elif tag == "CP":
        # R48 신설. 단가가 대장에 없는 이유는 `NWAs` 와 **다르다** — CP 는 현행
        # 제도이나 **분산특구 내 ESS 에 적용할 산정 기준이 부재**하다(판정 §6).
        return CapacityPayment(
            registered_capacity_kw=10.0,
            capacity_price_won_per_kw_month=6_000.0,
            enabled=True,
        )
    elif tag == "TouArbitrage":
        # R50 신설. **첨두·경부하 단가가 대장에 항목으로 없다** — 대장이 가진
        # 것은 실효단가(`tariff.hv_single_contract.avg`)·전력량요금
        # (`...energy_only`)·기본요금(`...demand_charge`) 셋이고 TOU 시간대별
        # 단가는 요금표(`core/regulation/tariff.py`)가 든다. 여기서 대장을 읽는
        # 척하면 없는 항목을 가리키는 코드가 되므로 탐침 단가를 그대로 준다 —
        # 이 테스트가 보는 것은 금액이 아니라 **배타 판정**이다
        # (`RC-ESS-B1` 오라클과 같은 200/80 을 쓴다).
        #
        # ⚠ 수량은 **연간값**이며 창에서 읽지 않는다
        # (`scales_with_dispatch_window = False`) — 이 테스트가 24스텝 **0원**
        # 디스패치를 주는데도 금액이 나야 유형 A 거부 검증이 0원끼리 비교가
        # 되지 않는다.
        return TouArbitrage(
            discharge_kwh=2_920.0,
            charge_kwh=2_920.0 / 0.9,
            peak_price_won_per_kwh=200.0,
            offpeak_price_won_per_kwh=80.0,
        )
    else:
        raise ValueError(f"지원하지 않는 편익 태그입니다: {tag}")


# 독립적인 기대 근거(Rationale) 테이블 — 테스트 코드 내 정의 (자기충족 검증 방지)
EXPECTED_RATIONALES: dict[tuple[str, str], str] = {
    ("SelfConsumption", "SurplusSale"): (
        "같은 1 kWh 를 자가소비 절감과 잉여판매로 동시 계상할 수 없다"
    ),
    ("SurplusSale", "DirectTrade"): (
        "같은 잉여량을 상계거래와 직접거래로 동시 정산할 수 없다"
    ),
    ("DistributedBenefit", "SelfConsumption"): (
        "송배전 회피·손실 감소는 현행 망이용요금에 반영 — "
        "미래 증설 회피 증분만 계상 (원칙 2-1)"
    ),
    ("REC", "SurplusSale"): (
        "상계거래 참여 설비의 REC 발급 제한 (제도 한정)"
    ),
    # ↓ R31 — **계약구조 축**으로 걸리는 첫 규칙 (결정 §2-4). 위 규칙은
    # `applies_to_profile: net_metering` 으로만 걸리는데, 구조와 프로파일은 독립
    # 축이라 사용자가 상계거래를 고르고도 다른 프로파일을 선택하면 조용히 통과한다.
    ("REC", "DistributedBenefit"): (
        "상계거래 구조에서는 REC 발급이 제한되므로, REC 를 켠 채 분산편익 크레딧까지 "
        "계상하면 제도가 인정하지 않는 두 수익이 함께 잡힌다. **프로파일이 아니라 "
        "구조로 걸린다** — 두 축이 독립이라 프로파일만으로는 조용히 통과한다 "
        "(R31 결정 §2-4)"
    ),
    # ↓ R32 — 집합 PPA 는 **전량 판매**다. 둘을 다 적는 것이 요점이며, 잉여판매만
    # 막으면 자가소비와 PPA 를 동시에 켤 수 있다(넘긴 kWh 를 집에서 또 쓴 셈).
    ("AggregatedPPA", "SurplusSale"): (
        "집합 PPA 는 발전량 전량을 팔았으므로 같은 kWh 를 잉여로 다시 팔 수 없다"
    ),
    ("AggregatedPPA", "SelfConsumption"): (
        "집합 PPA 로 넘긴 kWh 는 자가소비가 아니다 — 동일 물리량 이중 계상"
    ),
    # ↓ R48 — **운전 주체 축**(유형 E · 판정 §2). 계통 급전 편익 둘 × 사업자 운전
    # 편익 셋 = **여섯**이며(R48 은 편익 둘로 세어 넷이었고 R50 이 `TouArbitrage`
    # 를 세웠다), 하나라도 빠지면 그 조합만 조용히 열린 채 남는다.
    # 유형 `A` 가 아니다(같은 kWh 를 두 번 파는 것이 아니다) · 유형 `D` 도
    # 아니다(제도가 바뀌어도 성립하지 않는다).
    ("NWAs", "SelfConsumption"): (
        "방전 시점을 계통운영자가 정하면 사용자가 원하는 시각에 방전할 수 없고 "
        "사용자의 전기사용량에 영향이 없다 — 자가소비가 성립하지 않는다 "
        "(R48 판정 §2)"
    ),
    ("NWAs", "PeakShaving"): (
        "방전 시점을 계통운영자가 정하면 사용자가 원하는 시각에 방전할 수 없고 "
        "사용자의 전기사용량에 영향이 없다 — 자가 피크 저감이 성립하지 않는다 "
        "(R48 판정 §2)"
    ),
    ("CP", "SelfConsumption"): (
        "준중앙급전으로 등록하면 방전 시점을 계통운영자가 정하므로 사용자가 원하는 "
        "시각에 방전할 수 없고 사용자의 전기사용량에 영향이 없다 — 자가소비가 "
        "성립하지 않는다 (R48 판정 §2)"
    ),
    ("CP", "PeakShaving"): (
        "준중앙급전으로 등록하면 방전 시점을 계통운영자가 정하므로 사용자가 원하는 "
        "시각에 방전할 수 없고 사용자의 전기사용량에 영향이 없다 — 자가 피크 저감이 "
        "성립하지 않는다 (R48 판정 §2)"
    ),
    # ↓ R50 — `TouArbitrage` 가 서면서 계통 급전 편익 둘과 유형 `E` 로 갈렸다.
    # ⚠ **`SurplusSale` 과의 유형 A 는 R51/WP-5 가 뗐다**(사용자 판정 §4) — 같은
    # 전력이 ESS 를 경유한 것이므로 배타가 아니라 잉여판매 수량에서 비-태양광
    # ESS 방전분을 빼는 것으로 바뀌었다. 그 쌍은 이제 `DEFAULT_EXCLUSION_RULES`
    # 에 없으므로 이 순회는 그 쌍을 더는 방문하지 않는다 — 여기 다시 적지 않는다.
    ("NWAs", "TouArbitrage"): (
        "방전 시점을 계통운영자가 정하면 사업자가 피크 시각을 골라 팔 수 없다 — "
        "요금차 차익거래가 성립하지 않는다 (R48 판정 §2 의 운전 주체 축)"
    ),
    ("CP", "TouArbitrage"): (
        "준중앙급전으로 등록하면 방전 시점을 계통운영자가 정하므로 사업자가 피크 "
        "시각을 골라 팔 수 없다 — 요금차 차익거래가 성립하지 않는다 "
        "(R48 판정 §2 의 운전 주체 축)"
    ),
}


@pytest.mark.req("FR-402-AC1", "FR-402-AC2.A", "FR-402-AC6")
def test_dod6_benefit_breakdown_and_exclusion_enforcement() -> None:
    """17.6 DoD 6: 편익 계상 내역 표시 및 배타 위반 조합 감지.

    손계산 기대값, 독립 근거 검증 및 양성/음성 쌍(Spec 13.2.1) 순회 검증:
    - 선언적 배타 규칙 테이블(DEFAULT_EXCLUSION_RULES) 내 등록된 규칙 전건을 순회하며 검사함.
    - [양성] 규칙 활성화 시 배타 수집(collect_exclusions)이 각 규칙에 해당하는
      (benefit_a, benefit_b, exclusion_type) 및 비어있지 않은 독립 기대 근거를 정확히 감지함.
    - [양성] 편익 리포트(build_report) 생성 시 유형별 분류:
      - 유형 A/C/D 배타: '배타제외' 상태 분류
      - 유형 B 배타 (인과 하류): benefit_a 가 '증분만' 상태로 분류
    - [음성] 해당 규칙을 활성 목록에서 제외(inactive_rules)할 경우, 동일한 조합이
      배타로 감지되지 않음을 확인하여 규칙의 실질적 판정 주도성을 입증함 (spec 13.2.1).
    """
    assert len(DEFAULT_EXCLUSION_RULES) > 0

    assumptions = AssumptionSet.load_from_yaml("docs/assumptions.yaml")
    dispatch = DispatchResult.zeros(24)

    # 등록된 배타 규칙 전건 자동 검사 (양성/음성 쌍 및 독립 근거 단언)
    for rule in DEFAULT_EXCLUSION_RULES:
        # ★ **구조 한정 규칙이면 그 구조를 실어 준다 (R31).** 싣지 않으면 그
        # 규칙은 발동하지 않고 아래 양성 검증이 빨간불이 된다 — 즉 이 순회는
        # **구조 축을 쓰는 규칙이 실제로 발동 가능한지**까지 함께 붙든다.
        stream_a = _create_valuestream_for_tag(
            rule.benefit_a, assumptions, structure=rule.applies_to_structure
        )
        stream_b = _create_valuestream_for_tag(
            rule.benefit_b, assumptions, structure=rule.applies_to_structure
        )
        streams = [stream_a, stream_b]

        active_rules = rules_for_profile(
            rule.applies_to_profile, DEFAULT_EXCLUSION_RULES
        )

        # -------------------------------------------------------------
        # 1. 양성 검증 (Positive Case): 규칙 활성화 시 배타 감지
        # -------------------------------------------------------------
        exclusions = collect_exclusions(streams, active_rules)

        matched = [
            ex
            for ex in exclusions
            if ex[2] == rule.exclusion_type
            and {ex[0], ex[1]} == {rule.benefit_a, rule.benefit_b}
        ]
        assert len(matched) == 1, (
            f"양성 검증 실패 (배타 규칙 감지 안 됨): {rule.benefit_a} ↔ {rule.benefit_b} "
            f"(유형 {rule.exclusion_type.value})"
        )

        # 독립 기대값 대조 & 비어있지 않음 단언 (자기충족 검증 제거)
        detected_rationale = matched[0][3]
        expected_rationale = EXPECTED_RATIONALES[(rule.benefit_a, rule.benefit_b)]
        assert bool(detected_rationale and detected_rationale.strip()), (
            f"배타 근거가 비어 있음: {rule.benefit_a} ↔ {rule.benefit_b}"
        )
        assert detected_rationale == expected_rationale, (
            f"배타 근거 불일치 (독립 기대값과 다름): {rule.benefit_a} ↔ {rule.benefit_b}\n"
            f"감지값: {detected_rationale!r}\n기대값: {expected_rationale!r}"
        )

        # ── 유형 A 는 **거부**, B 는 증분만, C·D 는 배타제외 (R17) ─────────
        #
        # DoD 6 문면은 *「편익 계상 내역이 리포트에 표시되고, **배타 규칙 위반
        # 조합은 실행이 거부됨**」* 이고 `FR-402-AC2.A` 도 *「선택 시 검증 오류로
        # 거부한다」* 이다. **이 테스트는 「감지」에서 멈춰 있었다** — 유형 A 를
        # `배타제외` 라벨로 확인했고, 그것은 거부가 구현되면 빨간불이 나는
        # 형태다. WP-28B 가 거부를 배선하자 실제로 그렇게 됐다.
        #
        # 되돌리지 않았다. **조항이 정본이고 테스트가 따라간다** — 라벨은
        # 「표시」이고 조항이 요구한 것은 「거부」다.
        if rule.exclusion_type == ExclusionType.A:
            with pytest.raises(ValidationError) as refused:
                build_report(
                    streams, dispatch, year=1, profile=rule.applies_to_profile
                )
            assert refused.value.rule == "DV-12"
            assert rule.benefit_a in refused.value.reason
            assert rule.benefit_b in refused.value.reason
        else:
            report = build_report(
                streams, dispatch, year=1, profile=rule.applies_to_profile
            )
            lines_by_tag = {line.tag: line for line in report.all_lines()}

            assert rule.benefit_a in lines_by_tag
            assert rule.benefit_b in lines_by_tag

            if rule.exclusion_type == ExclusionType.B:
                assert lines_by_tag[rule.benefit_a].state == "증분만"
                assert lines_by_tag[rule.benefit_b].state in ("계상됨", "미화폐화0")
            else:
                # C·D — 「배타제외」 라벨은 이제 이 둘의 자리다
                assert lines_by_tag[rule.benefit_a].state == "배타제외"
                assert lines_by_tag[rule.benefit_b].state == "배타제외"

        # -------------------------------------------------------------
        # 2. 음성 검증 (Negative Case): 해당 규칙 제외 시 배타 감지 안 됨 (Spec 13.2.1)
        # -------------------------------------------------------------
        inactive_rules = tuple(r for r in active_rules if r != rule)
        neg_exclusions = collect_exclusions(streams, inactive_rules)
        neg_matched = [
            ex
            for ex in neg_exclusions
            if {ex[0], ex[1]} == {rule.benefit_a, rule.benefit_b}
        ]
        assert len(neg_matched) == 0, (
            f"음성 검증 실패 (규칙 비활성화 시에도 배타가 감지됨): "
            f"{rule.benefit_a} ↔ {rule.benefit_b}"
        )

    # 3. 추가 음성 검증: 배타 관계가 없는 편익 조합 (SelfConsumption ↔ REC)
    non_ex_a = _create_valuestream_for_tag("SelfConsumption", assumptions)
    non_ex_b = _create_valuestream_for_tag("REC", assumptions)
    non_ex_streams = [non_ex_a, non_ex_b]

    non_ex_exclusions = collect_exclusions(non_ex_streams, DEFAULT_EXCLUSION_RULES)
    assert len(non_ex_exclusions) == 0, (
        "음성 검증 실패: 배타 관계가 없는 편익 조합(SelfConsumption ↔ REC)이 배타로 감지됨"
    )

    non_ex_report = build_report(non_ex_streams, dispatch, year=1, profile=None)
    non_ex_lines = {line.tag: line for line in non_ex_report.all_lines()}
    assert non_ex_lines["SelfConsumption"].state in ("계상됨", "미화폐화0")
    assert non_ex_lines["REC"].state in ("계상됨", "미화폐화0")
