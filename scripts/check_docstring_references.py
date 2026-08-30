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
    TimeSeriesBinding.swap()           왼쪽이 대문자면 **클래스**로 본다

**소스를 정규식으로 훑지 않는다.** 독스트링은 `ast`, 주석은 `tokenize` 로
얻는다 — R24 가 소스 문면 검사를 `ast` 로 옮긴 것과 같은 판단이며, 문자열로
훑으면 코드 안의 문면과 문서 안의 문면이 섞인다.

**재수출을 참으로 인정한다** (R43 · WP-F3 의 규약). `import ... as` 가 만든
이름은 그 모듈의 이름이다 — 선언이 다른 파일에 있어도 참이다. 클래스도 같다:
`from x import Y as Z` 로 얻은 `Z` 는 클래스 `Y` 다.

## 점 표기의 왼쪽 — 모듈인가 클래스인가

`_DOTTED` 는 오래도록 왼쪽을 **소문자로 시작하는 것만** 잡았다. 그래서
`ESS.reducible_peak_kw()` 처럼 **클래스를 수신자로 쓴 문면 41건**이 정규식
문턱에서 통째로 빠졌다 — 문서화된 제외가 아니라 검토된 적 없는 빈틈이었다
(R44 · WP-10 이 세었다). 이제 왼쪽 첫 글자로 갈래를 나눈다.

    소문자·언더스코어 → 모듈. `_Index` 로 파일을 찾는다 (종전 그대로).
    대문자           → 클래스. `_ClassIndex` 로 선언을 찾는다.

클래스는 **파일에 매이지 않고 저장소 전체에 흩어져 선언**되므로 모듈 색인과
따로 둔다. 동명 클래스가 둘 이상이면 어느 것인지 말할 수 없다 — `_Index` 가
파일 이름에 이미 쓰는 규칙과 같다.

## 무엇을 **일부러 안 재는가** — 실측된 거짓 양성

- **왼쪽이 객체인 점 표기.** 실측에서 이 꼴로 걸린 셋 중 셋 다 거짓이었다 —
  수신자가 모듈이 아니라 **변수**였고(대장 제공자·자원 객체), 이름이 우연히
  모듈 파일 이름과 같았을 뿐이다. 그래서 왼쪽 이름이 **그 파일 안에서
  값으로 묶여 있으면**(매개변수·대입·`for`·`with as`) 대조하지 않는다.
  클래스 수신자에도 같은 이유로 같게 적용한다 — 클래스 이름과 우연히 같은
  지역 변수가 있다(실측 1건).
- **부모를 읽을 수 없는 클래스.** 저장소 밖 클래스를 상속하면 그것이 무슨
  이름을 물려주는지 말할 수 없다. 물려받은 메서드를 자식 이름으로 가리키는
  문면은 **정당한데**, 상속을 안 보면 그것이 전부 거짓 위반이 된다. 그래서
  부모를 하나라도 못 읽으면 그 클래스는 **판정하지 않는다.** 예외는
  `_INERT_BASES` 둘뿐이며 사유를 거기 적었다.
- **dunder 이름.** `__init__` · `__subclasses__` 처럼 `object` 가 내놓는
  이름은 어느 클래스에도 있다. 세면 거짓 위반이다(실측 1건).
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
백틱 문면 다섯은 전부 실재하는 것으로 골랐다 — 검사가 자기 자신을 포함해
전건을 돌아도 초록불이다. **이 파일을 건너뛰지 않는다**(건너뛰면 구멍이다).
클래스 갈래를 붙이며 같은 자리를 또 밟을 뻔했다: 설명에 「지어낸 클래스.
지어낸이름()」을 백틱으로 적으면 지금은 저장소에 없어 조용히 안 세어지지만,
같은 이름의 클래스가 생기는 날 자기가 자기에게 걸린다. **지어낸 예에는 백틱을
쓰지 않는다** — 위 예시 다섯이 전부 실물인 이유다.

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
from typing import NamedTuple

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

#: 점 표기 — 「왼쪽.이름()」. 괄호가 있어야 후보다. 왼쪽의 첫 글자로
#: 모듈(소문자)과 클래스(대문자)를 가른다 — 판정은 `_check_span()` 이 나눈다.
_DOTTED = re.compile(r"([A-Za-z_]\w*)\.([A-Za-z_]\w*)\(\)")

#: **아무 이름도 물려주지 않는** 저장소 밖 부모. 이것만 예외로 인정하고
#: 나머지 밖 부모(예: `BaseModel`·`StrEnum`·`HTMLParser`)는 무엇을 물려주는지
#: 말할 수 없으므로 그 클래스를 통째로 판정하지 않는다. 사유를 값에 적는다.
_INERT_BASES: dict[str, str] = {
    "ABC": "abc.ABC 는 `object` 의 dunder 말고 자기 이름을 내놓지 않는다.",
    "Protocol": "typing.Protocol 도 같다 — 구조만 선언하고 이름을 안 준다.",
}


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


class _ClassDecl(NamedTuple):
    """한 `class` 선언 — 자기 몸에 든 이름과 부모로 적힌 이름들."""

    name: str
    path: Path
    own: frozenset[str]
    #: 부모 이름. `None` 은 **이름으로 적히지 않은 부모**(첨자 표기 등)다.
    bases: tuple[str | None, ...]


def _class_own_names(node: ast.ClassDef) -> frozenset[str]:
    """그 클래스가 **직접** 갖는 이름.

    본문에 선언된 메서드·중첩 클래스와 클래스 수준 대입을 센다. 여기에
    `self.x = ...` 로 묶이는 **인스턴스 속성**도 더한다 — 문서가 「클래스.
    이름()」이라 적을 때 가리키는 것은 그 클래스가 내놓는 이름이지 선언이
    `class` 몸에 있는지가 아니다.
    """
    names: set[str] = set()
    for stmt in node.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(stmt.name)
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                names |= _bound_names(target)
        elif isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
            names |= _bound_names(stmt.target)
    for sub_node in ast.walk(node):
        if (
            isinstance(sub_node, ast.Attribute)
            and isinstance(sub_node.value, ast.Name)
            and sub_node.value.id == "self"
        ):
            names.add(sub_node.attr)
    return frozenset(names)


def _base_names(node: ast.ClassDef) -> tuple[str | None, ...]:
    out: list[str | None] = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            out.append(base.id)
        elif isinstance(base, ast.Attribute):
            out.append(base.attr)
        else:
            out.append(None)
    return tuple(out)


class _ClassIndex:
    """저장소 전체에 흩어진 `class` 선언을 **이름으로** 찾는다.

    클래스는 파일에 매이지 않으므로 `_Index` 와 따로 둔다. 동명이 둘 이상이면
    어느 것인지 말할 수 없다 — `_Index.by_name` 이 이미 쓰는 규칙과 같다.
    """

    def __init__(self, files: list[Path]) -> None:
        self.by_name: dict[str, list[_ClassDecl]] = defaultdict(list)
        self.by_alias: dict[str, set[str]] = defaultdict(set)
        seen_alias: list[tuple[str, str]] = []
        for path in files:
            tree = _parse(path)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    self.by_name[node.name].append(
                        _ClassDecl(
                            node.name, path, _class_own_names(node), _base_names(node)
                        )
                    )
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        if alias.asname:
                            seen_alias.append((alias.asname, alias.name.split(".")[-1]))
        # 재수출은 참이다 (머리말 참조) — `from x import Y as Z` 의 `Z` 는 `Y` 다.
        for asname, original in seen_alias:
            if original in self.by_name:
                self.by_alias[asname].add(original)

    def resolve(self, name: str) -> _ClassDecl | None:
        """이름 하나로 선언 하나를 짚는다. 못 짚으면 `None` — 세지 않는다."""
        found = self.by_name.get(name)
        if found is None:
            targets = self.by_alias.get(name, set())
            if len(targets) != 1:
                return None
            found = self.by_name[next(iter(targets))]
        return found[0] if len(found) == 1 else None

    def members(
        self, decl: _ClassDecl, seen: frozenset[str] = frozenset()
    ) -> frozenset[str] | None:
        """그 클래스가 갖는 이름 전부. **부모를 하나라도 못 읽으면 `None`.**

        완전한 MRO 해석은 하지 않는다 — 이름의 합집합이면 족하고, 이 검사가
        재는 것은 *그 이름이 있는가*이지 어느 부모의 것인가가 아니다.
        """
        if decl.name in seen:
            return decl.own
        names = set(decl.own)
        for base in decl.bases:
            if base is None:
                return None
            if base in _INERT_BASES:
                continue
            parent = self.resolve(base)
            if parent is None:
                return None  # 저장소 밖 부모 — 무엇을 물려주는지 말할 수 없다
            inherited = self.members(parent, seen | {decl.name})
            if inherited is None:
                return None
            names |= inherited
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
        """경로가 적힌 표기. **경로에 `/` 가 있을 때만** 부재를 단언한다.

        ★ **꼬리만 적은 경로를 인정한다** — `contracts/der.py` 는
        `core/contracts/der.py` 를 가리키며, 그렇게 읽히는 실물이 **하나뿐이면
        어느 파일인지 말할 수 있다.** 인정하지 않으면 이 검사가 앞뒤로
        어긋난다: 접두를 통째로 뺀 `ledger_levels.py` 는 이미 인정하면서
        일부만 뺀 것은 거짓으로 세게 된다. 이 검사가 재는 것은 **이름과 자리가
        실재하는가**이지 경로를 몇 마디로 적었는가가 아니다.
        """
        rel = text.replace("\\", "/")
        if "/" in rel:
            hit = self.by_rel.get(rel)
            if hit is not None:
                return hit, "ok"
            if (ROOT / rel).exists() or (ROOT / rel).with_suffix("").is_dir():
                return None, "skip"
            tails = [p for q, p in self.by_rel.items() if q.endswith(f"/{rel}")]
            if len(tails) == 1:
                return tails[0], "ok"
            if tails:
                return None, "skip"  # 여럿이면 어느 것인지 말할 수 없다
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
    span: str,
    origin: Path,
    index: _Index,
    classes: _ClassIndex,
    value_bound: frozenset[str],
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
            return None  # 모듈·클래스가 아니라 객체다 — 위 머리말 참조
        if left[:1].isupper():
            return _check_class_span(left, symbol, classes)
        module, _how = index.by_module_text(left)
        if module is None or module == origin:
            return None
        if symbol not in _declared(module):
            where = module.relative_to(ROOT).as_posix()
            return f"{left}.{symbol}()", f"{where} 에 그 이름이 없다: {symbol}"
    return None


def _check_class_span(
    left: str, symbol: str, classes: _ClassIndex
) -> tuple[str, str] | None:
    """클래스 수신자 갈래. **말할 수 없는 것은 전부 `None`(안 센다).**"""
    if symbol.startswith("__") and symbol.endswith("__"):
        return None  # `object` 가 내놓는 이름 — 어느 클래스에도 있다
    decl = classes.resolve(left)
    if decl is None:
        return None  # 저장소에 없거나 동명이 여럿이다 — 어느 것인지 말할 수 없다
    names = classes.members(decl)
    if names is None or symbol in names:
        return None  # `None` 은 부모를 못 읽었다는 뜻이다 (머리말 참조)
    where = decl.path.relative_to(ROOT).as_posix()
    return f"{left}.{symbol}()", f"{where} 의 {left} 에 그 이름이 없다: {symbol}"


def main() -> int:
    files = _py_files()
    if not files:
        print("ERROR: 훑을 파이썬 파일이 없다 — 검사를 수행하지 못했다", file=sys.stderr)
        return 2

    index = _Index(files)
    classes = _ClassIndex(files)
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
                verdict = _check_span(
                    match.group(1), path, index, classes, value_bound
                )
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
        f"클래스 선언 {sum(len(v) for v in classes.by_name.values())}건 · "
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
