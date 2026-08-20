import re
import sys
from pathlib import Path

import _specparse

# `NFR-402` 안의 `FR-402` 를 삼키지 않으려는 왼쪽 경계 (R21 처방).
# `\b` 는 `N`·`F` 사이(둘 다 단어문자)에는 경계를 만들지 않으므로
# `NFR-` 접두 뒤의 `FR-` 를 정확히 막는다 — `(?<!N)` 과 실측으로 대조해 골랐다
# (`.orch/R39/result_scan_boundary.md` §1-b).
FR_COL_BOUNDARY = re.compile(r"\bFR-")


def expand_ranges(text: str) -> list[str]:
    results = []
    parts = re.findall(r'(?:[A-Z]+-\d+~\d+|[A-Z]+-\d+)', text)
    for part in parts:
        m = re.match(r'([A-Z]+)-(\d+)~(\d+)', part)
        if m:
            prefix, start, end = m.groups()
            for i in range(int(start), int(end)+1):
                results.append(f"{prefix}-{i}")
        else:
            results.append(part)
    return results


def build_assigned_to(lines: list[str]) -> dict[str, list[str]]:
    """§16.3 구획표 줄들에서 `{FR-ID: [WP, ...]}` 를 뽑는다.

    `_specparse` 와 무관하게 원문 줄만 본다 — 합성 입력으로 이 함수 하나만
    떼어 검사할 수 있게 한다.
    """
    in_table = False
    assigned_to: dict[str, list[str]] = {}

    for line in lines:
        if line.startswith("### 16.3"):
            in_table = True
            continue
        if in_table and line.startswith("## ") and not line.startswith("### "):
            break

        if in_table and line.startswith("|") and "WP-" in line:
            cells = [c.strip() for c in line.split("|")]
            if len(cells) < 5:
                continue

            wp_col = cells[1]
            if "WP-" not in wp_col:
                continue

            m_wp = re.search(r'WP-\d+[a-z]?', wp_col)
            if not m_wp:
                continue
            wp = m_wp.group(0)

            if len(cells) > 5 and FR_COL_BOUNDARY.search(cells[3]):
                fr_col = cells[3]
                frs = expand_ranges(fr_col)
                for fr in frs:
                    if fr.startswith("FR-"):
                        assigned_to.setdefault(fr, []).append(wp)

    return assigned_to


def main():
    spec_path = Path(sys.argv[1] if len(sys.argv) > 1 else "rslt/spec-분산특구-경제성평가.md")
    reqs, _defects = _specparse.parse_spec(spec_path)

    phases = _specparse.parse_phase_appendix(spec_path)
    for req in reqs:
        if req.rid in phases:
            req.phase = phases[req.rid]

    must_phase1_frs = {
        r.rid for r in reqs
        if r.rid.startswith("FR-") and r.is_must and str(r.phase) == "1"
    }

    lines = spec_path.read_text(encoding="utf-8").splitlines()
    assigned_to = build_assigned_to(lines)

    errors = 0
    # Spec defects that WP-15 cannot fix (rslt/ is read-only)
    # R9/WP-20C: FR-611/FR-101/FR-1103 배정을 §16.3에서 고쳐 해소했다 — 셋 다
    # 근거가 있어 지웠다 (판정 근거: .orch/R9-WP20C-대장.md). 목록이 빈 것과
    # 「검사를 안 하는 것」을 구별하려고 빈 집합을 그대로 남긴다.
    known_missing: set[str] = set()
    known_dups: set[str] = set()

    for fr in sorted(must_phase1_frs):
        if fr not in assigned_to:
            if fr in known_missing:
                print(f"[경고] 알려진 spec 결함 (무시됨) - 미배정: {fr}")
            else:
                print(f"미배정: {fr}")
                errors += 1

    for fr, wps in assigned_to.items():
        if len(wps) > 1 and fr in must_phase1_frs:
            if fr in known_dups:
                print(f"[경고] 알려진 spec 결함 (무시됨) - 중복 배정: {fr} -> {', '.join(wps)}")
            else:
                print(f"중복 배정: {fr} -> {', '.join(wps)}")
                errors += 1

    if errors:
        sys.exit(1)

    print("Phase 1 Must-have FR 중 미배정 0건 · 중복 배정 0건 확인 완료")

if __name__ == "__main__":
    main()
