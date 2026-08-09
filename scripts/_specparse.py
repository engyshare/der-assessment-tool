"""spec 파서 — 요구사항·수용기준·Phase 배정표를 읽는다.

**`gen_traceability.py` 에서 갈라 나왔다 (08-08).** §9 보안 조항 파싱을 더하자
그 파일의 **코드 줄 수가 512줄이 되어 NFR-206 상한을 넘겼고**, `--code-strict`
게이트가 그것을 「코드 스프롤」로 차단했다 — 08-08 오전에 내가 켠 게이트다.

**규칙을 고치는 대신 파일을 쪼갠다.** 검사를 통과시키려고 상한을 올리는 것은
이 저장소가 반복해서 경계해 온 유형이고, 조항의 근거(DER-VET `Params.py`
1,830줄)가 겨냥한 것이 정확히 이 상태다.

경계는 **읽기와 쓰기**로 갈랐다 — 여기는 spec 을 자료구조로 바꾸는 데까지,
표를 그리고 테스트 마커를 모으는 것은 `gen_traceability.py` 가 한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

REQ_START = re.compile(r"^- \*\*((?:FR|NFR|UI)-\d+)\*\*\s*(.*)$")

# ── §9 보안 조항 (SC-N) ──────────────────────────────────────────────
#
# **SC 조항은 표로 적혀 있어 08-08까지 추적표 밖에 있었다.** FR·NFR·UI 는
# `- **FR-101**` 형식이라 위 정규식이 잡지만, SC 는 표 행이라 아무것도 잡지
# 않았다. `@pytest.mark.req("SC-8")` 을 달자 생성기가 «실재하지 않는 인용» 으로
# 보고했고 — 검사기는 옳았다 — 그때 조항 8건이 통째로 감시 밖이라는 것이
# 드러났다. **v0.7이 UI·NFR 34건에서 만난 것과 같은 상태다**(*"미매핑 게이트가
# Must-have만 훑으므로 34건이 통째로 감시 밖에 있었다 — 표기 누락 이상의
# 문제다"*).
#
# **수용기준 ID 를 `SC-N` 그대로 쓴다.** `SC-N-AC1` 로 만들면 기존 인용
# (작업 목록 2.3·2.14 등)과 마커가 한꺼번에 무효가 된다. 2.15가 동결한 규약이
# *"키는 저자가 1회 부여하고 동결하는 리터럴"* 이고, `SC-8` 은 이미 그 리터럴
# 이다 — 여기서 파생시키면 규약을 우리가 깬다.
#
# 한 행이 곧 하나의 규범 문장이므로 요구사항과 수용기준이 1:1 인 것도 사실에
# 맞다. FR 처럼 여러 AC 로 갈라야 할 조항이 생기면 그때 표를 쪼갠다.
SECURITY_START = re.compile(r"^## 9\.\s")
SECURITY_ROW = re.compile(r"^\|\s*(?:\*\*)?(SC-\d+)(?:\*\*)?\s*\|")
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
# 들여쓰기를 4칸으로 고정하지 않는 이유: 들여쓰기는 문서의 읽기 구조이지 ID의
# 근거가 아니다. v0.8까지는 표에 딸린 수용기준이 부모 불릿 아래 6칸에 놓여
# 있었고(FR-601-AC2 등), 그 비대칭이 무성 유실을 만들었다 — 2.15 ① 전개로
# 지금은 전건 4칸이지만, 판정은 여전히 오직 `**ACn**` 표기다.
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

# 수용기준 단위 Phase — **줄 끝 `[Phase N]`** 표기만 인정한다.
#
# 왜 필요한가: 자원·편익 레지스트리 표는 행마다 Phase가 다르다(자원 9행이
# Phase 1/2/3 = 6/2/1). 요구사항 단위 Phase만 있으면 전개 후 Phase 2·3 행이
# 전부 "Phase 1 Must-have 미인용"으로 뜨는데, 그것을 다룰 작업은 원리적으로
# 없다(해당 Phase 착수 시 작성). 게이트가 영구히 빨갛게 굳으면 아무도 보지
# 않게 된다 — 이 저장소가 이미 겪은 실패다.
#
# 왜 본문에서 `Phase N`을 찾지 않는가: 산문에 우연히 등장하면 오탐이다.
# 서술과 선언을 **뜻으로** 가르려는 시도는 이 저장소에서 네 번 실패했다.
# 판정 기준은 형식뿐이며, 위치를 줄 끝으로 고정해 우연한 일치를 배제한다.
#
# 표기가 없으면 요구사항의 Phase를 물려받는다 — 대다수 조항이 그렇다.
CRIT_PHASE = re.compile(r"\s*\[Phase (\d)\]\s*$")

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

# 테스트의 조항 마커를 **여기서 정규식으로 읽지 않는다.** 그 일은
# `gen_traceability.py` 가 `ast` 로 한다 (`_marks()` · `_walk_body()`).
#
# 예전에 이 자리에 정규식이 하나 있었고 아무도 쓰지 않았다. 지운 것은 죽은
# 코드여서가 아니라 **그것이 `ast` 수집기보다 덜 잡기 때문**이다 — 인자가
# 하나인 마커만 보고, 모듈 수준 `pytestmark` 와 클래스 상속을 못 보고,
# 문자열로 훑으므로 주석·독스트링의 언급까지 마커로 센다.
#
# 남겨 두면 언젠가 누가 집어 쓴다. 그러면 **매핑이 조용히 줄고**, 매핑표는
# 「검증이 빠졌다」와 「원래 없었다」를 구별해 주지 않는다. 이 저장소가 가장
# 경계하는 상태다.

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
    phase: str = ""      # 빈 값이면 소속 요구사항의 Phase를 물려받는다


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
            body = m.group(2)
            pm = CRIT_PHASE.search(body)
            crit_phase = pm.group(1) if pm else ""
            if pm:
                body = CRIT_PHASE.sub("", body)
            cur.criteria.append(Criterion(cid, summarize(body), kind, crit_phase))
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

    reqs += parse_security(lines, defects)

    for req in reqs:
        if not req.criteria:
            # v0.7까지는 진술 자체를 암묵 AC1로 보충했다. 그 보충이 곧 순번
            # 파생이므로 폐지했다. 진술 자체가 수용기준이라면 그렇게 적어야 한다.
            defects.append(f"{req.rid} 수용기준 0건 — "
                           f"`- Acceptance Criteria:` 아래 `- **AC1** …`을 선언하십시오")

    return reqs, defects


def parse_security(lines: list[str], defects: list[str]) -> list[Requirement]:
    """§9 보안 조항 표를 요구사항으로 읽는다 (SC-1~SC-N).

    표의 열 순서를 **이름으로 찾지 않고 위치로 고정**한다 — 헤더를 신뢰하면
    열을 하나 끼워 넣었을 때 우선순위 자리에서 요구사항 본문을 읽고도 아무
    오류가 나지 않는다. 대신 **열 수가 기대와 다르면 결함으로 보고**한다.
    """
    start = next((i for i, ln in enumerate(lines) if SECURITY_START.match(ln)), None)
    if start is None:
        defects.append("§9 보안 절을 찾지 못했습니다 — SC 조항이 추적표에서 빠집니다")
        return []

    found: list[Requirement] = []
    for offset, line in enumerate(lines[start:], start + 1):
        if line.startswith("## ") and offset - 1 != start:
            break
        if not SECURITY_ROW.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 5:
            defects.append(f"L{offset} §9 표의 열이 5개가 아닙니다 ({len(cells)}개): "
                           f"`ID | 항목 | 우선순위 | Phase | 요구사항` 이어야 합니다")
            continue
        sid, title, priority, phase, body = cells
        sid = clean(sid)
        req = Requirement(rid=sid, title=clean(title),
                          priority=clean(priority), phase=clean(phase))
        # 수용기준 ID 가 요구사항 ID 와 같다 — 위 `SECURITY_ROW` 주석 참조.
        req.criteria.append(Criterion(sid, summarize(body), "ac", ""))
        found.append(req)

    if not found:
        defects.append("§9 에서 SC 조항을 하나도 읽지 못했습니다 — "
                       "표 형식이 바뀌었는지 확인하십시오. 검사를 수행하지 "
                       "못한 것을 통과로 읽지 않습니다 (§13.0.1 ④)")
    return found


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


