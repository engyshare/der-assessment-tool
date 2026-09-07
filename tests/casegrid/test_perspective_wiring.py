"""관점 넷이 **배포 진입점**을 실제로 지나는가 — R52/WP-A.

⚠⚠⚠ **`status.md` 함정 맨 위 항** — 「검사가 배포 코드가 부르지 않는 함수를
직접 불러 통과한다」. 이 파일은 그 함정을 다시 만들지 않는다 — `core.cba.
perspective`·`core.casegrid.perspectives` 를 직접 부르지 않고, `app.run.
report_cli` 가 실제로 쓰는 진입점(`build_case_report` → `render_markdown`)만
지난다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.perspectives import build_perspective_wiring, build_society_annualised
from core.casegrid.profiles import load_daily_shapes
from core.cba.perspective import Perspective
from core.contracts.units import ZERO
from core.report.case_report import CONCLUSION_METRIC, build_case_report
from core.report.narrative import render_markdown
from core.report.perspective_report import REQUIRED_PERSPECTIVES
from core.valuestream import DistributedSubItems

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"


@pytest.fixture(scope="module")
def report():
    return build_case_report(_GOLDEN, assumptions_path=_ASSUMPTIONS)


@pytest.mark.req("FR-704-AC4")
def test_deployed_report_carries_the_four_perspectives_in_user_order(report) -> None:
    """`app.run.report_cli` 가 쓰는 진입점이 관점 넷을 사용자 판정 순서로 낸다."""
    text = render_markdown(report)
    assert (
        "| 지표 | 사회(국가) | 참여 주민(전기사용자) | 사업자(분산E) | 정부 |"
        in text
    )
    assert REQUIRED_PERSPECTIVES == (
        Perspective.SOCIETY,
        Perspective.RESIDENT,
        Perspective.OPERATOR,
        Perspective.GOVERNMENT,
    )


def test_operator_perspective_keeps_the_conclusion_axis(report) -> None:
    """사업자(`OPERATOR`) 관점의 NPV 는 4.1 결론축과 같다 — 다시 계산하지 않는다.

    ⚠ spec 조항이 아니라 R52/WP-A 판정 아-7(결론축 불변)의 검사다 —
    `@pytest.mark.req` 를 달지 않는다.

    ⚠ **리터럴을 R52/WP-6 이 갱신했다** — `benefit.rec_price` 가
    `default0`(0원) → `assume`(70원/kWh)으로 올라 결론축이 −12,591,162 →
    **−11,537,129원**(+1,054,033원)으로 움직였다. 이 검사는 「관점이 축을
    다시 계산하지 않는가」를 재는 것이지 축 자체의 값을 고정하는 자리가
    아니므로, 위 첫 단언(`report.metrics[CONCLUSION_METRIC]` 과 같은가)이
    실질이고 아래는 그 값을 실측으로 못박아 둔다.

    ⚠ **R60/WP-4-fix 가 다시 갱신했다** — 자산의 계절 절을 가정으로 채우며
    결론축이 −11,537,129 → **−11,552,270원**(−15,141원)으로 옮겼다. 연간
    총량은 그대로이고 몫 가중 평균 대표일의 **모양**만 바뀐 몫이다
    (`core/casegrid/profiles.py::DailyShape.representative_day`).

    ⚠ **R64/WP-4 가 다시 갱신했다** — 러너가 계절 넷의 대표일을 **각각 돌려
    계절일수로 가중 합산**하면서 −11,552,270 → **−11,495,622원**(+56,648원)으로
    옮겼다(착수 36ⓐ · 그 골든 파일의 R64 블록이 경위와 산식을 갖는다).
    ⚠ **R64/WP-6b 가 다시 갱신했다** — ESS 방전 배분의 배포 기본값이 「부하
    추종」으로 바뀌고 러너가 계절별 가구 부하를 ESS 에 넘기면서 −11,495,622 →
    **−11,502,062원**(−6,440원)으로 옮겼다(사용자 요구 5 · 그 골든 파일의
    R64/WP-6b 블록이 경위와 산식을 갖는다).
    ⚠ **R64/WP-7 이 다시 갱신했다** — 「AI 가전」이 가전 부하를 하루 안에서
    태양광 잉여 시각으로 옮기면서 −11,502,062 → **−11,625,181원**(−123,119원)
    으로 옮겼다(사용자 요구 2 · 그 골든 파일의 R64/WP-7 블록이 경위와 산식을
    갖는다). 연간 부하 총량은 **한 kWh 도 움직이지 않았다** — 움직인 것은
    하루의 모양이고, 그 모양이 계통 수전·송전과 첨두 절감을 바꿨다.

    ⚠⚠ **R65/WP-2c 가 다시 갱신했다 — 이번에는 「사업의 규모」다.** 사용자
    요구(*「가구수를 20가구로 설정」*)로 단지가 20호가 되고 설계 변수 셋이 그
    배수를 타면서(태양광 3 → 60 kW · ESS 10 → 200 kWh · 정격출력 5 → 100 kW)
    결론축이 −11,625,181 → **−323,257,263원**이 됐다. 앞의 갱신들과 달리 이번에
    움직인 것은 **하루의 모양이 아니라 사업의 크기**이며, 그 경위와 산식은
    `fixtures/golden/scenario_unsubsidized.yaml` 의 R65 블록이 갖는다.

    ⚠⚠ **이 검사가 재는 것은 「축이 절대 안 움직인다」가 아니다** — *「관점 층이
    축을 **다시 계산하지 않는가**」* 이며 그 실질은 **위 첫 단언**이다(사업자
    관점의 NPV 가 4.1 결론축과 같은 객체에서 오는가). 그 단언은 이 라운드에도
    통과했고, 아래 리터럴은 그 값을 실측으로 못박아 두는 자리다.

    ⚠⚠⚠ **R66/WP-2 가 −323,257,263 → −328,257,263원으로 옮겼다** (사용자 판정 ③).
    ESS 초기투자에 **원/kW 항**이 섰다 — 배터리 500,000 × (1 − 20%) = 400,000원/kWh
    × 200 kWh = 80,000,000 **+ PCS 250,000원/kW × 100 kW = 25,000,000** 이므로
    100,000,000 → **105,000,000원**이고, 총 초기투자가 196,000,000 → 201,000,000원
    이다. 이동 폭이 그 **+5,000,000 과 정확히 같은** 것은 초기투자가 1년차이고
    현가계수가 1.0 이기 때문이며, 교체비·잔존가치는 한 원도 안 움직였다
    (교체 단가는 별 항목 `capex.ess.replacement` 에서 오고 PCS 수명은 아직
    `None` 이다). 경위는 `fixtures/golden/scenario_unsubsidized.yaml` 의 R66 블록이
    갖는다.
    """
    operator = next(
        r for r in report.perspectives.results if r.perspective is Perspective.OPERATOR
    )
    assert int(operator.npv_value) == int(report.metrics[CONCLUSION_METRIC])
    assert int(operator.npv_value) == -328_257_263


@pytest.mark.req("FR-402-AC7")
def test_benefit_tags_do_not_overlap_between_resident_and_operator(report) -> None:
    """관점마다 편익 집합이 다르다 — `payer` 로 가른 태그가 겹치지 않는다."""
    by_perspective = {
        r.perspective: {row.tag for row in r.benefit_rows}
        for r in report.perspectives.results
    }
    resident_tags = by_perspective[Perspective.RESIDENT]
    operator_tags = by_perspective[Perspective.OPERATOR]
    assert resident_tags, "참여 주민 관점에 편익 태그가 없다 — PeakShaving 이 배선되지 않았다"
    assert resident_tags.isdisjoint(operator_tags), (
        f"참여 주민과 사업자 열의 편익 태그가 겹친다: {resident_tags & operator_tags}"
    )


def test_outside_perspective_wallets_are_not_attributed_to_any_column(report) -> None:
    """`NWAs`(배전사업자)·`CP`(전력시장)는 관점 넷 어디에도 들어가지 않는다."""
    all_tags = {
        row.tag for r in report.perspectives.results for row in r.benefit_rows
    }
    assert "NWAs" not in all_tags
    assert "CP" not in all_tags
    assert "관점 넷 밖의 지갑" in render_markdown(report)


@pytest.mark.req("FR-704-AC5")
def test_society_perspective_has_no_subsidy_benefit(report) -> None:
    """사회 관점 편익에 보조금이 없다 — `assert_subsidy_excluded_from_society` 통과."""
    society = next(
        r for r in report.perspectives.results if r.perspective is Perspective.SOCIETY
    )
    assert not any("보조" in (row.tag or "") for row in society.benefit_rows)


def test_resident_perspective_shows_what_is_present_and_absent(report) -> None:
    """참여 주민(전기사용자) 관점에 있는 편익과 없는 편익이 리포트에 드러난다.

    ⚠ 「거의 빈다」로 뭉뚱그리지 않는다(WP-A-fix 결함 2-③) — `PeakShaving`
    은 이 실행에서 0원이 아니므로 「빈다」는 과장이다.
    """
    text = render_markdown(report)
    assert "PeakShaving" in text
    assert "SelfConsumption" in text
    assert "거의 빈다" not in text


def test_npv_row_prints_no_number_for_perspectives_without_cost_basis(report) -> None:
    """NPV 행 — 비용 배분이 없는 관점은 「미산출」이고 「0」이 인쇄되지 않는다.

    WP-A-fix 결함 1 의 핵심 단언: 참여 주민 974,035원이 「이득」으로,
    사회·정부 0원이 「손익 0」으로 오독되던 것을 막는다.

    ⚠ **리터럴을 R52/WP-6 이 갱신했다** — `benefit.rec_price` 가 결론축을
    −12,591,162 → **−11,537,129원**으로 옮겼다(위
    `test_operator_perspective_keeps_the_conclusion_axis` 참조).
    R60/WP-4-fix 가 그것을 다시 **−11,552,270원**으로 옮겼다(같은 자리 참조).

    ⚠⚠ **「0 이 인쇄되지 않는가」를 칸으로 잰다** (R60/WP-4-fix). 종전에는 줄
    전체에서 글자 `0` 을 찾았고, 그것이 통과한 것은 **그때의 결론축 숫자에
    마침 `0` 이 없었기 때문**이다 — 수가 −11,552,270원으로 바뀌자 자기 자릿수에
    걸려 빨간불이 됐다. 이 검사가 붙드는 것은 *「비용 배분이 없는 관점 칸이
    「0원」으로 인쇄되지 않는가」* 이므로 **칸을 갈라 그 칸이 「0원」인지**를
    본다. 그렇게 하면 결론축 숫자가 무엇이든 이 검사의 뜻이 변하지 않는다.
    """
    text = render_markdown(report)
    npv_line = next(line for line in text.splitlines() if line.startswith("| NPV |"))
    assert npv_line.count("미산출") == 3, npv_line
    # ⚠ R64/WP-4 가 계절 합산을 세우며 −11,552,270 → −11,495,622원으로,
    # R64/WP-6b 가 방전 부하 추종을 세우며 −11,495,622 → −11,502,062원으로,
    # R64/WP-7 이 「AI 가전」의 부하 이동을 세우며 −11,502,062 → −11,625,181원
    # 으로 옮겼다 (위 `test_operator_perspective_keeps_the_conclusion_axis` 의 ⚠).
    # ⚠⚠ R65/WP-2c 가 단지를 20호로 세우며 −11,625,181 → −323,257,263원이 됐다.
    # ⚠⚠⚠ R66/WP-2 가 ESS 초기투자에 PCS 원/kW 항을 세우며(+5,000,000원)
    # −323,257,263 → −328,257,263원이 됐다 (위 `test_operator_perspective_keeps_
    # the_conclusion_axis` 의 ⚠⚠⚠ 절이 산식을 갖는다).
    assert "-328,257,263원" in npv_line, npv_line
    cells = [cell.strip() for cell in npv_line.strip().strip("|").split("|")]
    assert "0원" not in cells, npv_line
    assert "0" not in cells, npv_line


def test_cost_total_row_prints_not_allocated_for_perspectives_without_cost_basis(
    report,
) -> None:
    """비용 합계 행 — 같은 관점 셋은 「미배분」이지 「0원」이 아니다."""
    text = render_markdown(report)
    cost_line = next(line for line in text.splitlines() if line.startswith("| 비용 합계 |"))
    assert cost_line.count("미배분") == 3, cost_line
    # ⚠ R64/WP-4 — 계절 합산으로 계통 수전이 늘어(연 917.65 → 993.91kWh) 전력
    # 구매 비용이 오르며 17,746,097 → 17,929,097원이 됐다.
    # ⚠ R64/WP-6b — 저녁 부하가 큰 시각에 방전이 몰리며 계통 수전이 도로 조금
    # 줄어(대표일 2.723034 → 2.717654kWh) 17,929,097 → 17,924,397원이 됐다.
    # ⚠ R64/WP-7 — 「AI 가전」이 가전 부하를 태양광 잉여 시각으로 옮겨 **사는
    # 전기가 줄었다**(대표일 2.717654 → 2.480669kWh · 연 −86.50kWh). 전력 구매
    # 비용이 연 −10,380원이고 20년 누계가 −207,600원이라 17,924,397 →
    # **17,716,797원**이 됐다. ★ 이 축에서는 **비용이 내려간 것이 요구가 시킨
    # 결과**다 — 그런데도 결론축이 나빠진 이유(잉여판매·REC·첨두 절감의 감소)는
    # 아래 `test_benefit_total_row_always_prints_a_real_number` 가 적는다.
    # ⚠⚠ R65/WP-2c — 단지가 20호가 되며 전력 구매·고정 O&M·교체비가 다 20배
    # 규모로 다시 서서 17,716,797 → **468,935,338원**이 됐다. ⚠ 정확히 20배가
    # 아닌 것은 이 칸이 **비용 합계**(전력 구매 + 고정 O&M + 교체비 − 잔존가치)
    # 이고 그중 전력 구매만 부하에 비례하기 때문이다.
    # ⚠⚠⚠ R66/WP-2 — ESS 초기투자에 PCS 원/kW 항이 서며 468,935,338 →
    # **473,935,338원**(+5,000,000)이 됐다. ★ **위 괄호의 구성 목록은 초기투자를
    # 빠뜨렸다** — 실측하면 이 칸은 `초기투자 + 전력 구매 + 고정 O&M 둘 + 교체비
    # 둘 − 잔존가치 둘` 이고, 운영분만 더하면 272,935,338원이라 이 수가 되지
    # 않는다(196,000,000 을 더해야 468,935,338 이다). 그래서 이번 이동 폭이
    # 초기투자 증가분과 **정확히 같다** — 운영 행은 한 원도 안 움직였다.
    assert "473,935,338원" in cost_line, cost_line


def test_benefit_total_row_always_prints_a_real_number(report) -> None:
    """편익 합계 행은 비용 배분과 무관하게 늘 참인 수다 (WP-A-fix 결함 1 항목 2).

    ⚠ **사업자 리터럴을 R52/WP-6 이 갱신했다** — REC 편익(0 → 70원/kWh)이
    사업자 편익 합계에 더해져 4,038,000 → **5,658,600원**이 됐다. 참여
    주민은 REC 를 포함하지 않아 그대로다.

    ⚠ **R60/WP-4-fix 가 둘 다 갱신했다** — 계절 형상이 평균 대표일의 모양을
    바꿔 낮 시간대 발전과 가구 부하가 겹치는 몫이 늘었다. 자가소비가 커진 만큼
    참여 주민이 1,497,600 → **1,559,940원**으로 오르고, 계통으로 나가는 잉여가
    줄어 사업자가 5,658,600 → **5,414,340원**으로 내렸다. 연간 총량은 그대로다.

    ⚠ **R64/WP-4 가 사업자만 갱신했다** — 계절 넷을 각각 돌려 합산하자 겨울의
    부족과 여름의 잉여가 평균 하루에서 상쇄되던 것이 풀려 **계통 역송이
    늘었고**(연 1,070.73 → 1,144.59kWh), 그 수량에 붙는 잉여판매·REC 가 커져
    사업자가 5,414,340 → **5,684,440원**이 됐다. **참여 주민은 그대로다** —
    그쪽은 요금 절감(가구 자가소비)이고 그 총량은 움직이지 않았다.

    ⚠ **R64/WP-6b 도 사업자만 갱신했다** — 방전이 저녁 부하를 따라가면서 집이
    먼저 받아 가는 몫이 늘고 계통 역송이 조금 줄어(대표일 3.135868 →
    3.130487kWh) 잉여판매·REC 가 각 −365원/년, 사업자가 5,684,440 →
    **5,669,840원**이 됐다. **참여 주민은 이번에도 그대로다** — 자가소비량
    (대표일 5.518432kWh)이 한 자리도 안 움직였다.

    ⚠ **R64/WP-7 은 둘 다 갱신했다** — 「AI 가전」이 가전 부하를 낮의 태양광
    잉여 시각으로 옮기면서 ⓐ 저녁 봉우리가 낮아져 **첨두 절감이 연 −7,800원**
    (`PeakShaving` 은 사업장 최대부하가 정하는 편익이다) ⓑ 계통으로 나가는 잉여가
    줄어 **잉여판매 −7,300원 · REC −4,745원**이 됐다. 참여 주민은 ⓐ 만 지므로
    1,559,940 → **1,403,940원**(20년 누계 −156,000원), 사업자는 셋을 다 지므로
    5,669,840 → **5,272,940원**(20년 누계 −396,900원)이다.
    ⚠⚠ **참여 주민이 처음으로 움직였다** — 앞의 두 항이 *「참여 주민은
    그대로다」* 라고 적은 것은 그 배선들이 **자가소비량**을 바꾸지 않았기
    때문이고, 이 축은 **부하의 시각 자체**를 옮기므로 사업장 최대부하가 바뀐다.

    ⚠⚠ **R65/WP-2c 가 둘 다 갱신했다 — 규모가 20배가 됐다.** 참여 주민
    1,403,940 → **79,872,000원** · 사업자 5,272,940 → **83,142,400원**이다.
    ★ 둘의 배수가 다르다 — 참여 주민은 요금 절감(자가소비·첨두 절감)만 지고
    그 둘은 부하·설비에 비례해 커지는데, 사업자는 거기에 **잉여판매·REC** 를
    더 지고 그쪽은 계통 역송량에 붙는다. 20호 단지는 낮에도 부하가 커져
    **역송 자체가 규모만큼 늘지 않으므로** 사업자의 배수가 더 작다.
    """
    text = render_markdown(report)
    benefit_line = next(line for line in text.splitlines() if line.startswith("| 편익 합계 |"))
    assert "미산출" not in benefit_line and "미배분" not in benefit_line
    assert "79,872,000원" in benefit_line  # 참여 주민
    assert "83,142,400원" in benefit_line  # 사업자


def test_header_row_pairs_repository_and_user_vocabulary(report) -> None:
    """표 머리에 사용자 어휘(국가·전기사용자·분산e사업자)를 병기한다 (결함 2-②)."""
    text = render_markdown(report)
    assert (
        "| 지표 | 사회(국가) | 참여 주민(전기사용자) | 사업자(분산E) | 정부 |"
        in text
    )


# ── R53/WP-1 — 사회 관점 편익(`DistributedBenefit`)의 배선 ──────────────────
#
# ⚠ 아래 세 검사는 `run_single_case_e2e()`(배포 진입점)를 직접 지난다 — 대장의
# `benefit.distributed_credit.*` 다섯 칸이 항상 0(`default0`)이라 `report`
# 픽스처만으로는 ⓒ(0이 아닌 값에서 축이 안 움직이는가)를 잴 수 없다.


def _run_with_distributed_credit(sub_items: DistributedSubItems):
    """`distributed_sub_items` 하나만 바꿔 배포 경로를 돈다.

    `test_rec_wiring.py::_run` 과 같은 이유로 대장 수준표를 그대로 쓴다 —
    이 파일이 재는 것이 배선이지 값이 아니기 때문이다.
    """
    level_map = build_level_map(_ASSUMPTIONS)
    return run_single_case_e2e(
        {},
        level_map=level_map,
        horizon_years=20,
        daily_shapes=load_daily_shapes(),
        annual_load_kwh=level_map["household_load_annual_kwh"]["base"],
        distributed_sub_items=sub_items,
    )


def test_society_column_receives_a_distributed_benefit_row() -> None:
    """ⓐ 사회 열이 `DistributedBenefit` 행을 받는다 — 값이 0이어도 행은 있다.

    「행이 없어서 0원」과 「값이 0이어서 0원」은 뜻이 정반대다(러너
    `GridPurchase` 주석 — 826~830줄 — 이 같은 규칙을 적는다).
    """
    outcome = _run_with_distributed_credit(DistributedSubItems())
    society = next(
        r for r in outcome.perspectives.results if r.perspective is Perspective.SOCIETY
    )
    tags = {row.tag for row in society.benefit_rows}
    assert "DistributedBenefit" in tags, (
        f"사회 열에 DistributedBenefit 행이 없다 — {tags}. 값이 0이어도 행은 있어야 한다"
    )


def test_distributed_benefit_wiring_leaves_the_conclusion_axis_untouched_when_empty() -> None:
    """ⓑ `society_annualised` 가 비어 있으면 `build_perspective_wiring()` 은
    종전과 완전히 같게 동작한다 — 사업자 `npv_value` 가 원 단위로 같다.

    ⚠ 이 검사는 `core.casegrid.perspectives` 를 직접 부른다 — 이 파일 머리말의
    「배포 진입점만 지난다」원칙에서 벗어나지만, 위·아래 검사가 이미
    `run_single_case_e2e()`(배포 경로)를 지나므로 「내부만 통과하고 배포는
    안 지난다」함정을 재현하지 않는다. 이 검사가 재는 것은 인자 기본값의
    **계약**(비어 있으면 옛 동작과 같다)이며 함수 서명의 성질이다.
    ⚠⚠ 값이 0이라 잘못 배선해도 초록불일 수 있다 — 아래
    `test_distributed_benefit_structurally_cannot_touch_the_conclusion_axis`
    가 0이 아닌 값으로 그 빈틈을 막는다.
    """
    without_kwarg = build_perspective_wiring((), (), (), ZERO, 0.05, horizon_years=1)
    with_kwarg = build_perspective_wiring(
        (), (), (), ZERO, 0.05, horizon_years=1,
        society_annualised=build_society_annualised(),
    )
    op_without = next(
        r for r in without_kwarg.results if r.perspective is Perspective.OPERATOR
    )
    op_with = next(r for r in with_kwarg.results if r.perspective is Perspective.OPERATOR)
    assert int(op_without.npv_value) == int(op_with.npv_value)


def test_distributed_benefit_structurally_cannot_touch_the_conclusion_axis() -> None:
    """ⓒ ★★★ 사회 편익 단가를 0이 아닌 큰 값으로 주면 **사회 열만** 움직이고
    사업자 `npv` 는 한 원도 안 움직인다.

    「값이 0이라 축이 안 움직인다」가 아니라 「구조적으로 축에 닿을 수
    없다」는 것을 잰다 — R53/WP-1 판정 ①의 핵심 단언.
    """
    zero = _run_with_distributed_credit(DistributedSubItems())
    large = _run_with_distributed_credit(
        DistributedSubItems(transmission_avoidance_won=50_000_000.0)
    )

    zero_society = next(
        r for r in zero.perspectives.results if r.perspective is Perspective.SOCIETY
    )
    large_society = next(
        r for r in large.perspectives.results if r.perspective is Perspective.SOCIETY
    )
    assert large_society.npv_value != zero_society.npv_value, (
        "사회 편익 단가를 50,000,000원으로 올렸는데 사회 열 NPV 가 움직이지 않았다 "
        "— DistributedBenefit 이 사회 열에 실제로 실리지 않는다"
    )
    assert int(large.metrics["npv"]) == int(zero.metrics["npv"]), (
        f"사회 편익만 올렸는데 사업자 npv 가 {int(zero.metrics['npv']):,} → "
        f"{int(large.metrics['npv']):,} 로 움직였다 — 사회 편익이 결론축에 샜다"
    )


@pytest.mark.req("FR-704-AC8")
def test_transfers_empty_leaves_wiring_untouched(report) -> None:
    """R58 판정 ③ — transfers 가 비어 있으면 종전과 완전히 같게 동작한다.

    지금 이전 편익이 0개이므로 실제로 그렇다. 이것이 결론축을 안 움직인다는 증거다.
    """
    assert report.perspectives.transfers == ()

    op = next(r for r in report.perspectives.results if r.perspective is Perspective.OPERATOR)
    assert int(op.npv_value) == int(report.metrics[CONCLUSION_METRIC])
