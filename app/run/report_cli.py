"""심의용 리포트를 **파일로** 뽑는 명령 — `MC-1` 이 실제로 쓰는 출구.

## 왜 라우터만으로는 부족한가

`MC-1` 은 심의 경험자 3명에게 **리포트만** 건네고 두 가지를 설명하게 하는
검사다. 그 진행에 필요한 것은 서버가 아니라 **파일 하나**다 — 그리고
`docs/manual-checks.yaml` 의 `evidence` 칸이 요구하는 것도 파일 경로다.
서버를 띄워야만 산출물이 나온다면 검사를 주관하는 사람이 개발 환경을 갖춰야
하고, 그 순간 「리포트만 준다」가 성립하지 않는다.

## 사용

    PYTHONUTF8=1 python -m app.run.report_cli --scenario scenario_unsubsidized
    PYTHONUTF8=1 python -m app.run.report_cli --out docs/evidence/MC-1-리포트.md
    PYTHONUTF8=1 python -m app.run.report_cli --kind verification --split-stages \
        --out docs/evidence/검증-단계별/

`--out` 을 주지 않으면 표준출력으로 낸다. `--split-stages` 를 주면 `--out` 을
**디렉터리**로 읽어 검증 리포트를 단계마다 파일 하나(`01-` … `10-`)와 목차
(`00-목차.md`)로 나눠 쓴다 — 검증 리포트 전용이다. **덮어쓰기를 묻지 않는다** — 리포트는
대장과 코드로부터 언제든 다시 만들어지는 산출물이고, 손으로 고친 리포트는
`MC-1` 의 증거가 되지 못한다(고친 것이 리포트인지 사람인지 갈리지 않는다).

## 산출물을 둘 자리는 **기계가 정한다** — `DER_REPORT_OUT_DIR`

`--out` 을 안 주고 이 환경변수를 주면 **그 디렉터리에 이름을 지어 쓴다**
(`<시나리오>-<종류>.md`, 분할이면 `<시나리오>-<종류>-단계별/`). 둘 다 없으면
표준출력이다 — `DER_SCENARIO_STORE` 가 *「자리를 정하지 않으면 인메모리」* 인 것과
같은 규약이며 **결함이 아니다**.

⚠ **경로 리터럴을 이 소스에 박지 않는다.** 어느 기계의 어느 폴더인지는 저장소가
아는 사실이 아니다 — CI·Docker·다른 클론에는 그 폴더가 없다. 이름만 여기 한 곳이
갖고 값은 환경이 준다(`app/services/scenario_store_file.py::SCENARIO_STORE_ENV` 와
같은 규약). 이 기계의 값은 `CLAUDE.md` 가 적는다.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from app.services.verify_steps import VerifyStage, split_stages
from core.report.case_report import CaseReport, build_case_report
from core.report.narrative import render_markdown
from core.report.verification import render_verification_markdown, stage_blocks
from core.report.verification_chain import dependency_chain_lines
from core.report.verification_variants import policy_variant_sentence

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_DIR = _REPO_ROOT / "fixtures" / "golden"
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
#: 기본 시나리오. `status-human.md` 1-A 가 *「무보조 1건으로 충분」* 이라 적는다.
DEFAULT_SCENARIO = "scenario_unsubsidized"
#: 리포트 종류 — 기본값은 **바이트 한 글자도 바뀌면 안 된다** (R52/WP-1).
#: `MC-1` 재산출이 이 기본 경로를 그대로 쓴다.
KIND_DELIBERATION = "deliberation"
#: 검증 보고서 — 사용자 판정 §2(`docs/decisions-2026-09-02-R52.md`). 대조군이
#: 없는 대신 단계별 전제·계산·인계·수식을 늘어놓는다.
KIND_VERIFICATION = "verification"
REPORT_KINDS = (KIND_DELIBERATION, KIND_VERIFICATION)

#: 단계별 분할 출력의 목차 파일 이름. 단계 파일이 ``01-`` 부터 시작하므로 ``00-``
#: 을 앞세워 **사전순으로 목차가 먼저 오게** 한다.
INDEX_FILENAME = "00-목차.md"

#: Windows 가 파일 이름에 허용하지 않는 문자. 렌더러의 단계 제목에는 없지만,
#: 제목이 바뀌는 날 파일 쓰기가 터지지 않게 방어로만 둔다.
_FILENAME_FORBIDDEN = re.compile(r'[<>:"/\\|?*]')

#: `--out` 을 안 줬을 때 산출물을 둘 디렉터리를 정하는 환경변수.
#: **이름만 여기 한 곳이 갖고 값은 환경이 준다** —
#: `app/services/scenario_store_file.py::SCENARIO_STORE_ENV` 와 같은 규약이다.
REPORT_OUT_DIR_ENV = "DER_REPORT_OUT_DIR"

#: 분할 출력 디렉터리 이름의 꼬리. 파일과 디렉터리가 같은 자리에 서므로
#: **꼬리로 갈라** 둘이 이름으로 부딪히지 않게 한다.
_SPLIT_DIRNAME_SUFFIX = "-단계별"


def _configured_out_dir() -> Path | None:
    """`DER_REPORT_OUT_DIR` 가 가리키는 디렉터리. 안 줬거나 비었으면 `None`.

    ⚠ **여기서 `mkdir` 하지 않는다** — 자리를 만드는 것은 실제로 쓰는 쪽이고,
    조회만으로 디렉터리가 생기면 「환경변수를 잘못 적었다」가 조용히 지나간다.
    """
    raw = os.environ.get(REPORT_OUT_DIR_ENV, "").strip()
    return Path(raw) if raw else None


def _derived_out_path(scenario: str, kind: str, *, split: bool) -> Path | None:
    """환경변수 자리에 **이름을 지어** 낼 경로. 자리가 없으면 `None`.

    이름이 시나리오와 종류를 함께 나르는 이유는, 한 자리에 여러 실행이 쌓이는데
    파일명이 그것을 가르지 않으면 **뒤에 돈 실행이 앞의 것을 조용히 덮는다.**
    """
    out_dir = _configured_out_dir()
    if out_dir is None:
        return None
    stem = f"{scenario}-{kind}"
    return out_dir / (f"{stem}{_SPLIT_DIRNAME_SUFFIX}" if split else f"{stem}.md")


def available_scenarios() -> list[str]:
    return sorted(path.stem for path in _GOLDEN_DIR.glob("scenario_*.yaml"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.run.report_cli",
        description="골든 시나리오 하나로 심의용 리포트 한 장을 만든다",
    )
    parser.add_argument(
        "--scenario",
        default=DEFAULT_SCENARIO,
        help=f"시나리오 이름 (기본 {DEFAULT_SCENARIO})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="쓸 파일 경로. 주지 않으면 표준출력",
    )
    parser.add_argument(
        "--assumptions",
        type=Path,
        default=_ASSUMPTIONS,
        help="전제 대장 경로",
    )
    parser.add_argument(
        "--kind",
        choices=REPORT_KINDS,
        default=KIND_DELIBERATION,
        help=(
            f"낼 리포트 종류 (기본 {KIND_DELIBERATION}). "
            f"{KIND_VERIFICATION} 은 대조군 없이 단계별 전제·계산·인계·수식을 "
            "늘어놓는 검증 보고서다(사용자 판정 §2)"
        ),
    )
    parser.add_argument(
        "--split-stages",
        action="store_true",
        help=(
            f"검증 보고서를 단계마다 파일 하나로 나눠 쓴다 — --kind "
            f"{KIND_VERIFICATION} 전용. --out 을 디렉터리로 읽어 단계 파일과 "
            f"목차({INDEX_FILENAME})를 그 안에 쓴다"
        ),
    )
    return parser


def _stage_filename(stage: VerifyStage) -> str:
    """단계 파일 이름 — 두 자리 번호가 앞에 서서 **사전순 = 단계순**이 되게 한다."""
    safe = _FILENAME_FORBIDDEN.sub("_", stage.title)
    return f"{stage.number:02d}-{safe}.md"


def _index_markdown(stages: tuple[VerifyStage, ...], report: CaseReport) -> str:
    """목차 — 출처 표와 단계 번호 · 제목 · 파일명(사용자 판정 R67 §4-1).

    원본 머리말의 「항목 | 값」 표를 싣는다 — 한 덩어리가 머리말로 하던 일
    (어느 시나리오의 어느 대장 판·어느 실행이 낸 수인가)을 가르는 순간 잃으니
    목차가 대신 보관한다. 라벨과 16자리 매니페스트 자릿수는 렌더러 머리말
    (`core/report/verification.py`)과 한 글자도 다르지 않다 — 갈라지면 같은
    것이 두 이름을 갖는다(stderr 보고의 12자리와 헷갈리지 않는다).
    """
    lines = [
        "# 검증 보고서 — 단계별 목차",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 평가 대상 | {report.scenario_name} |",
        f"| 전제 대장 | `{report.assumption_set_name}` 판 "
        f"{report.assumption_set_version} |",
        f"| 실행 매니페스트 | `{report.manifest_hash[:16]}` |",
        "",
        # ★ **이 실행이 무슨 «정책 변형»인가** (R68/WP-9 · 검토서 §3.7 마지막).
        # 머리표의 「평가 대상」은 평가 «대상»이지 지원 조건이 아니다 — 세
        # 시나리오가 이 목차를 함께 쓰므로 문면은 실행에서 온다.
        # ⚠ 문면을 여기서 짓지 않는다(아래 의존 연결표와 같은 사유) —
        # `core/report/verification_variants.py::policy_variant_sentence` 가
        # 정본이고, 그 함수가 10단계 비교표와 같은 낱말·같은 상한을 쓴다.
        policy_variant_sentence(report),
        "",
        "| 단계 | 제목 | 파일 |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| {stage.number} | {stage.title} | {_stage_filename(stage)} |"
        for stage in stages
    )
    # ★★ **의존 연결표** (R68/WP-4-fix · 검토서 §2.2 *「어떤 계산이 어떤 값에
    # 의존하는지 한눈에 보이는 연결표가 없다 … 최소한 목차에 표시해야 한다」*).
    # ⚠ **문면을 여기서 짓지 않는다** — 재료는 각 단계의 ⓒ 절이고 그것을
    # `core/report/verification.py::StageBlock` 이 실어 온다. 이 파일이 다시
    # 적으면 단계가 바뀌는 날 목차만 옛말을 한다.
    # ⚠ 표의 위 `stages`(마크다운에서 쪼갠 것)와 아래 블록(렌더러가 낸 자료)은
    # 같은 아홉이다 — 어긋나면 `split_stages` 가 이미 멈춘다(`STAGE_COUNT`).
    lines += ["", *dependency_chain_lines(stage_blocks(report))]
    return "\n".join(lines) + "\n"


def _write_stage_files(text: str, out_dir: Path, report: CaseReport) -> int:
    """검증 리포트를 단계마다 파일 하나 + 목차 하나로 내는 갈래 (R67/WP-1).

    `--split-stages` 를 줄 때만 불리며, 그때 `--out` 은 **디렉터리**다. 가르는
    일은 `split_stages` 에 이미 있으니 다시 짜지 않는다 — 단계 수가
    `STAGE_COUNT` 와 어긋나면 그 예외가 그대로 올라와 CLI 가 멈춘다(일부만
    내지 않는다). 단계 파일 본문은 머리글(``## N단계 — …``)부터 렌더러 원문
    그대로다.
    """
    stages = split_stages(text)
    out_dir.mkdir(parents=True, exist_ok=True)
    for stage in stages:
        (out_dir / _stage_filename(stage)).write_text(stage.body, encoding="utf-8")
    (out_dir / INDEX_FILENAME).write_text(
        _index_markdown(stages, report), encoding="utf-8"
    )
    print(
        f"{out_dir} 에 단계 파일 {len(stages)}개와 목차 {INDEX_FILENAME} 을 썼습니다 — "
        f"{KIND_VERIFICATION} 리포트 · 전제 대장 판 {report.assumption_set_version} · "
        f"매니페스트 {report.manifest_hash[:12]}",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """리포트를 만들고 낸다. 시나리오가 없으면 **목록을 보여 주고 멈춘다.**"""
    args = build_parser().parse_args(argv)
    if args.split_stages and args.kind != KIND_VERIFICATION:
        print(
            f"--split-stages 는 --kind {KIND_VERIFICATION} 전용입니다 — "
            f"--kind {args.kind} 와 함께 쓸 수 없습니다",
            file=sys.stderr,
        )
        return 2
    # ★ `--out` 을 안 줬으면 환경변수가 정한 자리에 **이름을 지어** 쓴다
    #   (`DER_REPORT_OUT_DIR` · 머리말 그 절). ⚠ `--out` 이 있으면 손대지 않는다 —
    #   명시한 자리를 환경이 덮으면 사용자가 적은 경로가 조용히 무시된다.
    if args.out is None:
        args.out = _derived_out_path(
            args.scenario, args.kind, split=args.split_stages
        )
    if args.split_stages and args.out is None:
        print(
            "--split-stages 는 단계마다 파일을 만드는 선택지입니다 — "
            f"--out 에 받을 디렉터리를 주거나 {REPORT_OUT_DIR_ENV} 를 설정하세요",
            file=sys.stderr,
        )
        return 2
    names = available_scenarios()
    if args.scenario not in names:
        print(
            f"시나리오 {args.scenario!r} 이(가) 없습니다. "
            f"사용할 수 있는 것: {', '.join(names)}",
            file=sys.stderr,
        )
        return 2

    report = build_case_report(
        _GOLDEN_DIR / f"{args.scenario}.yaml", assumptions_path=args.assumptions
    )
    text = (
        render_verification_markdown(report)
        if args.kind == KIND_VERIFICATION
        else render_markdown(report)
    )

    if args.split_stages:
        return _write_stage_files(text, args.out, report)

    if args.out is None:
        print(text)
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(
        f"{args.out} 에 썼습니다 — {args.kind} 리포트 · 전제 대장 판 "
        f"{report.assumption_set_version} · 매니페스트 {report.manifest_hash[:12]}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - 진입점
    raise SystemExit(main())
