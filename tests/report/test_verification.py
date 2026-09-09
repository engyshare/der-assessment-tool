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
from app.services.verify_steps import STAGE_COUNT, split_stages
from core.report.appendix_sections import appendix_section
from core.report.case_report import CONCLUSION_METRIC, build_case_report
from core.report.verification import (
    StageBlock,
    render_verification_markdown,
    stage_blocks,
)
from core.report.verification_chain import (
    CHAIN_NODES,
    CHAIN_TITLE,
    NO_STAGE_NAMED,
    dependency_chain_lines,
    handoff_text,
    named_stages,
)
from core.report.verification_demand import DEMAND_ATTRIBUTE_HEAD
from core.report.verification_dispatch import (
    DISPATCH_TABLE_HEAD,
    LINKAGE_NOTE,
    SIGN_CONVENTION_NOTE,
)
from core.report.verification_gates import (
    GATE_NONE,
    GATE_ROW_NAMES,
    GATE_TITLE,
    QUESTION_HEAD,
    STAGE_QUESTIONS,
    gate_lines,
    run_identity_line,
    run_identity_rows,
    stage_gate,
    stage_question,
)
from core.report.verification_scaleup import (
    COINCIDENCE_EXCLUDED,
    EXCLUDED_BY_DECISION,
    SCALEUP_TITLE,
)
from core.report.verification_variants import (
    STAGE8_FORMULA_POINTER,
    unbuilt_variant_columns,
)

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


def test_the_sign_convention_moved_from_the_numbers_cell_to_the_formula_cell(
    tmp_path: Path,
) -> None:
    """★★★ **부호 규약이 ⓑ 에서 ⓓ 로 내려갔다** (R68/WP-2 · 검토서 §4.3).

    검토서 문면: *「현재는 양수·음수 부호 규칙을 읽어야 한다. 사람용 표에서는
    한전 수전·역송을 양의 수량으로 별도 열에 두고, **내부 부호는 수식 설명에만**
    남기는 편이 안전하다」*. 종전에는 그 규약 줄이 계절 기여 표 바로 아래
    (ⓑ 계산된 수치)에 있었고, 그래서 **표를 읽기 전에 규약을 먼저 읽어야** 했다.

    ⚠ **표 자체의 부호는 그대로다** — 자원 수지는 부호가 뜻이며(충전과 방전이
    한 열에 서야 스텝 합계를 눈으로 셀 수 있다) 옮긴 것은 규약 줄이다. 그래서
    이 검사는 「부하가 음수로 남아 있는가」까지 함께 잰다.
    """
    stage3 = split_stages(_verification_text(tmp_path))[2]
    cells = stage3.body.split("**ⓓ 계산 수식**")
    assert len(cells) == 2, f"3단계에 ⓓ 칸이 하나가 아니다 — {stage3.title}"
    before, formula = cells
    assert SIGN_CONVENTION_NOTE in formula, (
        f"부호 규약 줄이 ⓓ(계산 수식) 칸에 없다 — 「{SIGN_CONVENTION_NOTE[:30]}…」"
    )
    assert "부호 규약" not in before, (
        "부호 규약이 아직 ⓓ 앞(ⓐ·ⓑ·ⓒ)에 남아 있다 — 사람이 읽는 표를 규약보다 "
        "먼저 읽을 수 있어야 한다"
    )
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )
    negatives = [
        name
        for season in report.seasons
        for name, kwh in season.per_resource_annual_kwh.items()
        if kwh < 0.0
    ]
    assert negatives, (
        "픽스처 전제가 깨졌다 — 음수로 실리는 자원이 하나도 없어 부호 규약이 "
        "가리킬 것이 없다"
    )
    assert f"| {min(negatives)} |" not in stage3.body, (
        "계절 기여 표가 조인 키만으로 서 있다 — 사람용 이름을 병기해야 한다"
    )


def test_the_dispatch_table_splits_the_declaration_from_the_applied_allocation(
    tmp_path: Path,
) -> None:
    """★★★ **3단계 ⓐ 표가 선언 열과 실제 배분 열 «둘»을 갖는다** (검토서 §3.3).

    한 칸에 「전량 판매 (선언) · 본 실행 배분: 집 우선」이 함께 적혀, 같은
    문서의 「자가소비율 … (본 실행 실측)」과 **모순으로 읽혔다.** 두 축은 실제로
    둘 다 참이므로(선언은 잉여의 처분 방침 · 배분은 낮 동안 잉여의 행선지)
    없애지 않고 **가른다.**

    ⚠ 표 아래 세 줄이 함께 서 있어야 한다 — 갈렸다는 사실과 그것이 결함이
    아닌 사유, 이 실행에서 그 선언이 실현됐는가, 그리고 4단계와의 연결이다.
    적지 않으면 두 열이 「표기 문제」로만 읽힌다.
    """
    stage3 = split_stages(_verification_text(tmp_path))[2].body
    assert "\n".join(DISPATCH_TABLE_HEAD) in stage3, (
        "3단계 ⓐ 표의 머리가 두 열로 갈리지 않았다"
    )
    assert LINKAGE_NOTE in stage3, "4단계와의 연결 줄이 없다"
    assert "선언과 본 실행 배분이 갈린 자원" in stage3, (
        "선언과 실제가 갈렸는지를 말하는 줄이 없다"
    )
    assert "이 실행에서 그 선언이 실현됐는가" in stage3, (
        "그 선언이 이 실행에서 실현됐는지를 말하는 줄이 없다"
    )


def test_the_stage_three_file_carries_a_full_day_for_every_season(
    tmp_path: Path,
) -> None:
    """★★★ **CLI 산출물의 3단계 파일에 계절마다 하루가 전건 실린다** (검토서 §3.4).

    검토서 문면: *「계절별 연간 수전량은 있으나 … 계절마다 24스텝 표가 필요하다.
    표 아래에 «하루 합계 × 계절 일수 = 계절 연간값» 을 대조해야 한다」*.

    ★ **렌더러를 직접 부르지 않는다** — 이 파일 머리말의 사유이며, 배선이
    끊기면 다른 검사가 초록불이어도 사용자는 그 표를 못 본다.

    ⚠ 계절 이름·개수·스텝 수를 리터럴로 박지 않는다 — 리포트가 실어 온 것으로
    기대를 만든다. 박으면 자산이 달력을 바꾸는 날 이 검사가 「리포트가 틀렸다」로
    빨간불이 된다.
    """
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )
    assert len(report.seasons) >= 2, "이 시나리오가 계절을 갈라 돌지 않았다"

    stage3 = split_stages(_verification_text(tmp_path))[2].body
    rows = [
        line
        for line in stage3.splitlines()
        if line.startswith("| ") and "시 |" in line
    ]
    steps = len(report.dispatch_hours)
    assert len(rows) == steps * len(report.seasons), (
        f"3단계의 스텝 행이 {len(rows)}개다 — 계절 {len(report.seasons)}개에 "
        f"{steps}스텝을 곱한 {steps * len(report.seasons)}개여야 한다. 적으면 "
        "표본을 실은 것이고, 많으면 계절을 이어 붙인 것이다"
    )
    for season in report.seasons:
        assert f"**{season.name} — 대표일 {steps}스텝** (연 {season.days}일" in stage3, (
            f"{season.name} 의 하루 표 제목이 없거나 일수·스텝 수를 안 적었다"
        )
        annual = f"{season.grid_import_annual_kwh:,.2f}"
        assert annual in stage3, (
            f"{season.name} 의 대조에 러너가 실어 온 연간 수전량 {annual} 이 없다"
        )


def test_the_stage_two_file_carries_the_scale_up_rule(tmp_path: Path) -> None:
    """★★★ **CLI 산출물의 2단계 파일이 확대 규칙 표를 싣는다** (검토서 §3.5).

    검토서 문면: *「현재 20가구 총수요 = 가구당 총수요 × 20 은 표시되지만, 자원
    구성과 시간대 피크의 확대 규칙이 같은 수준으로 설명되지 않는다」*.

    ★ **렌더러를 직접 부르지 않는다** — 이 파일 머리말의 사유이며, 배선이
    끊기면 다른 검사가 초록불이어도 사용자는 그 표를 못 본다. 표의 축과 판정은
    `tests/report/test_verification_scaleup.py` 가 잰다 — 여기서는 **그 표가
    2단계 파일에 실려 나가는가**와 **단지 값이 실행값 그대로인가**만 본다.

    ⚠ 수를 리터럴로 박지 않는다 — 리포트가 실어 온 것으로 기대를 만든다.
    """
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )
    count = report.household_count
    assert count is not None and count > 1, "이 시나리오가 단지 규모로 돌지 않았다"

    stage2 = split_stages(_verification_text(tmp_path))[1].body
    assert SCALEUP_TITLE in stage2, "2단계에 확대 규칙 표의 제목이 없다"
    assert f"| 무엇 | 한 호 기준값 | 배수를 곱하는 자리 | {count}호 값 |" in stage2, (
        "표 머리가 없거나 단지 열이 실행의 가구 수를 이름으로 갖지 않는다"
    )
    for finding in report.capacity_review:
        assert f"| {finding.used_value:g} {finding.unit} |" in stage2, (
            f"{finding.label} 의 단지 값이 실행값({finding.used_value:g})과 다르다"
        )
    power_kw = report.ess_sizing.run_power_kw
    assert power_kw is not None, "이 실행이 저장장치를 세우지 않았다"
    assert f"| {power_kw:g} kW |" in stage2, "저장장치 정격출력 행이 없다"
    for where, _why in COINCIDENCE_EXCLUDED:
        assert f"| {where} | {EXCLUDED_BY_DECISION} |" in stage2, (
            f"동시율을 걸지 않는 자리 「{where}」가 「제외」로 서 있지 않다 — "
            "누락으로 읽히면 다음 사람이 넣고 결론축이 조용히 좋아진다"
        )


def test_the_stage_one_file_carries_the_six_attributes_of_every_demand_input(
    tmp_path: Path,
) -> None:
    """★★★ **CLI 산출물의 1단계 파일이 수요 입력의 여섯 속성을 싣는다** (검토서 §3.1).

    검토서 문면: *「모든 수요 입력에 `값`, `단위`, `출처`, `계측 경계`, `산출식`,
    `변경 경로`를 둔다」*.

    ★ **렌더러를 직접 부르지 않는다** — 배선이 끊기면 다른 검사가 초록불이어도
    사용자는 그 표를 못 본다. 표의 속살(대장 문면과 글자로 같은가 · 충전효율이
    곱해지지 않는가 · 멈춘 자리 둘)은 `tests/report/test_verification_demand.py`
    가 잰다 — 여기서는 **1단계 파일에 실려 나가는가**만 본다.

    ⚠ 「전제」를 세지 않는다 — 그 검사는 `test_the_stage_frame_adds_no_premise_word
    _and_no_new_stage` 와 화면 낱말 검사가 각자 지고 있다.
    """
    stage1 = split_stages(_verification_text(tmp_path))[0].body
    for line in DEMAND_ATTRIBUTE_HEAD:
        assert line in stage1, "1단계에 여섯 속성 표의 머리가 없다"
    # 멈춘 자리 둘이 **글자로** 서 있다 — 빈칸은 「없다」와 「싣지 못했다」를 가르지
    # 못하고, 이 둘은 사람의 판정을 기다리는 자리다(검토서 §3.1 · §4.4).
    assert "난방·냉방·급탕 분해는 이 표에 없다" in stage1
    assert "검증 상태(계산됨 · 출처 확인 · 조사 인용 · 가정)는 대장이 갖고 있지 않다" in stage1


# ── WP-4-fix — 목차의 의존 연결표 (검토서 §2.2) ─────────────────────────────


def _block(number: int, handoff: tuple[str, ...]) -> StageBlock:
    """시험용 단계 하나 — **ⓒ 만 다르다.** 본문은 이 검사들이 보지 않는다."""
    return StageBlock(number=number, title=f"{number}번", lines=(), handoff=handoff)


def _nine(handoff: tuple[str, ...]) -> tuple[StageBlock, ...]:
    """사슬이 가리키는 단계가 **다 있는** 아홉 — 그중 첫 단계만 ⓒ 를 바꾼다."""
    return tuple(
        _block(number, handoff if number == 1 else ("—",))
        for number in range(1, STAGE_COUNT + 1)
    )


def test_stage_blocks_carry_the_very_lines_the_stage_body_prints() -> None:
    """★★★ **ⓒ 는 사본이 아니라 같은 조각이다** (WP-4-fix).

    목차가 ⓒ 문면을 따로 적으면 단계가 바뀌는 날 목차만 옛말을 한다. 그래서
    렌더러가 단계를 지을 때 손에 있던 `c` 를 **그대로** 함께 낸다 — 이 검사는
    `handoff` 가 그 단계 본문의 ⓒ 절 **자리에 그대로 들어 있는지**를 잰다.
    """
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )
    blocks = stage_blocks(report)
    assert [block.number for block in blocks] == list(range(1, STAGE_COUNT + 1))
    for block in blocks:
        assert block.lines[0] == f"## {block.number}단계 — {block.title}"
        head = block.lines.index("**ⓒ 다음 단계로 넘긴 값**")
        # 머리글 · 빈 줄 다음이 ⓒ 줄들이다 — 조각이 같은지 그 자리에서 본다.
        start = head + 2
        assert block.lines[start : start + len(block.handoff)] == block.handoff, (
            f"{block.number}단계의 ⓒ 가 본문과 다른 조각이다"
        )
        assert block.handoff, f"{block.number}단계의 ⓒ 가 비어 있다"


def test_the_index_dependency_table_is_collected_not_rewritten(tmp_path: Path) -> None:
    """★★★ **목차의 연결표가 각 단계의 ⓒ 에서 온다** (검토서 §2.2).

    ★ 렌더러를 직접 부르는 것으로 끝내지 않는다 — 목차 파일을 CLI 로 뽑아
    **그 파일 안에** 아홉 행이 있는지 본다(배선이 끊기면 사용자는 그 표를 못 본다).
    """
    index = (_stage_dir(tmp_path) / INDEX_FILENAME).read_text(encoding="utf-8")
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )
    assert f"## {CHAIN_TITLE}" in index, "목차에 의존 연결 절이 없다"
    for block in stage_blocks(report):
        row = (
            f"| {block.number}단계 | {handoff_text(block)} "
            f"| {named_stages(block)} |"
        )
        assert row in index, f"{block.number}단계의 인계 행이 목차에 없다"


def test_the_chain_line_and_the_node_table_come_from_one_source(
    tmp_path: Path,
) -> None:
    """사슬 한 줄과 마디 표가 **같은 자료**에서 온다 — 마디를 두 번 적지 않는다."""
    index = (_stage_dir(tmp_path) / INDEX_FILENAME).read_text(encoding="utf-8")
    chain = " → ".join(label for label, _stages in CHAIN_NODES)
    assert f"`{chain}`" in index, "사슬 한 줄이 마디 표와 다른 낱말을 쓴다"
    for label, numbers in CHAIN_NODES:
        cell = " · ".join(f"{number}단계" for number in numbers)
        assert f"| {label} | {cell} |" in index, f"마디 「{label}」 행이 없다"
    # 사슬이 이름 부르지 않은 단계도 **세어서** 적는다 — 손으로 적지 않는다.
    mapped = {number for _label, numbers in CHAIN_NODES for number in numbers}
    unnamed = [n for n in range(1, STAGE_COUNT + 1) if n not in mapped]
    assert unnamed, "이 검사의 전제가 깨졌다 — 사슬이 아홉 단계를 다 이름 부른다"
    assert " · ".join(f"{n}단계" for n in unnamed) in index


def test_the_named_stage_column_follows_the_prose_not_a_hand_list() -> None:
    """오른쪽 칸은 **ⓒ 가 스스로 이름 부른 단계**다 — 자기 단계는 세지 않는다."""
    named = named_stages(_block(2, ("이 값은 4단계와 7단계가 받는다.",)))
    assert named == "4단계 · 7단계"
    # ⚠ **부정문을 읽지 못한다** — 적힌 이름을 그대로 센다. 그래서 칸 이름이
    # 「받는 단계」가 아니라 **「ⓒ 가 이름 부른 단계」**다(그 낱말이 이 한계를
    # 산출물에 적어 둔다). 이 검사가 그 한계를 «고정»한다.
    assert named_stages(_block(2, ("1단계가 아니라 4단계가 받는다.",))) == "1단계 · 4단계"
    assert "2단계" not in named_stages(_block(2, ("2단계 안에서만 쓰인다.",)))
    assert named_stages(_block(9, ("이후 단계로 넘기는 값이 없다.",))) == NO_STAGE_NAMED
    # 범위 문면(`2~9단계`)을 두 수로 쪼개 읽지 않는다 — 적힌 대로 싣는다.
    assert named_stages(_block(1, ("2~9단계 전체에서 쓰인다.",))) == "2~9단계"


def test_a_table_row_in_the_handoff_does_not_land_in_the_cell() -> None:
    """⚠ **칸에 표를 넣을 수 없다** — 1단계의 ⓒ 는 문장 하나 + 표 열일곱 행이다.

    표 행을 그대로 밀어 넣으면 목차의 표가 깨지고, 깨진 표는 「연결이 없다」로
    읽힌다. 그래서 문장만 싣고 **표는 그 단계 파일이 진다**(그 사실을 표 아래
    글자로 적는다).
    """
    block = _block(1, ("문장이다.", "", "| 변수 | 값 |", "|---|---|", "| a | 1 |"))
    assert handoff_text(block) == "문장이다."
    # 문장 «안에» 파이프가 있으면 탈출시킨다 — 그때도 표가 깨지지 않는다.
    assert handoff_text(_block(1, ("a | b 를 넘긴다.",))) == r"a \| b 를 넘긴다."


def test_a_chain_node_pointing_at_a_missing_stage_stops() -> None:
    """⚠ 사슬이 **없는 단계**를 가리키면 멈춘다 — 빈 칸으로 지나가지 않는다.

    빈 칸이면 검토자는 *「그 마디는 어디서도 안 나온다」* 로 읽는다.
    """
    missing = max(number for _label, numbers in CHAIN_NODES for number in numbers)
    blocks = tuple(block for block in _nine(("—",)) if block.number != missing)
    with pytest.raises(ValueError, match="사슬이 없는 단계를 가리킨다"):
        dependency_chain_lines(blocks)


def test_the_dependency_table_adds_no_stage_and_no_premise_word() -> None:
    """⛔ 단계를 늘리지 않고 ⛔ 사람이 읽는 자리에 「전제」를 새로 세우지 않는다.

    ⚠ 「전제」는 **이 모듈이 짓는 자리**(절 제목·표 머리)에서 잰다 — 가운데 칸은
    각 단계의 ⓒ 문면이고 그 낱말의 책임은 그 단계에 있다.
    """
    lines = dependency_chain_lines(_nine(("4단계가 받는다.",)))
    assert not any(line.startswith("## ") and "단계 — " in line for line in lines)
    authored = [f"## {CHAIN_TITLE}"] + [
        line for line in lines if line.startswith("| 사슬의 마디") or line.startswith("| 단계 |")
    ]
    assert len(authored) == 3, authored
    for line in authored:
        assert "전제" not in line


# ── WP-5 — 단계의 물음 · 실행 식별자 · 판단 게이트 (검토서 §2.1 · §4.1 · §4.7) ──


def test_every_stage_opens_with_the_question_it_answers(tmp_path: Path) -> None:
    """★★★ **아홉 단계가 저마다 답하는 물음을 첫 줄에 세운다** (검토서 §2.1).

    검토서 문면: *「각 파일은 ⓐ→ⓑ→ⓒ→ⓓ 틀을 반복한다. 이 형식은 계산 검증에는
    유용하지만, 각 단계가 **답하는 사업 질문을 드러내지 못한다**」*.

    ⚠ 물음의 문면을 이 검사가 다시 적지 않는다 — `STAGE_QUESTIONS` 에서 읽어
    맞댄다. 여기 베끼면 물음을 고치는 날 검사만 옛말을 한다.
    """
    stages = split_stages(_verification_text(tmp_path))
    assert len(STAGE_QUESTIONS) == STAGE_COUNT, "물음이 단계 수와 다르다"
    assert len(set(STAGE_QUESTIONS)) == STAGE_COUNT, "두 단계가 같은 물음을 적었다"
    for stage in stages:
        lines = stage.body.splitlines()
        assert lines[0].startswith(f"## {stage.number}단계"), lines[0]
        assert lines[2] == f"{QUESTION_HEAD} — {stage_question(stage.number)}", (
            f"{stage.number}단계의 첫 줄이 그 단계의 물음이 아니다: {lines[2]!r}"
        )
        assert lines[2].endswith("?"), (
            f"{stage.number}단계의 물음이 물음으로 끝나지 않는다 — 「답해야 할 "
            "질문」이 아니라 설명이 됐다"
        )


def test_every_stage_names_the_run_it_came_from(tmp_path: Path) -> None:
    """★★★ **단계 파일 하나만 열어도 어느 실행인지 안다** (검토서 §4.1).

    종전에는 평가 대상·대장 판·매니페스트가 `00-목차.md` 에만 있어, 단계 파일을
    폴더 밖으로 꺼내면 어느 실행의 수인지 알 수 없었다.

    ⚠ 한 파일에 **두 번 서지 않는다** — 되풀이가 늘면 그 줄이 읽히지 않는다.
    """
    out_dir = _stage_dir(tmp_path)
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )
    line = run_identity_line(report)
    assert report.manifest_hash[:16] in line, "머리말 줄이 매니페스트를 안 나른다"
    assert report.assumption_set_version in line, "머리말 줄이 대장 판을 안 나른다"
    for path in sorted(out_dir.iterdir()):
        if path.name == INDEX_FILENAME:
            continue
        body = path.read_text(encoding="utf-8")
        assert body.count(line) == 1, (
            f"{path.name} 에 실행 식별자 줄이 하나가 아니다({body.count(line)}개)"
        )


def test_the_index_and_the_report_head_print_one_identity(tmp_path: Path) -> None:
    """★★ **목차와 문서 머리말이 같은 자리에서 온다** — 두 벌로 짓지 않는다.

    목차는 `app/run/report_cli.py::_index_markdown` 이 짓고 문서 머리말은
    `core/report/verification_gates.py::run_identity_rows` 가 짓는다. 두 곳이
    갈라지면 **같은 것이 두 해시를 인쇄한다** — 이 검사가 그 드리프트를 잡는다.

    ⚠ 한 덩어리 산출물에서도 그 세 행이 **한 번씩만** 선다.
    """
    index = (_stage_dir(tmp_path) / INDEX_FILENAME).read_text(encoding="utf-8")
    single = _verification_text(tmp_path)
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )
    for row in run_identity_rows(report):
        assert row in index, f"목차가 이 행을 잃었거나 다르게 적었다: {row}"
        assert single.count(row) == 1, f"문서 머리말의 행이 하나가 아니다: {row}"


def test_every_stage_ends_with_a_judgement_gate(tmp_path: Path) -> None:
    """★★★ **단계 끝에 판정 네 줄이 선다** (검토서 §4.7 의 표 그대로).

    ⚠ 게이트는 ⓓ **뒤**에 온다 — 판정은 그 단계가 낸 것을 다 읽은 뒤의 물음이다.
    """
    text = _verification_text(tmp_path)
    assert text.count(GATE_TITLE) == STAGE_COUNT, (
        "게이트가 아홉 단계에 하나씩 서지 않았다"
    )
    for stage in split_stages(text):
        body = stage.body
        assert body.index("**ⓓ 계산 수식**") < body.index(GATE_TITLE), (
            f"{stage.number}단계의 게이트가 ⓓ 앞에 있다"
        )
        for name in GATE_ROW_NAMES:
            assert body.count(f"| {name} | ") == 1, (
                f"{stage.number}단계 게이트에 「{name}」 행이 하나가 아니다"
            )


def test_the_gate_is_judged_from_the_run_and_not_stamped(tmp_path: Path) -> None:
    """★★★ **아홉에 「가능 / 없음 / 적용 / 불필요」를 찍어 두면 이 표는 무의미하다.**

    이 게이트의 값은 *「불가」가 나올 수 있다* 는 데 있다(WP-5 §1ⓒ). 그래서
    이 검사는 문면이 아니라 **판정의 다양성**을 잰다 — 넷 중 어느 축도 아홉이
    같은 답이면 그것은 규칙이 아니라 도장이다.

    ⚠ 그리고 그 판정이 **실행에서** 왔는지 한 자리를 짚어 대조한다: 이 저장소는
    역산 결과를 실행에 되먹이지 않으므로(`core/report/ess_sizing_section.py`
    머리말) 2단계는 「진단만」이고, 그 사실을 리포트에서 독립적으로 읽는다.
    """
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )
    gates = [stage_gate(report, number) for number in range(1, STAGE_COUNT + 1)]
    assert any(gate.blocking for gate in gates), "「불가」가 한 건도 나오지 않는다"
    assert any(gate.diagnostic_only for gate in gates), "「진단만」이 한 건도 없다"
    assert any(gate.human for gate in gates), "「사람 판단 필요」가 한 건도 없다"
    assert any(
        not gate.blocking and not gate.unmet and not gate.human for gate in gates
    ), "아홉이 전부 걸렸다 — 그것도 판정이 아니라 도장이다"

    assert report.ess_sizing.unmeasurable_reason is None, (
        "픽스처 전제가 깨졌다 — 역산이 서지 않으면 2단계에 진단값이 없다"
    )
    assert stage_gate(report, 2).diagnostic_only, "2단계가 「진단만」이 아니다"
    text = _verification_text(tmp_path)
    assert f"| {GATE_ROW_NAMES[0]} | 불가 |" in text, (
        "「불가」가 배포 경로(CLI 산출물)에는 나가지 않는다"
    )
    assert f"| {GATE_ROW_NAMES[1]} | {GATE_NONE} |" in text, (
        "미충족이 없는 단계가 빈칸이 아니라 「없음」으로 서야 한다"
    )


def test_stage_nine_stops_reprinting_stage_eights_formulas(tmp_path: Path) -> None:
    """★★★ **8·9단계의 되풀이를 끊었다** (검토서 §3.7).

    실물이 그랬다 — 두 단계가 「결론 전환 지원율」과 「전액 지원 시 잔여 결손」을
    **자연어·표현식·대입 문면 세 줄까지 똑같이** 실었다. 산식은 8단계에 남기고
    9단계는 그것을 **가리킨다.**
    """
    stages = split_stages(_verification_text(tmp_path))
    eight, nine = stages[7].body, stages[8].body
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )
    repeated = [
        formula
        for formula in report.formulas
        if formula.label in {"결론 전환 지원율", "전액 지원 시 잔여 결손"}
    ]
    assert repeated, "픽스처 전제가 깨졌다 — 되풀이를 잴 산식이 이 실행에 없다"
    for formula in repeated:
        assert f"`{formula.expression}`" in eight, (
            f"8단계가 「{formula.label}」 산식을 잃었다 — 남기기로 한 자리다"
        )
        assert formula.substituted not in nine, (
            f"9단계가 「{formula.label}」 의 대입 문면을 다시 인쇄한다"
        )
    assert STAGE8_FORMULA_POINTER in nine, "9단계가 8단계를 가리키지 않는다"


def test_stage_nine_compares_the_variants_row_by_row(tmp_path: Path) -> None:
    """★★★ **9단계는 비교표만 갖는다** — 행마다 구성·초기투자·NPV·필요한 지원율.

    ⚠ 재료가 없는 열은 **「미산출」로 글자로** 선다(지어내지 않는다). ⚠ 두 변형의
    수가 같으면 「같다」와 그 사유가 함께 선다 — 같은 수를 두 줄로 인쇄하고 아무
    말도 안 하면 독자가 오류로 읽는다.
    """
    nine = split_stages(_verification_text(tmp_path))[8].body
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )
    for tag, label in report.variant_labels:
        if tag not in report.variants:
            continue
        outlay = report.variants[tag]["initial_outlay_won"]
        npv = report.variants[tag][CONCLUSION_METRIC]
        row = next(
            line for line in nine.splitlines() if line.startswith(f"| {label} |")
        )
        assert f"{outlay:,.0f}원" in row, f"{label} 행에 초기투자가 없다"
        assert f"{npv:,.0f}원" in row, f"{label} 행에 순현재가치가 없다"
        assert f"{report.break_even_subsidy_rate:.1%}" in row, (
            f"{label} 행에 필요한 지원율이 없다"
        )
    for name in unbuilt_variant_columns(report):
        assert f"**{name} — 미산출.**" in nine, f"미산출 열 「{name}」의 사유가 없다"
    assert report.subsidy_rate == 0.0, "픽스처 전제가 깨졌다 — 무지원 시나리오다"
    assert "수가 전부 같다" in nine, (
        "지원율 0% 실행이라 두 행의 수가 같은데 그 사실을 적지 않았다"
    )
    assert f"| 현재 지원율 | {report.subsidy_rate:.1%} |" in nine, (
        "현재 지원율과 결론 전환 지원율이 한 표에서 갈리지 않았다"
    )


def test_the_stage_frame_adds_no_premise_word_and_no_new_stage() -> None:
    """⛔ 이 틀이 새로 짓는 문면에 **「전제」가 없고** ⛔ 단계를 늘리지 않는다.

    이 WP 는 아홉 단계 **전부의 머리와 꼬리**를 만진다 — 사람이 읽는 자리로
    새는 자리가 가장 넓다(판정 R63b §1). ⚠ 머리말 표의 행 이름(`전제 대장`)은
    **종전 문면을 그대로 나른 것**이라 이 검사의 대상이 아니다.
    """
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )
    authored = [
        QUESTION_HEAD,
        GATE_TITLE,
        *GATE_ROW_NAMES,
        *STAGE_QUESTIONS,
        run_identity_line(report),
        *(
            line
            for number in range(1, STAGE_COUNT + 1)
            for line in gate_lines(stage_gate(report, number))
        ),
    ]
    for line in authored:
        assert "전제" not in line, f"사람이 읽는 자리에 「전제」를 새로 세웠다: {line}"
        assert not line.startswith("## "), f"이 틀이 단계를 늘렸다: {line}"


def test_a_stage_number_outside_the_nine_stops() -> None:
    """⚠ 물음도 판정 규칙도 **없는 번호로는 단계를 짓지 못한다.**

    빈 물음·빈 게이트를 내면 「판정할 것이 없다」와 「규칙을 안 썼다」가
    구별되지 않고, 그때 이 표가 무의미해진다.
    """
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )
    with pytest.raises(ValueError, match="물음이 없는 단계 번호"):
        stage_question(STAGE_COUNT + 1)
    with pytest.raises(ValueError, match="판정 규칙이 없는 단계 번호"):
        stage_gate(report, 0)


def test_every_ledger_row_is_one_line_in_both_tables() -> None:
    """★★★ **대장의 산문이 표를 깨지 않는다** — 1단계 ⓑ 와 붙임 1 둘 다 (R68/WP-8).

    ## 무엇이 실제로 깨져 있었나

    `docs/assumptions.yaml::load.heatpump.annual` 의 `source` 에 **줄바꿈이 들어
    있어**, 그 행이 마크다운 표에서 **여러 줄로 쪼개져 표 밖으로 튕겨 나갔다**
    (R68/WP-7 실측). 값은 옳고 인쇄가 틀린 자리다 — 그래서 판정
    (`.orch/R68/JUDGMENT-wp7.md`)은 *「대장을 고치지 말고 표시 층에서 접어라」*
    였고, **접는 자리를 여러 벌 만들지 말라**는 조건이 붙었다.

    ## 왜 두 표를 한 검사가 보는가

    같은 함정을 **두 산출물이 함께** 갖고 있었다 — 검증 1단계 ⓑ 와 심의 붙임 1.
    한쪽만 재면 다른 쪽이 조용히 깨진 채 남고, 그것이 이 저장소가 반복해 만난
    「같은 사실을 두 자리가 각자 인쇄한다」의 한 얼굴이다. 접는 자리는
    `core/report/_format.py::_cell` **하나**다.

    ⚠ **자르는 것이 아니다** — 값이 줄어들면 그것은 다른 결함이다. 그래서 접힌
    행이 원문의 **첫 조각과 마지막 조각을 둘 다** 갖는지 함께 잰다.
    """
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )
    multiline = [row for row in report.assumptions if "\n" in (row.source or "")]
    assert multiline, (
        "대장에 줄바꿈을 가진 `source` 가 0건이다 — 이 검사가 0회 순회로 통과한다"
    )
    stage1 = next(block for block in stage_blocks(report) if block.number == 1)
    for surface, lines in (
        ("검증 1단계 ⓑ", stage1.lines),
        ("심의 붙임 1", tuple(appendix_section(report))),
    ):
        for row in multiline:
            hits = [line for line in lines if line.startswith(f"| `{row.key}` |")]
            assert len(hits) == 1, (
                f"{surface} 에서 `{row.key}` 행이 {len(hits)}줄이다 — 대장의 "
                "줄바꿈이 표를 깼다"
            )
            head, tail = row.source.split("\n")[0], row.source.split("\n")[-1]
            assert head.strip() in hits[0] and tail.strip() in hits[0], (
                f"{surface} 의 `{row.key}` 행이 출처를 **잘랐다** — 접는 것이지 "
                "줄이는 것이 아니다"
            )


def test_the_money_and_time_columns_name_their_unit() -> None:
    """★★ **금액·연차 열이 단위를 제목에 싣는다** (검토서 §4.2 · R68/WP-8).

    ⚠ **이 규칙은 열마다 단위가 다른 표에만 건다.** 한 표의 열이 전부 같은
    단위면 제목이 지는 것이 이 저장소의 판정이고, 그 자리는
    `core/report/dispatch_sections.py` 의 `LOAD_HEAD` 위 주석이다 — 3단계 스텝
    표가 그 갈래다(표 제목이 `단위 kWh/스텝` 을 진다).

    ⛔ **값을 재지 않는다** — 제목만 보는 검사이며, 값이 움직이면 그것은 이
    변경의 결함이다(사다리 L0 이 그 자리를 진다).
    """
    report = build_case_report(
        _GOLDEN / f"{DEFAULT_SCENARIO}.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_verification_markdown(report)
    heads = [
        line
        for line in text.splitlines()
        if line.startswith("|") and not line.startswith("|---")
    ]
    for wanted in (
        "| 자원 | 취득비 (원) | 고정 O&M (원/년) |",
        "| 편익 | 1년차 금액 (원) | 만든 자원 |",
        "| 비용 | 1년차 금액 (원) | 자원 |",
        "| 자원 | 수명 (년) |",
        "| 자원 | 종류 | 계상 연차 (년차) | 금액 (원) |",
        "| 행 | 발생 연차 (년차) | 그 연차 금액 (원) |",
    ):
        assert wanted in heads, f"열 제목이 단위를 잃었다 — 「{wanted}」가 없다"
    variants = next(
        line for line in heads if line.startswith("| 변형 | ")
    )
    for unit in ("물리 충족률 (%)", "연간 수전량 (kWh/년)", "초기투자 (원)",
                 "할인 회수기간 (년)", "순현재가치 (원)"):
        assert unit in variants, (
            f"9단계 비교표의 「{unit}」 열 제목이 단위를 잃었다 — 이 표는 열마다 "
            "단위가 다르므로 표 제목이 질 수 없다"
        )
