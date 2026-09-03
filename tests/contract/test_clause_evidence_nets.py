"""**그물 ③-1 · ③-2** — 조항이 「검증됨」으로 세어지는데 인용이 **다른 조항**을 잰다.

R38-B2 가 `FR-101-AC3`(Must-have · Phase 1)에서 만난 결함의 **형태**를 기계로
잡는다. 그때 인용 2건이 **둘 다** 이웃 조항(`NFR-208-AC1`)을 재고 있었는데
매핑표는 그 조항을 「자동 검증됨」으로 셌다.

R37 의 두 그물은 이 형태를 놓쳤다 — ⓐ **인용이 1건뿐인 조항**은 문턱이 1 이라
2 를 보지 않고 ⓑ **Phase 어긋남**은 그 조항도 인용도 Phase 1 이라 어긋남이 없다.
**둘 다 인용의 내용을 보지 않는다.** 그리고 이것은 「인용 2건」의 문제가 아니다 —
인용 N건 전부가 같은 이웃을 재면 **N 이 얼마든 같은 상태**가 된다.

R38 이 그물 셋을 설계하고 ③-3(`test_evidence_form.py`)만 세웠다. 남은 둘이
여기 있다.

    ③-1  조항 문면이 특정 구획을 **명시**하면(「코어 엔진」·「리포트」·「요금엔진」)
         그 조항의 인용 중 **적어도 하나**는 그 구획을 실제로 import 해야 한다
    ③-2  한 조항 X 의 인용 **전부**가 문면에서 같은 다른 조항 Y 를 적고
         X 는 **한 번도** 적지 않으면 사람이 볼 목록에 올린다

★ **③-1 은 import 문만 센다. 문자열 상수는 세지 않는다.** R38 이 실측한 이유가
이것이다 — `FR-101-AC3` 의 인용 2건은 "core.engine" 을 **금지 목록 문자열로**
담고 있었을 뿐 import 하지 않았다. 그 구분이 이 그물의 전부다.

★ **자기 자신에 걸리는 문제(공통 4절 ②).** 이 파일은 조항 ID 를 문면에 잔뜩
적는데 ③-2 는 「문면에 어느 조항 ID 가 적혔나」를 세는 그물이다. **`req` 마커를
달지 않는 것으로 갈랐다** — 두 그물은 *인용*(= `req` 마커가 붙은 테스트)만 보고,
마커가 없는 이 파일의 함수는 애초에 인용이 아니다. 설명을 고쳐 피한 것이 아니라
**대상을 좁혀** 피했으며, 그것을 `test_this_net_is_not_one_of_its_own_citations`
가 기계로 확인한다. `test_evidence_form.py` 가 같은 자리를 같은 방식으로 갈랐다.

마커를 달지 않은 또 하나의 이유는 그 파일과 같다 — 「조항 인용이 그 조항을
실제로 재는가」를 요구하는 조항이 spec 에 없다. 없는 조항을 인용하는 것이 이
파일이 잡으려는 결함이다.
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from functools import cache, lru_cache
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
_TESTS = _REPO_ROOT / "tests"
_SPEC = _REPO_ROOT / "rslt" / "spec-분산특구-경제성평가.md"

#: 조항 문면의 낱말 → 그 낱말이 가리키는 **실물 구획**.
#:
#: ⚠ **좁게 둔다. 못 잡는 것을 감수한다**(설계 정본이 그렇게 적었다).
#: 넣지 않은 것과 그 이유:
#:
#: - **맨 「엔진」** — `FR-1005-AC1` 「**엔진 종류** 기록」은 실행 매니페스트의
#:   *필드 이름*이고, `FR-101-AC4` 「엔진이 매체 수지를 분리 집계」·
#:   `FR-201-AC1` 「엔진 코드 변경이 발생하지 않는다」는 구획을 지목하되 문면이
#:   「코어 엔진」이 아니다. **이 셋을 이 그물은 못 잡는다**
#: - **경로 문면 `core/engine/`** — spec 이 그 형태로 적은 조항은
#:   `NFR-201-M1`(「신규 자원 추가 PR에서 core/engine/ diff 0줄」)과
#:   `NFR-208-AC1`(「예: core/der/ → core/engine/ 금지」)인데 **둘 다 그 구획을
#:   만지지 말라는 조항**이다. 그것을 인용이 import 해야 한다고 물으면 **그물이
#:   뒤집힌다.** 그래서 경로 문면은 넣지 않는다
#: - **「자원」(25건)·「요금」(25건)·「시나리오」(21건)·「케이스」(18건)·
#:   「모델」(12건)** — 도메인 낱말이지 구획 이름이 아니다
PARTITION_WORDS: dict[str, str] = {
    "코어 엔진": "core.engine",
    "리포트": "core.report",
    "요금엔진": "core.regulation.tariff",
}

#: ★ **③-1 이 지금 지목하는 자리.** 실측이며 **부채다** — 조항이 구획을
#: 명시하는데 그 조항의 인용 중 어느 것도 그 구획을 만지지 않는다.
#: **여기 있는 것을 지우려고 마커나 조항을 고치지 않는다.** 닫는 방법은 그
#: 구획을 실제로 만지는 검사를 세우는 것뿐이다.
#:
#: - `FR-401-AC1` — 「편익을 추가·비활성화해도 코어 엔진 수정이 발생하지
#:   않는다」. 인용 15건 전부가 편익 **산식**을 재고 엔진을 만지지 않는다.
#:   `FR-101-AC3` 과 **같은 형태**이며 R38 이 그것을 닫은 방식(엔진을 실제로
#:   돌리는 검사)이 여기에도 필요하다
#: ✔ **`FR-602-AC2` 는 R57/WP-8 이 닫았다** — `FR-404-AC1` 과 **같은 방식**이며
#: 시험을 더해서가 아니라 **리포트 문면을 세워서**다. 붙임 1 안에 「기준 전제 대비
#: 변경 항목」 표가 서고(`core/report/appendix_sections.py`) `CaseReport` 가
#: `AssumptionSet.overridden_items()` 를 읽어 나른다 — 호출자 0곳이었던 그
#: 메서드에 **읽는 자리**가 생겼다. ⚠ 이 검사가 *「닫힌 것을 남겨 두면 다음
#: 사람이 없는 일을 한다」* 고 적으므로 위 목록에서 그 짝을 지웠다.
#: - **`core.report` 4건** — 조항이 「…를 리포트에 표시/명시/표기한다」라고
#:   적는데 인용이 전부 산출 쪽(`tests/asset`·`tests/der`·`tests/assumption`·
#:   `tests/cba`)에 있고 리포트 계층을 만지지 않는다. 조항의 **앞 절반**
#:   (계산)은 검증되고 **뒤 절반**(표시)은 비어 있는 상태다.
#:   ★ WP-15 가 여섯을 실물 대조했다 — 여섯 다 **리포트가 그 표시를 아예 내지
#:   않는다**(자료구조는 「리포트가 표시하도록」 있는데 `core/report/` 에 호출자가
#:   0곳). 그러므로 시험을 더해서는 닫히지 않는다. 일곱 번째였던 `FR-402-AC7` 만
#:   리포트가 이미 내고 있었고(`core/report/perspective_report.py` 의 관점별
#:   포함·제외 tag), WP-15 가 그것을 재는 검사를 세워 닫았다.
#:   ✔ **`FR-404-AC1` 은 R48/WP-D2 가 닫았다** — 시험을 더해서가 아니라
#:   **리포트 문면을 세워서**다(`core/report/policy_warnings.py` 가 정책 가정
#:   경고 절을 상단에 인쇄하고, 자원의 문면은 `DER.policy_warnings()` →
#:   `ResourceLine.policy_warnings` 를 타고 실려 온다)
KNOWN_PARTITION_DEBT: frozenset[tuple[str, str]] = frozenset({
    ("FR-401-AC1", "core.engine"),
    ("FR-106-AC5", "core.report"),
    ("FR-603-AC2", "core.report"),
    ("FR-705-AC1", "core.report"),
    ("FR-905-AC8", "core.report"),
})

#: spec 이 이 둘을 경로 문면(`core/engine/`)으로 적었고 둘 다 그 구획을 **만지지
#: 말라**는 조항이다. 그물이 뒤집히므로 이 시험의 사전은 경로 표기를 넣지 않는다(위 주석).
#: 검사기 쪽은 넣고 「사각지대」 사유로 흡수한다 — **두 선택 다 옳으며 이 상수가
#: 그 차이를 명시한다**
KNOWN_PARTITION_DESIGN_GAP: frozenset[tuple[str, str]] = frozenset({
    ("NFR-201-M1", "core.engine"),
    ("NFR-208-AC1", "core.engine"),
})

#: ★ **③-2 가 지금 지목하는 조항** → 그 인용 **전부**가 만장일치로 적은 이웃.
#:
#: ⚠ **판정이 아니라 지목이다.** R37 이 만난 결함은 **독스트링이 거짓이었던**
#: 것이므로 이 신호만으로 「이 마커가 틀렸다」고 말할 수 없다. 그래도 목록을
#: 래칫으로 두는 이유는 **새로 켜지는 신호에 사람 눈이 가게** 하기 위해서다.
#:
#: 두 무리로 갈린다.
#:
#: **ⓐ 다른 요구사항을 지목한다 — `FR-101-AC3` 과 같은 형태다. 4건.**
#: 자기 요구사항 밖의 조항만 적히므로 인용이 실제로 이웃을 재고 있을 수 있다.
#: **근거를 전수로 읽고 판정하는 것은 사람 몫이며 이 구획의 일이 아니다.**
#:
#: **ⓑ 같은 요구사항의 형제만 지목한다. 8건.**
#: 한 요구사항 안에서 형제 조항을 곁들여 적는 것은 흔하고 대개 정상이다
#: (예: `FR-609-AC3` 의 인용이 설명에서 `FR-609-AC1` 을 끌어 쓴다). 신호가 약하다.
#:
#: ⚠⚠ **「대개 정상」이 「언제나 정상」은 아니다 — R59 가 둘을 지웠다.**
#: `FR-604-AC5`·`FR-604-AC6` 이 여기 있었는데, 실제로는 **`FR-604` 의 마커가
#: 한 칸씩 밀려 있던 것**이었다(`AC2`(보조)에 융자 시험 · `AC3`(융자)에 세제
#: 시험 …). R59/WP-6 이 마커를 조항 문면에 맞춰 되돌리자 **둘 다 저절로
#: 닫혔다.** 판정 전문은 `docs/decisions-2026-09-04-R59.md` §5.
#: ★ 그리고 그 밀림 중 **셋은 이 그물에 애초에 걸리지 않았다** — 자기(틀린)
#: ID 를 문면에 정확히 적고 있었기 때문이다. **이 그물이 못 보는 형태다.**
KNOWN_SILENT_CITATIONS: dict[str, tuple[str, ...]] = {
    # ⓐ 다른 요구사항 (★ `FR-101-AC3` 형태)
    "FR-401-AC2.DistributedBenefit": ("FR-404-AC1",),
    "FR-703-AC1.fiscal-pv": ("FR-704-AC6",),
    "NFR-107-AC1.auto": ("FR-101-AC1",),
    "NFR-107-AC1.manual": ("NFR-302-M1",),
    # ⓑ 같은 요구사항의 형제
    # ⚠ `FR-204-AC2` 도 **R59 가 지웠다** — 그 조항은 [Phase 2] 인데 Phase 1 시험이
    #   마커를 달고 있었다. 마커를 떼자 인용이 0건이 되어 지목에서 사라졌다.
    #   **`AC2` 는 이제 미매핑이며 그것이 옳다**(Phase 2 · 구현 없음).
    "FR-501-AC2": ("FR-501-AC7",),
    "FR-501-AC3": ("FR-501-AC7",),
    # ⚠ `FR-604-AC5`·`AC6` 은 **R59 가 지웠다** — 마커 밀림이 원인이었고 되돌리자
    #   닫혔다(위 ⓑ 주석). 되살리기 전에 그 판정부터 다시 보라.
    "FR-604-AC8": ("FR-604-AC7",),
    "FR-609-AC2": ("FR-609-AC1",),
    "FR-609-AC3": ("FR-609-AC1",),
    "FR-704-AC2": ("FR-704-AC1",),
    "FR-704-AC3": ("FR-704-AC1",),
    "NFR-107-AC5": ("NFR-107-AC1.manual",),
}


def _load_script(stem: str) -> ModuleType:
    """`scripts/` 의 정본 도구를 그대로 쓴다 — **두 번째 파서를 만들지 않는다.**

    조항 목록의 정본은 `_specparse.parse_spec`, 마커 수집의 정본은
    `gen_traceability.collect_test_markers`(와 그것이 쓰는 `_marks`)다. 여기서
    다시 쓰면 정본이 둘이 되고 어긋나는 날 어느 쪽이 맞는지 말할 수 없다 —
    R38 의 교훈이며, `test_evidence_form.py`·`tests/ci/test_traceability_gate.py`
    가 쓰는 것과 같은 적재 방식이다.
    """
    scripts = str(_SCRIPTS)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    name = f"_nets_{stem}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{stem}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _criteria() -> tuple[dict[str, str], dict[str, str]]:
    """(수용기준 ID → 문면, 수용기준 ID → 소속 요구사항 ID).

    ⚠ **반환값을 고쳐 쓰지 말 것** — 한 번만 재고 캐시한다.
    """
    reqs, defects = _load_script("_specparse").parse_spec(_SPEC)
    assert not defects, f"spec 파싱 결함이 있어 조항 목록을 신뢰할 수 없다: {defects}"
    text = {c.cid: c.text for r in reqs for c in r.criteria}
    owner = {c.cid: r.rid for r in reqs for c in r.criteria}
    return text, owner


# ── ③-1 「조항이 지목한 구획을 인용이 만지는가」 ──────────────────────────


@cache
def _imported_modules(path: str) -> frozenset[str]:
    """그 파일이 **import 문으로** 들여온 점 이름 전부.

    ★ **`ast.Import`·`ast.ImportFrom` 만 본다. 문자열 상수는 세지 않는다** —
    그것이 이 그물의 핵심이다. 상대 import(`from . import x`)는 계층 이름이
    풀리지 않으므로 건너뛴다.

    ⚠ **붙들지 못하는 것 — 갈라 적는다.**
    ① 간접 경로. 인용이 `core.casegrid.e2e_runner` 를 통해 리포트를 만들어도
       리포트를 import 하지 않았으면 「안 만졌다」로 센다
    ② 픽스처(`conftest.py`)가 대신 들여오는 경우
    ③ `importlib` 로 동적 적재한 대상
    ④ import 해 놓고 쓰지 않는 경우는 「만졌다」로 센다 — 이 그물은 **아무도
       그 구획 근처에 가지 않는 상태**를 잡는 것이지 깊이를 재지 않는다
    """
    names: set[str] = set()
    tree = ast.parse(Path(path).read_text(encoding="utf-8", errors="replace"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            module = node.module or ""
            names.add(module)
            names.update(f"{module}.{alias.name}" for alias in node.names)
    return frozenset(names)


def measure_partition_gap() -> dict[tuple[str, str], list[str]]:
    """(조항, 구획) → 그 조항의 인용 파일 전부. **아무도 그 구획을 안 만지는** 것만.

    마커 수집은 `gen_traceability.collect_test_markers` **정본 그대로**다 —
    모듈 `pytestmark`·클래스 데코레이터 상속을 이미 처리하므로 다시 쓰지 않는다.
    미매핑 조항은 대상이 아니다(`check_task_mapping.py`·`NFR-107` 의 소관이다).
    """
    text, _owner = _criteria()
    markers, defects = _load_script("gen_traceability").collect_test_markers(_TESTS)
    assert not defects, f"테스트 파일 파싱 결함 — 마커가 통째로 빠진다: {defects}"

    gaps: dict[tuple[str, str], list[str]] = {}
    for cid, body in text.items():
        for word, package in PARTITION_WORDS.items():
            if word not in body:
                continue
            files = sorted({path for path, _manual in markers.get(cid, [])})
            if not files:
                continue
            if any(
                name == package or name.startswith(f"{package}.")
                for path in files
                for name in _imported_modules(path)
            ):
                continue
            gaps[(cid, package)] = [
                Path(path).relative_to(_REPO_ROOT).as_posix() for path in files
            ]
    return gaps


# ── ③-2 「인용 전부가 다른 조항만 적는다」 ────────────────────────────────


@cache
def _id_pattern(cid: str) -> re.Pattern[str]:
    """그 ID 가 더 긴 ID 의 **조각**으로 걸리지 않게 양옆을 막는다."""
    return re.compile(
        r"(?<![A-Za-z0-9-])" + re.escape(cid) + r"(?![A-Za-z0-9-])(?!\.[A-Za-z0-9])"
    )


def _mentions(text: str, cids: list[str]) -> frozenset[str]:
    """문면에 **온전히** 등장하는 수용기준 ID 들.

    정규식으로 「조항 ID 처럼 생긴 것」을 긁지 않고 **spec 이 들고 있는 ID 목록과
    대조**한다. 긁으면 접두가 겹치는 순간 조용히 틀린다 — `NFR-208-AC1` 안에서
    `FR-208-AC1` 을, `FR-601-AC5.source` 안에서 `FR-601-AC5` 를 본다.
    """
    return frozenset(
        # `cid in text` 는 정규식의 **필요조건**이라 결과를 바꾸지 않는다. 조항이
        # 700종이고 검사가 1,500개라 이 한 줄이 12초를 1초 아래로 줄인다.
        cid for cid in cids if cid in text and _id_pattern(cid).search(text)
    )


def _prose_of(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """그 검사의 **설명 문면** — 독스트링과 오류 문면.

    ★ **`func.body` 만 훑는다. 데코레이터를 빼는 것이 핵심이다.**
    `@pytest.mark.req("FR-102-AC1.EV_V2G")` 의 인수도 문자열 상수이므로 함께
    세면 **모든 인용이 자기 조항을 적은 것이 되어 그물이 영원히 조용해진다.**
    """
    return "\n".join(
        node.value
        for stmt in func.body
        for node in ast.walk(stmt)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


def _walk_citations(
    body: list[ast.stmt],
    inherited: list[str],
    *,
    marks,
    cids: list[str],
    rel: str,
    out: dict[str, list[tuple[str, str, frozenset[str]]]],
) -> None:
    """클래스·함수를 훑어 (조항 ID → [(파일, 테스트 이름, 문면이 적은 조항들)]).

    ⚠ **파일 루프 안의 중첩 함수로 두지 않는다.** 루프 변수를 클로저로 잡으면
    (ruff `B023`) 지연 호출로 바뀌는 순간 **마지막 파일의 경로가 전 항목에
    붙는다.** `gen_traceability._walk_body` 가 같은 이유로 모듈 수준에 있다.
    """
    for node in body:
        if isinstance(node, ast.ClassDef):
            _walk_citations(
                node.body, inherited + marks(node.decorator_list)[0],
                marks=marks, cids=cids, rel=rel, out=out,
            )
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            marked = inherited + marks(node.decorator_list)[0]
            if not marked:
                continue
            said = _mentions(_prose_of(node), cids)
            for cid in marked:
                out.setdefault(cid, []).append((rel, node.name, said))


@lru_cache(maxsize=1)
def collect_citation_prose() -> dict[str, list[tuple[str, str, frozenset[str]]]]:
    """수용기준 ID → [(파일, 테스트 이름, 그 검사의 문면이 적은 조항들)].

    ⚠ **반환값을 고쳐 쓰지 말 것** — 한 번만 훑고 캐시한다.

    마커 읽기는 `gen_traceability._marks` 그대로이고 상속 규칙도 `_walk_body`
    와 같은 형태다. **테스트 이름과 문면을 함께 얻는 것만이 차이**이며, 그
    차이가 어긋나지 않았음을 아래
    `test_citation_collection_agrees_with_the_traceability_collector` 가 정본과
    대조해 확인한다.
    """
    marks = _load_script("gen_traceability")._marks
    text, _owner = _criteria()
    cids = sorted(text, key=len, reverse=True)
    out: dict[str, list[tuple[str, str, frozenset[str]]]] = {}

    for py in sorted(_TESTS.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
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
                module_reqs += marks(items)[0]
        _walk_citations(
            tree.body, module_reqs, marks=marks, cids=cids,
            rel=py.relative_to(_REPO_ROOT).as_posix(), out=out,
        )
    return out


def measure_silent_citations() -> dict[str, tuple[str, ...]]:
    """조항 → 그 인용 **전부**가 적었는데 정작 자기 조항은 아무도 안 적은 이웃들.

    **만장일치를 요구하는 이유.** 「인용 하나라도 다른 조항을 적었다」로 두면
    45건이 걸리는데 그 대부분은 설명이 이웃을 곁들여 인용한 것이다. 만장일치는
    `FR-101-AC3` 의 형태를 그대로 옮긴 것이다 — 그 조항은 인용 **두 건 모두**가
    `NFR-208-AC1` 을 적고 자기를 적지 않았다.
    """
    pointed: dict[str, tuple[str, ...]] = {}
    for cid, cites in collect_citation_prose().items():
        if any(cid in said for _f, _n, said in cites):
            continue
        common = frozenset.intersection(*[said - {cid} for _f, _n, said in cites])
        if common:
            pointed[cid] = tuple(sorted(common))
    return pointed


def _cross_requirement(pointed: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    """지목 중 **다른 요구사항**을 가리키는 것만 — `FR-101-AC3` 과 같은 형태다."""
    _text, owner = _criteria()
    return {
        cid: tuple(y for y in ys if owner[y] != owner[cid])
        for cid, ys in pointed.items()
        if any(owner[y] != owner[cid] for y in ys)
    }


# ── 검사 ─────────────────────────────────────────────────────────────


def test_partition_debt_agrees_with_script_ledger() -> None:
    """★ 메타 검사 — 두 대장이 의도된 설계 차이만큼만 다름을 단언한다.

    시험(`KNOWN_PARTITION_DEBT`)과 검사기(`check_clause_partition.py` 의 `KNOWN_GAPS`)는
    사전에 경로 표기를 넣느냐 마느냐의 설계 차이로 인해 정확히 `KNOWN_PARTITION_DESIGN_GAP`
    만큼의 차이가 난다. 그 밖의 차이가 생기면 누군가 한쪽 대장만 갱신한 것이다.
    """
    check_clause_partition = _load_script("check_clause_partition")
    known_gaps = check_clause_partition.KNOWN_GAPS

    assert set(KNOWN_PARTITION_DEBT) <= set(known_gaps), (
        "시험 대장에 있는 항목이 검사기 대장에 없다.\n"
        f"  사라진 것: {sorted(set(KNOWN_PARTITION_DEBT) - set(known_gaps))}\n"
        "부채를 갚았다면 `tests/contract/test_clause_evidence_nets.py` 의 "
        "`KNOWN_PARTITION_DEBT` 에서도 해당 항목을 지우십시오."
    )

    diff = set(known_gaps) - set(KNOWN_PARTITION_DEBT)
    assert diff == set(KNOWN_PARTITION_DESIGN_GAP), (
        "검사기 대장과 시험 대장의 차이가 의도된 설계 차이와 다르다.\n"
        f"  실제 차이:   {sorted(diff)}\n"
        f"  의도된 차이: {sorted(set(KNOWN_PARTITION_DESIGN_GAP))}\n"
        "새 결손이 생겼거나 부채를 갚았다면 두 대장을 모두 갱신하십시오:\n"
        "  - `scripts/check_clause_partition.py` 의 `KNOWN_GAPS`\n"
        "  - `tests/contract/test_clause_evidence_nets.py` 의 `KNOWN_PARTITION_DEBT`"
    )


def test_the_partition_dictionary_resolves_to_real_packages_and_real_clauses() -> None:
    """그물의 **입구**를 두 층에 못 박는다 — 사전은 스스로 정하는 값이 아니다.

    낱말은 **spec 문면**에서, 구획 이름은 **실물 디렉터리**에서 확인한다(공통
    4절 ①). 사전만 보고 사전을 검사하면 무엇을 적어 넣어도 통과한다.
    """
    text, _owner = _criteria()
    for word, package in PARTITION_WORDS.items():
        as_path = _REPO_ROOT / Path(*package.split("."))
        assert as_path.is_dir() or as_path.with_suffix(".py").is_file(), (
            f"사전이 없는 구획을 가리킨다: {word} → {package}"
        )
        hits = [cid for cid, body in text.items() if word in body]
        assert hits, (
            f"사전의 낱말 {word!r} 이 어느 조항에도 없다 — spec 이 다시 쓰였거나 "
            "낱말이 처음부터 문면과 어긋났다. 사전을 spec 에 맞추십시오"
        )


def test_every_clause_that_names_a_partition_has_a_citation_that_imports_it() -> None:
    """★★ **그물 ③-1 본체.** 래칫이며 **양방향**이다 — 늘어도 줄어도 빨간불이다.

    조항이 구획을 명시하면 그 조항의 인용 중 적어도 하나는 그 구획을 실제로
    import 해야 한다. **문자열 상수는 세지 않는다** — `FR-101-AC3` 의 인용
    2건은 "core.engine" 을 금지 목록 문자열로 담고 있었을 뿐이었고, 그 둘을
    「엔진을 잰다」로 세는 순간 이 그물은 잡아야 할 형태를 통과시킨다.

    - **늘면 빨간불**: 새 조항이 구획을 명시했는데 인용이 그 구획을 안 만진다
    - **줄면서 목록을 안 고쳐도 빨간불**: 닫힌 것을 남겨 두면 다음 사람이
      **없는 일**을 한다

    ⚠ **여기 걸린 것을 지우려고 마커를 옮기거나 조항을 고치지 않는다.**
    닫는 방법은 그 구획을 실제로 만지는 검사를 세우는 것뿐이다.
    """
    text, _owner = _criteria()
    measured = measure_partition_gap()
    assert set(measured) == set(KNOWN_PARTITION_DEBT), (
        "조항이 지목한 구획을 아무 인용도 만지지 않는 자리의 목록이 선언과 다르다.\n"
        f"  새로 들어온 것: {sorted(set(measured) - set(KNOWN_PARTITION_DEBT))}\n"
        f"  닫힌 것: {sorted(set(KNOWN_PARTITION_DEBT) - set(measured))} — 좋은 "
        "방향이며 **선언에서 지우십시오**\n"
        + "\n".join(
            f"  {cid} → {package}\n    조항: {text[cid]}\n"
            + "\n".join(f"    인용: {f}" for f in files)
            for (cid, package), files in sorted(measured.items())
        )
    )


def test_citation_collection_agrees_with_the_traceability_collector() -> None:
    """★ ③-2 의 인용 수집이 **정본과 같은 것을 본다.**

    이 파일은 테스트 이름과 문면을 얻으려고 `_walk_body` 와 같은 형태의 훑기를
    다시 쓴다. 상속 규칙을 하나라도 다르게 쓰면 **이 그물이 매핑표와 다른 인용
    집합을 보게 되고**, 그러면 조용히 틀린 목록을 낸다. 조항별 건수를 정본과
    대조해 그것을 막는다.
    """
    official, defects = _load_script("gen_traceability").collect_test_markers(_TESTS)
    mine = collect_citation_prose()

    assert defects == [], f"테스트 파일 파싱 결함: {defects}"
    assert set(mine) == set(official), (
        "인용된 조항 집합이 정본과 다르다.\n"
        f"  이 그물만: {sorted(set(mine) - set(official))}\n"
        f"  정본만:   {sorted(set(official) - set(mine))}"
    )
    mismatched = {
        cid: (len(mine[cid]), len(official[cid]))
        for cid in mine
        if len(mine[cid]) != len(official[cid])
    }
    assert not mismatched, (
        f"조항별 인용 건수가 정본과 다르다 (이 그물, 정본): {mismatched}. "
        "마커 상속 규칙이 `gen_traceability._walk_body` 와 갈렸다"
    )


def test_clauses_whose_citations_unanimously_name_someone_else() -> None:
    """★★ **그물 ③-2 본체.** 래칫이며 **양방향**이다.

    ⚠ **판정이 아니라 지목이다.** 여기 오른 조항이 곧 결함인 것이 아니다 —
    `FR-101-AC3` 의 결함은 **독스트링이 거짓이었던** 것이고 그 판정은 근거를
    전수로 읽은 사람이 했다. 이 그물이 하는 일은 **새로 켜지는 신호에 사람
    눈이 가게** 하는 것뿐이며, 그래서 빨간불의 뜻은 「고쳐라」가 아니라
    「읽고 판정한 뒤 선언을 갱신하라」다.

    목록만 인쇄하지 않고 래칫으로 세운 이유는 **아무도 안 보기** 때문이다 —
    `-q` 로 도는 CI 에서 표준출력은 삼켜진다.
    """
    measured = measure_silent_citations()
    prose = collect_citation_prose()
    assert measured == KNOWN_SILENT_CITATIONS, (
        "인용 전부가 자기 조항을 안 적고 같은 이웃만 적는 자리의 목록이 선언과 "
        "다르다. **읽고 판정한 뒤 선언을 갱신하십시오.**\n"
        f"  새로 들어온 것: {sorted(set(measured) - set(KNOWN_SILENT_CITATIONS))}\n"
        f"  닫힌 것: {sorted(set(KNOWN_SILENT_CITATIONS) - set(measured))}\n"
        + "\n".join(
            f"  {cid} → {ys}\n"
            + "\n".join(f"    인용: {f}::{n}" for f, n, _s in prose.get(cid, []))
            for cid, ys in sorted(measured.items())
            if KNOWN_SILENT_CITATIONS.get(cid) != ys
        )
    )


def test_the_cross_requirement_subset_is_called_out_separately() -> None:
    """★ 지목 중 **다른 요구사항**을 가리키는 것 — `FR-101-AC3` 과 같은 형태다.

    같은 요구사항의 형제를 곁들여 적는 것은 흔하고 대개 정상이다. 요구사항
    **밖**의 조항만 적히는 것이 R38 이 만난 형태이며, 그 부분집합이 조용히
    커지는 것을 따로 붙든다 — 전체 래칫만 두면 형제 항목 하나가 닫히는 같은
    회차에 강한 신호 하나가 들어와도 **집합이 달라지므로 빨간불이 나기는
    하나**, 무엇이 강한 신호인지는 그 메시지가 말해 주지 않는다.
    """
    strong = _cross_requirement(measure_silent_citations())
    declared = _cross_requirement(KNOWN_SILENT_CITATIONS)
    assert strong == declared, (
        "다른 요구사항만 지목하는 인용 집합이 선언과 다르다 — R38 이 "
        "`FR-101-AC3` 에서 만난 것과 같은 형태다.\n"
        f"  실측: {sorted(strong.items())}\n  선언: {sorted(declared.items())}"
    )


def test_this_net_is_not_one_of_its_own_citations() -> None:
    """★ 공통 4절 ② — **이 그물이 자기 문면에 걸리지 않는 것을 기계로 확인한다.**

    이 파일은 조항 ID 를 사전·래칫·설명에 잔뜩 적는다. ③-2 는 「문면에 어느
    조항 ID 가 적혔나」를 세는 그물이므로 **이 파일이 인용이 되는 순간 자기
    자신을 지목한다.** 갈라 놓은 방법은 **`req` 마커를 달지 않는 것**이며
    (설명을 고친 것이 아니라 대상을 좁힌 것이다), 그것이 지켜지는지 여기서
    센다. 누가 이 파일에 마커를 달면 이 검사가 먼저 멈춘다.
    """
    here = Path(__file__).relative_to(_REPO_ROOT).as_posix()
    citing = {
        cid: name
        for cid, cites in collect_citation_prose().items()
        for f, name, _said in cites
        if f == here
    }
    assert not citing, (
        f"이 파일이 조항을 인용하고 있다: {citing}. 그러면 ③-2 가 이 파일의 "
        "설명 문면을 세게 되고 **그물이 자기 자신을 지목한다.** 마커를 여기 "
        "달지 말고 실제로 그 조항을 재는 검사에 다십시오"
    )
