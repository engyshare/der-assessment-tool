#!/usr/bin/env python3
"""**조항 인용 대장** — 후보 조항마다 「조항이 요구하는 것」과 「인용이 재는 것」을
한자리에 편다. `audit_clause_selfreference.py` 가 지목한 후보를 **사람이 대조할 수
있는 형태로** 펴는 것이 전부다.

## 왜 이것이 있는가

③-2 지목은 후보를 수십 건 낸다. 그 전건을 **손으로 대조하게 두면 이 저장소는 조항
문면을 지어냈다** — 기억으로 쓴 문장 위에 판정이 서고, 원문과 어긋난 그 판정이
다음 라운드에 계획으로 따라 들어간다. 그래서 대조하는 사람이 볼 문면을 **도구가
원문에서 떠다 준다.** 대장에 없는 문장은 판정 근거가 아니다.

    ① 조항 문면 그대로      spec 원문 줄을 **줄이지 않고** 낸다
    ② 인용 전건의 자리       `파일:줄` · 함수 이름
    ③ 인용마다 근거줄        독스트링 머리 · `assert` 줄 (자르면 **자른 표시**를 남긴다)
    ④ 인용이 적은 조항 ID    `_citations.MENTION` 그대로 — 지목 도구와 **같은 정규식**

## 판정하지 않는다

`audit_` 접두는 `audit_clause_selfreference.py` 독스트링이 적어 둔 그 판단이다 —
**거짓일 수 있는 문면으로 위반을 선고할 수 없다.** 이 도구는 거기서 한 걸음 더
물러서 있다: 지목조차 하지 않고 **원문을 펴 놓기만 한다.** 그러므로 종료 코드를
차단으로 올리지 않고 **CI 에 배선하지 않는다.**

## 무엇을 다시 만들지 않았나

| 무엇 | 어디서 가져오나 |
|---|---|
| 후보 목록 | `audit_clause_selfreference.candidates()` |
| 인용 수집 · 마커 상속 | `_citations.collect()` · `by_clause()` |
| 인용이 적은 조항 ID | `_citations.Citation.mentions` (정규식 `MENTION` 단독 소유) |
| 유효한 조항 ID 집합 | `_specparse.parse_spec()` |
| 조항 줄의 생김새 | `_specparse.CRITERION` · `REQ_START` · `SECURITY_ROW` |

**재사용할 수 없었던 자리 둘 — 사유를 여기 적는다.**

1. **조항 문면의 원문.** `parse_spec()` 이 주는 `Criterion.text` 는 `summarize()`
   를 거친 것이라 **90자에서 잘리고 마크다운 강조가 걷힌** 상태이고, 게다가 **선언
   줄 한 줄뿐**이다 — spec 의 긴 조항은 접혀 있어(`FR-101-AC5` 는 네 줄이다) 첫
   줄만 내면 문장이 중간에서 끊긴다. 추적표 한 칸에는 족하지만 이 도구가 필요로
   하는 「원문 그대로」가 아니다(줄여 낸 문면 위에 판정이 서는 것이 막으려는 바로
   그 일이다). 그래서 spec 을 한 번 더 읽어 **조항 ID 의 원문 줄과 접힌 뒷줄을
   찾는다.** ⚠ **어느 줄이 조항인가를 다시 판정하지는 않는다** — 유효한 ID 집합은
   `parse_spec()` 이 소유하고 여기서는 그 ID 의 **자리를 찾을 뿐**이다. 못 찾으면
   조용히 비우지 않고 그렇게 적어 낸다.
2. **인용 함수의 근거줄.** `_citations` 는 문면에서 **조항 ID 만** 뽑고 원문 줄은
   버린다(그 모듈에 필요한 것이 ID 뿐이다). 독스트링 머리와 `assert` 줄은 여기서
   `ast` 로 다시 얻되 **같은 층위로 읽는다** — 함수 본문 한정이며 정규식으로 소스를
   훑지 않는다(`_citations` 머리말의 그 이유 그대로다).

## 종료 코드

    0  대장을 냈다 (후보가 몇 건이든 0 이다 — **차단이 아니다**)
    2  훑을 것이 없다 (인용 0건 · 테스트 파싱 결함 · 고를 것을 안 줬다) — 검사 미수행

    python scripts/audit_clause_dossier.py --from-audit --min-citations 5 --out 대장.md
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

from _citations import DEFAULT_SPEC, DEFAULT_TESTS, Citation, by_clause, collect
from _specparse import CRITERION, REQ_START, SECURITY_ROW, parse_spec
from audit_clause_selfreference import candidates

ROOT = Path(__file__).resolve().parents[1]

#: 근거줄의 상한. **자르되 자른 것을 숨기지 않는다** — 조용히 자르면 판정이 잘린
#: 문장 위에 선다. 줄 수 상한을 넘긴 것은 블록 끝에, 글자 수 상한을 넘긴 것은
#: 그 줄 끝에 표시가 남는다.
DOC_HEAD_LINES = 8
MAX_ASSERTS = 12
MAX_CHARS = 240
CUT = " …[잘림]"

MISSING_CLAUSE = "⚠ spec 원문 줄을 찾지 못했다 — 이 조항은 문면 대조가 불가능하다"

#: 조항 불릿 **뒤에 붙는 다른 블록**의 첫 글자. 이것으로 시작하는 줄은 접힌
#: 뒷줄이 아니라 새 블록이므로 조항 문면에 넣지 않는다 — `FR-401-AC2.AggregatedPPA`
#: 는 빈 줄 없이 바로 `> **왜 `SurplusSale` 로 …**` 인용 블록이 이어지는데, 그것은
#: 조항이 아니라 옆에 붙인 사유다. 넣으면 「조항이 요구하는 것」이 18줄로 부푼다.
BLOCK_OPENERS = (">", "- ", "* ", "|", "```")


def clip(text: str) -> str:
    """한 줄로 눕히고 상한에서 자른다. 자르면 **자른 표시를 남긴다**."""
    flat = " ".join(text.split())
    return flat if len(flat) <= MAX_CHARS else flat[:MAX_CHARS] + CUT


@dataclass(frozen=True)
class Grounds:
    """인용 한 건의 근거줄."""

    doc: tuple[str, ...]
    doc_cut: bool
    asserts: tuple[str, ...]
    asserts_cut: bool
    note: str = ""


class SourceIndex:
    """테스트 파일의 원문과 함수 노드. 파일마다 한 번만 읽는다."""

    def __init__(self, root: Path = ROOT) -> None:
        self.root = root
        self._cache: dict[str, tuple[list[str], dict[tuple[str, int], ast.AST]]] = {}

    def _load(self, rel: str) -> tuple[list[str], dict[tuple[str, int], ast.AST]]:
        if rel in self._cache:
            return self._cache[rel]
        path = self.root / rel
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src, filename=str(path))
        except (OSError, SyntaxError):
            # 여기서 삼키는 것은 **근거줄뿐**이다. 인용 자체는 `_citations.collect()`
            # 가 이미 모았고 파싱 결함이면 그쪽이 rc=2 로 멈춘다.
            self._cache[rel] = ([], {})
            return self._cache[rel]
        funcs: dict[tuple[str, int], ast.AST] = {
            (n.name, n.lineno): n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        self._cache[rel] = (src.splitlines(), funcs)
        return self._cache[rel]

    def grounds(self, cite: Citation) -> Grounds:
        """`cite` 를 단 함수의 독스트링 머리와 `assert` 줄."""
        lines, funcs = self._load(cite.path)
        node = funcs.get((cite.func, cite.lineno))
        if node is None:
            return Grounds((), False, (), False,
                           note=f"⚠ 원문에서 `{cite.func}` 를 찾지 못했다 — "
                                f"근거줄을 뜨지 못했다")

        doc_all = [ln.strip() for ln in (ast.get_docstring(node) or "").splitlines()
                   if ln.strip()]
        doc = tuple(clip(ln) for ln in doc_all[:DOC_HEAD_LINES])

        found = sorted(
            (n for n in ast.walk(node) if isinstance(n, ast.Assert)),
            key=lambda n: n.lineno,
        )
        asserts = tuple(
            clip(" ".join(lines[n.lineno - 1:(n.end_lineno or n.lineno)]))
            for n in found[:MAX_ASSERTS]
        )
        return Grounds(doc, len(doc_all) > DOC_HEAD_LINES,
                       asserts, len(found) > MAX_ASSERTS)


def continuation(lines: list[str], index: int) -> list[str]:
    """수용기준 불릿의 **줄바꿈된 뒷부분**.

    `_specparse` 는 선언 줄 **한 줄만** 읽는다 — 추적표 한 칸에 넣을 요약이면 그것
    으로 족하기 때문이다. 그런데 spec 의 긴 조항은 접혀 있고(예: `FR-101-AC5` 는
    네 줄이다), 첫 줄만 내면 **문장이 중간에서 끊긴 채로 판정 근거가 된다.** 「원문
    그대로」가 이 도구의 존재 이유이므로 여기서 이어 붙인다.

    경계는 **형식으로만** 정한다 — 불릿보다 깊이 들여쓴 **연속된 비어 있지 않은
    줄**이되 `BLOCK_OPENERS` 로 시작하지 않는 것까지다. 빈 줄에서도 끊고 새 블록
    에서도 끊으므로, 뒤따르는 인용 블록(`> **신설 사유 …**`)은 빈 줄이 있든 없든
    들어오지 않는다: 그것은 조항 문면이 아니라 옆에 붙인 설명이다.
    """
    base = len(lines[index]) - len(lines[index].lstrip())
    out: list[str] = []
    for line in lines[index + 1:]:
        stripped = line.strip()
        if not stripped or len(line) - len(line.lstrip()) <= base:
            break
        if stripped.startswith(BLOCK_OPENERS):
            break
        out.append(stripped)
    return out


@dataclass(frozen=True)
class ClauseText:
    """조항 하나의 spec 원문. `parent` 는 그 조항이 딸린 요구사항 줄이다."""

    lineno: int
    body: tuple[str, ...]
    parent: tuple[int, str] | None = None

    @property
    def span(self) -> str:
        end = self.lineno + len(self.body) - 1
        return f"{self.lineno}" if end == self.lineno else f"{self.lineno}-{end}"


def clause_sources(spec_path: Path) -> tuple[dict[str, ClauseText], list[str]]:
    """조항 ID → **원문 줄 그대로**. 그리고 spec 파싱 결함.

    유효한 ID 집합은 `parse_spec()` 이 준다 — 여기서는 그 ID 가 **어느 줄에서 왔는지**
    만 찾는다. 같은 ID 가 두 번 보이면 **첫 줄**을 취한다(둘 이상이면 `parse_spec`
    이 「수용기준 ID 중복」 결함으로 이미 보고한다).

    ★ **상위 요구사항 줄을 함께 뜬다.** `NFR-303-M1` 의 문면은 *「오류 메시지 리뷰
    체크리스트」* 뿐이고, 무엇을 재라는 것인지는 상위 `NFR-303` 줄에만 있다. 그것을
    안 뜨면 대조하는 사람이 **기억으로 채우게 되며**, 그것이 이 도구가 막으려는
    바로 그 일이다. §9 보안 표(`SC-N`)는 행 하나가 곧 요구사항이라 상위가 없다.
    """
    reqs, defects = parse_spec(spec_path)
    known = {c.cid for r in reqs for c in r.criteria}

    lines = spec_path.read_text(encoding="utf-8").splitlines()
    out: dict[str, ClauseText] = {}
    parent: tuple[int, str] | None = None
    rid: str | None = None
    for index, line in enumerate(lines):
        lineno = index + 1
        m = REQ_START.match(line)
        if m:
            rid = m.group(1)
            parent = (lineno, line.strip().lstrip("- ").strip())
            continue
        m = CRITERION.match(line)
        if m and rid:
            cid = f"{rid}-{m.group(1)}"
            if cid in known and cid not in out:
                body = (m.group(2).strip(), *continuation(lines, index))
                out[cid] = ClauseText(lineno, body, parent)
            continue
        m = SECURITY_ROW.match(line)
        if m:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            cid = m.group(1)
            if cid in known and cid not in out and len(cells) == 5:
                out[cid] = ClauseText(lineno, (cells[4],), None)
    return out, defects


def render_clause(
    cid: str,
    cites: list[Citation],
    sources: dict[str, ClauseText],
    tests: SourceIndex,
    spec_rel: str,
) -> list[str]:
    """후보 하나의 대장 덩어리."""
    lines = [f"## {cid} — 인용 {len(cites)}건", ""]

    found = sources.get(cid)
    if found is None:
        lines += ["### 조항 문면", "", MISSING_CLAUSE, ""]
    else:
        if found.parent:
            p_lineno, p_text = found.parent
            lines += [f"### 상위 요구사항 — `{spec_rel}:{p_lineno}` (원문 그대로)", "",
                      f"> {p_text}", ""]
        lines += [f"### 조항 문면 — `{spec_rel}:{found.span}` (원문 그대로)", ""]
        lines += [f"> {ln}" for ln in found.body]
        lines += [""]

    lines += ["### 인용", ""]
    for i, c in enumerate(sorted(cites, key=lambda c: (c.path, c.lineno)), 1):
        others = sorted(c.mentions)
        lines.append(f"#### {i}. `{c.path}:{c.lineno}` — `{c.func}`")
        lines.append("")
        lines.append(f"- 이 문면이 적은 조항 ID: "
                     f"{', '.join(f'`{m}`' for m in others) if others else '(없음)'}")
        g = tests.grounds(c)
        if g.note:
            lines += ["", g.note, ""]
            continue
        lines.append("- 독스트링:")
        if g.doc:
            lines += [f"  > {ln}" for ln in g.doc]
            if g.doc_cut:
                lines.append(f"  > {CUT.strip()} (독스트링이 {DOC_HEAD_LINES}줄을 넘는다)")
        else:
            lines.append("  > (없음)")
        lines.append("- `assert` 줄:")
        if g.asserts:
            lines += [f"  - `{ln}`" for ln in g.asserts]
            if g.asserts_cut:
                lines.append(f"  - {CUT.strip()} (`assert` 가 {MAX_ASSERTS}건을 넘는다)")
        else:
            lines.append("  - (없음)")
        lines.append("")
    return lines


def render(
    picked: list[str],
    cited: dict[str, list[Citation]],
    sources: dict[str, ClauseText],
    tests: SourceIndex,
    *,
    spec_rel: str,
    total_cites: int,
    min_citations: int,
    unknown: list[str],
    spec_defects: list[str],
) -> str:
    head = [
        "# 조항 인용 대장 — `scripts/audit_clause_dossier.py`",
        "",
        "⚠ **판정이 아니다.** 대조하는 사람이 볼 원문을 편 것이다 —",
        "**여기 없는 문장을 판정 근거로 쓰지 않는다.**",
        "",
        f"- 인용 있는 조항 {len(cited)}건 · 인용 {total_cites}건",
        f"- 이 대장의 후보: **{len(picked)}건** (인용 {min_citations}건 이상)",
        f"- spec 정본: `{spec_rel}`",
        "",
    ]
    if unknown:
        head += [f"⚠ 인용이 0건이라 대장에 없는 요청 조항: "
                 f"{', '.join(f'`{c}`' for c in unknown)}", ""]
    if spec_defects:
        head += [f"⚠ spec 파싱 결함 {len(spec_defects)}건 — 조항 문면이 빠질 수 있다:", ""]
        head += [f"- {d}" for d in spec_defects[:10]]
        head += [""]
    head += ["## 후보 목록", ""]
    head += [f"{i}. `{cid}` — 인용 {len(cited[cid])}건"
             for i, cid in enumerate(picked, 1)]
    head += [""]

    body: list[str] = []
    for cid in picked:
        body += render_clause(cid, cited[cid], sources, tests, spec_rel)
    return "\n".join(head + body) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="조항 인용 대장 — 후보 조항의 원문과 인용 근거를 편다 (판정 아님)"
    )
    ap.add_argument("--clause", action="append", default=[], metavar="ID",
                    help="대장에 담을 조항 ID. 여러 번 줄 수 있다")
    ap.add_argument("--from-audit", action="store_true",
                    help="`audit_clause_selfreference.py` 의 후보 전건을 담는다")
    ap.add_argument("--min-citations", type=int, default=0, metavar="N",
                    help="인용 N건 이상인 후보만 담는다")
    ap.add_argument("--tests", type=Path, default=DEFAULT_TESTS)
    ap.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    ap.add_argument("--out", type=Path, help="없으면 표준출력")
    args = ap.parse_args()

    if not args.clause and not args.from_audit:
        print("ERROR: `--clause` 또는 `--from-audit` 중 하나가 필요하다 — "
              "무엇을 펼지 정하지 않은 것을 「후보 0건」으로 읽지 않는다", file=sys.stderr)
        return 2

    citations, defects = collect(args.tests)
    if defects:
        print(f"ERROR: 테스트 파싱 결함 {len(defects)}건 — 인용 목록을 믿을 수 없다",
              file=sys.stderr)
        for d in defects[:10]:
            print(f"  {d}", file=sys.stderr)
        return 2
    if not citations:
        print("ERROR: 인용 0건 — 펼 것이 없다", file=sys.stderr)
        return 2

    cited = by_clause(citations)

    picked: list[str] = []
    if args.from_audit:
        picked += [cid for cid, _n, _others in candidates(cited)]
    picked += [cid for cid in args.clause if cid not in picked]

    unknown = sorted(cid for cid in picked if cid not in cited)
    picked = sorted(cid for cid in picked
                    if cid in cited and len(cited[cid]) >= args.min_citations)

    sources, spec_defects = clause_sources(args.spec)
    try:
        spec_rel = args.spec.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        spec_rel = args.spec.as_posix()

    text = render(
        picked, cited, sources, SourceIndex(),
        spec_rel=spec_rel,
        total_cites=len(citations),
        min_citations=args.min_citations,
        unknown=unknown,
        spec_defects=spec_defects,
    )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"대장 {len(picked)}건 → {args.out}")
        for cid in picked:
            print(f"  {cid}  인용 {len(cited[cid])}건")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
