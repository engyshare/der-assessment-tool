#!/usr/bin/env python3
"""작업 목록의 수용기준 인용 검사 — NFR-107 보조.

왜 필요한가
-----------
`gen_traceability.py`는 인용 ID가 **실재하는지**만 본다. 실재하지만 **엉뚱한
조항**을 가리키는 경우는 잡지 못한다. 그 상태로 테스트에
`@pytest.mark.req("FR-601-AC3")`을 붙이면:

  · 엉뚱한 조항(AC3)이 "검증됨"으로 보고되고
  · 정작 검증한 조항(AC4)은 미매핑으로 남으며
  · 둘 다 아무도 이상을 눈치채지 못한다

NFR-107이 막으려던 상태를 게이트가 통과시킨다. **spec 개정으로 AC가 중간에
삽입되면 이후 번호가 전부 밀리므로 이 사고는 개정 때마다 재발한다.**
v0.7에서 실제로 발생했다 — 34건 우선순위 부여로 AC가 삽입되어 작업 목록의
인용 7건이 다른 조항을 가리켰다.

검사 3종 — 기계가 확실히 판정할 수 있는 것만
--------------------------------------------
1. **범위 초과**   `FR-501-AC1`~`AC4` 인용인데 해당 FR에 AC가 3개뿐인 경우
2. **미인용 조항** Phase 1 Must-have 수용기준 중 어느 작업도 인용하지 않는 것
                   → 인용이 엉뚱한 곳으로 갔을 때 **비어 버린 자리**가 드러난다
3. **중복 인용**   같은 조항을 서로 다른 상위 작업이 인용 → 오귀속 의심

**어휘 유사도는 쓰지 않는다.** 시도했으나 한국어 조사·복합어 때문에 올바른
매핑도 0.00으로 나와 오탐 100%였다. 사람이 읽지 않게 되는 도구는 없느니만
못하다. 대신 `--review`로 인용 쌍을 나란히 찍어 사람이 훑게 한다.

사용법
------
    python scripts/check_task_mapping.py            # 검사 3종
    python scripts/check_task_mapping.py --review   # 인용 쌍 전건 대조 출력
    python scripts/check_task_mapping.py --fr FR-601  # 특정 FR의 AC 목록

종료 코드: 0 통과 / 1 의심 존재 / 2 설정 오류
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

# 표 수용기준 전개(2.15 ①)로 생긴 `FR-102-AC1.PV` 형식을 함께 받는다.
# 키는 저자가 부여한 리터럴이며 대소문자를 구분한다 — `PV`를 `pv`로 낮추는 것도
# 파생이므로 하지 않는다. 점은 한 단계까지만이다.
CITE = re.compile(r"`((?:FR|NFR|UI)-\d+-(?:AC|M)\d+(?:\.[A-Za-z][A-Za-z0-9_-]*)?)`")
RANGE = re.compile(r"`((?:FR|NFR|UI)-\d+)-(AC|M)(\d+)`\s*~\s*`?(?:AC|M)?(\d+)`?")

# 작업 항목 식별.
#   - **5.7** [I] …        일반 하위 작업
#   - **6.0.S1** [T] …     공통 단계 (6.0처럼 반복 절차를 갖는 상위 작업)
#   1. [T] …               번호 목록으로 쓴 절차
#
# `\d+\.\d+` 만 받으면 `6.0.S1`이 걸리지 않는다. 그러면 그 아래 수용기준 줄이
# **직전에 열린 다른 작업**에 붙어 오귀속이 생긴다 — 실제로 6.0 공통 단계의
# 인용이 전부 5.7(규제 프로파일)로 집계됐다. 도구가 잡으라고 만든 오귀속을
# 도구가 만들어내던 상태다.
TASK_LINE = re.compile(r"^- \*\*([\d.]+(?:S\d+)?)\*\*\s*(?:\[[TIR]\])?\s*(.*)$")
NUMBERED = re.compile(r"^(\d+)\.\s+(?:\[[TIR]\])?\s*(.+)$")
PARENT = re.compile(r"^## ([\d.]+) ")

# 인용은 `- 수용기준:` 필드에서만 수집한다.
#
# 들여쓴 줄이면 무엇이든 인용으로 세면, **조항을 언급하는 서술**과 **그 조항을
# 검증하겠다는 선언**이 구분되지 않는다. 둘은 다른 행위다.
#
# 실제로 2.15의 "ID가 바뀌므로 FR-102-AC1·FR-401-AC2… 를 함께 갱신해야 한다"는
# 서술이 2.0의 인용으로 집계되어 유령 중복 5건을 만들었다. 검사 도구를
# 설명하는 문장이 검사에 걸린 것이며, 같은 유형이 이 프로젝트에서 세 번째다
# (spec §16.5.2 나쁜 예 리터럴, 작업 목록 범위 초과 예시, 그리고 이것).
#
# 문서가 이미 `- 수용기준:` 필드 관례를 지키므로 수집을 그 필드로 한정한다.
# `~` 범위 표기도 이 필드에만 나타나므로 RANGE 처리에 영향이 없다.
CRITERION_FIELD = re.compile(r"^\s*- 수용기준\s*:")
TR_ROW = re.compile(r"^\|\s*(?:`([A-Z]+-\d+)`)?\s*\|([^|]*)\|([^|]*)\| `([^`]+)`[^|]*\| ([^|]*)\|")

# 형식 이탈 선언 검출.
#
# 인용 수집을 `- 수용기준:` 필드로 한정한 대가가 있다. **형식이 어긋난 선언은
# 집계에서 통째로 빠지고**, 그 조항은 아무도 검증하지 않는 것처럼 보인다.
# 실제로 6.6의 하위 단계 2건이 블록인용 안에 콜론 없이 적혀 있어
# `FR-106-AC2`~`AC6`이 「미인용 Must-have」 오탐 5건이 되어 있었다.
# 없던 인용을 만드는 오류가 아니라 **있는 인용을 지우는** 오류이므로,
# 통과 화면만 봐서는 영영 드러나지 않는다.
#
# 서술과 선언을 뜻으로 가르려 하지 않는다 — 그 시도가 이 저장소에서 네 번
# 실패했다. 판정 기준은 **형식뿐**이고, 표준 형식이 아니면 사람이 본다.
STRAY_HINT = re.compile(r"수용기준")


def load_criteria(path: Path):
    """{cid: (본문, 소속 요구사항, 우선순위, Phase)}"""
    out = {}
    cur = pri = ph = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        m = TR_ROW.match(line)
        if not m:
            continue
        # 우선순위는 요구사항 단위라 첫 행에만 있고 이후 조항이 물려받는다.
        # **Phase는 수용기준 단위**이므로 행마다 다시 읽는다 — 물려받게 두면
        # 자원·편익 레지스트리처럼 행별 Phase가 다른 표에서, Phase 2·3 조항이
        # 전부 Phase 1로 취급되어 미인용 오탐이 된다.
        if m.group(1):
            cur, pri = m.group(1), m.group(2).strip()
        ph = m.group(3).strip() or ph
        out[m.group(4)] = (m.group(5).strip(), cur, pri, ph)
    return out


def load_tasks(path: Path):
    """[(상위, 하위, 텍스트, [인용 ID])]"""
    tasks = []
    parent = "?"
    cur = None

    def flush():
        nonlocal cur
        if cur:
            tasks.append(cur)
            cur = None

    for line in path.read_text(encoding="utf-8").splitlines():
        p = PARENT.match(line)
        if p:
            # **섹션 경계에서 반드시 닫는다.** 닫지 않으면 다음 섹션의
            # 들여쓴 줄이 이전 섹션의 마지막 작업에 계속 붙는다.
            flush()
            parent = p.group(1)
            continue

        m = TASK_LINE.match(line) or NUMBERED.match(line)
        if m:
            flush()
            cur = [parent, m.group(1), m.group(2), CITE.findall(m.group(2)), line]
            continue

        if cur and line.startswith("  "):
            cur[4] += "\n" + line
            if CRITERION_FIELD.match(line):
                cur[3].extend(CITE.findall(line))
    flush()
    return tasks


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="작업 목록 수용기준 인용 검사")
    ap.add_argument("--tasks", type=Path, default=None)
    ap.add_argument("--traceability", type=Path, default=repo / "docs/traceability.md")
    ap.add_argument("--review", action="store_true", help="인용 쌍 전건 대조 출력")
    ap.add_argument("--fr", help="특정 요구사항의 수용기준 목록 출력")
    args = ap.parse_args()

    if not args.traceability.is_file():
        print(f"ERROR: 매핑표 없음 — {args.traceability}", file=sys.stderr)
        return 2
    crit = load_criteria(args.traceability)

    if args.fr:
        for cid, (body, req, _, _) in crit.items():
            if req == args.fr:
                print(f"  {cid}  {body[:110]}")
        return 0

    tf = args.tasks
    if tf is None:
        cands = sorted((repo / "rslt").glob("task-*.md"))
        if len(cands) != 1:
            print(f"ERROR: 작업 목록을 특정할 수 없습니다 ({len(cands)}건)", file=sys.stderr)
            return 2
        tf = cands[0]
    tasks = load_tasks(tf)

    # 검사 대상 텍스트도 `- 수용기준:` 필드로 한정한다.
    # 파일 전체를 쓰면 서술 문장의 언급이 "인용됨"으로 세어져 **미인용 건수를
    # 실제보다 낮게** 보고한다 — 유령 중복과 같은 원인, 반대 방향의 오류다.
    raw = "\n".join(
        ln for ln in tf.read_text(encoding="utf-8").splitlines()
        if CRITERION_FIELD.match(ln)
    )

    print(f"작업 목록  {tf.name}")
    print("─" * 78)

    if args.review:
        for parent, tid, text, cites, _ in tasks:  # noqa: B007 — tid 는 아래 분기에서 쓰인다
            if not cites:
                continue
            print(f"\n[{tid}] {text.strip()[:88]}")
            for cid in dict.fromkeys(cites):
                body, req, _, _ = crit.get(cid, ("(없음)", "", "", ""))
                print(f"    {cid:16} {body[:88]}")
        return 0

    problems = 0

    # ── 0. 형식 이탈 선언 ───────────────────────────────────────────
    stray = [
        (n, ln.strip())
        for n, ln in enumerate(tf.read_text(encoding="utf-8").splitlines(), 1)
        if STRAY_HINT.search(ln) and CITE.search(ln) and not CRITERION_FIELD.match(ln)
    ]
    if stray:
        print(f"· 형식 이탈 인용 의심 {len(stray)}건 "
              f"— 표준형은 `  - 수용기준: \\`FR-106-AC1\\`~\\`AC4\\``")
        print("    이 줄들의 인용은 **집계에 들어가지 않는다.** 선언이라면 표준형으로 고치고, "
              "서술이라면 그대로 두십시오")
        for n, ln in stray:
            print(f"    L{n}  {ln[:96]}")
        print()
    else:
        print("· 형식 이탈 인용 없음")

    # ── 1. 범위 초과 ────────────────────────────────────────────────
    counts = defaultdict(int)
    for _cid, (_, req, _, _) in crit.items():
        counts[req] += 1
    over = []
    for req, kind, lo, hi in RANGE.findall(raw):  # noqa: B007 — kind 는 아래 집합 생성에 쓰인다
        if int(hi) > counts.get(req, 0):
            over.append((req, lo, hi, counts.get(req, 0)))
    if over:
        problems += len(over)
        print(f"✗ 범위 초과 인용 {len(over)}건")
        for req, lo, hi, n in over:
            print(f"    {req}-AC{lo}~AC{hi} 인용 — 실제 수용기준 {n}건뿐")
    else:
        print("· 범위 초과 인용 없음")

    cited = set(CITE.findall(raw))
    for req, kind, lo, hi in RANGE.findall(raw):
        cited |= {f"{req}-{kind}{n}" for n in range(int(lo), int(hi) + 1)}

    # ── 1b. 실재하지 않는 조항 인용 ─────────────────────────────────
    #
    # 어느 도구도 **인용된 ID가 실제로 존재하는지**를 보지 않았다. 범위 초과
    # 검사는 범위 표기의 상한만 세고, 미인용 검사는 실재 조항 쪽을 순회하므로
    # 유령 인용은 양쪽 시야 밖이다. gen_traceability는 수동 대장과 테스트
    # 마커에 대해서만 실재 검사를 한다 — 작업 목록은 대상이 아니었다.
    #
    # 표 수용기준을 행 단위로 가르면(2.15 ①) 부모 ID가 폐기되면서 수십 개의
    # 인용이 한 번에 갈 곳을 잃는다. 그때 드러나는 유일한 신호가 「미인용 N건」
    # 인데, 그것은 "아직 새 ID를 안 붙였다"로도 읽혀 원인이 가려진다.
    # 폐기된 ID를 가리키는 인용은 **조용히 무효**가 되므로 여기서 이름을 준다.
    ghost = sorted(cited - set(crit))
    if ghost:
        problems += len(ghost)
        print(f"\n✗ 실재하지 않는 수용기준 인용 {len(ghost)}건")
        print("    작업 목록이 인용하는 ID가 spec에 없다 — 폐기되었거나 오타다")
        for cid in ghost:
            print(f"    {cid}")
        print()
    else:
        print("· 실재하지 않는 인용 없음")

    # ── 2. 미인용 Phase 1 Must-have 조항 ────────────────────────────
    uncited = [(cid, body, req) for cid, (body, req, pri, ph) in crit.items()
               if pri.startswith("Must") and ph in ("1", "-") and cid not in cited]
    if uncited:
        problems += len(uncited)
        print(f"\n✗ 미인용 Must-have 수용기준 {len(uncited)}건")
        print("    인용이 엉뚱한 조항으로 갔을 때 **비어 버린 자리**가 여기 드러난다")
        by_req = defaultdict(list)
        for cid, body, req in uncited:
            by_req[req].append((cid, body))
        for req in sorted(by_req):
            print(f"  {req}")
            for cid, body in by_req[req]:
                print(f"    {cid:16} {body[:82]}")
    else:
        print("· 미인용 Must-have 수용기준 없음")

    # ── 3. 상위 작업 간 중복 인용 ───────────────────────────────────
    owner = defaultdict(set)
    for parent, _tid, _, cites, _ in tasks:
        for cid in cites:
            owner[cid].add(parent)
    dup = {c: p for c, p in owner.items() if len(p) > 1}
    if dup:
        print(f"\n· 상위 작업 간 중복 인용 {len(dup)}건 (오귀속 의심 — 정당할 수도 있다)")
        for cid, parents in sorted(dup.items()):
            print(f"    {cid:16} {' / '.join(sorted(parents))}")

    print("─" * 78)
    if problems:
        print(f"의심 {problems}건 — `--review`로 인용 쌍을 대조하십시오")
        return 1
    print("통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
