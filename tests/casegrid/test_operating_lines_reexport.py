"""러너가 `operating_lines` 를 **정말 재수출하는가** — 이름이 아니라 객체로 잰다.

## 왜 이 파일이 있는가

R43-F2 가 연간화 갈래를 `core/casegrid/operating_lines.py` 로 떼면서, 밖에서
`core.casegrid.e2e_runner` 경로로 부르던 이름들을 **러너가 받아 넘기는** 형태로
남겼다(제품 1곳 · 테스트 6곳). 그런데 **그 재수출을 재는 것이 하나도 없었다.**

「호출처가 여섯 곳이니 끊기면 곧 드러난다」는 그물이 아니다 — 끊기면 그 파일들은
`ImportError` 로 **수집 단계에서 죽고**, 수집 단계에서 죽은 것은 *검사가 돌지
않은 것*이지 *검사가 잡은 것*이 아니다. 이 저장소는 그것을 조항으로 적어 두었다:
**«검사를 수행하지 못한 것을 통과로 읽지 않는다»** (§13.0.1 ④ ·
`scripts/check_test_accompaniment.py` 독스트링).

⚠ **더 나쁜 갈래가 하나 더 있다.** 누가 러너 안에 같은 이름의 **사본**을 만들면
import 는 성립하고 전건이 초록불인 채 두 구현이 갈린다. 값이 아니라 **어느
객체를 부르는가**가 틀리므로 어떤 오라클도 그것을 보지 못한다. 그래서 이 파일은
존재가 아니라 **동일성(`is`)** 을 잰다.

## 목록을 손으로 적지 않는다

대상은 `operating_lines.__all__` 에서 온다. 손으로 적으면 이름이 늘 때 따라오지
않고, 그 순간 이 검사는 **아무것도 안 재는 쪽으로 조용히 기운다** — 이 저장소가
반복해 밟은 형태다(「초록불이 된 래칫을 먼저 의심한다」).

그 대가를 함께 적어 둔다: `__all__` 에 이름을 더하면서 러너에 재수출을 두지
않으면 이 검사가 **빨간불**이 된다. **그것이 의도다** — `operating_lines` 의
공개면은 「러너 경로로도 부를 수 있는 것」이라고 F2 가 정했고, 예외를 두려면
이 파일이 아니라 그 규약을 고쳐야 한다. 공개면에서 빼려는 이름은 `__all__` 에
넣지 않으면 된다(모듈 안에서만 쓰는 이름은 애초에 대상이 아니다).

## 소스 문면을 읽지 않는다

R24 가 문면 검사의 헐거움을 잡아 `ast` 로 옮겼다. 여기서는 한 걸음 더 간다 —
**두 모듈을 실제로 import 해 객체를 견준다.** 문면은 무엇이 실행되는지를
말해 주지 못하고, `ast` 는 `import ... as _alias` 가 **같은 객체를 가리키는지**
까지는 말해 주지 못한다.
"""

from __future__ import annotations

import pytest

from core.casegrid import e2e_runner, operating_lines


def _runner_binding(name: str) -> tuple[str, object]:
    """`operating_lines` 의 공개 이름 하나가 **러너에 어떤 이름으로 매여 있는가**.

    러너는 자기가 안에서 쓰는 것에 `_` 를 앞세운다(`_annualise`·`_cost_lines`) —
    밖으로 그 경로를 여는 것과 안에서 부르는 것이 같은 이름일 필요는 없기
    때문이다. 그래서 두 형태를 다 인정한다.

    ⚠ **못 찾으면 건너뛰지 않고 실패한다.** 「대상이 아닌 것으로 처리」는 검사가
    조용히 비는 길이고, 이 파일이 막으려는 것이 정확히 그것이다.
    """
    for candidate in (name, f"_{name}"):
        if hasattr(e2e_runner, candidate):
            return candidate, getattr(e2e_runner, candidate)
    raise AssertionError(
        f"operating_lines.{name} 을 러너가 재수출하지 않는다 — "
        f"`e2e_runner.{name}` 도 `e2e_runner._{name}` 도 없다. "
        "밖에서 러너 경로로 부르던 호출이 수집 단계에서 죽는다"
    )


def test_the_measured_set_is_not_empty() -> None:
    """**무엇을 재는지 먼저 잰다** — 대상이 비면 아래 검사들은 0건을 돈다.

    `__all__` 에서 목록을 가져오는 대가다. 목록이 빈 튜플이 되거나 이름이
    중복돼도 아래 검사는 초록불이므로, 그 상태를 여기서 따로 붙든다.
    """
    names = operating_lines.__all__
    assert names, "operating_lines.__all__ 이 비었다 — 아래 검사가 0건을 돈다"
    assert len(set(names)) == len(names), f"__all__ 에 중복이 있다: {names}"


@pytest.mark.parametrize("name", operating_lines.__all__)
def test_the_runner_hands_over_the_same_object(name: str) -> None:
    """러너 경로로 얻는 것이 선언 자리의 **그 객체**인가 (`is`).

    같은 값을 내는 사본이면 통과시키지 않는다 — 사본은 갈리고, 갈린 뒤에도
    두 쪽이 같은 값을 내는 동안은 아무 검사도 빨간불이 되지 않는다.
    """
    bound_as, handed = _runner_binding(name)
    declared = getattr(operating_lines, name)

    assert handed is declared, (
        f"e2e_runner.{bound_as} 가 operating_lines.{name} 과 **다른 객체**다 — "
        "재수출이 아니라 사본이다"
    )


def test_public_reexports_are_declared_in_the_runner_all() -> None:
    """공개 이름으로 넘기는 것은 러너 `__all__` 에 **적혀 있어야** 한다.

    mypy strict 의 `no_implicit_reexport` 가 그것을 요구한다. 적히지 않으면
    `core/report/dispatch_sections.py` 의
    `from core.casegrid.e2e_runner import DAYS_PER_YEAR` 가 **타입 검사에서만**
    끊긴다 — 런타임 import 는 멀쩡하므로 `pytest` 는 전건 초록불이고, 그래서
    이 자리를 따로 잰다. F2 가 러너에 `__all__` 을 세운 이유가 이것이다.

    `_` 를 앞세운 별칭은 대상이 아니다 — 그쪽은 애초에 비공개 이름이라
    `__all__` 이 다루지 않고, 부르는 쪽이 그 사실을 알고 부른다.
    """
    declared = set(e2e_runner.__all__)
    missing = [
        name
        for name in operating_lines.__all__
        if _runner_binding(name)[0] == name and name not in declared
    ]

    assert not missing, (
        f"러너가 공개 이름으로 넘기면서 `__all__` 에 적지 않았다: {missing} — "
        "mypy strict 가 암묵 재수출을 거부하므로 밖의 import 가 끊긴다"
    )
