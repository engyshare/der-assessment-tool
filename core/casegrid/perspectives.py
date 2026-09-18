"""관점 넷을 배포 경로에 배선한다 — R52/WP-A.

## 왜 이 모듈이 생겼는가 — **기계는 있었는데 배포 코드가 0곳이었다**

`core/cba/perspective.py` 의 `Perspective`·`compute_perspective_npv` 와
`core/report/perspective_report.py` 의 `build_parallel_perspective_report()` 는
이미 서 있었다. 그런데 `run_single_case_e2e()`(배포 경로의 실제 진입점)가 그
기계를 부르는 자리는 0곳이었다 — `status.md` 「함정」 절 맨 위 항, R51/WP-7 이
잡은 것과 같은 형태다. 이 모듈이 그 배선이다.

## ★★★ 관점별 편익 집합 — `payer` 가 정본이다. 발명하지 않는다

이 저장소는 편익마다 「지불 주체」(`Payer`)를 이미 선언해 두었다(`DV-13`·
`FR-402-AC5`). **한 관점의 편익 = `effective_payer` 가 그 관점인 편익** —
새 매핑을 만들지 않는다(사용자 판정 `docs/decisions-2026-09-02-R52b.md` §1·
R52/WP-A 판정 아-3). `s.payer` 가 아니라 `s.effective_payer` 를 읽는 이유는
`payer_by_structure` 로 계약구조에 따라 주체가 갈리는 편익(`SurplusSale` 등)이
있기 때문이다 — 모듈 상수(`payer`)만 읽으면 그 구조별 귀속이 무시된다
(`core/valuestream/report.py::build_report` 가 같은 이유로 `effective_payer`
를 쓴다).

## ★★★ 사업자(`OPERATOR`) 열은 **결론축 그대로다** — 다시 계산하지 않는다

R52/WP-A 판정 아-7: *「결론축이 움직이면 안 된다」*. 그래서 `OPERATOR`
`PerspectiveResult` 는 `payer` 로 새로 거른 편익이 아니라 **이 실행이 이미
낸 편익 전체·비용 전체·초기투자**를 그대로 담고, `npv_value` 도 호출측
(`core/casegrid/case_metrics.py::metrics_for`)과 **같은 재료**(편익 전체·비용
전체·초기투자·할인율)로 `net_operating_flows()` → `npv()` 를 다시 불러
얻는다 — 재료가 같으므로 이 결과는 대수적으로 `metrics_for()` 의 `"npv"` 와
같아야 한다.
`compute_perspective_npv()` 를 쓰지 않는 이유는 그 함수가 `cost_rows` 를
NPV 계산에 넣지 않기 때문이다(관점별 「자부담」모형 — `PerspectiveResult`
독스트링 참조) — 그대로 쓰면 비용이 두 번 빠지거나(넣지 않아서) 결론축과
어긋난다.

## ★★ `RESIDENT`·`GOVERNMENT`·`SOCIETY` — 비용을 발명하지 않는다

세 관점은 `cost_rows=()`·`initial_investment=Money(0)` 으로 낸다(R52/WP-A
판정 아-5: *「요금 이전 제외·사회적 할인율·외부효과 화폐화를 발명하지
마라」*). 이 저장소는 참여 주민·정부·사회가 이 사업의 초기투자·운영비 중
얼마를 부담하는지 선언한 자료가 없다 — 없는 것을 지어 넣는 대신 **편익만
관점별로 가르고, 비용 배분은 다음 라운드의 몫으로 비워 둔다.** 그 결과
세 관점의 NPV 는 「그 관점에 귀속되는 편익의 현재가치」이지 「그 관점의
순손익」이 아니다 — `result_A.md` 가 이 가정을 적는다.

## ⚠⚠ `GRID_OPERATOR`·`POWER_MARKET` 은 관점 넷 중 어디에도 없다

`NWAs`(배전사업자)·`CapacityPayment`(전력시장)는 `Payer` 독스트링(R50)이
*「다른 지갑」* 이라 적은 그대로 **관점 넷 밖**이다. 억지로 사업자·사회에
밀어 넣지 않는다 — `OutsideWalletBenefit` 로 따로 담아 리포트가 그 사실을
명시하게 한다.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from core.casegrid.operating_lines import net_operating_flows
from core.cba.metrics import npv
from core.cba.perspective import (
    Perspective,
    PerspectiveInclusions,
    PerspectiveResult,
    assert_subsidy_excluded_from_society,
    compute_perspective_npv,
    society_excludes_subsidy,
    society_excludes_transfers,
)
from core.cba.proforma import benefit_row, escalation_factor
from core.contracts.der import DispatchResult
from core.contracts.schemas import CashFlowRow
from core.contracts.units import ZERO, Money, to_won
from core.contracts.valuestream import Payer, ValueStream
from core.valuestream.distributed_benefit import DistributedBenefit, DistributedSubItems

#: `payer` 값 → 관점. `OPERATOR` 는 없다 — 그 열은 결론축을 그대로 쓰고
#: 이 표로 다시 거르지 않는다(위 머리말). `MappingProxyType` — 모듈 수준
#: 가변 컨테이너 금지(`tests/ci/test_ci_gates.py::test_no_module_or_
#: class_level_mutable_containers`, FR-805 병렬 실행 안전).
_PAYER_TO_PERSPECTIVE: MappingProxyType[Payer, Perspective] = MappingProxyType({
    Payer.RESIDENT: Perspective.RESIDENT,
    Payer.GOVERNMENT: Perspective.GOVERNMENT,
    Payer.SOCIETY: Perspective.SOCIETY,
})

#: 관점 넷 중 어디에도 들어가지 않는 지갑 (`Payer` 독스트링 R50).
OUTSIDE_PERSPECTIVE_PAYERS: tuple[Payer, ...] = (Payer.GRID_OPERATOR, Payer.POWER_MARKET)


@dataclass(frozen=True)
class OutsideWalletBenefit:
    """관점 넷 밖의 지갑에서 나오는 편익 한 줄 — 리포트가 명시로 적어야 한다."""

    tag: str
    payer: Payer
    annual_won: int


@dataclass(frozen=True)
class TransferFlow:
    """이전(transfer) 흐름 한 줄 — 양쪽 관점에 부호 반대로 서기 위한 자료.

    왜 이 자리가 필요한가 (R58 판정 ③): 내는 쪽이 `OPERATOR` 인 이전이 오면
    `OPERATOR` 열에 `-` 행을 세우고 싶어지는데, 그 열은 결론축 그대로여야 한다
    (결론축 재계산 금지). 그래서 결론축을 건드리지 않으면서 「관점별 표에서
    소거하지 않고 부호를 반대로 적는다」를 리포트 쪽에서 이룰 수 있게 그 자료를 세운다.
    """

    tag: str
    from_payer: Payer
    to_payer: Payer
    annual_won: int


@dataclass(frozen=True)
class PerspectiveWiring:
    """한 실행의 관점 넷 결과 + 관점 밖 편익 — `CaseOutcome.perspectives`."""

    #: 사회·참여 주민·사업자·정부 넷 (순서는 호출측이 정하지 않는다 —
    #: `build_parallel_perspective_report()` 가 `REQUIRED_PERSPECTIVES` 순으로
    #: 다시 정렬한다).
    results: tuple[PerspectiveResult, ...]
    outside: tuple[OutsideWalletBenefit, ...]
    transfers: tuple[TransferFlow, ...] = ()


def build_society_annualised(
    sub_items: DistributedSubItems | None = None,
) -> tuple[tuple[ValueStream, int], ...]:
    """대장 다섯 칸을 그대로 받아 `DistributedBenefit` 스트림을 짓는다 (R54/WP-3).

    ``build_perspective_wiring()`` 의 ``society_annualised`` 로만 들어간다 —
    `annualised`(결론축 재료)에는 절대 섞지 않는다(위 머리말 「사업자 열은
    결론축 그대로다」, R53/WP-1 판정 ①). 이 함수는 러너의 `annualised`·
    `annual_benefit`·`benefit_rows` 를 하나도 건드리지 않는다.

    ⚠ 대장(`benefit.distributed_credit.*`)이 다섯 칸으로 나뉘었다(R54/WP-3
    판정 ①). R53/WP-1 은 그 틈을 ``grid_service_won`` 한 칸에 전액을 몰아
    넣는 임의 선택으로 넘겼었다 — 이 함수는 이제 그 임의 배분을 하지 않고
    `DistributedSubItems` 다섯을 받은 그대로 흘려보낸다. ``sub_items`` 가
    `None` 이면 `DistributedBenefit` 자신의 기본값(전부 0)을 쓴다.
    """
    stream: ValueStream = DistributedBenefit(sub_items=sub_items)
    annual_won = int(stream.annual_value(DispatchResult.zeros(1), year=1))
    return ((stream, annual_won),)


def _schedule(
    tag: str,
    annual_won: int,
    *,
    horizon_years: int,
    escalation_by_tag: Mapping[str, float],
) -> dict[int, int]:
    """관점 표에 실을 **연차별** 금액 — 요금 연동 갈래만 계수를 탄다 (R69/WP-2).

    ## ★ 왜 여기서도 굴려야 하는가 — **같은 편익이 두 값으로 인쇄된다**

    종전 이 함수 자리는 `{year: annual_won for year …}` 였다 — 1년차 값을 20년
    깔았고, 그때는 **아무 편익도 연차를 타지 않았으므로** 그것이 옳았다.
    R69/WP-2 가 첨두 절감(`PeakShaving`)을 요금 인상률에 태우면서 그 전제가
    깨졌다: 결론축(사업자 열)은 오르는 값으로 서는데 참여 주민 열은 평평한
    값으로 서서, **같은 편익의 20년 합계가 표 안에서 두 수로 인쇄된다.**

    ⚠ **어느 갈래가 요금 연동인지를 이 모듈이 정하지 않는다.** 판정은 러너가
    갖고(`e2e_runner.py` 의 편익 일정표 옆 ★★★), 여기는 `태그 → 인상률` 을
    받기만 한다 — 여기서 태그 목록을 다시 적으면 정본이 둘이 되고, 한쪽이
    먼저 바뀌는 날 두 열이 조용히 갈린다.

    ⚠ 계수를 짓는 식은 `core/cba/proforma.py::escalation_factor()` **하나**다.
    ⚠ 비어 있으면(`{}`) 전 연차 계수가 1.0 이라 **종전과 원 하나까지 같다.**
    """
    rate = escalation_by_tag.get(tag, 0.0)
    if not rate:
        return {year: annual_won for year in range(1, horizon_years + 1)}
    return {
        year: int(to_won(annual_won * escalation_factor(rate, year=year)))
        for year in range(1, horizon_years + 1)
    }


def build_perspective_wiring(
    annualised: Sequence[tuple[ValueStream, int]],
    operator_benefit_rows: Sequence[CashFlowRow],
    operator_cost_rows: Sequence[CashFlowRow],
    initial_investment: Money,
    discount_rate: float,
    *,
    horizon_years: int,
    society_annualised: Sequence[tuple[ValueStream, int]] = (),
    escalation_by_tag: Mapping[str, float] = MappingProxyType({}),
) -> PerspectiveWiring:
    """`run_single_case_e2e()` 가 이미 가진 재료에서 관점 넷을 짓는다.

    ``annualised`` 는 `core/casegrid/operating_lines.py::annualise` 의
    반환값 그대로다 — `(스트림, 1년차 연간액)` 목록이며 `PeakShaving` 도
    포함한다. 각 스트림의 `effective_payer` 를 읽어 관점별 편익 행을 짓는다.

    ``society_annualised`` 는 `annualised` 와 같은 모양이지만 **결론축에는
    닿지 않는다**(R53/WP-1 판정 ① — `build_society_annualised()` 참조). 비어
    있으면 이 함수는 종전과 완전히 같게 동작한다.

    ``escalation_by_tag`` 는 `태그 → 연 인상률(소수)` 이며 **요금에 연동된
    편익만** 여기 실린다(R69/WP-2). 비어 있으면 전 연차 계수가 1.0 이라
    종전과 원 하나까지 같다 — 어느 갈래가 요금 연동인지의 판정은 러너가
    갖는다(`_schedule()` 독스트링 참조).

    ``operator_benefit_rows``·``operator_cost_rows`` 는 호출측이 이미 지은
    편익·비용 행 **전부**다 — `OPERATOR` 열이 새로 거르지 않고 결론축 그대로
    쓰는 이유는 위 머리말 참조. `net_operating_flows()` 로 여기서 다시 순현금
    흐름을 지어 `npv()` 에 넘긴다 — 호출측
    (`core/casegrid/case_metrics.py::metrics_for`)과 **같은 함수를
    같은 인자로** 부르므로 대수적으로 같은 값이 나온다.
    """
    operator_result = PerspectiveResult(
        perspective=Perspective.OPERATOR,
        benefit_rows=tuple(operator_benefit_rows),
        cost_rows=tuple(operator_cost_rows),
        initial_investment=initial_investment,
        npv_value=npv(
            initial_investment,
            net_operating_flows(list(operator_benefit_rows), list(operator_cost_rows)),
            discount_rate,
        ),
        inclusions=PerspectiveInclusions(),
    )

    by_perspective: dict[Perspective, list[CashFlowRow]] = {
        Perspective.RESIDENT: [],
        Perspective.GOVERNMENT: [],
        Perspective.SOCIETY: [],
    }
    outside: list[OutsideWalletBenefit] = []
    transfers: list[TransferFlow] = []

    for stream, annual_won in (*annualised, *society_annualised):
        payer = stream.effective_payer

        # R58 이전(transfer) 처리
        if stream.transfer_counterparty is not None:
            transfers.append(
                TransferFlow(
                    tag=stream.tag,
                    from_payer=stream.transfer_counterparty,
                    to_payer=payer,
                    annual_won=annual_won,
                )
            )
            # 사회 관점에는 세우지 않는다 (by_perspective[SOCIETY] 에 넣지 않음).
            # 받는 관점(payer)이 RESIDENT/GOVERNMENT 면 + 행
            perspective = _PAYER_TO_PERSPECTIVE.get(payer)
            if perspective in (Perspective.RESIDENT, Perspective.GOVERNMENT):
                by_perspective[perspective].append(
                    benefit_row(
                        stream.tag,
                        _schedule(
                            stream.tag, annual_won,
                            horizon_years=horizon_years,
                            escalation_by_tag=escalation_by_tag,
                        ),
                    )
                )
            # 내는 관점(transfer_counterparty)이 RESIDENT/GOVERNMENT 면 -annual_won 행
            counter_perspective = _PAYER_TO_PERSPECTIVE.get(stream.transfer_counterparty)
            if counter_perspective in (Perspective.RESIDENT, Perspective.GOVERNMENT):
                by_perspective[counter_perspective].append(
                    benefit_row(
                        stream.tag,
                        _schedule(
                            stream.tag, -annual_won,
                            horizon_years=horizon_years,
                            escalation_by_tag=escalation_by_tag,
                        ),
                    )
                )
            continue

        if payer in OUTSIDE_PERSPECTIVE_PAYERS:
            if annual_won != 0:
                outside.append(
                    OutsideWalletBenefit(tag=stream.tag, payer=payer, annual_won=annual_won)
                )
            continue
        perspective = _PAYER_TO_PERSPECTIVE.get(payer)
        if perspective is None:
            # `OPERATOR`(위에서 이미 결론축으로 담았다) · `UNSPECIFIED`
            # (`DV-13` 이 생성 시점에 이미 거부하므로 활성 스트림에는 오지
            # 않는다) — 이 표에서는 볼 일이 없다.
            continue
        by_perspective[perspective].append(
            benefit_row(
                stream.tag,
                _schedule(
                    stream.tag, annual_won,
                    horizon_years=horizon_years,
                    escalation_by_tag=escalation_by_tag,
                ),
            )
        )

    resident_result = compute_perspective_npv(
        Perspective.RESIDENT, by_perspective[Perspective.RESIDENT], [], ZERO, discount_rate
    )
    government_result = compute_perspective_npv(
        Perspective.GOVERNMENT, by_perspective[Perspective.GOVERNMENT], [], ZERO, discount_rate
    )

    # 사회 관점 소거 사유 합치기 (보조금 + 일반 이전)
    transfer_streams = [
        (stream, won) for stream, won in (*annualised, *society_annualised)
        if stream.transfer_counterparty is not None
    ]
    transfer_inclusions = society_excludes_transfers(transfer_streams)

    society_benefits = by_perspective[Perspective.SOCIETY]
    subsidy_row = next((r for r in society_benefits if "보조" in (r.tag or "")), None)
    subsidy_inclusions = society_excludes_subsidy(subsidy_row) if subsidy_row else None

    excluded_tags = list(transfer_inclusions.excluded_tags)
    exclusion_rationale = dict(transfer_inclusions.exclusion_rationale)
    if subsidy_inclusions:
        excluded_tags.extend(subsidy_inclusions.excluded_tags)
        exclusion_rationale.update(subsidy_inclusions.exclusion_rationale)

    society_inclusions = PerspectiveInclusions(
        included_tags=(),
        excluded_tags=tuple(excluded_tags),
        exclusion_rationale=exclusion_rationale,
    )

    society_result = compute_perspective_npv(
        Perspective.SOCIETY,
        society_benefits,
        [],
        ZERO,
        discount_rate,
        inclusions=society_inclusions,
    )
    # FR-704-AC5 — 사회 관점 편익에 보조금이 남아 있으면 여기서 예외가 난다.
    assert_subsidy_excluded_from_society(society_result)

    return PerspectiveWiring(
        results=(society_result, resident_result, operator_result, government_result),
        outside=tuple(outside),
        transfers=tuple(transfers),
    )
