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

`--out` 을 주지 않으면 표준출력으로 낸다. **덮어쓰기를 묻지 않는다** — 리포트는
대장과 코드로부터 언제든 다시 만들어지는 산출물이고, 손으로 고친 리포트는
`MC-1` 의 증거가 되지 못한다(고친 것이 리포트인지 사람인지 갈리지 않는다).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.report.case_report import build_case_report
from core.report.narrative import render_markdown
from core.report.verification import render_verification_markdown

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
    return parser


def main(argv: list[str] | None = None) -> int:
    """리포트를 만들고 낸다. 시나리오가 없으면 **목록을 보여 주고 멈춘다.**"""
    args = build_parser().parse_args(argv)
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
