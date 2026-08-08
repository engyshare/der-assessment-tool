#!/usr/bin/env python3
"""수용기준 ↔ 검증 항목 추적 매핑표 생성 — spec NFR-107.

무엇을 하는가
-------------
1. spec에서 요구사항(FR/NFR/UI)과 그 수용기준을 추출해 안정적인 ID를 붙인다
2. `Priority:` 줄에 Phase가 없는 요구사항은 **부록 A.1 배정표**에서 채운다
3. tests/ 에서 `@pytest.mark.req("FR-104-AC3")` 마커를 수집한다
4. docs/manual-checks.yaml 에서 수동 검증 항목을 수집한다
5. 셋을 대조하여 docs/traceability.md 를 생성한다
6. Must-have 요구사항에 미매핑 수용기준이 있으면 종료 코드 1

우선순위와 Phase는 **별개 축**이며 §4.0 R-1은 둘 다 요구한다. 그래서 요약에
「Phase 미지정」을 우선순위 미지정과 나란히 집계한다 — 한쪽만 채우고 닫으면
게이트가 초록불이어도 *지금 Phase에서* 지켜졌다는 보장이 되지 않는다.

왜 생성하는가 — 손으로 쓰지 않는 이유
--------------------------------------
매핑표를 수동 유지하면 반드시 spec과 어긋난다. 수용기준이 추가·삭제될 때마다
표를 고쳐야 하는데, 그것을 기억하는 사람은 없다. 어긋난 매핑표는 없느니만
못하다 — "매핑됨"이라고 적혀 있는데 실제로는 검증되지 않는 상태가 되기 때문이다.

그래서 docs/traceability.md 는 **수동 편집 금지**이며 이 스크립트가 정본이다.

수용기준 ID 규약 — **spec이 직접 들고 있다** (v0.8 전환)
--------------------------------------------------------
    - Acceptance Criteria:
      - **AC1** 속성: `name`, `tag`, ...
      - **AC2** 메서드: `capex()`, ...
    - Measurement:
      - **M1** 동일 시나리오 10회 실행 결과 해시 일치

이 스크립트는 **ID를 만들지 않는다. 읽기만 한다.** v0.7까지는 선언 순서에서
ID를 뽑았기 때문에 spec에 수용기준을 중간 삽입하면 이후 번호가 전부 밀렸고,
그때마다 작업 목록 인용과 테스트 마커가 조용히 다른 조항을 가리켰다 —
v0.7에서 실제로 7건 발생했다. 파서를 고쳐서는 막을 수 없는 종류의 사고다.
번호를 문서가 들고 있으면 삽입해도 밀리지 않는다.

번호는 **연속일 필요가 없다.** AC3을 삭제하면 AC1·AC2·AC4로 남는 것이 정상이다.
빈 번호를 메우려고 재배열하면 v0.7의 사고를 그대로 재현하게 된다.

ID 없는 수용기준은 **문서 결함으로 보고하고 종료 코드 2**를 낸다. 조용히
순번을 부여하면 v0.7 이전으로 돌아간다.

사용법
------
    python scripts/gen_traceability.py            # 생성 + 미매핑 검사
    python scripts/gen_traceability.py --check    # 생성하지 않고 검사만 (CI)

의존성: PyYAML
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: PyYAML이 필요합니다 — pip install pyyaml", file=sys.stderr)
    raise SystemExit(2)


REQ_START = re.compile(r"^- \*\*((?:FR|NFR|UI)-\d+)\*\*\s*(.*)$")
PRIORITY = re.compile(r"^  - Priority:\s*\*\*([^*]+)\*\*(.*)$")
BODY_START = re.compile(r"^## 1\. ")
PHASE_IN_PRIORITY = re.compile(r"Phase (\d)")

# 부록 A.1 Must-have Phase 배정표 — `Priority:` 줄에 Phase가 없는 요구사항을 채운다.
#
# 인라인 표기만 읽으면 43건이 공란으로 남는다. 공란은 그 자체로 조용한 구멍이다.
# §4.0 R-1은 우선순위와 Phase를 **둘 다** 요구하는데, 공란이 요약에 집계되지
# 않으면 절반만 채운 상태가 통과로 보인다.
#
# 배정표가 `Priority:` 줄을 **덮어쓰지는 않는다.** 요구사항 자신의 선언이 더
# 가깝고, 둘이 어긋나면 그것 자체가 spec 결함이므로 덮지 않고 보고한다.
APPENDIX_A1 = re.compile(r"^### A\.1\s")
APPENDIX_END = re.compile(r"^## ")
PHASE_ROW = re.compile(r"^\|\s*\*\*(\d+)[^|*]*\*\*\s*\|(.+)$")
REQ_ID = re.compile(r"\b((?:FR|NFR|UI)-\d+)\b")

# 수용기준 선언. **이 한 줄만이 수용기준을 만든다.**
#
# 들여쓰기를 4칸으로 고정하지 않는 이유: 표에 딸린 수용기준은 부모 불릿 아래
# 6칸에 놓인다(FR-601-AC2 등). 들여쓰기는 문서의 읽기 구조이지 ID의 근거가
# 아니므로 여기서 판정에 쓰지 않는다. 판정은 오직 `**ACn**` 표기다.
## 표 수용기준 전개 키 (2.15 ①)
#
# `(표)` 캡션 1건으로 뭉쳐 있던 표를 행 단위 조항으로 가를 때, 각 행은
# `AC1.PV` 처럼 **저자가 부여한 리터럴 키**를 갖는다.
#
# **키는 무엇으로부터도 계산하지 않는다.** 행 위치(`AC1.1`)는 물론이고
# 지표명 슬러그화·대소문자 변환도 파생이다. 파생하는 순간 원본이 바뀔 때
# ID가 조용히 다른 것을 가리키며, 그것이 v0.7에서 7건을 어긋나게 한 구조다.
# 그래서 `PV`는 `pv`로 낮추지 않는다 — 낮추는 것 자체가 파생이다.
KEY = r"[A-Za-z][A-Za-z0-9_-]*"

CRITERION = re.compile(rf"^\s{{2,}}- \*\*(AC\d+(?:\.{KEY})?|M\d+)\*\*\s+(.+)$")

# 수용기준 자리에 있으나 ID 형식이 어긋난 선언.
#
# `BARE_BULLET`은 **4칸 들여쓰기만** 잡는다. 그런데 표에 딸린 수용기준은
# 6칸에 놓인다(FR-601-AC2·AC5, FR-611-AC3, FR-801-AC7). 그 결과 형식이
# 어긋난 선언의 운명이 들여쓰기에 따라 정반대로 갈렸다 —
#
#   4칸: BARE_BULLET에 걸려 결함 보고 → 종료 코드 2 (요란하게 멈춤)
#   6칸: CRITERION에도 BARE_BULLET에도 안 걸려 **그냥 사라짐** (초록불)
#
# 사라진 조항은 미매핑으로도 잡히지 않는다. 조항 자체가 없기 때문이다.
# 통과 화면만 보면 아무 일도 없어 보인다. 이 비대칭을 여기서 닫는다.
MALFORMED_ID = re.compile(r"^\s{2,}- \*\*((?:AC|M)[^*]*)\*\*")

# 수용기준 필드의 머리줄. 선언은 이 줄 뒤에만 온다.
#
# 요구사항 블록 안이라는 조건만으로는 부족하다. 설명이나 나쁜 예로 적은
# `- **AC1** …` 이 수용기준으로 집계되면, 이 저장소에서 네 번 난 사고
# (문서를 설명하는 문장이 그 검사에 걸린다)가 다섯 번째로 반복된다.
#
# 수용기준을 담는 필드는 세 가지뿐이다. 늘리려면 여기에 적어야 하며,
# 적지 않은 필드 아래의 `- **ACn**` 은 결함으로 보고된다 — 어느 필드가
# 수용기준을 담는지를 문서와 도구가 같은 목록으로 알고 있어야 한다.
FIELD_HEADER = re.compile(r"^  - (Acceptance Criteria|Measurement|Validation)\b")

# ID 없는 하위 불릿 — 수용기준 자리에 있으나 번호를 달지 않은 것.
# 조용히 순번을 부여하지 않고 결함으로 보고한다.
BARE_BULLET = re.compile(r"^    - (?!\*\*(?:AC|M)\d+\*\*)(.+)$")

TEST_MARKER = re.compile(r'@pytest\.mark\.req\(\s*["\']([^"\']+)["\']\s*\)')

# 표시용 정리 — 강조·링크·주석을 걷어낸다
CLEAN = [
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
    (re.compile(r"\*([^*]+)\*"), r"\1"),
    (re.compile(r"`([^`]+)`"), r"\1"),
    (re.compile(r"\[\[([^\]]+)\]\]"), r"\1"),
    (re.compile(r"\s+"), " "),
]


@dataclass
class Criterion:
    cid: str
    text: str
    kind: str            # "ac" | "measurement"


@dataclass
class Requirement:
    rid: str
    title: str
    priority: str = "미지정"
    phase: str = "-"
    criteria: list[Criterion] = field(default_factory=list)

    @property
    def is_must(self) -> bool:
        return self.priority.startswith("Must")


def clean(text: str) -> str:
    for pattern, repl in CLEAN:
        text = pattern.sub(repl, text)
    return text.strip(" .")


def summarize(text: str, width: int = 90) -> str:
    text = clean(text)
    # 표 셀 구분자가 남으면 markdown 표가 깨진다
    text = text.replace("|", "/")
    return text if len(text) <= width else text[: width - 1] + "…"


def parse_spec(path: Path) -> tuple[list[Requirement], list[str]]:
    """spec을 읽어 요구사항과 **문서에 적힌** 수용기준 ID를 수집한다.

    ID를 계산하지 않으므로 상태 기계가 거의 없다. 남은 상태는 "지금 수용기준
    필드 안인가" 하나뿐이며, 그것도 설명문이 선언으로 집계되는 것을 막기 위한
    것이지 번호를 세기 위한 것이 아니다.

    결함(defects)은 조용히 보정하지 않고 그대로 돌려준다.
    """
    lines = path.read_text(encoding="utf-8").splitlines()

    start = next((i for i, ln in enumerate(lines) if BODY_START.match(ln)), 0)

    reqs: list[Requirement] = []
    defects: list[str] = []
    cur: Requirement | None = None
    in_field = False

    for offset, line in enumerate(lines[start:], start + 1):
        m = REQ_START.match(line)
        if m:
            cur = Requirement(rid=m.group(1), title=clean(m.group(2)))
            reqs.append(cur)
            in_field = False
            continue

        if cur is None:
            # 요구사항 블록 밖의 선언 — 어디에도 속하지 않는다
            if CRITERION.match(line):
                defects.append(f"L{offset} 요구사항 블록 밖의 수용기준 선언: "
                               f"{line.strip()[:70]}")
            continue

        # 요구사항 블록을 벗어나는 신호
        if line.startswith("#") or (line.startswith("- ") and not REQ_START.match(line)):
            cur, in_field = None, False
            continue

        m = PRIORITY.match(line)
        if m:
            cur.priority = m.group(1).strip()
            ph = (PHASE_IN_PRIORITY.search(m.group(2))
                  or PHASE_IN_PRIORITY.search(m.group(1)))
            if ph:
                cur.phase = ph.group(1)
            continue

        if FIELD_HEADER.match(line):
            in_field = True
            continue

        m = CRITERION.match(line)
        if m:
            if not in_field:
                defects.append(f"L{offset} 수용기준 필드 밖의 선언 ({cur.rid}): "
                               f"{line.strip()[:70]}")
                continue
            cid = f"{cur.rid}-{m.group(1)}"
            if any(c.cid == cid for c in cur.criteria):
                defects.append(f"L{offset} 수용기준 ID 중복: {cid}")
                continue
            kind = "measurement" if m.group(1).startswith("M") else "ac"
            cur.criteria.append(Criterion(cid, summarize(m.group(2)), kind))
            continue

        # ID 형식이 어긋난 선언 — 들여쓰기와 무관하게 잡는다.
        m = MALFORMED_ID.match(line)
        if m and in_field:
            defects.append(f"L{offset} 수용기준 ID 형식 오류 ({cur.rid}): "
                           f"`**{m.group(1)}**` — `AC3` 또는 `AC3.key` 형식이어야 "
                           f"합니다 (key는 `{KEY}`, 점은 한 단계)")
            continue

        # 다른 2칸 필드가 열리면 수용기준 필드는 닫힌다.
        # 닫지 않으면 NFR-103의 `- **경계 정의**:` 같은 후속 필드의 하위 불릿이
        # 수용기준 자리로 오인된다.
        if line.startswith("  - "):
            in_field = False
            continue

        if in_field and BARE_BULLET.match(line):
            defects.append(f"L{offset} ID 없는 수용기준 ({cur.rid}): "
                           f"{line.strip()[:70]}")

    for req in reqs:
        if not req.criteria:
            # v0.7까지는 진술 자체를 암묵 AC1로 보충했다. 그 보충이 곧 순번
            # 파생이므로 폐지했다. 진술 자체가 수용기준이라면 그렇게 적어야 한다.
            defects.append(f"{req.rid} 수용기준 0건 — "
                           f"`- Acceptance Criteria:` 아래 `- **AC1** …`을 선언하십시오")

    return reqs, defects


def parse_phase_appendix(path: Path) -> dict[str, str]:
    """부록 A.1 배정표에서 요구사항 → Phase 를 읽는다.

    한 요구사항이 여러 Phase 행에 나타날 수 있다 — FR-404는 Phase 1(`기본0`)과
    Phase 3(`화폐화 산식`)에, NFR-107은 Phase 0(`게이트 구축`)과 Phase 1
    (`매핑 전건`)에 등장한다. 이때는 **가장 이른 Phase**를 취한다.

    이 값이 쓰이는 곳은 "언제부터 감시 대상인가"이므로, 늦은 쪽을 취하면 그
    사이 기간이 감시 밖으로 빠진다. 반대 방향의 오차는 이르게 잡는 것뿐이다.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((i for i, ln in enumerate(lines) if APPENDIX_A1.match(ln)), None)
    if start is None:
        return {}

    out: dict[str, str] = {}
    for line in lines[start + 1:]:
        if APPENDIX_END.match(line):
            break
        m = PHASE_ROW.match(line)
        if not m:
            continue
        phase = m.group(1)
        # §4.0은 Phase 1·2·3만 정의한다. NFR 배정표의 `0 (Wave 0)` 행은 Phase가
        # 아니라 **착수 시점을 구분하는 Wave 라벨**이며, 표 바로 아래 주석이
        # 그렇게 못박고 있다 — *"Wave 0은 Phase 1 내부의 선행 단계이므로 별도
        # Phase가 아니다. §4.0 R-2 판정상 전건 Phase 1 배정이다."*
        #
        # 이것을 Phase 0으로 읽으면 NFR-107·NFR-208이 본문과 충돌하는 것처럼
        # 보인다. 문서가 스스로 해소해 둔 것을 도구가 다시 벌리는 셈이다.
        if int(phase) == 0:
            phase = "1"
        for rid in REQ_ID.findall(m.group(2)):
            if rid not in out or int(phase) < int(out[rid]):
                out[rid] = phase
    return out


def collect_test_markers(tests_dir: Path) -> dict[str, list[str]]:
    """수용기준 ID → 그것을 검증하는 테스트 파일 목록."""
    mapping: dict[str, list[str]] = {}
    if not tests_dir.is_dir():
        return mapping
    for py in sorted(tests_dir.rglob("*.py")):
        text = py.read_text(encoding="utf-8", errors="replace")
        for cid in TEST_MARKER.findall(text):
            mapping.setdefault(cid, []).append(str(py))
    return mapping


def collect_manual(path: Path) -> tuple[dict[str, dict], list[str]]:
    """수용기준 ID → 수동 검증 항목. 그리고 대상이 없는 항목 목록.

    요구사항 단위가 아니라 **수용기준 단위**로 건다. 요구사항 단위로 걸면
    자동화 가능한 수용기준까지 "수동으로 검증됨"으로 표시되어 커버리지를
    과대 계상한다 — 실제로 FR-1001의 자동 검증 대상 4건이 그렇게 잡혔다.
    """
    if not path.is_file():
        return {}, []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, dict] = {}
    orphan: list[str] = []
    for chk in data.get("checks") or []:
        cid = chk.get("criterion_id")
        if not cid:
            orphan.append(f'{chk["id"]} — criterion_id 없음 (requirement: '
                          f'{chk.get("requirement", "?")})')
            continue
        out[cid] = chk
    return out, orphan


def render(reqs: list[Requirement], tests: dict[str, list[str]],
           manual: dict[str, dict], orphan: list[str],
           spec_name: str) -> tuple[str, list[str]]:
    unmapped: list[str] = []
    rows: list[str] = []

    n_total = n_auto = n_manual = 0
    unprioritized = [r.rid for r in reqs if r.priority == "미지정"]
    unphased = [r.rid for r in reqs if r.phase == "-"]
    unphased_must = [r.rid for r in reqs if r.phase == "-" and r.is_must]

    for req in reqs:
        for i, crit in enumerate(req.criteria):
            n_total += 1
            if crit.cid in tests:
                status = "자동"
                where = ", ".join(Path(p).name for p in tests[crit.cid])
                n_auto += 1
            elif crit.cid in manual:
                chk = manual[crit.cid]
                state = chk.get("status", "미수행")
                verdict = chk.get("verdict")
                status = "수동"
                where = f'{chk["id"]} ({state}{"/" + verdict if verdict else ""})'
                n_manual += 1
            else:
                status = "**미매핑**"
                where = "—"
                if req.is_must:
                    unmapped.append(f"{crit.cid} — {crit.text[:60]}")

            head = f"`{req.rid}`" if i == 0 else ""
            pri = req.priority if i == 0 else ""
            rows.append(
                f"| {head} | {pri} | {req.phase if i == 0 else ''} | "
                f"`{crit.cid}` | {crit.text} | {status} | {where} |")

    must = [r for r in reqs if r.is_must]
    n_unmapped = len(unmapped)

    header = f"""# 수용기준 ↔ 검증 항목 추적 매핑표

> **이 파일은 자동 생성됩니다. 직접 편집하지 마십시오.**
> 생성: `python scripts/gen_traceability.py`
> 입력: `{spec_name}` · `docs/manual-checks.yaml` · `tests/`
> 근거: spec **NFR-107**

## 요약

| 항목 | 수 |
|---|---|
| 요구사항 | {len(reqs)} |
| 그중 Must-have | {len(must)} |
| 수용기준 총계 | {n_total} |
| 자동 검증 매핑 | {n_auto} |
| 수동 검증 매핑 | {n_manual} |
| **Must-have 미매핑** | **{n_unmapped}** |
| 우선순위 미지정 요구사항 | {len(unprioritized)} |
| **Phase 미지정 요구사항** | **{len(unphased)}** |

"""

    if unprioritized:
        header += f"""> **우선순위 미지정 {len(unprioritized)}건 — spec 결함입니다.**
>
> `{", ".join(unprioritized)}`
>
> spec §4.0 R-1은 *"모든 요구사항은 우선순위와 Phase를 둘 다 가진다"* 를 요구하고,
> `spec 작성 시 원칙` 1-A도 같습니다. 위 요구사항에는 `Priority:` 줄이 없습니다.
>
> **이것은 표기 누락 이상입니다.** 미매핑 게이트는 Must-have만 대상으로 하므로,
> 우선순위가 없는 요구사항은 **검사에서 조용히 빠집니다.** 위 {len(unprioritized)}건의
> 수용기준은 지금 아무도 지키지 않아도 CI가 알려주지 않습니다.

"""

    if unphased:
        header += f"""> **Phase 미지정 {len(unphased)}건 — §4.0 R-1 위반입니다.**
>
> `{", ".join(unphased)}`
>
> 그중 **Must-have {len(unphased_must)}건**{" — `" + ", ".join(unphased_must) + "`" if unphased_must else ""}
>
> 우선순위(중요도)와 Phase(시점)는 별개 축이며 §4.0 R-1은 **둘 다** 요구합니다.
> `Priority:` 줄의 인라인 표기와 부록 A.1 배정표 어느 쪽에서도 찾지 못했습니다.
> 부록 A.1은 **Must-have만** 등재하는 표이므로, 위 목록이 전부 Should-have 이하라면
> 그 표의 「미배정 0건」 표기와 모순되지 않습니다.
>
> **둘의 긴급도는 다릅니다.** Must-have가 여기 있으면 미매핑 게이트가 그 수용기준을
> 감시하면서도 *언제까지* 지켜야 하는지는 말하지 못하는 상태입니다. Should-have만
> 남았다면 R-1 정비 사항이며 게이트 판정에는 영향이 없습니다.

"""

    if orphan:
        header += f"""> **대상이 없는 검증 항목 {len(orphan)}건 — 매달린 참조입니다.**
>
{chr(10).join("> · " + o for o in orphan)}
>
> 이 항목들은 **아무것도 검증하지 않습니다.** 수용기준이 삭제되었거나 ID가
> 밀렸는데 참조를 갱신하지 않은 상태이며, 요구사항 쪽에서는 그냥 `미매핑`으로만
> 보이므로 원인이 드러나지 않습니다.
>
> `criterion_id` 누락이라면 지정하십시오. 요구사항 단위로 걸면 자동화 가능한
> 수용기준까지 "수동으로 검증됨"으로 표시되어 커버리지가 과대 계상됩니다.

"""

    if n_unmapped:
        header += f"""> **미매핑 {n_unmapped}건.** NFR-107은 미매핑 0건을 요구합니다.
>
> 현재 저장소에 테스트가 없으므로 전건 미매핑인 것이 정상입니다. 이 표는
> **Wave 0 시점의 작업 목록**으로 읽으십시오 — 각 행이 곧 작성해야 할 테스트
> 하나입니다. 구현이 진행되면서 `자동`으로 채워집니다.
>
> 테스트에 `@pytest.mark.req("FR-104-AC3")` 마커를 달면 이 표에 반영됩니다.

"""
    else:
        header += "> **미매핑 0건.** NFR-107 충족.\n\n"

    header += """## 매핑

| 요구사항 | 우선순위 | Phase | 수용기준 | 내용 | 검증 | 위치 |
|---|---|---|---|---|---|---|
"""

    body = "\n".join(rows)

    tail = """

## ID 규약

ID는 **spec이 직접 들고 있습니다.** 이 표를 만드는 스크립트는 읽기만 하며
번호를 부여하지 않습니다.

```markdown
  - Acceptance Criteria:
    - **AC1** 속성: `name`, `tag`, ...
    - **AC2** 메서드: `capex()`, ...
  - Measurement:
    - **M1** 동일 시나리오 10회 실행 결과 해시 일치
```

그래서 수용기준을 **중간에 삽입해도 이후 ID가 밀리지 않습니다.** v0.7까지는
선언 순서에서 ID를 뽑았기 때문에 삽입 한 번에 이후 번호가 전부 밀렸고, 작업
목록 인용과 테스트 마커가 조용히 다른 조항을 가리켰습니다(실제 7건).

**번호는 연속일 필요가 없습니다.** AC3을 삭제하면 AC1·AC2·AC4로 남는 것이
정상입니다. 빈 번호를 메우려고 재배열하면 그 사고를 그대로 재현합니다.

표(table)로 기술된 수용기준은 표 앞의 **`(표)` 캡션 줄이 ID를 가지며, 표
전체를 1건**으로 셉니다. 행 단위로 나누려면 캡션을 행별 선언으로 바꾸고
인용처를 함께 갱신하십시오.

## 수동 검증

자동화할 수 없는 수용기준은 `docs/manual-checks.yaml` 에 등재하고 여기서
`수동`으로 표시합니다. 수행 이력(일자·수행자·표본·결과)이 없으면 `미수행`이며,
Phase DoD 판정 시 미수행 건수를 확인합니다.

수동 등재는 예외이지 도피처가 아닙니다. 등재 기준과 제외 사유는
`manual-checks.yaml` 머리말에 있습니다.
"""

    return header + body + tail, unmapped


def main() -> int:
    repo = Path(__file__).resolve().parent.parent

    ap = argparse.ArgumentParser(description="수용기준 추적 매핑표 생성 (NFR-107)")
    ap.add_argument("--spec", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=repo / "docs/traceability.md")
    ap.add_argument("--manual", type=Path, default=repo / "docs/manual-checks.yaml")
    ap.add_argument("--tests", type=Path, default=repo / "tests")
    ap.add_argument("--check", action="store_true",
                    help="파일을 쓰지 않고 미매핑 여부만 검사한다 (CI)")
    args = ap.parse_args()

    spec_path = args.spec
    if spec_path is None:
        candidates = sorted((repo / "rslt").glob("spec-*.md"))
        if len(candidates) != 1:
            print(f"ERROR: spec을 특정할 수 없습니다 ({len(candidates)}건)", file=sys.stderr)
            return 2
        spec_path = candidates[0]

    reqs, defects = parse_spec(spec_path)
    if defects:
        # 결함이 있으면 표를 만들지 않는다. 결함을 안은 채 생성된 표는
        # "매핑됨"과 "누락"을 뒤섞어 보고하므로 없느니만 못하다.
        print(f"ERROR: spec 수용기준 선언 결함 {len(defects)}건", file=sys.stderr)
        for d in defects:
            print(f"  · {d}", file=sys.stderr)
        print("\n수용기준 ID는 spec이 직접 들고 있어야 합니다 — "
              "`- **AC3** …` 형식. 순번을 자동 부여하지 않습니다.", file=sys.stderr)
        return 2

    # 부록 A.1 배정표로 Phase 공란을 채운다. `Priority:` 줄이 이미 말한 것은
    # 덮지 않고, 어긋나면 spec 결함으로 보고한다 — 같은 사실이 두 곳에서 다르게
    # 적혀 있다는 뜻이므로 조용히 한쪽을 고르면 안 된다.
    appendix = parse_phase_appendix(spec_path)
    conflicts: list[str] = []
    for req in reqs:
        assigned = appendix.get(req.rid)
        if assigned is None:
            continue
        if req.phase == "-":
            req.phase = assigned
        elif req.phase != assigned:
            conflicts.append(
                f"{req.rid} — 본문 Priority 줄 Phase {req.phase} / "
                f"부록 A.1 Phase {assigned}")

    tests = collect_test_markers(args.tests)
    manual, orphan = collect_manual(args.manual)

    # 매달린 참조 검사 — 대장이나 테스트 마커가 없는 수용기준을 가리키는 경우.
    #
    # 이것을 검사하지 않으면 조용히 무효가 된다. 수용기준이 삭제되거나 ID가
    # 밀렸을 때 해당 수동 항목·테스트 마커는 아무것도 덮지 않게 되는데,
    # 요구사항 쪽은 그냥 "미매핑"으로 보이므로 원인이 드러나지 않는다.
    known = {c.cid for r in reqs for c in r.criteria}
    for cid, chk in sorted(manual.items()):
        if cid not in known:
            orphan.append(f'{chk["id"]} — 수용기준 {cid} 가 spec에 없음 '
                          f'(삭제되었거나 ID가 밀렸습니다)')
    for cid in sorted(set(tests) - known):
        orphan.append(f'테스트 마커 {cid} — 해당 수용기준이 spec에 없음 '
                      f'({", ".join(Path(p).name for p in tests[cid])})')

    content, unmapped = render(reqs, tests, manual, orphan, spec_path.name)

    if not args.check:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(content, encoding="utf-8")
        # 저장소 밖 경로(--out으로 임시 파일을 지정하는 음성 테스트 등)에서도
        # 죽지 않아야 한다. relative_to()는 subpath가 아니면 ValueError를 낸다.
        try:
            shown = args.out.relative_to(repo)
        except ValueError:
            shown = args.out
        print(f"생성: {shown}")

    n_crit = sum(len(r.criteria) for r in reqs)
    n_unphased = sum(1 for r in reqs if r.phase == "-")
    print(f"요구사항 {len(reqs)}건 / 수용기준 {n_crit}건 / "
          f"자동 {len(tests)}건 / 수동 {len(manual)}건 / "
          f"Phase 미지정 {n_unphased}건")

    if conflicts:
        print(f"Phase 표기 충돌 {len(conflicts)}건 — 본문과 부록 A.1이 다릅니다")
        for c in conflicts:
            print(f"  · {c}")

    if orphan:
        print(f"수동 대장 대상 없음 {len(orphan)}건 — criterion_id 누락")
        for o in orphan:
            print(f"  · {o}")

    if unmapped:
        print(f"Must-have 미매핑 {len(unmapped)}건")
        for line in unmapped[:10]:
            print(f"  · {line}")
        if len(unmapped) > 10:
            print(f"  … 외 {len(unmapped) - 10}건")
        return 1

    print("미매핑 0건 — NFR-107 충족")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
