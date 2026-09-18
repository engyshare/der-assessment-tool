"""붙임 3 의 **3중 표기 산식**이 무엇을 약속하는가 — `FR-1001-AC2`·`AC3`.

## 왜 이 파일이 지금 생기는가

R64/WP-2 가 `NFR-206` 코드 스프롤 상한(500줄) 때문에 `Formula` 와
`build_formulas()` 를 `core/report/case_report.py` 에서 갈라
`core/report/case_formulas.py` 로 옮겼다. **옮긴 자리를 읽는 검사가 하나도
없었다** — 저장소 전수로 이 모듈을 import 하는 검사가 0건이고, 이름을 문면으로
언급하는 자리 하나가 있을 뿐이다(`tests/report/test_conclusion_gap.py` 의
독스트링). **언급은 import 가 아니다.** 그것이 CI 의 「테스트 동반」 게이트
(`NFR-105`)가 잡은 것이며, 이 파일이 그 빈자리를 채운다.

## 무엇을 붙드는가

    ① 3중 표기가 **셋 다 서 있다**        ← 하나가 비면 그 약속이 깨진다
    ② 대입값이 **넘긴 수를 되읽는다**      ← 「대입값」이 이름뿐이면 수식만 남는다
    ③ 수식과 대입값이 **서로 다르다**      ← 같으면 대입이 일어나지 않은 것이다
    ④ 지원율을 바꾸면 **결론 축 산식이 따라 움직인다** ← 인자를 실제로 읽는다
    ⑤ 조립이 **조용히 비지 않는다**        ← 빈 붙임은 아무 오류도 내지 않는다

⚠ **입력을 지어내지 않는다.** `CaseBasis` 와 지표는 골든 시나리오를 실제로
돌려서 얻는다. 손으로 지으면 **없는 사업**의 산식을 재게 되고, 그때 이 파일은
산식을 붙드는 자리가 아니라 지어낸 수를 붙드는 자리가 된다
(`tests/report/conftest.py` 의 `report_shapes()` 가 같은 함정을 적는다).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.report.case_formulas import Formula, build_formulas
from core.report.case_influences import break_even_subsidy_rate
from core.report.case_report import (
    CONCLUSION_METRIC,
    CaseReport,
    build_case_report,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"

#: 결론 축을 지원율로 환산해 싣는 건 — ④ 가 이 건을 본다.
_FLIP_LABEL = "결론 전환 지원율"
#: 초기투자와 결론 축이 함께 대입되는 건 — ② 가 이 건을 본다.
_NPV_LABEL = "순현재가치"
#: 편익과 운영비가 그대로 대입되는 건 — ② 가 이 건을 함께 본다.
_NET_LABEL = "연 순현금흐름"


@pytest.fixture(scope="module")
def golden_report() -> CaseReport:
    """골든 한 건을 **실제로 돌린** 리포트 — 이 파일의 입력 정본.

    모듈 범위인 이유는 실행에 몇 초가 걸리기 때문이며, 검사들이 이것을 **읽기만**
    한다(`CaseReport` 는 frozen 이고 어느 검사도 여기에 쓰지 않는다).
    """
    return build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )


def _build(
    report: CaseReport, *, subsidy_rate: float | None = None
) -> tuple[Formula, ...]:
    """리포트가 부르는 것과 **같은 넷**으로 조립기를 부른다.

    ⚠ `total_project_cost_won` 은 `CaseBasis` 의 총사업비가 아니라 **무지원
    기준선 변형의 초기지출**이다 — `build_formulas()` 독스트링이 그 이유를 적는다
    (지원을 받은 사업의 산식이 지원 전 금액으로 서면 검토자가 대입값을 따라갔을
    때 리포트의 결론과 다른 수가 나온다).
    """
    return build_formulas(
        report.basis,
        report.metrics,
        subsidy_rate=report.subsidy_rate if subsidy_rate is None else subsidy_rate,
        total_project_cost_won=float(report.baseline_metrics["initial_outlay_won"]),
    )


def _by_label(formulas: tuple[Formula, ...], label: str) -> Formula:
    found = next((item for item in formulas if item.label == label), None)
    assert found is not None, (
        f"{label!r} 산식이 조립 결과에 없습니다: "
        f"{[item.label for item in formulas]} — 이 검사가 전제한 건이 사라졌습니다"
    )
    return found


def test_every_formula_carries_all_three_notations(golden_report: CaseReport) -> None:
    """건마다 **자연어·수식·대입값이 셋 다** 서 있다 (성질 가).

    `Formula` 가 *「3중 표기 한 건 — 자연어 + 수식 + 대입값(`FR-1001-AC3`)」* 이라고
    약속한다. 셋 중 하나가 비면 붙임 3 의 그 줄은 **칸만 있고 내용이 없는 행**이
    되는데, 자료형이 `str` 을 요구할 뿐이라 빈 문자열은 아무 오류도 내지 않는다 —
    화면에 나가서야 보인다. 라벨까지 함께 보는 이유는 라벨이 비면 검토자가 그
    줄이 무엇의 산식인지 알 수 없기 때문이다.
    """
    formulas = _build(golden_report)

    for item in formulas:
        for field in ("label", "natural", "expression", "substituted"):
            value = getattr(item, field)
            assert value.strip(), (
                f"{item.label!r} 산식의 {field} 가 비어 있습니다 — "
                "3중 표기 중 한 칸이 빈 채로 붙임 3 에 실립니다"
            )


def test_the_substituted_line_reads_back_the_numbers_it_was_given(
    golden_report: CaseReport,
) -> None:
    """대입값에 **넘긴 수가 실제로 들어 있다** (성질 나).

    *「대입값」* 이 이름뿐이면 화면에는 수식만 남고, 검토자는 본문의 수가 어디서
    왔는지 따라갈 통로를 잃는다(`build_formulas()` 안의 `MC-1` 주석이 그 통로를
    적는다). 그래서 **넘긴 인자에서 문면을 되읽는다**:

        결론 축(`npv`)·초기지출      → 「순현재가치」의 대입값
        연 편익·연 운영비            → 「연 순현금흐름」의 대입값
        총사업비                     → 「결론 전환 지원율」의 대입값

    ★ **뒤쪽 절반이 이 검사의 값이다.** 앞쪽만 두면 대입값 자리에 상수를 박아 둔
    구현도 통과한다 — 지표를 바꿔 넣고 **문면이 따라 움직이는지**까지 본다.
    """
    basis = golden_report.basis
    total = float(golden_report.baseline_metrics["initial_outlay_won"])
    formulas = _build(golden_report)

    npv_line = _by_label(formulas, _NPV_LABEL).substituted
    assert f"{golden_report.metrics[CONCLUSION_METRIC]:,.0f}원" in npv_line, (
        f"「{_NPV_LABEL}」의 대입값에 넘긴 결론 축이 없습니다: {npv_line}"
    )
    assert f"{int(golden_report.metrics['initial_outlay_won']):,}원" in npv_line, (
        f"「{_NPV_LABEL}」의 대입값에 넘긴 초기지출이 없습니다: {npv_line}"
    )

    net_line = _by_label(formulas, _NET_LABEL).substituted
    assert f"{basis.annual_benefit_won:,}원" in net_line, (
        f"「{_NET_LABEL}」의 대입값에 연 편익이 없습니다: {net_line}"
    )
    assert f"{basis.annual_cost_won:,}원" in net_line, (
        f"「{_NET_LABEL}」의 대입값에 연 운영비가 없습니다: {net_line}"
    )

    flip_line = _by_label(formulas, _FLIP_LABEL).substituted
    assert f"{total:,.0f}원" in flip_line, (
        f"「{_FLIP_LABEL}」의 대입값에 넘긴 총사업비가 없습니다: {flip_line}"
    )

    # ★ 지표를 바꿔 넣으면 문면이 따라 움직인다 — 상수를 박아 둔 구현을 거른다.
    moved = dict(golden_report.metrics)
    moved[CONCLUSION_METRIC] = float(golden_report.metrics[CONCLUSION_METRIC]) / 2.0
    moved_line = _by_label(
        build_formulas(
            basis,
            moved,
            subsidy_rate=golden_report.subsidy_rate,
            total_project_cost_won=total,
        ),
        _NPV_LABEL,
    ).substituted
    assert f"{moved[CONCLUSION_METRIC]:,.0f}원" in moved_line, (
        f"결론 축을 바꿔 넘겼는데 「{_NPV_LABEL}」의 대입값이 옛 수를 들고 "
        f"있습니다: {moved_line}"
    )


def test_the_expression_and_the_substituted_line_are_not_the_same_text(
    golden_report: CaseReport,
) -> None:
    """수식과 대입값이 **서로 다르다** (성질 다).

    같으면 대입이 일어나지 않은 것이다 — 붙임 3 은 같은 줄을 두 번 싣게 되고,
    검토자가 보는 것은 기호뿐이다. 성질 가(빈 칸 없음)로는 이 상태를 걸러내지
    못한다: 대입값 칸에 수식을 그대로 복사해도 비어 있지 않다.
    """
    for item in _build(golden_report):
        assert item.expression != item.substituted, (
            f"{item.label!r} 의 수식과 대입값이 같은 문면입니다: "
            f"{item.expression!r} — 대입이 일어나지 않았습니다"
        )


def test_raising_the_subsidy_rate_raises_the_conclusion_flipping_rate(
    golden_report: CaseReport,
) -> None:
    """지원율을 올리면 **결론 전환 지원율이 그만큼 오른다** (성질 라).

    조립기가 `subsidy_rate` 를 **실제로 읽는다**는 증거다. 인자를 무시하고 대장이나
    리포트에서 다시 읽는 구현이면 두 결과가 같다.

    ★ **방향까지 재는 근거는 이 모듈이 스스로 인쇄하는 수식이다** — `s* = s - NPV
    / I_total` 이므로, 결론 축과 총사업비를 고정한 채 `s` 만 올리면 `s*` 는 **정확히
    같은 폭**으로 오른다. 그래서 「달라진다」에서 멈추지 않고 **환산 한 곳**
    (`break_even_subsidy_rate()`)이 낸 값이 문면의 머리에 그대로 서는지까지 본다 —
    본문 5.1 과 붙임 3 이 같은 함수를 쓴다는 약속이 그 함수의 독스트링에 있다.

    ⚠ 여기서 지표를 함께 움직이지 않는 것은 **의도한 것이다.** 실제 실행에서는
    지원율이 오르면 결론 축도 함께 오르지만, 그 둘을 같이 움직이면 무엇이 문면을
    바꿨는지 갈라낼 수 없다. 이 검사가 재는 것은 사업이 아니라 **인자가 읽히는가**다.
    """
    total = float(golden_report.baseline_metrics["initial_outlay_won"])
    npv = float(golden_report.metrics[CONCLUSION_METRIC])
    low_rate = golden_report.subsidy_rate
    high_rate = low_rate + 0.2

    low = _build(golden_report, subsidy_rate=low_rate)
    high = _build(golden_report, subsidy_rate=high_rate)
    assert low != high, (
        "지원율을 20%p 올렸는데 조립 결과가 한 글자도 달라지지 않았습니다 — "
        "`subsidy_rate` 를 읽지 않는 구현입니다"
    )

    rates = {}
    for rate, formulas in ((low_rate, low), (high_rate, high)):
        expected = break_even_subsidy_rate(
            subsidy_rate=rate, npv_won=npv, total_project_cost_won=total
        )
        rates[rate] = expected
        line = _by_label(formulas, _FLIP_LABEL).substituted
        assert line.startswith(f"{expected:.1%}"), (
            f"지원율 {rate:.1%} 에서 「{_FLIP_LABEL}」의 대입값이 환산값 "
            f"{expected:.1%} 로 시작하지 않습니다: {line}"
        )
        assert f"= {rate:.1%} -" in line, (
            f"「{_FLIP_LABEL}」의 대입값에 넘긴 현 지원율 {rate:.1%} 이 "
            f"없습니다: {line}"
        )

    assert rates[high_rate] > rates[low_rate], (
        f"지원율을 올렸는데 전환 지원율이 오르지 않았습니다: "
        f"{rates[low_rate]:.1%} → {rates[high_rate]:.1%}"
    )


def test_the_assembly_never_returns_an_empty_tuple(golden_report: CaseReport) -> None:
    """반환이 **`Formula` 의 짝**이고 건수가 0 이 아니다 (성질 마).

    조립이 조용히 빈 것을 내면 붙임 3 이 통째로 비는데, 그 상태는 **아무 오류도
    내지 않는다** — 리포트는 정상으로 인쇄되고 산식 절만 사라진다. 건수를 몇으로
    박지 않는 이유는 그것이 실행에 따라 갈리기 때문이다: 전환 지원율이 지원 상한을
    넘으면 「전액 지원 시 잔여 결손」 한 건이 더 붙는다.
    """
    formulas = _build(golden_report)

    assert isinstance(formulas, tuple)
    assert formulas, "산식 조립이 0건을 냈습니다 — 붙임 3 이 통째로 빕니다"
    for item in formulas:
        assert isinstance(item, Formula)


def test_the_report_carries_exactly_what_the_assembler_builds(
    golden_report: CaseReport,
) -> None:
    """리포트의 붙임 3 이 **조립기가 낸 것 그대로**다 — 갈라 놓은 뒤의 배선.

    R64/WP-2 가 이 함수를 다른 파일로 옮기며 *「동작을 바꾸지 않았다」* 고 적었다.
    옮긴 자체는 지금 다시 잴 수 없지만(옛 자리가 없다), **호출부가 규약대로
    넘기는가**는 잴 수 있다 — 기준선 변형의 초기지출을 총사업비로, 계획 변형의
    지표를 지표로 넘긴다.

    ⚠ **이 골든에서는 두 값이 같다**(무보조라 `CaseBasis` 의 총사업비와 기준선
    초기지출이 둘 다 9,800,000원이다). 그러므로 이 검사는 *「`I₀` 로 어느 쪽을
    골랐는가」* 를 갈라내지 못하고, **호출부가 다른 것을 끼워 넣지 않았다**는
    것만 붙든다. 어느 쪽을 골라야 하는지는 `build_formulas()` 독스트링이 진다.
    """
    assert tuple(golden_report.formulas) == _build(golden_report), (
        "리포트가 실은 산식이 조립기가 내는 것과 다릅니다 — 호출부가 다른 값을 "
        "넘기고 있거나 조립 뒤에 문면을 손보고 있습니다"
    )
