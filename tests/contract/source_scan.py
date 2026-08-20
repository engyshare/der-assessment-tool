"""모듈 소스에서 **진짜 import 줄만** 골라낸다 — 독스트링·주석은 포함하지 않는다.

## 왜 한 곳인가

`test_der_contract.py::test_implements_der_without_engine_knowledge` 와
`test_smoke_wave0.py::test_reference_impl_imports_only_contracts` 가 둘 다
*「구현체가 금지된 `core` 하위를 참조하지 않는다」* 를 잰다. 예전에는 전자가
`inspect.getsource(module)` 전문을 문자열로 통째로 검사해, 자원 구현의
독스트링이 설명을 위해 `core.engine` 을 언급하기만 해도 빨간불이 났다
(R38-D4, `.orch/R38/result_verify_sweep.md` 5절②). 후자는 처음부터 줄
단위로 걸러 그 함정에 서지 않았다. 같은 판단을 재는 두 검사가 각자 다른
필터를 들면 한쪽만 고쳐지고 나머지가 같은 함정을 다시 밟는다 — 그래서
「무엇이 진짜 import 줄인가」를 고르는 로직 하나만 여기로 모은다.
금지 대상 목록(어느 `core` 하위를 금지하는가)은 검사마다 다르므로 옮기지
않는다 — 그건 각 조항의 몫이다.

⚠ **이 필터는 줄이 들여쓰기 없이 시작하는지만 본다 — 함수·메서드 안의
지역 import 는 잡지 못한다.** `line.startswith("import ")` 는 앞에 공백이
있으면(들여쓴 줄이면) 거짓이다. 지금 옮기는 것은 「독스트링·주석에 안
걸리는」 형태이지 「모든 import 형태를 다 잡는」 형태가 아니다 — 이 간극은
알려진 한계로 남긴다(R38-D4 result 4절 실측).
"""
from __future__ import annotations


def top_level_import_lines(source: str) -> list[str]:
    """`source` 에서 들여쓰지 않은 `import`/`from` 줄만 뽑는다(양끝 공백 제거).

    독스트링·주석·들여쓴 지역 import 는 이 목록에 들지 않는다.
    """
    return [
        line.strip()
        for line in source.splitlines()
        if line.startswith(("import ", "from "))
    ]
