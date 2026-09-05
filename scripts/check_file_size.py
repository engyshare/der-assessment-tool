"""NFR-206 파일 규모 검사 — 단일 소스 파일 500줄 상한.

**왜 저장소 전체를 훑는가.** 이 검사를 쓴 것은 WP-1e 하나뿐이었고
(`tests/der/test_load.py`·`test_thermal_load.py`), 그것도 **자기 파일 두 개만**
보았다. 나머지 네 자원은 감시 밖이었고, 계약 개정으로 상한을 넘긴 것이 정확히
그 넷이다. 자원마다 손으로 쓰는 검사는 반드시 빠진다 — 계약 테스트를 상속으로
따라오게 만든 것과 같은 이유다 (§16.2).

**총 줄 수와 코드 줄 수를 함께 보고하는 이유.**

    NFR-206-M1 은 `lint 경고` 이고, 조항의 **근거는 DER-VET `Params.py` 1,830줄
    유지보수 실패** 다. 그것이 겨냥하는 것은 **코드 스프롤**이다. 그런데 이
    저장소는 판단 근거를 코드 옆에 남기는 것을 규율로 삼고 있어(§13.2.1 오라클
    명시·「왜 이렇게 했는가」 주석), 총 줄 수의 상당 부분이 설명이다.

    총 줄 수만 보고하면 두 가지가 한 숫자에 섞인다 — 「함수가 40개인 파일」과
    「함수 15개에 근거를 충실히 적은 파일」이 같은 경고를 받는다. 그러면 경고를
    지우는 가장 쉬운 길이 **설명을 지우는 것**이 되고, 조항이 지키려던 유지
    보수성이 오히려 나빠진다.

    그래서 **판정은 조항 문면대로 총 줄 수로 하되**, 코드 줄 수를 함께 적어
    초과의 성질을 구분한다. 상한값과 판정 기준을 바꾸는 것은 spec 개정이며
    §16.5 절차가 필요하다 — 검사를 통과시키려고 규칙을 고치는 것은 이 저장소가
    반복해서 경계해 온 유형이다.

        코드 스프롤   총 초과 **그리고** 코드 초과 → 조항 취지 그대로의 위반
        설명 밀도     총 초과 **그러나** 코드 이내 → 문면 위반이나 성질이 다르다

**경고이고 차단이 아니다.** 파일 분할을 마친 뒤 회귀를 막으려면 `--strict` 를
켠다. `--code-strict` 는 **코드 스프롤만** 차단한다 — 설명 밀도 초과는 통과시키고
싶을 때 쓴다.

    종료 코드 0  상한 이내, 또는 초과분을 경고로만 보고
    종료 코드 1  `--strict`(총) 또는 `--code-strict`(코드) 위반
    종료 코드 2  검사 자체가 성립하지 않음 (대상 파일 0개)
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

LIMIT = 500

#: 검사 대상. 테스트는 제외한다 — 검증 케이스는 자원 하나에 수십 건이 붙으므로
#: 같은 상한을 걸면 케이스를 쪼개는 압력이 되고, 그것은 NFR-106(자원별 케이스
#: 의무)과 정면으로 부딪친다. NFR-206 이 말하는 것은 **소스 파일**이다.
TARGETS = ("core", "app", "infra", "scripts", "web")

EXCLUDE_PARTS = {"__pycache__", ".venv", "migrations"}


@dataclass(frozen=True)
class Measured:
    path: Path
    total: int
    code: int
    doc: int
    comment: int
    blank: int

    @property
    def over_total(self) -> bool:
        return self.total > LIMIT

    @property
    def over_code(self) -> bool:
        return self.code > LIMIT

    @property
    def kind(self) -> str:
        """초과의 성질. 판정이 아니라 **분류**다."""
        if self.over_code:
            return "코드 스프롤"
        return "설명 밀도"


def measure_file(path: Path, *, label: Path | None = None) -> Measured:
    """총·코드·독스트링·주석·공백 줄 수로 가른다.

    `label` 은 보고에 쓸 경로다(보통 저장소 상대 경로). 읽기와 표시를 가르는
    이유는 절대 경로가 출력에 섞이면 SC-3(로컬 경로 노출)에 걸리기 때문이다.

    독스트링을 `ast` 로 세는 이유: 정규식으로는 `\"\"\"` 가 문자열 리터럴 안에
    있는 경우와 구분되지 않고, 그 오판이 **어느 쪽으로 얼마나 틀렸는지 드러나지
    않는다.** 파서가 판정하면 최소한 문법이 보증한다.
    """
    shown = label if label is not None else path
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()

    doc_lines: set[int] = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        # 문법 오류 파일은 코드 줄 수를 셀 수 없다. 총 줄 수만 신뢰한다 —
        # 추정치를 코드 줄 수로 내보내면 판단 근거가 조용히 거짓이 된다.
        return Measured(shown, len(lines), len(lines), 0, 0, 0)

    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        if ast.get_docstring(node, clean=False) is None or not node.body:
            continue
        first = node.body[0]
        doc_lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))

    comment = blank = 0
    for lineno, text in enumerate(lines, start=1):
        if lineno in doc_lines:
            continue
        stripped = text.strip()
        if not stripped:
            blank += 1
        elif stripped.startswith("#"):
            comment += 1

    total = len(lines)
    doc = len(doc_lines)
    return Measured(shown, total, total - doc - comment - blank, doc, comment, blank)


def measure(root: Path) -> list[Measured]:
    found: list[Measured] = []
    for target in TARGETS:
        base = root / target
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if EXCLUDE_PARTS & set(path.parts):
                continue
            found.append(measure_file(path, label=path.relative_to(root)))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NFR-206 파일 규모 검사 (500줄)")
    parser.add_argument("--root", default=".", help="저장소 루트")
    parser.add_argument("--strict", action="store_true",
                        help="총 줄 수 초과 시 종료 코드 1 (기본은 경고만)")
    parser.add_argument("--code-strict", action="store_true",
                        help="**코드** 줄 수 초과 시에만 종료 코드 1")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    measured = measure(root)
    if not measured:
        print(f"검사 대상 파일이 없습니다: {root} / {', '.join(TARGETS)}", file=sys.stderr)
        print("검사를 수행하지 못한 것을 통과로 읽지 않습니다 (§13.0.1 ④)", file=sys.stderr)
        return 2

    over = sorted((m for m in measured if m.over_total), key=lambda m: -m.total)
    sprawl = [m for m in over if m.over_code]

    print(f"NFR-206 파일 규모 — 상한 {LIMIT}줄 / 대상 {len(measured)}개 파일")
    print("─" * 78)
    if over:
        print(f"{'':6s}{'총':>5s} {'코드':>6s} {'독스':>5s} {'주석':>5s}  파일")
    for m in over:
        print(f"경고  {m.total:5d} {m.code:6d} {m.doc:5d} {m.comment:5d}  "
              f"{m.path}  [{m.kind}]")
    if not over:
        widest = max(measured, key=lambda m: m.total)
        print(f"전건 상한 이내 — 최대 {widest.total}줄 ({widest.path})")
    print("─" * 78)

    if over:
        print(f"총 줄 수 초과 {len(over)}건 — 그중 코드 줄 수도 초과한 것 "
              f"**{len(sprawl)}건**")
        print()
        if sprawl:
            print("  「코드 스프롤」은 조항 취지 그대로의 위반이다. 파일을 쪼개십시오.")
            for m in sprawl:
                print(f"    · {m.path} — 코드 {m.code}줄")
        else:
            print("  전건 「설명 밀도」다 — **코드 줄 수는 모두 상한 이내**이며, 조항의")
            print("  근거(DER-VET `Params.py` 1,830줄 코드 스프롤)에 해당하는 파일은 없다.")
        print()
        print("  **줄 수를 맞추려고 근거 주석을 지우지 마십시오.** 그것은 조항이")
        print("  지키려던 유지보수성을 오히려 나쁘게 만듭니다. 총 줄 수 상한을")
        print("  코드 기준으로 바꾸려면 spec 개정이며 §16.5 절차가 필요합니다.")
        if args.code_strict:
            return 1 if sprawl else 0
        return 1 if args.strict else 0

    print("통과")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
