#!/usr/bin/env python3
"""정본(定本) 규칙 문서 대조 — spec §16.5.3 절차 1~2b 구현.

대조 5종
--------
1. 정본 해시            정본 파일이 lock 기록 이후 바뀌었는가
2. 저장소 사본 동일성   docs/ 사본이 정본과 바이트 동일한가
3. 앵커 실재            spec이 인용하는 좌표가 정본에 아직 있는가
4. spec↔lock 인용 정합  본문 인용과 lock 앵커 목록이 일치하는가 (원칙·제목 양방향)
5. 폐지 좌표 인용       정본이 폐기한 하위 절 번호(2.1 등)를 쓰고 있지 않은가

`mtime`·`size_bytes`는 **판본 식별 기록이며 대조 대상이 아니다.** 판정의
근거는 sha256뿐이다. 다만 `--update` 는 셋을 함께 갱신한다 — 해시만 고치면
기록이 다른 판본을 가리키게 된다.

1과 4는 서로 다른 방향의 표류를 잡는다.
  - 1은 "정본이 움직였다"     — 남이 바꾼 것
  - 4는 "spec이 움직였다"     — 내가 인용을 추가/삭제하고 lock을 안 고친 것
둘 다 없어야 통과다.

해시가 같으면 3은 자동으로 참이다. 그래도 검사하는 이유는 lock을 갱신하는
사람이 해시만 바꾸고 앵커 목록을 방치하는 경우를 잡기 위해서다.

정본을 어디서 읽는가
--------------------
정본은 Obsidian 볼트에 있고 저장소에는 없다. 따라서 실행 환경에 따라 다르다.

  로컬  볼트가 있으면 볼트의 정본을 읽는다 (권위 있는 검사)
  CI    볼트가 없으면 저장소 사본(docs/*.md)을 읽는다

저장소 사본은 정본과 **바이트 동일**해야 한다. 동기화 메타데이터(정본 경로·
일자·해시)는 사본 안의 머리말이 아니라 이 lock 파일에 둔다. 사본에 머리말을
넣으면 해시가 달라져 CI에서 대조가 불가능해진다 (§16.5.3 절차 5).

종료 코드
---------
  0  통과
  1  표류 감지
  2  설정 오류 — lock 파일 없음, 정본·사본 모두 없음 등

표류를 경고로 볼지 차단으로 볼지는 **호출 측이 정한다** (워크플로의
continue-on-error, pre-commit 훅의 처리 방식). 스크립트가 가진 레버는 종료
코드뿐이므로 여기서 둘을 구분할 방법이 없다.

사용법
------
  python scripts/check_source_rules.py
  python scripts/check_source_rules.py --lock docs/source-rules.lock --spec rslt/spec-*.md
  python scripts/check_source_rules.py --update      # 표류를 lock에 반영 (검토 후 커밋)


의존성: PyYAML
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: PyYAML이 필요합니다 — pip install pyyaml", file=sys.stderr)
    raise SystemExit(2) from None


# ── spec 본문 추출 규칙 ────────────────────────────────────────────────
# §16.5.3 절차 2b — 본문만 스캔하고 변경 요약·정정 이력은 제외한다.
# 그 블록들은 "무엇이 폐기되었는지"를 기록하는 곳이므로 폐기된 앵커를
# 인용하는 것이 정상이며, 포함하면 영구 오탐이 된다.

BODY_START = re.compile(r"^## 1\. ")
EXCLUDED_SECTION = re.compile(r"^#{2,4} .*(변경 요약|정정 이력|Revision History)")
ANY_HEADING = re.compile(r"^#{1,6} ")
FENCE = re.compile(r"^\s*```")

PRINCIPLE = re.compile(r"원칙 \d-\d")

# 폐지된 하위 절 번호 인용 판별.
#
# spec은 자기 자신의 절도 §N.M 으로 참조하므로(§16.5.3, §7.2 …) 패턴만으로는
# 구분할 수 없다. 정본 출처 표지 **바로 옆**에 붙은 §N.M 만 정본 인용으로 본다.
# 인용은 관례상 표지에 인접하며, 멀리 떨어진 §는 거의 항상 spec 자기 참조다.
#
# 창(window)을 두지 않고 "같은 줄에 표지가 있으면 위반"으로 하면
# 파생 관계표 같은 줄에서 오탐이 난다 — 실제로 그렇게 잡혔다.
ADJACENCY_WINDOW = 40
SUBSECTION = re.compile(r"§\d+\.\d+")

# 도메인 정본을 가리키는 출처 표지. §16.5.2가 허용한 형식과 일치해야 한다.
#
# **두 검사가 이 집합을 공유한다** — 인용 수집(cited_principles)과
# 폐지 좌표 검출(deprecated_citations). 따로 두었더니 실제로 어긋났다:
# 인용 수집은 "도메인 원칙"을 인정하는데 폐지 검출은 위키링크만 봐서,
# `도메인 원칙 §2.4` 가 탐지를 빠져나갔다. spec §13.2가 실제로 쓰는 표기다.
DOMAIN_MARKERS = ("[[분산자원 경제성 평가 원칙]]", "도메인 원칙")


@dataclass
class Finding:
    level: str          # "DRIFT" | "ERROR" | "INFO"
    source: str
    message: str
    detail: str = ""


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, level: str, source: str, message: str, detail: str = "") -> None:
        self.findings.append(Finding(level, source, message, detail))

    @property
    def drifted(self) -> bool:
        return any(f.level in ("DRIFT", "ERROR") for f in self.findings)


def anchor_parts(anchor) -> tuple[str, str]:
    """앵커 항목을 (spec 표기, 정본에서 찾을 문자열)로 푼다.

    두 형식을 지원한다.
      "원칙 5-1"                              — spec 표기와 정본 문자열이 같음
      {label: "5절", match: "## 5. 수치…"}    — 다름. 절 인용이 대표적이다
                                                spec은 "5절", 정본 제목은 "## 5. …"
    """
    if isinstance(anchor, dict):
        return anchor["label"], anchor["match"]
    return anchor, anchor


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_body(spec_text: str) -> str:
    """spec 본문만 남긴다 — 변경 요약·정정 이력·코드펜스 제외."""
    lines = spec_text.splitlines()

    start = next((i for i, ln in enumerate(lines) if BODY_START.match(ln)), None)
    if start is None:
        raise ValueError("spec 본문 시작(## 1. ...)을 찾지 못했습니다")

    kept: list[str] = []
    skipping_section = False
    skip_depth = 0
    in_fence = False

    for line in lines[start:]:
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            # 코드 블록 — lock YAML 예시 등이 들어 있어 인용으로 세지 않는다
            continue

        if ANY_HEADING.match(line):
            depth = len(line) - len(line.lstrip("#"))
            if EXCLUDED_SECTION.match(line):
                skipping_section, skip_depth = True, depth
                continue
            if skipping_section and depth <= skip_depth:
                skipping_section = False

        if not skipping_section:
            kept.append(line)

    return "\n".join(kept)


# 원칙 번호는 문서 간에 충돌한다.
#   분산자원 경제성 평가 원칙 : 원칙 1-1 ~ 7-5
#   spec 작성 시 원칙         : 원칙 1-A ~ 8-4
# 두 문서가 19개 토큰을 공유한다 (2-1, 4-3, 7-2 …). 따라서 `원칙 N-M` 만으로는
# 어느 문서를 가리키는지 판정할 수 없다 — 정본이 문서 안에서 경고한 충돌과
# 같은 것이 문서 사이에서 일어난다.
#
# 판정: 같은 줄에 출처 표지가 있어야 그 문서의 인용으로 센다.
# 도메인 표지는 위 DOMAIN_MARKERS 를 공유한다.
PROCESS_MARKERS = ("spec 작성 시 원칙",)


def cited_principles(body: str) -> tuple[set[str], list[tuple[int, str]]]:
    """도메인 정본을 가리키는 원칙 인용과, 출처가 모호한 인용을 함께 돌려준다."""
    domain: set[str] = set()
    ambiguous: list[tuple[int, str]] = []

    for n, line in enumerate(body.splitlines(), 1):
        tokens = PRINCIPLE.findall(line)
        if not tokens:
            continue
        if any(m in line for m in DOMAIN_MARKERS):
            domain.update(tokens)
        elif any(m in line for m in PROCESS_MARKERS):
            continue  # 프로세스 규칙 인용 — 이 lock의 대상이 아니다
        else:
            ambiguous.append((n, line.strip()))

    return domain, ambiguous


def deprecated_citations(body: str, markers: list[str]) -> list[tuple[int, str]]:
    """정본 출처 표지에 인접한 §N.M 인용을 찾는다 (폐지된 좌표계).

    spec 자기 참조(§7.2, §16.5.3 …)를 걸러내기 위해 인접성을 요구한다.
    표지 집합은 인용 수집과 **동일해야 한다** — 다르면 한쪽만 인정하는 표기가
    탐지 사각이 된다.
    """
    hits: list[tuple[int, str]] = []
    for n, line in enumerate(body.splitlines(), 1):
        spans = [(m.start(), m.end()) for w in markers
                 for m in re.finditer(re.escape(w), line)]
        if not spans:
            continue
        for sub in SUBSECTION.finditer(line):
            near = any(
                # 링크 뒤 창 안 / 링크 앞 창 안
                0 <= sub.start() - end <= ADJACENCY_WINDOW
                or 0 <= start - sub.end() <= ADJACENCY_WINDOW
                for start, end in spans
            )
            if near:
                hits.append((n, line.strip()))
                break
    return hits


def resolve_source(entry: dict, vault_root: Path, repo_root: Path,
                   report: Report) -> tuple[Path | None, str]:
    """정본 실물 경로를 정한다. 볼트 우선, 없으면 저장소 사본."""
    name = entry["path"]

    vault_file = vault_root / name
    if vault_file.is_file():
        return vault_file, "vault"

    copy_rel = entry.get("repo_copy")
    if copy_rel:
        copy_file = repo_root / copy_rel
        if copy_file.is_file():
            report.add("INFO", name,
                       "볼트 미접근 — 저장소 사본으로 대조",
                       f"{copy_rel} (사본은 정본과 바이트 동일해야 한다)")
            return copy_file, "repo_copy"

    report.add("ERROR", name, "정본과 저장소 사본 모두 없음",
               f"볼트: {vault_file}\n사본: {copy_rel or '(미지정)'}")
    return None, "missing"


def check_repo_copy(entry: dict, vault_hash: str, report: Report) -> None:
    """저장소 사본이 정본과 바이트 동일한지 확인한다 (§16.5.3 절차 5).

    사본에 머리말을 넣거나 직접 손대면 여기서 걸린다. 사본이 정본과 다르면
    볼트 없는 환경(CI)의 대조가 무의미해지므로, 사본 자체가 검사 대상이다.
    """
    name = entry["path"]
    copy_rel = entry.get("repo_copy")
    if not copy_rel:
        return

    repo_root = Path(__file__).resolve().parent.parent
    copy_file = repo_root / copy_rel

    if not copy_file.is_file():
        report.add("DRIFT", name, f"저장소 사본 없음: {copy_rel}",
                   "볼트에 접근할 수 없는 환경(CI)에서는 대조가 불가능합니다. "
                   "정본을 그대로 복사하십시오 (§16.5.3 절차 5).")
        return

    copy_hash = sha256_of(copy_file)
    if copy_hash != vault_hash:
        report.add("DRIFT", name, f"저장소 사본이 정본과 다름: {copy_rel}",
                   f"정본 {vault_hash}\n"
                   f"사본 {copy_hash}\n"
                   "사본은 정본과 **바이트 동일**해야 합니다. 머리말을 넣지 마십시오 — "
                   "동기화 메타데이터는 lock에 둡니다.\n"
                   "개정은 정본에서만 합니다. 사본을 고치면 정본이 둘이 됩니다.")
    else:
        report.add("INFO", name, f"저장소 사본 동기 ({copy_rel})")


def check_source(entry: dict, path: Path, origin: str, report: Report) -> str | None:
    """해시·앵커·제목을 검사하고 실제 해시를 돌려준다."""
    name = entry["path"]
    text = path.read_text(encoding="utf-8")
    actual = sha256_of(path)
    expected = entry["sha256"]

    if actual != expected:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC).astimezone()
        if origin == "vault":
            headline = "해시 불일치 — 정본이 개정되었습니다"
            action = "§16.5.1 파생 관계표를 따라 영향 FR을 재검토하십시오."
        else:
            # 정본을 못 읽었으므로 둘 중 어느 쪽인지 여기서는 판정할 수 없다.
            headline = "해시 불일치 — 정본 개정 또는 사본 오염"
            action = ("볼트에 접근 가능한 환경에서 재실행하여 구분하십시오.\n"
                      "  정본과 사본이 같다  → 정본이 개정된 것\n"
                      "  정본과 사본이 다르다 → 사본을 직접 고친 것 "
                      "(§16.5.3 — 사본은 읽기 전용, 개정은 정본에서만)")
        report.add("DRIFT", name, headline,
                   f"lock   {expected}\n"
                   f"실제   {actual}\n"
                   f"현재 mtime {mtime.isoformat(timespec='seconds')}\n"
                   f"읽은 곳   {origin} — {path}\n"
                   f"{action}")
    else:
        report.add("INFO", name, f"해시 일치 ({origin})", expected[:16] + "…")

    # 볼트로 검사했더라도 저장소 사본을 따로 확인한다.
    # 하지 않으면 사본 오염이 로컬에서 영영 드러나지 않고, CI에서만
    # "정본 개정"으로 오인되어 나타난다 — 진단이 한 단계 늦어진다.
    if origin == "vault":
        check_repo_copy(entry, actual, report)

    for anchor in entry.get("cited_anchors") or []:
        label, needle = anchor_parts(anchor)
        if needle not in text:
            extra = "" if label == needle else f' (spec 표기 "{label}")'
            report.add("DRIFT", name, f"인용 앵커 소실: {needle}{extra}",
                       "spec이 인용하는 좌표가 정본에서 사라졌습니다. "
                       "§16.5.1 파생 관계표를 따라 영향 FR을 재검토하십시오.")

    for heading in entry.get("cited_headings") or []:
        if heading not in text:
            report.add("DRIFT", name, f"인용 제목 소실: {heading}",
                       "원칙 번호가 없어 제목 전문으로 인용한 대상입니다 "
                       "(§16.5.2 3순위). 제목 변경에 취약한 지점입니다.")

    return actual


def check_citation_sync(lock: dict, body: str, report: Report) -> None:
    """spec 본문의 인용과 lock 앵커 목록이 일치하는지 (양방향)."""
    locked: set[str] = set()
    for entry in lock["sources"]:
        for anchor in entry.get("cited_anchors") or []:
            label, _ = anchor_parts(anchor)
            if PRINCIPLE.fullmatch(label):
                locked.add(label)

    cited, ambiguous = cited_principles(body)

    for _, line in ambiguous:
        report.add("DRIFT", "spec", "출처가 모호한 원칙 인용",
                   f"{line[:160]}\n"
                   "두 규칙 문서가 원칙 번호 19개를 공유하므로 문서 표지 없는 "
                   "`원칙 N-M`은 어느 문서인지 판정할 수 없습니다. "
                   "[[분산자원 경제성 평가 원칙]] / '도메인 원칙' / "
                   "'spec 작성 시 원칙' 중 하나를 같은 줄에 명시하십시오 (§16.5.2).")

    for missing in sorted(cited - locked):
        report.add("DRIFT", "spec ↔ lock",
                   f"spec이 인용하나 lock에 없음: {missing}",
                   "인용을 추가하고 lock을 갱신하지 않았습니다. "
                   "이 앵커는 정본 개정 시 감시되지 않습니다.")

    for stale in sorted(locked - cited):
        report.add("DRIFT", "spec ↔ lock",
                   f"lock에 있으나 spec이 인용하지 않음: {stale}",
                   "인용을 삭제하고 lock을 갱신하지 않았습니다. "
                   "불필요한 감시 대상입니다.")

    if cited == locked:
        report.add("INFO", "spec ↔ lock",
                   f"인용 정합 — 원칙 앵커 {len(cited)}건 양방향 일치")

    # 제목 앵커도 같은 양방향 검사를 받아야 한다.
    #
    # v0.6 초판은 제목 앵커를 "정본에 있는가"만 봤다. 그러면 spec이 인용을
    # 지워도 lock에 남아, 감시 대상이 실제 인용과 어긋난다. 원칙 앵커는
    # 양방향인데 제목만 단방향이면 비대칭 자체가 결함이다.
    locked_headings: set[str] = set()
    for entry in lock["sources"]:
        locked_headings |= set(entry.get("cited_headings") or [])

    for heading in sorted(locked_headings):
        if heading not in body:
            report.add("DRIFT", "spec ↔ lock",
                       f"lock에 있으나 spec이 인용하지 않는 제목: {heading}",
                       "인용을 삭제하고 lock을 갱신하지 않았습니다. "
                       "불필요한 감시 대상입니다.")

    if locked_headings and all(h in body for h in locked_headings):
        report.add("INFO", "spec ↔ lock",
                   f"제목 앵커 {len(locked_headings)}건 양방향 일치")


def check_deprecated(lock: dict, body: str, report: Report) -> None:
    # 정본 위키링크 + DOMAIN_MARKERS. 인용 수집과 같은 집합을 써야 한다.
    markers = sorted({
        *(e["wikilink"] for e in lock["sources"] if e.get("wikilink")),
        *DOMAIN_MARKERS,
    })
    hits = deprecated_citations(body, markers)
    for _, line in hits:
        report.add("DRIFT", "spec", "폐지된 하위 절 번호 인용",
                   f"{line[:160]}\n"
                   "정본이 하위 절 번호를 폐지했습니다 "
                   "(사유: '2.1'과 '원칙 2-1' 충돌). §16.5.2에 따라 "
                   "원칙 번호 또는 제목 전문으로 인용하십시오.")
    if not hits:
        report.add("INFO", "spec", "폐지 좌표 인용 없음")


def update_lock(lock_path: Path, updates: dict[str, dict]) -> None:
    """판본 기록 3종(sha256·mtime·size_bytes)을 제자리 치환한다.

    주석과 서식을 보존해야 하므로 YAML을 다시 쓰지 않고 줄 단위로 편집한다.
    `updates`는 {정본 path: {sha256, mtime, size_bytes}} 형태다.

    **세 값을 함께 갱신한다.** 해시만 고치면 mtime·size가 낡아 다른 판본을
    가리키게 된다. 대조 대상은 해시뿐이지만, 기록이 틀리면 "언제 것인가"를
    사람이 판단할 때 오도한다 — 없느니만 못한 기록이 된다.
    """
    # newline="" 로 열어 개행 변환을 끈다. 끄지 않으면 Windows에서 파일 전체가
    # CRLF로 재작성되어, 세 줄만 바뀌었는데 diff가 전부 바뀐 것으로 보인다.
    # 변경 검토를 불가능하게 만들므로 lock 갱신에서는 치명적이다.
    with lock_path.open("r", encoding="utf-8", newline="") as fh:
        lines = fh.readlines()

    out: list[str] = []
    cur: dict | None = None

    for line in lines:
        m = re.match(r'^(\s*)- path:\s*"([^"]+)"', line)
        if m:
            cur = updates.get(m.group(2))
            out.append(line)
            continue

        if cur:
            m2 = re.match(r'^(\s*)(sha256|mtime|size_bytes):\s*(.*?)(\r?\n?)$', line)
            if m2:
                indent, key, eol = m2.group(1), m2.group(2), m2.group(4)
                val = cur[key]
                rendered = val if key == "size_bytes" else f'"{val}"'
                out.append(f"{indent}{key}: {rendered}{eol}")
                continue

        out.append(line)

    with lock_path.open("w", encoding="utf-8", newline="") as fh:
        fh.write("".join(out))


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent

    ap = argparse.ArgumentParser(description="정본 규칙 문서 대조 (spec §16.5.3)")
    ap.add_argument("--lock", type=Path, default=repo_root / "docs/source-rules.lock")
    ap.add_argument("--spec", type=Path, default=None,
                    help="기본값: rslt/ 의 spec-*.md 중 유일한 것")
    ap.add_argument("--vault", type=Path, default=None,
                    help="lock의 vault_root 를 덮어씀")
    ap.add_argument("--update", action="store_true",
                    help="해시 표류를 lock에 반영한다. 앵커 표류는 반영하지 않는다")
    args = ap.parse_args()

    if not args.lock.is_file():
        print(f"ERROR: lock 파일 없음 — {args.lock}", file=sys.stderr)
        return 2

    lock = yaml.safe_load(args.lock.read_text(encoding="utf-8"))

    spec_path = args.spec
    if spec_path is None:
        candidates = sorted((repo_root / "rslt").glob("spec-*.md"))
        if len(candidates) != 1:
            print(f"ERROR: spec 파일을 특정할 수 없습니다 ({len(candidates)}건). "
                  "--spec 으로 지정하십시오.", file=sys.stderr)
            return 2
        spec_path = candidates[0]

    if not spec_path.is_file():
        print(f"ERROR: spec 파일 없음 — {spec_path}", file=sys.stderr)
        return 2

    # 볼트 경로는 사람마다 다르고 저장소가 공개되므로 lock에 박지 않는다.
    # 우선순위: --vault > 환경변수 > lock. 어느 것도 없으면 저장소 사본으로
    # 대조하며, 그 사실은 리포트에 INFO로 남는다.
    vault_root = Path(args.vault
                      or os.environ.get("DER_VAULT_ROOT")
                      or lock.get("vault_root", ""))
    report = Report()

    try:
        body = extract_body(spec_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    pending: dict[str, dict] = {}
    for entry in lock["sources"]:
        path, origin = resolve_source(entry, vault_root, repo_root, report)
        if path is None:
            continue
        actual = check_source(entry, path, origin, report)
        if actual and actual != entry["sha256"]:
            if origin != "vault":
                # 사본으로 읽은 값으로 lock을 갱신하면, 사본 오염을 정본
                # 개정으로 굳혀 버린다. 볼트에서만 갱신한다.
                report.add("INFO", entry["path"],
                           "--update 대상 아님 — 볼트로 읽지 않았습니다",
                           "볼트에 접근 가능한 환경에서 갱신하십시오.")
                continue
            st = path.stat()
            pending[entry["path"]] = {
                "sha256": actual,
                "mtime": datetime.fromtimestamp(st.st_mtime, UTC)
                                 .astimezone().isoformat(timespec="seconds"),
                "size_bytes": st.st_size,
            }

    check_citation_sync(lock, body, report)
    check_deprecated(lock, body, report)

    # ── 출력 ──────────────────────────────────────────────────────────
    print(f"정본 대조 — lock {args.lock.name} / spec {spec_path.name}")
    print(f"볼트 {vault_root}")
    print("─" * 72)

    for f in report.findings:
        mark = {"DRIFT": "✗", "ERROR": "!", "INFO": "·"}[f.level]
        print(f"{mark} [{f.source}] {f.message}")
        if f.detail:
            for line in f.detail.splitlines():
                print(f"    {line}")

    print("─" * 72)

    if not report.drifted:
        print("통과 — 정본과 spec이 정합합니다")
        return 0

    n = sum(1 for f in report.findings if f.level in ("DRIFT", "ERROR"))
    print(f"표류 {n}건 감지")

    if args.update and pending:
        update_lock(args.lock, pending)
        print(f"\nlock의 판본 기록 {len(pending)}건을 갱신했습니다 "
              f"(sha256 · mtime · size_bytes).")
        print("경고: 판본 기록만 갱신했습니다. 다음을 수동으로 수행하십시오 —")
        print("  1. §16.5.1 파생 관계표를 따라 영향 FR 전수 재검토")
        print("  2. 정본 어휘 변경 시 DB enum·UI 라벨·테스트 픽스처까지 추적")
        print("  3. cited_anchors 목록 재확인")
        print("  4. 저장소 사본 동기화")
        print("  검토 없이 커밋하지 마십시오. 그러면 이 장치가 무의미해집니다.")

    print("\n조치: spec §16.5.3 절차 3~5")
    # 표류는 항상 1을 돌려준다. **경고로 볼지 차단으로 볼지는 호출 측이 정한다** —
    # 워크플로의 continue-on-error, pre-commit 훅의 처리 방식 등.
    # 스크립트가 가진 유일한 레버가 종료 코드이므로 여기서 둘을 구분할 방법이
    # 없다. v0.6 초판의 --strict 플래그는 양쪽 분기가 같은 값을 돌려주는
    # 죽은 코드였다.
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
