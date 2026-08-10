#!/usr/bin/env python3
"""조항 마커 검증 내용 검사 — tests/에서 @pytest.mark.req(...)를 달고
본문에 검증이 없는 테스트를 잡는다.

왜 이 검사가 필요한가
--------------------
이 저장소에서 가장 나쁜 상태는 「빨간불」이 아니라 **「검사하지 않으면서
초록불인 것」**입니다. 지난 라운드에 그런 것이 두 번 나왔습니다 —
본문이 `pass` 한 줄인데 조항 마커 셋을 달고 있던 테스트(`FR-611-AC4`),
그리고 조항의 **정반대**를 고정하고 있던 테스트(`RC-ESS-B3`).
둘 다 매핑표에서는 초록불이었습니다.

손으로 유지하는 목록은 목록 밖의 것을 조용히 통과시킵니다. 그래서
면제 목록을 만들지 말고 **판정 규칙 자체를 정확히**하세요.

판정 규칙
----------
대상: `tests/` 하위 `.py`의 모든 테스트 함수.

한 함수가 아래 셋을 **모두** 만족하면 **위반**입니다.

1. `@pytest.mark.req(...)`를 갖는다
   — 함수 데코레이터뿐 아니라 **모듈 수준 `pytestmark`와 클래스 데코레이터
   상속**도 인정합니다. `scripts/gen_traceability.py`가 이미 그렇게 읽으니
   **그 파일의 수집 방식을 그대로 따릅니다** (`_marks()`·`_walk_body()`).

2. `@pytest.mark.manual`이 **없다**
   — `manual`이 붙은 것은 사람이 하는 검증의 명세 스텁이고, 본문이 비어
   있는 것이 **정상**입니다 (`tests/web/test_manual_stubs.py` 7개가 그 예).

3. 본문에 **검증 행위가 하나도 없다** — 아래 중 어느 것도 없을 때입니다.
   - `assert` 문
   - `raise AssertionError(...)` · `pytest.fail(...)`
     — **`assert`보다 약한 것이 아니라 강한 것입니다.** `assert`는
     `python -O`에서 통째로 사라지지만 이 둘은 남습니다. 인정하지 않으면
     `ruff`의 `B011`(`assert False` 금지)과 이 게이트가 **정면으로
     부딪히고**, 사람은 게이트를 통과시키려고 사라지는 `assert False`로
     되돌아갑니다. 실제로 R8에서 그 충돌이 났습니다 — `B011` 9건을
     `raise AssertionError`로 고치자 이 게이트가 멀쩡한 테스트 4건을
     위반으로 잡았습니다
   - `pytest.raises`·`pytest.warns`·`pytest.deprecated_call`의 `with` 사용
   - `.assert_...()` 형태의 Mock 단언 (`assert_called_once` 등)
   - **같은 모듈 안에 정의된 다른 함수를 호출하는데 그 함수가 위 셋 중
     하나를 갖는 경우** (헬퍼로 단언을 뺀 정상 형태 — 한 단계만 따라가면
     충분합니다)

종료 코드
----------
0   위반 없음
1   위반이 있다
2   검사 자체가 성립하지 않음 (tests/를 못 읽음, 파싱 실패 등)

**종료 코드 2를 반드시 둡니다.** 검사를 수행하지 못한 것을 통과로 읽으면
게이트가 조용히 무력화됩니다.

출력
------
위반 목록은 **파일:줄·함수명·인용한 조항 ID**를 함께 내세요.
조항 ID가 없으면 사람이 무엇이 덮였는지 알 수 없습니다.
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Callable
from pathlib import Path


def _attr_path(node: ast.AST | None) -> str:
    """`pytest.mark.req` 같은 점 표기를 문자열로 되돌린다."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _marks(decorators: list[ast.expr]) -> tuple[list[str], bool]:
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


def _has_verification(body: list[ast.stmt],
                       module_functions: dict[str, Callable[[list[ast.expr]], bool]]
                       ) -> bool:
    """함수 본문에 검증 행위가 있는지 판정한다.

    AST로 읽는 이유: 문자열로 훑으면 주석과 독스트링의 언급이 단언으로
    세어집니다. 실제로 이 저장소에서 여섯 번 걸린 유형이고, 이 방향의 오판은
    **게이트를 조용히 초록불**로 만들기 때문에 더 나쁩니다.

    본문 전체를 재귀 순회합니다 — for·if·with·try·while 안에 든 assert도
    놓치지 않기 위해서입니다. 중첩 함수 안의 assert도 인정합니다 (이번
    라운드에서 — 중첩 함수의 실행 여부를 판정하는 것은 복잡도가 너무 높아
    오탐을 늘리므로 게이트를 끄게 만듭니다).
    """

    def check_node(node: ast.AST) -> bool:
        if isinstance(node, ast.Assert):
            return True
        if isinstance(node, ast.Raise):
            # `raise AssertionError(...)` — **`assert`보다 약한 것이 아니라 강한
            # 것입니다.** `assert`는 `python -O`에서 통째로 사라지지만 이것은
            # 남습니다. 인정하지 않으면 `ruff`의 `B011`(`assert False` 금지)과
            # 이 게이트가 정면으로 부딪히고, 사람은 게이트를 통과시키려고
            # **사라지는 `assert False`로 되돌아갑니다.**
            exc = node.exc
            if isinstance(exc, ast.Call):
                exc = exc.func
            if _attr_path(exc) in ("AssertionError", "pytest.fail"):
                return True
        if isinstance(node, ast.With):
            # with pytest.raises(...), with pytest.warns(...), with pytest.deprecated_call(...)
            for item in node.items:
                context_expr = item.context_expr
                if isinstance(context_expr, ast.Call):
                    name = _attr_path(context_expr.func)
                    if name in ("pytest.raises", "pytest.warns", "pytest.deprecated_call"):
                        return True
        if isinstance(node, ast.Call):
            # mock.assert_...() 형태 (예: assert_called_once, assert_called_with)
            name = _attr_path(node.func)
            if name == "pytest.fail":
                # 조건 분기 아래의 `pytest.fail(...)`도 판정 행위다. 위
                # `raise AssertionError`와 같은 이유로 인정한다.
                return True
            if name and ".assert_" in name and "pytest" not in name:
                # 표준 Mock 단언 메서드들 (예: session.add.assert_called_once)
                return True
            # 같은 모듈의 헬퍼 함수 호출 → 그 함수가 검증을 갖는지 확인.
            # 헬퍼의 본문에 단언이 있는지만 본다 — 인수가 실제로 쓰이는지는
            # 따지지 않는다.
            if (isinstance(node.func, ast.Name) and node.func.id in module_functions
                    and module_functions[node.func.id](node.args)):
                return True
        return False

    # 본문 전체를 재귀 순회한다. **한 겹만 보면 안 된다** — `for`·`if`·`with`·
    # `try`·`while` 안에 든 단언을 놓치고, 그러면 멀쩡한 테스트가 위반으로
    # 잡힌다. 실제로 초판이 그렇게 해서 정상 테스트 셋을 오탐했다.
    return any(check_node(node) for stmt in body for node in ast.walk(stmt))


def _collect_module_functions(tree: ast.Module) -> dict[str, Callable[[list[ast.expr]], bool]]:
    """같은 모듈 안에 정의된 함수를 수집한다.

    헬퍼로 단언을 뺀 정상 형태를 감지하기 위해 사용합니다.
    한 단계만 따라갑니다 — 재귀로 모든 호출을 따라가면 너무 복잡해집니다.
    """
    functions: dict[str, Callable[[list[ast.expr]], bool]] = {}

    def collect_defs(node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # 클로저 문제(B023)를 피하기 위해 함수명과 본문을 캡처
            func_name = node.name
            func_body = node.body

            def check(args: list[ast.expr]) -> bool:
                # 인수를 쓰지 않고 본문만 검사 — 파라미터가 사용되는지는 따지지 않음
                # 헬퍼의 본문에 assert가 있는지가 중요
                return _has_verification(func_body, {})  # 헬퍼의 헬퍼는 따지지 않음

            functions[func_name] = check

    for node in tree.body:
        collect_defs(node)
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                collect_defs(item)

    return functions


def _walk_body(
    body: list[ast.stmt],
    inherited_reqs: list[str],
    inherited_manual: bool,
    *,
    module_functions: dict[str, Callable[[list[ast.expr]], bool]],
    path: str,
    violations: list[tuple[int, str, list[str]]],
) -> None:
    """클래스·함수를 훑어 위반을 모은다."""
    for node in body:
        if isinstance(node, ast.ClassDef):
            r, m = _marks(node.decorator_list)
            _walk_body(
                node.body,
                inherited_reqs + r,
                inherited_manual or m,
                module_functions=module_functions,
                path=path,
                violations=violations,
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            r, m = _marks(node.decorator_list)
            all_reqs = inherited_reqs + r
            has_manual = inherited_manual or m

            # 테스트 함수인지 확인 (def test_... 또는 pytest.fixture)
            func_name = node.name
            is_test = func_name.startswith("test_") or any(
                _attr_path(d.func) == "pytest.fixture"
                for d in node.decorator_list
                if isinstance(d, ast.Call)
            )

            if (is_test and all_reqs and not has_manual
                    and not _has_verification(node.body, module_functions)):
                violations.append((node.lineno, func_name, all_reqs))


def check_marker_substance(tests_dir: Path) -> tuple[list[tuple[str, int, str, list[str]]], int]:
    """tests/를 훑어 조항 마커가 있는데 검증이 없는 함수를 찾는다.

    Returns:
        (위반 목록 [(파일, 줄, 함수명, 조항ID목록)], 종료 코드)
        종료 코드: 0=위반 없음, 1=위반 있음, 2=검사 실패
    """
    if not tests_dir.is_dir():
        return [], 2

    result: list[tuple[str, int, str, list[str]]] = []
    parse_errors: list[tuple[str, int, str]] = []

    for py in sorted(tests_dir.rglob("*.py")):
        text = py.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError as e:
            parse_errors.append((str(py), e.lineno or 0, e.msg))
            continue

        # 모듈 수준 pytestmark = [...]도 전 테스트에 걸린다
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

        # 같은 모듈의 함수들 수집 (헬퍼 검사용)
        module_functions = _collect_module_functions(tree)

        local_violations: list[tuple[int, str, list[str]]] = []
        _walk_body(
            tree.body,
            mod_reqs,
            mod_manual,
            module_functions=module_functions,
            path=str(py),
            violations=local_violations,
        )

        for lineno, func_name, reqs in local_violations:
            result.append((str(py), lineno, func_name, reqs))

    if parse_errors:
        # 파싱 실패를 조용히 건너뛰면 마커가 통째로 사라진다
        for path, lineno, msg in sorted(parse_errors):
            print(f"파싱 실패: {path}:{lineno} — {msg}", file=sys.stderr)
        return [], 2

    return result, 1 if result else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="조항 마커 실질 검사 — req 마커가 있는데 "
                    "본문에 검증이 없는 테스트를 잡는다"
    )
    parser.add_argument("--tests", type=Path, default=None,
                        help="tests 디렉토리 경로 (기본: 저장소 루트/tests)")
    args = parser.parse_args(argv)

    repo = Path(__file__).resolve().parent.parent
    tests_dir = args.tests or (repo / "tests")

    violations, exit_code = check_marker_substance(tests_dir)

    if exit_code == 2:
        print("검사를 수행할 수 없습니다", file=sys.stderr)
        return 2

    for path, lineno, func_name, reqs in sorted(violations):
        rel_path = Path(path).relative_to(repo) if path.startswith(str(repo)) else Path(path)
        req_list = ", ".join(f'"{r}"' for r in sorted(reqs))
        print(f"{rel_path}:{lineno}:{func_name} req=[{req_list}]")

    if violations:
        print(f"\n위반 {len(violations)}건 — 조항 마커가 있는데 검증이 없는 테스트입니다")
        return 1

    print("위반 0건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
