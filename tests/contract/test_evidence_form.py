"""**그물 ③-3** — 조항이 검증 방법을 지정했으면 그 조항의 인용이 그 방법인가.

R38-B2 가 `FR-101-AC3` 에서 만난 결함의 **형태**를 기계로 잡는다. 그때 인용
2건이 **둘 다** `inspect.getsource` 검사였는데 조항은 *「(단위 테스트로 **실증**)」*
을 요구했다 — 아무것도 실행하지 않는 검사 둘이 「실증」 칸에 앉아 있었고 매핑표는
그 조항을 「자동 검증됨」으로 셌다.

R37 의 두 그물은 이 형태를 놓쳤다. ⓐ **인용이 1건뿐인 조항**은 문턱이 1 이라
2 를 보지 않고 ⓑ **Phase 어긋남**은 `AC3` 가 Phase 1 이고 인용도 Phase 1 이라
어긋남이 없다. **둘 다 인용의 내용을 보지 않는다.**

    조항 문면에 「테스트로 실증」·「실행하고 통과를 확인」이 있다
        → 그 조항의 인용 **중 적어도 하나**는 문면 검사가 아니어야 한다

★ **조항 단위로 묻는다. 검사 단위로 묻지 않는다.** 검사 하나씩 훑어 「이 검사는
`ast` 를 쓴다」로 빨간불을 내면 **그물이 자기 자신을 잡는다** — 이 파일도
`ast` 검사이고, `FR-101-AC3` 을 재는 검사 둘 중 하나도 `ast` 검사다. 실행하는
검사가 **함께** 있으면 조항은 「실증」을 갖는다.

`req` 마커를 달지 않았다 — 「조항 인용이 조항이 지정한 검증 방법을 지키는가」를
요구하는 조항이 없다. 없는 조항을 인용하는 것이 이 파일이 잡으려는 결함이다.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
_TESTS = _REPO_ROOT / "tests"
_SPEC = _REPO_ROOT / "rslt" / "spec-분산특구-경제성평가.md"

#: 조항 문면이 **실행을 검증 방법으로 지정**했다고 볼 낱말.
#:
#: ⚠ **좁게 둔다.** 맨 「실증」을 넣으면 `SC-3`(*「**실증** 참여 가구의 개별
#: 식별정보 미저장」*)이 걸린다 — 이 사업 자체가 분산특구 **실증**사업이므로
#: 그 낱말은 「시험으로 증명한다」와 「실증사업의」 둘로 쓰인다. 맨 「테스트」도
#: 넣지 않는다(9건이 걸리는데 대부분 커버리지·회귀 **문턱**을 말한다).
METHOD_TOKENS = ("테스트로 실증", "단위 테스트로", "실행하고 통과를 확인")

#: ★ **이 그물이 판정하지 못하는 조항.** 부채가 **아니다** — 저장소의 어긋남이
#: 아니라 **그물의 사각지대**다. 사람이 판정한 결과를 함께 적는다.
#:
#: `NFR-107-AC1.auto` — 인용 1건
#: (`tests/ci/test_traceability_gate.py::test_traceability_collects_executed_req_markers_as_auto`)
#: 은 `collect_test_markers()` 를 **실제로 돌려** 반환값을 단언한다. 즉 사람의
#: 판정은 **「충족」**이다. 그런데 그 검사는 그 함수를 `importlib` 로 동적 적재해
#: (`gen = _load_script("gen_traceability")`) 쓰므로 **정적으로는 어느 모듈의
#: 무엇인지 이름이 풀리지 않는다.** 게다가 대상이 `scripts/` 라 `core|app|infra`
#: 접두로도 걸리지 않는다.
#:
#: **줄이는 방법**: 그물이 `scripts/` 를 계층으로 인정하고 `importlib` 적재
#: 관용구(`_load_script("<stem>")`)를 이름 해석에 넣으면 이 항이 사라진다.
#: 여기 남아 있는 동안은 **「통과」로 세지 않는다** — 그것이 조용한 실패다.
KNOWN_UNDECIDED = frozenset({"NFR-107-AC1.auto"})

#: 문면만 읽는 호출. `ast` 의 **`Call` 노드만** 보므로 독스트링·주석은
#: 구조적으로 배제된다 — 문면 제외 목록을 따로 만들지 않았다(공통 4절 ②).
SOURCE_READING = frozenset({
    "getsource", "getsourcelines", "getsourcefile", "getmodule",
    "read_text", "read_bytes", "readlines", "parse", "open",
})

#: 이름이 이 접두의 패키지에서 왔으면 「제품 코드」로 본다.
LAYER_ROOTS = ("core", "app", "infra")


def _load_script(stem: str) -> ModuleType:
    """`scripts/` 의 정본 도구를 그대로 쓴다 — 두 번째 파서를 만들지 않는다.

    조항 목록의 정본은 `_specparse.parse_spec`, 마커 읽기의 정본은
    `gen_traceability._marks` 다. 여기서 다시 쓰면 정본이 둘이 되고 어긋나는
    날 어느 쪽이 맞는지 말할 수 없다. `tests/ci/test_traceability_gate.py` 가
    쓰는 것과 같은 적재 방식이다.
    """
    scripts = str(_SCRIPTS)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    name = f"_net3_{stem}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{stem}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _selected_criteria() -> dict[str, str]:
    """검증 방법으로 **실행**을 지정한 수용기준 → 그 문면.

    ⚠ **반환값을 고쳐 쓰지 말 것** — 한 번만 재고 캐시한다(전 테스트 파일을
    다시 훑으면 이 파일 하나가 20초를 넘는다).

    ⚠ **조항 ID 를 리터럴로 적지 않는다.** spec 이 개정돼 같은 낱말을 쓰는
    조항이 늘면 **코드 수정 없이 함께 잡혀야** 한다.
    """
    reqs, defects = _load_script("_specparse").parse_spec(_SPEC)
    assert not defects, f"spec 파싱 결함이 있어 조항 목록을 신뢰할 수 없다: {defects}"
    return {
        c.cid: c.text
        for r in reqs
        for c in r.criteria
        if any(token in c.text for token in METHOD_TOKENS)
    }


def _root_name(node: ast.expr) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _leaf_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _layer_names(tree: ast.Module) -> set[str]:
    """모듈이 `core|app|infra` 에서 들여온 이름들."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in LAYER_ROOTS:
                    names.add((alias.asname or alias.name).split(".")[0])
        elif (
            isinstance(node, ast.ImportFrom)
            and (node.module or "").split(".")[0] in LAYER_ROOTS
        ):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def classify_test(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    layer_names: set[str],
    module_funcs: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
) -> str:
    """`"실행"` · `"문면"` · `"모른다"` 중 하나.

    신호 셋을 센다.

    | 신호 | 뜻 |
    |---|---|
    | `invoke` | 제품 클래스를 **만들어 그 메서드를 부른다** (`RuleBasedEngine().run(...)`) |
    | `plain`  | 제품 함수를 부른다 (문면 읽기가 아닌 것) |
    | `read`   | 문면을 읽는다 (`inspect.getsource` · `ast.parse` · `read_text` …) |

    판정:

        invoke 있으면                        → 실행
        invoke 없고 read 있으면              → 문면
        invoke·read 없고 plain 있으면        → 실행
        아무 신호도 없으면                    → 모른다

    ★ **`read` 가 `plain` 을 이긴다.** 이 순서가 이 판정의 핵심이며 실측으로
    정했다. `test_engine_source_names_no_resource_tag_beyond_the_declared_three`
    는 `discover(core.der, DER)`(제품 함수)를 부르지만 **단언이 소비하는 것은
    엔진 소스의 `ast`** 다. `plain` 을 우선하면 그 문면 검사가 「실행」으로
    세어지고, 그러면 이 그물은 **자기가 잡아야 할 형태를 통과시킨다.**

    ⚠ **붙들지 못하는 것 — 갈라 적는다.**
    ① `importlib` 로 동적 적재한 대상은 이름이 풀리지 않아 **모른다**가 된다
       (`KNOWN_UNDECIDED` 의 유일한 항이 그 경우다)
    ② `scripts/` 는 계층으로 세지 않는다 — 제품 코드이지만 `core|app|infra` 가
       아니다
    ③ 같은 모듈 헬퍼는 **한 단계만** 따라간다
       (`check_marker_substance.py` 의 규칙과 같은 깊이)
    ④ 단언이 실행 결과를 **실제로 소비하는지**는 보지 않는다. 돌려 놓고 단언은
       문면으로 하는 검사는 「실행」으로 세어진다
    ⑤ 픽스처(`conftest.py`)가 대신 실행하는 경우는 보지 않는다
    """
    invoke = 0
    plain = 0
    read = 0
    followed: set[str] = set()

    def scan(node: ast.AST, depth: int) -> None:
        nonlocal invoke, plain, read
        # 제품 클래스를 만들어 메서드를 부르는 자리: `X(...).m(...)`
        for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
            leaf = _leaf_name(call.func)
            if (
                isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Call)
                and _root_name(call.func.value.func) in layer_names
                and leaf not in SOURCE_READING
            ):
                invoke += 1
                continue
            if leaf in SOURCE_READING:
                read += 1
                continue
            if _root_name(call.func) in layer_names:
                plain += 1
                continue
            if depth == 0 and leaf in module_funcs and leaf not in followed:
                followed.add(leaf)
                scan(module_funcs[leaf], depth + 1)

    scan(func, 0)
    if invoke:
        return "실행"
    if read:
        return "문면"
    if plain:
        return "실행"
    return "모른다"


def _walk_marked(
    body: list[ast.stmt],
    inherited: list[str],
    *,
    marks,
    layer_names: set[str],
    module_funcs: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    rel: str,
    out: dict[str, list[tuple[str, str, str]]],
) -> None:
    """클래스·함수를 훑어 (조항 ID → 인용) 을 모은다.

    ⚠ **파일 루프 안의 중첩 함수로 두지 않는다.** 루프 변수를 클로저로 잡으면
    (ruff `B023`) 나중에 지연 호출로 바뀌는 순간 **마지막 파일의 경로가 전
    항목에 붙는다.** `gen_traceability._walk_body` 가 같은 이유로 모듈 수준에
    있고, 그 독스트링이 그 사실을 적어 두었다 — 여기서 다시 밟지 않는다.
    """
    for node in body:
        if isinstance(node, ast.ClassDef):
            _walk_marked(
                node.body,
                inherited + marks(node.decorator_list)[0],
                marks=marks,
                layer_names=layer_names,
                module_funcs=module_funcs,
                rel=rel,
                out=out,
            )
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            cids = inherited + marks(node.decorator_list)[0]
            if not cids:
                continue
            verdict = classify_test(node, layer_names, module_funcs)
            for cid in cids:
                out.setdefault(cid, []).append((rel, node.name, verdict))


@lru_cache(maxsize=1)
def collect_citations() -> tuple[dict[str, list[tuple[str, str, str]]], list[str]]:
    """수용기준 ID → [(파일, 테스트 이름, 판정)]. 그리고 파싱 결함.

    ⚠ **반환값을 고쳐 쓰지 말 것** — 한 번만 훑고 캐시한다.

    마커 읽기는 `gen_traceability._marks` 그대로다. 상속 규칙(모듈
    `pytestmark` · 클래스 데코레이터)도 `_walk_body` 와 같은 형태로 훑는다 —
    pytest 가 그렇게 동작하므로 도구도 같아야 한다. **함수 이름을 더한 것만이
    차이**이며, 그 차이가 어긋나지 않았음을 아래
    `test_citation_collection_agrees_with_the_traceability_collector` 가 정본과
    대조해 확인한다.
    """
    marks = _load_script("gen_traceability")._marks
    out: dict[str, list[tuple[str, str, str]]] = {}
    defects: list[str] = []

    for py in sorted(_TESTS.rglob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            defects.append(f"{py.name} 파싱 실패 (L{exc.lineno}) — 이 파일의 마커가 빠진다")
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
                module_reqs += marks(items)[0]

        _walk_marked(
            tree.body,
            module_reqs,
            marks=marks,
            layer_names=_layer_names(tree),
            module_funcs={
                n.name: n
                for n in tree.body
                if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
            },
            rel=py.relative_to(_REPO_ROOT).as_posix(),
            out=out,
        )

    return out, defects


# ── 검사 ─────────────────────────────────────────────────────────────


def test_the_net_derives_its_clause_list_from_spec_and_stays_narrow() -> None:
    """그물의 **입구**를 고정한다 — 낱말을 넓히면 여기서 멈춘다.

    `SC-3` 이 걸리지 않는 것을 단언하는 이유: 맨 「실증」을 낱말에 넣으면
    *「**실증** 참여 가구의 개별 식별정보 미저장」* 이 걸리는데 그것은 **개인정보
    보호 조항**이고 검증 방법을 지정한 것이 아니다. **그물의 오탐이며 부채가
    아니다.** 낱말을 넓히는 사람이 이 단언에서 멈추고 근거를 남기게 한다.
    """
    selected = _selected_criteria()
    assert selected, (
        "검증 방법을 지정한 조항이 0건이다 — 낱말이 spec 문면과 어긋났거나 "
        f"`_specparse` 의 문면이 바뀌었다. 낱말: {METHOD_TOKENS}"
    )
    assert "SC-3" not in selected, (
        "`SC-3`(개인정보 최소수집)이 걸렸다. 낱말이 넓어져 「실증사업」의 "
        "「실증」까지 잡고 있다 — 이 저장소는 분산특구 **실증**사업이므로 그 "
        "낱말은 두 뜻으로 쓰인다. 낱말을 좁히십시오"
    )
    for cid, text in selected.items():
        assert any(token in text for token in METHOD_TOKENS), (
            f"{cid} 이 낱말 없이 선택됐다 — 선택 규칙이 문면과 갈렸다: {text!r}"
        )


def test_citation_collection_agrees_with_the_traceability_collector() -> None:
    """★ 인용 수집이 **정본과 같은 것을 본다.**

    이 파일은 함수 이름을 얻기 위해 `_walk_body` 와 같은 형태의 훑기를 다시
    쓴다. 상속 규칙을 하나라도 다르게 쓰면 **이 그물이 매핑표와 다른 인용
    집합을 보게 되고**, 그러면 조용히 틀린 판정을 낸다. 조항별 건수를 정본과
    대조해 그것을 막는다.
    """
    gen = _load_script("gen_traceability")
    official, official_defects = gen.collect_test_markers(_TESTS)
    mine, my_defects = collect_citations()

    assert official_defects == my_defects == [], (
        f"테스트 파일 파싱 결함 — 정본 {official_defects} / 이 그물 {my_defects}"
    )
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


def test_every_clause_that_names_execution_has_an_executing_citation() -> None:
    """★★ **그물 ③-3 본체.** 조항 단위로 묻는다.

    `FR-101-AC3` 에 R38-B2 **전의** 상태를 넣으면 빨간불이다 — 인용 2건이
    둘 다 `inspect.getsource` 검사였다. 지금은
    `test_a_contract_only_resource_dispatches_through_the_unmodified_engine`
    이 엔진을 실제로 돌리므로 초록불이다.

    **「모른다」를 「통과」로 읽지 않는다.** 판정 불가는 `KNOWN_UNDECIDED` 로
    따로 세고(다음 검사), 여기서는 **명백히 실행하는 인용이 하나라도 있는가**만
    본다.
    """
    selected = _selected_criteria()
    citations, _defects = collect_citations()

    offenders: dict[str, list[tuple[str, str, str]]] = {}
    for cid in selected:
        cites = citations.get(cid, [])
        if not cites:
            continue  # 미매핑은 `check_task_mapping.py`·NFR-107 의 소관이다
        if any(verdict == "실행" for _f, _n, verdict in cites):
            continue
        if cid in KNOWN_UNDECIDED:
            continue
        offenders[cid] = cites

    assert not offenders, (
        "조항이 **실행으로 검증하라**고 적었는데 그 조항의 인용 중 실행하는 것이 "
        "하나도 없다 — 아무것도 돌리지 않는 검사가 「실증」 칸에 앉아 있고 "
        "매핑표는 그 조항을 「검증됨」으로 센다.\n"
        + "\n".join(
            f"  {cid}\n    조항: {selected[cid]}\n"
            + "\n".join(f"    [{v}] {f}::{n}" for f, n, v in cites)
            for cid, cites in sorted(offenders.items())
        )
        + "\n실행하는 검사를 세우십시오. **마커만 옮기면 「검증됨」이 다시 "
        "거짓이 됩니다.**"
    )


def test_the_undecided_list_is_exactly_what_the_net_cannot_classify() -> None:
    """★ 래칫 — **양방향**이다. 늘어도 줄어도 빨간불이다.

    `KNOWN_UNDECIDED` 에 있는 것은 **저장소의 어긋남이 아니라 그물의
    사각지대**다(그 상수의 주석에 건별 사람 판정과 근거를 적었다). 그래도
    래칫으로 두는 이유는 **「모른다」가 조용히 「통과」로 읽히는 것을 막기**
    위해서다.

    - **늘면 빨간불**: 새 조항이 판정 불가로 들어왔다. 그물을 넓히거나, 그
      조항의 인용을 실행하는 검사로 만들어야 한다
    - **줄면서 목록을 안 고쳐도 빨간불**: 닫힌 것을 목록에 남겨 두면 다음
      사람이 **없는 일**을 한다
    """
    selected = _selected_criteria()
    citations, _defects = collect_citations()

    undecided = {
        cid
        for cid in selected
        if citations.get(cid)
        and not any(v == "실행" for _f, _n, v in citations[cid])
        and any(v == "모른다" for _f, _n, v in citations[cid])
    }
    assert undecided == set(KNOWN_UNDECIDED), (
        "그물이 판정하지 못하는 조항 목록이 선언과 다르다.\n"
        f"  선언: {sorted(KNOWN_UNDECIDED)}\n"
        f"  실측: {sorted(undecided)}\n"
        f"  새로 들어온 것: {sorted(undecided - set(KNOWN_UNDECIDED))} — 그물을 "
        "넓히거나 그 조항에 실행하는 검사를 세우십시오\n"
        f"  닫힌 것: {sorted(set(KNOWN_UNDECIDED) - undecided)} — 좋은 방향이며 "
        "**선언에서 지우십시오**. 남겨 두면 다음 사람이 없는 일을 합니다"
    )
