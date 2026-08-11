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
import ast
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: PyYAML이 필요합니다 — pip install pyyaml", file=sys.stderr)
    raise SystemExit(2) from None


from _specparse import (
    Requirement,
    parse_phase_appendix,
    parse_spec,
)


def _attr_path(node) -> str:
    """`pytest.mark.req` 같은 점 표기를 문자열로 되돌린다."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _marks(decorators) -> tuple[list[str], bool]:
    """데코레이터 목록에서 (req 인용 ID들, manual 표기 여부)."""
    reqs: list[str] = []
    manual = False
    for d in decorators:
        target = d.func if isinstance(d, ast.Call) else d
        name = _attr_path(target)
        if not name.startswith("pytest.mark."):
            continue
        kind = name.split(".")[-1]
        if kind == "manual":
            manual = True
        elif kind == "req" and isinstance(d, ast.Call):
            for a in d.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    reqs.append(a.value)
    return reqs, manual


def _walk_body(body, inherited_reqs: list[str], inherited_manual: bool,
               path: str, mapping: dict[str, list[tuple[str, bool]]]) -> None:
    """클래스·함수를 훑어 마커를 모은다.

    파일 루프 안에 중첩 함수로 두지 않는 이유: 루프 변수를 클로저로 잡으면
    (ruff B023) 나중에 지연 호출로 바뀌는 순간 **마지막 파일의 경로가 전
    항목에 붙는다.** 지금은 즉시 호출이라 문제가 없지만, 그 사실은 코드
    어디에도 적혀 있지 않아 다음 사람이 안전하게 고칠 수 없다.
    """
    for node in body:
        if isinstance(node, ast.ClassDef):
            r, m = _marks(node.decorator_list)
            _walk_body(node.body, inherited_reqs + r,
                       inherited_manual or m, path, mapping)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            r, m = _marks(node.decorator_list)
            for cid in inherited_reqs + r:
                mapping.setdefault(cid, []).append((path, inherited_manual or m))


def collect_test_markers(tests_dir: Path) -> tuple[dict[str, list[tuple[str, bool]]], list[str]]:
    """수용기준 ID → [(테스트 파일, manual 표기 여부)]. 그리고 파싱 결함.

    **`@pytest.mark.manual` 을 함께 읽는다 (NFR-107-AC1.manual).**

    v0.9까지 이 함수는 `@pytest.mark.req` 만 정규식으로 긁었다. 그 결과
    `manual` 로 skip 처리된 **명세 스텁**이 매핑표에 `자동`으로 표시됐다 —
    아무것도 실행하지 않는 테스트가 "실행·통과 확인" 칸에 앉는 것이며,
    `NFR-107-AC1.manual`(실행하지 않고 매핑 존재만 확인)과
    `NFR-107-AC4`(자동/수동 구분 표시)를 동시에 위반한다.

    표 수용기준이 `AC1` 한 건으로 뭉쳐 있는 동안은 자동 쪽이 채워져
    조항 전체가 충족된 것처럼 보였다. 2.15 ① 전개로 `AC1.manual` 이
    독립 ID를 얻자 이 구멍이 미매핑으로 드러났고, 여기서 닫는다.

    **정규식이 아니라 `ast` 로 읽는 이유**: 두 마커가 *같은 테스트에*
    붙었는지를 판정해야 한다. 파일 단위 정규식으로는 파일 어딘가에
    `manual` 이 있다는 것만 알 뿐, 그것이 이 `req` 의 짝인지 알 수 없다.
    클래스 데코레이터와 모듈 `pytestmark` 도 상속시킨다 — pytest가
    그렇게 동작하므로 도구도 같아야 한다.
    """
    mapping: dict[str, list[tuple[str, bool]]] = {}
    defects: list[str] = []
    if not tests_dir.is_dir():
        return mapping, defects

    for py in sorted(tests_dir.rglob("*.py")):
        text = py.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError as e:
            # 조용히 건너뛰면 그 파일의 마커가 통째로 사라지고, 해당
            # 수용기준은 "아무도 검증하지 않는 것"처럼 보인다. 있는 인용을
            # 지우는 오류이므로 결함으로 보고한다.
            defects.append(f"{py.name} 파싱 실패 (L{e.lineno}) — "
                           f"이 파일의 마커가 집계에서 통째로 빠집니다: {e.msg}")
            continue

        # 모듈 수준 pytestmark = [...] 도 전 테스트에 걸린다
        mod_reqs: list[str] = []
        mod_manual = False
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
                items = node.value.elts if isinstance(node.value, (ast.List, ast.Tuple)) \
                    else [node.value]
                r, m = _marks(items)
                mod_reqs += r
                mod_manual = mod_manual or m

        _walk_body(tree.body, mod_reqs, mod_manual, str(py), mapping)

    return mapping, defects


RECORD_FIELDS = ("performed_at", "performed_by", "result_note")


def collect_manual(path: Path) -> tuple[dict[str, dict], list[str], list[str], list[str]]:
    """수용기준 ID → 수동 검증 항목. 그리고 세 종류의 결함 목록.

    요구사항 단위가 아니라 **수용기준 단위**로 건다. 요구사항 단위로 걸면
    자동화 가능한 수용기준까지 "수동으로 검증됨"으로 표시되어 커버리지를
    과대 계상한다 — 실제로 FR-1001의 자동 검증 대상 4건이 그렇게 잡혔다.

    반환: (criterion_id → 항목, 대상 없는 항목, blocking_dod 칸 누락,
    수행 기록 불완전).

    뒤의 둘은 **대장 전건**에 건다 — `blocking_dod` 를 읽는 코드가 하나도
    없으면 사람이 적은 "이건 차단이다"가 기계에는 주석과 같다(WP-24C).
    """
    if not path.is_file():
        return {}, [], [], []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, dict] = {}
    orphan: list[str] = []
    missing_blocking: list[str] = []
    incomplete: list[str] = []
    for chk in data.get("checks") or []:
        chk_id = chk["id"]
        if "blocking_dod" not in chk:
            missing_blocking.append(
                f'{chk_id} — blocking_dod 칸이 없음 (requirement: '
                f'{chk.get("requirement", "?")})')
        if chk.get("status") == "수행":
            missing_fields = [f for f in RECORD_FIELDS if not chk.get(f)]
            for f in missing_fields:
                incomplete.append(f'{chk_id} — status=수행인데 {f} 기록 없음')

        cid = chk.get("criterion_id")
        if not cid:
            orphan.append(f'{chk_id} — criterion_id 없음 (requirement: '
                          f'{chk.get("requirement", "?")})')
            continue
        out[cid] = chk
    return out, orphan, missing_blocking, incomplete


def _file_list(paths: list[str]) -> str:
    """검증 테스트 칸. **같은 파일이 여러 번이면 「N건」으로 접는다.**

    한 파일에 그 조항의 마커가 N개 있으면 N번 반복해 적고 있었다. 조항 하나를
    파일 하나가 여러 테스트로 검증하는 것은 흔하므로 반복 자체는 정보이지만,
    나열은 정보를 가린다 — R19 에 `FR-803-AC1` 이 **같은 파일명 13회**가 되어
    칸 하나가 표의 다른 행 전체보다 길어졌다.

    접으면 **몇 개가 검증하는가가 오히려 드러난다.** 1회는 접지 않는다 —
    「1건」은 없는 정보를 더하는 것이고, 기존 형식과도 어긋난다.

    곱셈기호(`×`)를 쓰지 않는 이유: `ruff` 의 `RUF001` 이 라틴 `x` 와 혼동될 수
    있다고 막는다. 괄호도 쓰지 않는다 — 같은 칸에서 `(스텁)`·`(미수행)` 이 이미
    **다른 뜻**으로 괄호를 쓰고 있어 형식이 겹친다.
    """
    counts: dict[str, int] = {}
    for path in paths:
        name = Path(path).name
        counts[name] = counts.get(name, 0) + 1
    return ", ".join(
        name if n == 1 else f"{name} {n}건" for name, n in counts.items()
    )


def render(reqs: list[Requirement], tests: dict[str, list[str]],
           manual: dict[str, dict], orphan: list[str],
           spec_name: str, *,
           blocking_unperformed: list[tuple[str, dict]] = ()
           ) -> tuple[str, list[str]]:
    unmapped: list[str] = []
    rows: list[str] = []

    n_total = n_auto = n_manual = 0
    # `manual` 스텁으로만 매핑됐는데 대장에 수행 기록이 없는 조항.
    # AC1.manual 은 스텁을 매핑 형식으로 인정하지만, AC3 은 수행 일자·수행자·
    # 결과를 대장에 남기라고 한다. 스텁만 있고 대장에 없으면 **매핑은 있으나
    # 수행 기록이 원리상 생길 수 없는 상태**이며, 그대로 두면 "수동으로
    # 검증됨"이 영원히 미수행을 가린다.
    stub_without_record: list[str] = []
    unprioritized = [r.rid for r in reqs if r.priority == "미지정"]
    unphased = [r.rid for r in reqs if r.phase == "-"]
    unphased_must = [r.rid for r in reqs if r.phase == "-" and r.is_must]

    for req in reqs:
        for i, crit in enumerate(req.criteria):
            n_total += 1
            if crit.cid in tests:
                entries = tests[crit.cid]
                # 하나라도 실행되는 테스트가 있으면 자동이다. 전부 manual
                # 표기면 실행되지 않으므로 자동으로 셀 수 없다.
                auto_hits = [p for p, is_manual in entries if not is_manual]
                if auto_hits:
                    status = "자동"
                    where = _file_list(auto_hits)
                    n_auto += 1
                else:
                    status = "수동"
                    files = _file_list([p for p, _ in entries])
                    n_manual += 1
                    chk = manual.get(crit.cid)
                    if chk:
                        state = chk.get("status", "미수행")
                        verdict = chk.get("verdict")
                        where = (f'{files} (스텁) + {chk["id"]} '
                                 f'({state}{"/" + verdict if verdict else ""})')
                    else:
                        where = f"{files} (스텁 — **수행 기록 없음**)"
                        stub_without_record.append(f"{crit.cid} — {files}")
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
            # Phase는 **모든 행에** 찍는다. 첫 행에만 찍으면 수용기준 단위
            # Phase가 표에서 표현되지 않고, 이 표를 읽는 check_task_mapping이
            # 요구사항 Phase를 이후 조항에 그대로 물려 버린다 — 행별 Phase가
            # 도구에 도달하지 못하던 원인이 바로 이것이다.
            rows.append(
                f"| {head} | {pri} | {crit.phase or req.phase} | "
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
| **차단 미수행 (판정불가)** | **{len(blocking_unperformed)}** |

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
        must_note = f" — `{', '.join(unphased_must)}`" if unphased_must else ""
        header += f"""> **Phase 미지정 {len(unphased)}건 — §4.0 R-1 위반입니다.**
>
> `{", ".join(unphased)}`
>
> 그중 **Must-have {len(unphased_must)}건**{must_note}
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

    if blocking_unperformed:
        rows_bd = "\n".join(
            f"> · `{cid}` — {chk['id']} ({chk.get('status', '미수행')})"
            for cid, chk in blocking_unperformed)
        header += f"""> **차단 미수행(판정불가) {len(blocking_unperformed)}건.**
> `blocking_dod: true` 인 수동 검사가 아직 수행되지 않았습니다. Phase DoD
> 판정에서 이 항목들은 **"충족"이 아니라 "판정불가"** 로 셉니다.
>
> CI는 이 때문에 실패하지 않습니다 — 실패시키면 사람이 수행할 때까지 CI가
> 영구히 빨간불이 되며, 그것은 `manual-checks.yaml` 머리말이 스스로 막으려는
> 두 상황 중 하나입니다. 대신 Phase 완료 판정을 사람이 이 목록을 보고
> 내려야 합니다.
>
{rows_bd}

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

표 수용기준은 **행 단위로 전개되어 있습니다** (2.15 ①, spec v0.9). 각 행은
`FR-102-AC1.PV` 처럼 `<기존AC>.<키>` 형식이며, 키는 **저자가 1회 부여하고
동결하는 리터럴**입니다 — 행 위치도 슬러그화도 대소문자 변환도 파생이므로
쓰지 않습니다(`PV`를 `pv`로 낮추는 것 자체가 파생입니다). 점은 한 단계까지입니다.

**수용기준을 만드는 것은 `- **AC…**` 불릿 줄뿐입니다.** `|` 로 시작하는 표
행은 읽지 않으므로, 표에 ID 열을 넣어도 조항이 생기지 않습니다. 새 표를
수용기준으로 쓰려면 선언 불릿 목록으로 적으십시오.

행마다 Phase가 다르면 줄 끝에 `[Phase N]` 을 답니다. 표기가 없는 조항은
요구사항의 Phase를 물려받습니다.

## 수동 검증

자동화할 수 없는 수용기준은 `docs/manual-checks.yaml` 에 등재하고 여기서
`수동`으로 표시합니다. 수행 이력(일자·수행자·표본·결과)이 없으면 `미수행`이며,
Phase DoD 판정 시 미수행 건수를 확인합니다.

수동 등재는 예외이지 도피처가 아닙니다. 등재 기준과 제외 사유는
`manual-checks.yaml` 머리말에 있습니다.

각 항목은 `blocking_dod` 칸을 갖습니다 — 미수행이면 Phase 완료를 막아야
하는가를 사람이 미리 표시한 값입니다. `true` 이고 아직 수행되지 않았으면
위 요약과 "차단 미수행" 절에 **판정불가**로 표기됩니다. "충족"과 혼동되지
않도록 별도 상태로 셉니다 — CI는 이 상태로 실패하지 않습니다.
"""

    return header + body + tail, unmapped, stub_without_record


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

    tests, test_defects = collect_test_markers(args.tests)
    if test_defects:
        print(f"ERROR: 테스트 마커 수집 결함 {len(test_defects)}건", file=sys.stderr)
        for d in test_defects:
            print(f"  · {d}", file=sys.stderr)
        return 2

    manual, orphan, missing_blocking, incomplete_records = collect_manual(args.manual)

    # ── blocking_dod 칸 필수화 (WP-24C) ──────────────────────────────
    #
    # `blocking_dod` 를 읽는 코드가 없으면 사람이 적어 둔 "이건 차단이다"가
    # 기계에는 주석과 같다. 칸이 없으면 다음 사람이 깃발을 지우거나 false로
    # 바꿔도 아무 일도 일어나지 않으므로, 대장 전건에 이 칸을 강제한다.
    if missing_blocking:
        print(f"ERROR: blocking_dod 칸 누락 {len(missing_blocking)}건", file=sys.stderr)
        for m in missing_blocking:
            print(f"  · {m}", file=sys.stderr)
        print("\n모든 수동 검사 항목은 blocking_dod(참/거짓)를 명시해야 합니다 — "
              "없으면 Phase DoD 판정이 이 항목의 존재조차 모르게 됩니다.",
              file=sys.stderr)
        return 2

    # ── 수행 기록 완전성 (NFR-107-AC3) ───────────────────────────────
    #
    # status: 수행 인데 수행 일자·수행자·결과 중 하나라도 비어 있으면 「수행했다고
    # 적기만 하는」 우회가 된다. 대장 머리말이 "기록 없는 항목은 미수행으로
    # 본다"고 이미 적고 있는데 지금까지 아무도 확인하지 않았다.
    if incomplete_records:
        print(f"ERROR: 수행 기록 불완전 {len(incomplete_records)}건", file=sys.stderr)
        for m in incomplete_records:
            print(f"  · {m}", file=sys.stderr)
        print("\nstatus: 수행 인 항목은 performed_at·performed_by·result_note를 "
              "모두 기록해야 합니다 (NFR-107-AC3). 기록이 없으면 미수행으로 "
              "간주합니다.", file=sys.stderr)
        return 2

    # ── 게이트 자기참조 금지 (NFR-107-AC5 ⓒ) ────────────────────────
    #
    # `NFR-107-AC1.manual` 을 수동 대장에 등재해 충족시키면, 수동 예외 경로를
    # 정당화하는 조항 자신이 그 예외 경로로 "검증됨" 처리된다. 그 순간
    # **아무것도 검증되지 않은 채 미매핑 0건 초록불**이 뜬다.
    #
    # 이 상태는 표를 전개하지 않아도 이미 도달 가능했고, 금지 규칙이 문서에도
    # 도구에도 없었다. spec v0.9에서 AC5 본문에 명문화했고 여기서 강제한다.
    # 수동 항목은 *분류를 규정하는 조항*이 아니라 *분류된 조항*에 건다.
    self_ref = sorted(cid for cid in manual
                      if re.match(r"NFR-10[567]-", cid))
    if self_ref:
        print(f"ERROR: 게이트 자신을 수동 대장에 등재했습니다 {len(self_ref)}건",
              file=sys.stderr)
        for cid in self_ref:
            print(f"  · {cid} ({manual[cid]['id']})", file=sys.stderr)
        print("\n검증 게이트(NFR-105~107)의 수용기준은 수동 검증으로 자기충족될 수 "
              "없습니다 (NFR-107-AC5). 수동 항목은 분류를 규정하는 조항이 아니라 "
              "분류된 조항에 겁니다.", file=sys.stderr)
        return 2

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
                      f'({", ".join(Path(p).name for p, _ in tests[cid])})')

    # 미수행 차단 수동검사 — 「충족」이 아니라 「판정불가」로 센다 (WP-24C).
    # 게이트는 실패시키지 않는다: MC-1처럼 코드로 닫을 수 없는 검사가 있고,
    # 실패시키면 사람이 수행할 때까지 CI가 영구히 빨간불이 된다.
    blocking_unperformed = sorted(
        (cid, chk) for cid, chk in manual.items()
        if chk.get("blocking_dod") and chk.get("status") != "수행")

    content, unmapped, stub_only = render(
        reqs, tests, manual, orphan, spec_path.name,
        blocking_unperformed=blocking_unperformed)

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
    n_stub = sum(1 for entries in tests.values()
                 if entries and all(is_manual for _, is_manual in entries))
    print(f"요구사항 {len(reqs)}건 / 수용기준 {n_crit}건 / "
          f"자동 {len(tests) - n_stub}건 / 수동 {len(manual)}건 / "
          f"수동 스텁 {n_stub}건 / Phase 미지정 {n_unphased}건")

    print(f"차단 미수행(판정불가) {len(blocking_unperformed)}건")
    for cid, chk in blocking_unperformed:
        print(f"  · {chk['id']} ({cid}) — {chk.get('status', '미수행')}, "
              f"blocking_dod=true → Phase DoD 판정불가")

    if conflicts:
        print(f"Phase 표기 충돌 {len(conflicts)}건 — 본문과 부록 A.1이 다릅니다")
        for c in conflicts:
            print(f"  · {c}")

    if orphan:
        print(f"수동 대장 대상 없음 {len(orphan)}건 — criterion_id 누락")
        for o in orphan:
            print(f"  · {o}")

    if stub_only:
        # 결함이다. 매핑은 있으나 수행 기록이 생길 자리가 없다 — AC1.manual 은
        # 스텁을 인정하지만 AC3 은 수행 일자·수행자·결과를 대장에 요구한다.
        print(f"\nERROR: 수행 기록 없는 수동 스텁 {len(stub_only)}건", file=sys.stderr)
        for s in stub_only:
            print(f"  · {s}", file=sys.stderr)
        print("\n`@pytest.mark.manual` 스텁은 매핑 형식으로 인정되지만(AC1.manual), "
              "수행 일자·수행자·결과는 `docs/manual-checks.yaml`에 남겨야 합니다(AC3). "
              "대장 등재 없이 스텁만 두면 '수동으로 검증됨'이 미수행을 영구히 가립니다.",
              file=sys.stderr)
        return 2

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
