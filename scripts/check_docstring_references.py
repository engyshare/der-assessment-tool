#!/usr/bin/env python3
"""독스트링·주석이 가리키는 **코드 이름이 실재하는가** — 없는 이름·옮겨진 자리.

## 왜 이 검사가 필요한가

이 저장소의 독스트링은 **길고, 근거를 적고, 서로를 가리킨다.** 그것이 이
저장소의 가장 좋은 자산이지만 동시에 **가장 빨리 낡는 것**이다. 코드가
움직여도 그 문장은 따라 움직이지 않는다.

R43 이 같은 형태를 **두 번** 고쳤다.

    WP-A   러너가 내놓는다고 적힌 함수 이름이 **어디에도 없었다** (2곳).
           R38·R39 가 두 번 신고했고 **두 라운드를 살아남았다.**
    WP-F3  이름은 실재하는데 **선언 자리가 옮겨졌고** 문면은 옛 자리를
           가리켰다 (3곳).

두 번 다 **사람이 눈으로 찾았다.** 재는 것이 없으면 다음에도 다시 쌓인다.
이것이 이 저장소가 반복해 적은 형태다 — *「선언과 구현이 갈린다」* ·
*「문서가 실물보다 후하게 적는다」*.

## 무엇을 재는가 — **좁게 잡았다**

백틱 안의 문면 중 **자기 자신이 무엇을 가리키는지 말하는 것**만 본다.

    core/cba/proforma.py::fee_row      모듈 경로 + 이름 — 둘 다 대조한다
    ledger_levels.py::_LEDGER_VARS     이름이 저장소에서 유일하면 대조한다
    core/report/unreflected.py         경로 표기 — 파일이 실재하는가
    operating_lines.net_operating_flows()   왼쪽이 모듈일 때만 (아래 참조)

**소스를 정규식으로 훑지 않는다.** 독스트링은 `ast`, 주석은 `tokenize` 로
얻는다 — R24 가 소스 문면 검사를 `ast` 로 옮긴 것과 같은 판단이며, 문자열로
훑으면 코드 안의 문면과 문서 안의 문면이 섞인다.

**재수출을 참으로 인정한다** (R43 · WP-F3 의 규약). `import ... as` 가 만든
이름은 그 모듈의 이름이다 — 선언이 다른 파일에 있어도 참이다.

## 무엇을 **일부러 안 재는가** — 실측된 거짓 양성

- **왼쪽이 객체인 점 표기.** 실측에서 이 꼴로 걸린 셋 중 셋 다 거짓이었다 —
  수신자가 모듈이 아니라 **변수**였고(대장 제공자·자원 객체), 이름이 우연히
  모듈 파일 이름과 같았을 뿐이다. 그래서 왼쪽 이름이 **그 파일 안에서
  값으로 묶여 있으면**(매개변수·대입·`for`·`with as`) 대조하지 않는다.
- **경로 없는 흔한 파일 이름** — 여러 곳에 같은 이름이 있으면 어느 것인지
  말할 수 없다. 말할 수 없는 것은 세지 않는다.
- **경위를 적는 문장.** *「종전에는 …였다」* 는 **옛 이름을 일부러 적는다.**
  거짓으로 세면 이 저장소의 가장 좋은 문서들이 빨간불이 된다. 그래서
  `KNOWN_STALE` 로 **빠져나갈 문을 두되 사유를 적게 한다** (R42 의
  `scripts/check_dependency_audit.py` 가 세운 형태 — *「막는 것은 취약점이
  아니라 아무도 안 본 취약점이다」*).

`KNOWN_STALE` 은 **면제 목록이 아니라 부채 목록**이다. 실측과 다르면 —
늘어도, 줄었는데 목록을 안 고쳐도 — 종료 코드 1 이다.

## 이 검사 자신이 자기 검사에 걸리는 문제

이 저장소가 **여섯 번** 걸린 유형이다. 위 머리말에서 *없는 이름*을 예로 들
자리(WP-A 가 지운 그 함수)는 백틱을 쓰지 않고 **말로 적었다.** 예시로 든
백틱 문면 넷은 전부 실재하는 것으로 골랐다 — 검사가 자기 자신을 포함해
전건을 돌아도 초록불이다. **이 파일을 건너뛰지 않는다**(건너뛰면 구멍이다).

## 종료 코드

    0  대조한 문면이 전부 실물과 맞는다
    1  실물에 없는 것을 가리킨다 · `KNOWN_STALE` 이 실측과 다르다
    2  대조할 것이 없다 — 대상 파일 0개 또는 뽑힌 문면 0건 (**검사 미수행**)

    python scripts/check_docstring_references.py
"""

from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 훑는 층. 배포 코드와 검사·시험을 모두 본다 — 낡은 문면은 어디서나 쌓인다.
SCAN_ROOTS: tuple[str, ...] = ("core", "app", "infra", "web", "scripts", "tests")

#: 경위를 적느라 **일부러** 옛 이름을 쓰는 자리. (파일, 문면) → 사유.
#: 부채 목록이며 면제 목록이 아니다 (위 머리말 참조). 2026-08-30 실측.
KNOWN_STALE: dict[tuple[str, str], str] = {
    (
        "tests/valuestream/test_settlement.py",
        "core/model/settlement.py::SettlementEngine",
    ): "R31 이 없앤 사본을 적는 경위 문장. 「종전 … 은」으로 시작한다.",
    (
        "tests/contract/test_payer_structure_contract.py",
        "core/model/settlement.py",
    ): "위와 같음 — R31 이 없앤 사본의 자리를 적는다.",
}

#: 백틱 한 겹 또는 두 겹. 줄바꿈을 넘어도 잡는다 — 긴 경로는 줄을 넘겨 적힌다.
_BACKTICK = re.compile(r"``?([^`]+?)``?", re.S)

#: `모듈::이름` 의 오른쪽에서 이름만 떼어낸다 (`name()` · `= 0.15` 등이 붙는다).
_SYMBOL = re.compile(r"^([A-Za-z_][\w.]*)")

#: 경로 표기 — 뒤에 `:줄` 이 붙을 수 있다.
_PATH = re.compile(r"([\w/.-]+\.py)(?::\d+(?:-\d+)?)?")

#: 점 표기 — 「왼쪽.이름()」. 괄호가 있어야 후보다.
_DOTTED = re.compile(r"([a-z_]\w*)\.([A-Za-z_]\w*)\(\)")


def _py_files() -> list[Path]:
    out: list[Path] = []
    for root in SCAN_ROOTS:
        base = ROOT / root
        if not base.is_dir():
            continue
        out += [p for p in sorted(base.rglob("*.py")) if "__pycache__" not in p.parts]
    return out


def _bound_names(target: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(target):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
    return out


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None


def _declared(path: Path) -> frozenset[str]:
    """모듈이 내놓는 이름 전부. **import 별칭을 포함한다** — 재수출은 참이다."""
    tree = _parse(path)
    if tree is None:
        return frozenset()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names |= _bound_names(target)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            names |= _bound_names(node.target)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
    return frozenset(names)


def _value_bound(path: Path) -> frozenset[str]:
    """그 파일 안에서 **값으로 묶인** 이름 — 매개변수·대입·`for`·`with as`.

    점 표기의 왼쪽이 여기 있으면 그것은 모듈이 아니라 객체다. 실측된 거짓
    양성 셋이 전부 이 형태였다.
    """
    tree = _parse(path)
    if tree is None:
        return frozenset()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            every = [*args.posonlyargs, *args.args, *args.kwonlyargs]
            if args.vararg is not None:
                every.append(args.vararg)
            if args.kwarg is not None:
                every.append(args.kwarg)
            names.update(arg.arg for arg in every)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names |= _bound_names(target)
        elif isinstance(
            node,
            (ast.AnnAssign, ast.AugAssign, ast.For, ast.AsyncFor, ast.comprehension),
        ):
            names |= _bound_names(node.target)
        elif isinstance(node, ast.withitem):
            if node.optional_vars is not None:
                names |= _bound_names(node.optional_vars)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    return frozenset(names)


class _Index:
    """저장소 안의 파이썬 파일을 경로·파일이름·모듈이름으로 찾는다."""

    def __init__(self, files: list[Path]) -> None:
        self.by_rel: dict[str, Path] = {}
        self.by_name: dict[str, list[Path]] = defaultdict(list)
        self.by_stem: dict[str, list[Path]] = defaultdict(list)
        for path in files:
            self.by_rel[path.relative_to(ROOT).as_posix()] = path
            self.by_name[path.name].append(path)
            self.by_stem[path.stem].append(path)

    def by_path_text(self, text: str) -> tuple[Path | None, str]:
        """경로가 적힌 표기. **경로에 `/` 가 있을 때만** 부재를 단언한다."""
        rel = text.replace("\\", "/")
        if "/" in rel:
            hit = self.by_rel.get(rel)
            if hit is not None:
                return hit, "ok"
            if (ROOT / rel).exists() or (ROOT / rel).with_suffix("").is_dir():
                return None, "skip"
            return None, "absent"
        found = self.by_name.get(rel, [])
        return (found[0], "ok") if len(found) == 1 else (None, "skip")

    def by_module_text(self, text: str) -> tuple[Path | None, str]:
        """`::` 왼쪽. 경로·파일이름·모듈이름 셋 다 받는다."""
        if not text:
            return None, "skip"
        if text.endswith(".py"):
            return self.by_path_text(text)
        found = self.by_stem.get(text, [])
        return (found[0], "ok") if len(found) == 1 else (None, "skip")


def _chunks(path: Path, src: str) -> list[tuple[int, str]]:
    """독스트링(`ast`)과 주석(`tokenize`). **소스 문면을 훑지 않는다.**"""
    out: list[tuple[int, str]] = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        text = ast.get_docstring(node, clean=False)
        if text and node.body and isinstance(node.body[0], ast.Expr):
            out.append((node.body[0].lineno, text))
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                out.append((tok.start[0], tok.string))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return out


def _check_span(
    span: str, origin: Path, index: _Index, value_bound: frozenset[str]
) -> tuple[str, str] | None:
    """한 문면을 판정한다. 위반이면 `(문면, 사유)`, 아니면 `None`."""
    text = " ".join(span.split())
    if "::" in text:
        left, _, right = re.sub(r"\s*::\s*", "::", text).partition("::")
        left = left.split()[-1] if left.split() else ""
        match = _SYMBOL.match(right)
        if match is None:
            return None
        module, how = index.by_module_text(left)
        if how == "absent":
            return f"{left}::{match.group(1)}", f"모듈 파일이 없다: {left}"
        if module is None:
            return None
        names = _declared(module)
        missing = [part for part in match.group(1).split(".") if part not in names]
        if missing:
            where = module.relative_to(ROOT).as_posix()
            return (
                f"{left}::{match.group(1)}",
                f"{where} 에 그 이름이 없다: {'·'.join(missing)}",
            )
        return None

    path_match = _PATH.fullmatch(text)
    if path_match is not None:
        _, how = index.by_path_text(path_match.group(1))
        if how == "absent":
            return path_match.group(1), f"그 경로에 파일이 없다: {path_match.group(1)}"
        return None

    dotted = _DOTTED.fullmatch(text)
    if dotted is not None:
        left, symbol = dotted.group(1), dotted.group(2)
        if left in value_bound:
            return None  # 모듈이 아니라 객체다 — 위 머리말 참조
        module, _how = index.by_module_text(left)
        if module is None or module == origin:
            return None
        if symbol not in _declared(module):
            where = module.relative_to(ROOT).as_posix()
            return f"{left}.{symbol}()", f"{where} 에 그 이름이 없다: {symbol}"
    return None


def main() -> int:
    files = _py_files()
    if not files:
        print("ERROR: 훑을 파이썬 파일이 없다 — 검사를 수행하지 못했다", file=sys.stderr)
        return 2

    index = _Index(files)
    scanned = 0
    violations: list[str] = []
    seen_stale: set[tuple[str, str]] = set()

    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue
        value_bound = _value_bound(path)
        for lineno, chunk in _chunks(path, src):
            for match in _BACKTICK.finditer(chunk):
                scanned += 1
                verdict = _check_span(match.group(1), path, index, value_bound)
                if verdict is None:
                    continue
                span, reason = verdict
                key = (rel, span)
                if key in KNOWN_STALE:
                    seen_stale.add(key)
                    continue
                violations.append(f"  {rel}:{lineno}  `{span}`\n      -> {reason}")

    if scanned == 0:
        print("ERROR: 뽑힌 문면이 0건 — 검사를 수행하지 못했다", file=sys.stderr)
        return 2

    print(
        f"훑은 파일 {len(files)}개 · 백틱 문면 {scanned}건 · "
        f"경위 면제 {len(KNOWN_STALE)}건"
    )

    stale_gone = sorted(set(KNOWN_STALE) - seen_stale)
    if violations:
        print(f"\n실물에 없는 것을 가리키는 문면 {len(violations)}건:")
        print("\n".join(violations))
    if stale_gone:
        print(f"\nKNOWN_STALE 에 있는데 실측되지 않은 항목 {len(stale_gone)}건 —")
        print("실물이 고쳐졌거나 문면이 바뀌었다. 목록에서 빼라:")
        for rel, span in stale_gone:
            print(f"  {rel}  `{span}`")
    if violations or stale_gone:
        return 1

    print("어긋난 문면 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
