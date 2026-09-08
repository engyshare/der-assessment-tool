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

import pytest

from app.run.report_cli import (
    DEFAULT_SCENARIO,
    INDEX_FILENAME,
    REPORT_OUT_DIR_ENV,
    main,
)
from app.services.verify_steps import split_stages
from core.report.case_report import build_case_report
from core.report.verification import render_verification_markdown

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


def test_stderr_names_which_report_kind_was_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "verification.md"
    assert main(["--kind", "verification", "--out", str(target)]) == 0
    message = capsys.readouterr().err
    assert "verification" in message


def test_no_judgement_sentences(tmp_path: Path) -> None:
    """해설 금지(판정 §6) — 「이 사업은 …이다」류 판정 문장이 실리지 않는다."""
    text = _verification_text(tmp_path)
    for banned in ("타당하다", "타당하지", "적절하다", "바람직하다", "권고한다", "결론적으로"):
        assert banned not in text, f"판정 문장으로 읽히는 낱말이 있다: {banned!r}"


# ---------------------------------------------------------------------------
# R67/WP-1 — `--split-stages`: 검증 보고서를 단계별 파일로 나눠 내는 선택지.
# 요구 정본: `docs/decisions-2026-09-08-R67.md` §4-1.
# ---------------------------------------------------------------------------


def _stage_dir(tmp_path: Path) -> Path:
    """`--split-stages` 로 단계별 파일을 뽑는다 — 돌려값은 받은 디렉터리."""
    out_dir = tmp_path / "stages"
    assert (
        main(["--kind", "verification", "--split-stages", "--out", str(out_dir)]) == 0
    )
    return out_dir


def test_split_stages_writes_nine_stage_files_and_an_index(tmp_path: Path) -> None:
    out_dir = _stage_dir(tmp_path)
    names = sorted(p.name for p in out_dir.iterdir())
    assert names[0] == INDEX_FILENAME, "목차가 사전순으로 가장 앞이어야 한다"
    stage_files = names[1:]
    assert len(stage_files) == 9, f"단계 파일은 9개여야 한다: {stage_files}"
    assert [n[:2] for n in stage_files] == [f"{n:02d}" for n in range(1, 10)], (
        "사전순 = 단계순이어야 한다(01- … 09-)"
    )


def test_split_stages_index_lists_every_stage(tmp_path: Path) -> None:
    out_dir = _stage_dir(tmp_path)
    index = (out_dir / INDEX_FILENAME).read_text(encoding="utf-8")
    for stage in split_stages(_verification_text(tmp_path)):
        row = f"| {stage.number} | {stage.title} |"
        assert row in index, f"목차에 {stage.number}단계의 번호·제목 행이 없다"
    for path in sorted(out_dir.iterdir()):
        if path.name != INDEX_FILENAME:
            assert path.name in index, f"목차가 실제 파일을 가리키지 않는다: {path.name}"


def test_split_stages_index_carries_the_reports_provenance(tmp_path: Path) -> None:
    """목차는 가르면서 사라진 출처를 보관한다 — 시나리오명·전제 대장 판·매니페스트.

    값은 `report` 를 독립 재실행해 얻어 대조한다(박아 두면 시나리오가 바뀌는
    날 거짓이 된다). 라벨과 16자리 매니페스트 자릿수는 렌더러 머리말
    (`core/report/verification.py`)과 같다 — stderr 보고의 12자리가 아니다.
    """
    index = (_stage_dir(tmp_path) / INDEX_FILENAME).read_text(encoding="utf-8")
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )
    assert f"| 평가 대상 | {report.scenario_name} |" in index
    assert (
        f"| 전제 대장 | `{report.assumption_set_name}` 판 "
        f"{report.assumption_set_version} |" in index
    )
    assert f"| 실행 매니페스트 | `{report.manifest_hash[:16]}` |" in index


def test_verification_without_split_stages_is_the_unchanged_single_file(
    tmp_path: Path,
) -> None:
    """★★★ `--split-stages` 를 «주지 않으면» 종전의 한 덩어리 그대로다.

    골든값과 `/ui/verify` 화면이 이 문자열에 걸려 있다(WP-1 합격 조건).
    종전과의 대조는 렌더러를 **독립 재실행해** 잰다 — CLI 를 두 번 불러 서로
    같다고 확인하는 것만으로는 «안 바뀌었다»가 증명되지 않는다."""
    single = tmp_path / "single.md"
    again = tmp_path / "single_again.md"
    assert main(["--kind", "verification", "--out", str(single)]) == 0
    assert main(["--kind", "verification", "--out", str(again)]) == 0
    assert single.read_bytes() == again.read_bytes(), "같은 시나리오 두 번이 다르다"
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )
    assert single.read_text(encoding="utf-8") == render_verification_markdown(report)


def test_split_stage_files_cover_every_stage_of_the_original(tmp_path: Path) -> None:
    """나눈 조각을 이어 보면 단계 본문이 원본에 «다» 있다 — 빠진 단계가 없다."""
    out_dir = _stage_dir(tmp_path)
    original = _verification_text(tmp_path)
    pieces = {
        path.read_text(encoding="utf-8")
        for path in out_dir.iterdir()
        if path.name != INDEX_FILENAME
    }
    for stage in split_stages(original):
        assert stage.body in original, "픽스처 전제가 깨졌다 — body 는 원본 조각이다"
        assert stage.body in pieces, f"{stage.number}단계 파일이 본문을 온전히 담지 않는다"


def test_split_stages_refuses_deliberation_kind(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--split-stages` 는 검증 보고서 전용 — 다른 `--kind` 와 함께 주면 멈춘다."""
    target = tmp_path / "should-not-exist"
    rc = main(["--kind", "deliberation", "--split-stages", "--out", str(target)])
    assert rc != 0
    assert not target.exists(), "오류로 멈췄으면 아무 것도 쓰지 않는다"
    assert capsys.readouterr().err.strip() != ""


def test_split_stages_requires_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """단계별 파일은 표준출력으로 낼 수 없다 — 받을 자리가 없으면 멈춘다.

    ⚠ 환경변수를 **지우고** 잰다 — 이 검사가 재는 것은 「자리가 없을 때」이고,
    돌리는 기계에 `DER_REPORT_OUT_DIR` 가 서 있으면 자리가 «있는» 것이라
    지우지 않으면 검사가 기계에 따라 답을 바꾼다.
    """
    monkeypatch.delenv(REPORT_OUT_DIR_ENV, raising=False)
    assert main(["--kind", "verification", "--split-stages"]) != 0


def test_out_dir_env_names_the_file_when_out_is_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--out` 을 안 주면 `DER_REPORT_OUT_DIR` 자리에 이름을 지어 쓴다."""
    monkeypatch.setenv(REPORT_OUT_DIR_ENV, str(tmp_path))
    assert main(["--kind", "verification"]) == 0
    written = sorted(path.name for path in tmp_path.iterdir())
    assert written == [f"{DEFAULT_SCENARIO}-verification.md"], written
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )
    body = (tmp_path / written[0]).read_text(encoding="utf-8")
    assert body == render_verification_markdown(report)


def test_out_dir_env_names_the_directory_when_splitting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """분할도 같은 자리에 쓴다 — 그때 이름은 **디렉터리**이고 꼬리로 갈린다."""
    monkeypatch.setenv(REPORT_OUT_DIR_ENV, str(tmp_path))
    assert main(["--kind", "verification", "--split-stages"]) == 0
    out_dir = tmp_path / f"{DEFAULT_SCENARIO}-verification-단계별"
    assert out_dir.is_dir(), sorted(p.name for p in tmp_path.iterdir())
    assert INDEX_FILENAME in {path.name for path in out_dir.iterdir()}


def test_explicit_out_wins_over_the_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ `--out` 을 적었으면 환경변수가 그것을 덮지 않는다.

    덮으면 사용자가 적은 경로가 **조용히 무시된다** — 그 침묵이 「썼는데 없다」로
    돌아온다.
    """
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    monkeypatch.setenv(REPORT_OUT_DIR_ENV, str(env_dir))
    explicit = tmp_path / "적은자리.md"
    assert main(["--kind", "verification", "--out", str(explicit)]) == 0
    assert explicit.exists(), "명시한 자리에 쓰이지 않았다"
    assert list(env_dir.iterdir()) == [], "환경변수 자리에도 썼다 — 두 벌이 생긴다"


def test_env_var_absent_still_goes_to_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """둘 다 없으면 **종전처럼** 표준출력이다 — 규약이며 결함이 아니다."""
    monkeypatch.delenv(REPORT_OUT_DIR_ENV, raising=False)
    assert main(["--kind", "verification"]) == 0
    assert "# 계산 검증 보고서" in capsys.readouterr().out
