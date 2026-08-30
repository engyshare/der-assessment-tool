#!/usr/bin/env python3
"""조항 인용의 **내용**을 읽는 공통 자료 — 그물 ③-1·③-2 가 함께 쓴다.

## 왜 이 모듈이 있는가

R37 이 세운 두 그물은 **인용의 내용을 보지 않는다.** 하나는 인용 **건수**를
세고(1건뿐인 조항), 다른 하나는 **Phase** 를 견준다. R38 이 `FR-101-AC3` 에서
그 둘 사이로 빠져나가는 세 번째 형태를 찾았다 —
*「인용이 여럿인데 그 전부가 다른 조항을 잰다」*
(`.orch/R38/result_ac3_empty.md:306-364`).

그 형태를 잡으려면 인용마다 **무엇을 import 하는가**(그물 ③-1)와 **무슨 조항
ID 를 적는가**(그물 ③-2)를 알아야 한다. 두 그물이 같은 자료를 쓰므로 수집을
여기 **한 곳에 둔다** — 각자 훑으면 마커 상속 규칙이 갈리고, 그러면 두 그물이
서로 다른 인용 집합을 보면서 조용히 다른 판정을 낸다.

## 정본을 다시 짜지 않는다

- 마커 읽기는 `gen_traceability._marks` 그대로다. 상속(모듈 `pytestmark` ·
  클래스 데코레이터)도 `_walk_body` 와 같은 형태로 훑는다 — pytest 가 그렇게
  동작하므로 도구도 같아야 한다. **함수 이름·줄번호·문면을 더한 것만이
  차이**이며, 그 차이가 어긋나지 않았음은 `negtest_clause_nets.py` 의 갈래
  ⑬ 이 `collect_test_markers()` 와 대조해 확인한다.
- 조항 목록은 `_specparse.parse_spec` 그대로다.
- 조항 ID 의 생김새는 `_specparse.CID_BODY` 단독 소유다.

## 문면을 정규식으로 훑지 않는다

`check_docstring_references._chunks()` 와 같은 판단이다 — 독스트링과 문자열
상수는 `ast` 로, 주석은 `tokenize` 로 얻는다. 소스를 문자열로 훑으면 코드 안의
문면과 문서 안의 문면이 섞인다.

★ **데코레이터는 문면에서 뺀다.** `@pytest.mark.req("FR-101-AC3")` 의 인자는
`ast.walk(함수노드)` 에 딸려 온다. 그것을 「이 테스트가 조항을 적었다」로 세면
**모든 인용이 자기 조항을 적은 것이 되어 그물 ③-2 가 통째로 잠든다** — 실측으로
확인했다(그렇게 세면 인용 있는 조항 294건 전부가 「자기 이름을 적음」이 되고
지목이 0건이 된다).
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path
from typing import NamedTuple

from _specparse import CID_BODY, parse_spec
from gen_traceability import _marks

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "rslt" / "spec-분산특구-경제성평가.md"
DEFAULT_TESTS = ROOT / "tests"

#: 문면 안의 조항 ID. **백틱을 요구하지 않는다** — 오류 문면(`assert ..., "…"`)은
#: 백틱 없이 조항을 적는다.
#:
#: 왼쪽 경계 `(?<![A-Za-z0-9])` 가 이 정규식의 핵심이다. 이 저장소는 `FR-` 를
#: 그냥 찾다가 `NFR-` 를 함께 잡는 함정을 반복해 밟았다 — 대안 목록에 `NFR` 이
#: 있어도 경계가 없으면 `NFR-208` 의 두 번째 글자에서 `FR-208` 이 또 걸린다.
MENTION = re.compile(rf"(?<![A-Za-z0-9])({CID_BODY})")


class Citation(NamedTuple):
    """마커 하나가 만드는 인용 한 건."""

    cid: str
    path: str
    func: str
    lineno: int
    #: 인용을 단 **파일**이 들여오는 점 표기 이름들. 문자열 상수는 들어 있지
    #: 않다 — 그 구분이 그물 ③-1 의 판정 그 자체다.
    imports: frozenset[str]
    #: 인용을 단 **함수 본문**이 적은 조항 ID 들. 데코레이터는 뺀다.
    mentions: frozenset[str]


def criteria(spec_path: Path) -> tuple[dict[str, str], list[str]]:
    """수용기준 ID → 문면. 그리고 spec 파싱 결함."""
    reqs, defects = parse_spec(spec_path)
    return {c.cid: c.text for r in reqs for c in r.criteria}, defects


def same_clause(a: str, b: str) -> bool:
    """`a` 와 `b` 가 **같은 조항**인가 — 2.15 표 전개의 부모·자식을 포함한다.

    `FR-601-AC2.cost` 를 재는 테스트가 문면에 `FR-601-AC2` 라고 적는 것은
    「다른 조항을 적었다」가 아니다. 표 수용기준 전개(2.15 ①)로 한 조항이
    행 단위로 갈린 것이고, 전개 전 이름을 적는 것은 **자기 조항을 적은 것**
    이다. 이 구분이 없으면 그물 ③-2 의 지목이 61건이고, 두면 46건이다 —
    지운 15건은 전부 전개 부모·자식이었다(실측).
    """
    return a == b or a.startswith(f"{b}.") or b.startswith(f"{a}.")


def module_imports(tree: ast.Module) -> frozenset[str]:
    """`import` 문이 들여오는 점 표기 이름들. **문자열 리터럴은 세지 않는다.**

    `from core.engine.rule_based import X` 는 `core.engine.rule_based` 와
    `core.engine.rule_based.X` 를 함께 낸다 — 그물 ③-1 이 구획 접두로 견주므로
    둘 다 있어도 판정은 같지만, 상대 import(`from . import x`)를 조용히 절대
    이름으로 지어내지 않기 위해 `level > 0` 은 버린다.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return frozenset(names)


def _comment_lines(src: str) -> dict[int, str]:
    """줄번호 → 주석 문면. `tokenize` 로 얻는다 (정규식이 아니다)."""
    out: dict[int, str] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                out[tok.start[0]] = tok.string
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # 주석을 못 읽어도 독스트링·오류 문면은 `ast` 로 얻는다. 조용히 비우고
        # 넘어가되 문면 자체가 0건이 되는 것은 부르는 쪽이 rc=2 로 잡는다.
        pass
    return out


def _mentions(
    func: ast.FunctionDef | ast.AsyncFunctionDef, comments: dict[int, str]
) -> frozenset[str]:
    """함수 **본문**이 적은 조항 ID 들.

    본문의 문자열 상수(독스트링·오류 문면)와 본문 줄 범위의 주석만 본다.
    데코레이터를 빼는 이유는 이 모듈 머리말에 적었다.
    """
    if not func.body:
        return frozenset()
    lo = func.body[0].lineno
    hi = func.end_lineno or lo
    texts: list[str] = [
        node.value
        for stmt in func.body
        for node in ast.walk(stmt)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    texts += [text for lineno, text in comments.items() if lo <= lineno <= hi]
    return frozenset(MENTION.findall("\n".join(texts)))


def _walk(
    body: list[ast.stmt],
    inherited: list[str],
    *,
    imports: frozenset[str],
    comments: dict[int, str],
    rel: str,
    out: list[Citation],
) -> None:
    """클래스·함수를 훑어 인용을 모은다.

    ⚠ **파일 루프 안의 중첩 함수로 두지 않는다.** 루프 변수를 클로저로 잡으면
    (ruff `B023`) 지연 호출로 바뀌는 순간 마지막 파일의 경로가 전 항목에
    붙는다. `gen_traceability._walk_body` 가 같은 이유로 모듈 수준에 있다.
    """
    for node in body:
        if isinstance(node, ast.ClassDef):
            _walk(
                node.body,
                inherited + _marks(node.decorator_list)[0],
                imports=imports,
                comments=comments,
                rel=rel,
                out=out,
            )
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            cids = inherited + _marks(node.decorator_list)[0]
            if not cids:
                continue
            mentions = _mentions(node, comments)
            for cid in cids:
                out.append(
                    Citation(cid, rel, node.name, node.lineno, imports, mentions)
                )


def collect(tests_dir: Path, root: Path = ROOT) -> tuple[list[Citation], list[str]]:
    """`tests/` 전건의 인용. 그리고 파싱 결함.

    결함을 조용히 건너뛰지 않는 이유는 `gen_traceability.collect_test_markers`
    가 적어 둔 그대로다 — 파일 하나를 건너뛰면 그 파일의 마커가 통째로 사라지고
    해당 수용기준이 「아무도 검증하지 않는 것」처럼 보인다.
    """
    out: list[Citation] = []
    defects: list[str] = []
    if not tests_dir.is_dir():
        return out, defects

    for py in sorted(tests_dir.rglob("*.py")):
        src = py.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src, filename=str(py))
        except SyntaxError as exc:
            defects.append(
                f"{py.name} 파싱 실패 (L{exc.lineno}) — "
                f"이 파일의 마커가 집계에서 통째로 빠집니다: {exc.msg}"
            )
            continue

        module_reqs: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
            ):
                items = (
                    node.value.elts
                    if isinstance(node.value, ast.List | ast.Tuple)
                    else [node.value]
                )
                module_reqs += _marks(items)[0]

        try:
            rel = py.relative_to(root).as_posix()
        except ValueError:
            rel = py.as_posix()

        _walk(
            tree.body,
            module_reqs,
            imports=module_imports(tree),
            comments=_comment_lines(src),
            rel=rel,
            out=out,
        )

    return out, defects


def by_clause(citations: list[Citation]) -> dict[str, list[Citation]]:
    """조항 ID → 그 조항의 인용들. **조항 단위로 묻기 위한 것이다.**

    두 그물 다 검사 하나씩을 판정하지 않는다 — 조항 하나에 대해 *그 인용
    전부* 를 본다. `.orch/R38/result_ac3_empty.md:362` 가 그 이유를 적었다.
    """
    out: dict[str, list[Citation]] = {}
    for cite in citations:
        out.setdefault(cite.cid, []).append(cite)
    return out
