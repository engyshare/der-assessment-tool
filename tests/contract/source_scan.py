"""모듈 소스에서 **진짜 import 문만** 골라낸다 — 독스트링·주석은 포함하지 않는다.

## 왜 한 곳인가

`test_der_contract.py::test_implements_der_without_engine_knowledge` 와
`test_smoke_wave0.py::test_reference_impl_imports_only_contracts` 가 둘 다
*「구현체가 금지된 `core` 하위를 참조하지 않는다」* 를 잰다. 예전에는 전자가
`inspect.getsource(module)` 전문을 문자열로 통째로 검사해, 자원 구현의
독스트링이 설명을 위해 `core.engine` 을 언급하기만 해도 빨간불이 났다
(R38-D4, `.orch/R38/result_verify_sweep.md` 5절②). 후자는 처음부터 줄
단위로 걸러 그 함정에 서지 않았다. 같은 판단을 재는 두 검사가 각자 다른
필터를 들면 한쪽만 고쳐지고 나머지가 같은 함정을 다시 밟는다 — 그래서
「무엇이 진짜 import 인가」를 고르는 로직 하나만 여기로 모은다. 금지 대상
목록(어느 `core` 하위를 금지하는가)은 검사마다 다르므로 옮기지 않는다 —
그건 각 조항의 몫이다.

## `ast` 로 옮긴 이유 (R39-A)

**줄 필터(`line.startswith(("import ", "from "))`)는 들여쓴 줄을 놓쳤다.**
함수·메서드 본문 안의 지역 import 는 앞에 공백이 있어 이 조건이 거짓이
되고, 그래서 `core/der/pv.py::PV.capex()` 본문 안에
`from core.cba import BCResult` 를 심어도 두 검사 모두 초록불이었다
(`.orch/R39/result_ast_import.md` 1-c 실측). **위반이 통과로 보고되는
조용한 실패이며, 「독스트링·주석에 안 걸리려다 코드까지 놓친」 반대
방향이다.** `ast.walk` 로 전체 트리를 훑으면 들여쓴 지역 import 도
`Import`/`ImportFrom` 노드로 잡힌다 — 애초에 독스트링·주석은 `ast.parse`
대상에 들지 않으므로 그쪽 함정에는 서지 않는다.
"""
from __future__ import annotations

import ast


def imported_module_names(source: str) -> list[str]:
    """`source` 안의 모든 `import`/`from ... import` 문이 참조하는 모듈 경로.

    `ast.walk` 로 트리 전체를 훑으므로 함수·메서드 본문 안의 지역 import 도
    잡는다(R39-A) — 이전의 줄 필터는 들여쓴 줄을 놓쳤다. 독스트링·주석은
    `ast.parse` 대상이 아니므로 애초에 걸리지 않는다.

    반환값은 원문 줄이 아니라 **모듈 경로 문자열**이다: `import foo.bar` 는
    `"foo.bar"`, `from foo.bar import baz` 는 `"foo.bar"` 로 낸다 — 가져오는
    이름(`baz`)은 담지 않는다. 호출자가 재는 것은 「어느 모듈을 참조하는가」이지
    「무엇을 가져오는가」가 아니다.

    ⚠ **상대 import(`from . import x`, `from ..cba import y`)는 절대 경로로
    낼 수 없다.** `ast.ImportFrom.level > 0` 인 경우 절대 경로를 만들려면 이
    함수가 모르는, 임포트하는 쪽의 패키지 이름이 필요하다. 이 경우
    `"." * level + (module or "")` 형태(예: `"."`, `"..cba"`)로 그대로 낸다 —
    절대 경로 문자열과 형태가 겹치지 않도록 하기 위해서다. 호출자가 쓰는
    `"core.XXX"` 접두 대조는 이 점 형태에 걸리지 않는다. 이 저장소의 `core/`
    하위는 지금 상대 import 를 쓰지 않는다(R39-A 확인 — `core/` 전체에
    `^\\s*from \\.` 검색 무결과). **못 내는 형태를 그대로 갈라 적어 둔다** —
    상대 import 를 쓰는 구현이 새로 생기면 이 한계부터 다시 봐야 한다.

    ⚠ **`ast.parse` 는 들여쓰기가 있는 채로 떼어낸 소스(예: 클래스 본문만)를
    받으면 `IndentationError` 로 실패한다.** 두 호출자는 모두
    `inspect.getsource(module)` 로 **모듈 전체**를 넘기므로 이 함수 자신은 그
    전제를 검사하지 않는다.
    """
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                names.append("." * node.level + (node.module or ""))
            else:
                assert node.module is not None  # level 0 이면 문법상 module 이 있다
                names.append(node.module)
    return names
