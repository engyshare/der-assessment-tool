"""검증 보고서 — CLI 배선과 단계 인계값 대조 (사용자 판정 §2 · R52/WP-1).

`docs/decisions-2026-09-02-R52.md` §2: *「계산값 대조는 현 시점에서 불가함
(처음 하는 사업이라서 계산 결과가 없음) 대신 본 프로그램에서 순차적으로
검증을 진행할 수 있도록 단계적으로 정보를 제공해야 함」*. 대조군이 없으므로
이 검사가 대신 붙드는 것은 ⓐ 배포 경로(CLI)가 실제로 그 산출물을 내는가와
ⓑ 단계 사이에서 넘어간다고 적은 수가 **실제로 같은 수인가**다.

★★★ **렌더러 함수만 직접 부르는 검사를 주 검사로 두지 않는다.**
`app.run.report_cli.main(["--kind", "verification", …])` 를 통과해 CLI 로 뽑은
문면을 검사한다 — 그렇지 않으면 CLI 배선이 끊겨도 초록불이다(`status.md`
함정 「검사가 배포 코드가 부르지 않는 함수를 직접 불러 통과한다」 · R51/R26).

⚠ **`@pytest.mark.req(...)` 를 달지 않았다.** spec 을 훑어 이 산출물(검증
보고서)에 대응하는 수용기준을 찾지 못했다 — `FR-1001`~`FR-1005` 는 심의용
리포트(`MC-1`)의 산식 표기·영향도·내보내기 형식을 정할 뿐 「단계별 검증
보고서」라는 별도 산출물을 요구하지 않는다. `tests/app/test_report_cli.py`
의 `test_cli_writes_a_report_file` 가 같은 이유로 마커를 달지 않은 전례를
따른다 — 맞지 않는 조항을 달면 「이 조항을 충족했다」는 거짓 인용이 된다.
spec 개정 여부는 `status-human.md` 로 넘긴다.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from app.run.report_cli import DEFAULT_SCENARIO, main
from core.report.case_report import build_case_report

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"

_CELLS = ("ⓐ 전제한 수치", "ⓑ 계산된 수치", "ⓒ 다음 단계로 넘긴 값", "ⓓ 계산 수식")


def _verification_text(tmp_path: Path, scenario: str = DEFAULT_SCENARIO) -> str:
    """CLI 를 통해 검증 보고서를 뽑는다 — 렌더러를 직접 부르지 않는다."""
    target = tmp_path / "verification.md"
    rc = main(
        ["--kind", "verification", "--scenario", scenario, "--out", str(target)]
    )
    assert rc == 0
    return target.read_text(encoding="utf-8")


def test_cli_writes_nine_stages_each_with_four_cells(tmp_path: Path) -> None:
    text = _verification_text(tmp_path)
    for n in range(1, 10):
        assert f"## {n}단계" in text, f"{n}단계가 CLI 산출물에 없다"
    for cell in _CELLS:
        assert text.count(cell) == 9, f"{cell!r} 칸이 9단계마다 하나씩 있지 않다"


def test_transferred_values_agree_when_read_from_the_pipeline_independently(
    tmp_path: Path,
) -> None:
    """4·5단계 ⓒ 의 연 편익·운영비가 7단계 현금흐름 1년차 합과 같은 수인가.

    ⚠ **검사 대상(`verification.py`)의 계산을 다시 부르지 않는다** — 그러면
    「렌더러는 렌더러가 계산한 값을 인쇄한다」만 확인하는 동어반복이 된다
    (`status.md` 함정 「검사가 자기 검사 대상에서 정본을 읽어 오면
    공허해진다」). 대신 `CaseReport`·`CashflowSplit` 을 **재실행해 독립적으로**
    읽고, CLI 산출 문면과 대조한다.
    """
    text = _verification_text(tmp_path)
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )

    benefit_year1 = sum(
        int(row.amounts.get(1, Decimal(0))) for row in report.cashflows.benefit
    )
    assert benefit_year1 == report.basis.annual_benefit_won, (
        "픽스처 전제가 깨졌다 — 이 대조가 성립하려면 4단계와 7단계의 1년차 "
        "편익 합이 애초에 같은 수여야 한다"
    )
    assert f"{report.basis.annual_benefit_won:,}원" in text
    assert "✔ 일치" in text, "CLI 산출물이 4단계 ⓒ와 7단계 편익 행의 일치를 보이지 않는다"
    assert "⚠ 불일치" not in text, "CLI 산출물이 단계 사이 어긋남을 스스로 드러냈다"

    opex_year1 = sum(
        int(row.amounts.get(1, Decimal(0)))
        for row in (
            *report.cashflows.operating_cost, *report.cashflows.lifecycle,
        )
    )
    assert opex_year1 == report.basis.annual_cost_won, (
        "픽스처 전제가 깨졌다 — `annual_cost_won` 은 운영비+생애주기 1년차 "
        "합으로 만들어진다(e2e_runner.py)"
    )
    assert f"{report.basis.annual_cost_won:,}원" in text


def test_default_kind_is_byte_identical_to_omitting_the_flag(tmp_path: Path) -> None:
    """`--kind` 를 안 주면 `deliberation` 과 **바이트 동일**해야 한다 — `MC-1`
    재산출이 이 기본 경로를 그대로 쓴다."""
    with_flag = tmp_path / "with_flag.md"
    without_flag = tmp_path / "without_flag.md"
    assert main(["--kind", "deliberation", "--out", str(with_flag)]) == 0
    assert main(["--out", str(without_flag)]) == 0
    assert with_flag.read_bytes() == without_flag.read_bytes()


def test_verification_kind_differs_from_deliberation(tmp_path: Path) -> None:
    verification = tmp_path / "verification.md"
    deliberation = tmp_path / "deliberation.md"
    assert main(["--kind", "verification", "--out", str(verification)]) == 0
    assert main(["--out", str(deliberation)]) == 0
    assert (
        verification.read_text(encoding="utf-8")
        != deliberation.read_text(encoding="utf-8")
    )


def test_stderr_names_which_report_kind_was_written(tmp_path: Path, capsys) -> None:
    target = tmp_path / "verification.md"
    assert main(["--kind", "verification", "--out", str(target)]) == 0
    message = capsys.readouterr().err
    assert "verification" in message


def test_no_judgement_sentences(tmp_path: Path) -> None:
    """해설 금지(판정 §6) — 「이 사업은 …이다」류 판정 문장이 실리지 않는다."""
    text = _verification_text(tmp_path)
    for banned in ("타당하다", "타당하지", "적절하다", "바람직하다", "권고한다", "결론적으로"):
        assert banned not in text, f"판정 문장으로 읽히는 낱말이 있다: {banned!r}"
