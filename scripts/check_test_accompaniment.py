"""NFR-105 게이트 ② 테스트 동반 검사 — 작업 2.6.

조항 문면: *"`core/` 하위 구현 파일이 변경된 PR에 **대응** 테스트 파일 변경이
없으면 자동 실패"* (NFR-105 Measurement 2).

**이 검사가 막는 것은 「테스트를 잊는 것」이다.** TDD 여부 자체는 기계가 볼 수
없다 — 커밋 순서를 보는 Measurement 3이 그것을 근사하지만 경고에 그친다(스쿼시
병합 등 정당한 예외가 있다). 반면 *"구현만 고치고 테스트는 손대지 않았다"* 는
diff에서 완전히 판정된다. 그래서 이 셋 중 이것만 차단으로 켤 수 있다.

**「대응」을 넓게도 좁게도 잡을 수 없다.**

    너무 넓게 (아무 테스트나 바뀌면 통과)
        core 파일 6개를 고치고 관계없는 테스트 한 줄을 고치면 통과한다.
        게이트가 있는데 아무것도 막지 않는 상태이며, 초록불이므로 그 사실이
        드러나지 않는다.

    너무 좁게 (파일명 규약만 인정: core/der/pv.py ↔ tests/der/test_pv.py)
        이 저장소는 이미 규약을 벗어난다 — `core/contracts/der.py` 의 대응
        테스트는 `tests/contract/test_der_contract.py` 다. 규약만 보면 계약을
        고칠 때마다 정당한 PR이 막히고, 막히는 게이트는 꺼진다.

그래서 **두 경로를 모두 인정한다** — ⓐ 변경된 테스트가 그 모듈을 import 하거나
ⓑ 파일명 규약(`test_<stem>.py`)에 맞는다. 어느 쪽도 없으면 위반이다.

**import 는 `ast` 로 읽는다.** 파일을 문자열로 훑으면 *"`core.der.pv` 를 예로
들면"* 같은 **주석·독스트링의 언급이 대응 테스트로 세어진다.** 이 저장소가 여섯
번 걸린 유형(*"검사 도구를 설명하는 문장이 그 검사에 걸린다"*)의 반대 방향이며,
결과가 더 나쁘다 — 서술이 선언으로 세어지면 **게이트가 조용히 초록불**이 된다.

**패키지 import 를 상위 포섭으로 인정한다.** `tests/contract/test_registry.py`
는 `core.der` 를 import해 레지스트리를 순회한다(NFR-106). `core/der/pv.py` 가
바뀌면 그 순회가 실제로 다시 검증하므로 대응 테스트로 센다. 이것은 의도된 느슨함
이고, 그래서 보고에 **어느 경로로 인정되었는지** 적는다 — 느슨함이 보이지 않으면
그것에 기대는 PR이 늘어난다.

**코드가 없는 파일은 대상이 아니다.** 조항의 주어는 *"모든 **계산 코드**"* 다.
패키지 표식 `__init__.py` 의 독스트링을 고쳤다고 테스트를 요구하면 그 요구가
정당하지 않고, 정당하지 않은 요구는 게이트를 꺼지게 만든다. 판정은 `ast` 로
한다 — 독스트링·주석·`from __future__` 뿐이면 계산 코드가 아니다.

**그리고 그 원칙은 diff 에도 걸린다.** 조항의 주어는 「구현 변경」이지 「구현이
있는 파일의 변경」이 아니다. 파일 단위로만 보면 `core/der/pv.py` 의 독스트링 한
줄을 고친 커밋도 **항상** 동반 테스트를 요구한다 — 이미 코드가 있는 파일이기
때문이다. 그래서 **이전 이미지**(`_gitdiff.base_reader`)를 함께 읽어, 독스트링·
주석을 뺀 나머지 AST 가 실제로 달라졌을 때만 구현 변경으로 센다. 이전 이미지가
**없는** 파일(신규)은 견줄 것이 없으므로 종전대로 판정한다 — 「이전이 없다」와
「이전과 같다」는 다른 사실이다.

    종료 코드 0  전건 동반됨 (또는 대상 변경 없음)
    종료 코드 1  동반되지 않은 구현 변경이 있다
    종료 코드 2  검사 자체가 성립하지 않음 (기준 ref 없음·빈 diff 등)

**종료 코드 2가 이 검사의 핵심이다.** 기준 ref 를 못 찾으면 `git diff` 는 빈
목록을 내고, 빈 목록은 「위반 없음」과 구별되지 않는다. 08-08에 매핑 게이트에서
만난 것과 같은 구멍이다(`|| true` 로 종료 코드를 버리자 결함 시 파일이 안 바뀌어
diff가 통과했다). **검사를 수행하지 못한 것을 통과로 읽지 않는다** (§13.0.1 ④).
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from _gitdiff import Change, CheckError, base_reader, changed_files, head_reader

#: 조항 문면이 지정한 대상은 `core/` 다. `app/`·`infra/` 를 넣지 않는 것은
#: 임의 축소가 아니라 조항을 넓히지 않는 것이다 — 넓히려면 spec 개정(§16.5)이며,
#: 검사가 조항보다 강하면 「조항에 없는 이유로 막혔다」는 반발이 게이트를 끈다.
IMPL_ROOT = "core"

TEST_ROOT = "tests"

#: 독스트링을 가질 수 있는 노드. `ast.get_docstring` 이 받는 것과 같은 집합이다.
DOCSTRING_HOLDERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)

#: 삭제된 구현은 테스트를 요구하지 않고(고칠 코드가 없다), 삭제된 테스트는 동반
#: 으로 세지 않는다(테스트를 지워서 게이트를 통과하는 경로를 막는다).
#: 판정은 `Change.deleted` 가 한다 — `_gitdiff` 단독 소유다.


@dataclass(frozen=True)
class Violation:
    module: str
    path: str


@dataclass(frozen=True)
class Accompanied:
    module: str
    path: str
    by: str
    how: str


def module_of(path: str) -> str:
    """`core/der/pv.py` → `core.der.pv`, `core/der/__init__.py` → `core.der`."""
    parts = Path(path).with_suffix("").parts
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def has_code(source: str) -> bool:
    """계산 코드가 있는가 — 독스트링·주석·`from __future__` 만이면 없다.

    `ast` 로 판정하는 이유: 정규식으로는 `\"\"\"` 가 문자열 리터럴 안에 있는
    경우와 구분되지 않고, 그 오판이 어느 방향으로 틀렸는지 드러나지 않는다.
    문법 오류 파일은 **코드가 있는 것으로 본다** — 판정할 수 없는 것을 «없음»
    으로 처리하면 검사가 조용히 느슨해진다.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return True

    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    for node in body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            continue
        return True
    return False


def code_shape(source: str) -> str | None:
    """`has_code()` 가 보는 것과 같은 층위의 정규형 — 두 시점을 견주기 위한 것.

    독스트링·주석·`from __future__` 를 뺀 나머지 AST 를 덤프한다. 주석은 애초에
    AST 에 없고, 독스트링만 골라내면 **「설명을 고쳤다」와 「계산을 고쳤다」가
    갈린다.** 줄 번호를 담지 않으므로(`ast.dump` 의 기본값) 코드가 아래로 밀린
    것만으로는 달라지지 않는다.

    **정규식으로 벗기지 않는 이유는 `has_code` 와 같다** — `\"\"\"` 가 문자열
    리터럴 안에 있는 경우와 구분되지 않고, 그 오판이 어느 방향으로 틀렸는지
    드러나지 않는다.

    문법 오류는 `None` 이다. 판정할 수 없는 것을 «같다» 로 처리하면 검사가 조용히
    느슨해진다 — `has_code` 가 문법 오류를 «코드 있음» 으로 보는 것과 같은 방향의
    보수적 처리다.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    for node in list(ast.walk(tree)):
        if not isinstance(node, DOCSTRING_HOLDERS):
            continue
        body = list(node.body)
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            body = body[1:]
        if isinstance(node, ast.Module):
            body = [
                n for n in body
                if not (isinstance(n, ast.ImportFrom) and n.module == "__future__")
            ]
        node.body = body

    return ast.dump(tree)


def code_changed(before: str | None, after: str) -> bool:
    """이번 diff 가 **계산 코드를** 바꿨는가.

    조항의 주어는 「구현 변경」이지 「구현이 있는 파일의 변경」이 아니다. 파일에
    코드가 있는지만 보면 `core/der/pv.py` 의 독스트링 한 줄을 고친 커밋도 항상
    동반 테스트를 요구하고, **정당하지 않은 요구는 게이트를 꺼지게 만든다** —
    이 파일의 독스트링이 「코드가 없는 파일은 대상이 아니다」로 이미 적어 둔
    원칙을 파일 단위에서만 지키고 diff 단위에서는 안 지키던 상태였다.

    **`before is None` 은 「이전에 없었다」이며 「이전과 같다」와 다르다.** 신규
    파일은 견줄 이전이 없으므로 종전 판정(파일에 코드가 있는가)이 그대로 선다 —
    호출부가 이미 `has_code` 로 걸렀다.
    """
    if before is None:
        return True
    shape_before = code_shape(before)
    shape_after = code_shape(after)
    if shape_before is None or shape_after is None:
        return True
    return shape_before != shape_after


def imported_core_modules(source: str) -> set[str]:
    """테스트가 import 한 `core.*` 모듈의 점 이름.

    `from core.der import pv` 는 `core.der.pv` 로도 센다 — 문법은 «패키지에서
    이름을 가져온다» 이지만 그 이름이 모듈이면 실제로 그 모듈을 쓴다. 이름이
    모듈이 아니라 클래스여도(예: `from core.der.pv import PV`) 손해는 없다:
    `core.der.PV` 라는 모듈은 존재하지 않으므로 아무것도 포섭하지 않는다.

    **주석·독스트링은 세지 않는다.** 파서를 쓰는 것이 곧 그 보장이다 — 서술이
    선언으로 세어지면 게이트가 조용히 초록불이 된다.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names if _is_core(a.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module or not _is_core(node.module):
                continue
            found.add(node.module)
            found.update(f"{node.module}.{a.name}" for a in node.names)
    return found


def _is_core(dotted: str) -> bool:
    return dotted == IMPL_ROOT or dotted.startswith(f"{IMPL_ROOT}.")


def covers(imported: set[str], module: str) -> str | None:
    """`module` 을 포섭하는 import 가 있으면 그 근거를 돌려준다.

    상위 패키지도 인정한다 — 레지스트리 순회 테스트(NFR-106)는 `core.der` 만
    import하고 자원 파일 전건을 실제로 검증한다. 다만 `core` 자체는 인정하지
    않는다: `import core` 한 줄로 저장소 전체가 포섭되면 게이트가 사라진다.
    """
    if module in imported:
        return f"import {module}"
    for candidate in sorted(imported, key=len, reverse=True):
        if candidate == IMPL_ROOT:
            continue
        if module.startswith(f"{candidate}."):
            return f"import {candidate} (상위 패키지)"
    return None


def check(
    changes: list[Change],
    read: Callable[[str], str],
    read_before: Callable[[str], str | None] | None = None,
) -> tuple[list[Violation], list[Accompanied]]:
    """변경 목록을 판정한다.

    `read(path) -> str` 는 «변경 후» 소스를, `read_before(path) -> str | None` 은
    «변경 전» 소스를 읽는다(`None` 은 그 시점에 그 파일이 **없었다**는 뜻이다).
    git 을 직접 부르지 않는 이유는 이 함수가 임의의 diff 에 대해 검사 가능해야
    하기 때문이다 — 검증 케이스가 실제 커밋을 만들지 않고도 판정 논리를 시험할
    수 있다.

    `read_before` 를 안 주면 **이전 이미지 없이** 판정한다 — 모든 변경을 신규로
    보는 것과 같아 「파일에 코드가 있는가」만 남는다. 이전을 못 읽는 상황에서
    조용히 느슨해지지 않게 하려는 기본값이다(안 주면 더 많이 잡는다).
    """
    read_source = read

    impl = [
        c for c in changes
        if not c.deleted and c.path.startswith(f"{IMPL_ROOT}/") and c.path.endswith(".py")
    ]
    tests = [
        c for c in changes
        if not c.deleted and c.path.startswith(f"{TEST_ROOT}/") and c.path.endswith(".py")
    ]

    # 변경된 테스트가 import한 모듈과 파일명 규약을 미리 모은다.
    imported_by: dict[str, set[str]] = {}
    stems: dict[str, str] = {}
    for t in tests:
        imported_by[t.path] = imported_core_modules(read_source(t.path))
        stem = Path(t.path).stem
        if stem.startswith("test_"):
            stems.setdefault(stem[len("test_"):], t.path)

    violations: list[Violation] = []
    accompanied: list[Accompanied] = []
    for c in impl:
        after = read_source(c.path)
        if not has_code(after):
            continue
        # 파일에 코드가 있다는 것과 **이번 diff 가 코드를 바꿨다**는 것은 다르다.
        # 이전 이미지를 읽을 수 있을 때만 뒤엣것까지 본다.
        if read_before is not None and not code_changed(read_before(c.path), after):
            continue
        module = module_of(c.path)

        hit: tuple[str, str] | None = None
        for path, imported in imported_by.items():
            reason = covers(imported, module)
            if reason:
                hit = (path, reason)
                break
        if hit is None:
            conventional = stems.get(Path(c.path).stem)
            if conventional:
                hit = (conventional, f"파일명 규약 test_{Path(c.path).stem}.py")

        if hit is None:
            violations.append(Violation(module=module, path=c.path))
        else:
            accompanied.append(
                Accompanied(module=module, path=c.path, by=hit[0], how=hit[1])
            )
    return violations, accompanied


# ── git 연결부 ───────────────────────────────────────────────────────
#
# 기준 ref 해석과 변경 목록은 `_gitdiff` 단독 소유다. 게이트 ①도 같은 것을
# 필요로 하고, 각자 쓰면 반드시 갈리며 갈린 쪽이 느슨하면 그 게이트가 조용히
# 무력화된다 (§16.1 W-4).


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="NFR-105 게이트 ② 테스트 동반 검사 (작업 2.6)"
    )
    parser.add_argument("--base", required=True,
                        help="비교 기준 ref (예: origin/main). PR 의 대상 브랜치")
    parser.add_argument("--root", default=".", help="저장소 루트")
    parser.add_argument("--allow-empty", action="store_true",
                        help="변경 파일 0건을 통과로 본다. 로컬 확인용이며 CI 에서 "
                             "쓰지 않는다 — 빈 diff 는 기준 ref 오류의 증상이다")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    print(f"테스트 동반 검사 — 기준 {args.base}")
    print("─" * 78)

    try:
        changes = changed_files(args.base, root)
        read_before = base_reader(args.base, root)
    except CheckError as exc:
        print(f"검사를 수행할 수 없습니다: {exc}", file=sys.stderr)
        print("검사를 수행하지 못한 것을 통과로 읽지 않습니다 (§13.0.1 ④)",
              file=sys.stderr)
        return 2

    if not changes and not args.allow_empty:
        print("변경된 파일이 0건입니다 — PR 에서는 일어날 수 없습니다.",
              file=sys.stderr)
        print(f"기준 ref({args.base}) 가 HEAD 와 같은지 확인하십시오. "
              "0건을 통과로 읽으면 게이트가 조용히 무력화됩니다 (§13.0.1 ④)",
              file=sys.stderr)
        return 2

    violations, accompanied = check(changes, head_reader(root), read_before)

    for a in accompanied:
        print(f"· {a.path}")
        print(f"    ← {a.by}  [{a.how}]")
    if not accompanied and not violations:
        print(f"· `{IMPL_ROOT}/` 하위 구현 변경 없음 — 판정 대상이 없습니다")
    print("─" * 78)

    if violations:
        print(f"동반 테스트가 없는 구현 변경 {len(violations)}건 — NFR-105 위반")
        for v in violations:
            print(f"  · {v.path}")
            stem = Path(v.path).stem
            print("      대응 테스트를 함께 변경하십시오. 인정되는 경로는 두 "
                  "가지입니다 —")
            print(f"      ⓐ `{v.module}` 을 import 하는 테스트")
            print(f"      ⓑ 파일명 규약 `{TEST_ROOT}/<구획>/test_{stem}.py`")
        print()
        print("  **테스트를 지워서 통과시킬 수는 없습니다** — 삭제된 테스트는")
        print("  동반으로 세지 않습니다. 구현만 고쳐야 하는 정당한 경우라면")
        print("  그것이 계산 코드인지 다시 보십시오 (NFR-105 의 주어는 계산 코드다).")
        return 1

    print(f"통과 — 구현 변경 {len(accompanied)}건 전건 동반됨")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
