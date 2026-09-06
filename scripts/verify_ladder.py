"""**하향식 사다리** — 결론축부터 내려가며 «어디서 갈렸는지»를 말한다 (R64/WP-TEST).

## 사용자가 정한 구조 (2026-09-06 20:0x)

> *「테스트 순서를 효과적으로 설정하면 될 것 같은데. 먼저 최종 수치 변경 여부
> 확인, 수치가 동일하면 테스트 종료, 상이하면 순차적으로 차상위 주요 수치 확인
> 식으로 하향식, 단계별로 테스트」*

## 사다리는 **이미 저장소에 있었다** — 새로 짓지 않았다

`core/report/verification.py::render_verification_markdown` 이 내는 **9단계**가
그 사다리다(1 전제 → 2 자원 → 3 운전 → 4 편익 → 5 운영비 → 6 생애주기 →
7 현금흐름 → 8 지표 → 9 변형). 이 파일은 **그 문자열을 층으로 잘라 견주는 일만**
한다 — 새 계산도, 둘째 정본도 만들지 않는다.

    L0  결론축            report.metrics 의 npv · payback_years
    L1  8·9단계          지표 · 지원율 변형
    L2  7단계            현금흐름
    L3  4·5·6단계        편익 · 운영비 · 생애주기
    L4  3단계            운전(디스패치)
    L5  2단계            자원·초기투자
    L6  1단계            전제 대장

## ⚠⚠ 이것이 **못 잡는 것** — 「L0 동일」은 「아무것도 안 바뀌었다」가 아니다

- **상쇄.** 편익 +100 · 운영비 +100 이면 순현재가치는 1원도 안 움직인다.
  L0 만 보고 끊으면 그 둘을 못 본다. ⇒ 축을 움직이는 변경 뒤에는 `--deep`.
- **화면.** `tests_e2e/` 도 `tests/app/` 도 이 사다리에 없다.
- **계약·규약.** `tests/contract` · `tests/ci` 가 보는 것(구획 경계·조항 인용·
  파일 규모)은 산출물 수치에 나타나지 않는다.
- **골든 셋 밖.** 견주는 것은 `fixtures/golden/scenario_*.yaml` 뿐이다.

⛔ **「L0 동일하니 통과」로 커밋을 판정하지 마라.** 이 사다리가 대신하는 것은
*「축이 움직였나」* 이지 *「아무것도 안 깨졌나」* 가 아니다.

## 기준선을 «스냅숏 파일»로 잡은 근거

`origin/main` 의 산출물과 견주는 것이 이상적이지만, 그러려면 그 커밋을 워크트리로
꺼내 **거기서도 `build_case_report` 를 돌려야** 한다 — 비용이 정확히 두 배이고,
라운드 중에는 작업 트리가 더러워 꺼내는 것 자체가 위험하다. 그래서 **직전
스냅숏 파일**과 견준다(`.orch/verify_ladder/baseline.json`, `.gitignore` 안).
`git` 기준선이 필요하면 워크트리를 사람이 만들고 `--baseline` 으로 그 산출물을
가리키면 된다 — 통로를 둘 만들지 않는다.

## 쓰는 법

    export PYTHONUTF8=1
    ./.venv/Scripts/python.exe scripts/verify_ladder.py snapshot        # 기준선을 잡는다
    ./.venv/Scripts/python.exe scripts/verify_ladder.py check           # 빠른 갈래(L0 에서 끊음)
    ./.venv/Scripts/python.exe scripts/verify_ladder.py check --deep    # 깊은 갈래(L6 까지)

대장을 고쳐 보고 싶으면 **실물을 건드리지 말고 사본을 준다** — 기준선(실물 대장)과
층별로 견준다:

    ./.venv/Scripts/python.exe scripts/verify_ladder.py check --assumptions <고친 사본>

종료 코드: `0` 갈린 층 없음 · `1` 갈렸다 · `2` 기준선이 없다·못 읽는다.

## 검증 보고서를 **파일로 떨구는 일은 여기 없다**

이 파일이 하는 것은 *「층으로 잘라 견주기」* 하나다. 검증 보고서를 그대로 파일에
쓰는 CLI 는 별개의 관심사이며, 그런 것이 생기더라도 **이 파일은 그 산출물을
읽지 않고** `render_verification_markdown()` 을 계속 직접 부른다 — 파일을 거치면
한 번이면 될 실행이 두 번이 되고, 그 두 번이 갈리면 어느 쪽이 정본인지 말할 수
없게 된다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from core.report.case_report import build_case_report
from core.report.verification import render_verification_markdown

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO_ROOT / "fixtures" / "golden"
ASSUMPTIONS_PATH = REPO_ROOT / "docs" / "assumptions.yaml"
DEFAULT_BASELINE = REPO_ROOT / ".orch" / "verify_ladder" / "baseline.json"

#: L0 이 견주는 것 — **결론축**. `initial_outlay_won` 은 지표가 아니라 대입값이라
#: 여기 넣지 않는다(그것은 8단계에 실려 L1 이 본다).
CONCLUSION_KEYS: tuple[str, ...] = ("npv", "payback_years")

#: 층 → (이름, 그 층이 견주는 `N단계` 번호들). **순서가 사다리다.**
LADDER: tuple[tuple[str, str, tuple[int, ...]], ...] = (
    ("L0", "결론축(순현재가치·회수기간)", ()),
    ("L1", "8·9단계 — 지표 · 지원율 변형", (8, 9)),
    ("L2", "7단계 — 현금흐름", (7,)),
    ("L3", "4·5·6단계 — 편익 · 운영비 · 생애주기", (4, 5, 6)),
    ("L4", "3단계 — 운전(디스패치)", (3,)),
    ("L5", "2단계 — 자원 · 초기투자", (2,)),
    ("L6", "1단계 — 전제 대장", (1,)),
)

#: 검증 보고서의 단계 머리글. `_stage()` 가 내는 모양 그대로다
#: (`core/report/verification.py::_stage` → `f"## {number}단계 — {title}"`).
_STAGE_HEADING = re.compile(r"^## (\d)단계 — ", re.MULTILINE)


def _split_stages(markdown: str) -> dict[str, str]:
    """검증 보고서를 `{"1": …, …, "9": …}` 로 자른다.

    ⚠ **머리말(표제·매니페스트 해시)은 버린다.** 해시는 입력이 한 원이라도
    움직이면 함께 움직이므로 「무엇이 갈렸나」를 말하지 못하고, 층에 실으면
    모든 층이 늘 상이해진다.
    """
    marks = list(_STAGE_HEADING.finditer(markdown))
    if len(marks) != 9:
        raise RuntimeError(
            f"검증 보고서에서 9단계를 찾지 못했다 — {len(marks)}개를 찾았다. "
            "`core/report/verification.py` 의 단계 머리글 모양이 바뀌었는지 보라"
        )
    stages: dict[str, str] = {}
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(markdown)
        stages[mark.group(1)] = markdown[mark.start() : end].strip()
    return stages


def _scenario_paths() -> list[Path]:
    paths = sorted(GOLDEN_DIR.glob("scenario_*.yaml"))
    if not paths:
        raise RuntimeError(f"골든 시나리오가 없다 — {GOLDEN_DIR}")
    return paths


def collect(assumptions_path: Path = ASSUMPTIONS_PATH) -> dict[str, Any]:
    """골든 셋을 **각각 한 번씩만** 돌려 층 재료를 모은다.

    ⚠ **`build_case_report()` 를 시나리오당 한 번 부른다.** 그 한 번이 9단계
    문자열과 결론축을 함께 낸다 — 층마다 다시 돌리면 사다리가 전건보다 비싸진다.

    ⚠ `assumptions_path` 를 받는 이유는 **「대장을 이렇게 고치면 축이 움직이나」**
    를 묻기 위해서다 — 고친 대장 사본을 주면 기준선(실물 대장)과 층별로 견준다.
    실물 대장을 건드리지 않고 물을 수 있는 통로가 이것뿐이다.
    """
    collected: dict[str, Any] = {}
    for path in _scenario_paths():
        report = build_case_report(path, assumptions_path=assumptions_path)
        collected[path.name] = {
            "conclusion": {
                key: report.metrics[key] for key in CONCLUSION_KEYS
            },
            "stages": _split_stages(render_verification_markdown(report)),
        }
    return collected


def _conclusion_diff(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> list[str]:
    notes: list[str] = []
    for name in sorted(set(before) | set(after)):
        if name not in before:
            notes.append(f"{name}: 기준선에 없던 시나리오다")
            continue
        if name not in after:
            notes.append(f"{name}: 시나리오가 사라졌다")
            continue
        old = before[name]["conclusion"]
        new = after[name]["conclusion"]
        for key in CONCLUSION_KEYS:
            if old.get(key) != new.get(key):
                notes.append(f"{name}: {key} {old.get(key)} → {new.get(key)}")
    return notes


def _stage_diff(
    before: Mapping[str, Any], after: Mapping[str, Any], stages: Iterable[int]
) -> list[str]:
    notes: list[str] = []
    for name in sorted(set(before) & set(after)):
        for stage in stages:
            key = str(stage)
            old = before[name]["stages"].get(key)
            new = after[name]["stages"].get(key)
            if old != new:
                notes.append(f"{name}: {stage}단계")
    return notes


def _levels(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> list[tuple[str, str, list[str]]]:
    """L0~L6 을 **전부** 판정한다 — 끊는 것은 부르는 쪽의 일이다."""
    verdicts: list[tuple[str, str, list[str]]] = []
    for level, title, stages in LADDER:
        notes = (
            _conclusion_diff(before, after)
            if not stages
            else _stage_diff(before, after, stages)
        )
        verdicts.append((level, title, notes))
    return verdicts


def _report(verdicts: Sequence[tuple[str, str, list[str]]], *, deep: bool) -> int:
    """사다리를 인쇄하고 종료 코드를 낸다.

    ⚠ **「최초로 갈린 층」이 아니라 「가장 깊이 갈린 층」이 원인 자리다.**
    파이프라인은 1단계 → 9단계로 흐르므로 위층(L0)은 아래층이 움직이면 함께
    움직인다. 갈림이 시작된 자리는 **상이한 층 중 가장 아래**다.
    ⚠ 위층이 같아도 아래층이 다를 수 있다(상쇄) — 그래서 `--deep` 은 끊지 않고
    전부 인쇄한다.
    """
    if not verdicts[0][2] and not deep:
        print("L0 동일 — 결론축이 움직이지 않았다.")
        print(
            "  (빠른 갈래라 여기서 끊는다. 상쇄·화면·계약은 안 잰다 — "
            "`--deep` 이 L1~L6 을 마저 본다)"
        )
        return 0

    trail: list[str] = []
    deepest: tuple[str, str] | None = None
    for level, title, notes in verdicts:
        mark = "상이" if notes else "동일"
        trail.append(f"{level} {mark}")
        print(f"{level} {mark} — {title}")
        for note in notes[:12]:
            print(f"    · {note}")
        if len(notes) > 12:
            print(f"    · … 그리고 {len(notes) - 12}건 더")
        if notes:
            deepest = (level, title)

    print()
    print(" → ".join(trail))
    if deepest is None:
        print("갈린 층이 없다.")
        return 0
    print(f"⇒ **가장 깊이 갈린 층은 {deepest[0]}** — {deepest[1]}. 여기가 뿌리다.")
    return 1


def _load_baseline(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"기준선이 없다 — {path}\n"
            "먼저 `python scripts/verify_ladder.py snapshot` 으로 잡아라."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _write_baseline(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_ladder",
        description="결론축부터 내려가며 어디서 갈렸는지 말한다 (R64/WP-TEST)",
    )
    parser.add_argument("mode", choices=("snapshot", "check"))
    parser.add_argument(
        "--baseline", type=Path, default=DEFAULT_BASELINE,
        help=f"기준선 파일 (기본 {DEFAULT_BASELINE.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--deep", action="store_true",
        help="L0 이 같아도 끊지 않고 L1~L6 을 전부 견준다 (상쇄를 잡는다)",
    )
    parser.add_argument(
        "--assumptions", type=Path, default=ASSUMPTIONS_PATH,
        help="이번 실행이 쓸 전제 대장 (기본 docs/assumptions.yaml). "
             "고친 사본을 주면 «이렇게 고치면 축이 움직이나» 를 묻는다",
    )
    args = parser.parse_args(argv)

    if args.mode == "snapshot":
        _write_baseline(args.baseline, collect(args.assumptions))
        print(f"기준선을 잡았다 — {args.baseline}")
        return 0

    try:
        before = _load_baseline(args.baseline)
    except (OSError, ValueError) as exc:
        print(f"기준선을 읽지 못했다: {exc}", file=sys.stderr)
        return 2
    return _report(_levels(before, collect(args.assumptions)), deep=args.deep)


if __name__ == "__main__":
    sys.exit(main())
