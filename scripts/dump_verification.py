"""검증 보고서를 **파일로 떨구는** 명령 — 시나리오 «경로» 하나를 받는다 (R64/WP-TXT).

## 무엇을 여는가

사용자 요구(2026-09-06): *「조직과 분석 결과를 확인할 수 있는 방법이 필요하며
주요 사항을 텍스트로 저장해서 이를 확인할 수 있게 하는 방법이 필요할 것
같음」*. 그 텍스트는 **이미 있다** —
`core/report/verification.py::render_verification_markdown` 이 내는 9단계
마크다운이며, 이 파일은 그것을 파일에 쓰기만 한다.

## ⚠ `app/run/report_cli.py` 와 무엇이 다른가 — **골든 밖 시나리오**

`python -m app.run.report_cli --kind verification --out …` 가 같은 문자열을
낸다. 그 명령의 `--scenario` 는 **이름**이고 `fixtures/golden/scenario_*.yaml`
안에서만 고를 수 있다(`available_scenarios()` 가 그 목록을 짓고, 밖의 이름은
`rc=2` 로 거부한다). 이 파일이 받는 것은 **경로**이며, 그래서 손으로 지은
시나리오·화면이 저장한 시나리오도 그대로 뽑을 수 있다.

⛔ **서식을 여기 두지 않는다.** 한 줄이라도 여기서 지으면 화면(`/ui/verify`)이
싣는 문면과 이 파일이 쓰는 문면이 갈리고, 그것이
`app/services/verify_steps.py` 머리말이 경고한 「통로가 둘」이다. 이 파일이
하는 일은 ① 인자를 읽고 ② 두 함수를 부르고 ③ 파일에 쓰는 것뿐이다.

⛔ **`app/run/report_cli.py` 를 고쳐 경로를 받게 하지 않았다** — `app/` 은 이
WP 가 만질 수 없는 자리다(웹·앱은 다음 WP). 그 파일이 경로를 받게 되는 날
이 스크립트는 지워도 된다.

## 쓰는 법

    export PYTHONUTF8=1
    ./.venv/Scripts/python.exe scripts/dump_verification.py \\
      --scenario fixtures/golden/scenario_unsubsidized.yaml \\
      --out .orch/R64/verify_unsubsidized.md

종료 코드: `0` 썼다 · `2` 시나리오·대장 파일이 없다 · `1` 시나리오가 거부됐다.

⚠ **덮어쓰기를 묻지 않는다.** 산출물은 대장과 코드로부터 언제든 다시
만들어지며, 손으로 고친 산출물은 검증의 근거가 되지 못한다
(`app/run/report_cli.py` 머리말이 같은 판단을 적었다).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.contracts.validation import ValidationError
from core.report.case_report import build_case_report
from core.report.verification import render_verification_markdown

REPO_ROOT = Path(__file__).resolve().parents[1]
#: 전제 대장의 기본 경로. `app/run/report_cli.py` 와 **같은 파일**을 가리킨다 —
#: 갈리면 두 명령이 다른 대장으로 다른 수를 인쇄한다.
DEFAULT_ASSUMPTIONS = REPO_ROOT / "docs" / "assumptions.yaml"


def build_parser() -> argparse.ArgumentParser:
    """인자 셋 — `--scenario`(필수) · `--assumptions` · `--out`(필수).

    ⚠ `--help` 가 **무엇을 내는지** 말하게 한다. 「검증 보고서」라는 이름만
    적으면 읽는 사람이 그것이 9단계 텍스트인지 표인지 알 수 없다.
    """
    parser = argparse.ArgumentParser(
        prog="python scripts/dump_verification.py",
        description=(
            "시나리오 하나로 검증 보고서(9단계 마크다운)를 파일에 쓴다. "
            "각 단계가 ⓐ 전제한 수치 → ⓑ 계산된 수치 → ⓒ 다음 단계로 넘긴 값 "
            "→ ⓓ 계산 수식을 싣는다"
        ),
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        required=True,
        help="시나리오 yaml 의 경로 (골든 밖의 파일도 받는다)",
    )
    parser.add_argument(
        "--assumptions",
        type=Path,
        default=DEFAULT_ASSUMPTIONS,
        help=f"전제 대장 경로 (기본 {DEFAULT_ASSUMPTIONS.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="쓸 파일 경로. 있으면 덮어쓴다 (묻지 않는다)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """보고서를 만들어 파일에 쓴다 — **없는 파일은 여기서 가른다.**

    ⚠ 파일이 없을 때 `build_case_report` 가 던지는 것은 `FileNotFoundError`
    이며 그 문면에는 *「무엇을 하면 되는가」*가 없다. 명령줄 도구가 역추적을
    통째로 뱉으면 사람은 자기가 오타를 냈는지 프로그램이 깨졌는지 가릴 수
    없으므로, 여기서 두 갈래를 갈라 **한 줄로** 말한다.
    """
    args = build_parser().parse_args(argv)
    for label, path in (("시나리오", args.scenario), ("전제 대장", args.assumptions)):
        if not path.is_file():
            print(f"{label} 파일이 없습니다: {path}", file=sys.stderr)
            return 2

    try:
        report = build_case_report(args.scenario, assumptions_path=args.assumptions)
    except ValidationError as rejected:
        # ⚠ 거부는 결함이 아니다 — 시나리오가 규약을 어긴 것이며, 그 세 요소
        # (자리·사유·조치)를 그대로 내야 사람이 무엇을 고칠지 안다(`NFR-303`).
        print(f"시나리오가 거부됐습니다: {rejected}", file=sys.stderr)
        return 1

    text = render_verification_markdown(report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(
        f"{args.out} 에 썼습니다 — 검증 보고서 · {len(text.splitlines())}줄 · "
        f"전제 대장 판 {report.assumption_set_version} · "
        f"매니페스트 {report.manifest_hash[:12]}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - 진입점
    raise SystemExit(main())
