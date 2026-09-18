"""편익 단계가 **수량과 금액을 가른다** — 검증 4단계 (R68/WP-8 · 검토서 §3.6).

검토서 §3.6 은 4단계에 *「3단계의 어떤 물리 결과를 금액화하는가」* 를 요구하고
다섯 쌍을 갈라 보이라고 적는다 — 자가소비량과 구매 회피액 · 잉여판매량과 판매
수입 · 한전 수전량과 전력 구매비 · 피크 절감량과 기본요금 절감액 · PV·ESS 의
설치비와 교체비.

## ★★ 이 검사가 붙드는 것은 **「0원을 어떻게 읽는가」**다

종전 4단계 ⓑ 는 금액 셋뿐이라 「잉여전력 판매 0원」이 *「팔 것이 없었다」* 인지
*「값이 0이었다」* 인지 갈리지 않았다. 그 둘은 **고치는 사람이 다르다** — 앞은
운전(3단계)이고 뒤는 단가(1단계)다. 그래서 이 파일이 재는 것은 표가 서 있는가가
아니라 **수량 칸과 금액 칸이 같은 행에 나란히 서는가**이며, 0원 행에 *「효과
없음이 아니다」* 가 글자로 붙는가다(§3.6 마지막 문단).

## ⚠ 값을 재지 않는다 — **자리와 낱말만 잰다**

수량의 정본은 `core/report/measured_run.py::measured_over_seasons` 이고 금액의
정본은 러너가 만든 `CaseBasis` 다. 여기서 기대값을 리터럴로 적으면 그것이
사본이 되고, 대장이나 운전이 바뀌는 날 **이 검사만 조용히 낡는다.** 그래서
기대값은 **같은 자료에서 다시 읽어** 만든다.

## ⚠ `@pytest.mark.req(...)` 를 달지 않았다

`tests/report/test_verification.py` 머리말과 같은 사유다 — spec 에 「검증 보고서」
라는 산출물에 대응하는 수용기준이 없고, 근거 없는 마커는 `docs/traceability.md`
에 거짓 인용을 싣는다.
"""
from __future__ import annotations

from pathlib import Path

from core.casegrid.models import ONE_OFF_REPLACEMENT
from core.casegrid.operating_lines import DAYS_PER_YEAR
from core.report.case_report import CaseReport, build_case_report
from core.report.measured_run import measured_over_seasons
from core.report.verification import stage_blocks
from core.report.verification_benefit import (
    NOT_COMPUTED,
    NOT_MONETISED,
    PAIR_TITLE,
    benefit_pair_lines,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"


def _report() -> CaseReport:
    """골든 시나리오 하나 — 이 파일의 모든 검사가 같은 실행을 본다."""
    return build_case_report(_GOLDEN, assumptions_path=_ASSUMPTIONS)


def test_the_block_lands_inside_the_benefit_stage_and_nowhere_else() -> None:
    """★★ **부르는 자리가 하나다** — 같은 표가 두 단계에 서면 정본이 사라진다.

    ⚠ 단계 **번호를 박지 않는다** — 「편익 화폐화」 단계가 어느 번호인지는
    렌더러가 정하고 R69/WP-1 이 그것을 4 에서 5 로 밀었다. 여기서 재는 것은
    *「그 표가 편익 단계 하나에만 선다」* 이지 그 번호가 아니다.
    """
    report = _report()
    carrying = [
        (block.number, block.title)
        for block in stage_blocks(report)
        if any(PAIR_TITLE in line for line in block.lines)
    ]
    assert len(carrying) == 1, (
        f"「{PAIR_TITLE}」 표가 {carrying} 에 서 있다 — 한 단계여야 한다"
    )
    assert carrying[0][1] == "편익 화폐화", (
        f"「{PAIR_TITLE}」 표가 「{carrying[0][1]}」 단계에 서 있다 — "
        "편익 화폐화 단계여야 한다"
    )


def test_each_quantity_stands_next_to_its_money_in_one_row() -> None:
    """★★★ **네 쌍이 각각 한 행에 선다** — 수량 열과 금액 열이 갈려 있다.

    이 단언이 없으면 「수량을 어딘가 적었다」로도 통과한다 — 그러면 검토자가 두
    표를 눈으로 맞춰야 하고, 그 맞춤이 §3.6 이 없애려던 일이다.
    """
    lines = benefit_pair_lines(_report())
    rows = [line for line in lines if line.startswith("| ") and "|---" not in line]
    for quantity, money in (
        ("자가소비량", "구매 회피액"),
        ("잉여판매량", "`SurplusSale`"),
        ("한전 수전량", "`GridPurchase`"),
        ("피크 절감량", "`PeakShaving`"),
    ):
        assert any(quantity in row and money in row for row in rows), (
            f"「{quantity}」과 「{money}」이 같은 행에 서지 않는다 — 갈라 실으라는 "
            "요구가 두 표로 흩어지면 검토자가 눈으로 맞춰야 한다"
        )


def test_the_quantities_are_the_ones_the_run_measured() -> None:
    """★★★ **인쇄된 수량이 이 실행이 «잰» 수량이다** — 지어낸 수가 아니다.

    ⚠ 기대값을 리터럴로 적지 않는다 — 같은 자료
    (`measured_over_seasons`)에서 다시 읽어 만든다(머리말 ⚠).
    """
    report = _report()
    measured = measured_over_seasons(report.dispatch_hours, report.seasons)
    assert measured is not None, "잴 운전이 없다 — 이 검사가 성립하지 않는다"
    text = "\n".join(benefit_pair_lines(report))
    for daily in (
        measured.self_consumption,
        measured.grid_export,
        measured.grid_import,
    ):
        printed = f"{daily * DAYS_PER_YEAR:,.0f} kWh/년"
        assert printed in text, f"수량 「{printed}」이 표에 없다"


def test_a_pair_without_material_says_so_instead_of_inventing_a_number() -> None:
    """★★★ **피크 절감량은 「미산출」이라 적는다** — 산문에서 되뽑지 않는다.

    감축 출력(kW)은 이 실행의 어느 자료형에도 없다. 4단계 ⓓ 의 산식 문면에는
    있으나 그것을 정규식으로 되뽑으면 **표기를 다듬는 날 그 수가 조용히
    바뀐다** — 이 저장소가 명시로 금한 갈래다.
    """
    rows = [
        line for line in benefit_pair_lines(_report()) if line.startswith("| 피크")
    ]
    assert len(rows) == 1 and NOT_COMPUTED in rows[0], (
        f"피크 절감량 칸이 「{NOT_COMPUTED}」이 아니다 — 재료가 없는 쌍에 수를 "
        f"지어냈다: {rows}"
    )


def test_a_benefit_that_is_not_monetised_is_words_not_a_zero() -> None:
    """★★★ **화폐화하지 않은 것과 0원이 갈린다** (§3.6).

    자가소비는 수량 배분으로만 반영되고 편익 갈래에 `SelfConsumption` 이 없다.
    그 칸에 `0원` 을 적으면 *「자가소비의 값어치가 0이다」* 가 되고, 그것은
    사실이 아니다 — 「미반영 항목」 표가 그 크기를 연 +739,017원으로 재고 있다.
    """
    rows = [
        line
        for line in benefit_pair_lines(_report())
        if line.startswith("| 자가소비량")
    ]
    assert len(rows) == 1 and NOT_MONETISED in rows[0], (
        f"자가소비의 금액 칸이 「{NOT_MONETISED}」이 아니다: {rows}"
    )
    assert "0원" not in rows[0], (
        "화폐화하지 않은 칸에 0원을 적었다 — 「값어치가 0」으로 읽힌다"
    )


def test_a_zero_benefit_is_printed_as_a_reading_rule_not_as_no_effect() -> None:
    """★★★ **0원 갈래에 「효과 없음이 아니다」가 글자로 붙는다** (§3.6 마지막 문단).

    그리고 그 사유가 **이 실행에서 잰 것**이어야 한다 — 계통 송전이 0인 것은
    잉여가 없어서가 아니라 부하 이동과 저장장치 충전이 먼저 쓰기 때문이다
    (`status.md` R67 종료 블록 ②).
    """
    report = _report()
    zeros = [line for line in report.basis.benefits if line.annual_won == 0]
    assert zeros, "0원 편익 갈래가 0건이다 — 이 검사가 0회 순회로 통과한다"
    text = "\n".join(benefit_pair_lines(report))
    for line in zeros:
        assert f"`{line.tag}`" in text, f"0원 갈래 `{line.tag}` 가 주석에 없다"
    assert "그 편익이 없다」가 아니라" in text, (
        "0원을 「효과 없음」과 가르는 문면이 없다 — 빈 0은 「없다」로 읽힌다"
    )
    assert "먼저 쓰기" in text, "0이 된 사유를 적지 않았다"


def test_the_install_cost_and_the_replacement_cost_stand_in_separate_columns() -> None:
    """★★ **설치비와 교체비가 같은 칸에 뭉치지 않는다** (§3.6 다섯째 쌍).

    ⚠ 교체비는 **계상 연차와 함께** 선다 — 없으면 검토자가 그것을 연간액으로
    읽는다(`core/casegrid/models.py::OneOffLine` 이 같은 사유로 연차를 필수로 뒀다).
    """
    report = _report()
    text = "\n".join(benefit_pair_lines(report))
    for resource in report.basis.resources:
        assert f"| {resource.kind} | {resource.capex_won:,.0f}원 " in text, (
            f"`{resource.name}` 의 설치비가 자기 열에 서지 않는다"
        )
    for flow in report.basis.one_off_flows:
        if flow.kind != ONE_OFF_REPLACEMENT:
            continue
        assert f"{flow.amount_won:,.0f}원 ({flow.year}년차)" in text, (
            f"`{flow.resource_name}` 의 교체비가 연차와 함께 서지 않는다"
        )
