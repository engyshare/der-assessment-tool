"""플러그인 자동 등록 — 작업 6.7 / spec NFR-207.

**중앙 등록 파일을 만들지 않는다** (AC1 · §16.1 W-3). 자원 6종을 6명이 만들 때
모두가 `core/der/__init__.py` 한 줄씩을 추가하는 구조라면, 격리는 선언만 있고
실제로는 없다 — 같은 파일의 같은 위치를 6명이 편집한다.

대신 **패키지를 스캔한다.** 신규 자원은 `core/der/<tag>.py` 를 새로 만드는
것으로 끝이며, §16.4 공유 파일 목록의 어느 파일도 바뀌지 않는다 (M1).

**왜 이 모듈이 `core/contracts/` 에 있는가.**

    발견기는 `core.der` 를 **import하지 않는다** — 스캔할 패키지를 인자로 받는다.
    그래서 NFR-208-AC3(`core.contracts` 는 어떤 구획도 import하지 않는다)이
    그대로 성립하고, 동시에 플러그인 규약이 계약 계층에 남는다.

        registry = discover(core.der, DER)       ← 호출부가 패키지를 건넨다

    반대로 발견기가 `core.der` 를 직접 알면, 계약이 구획을 참조하게 되어
    순환이 생기고 「모든 구획이 계약을 경유한다」가 형식적으로만 성립한다.
    `CommonAsset`(`core.asset`)에도 같은 함수를 쓸 수 있게 되는 것은 부수 이득이
    아니라 같은 원인의 결과다 — 발견기가 특정 구획을 모르기 때문이다.

**등록 충돌은 기동 시점에 터진다** (AC2). 늦게 발견되면 두 자원 중 어느 것이
계산에 들어갔는지 결과만 보고는 알 수 없고, 둘 다 그럴듯한 값을 낸다.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType
from typing import TypeVar

T = TypeVar("T")

#: **중간 기반 클래스 표식.** 구상(추상 메서드를 모두 채웠음)이지만 그 자체는
#: 등록 대상이 아닌 클래스가 `REGISTRY_ABSTRACT = True` 로 선언한다.
#: 예: `StandardCommonAsset` — CEMS·HEMS·공용 계량통신이 공유하는 구현 기반이며
#: FR-106-AC2 가 열거한 «유형» 이 아니다.
#:
#: **왜 표식을 요구하고 조용히 건너뛰지 않는가.** 「`tag` 가 없으면 기반 클래스로
#: 본다」로 정하면, `tag` 를 잊은 **진짜 자원**도 함께 조용히 사라진다. 그러면
#: NFR-106(레지스트리 순회 케이스 누락 검사)이 그 자원을 보지 않은 채 통과한다.
#: 표식은 한 줄이고 의도가 드러나며, 잊은 것과 뺀 것을 구분한다.
REGISTRY_ABSTRACT_FLAG = "REGISTRY_ABSTRACT"


class RegistryError(Exception):
    """플러그인 등록이 성립하지 않는다 — **기동을 막는다** (NFR-207-AC2).

    경고로 흘리지 않는 이유: 등록이 깨진 상태로 계산이 진행되면 빠진 자원의
    비용·편익이 통째로 0이 되고, 결과는 그럴듯한 숫자로 남는다.
    """


def load_package_modules(package: ModuleType) -> list[str]:
    """패키지 안의 모듈을 전부 import하고 그 이름을 돌려준다.

    **import해야 클래스가 정의된다.** 파일 이름만 훑어서는 그 안에 무엇이 있는지
    알 수 없고, 파일명과 클래스명을 규약으로 묶으면(`pv.py` → `PV`) 규약이
    조용히 깨질 자리가 하나 더 생긴다 — 대소문자·밑줄 처리에서 `EV_V2G` 같은
    이름이 즉시 문제가 된다 (spec `FR-102-AC1.EV_V2G` 는 리터럴이다).

    비공개 모듈(`_` 로 시작)은 건너뛴다 — 자원이 아닌 내부 도우미를 두는 자리다.
    """
    if not hasattr(package, "__path__"):
        raise RegistryError(
            f"{package.__name__} 은 패키지가 아닙니다. 스캔 대상은 "
            "`core/der/` 처럼 모듈을 담는 패키지입니다"
        )

    loaded: list[str] = []
    for info in pkgutil.iter_modules(package.__path__):
        if info.name.startswith("_"):
            continue
        importlib.import_module(f"{package.__name__}.{info.name}")
        loaded.append(info.name)
    return loaded


def _concrete_subclasses(contract: type[T], prefix: str) -> list[type[T]]:
    """`contract` 의 구상 하위 클래스 중 `prefix` 패키지에 정의된 것.

    **`__module__` 로 걸러내는 것이 이 함수의 핵심이다.** 걸러내지 않으면
    ⓐ 다른 모듈이 import해 둔 클래스가 두 번 잡히고 ⓑ **테스트의 참조 구현이
    등록된다** — `tests/contract/test_smoke_wave0.py` 의 `ReferencePV` 는
    `tag = "PV"` 이므로, pytest 실행 중에 스캔하면 진짜 `PV` 와 충돌하는 「등록
    충돌」이 뜬다. 그 오류는 구현에 아무 잘못이 없는데도 뜨므로 원인을 찾기
    어렵고, 피하려고 참조 구현의 `tag` 를 바꾸면 그것은 계약 위반이다.
    """
    found: dict[str, type[T]] = {}

    def walk(cls: type) -> None:
        for sub in cls.__subclasses__():
            module = getattr(sub, "__module__", "")
            abstract = bool(getattr(sub, "__abstractmethods__", frozenset()))
            if module.startswith(prefix) and not abstract:
                # 같은 클래스가 여러 경로로 도달할 수 있으므로 정규 이름으로 색인
                found[f"{module}.{sub.__qualname__}"] = sub
            walk(sub)

    walk(contract)
    return list(found.values())


def discover(package: ModuleType, contract: type[T]) -> dict[str, type[T]]:
    """`package` 를 스캔해 `contract` 구현을 `tag` 로 색인한다 (NFR-207-AC1).

        REGISTRY = discover(core.der, DER)        # {"PV": PV, "ESS": ESS, …}

    `tag` 는 spec 조항 ID(`FR-102-AC1.<키>`)와 **같은 리터럴**이다. 클래스명이나
    파일명에서 파생시키지 않는 이유는 파생이 규약을 하나 더 만들기 때문이다 —
    파생하는 순간 원본이 바뀔 때 키가 조용히 다른 것을 가리킨다 (v0.7 사고).

    다음 셋을 **기동 시점에 오류로 막는다** (AC2).

        · 같은 `tag` 를 두 클래스가 선언       어느 것이 계산에 들어갔는지 모른다
        · 구상 구현이 `tag` 를 선언하지 않음   레지스트리에서 조용히 사라진다
        · `tag` 가 빈 문자열                   위와 같으나 더 찾기 어렵다

    유형이 아닌 공유 기반 클래스는 `REGISTRY_ABSTRACT = True` 로 **명시적으로**
    빠진다 — 잊은 것과 뺀 것을 구분하기 위해서다.

    **`tag` 미선언을 오류로 두는 것이 중요하다.** 건너뛰면 그 자원은 목록에
    나타나지 않고, NFR-106(레지스트리를 순회해 검증 케이스 누락을 검사)이
    **그 자원을 아예 보지 않은 채 초록불**이 된다 — 순회 검사가 검사 대상을
    잃는 것이므로 누락 하나가 아니라 검사 자체가 무의미해진다.
    """
    # **지금 파일로 존재하는 모듈만 자원으로 센다.**
    #
    # `__subclasses__()` 는 클래스 객체가 살아 있는 한 계속 돌려준다. 파일을
    # 지우고 `sys.modules` 에서 빼도 **그 클래스를 참조하는 무언가가 남아
    # 있으면 레지스트리에 계속 잡힌다.** 08-09 에 실제로 그랬다 — 인수 판정
    # 시험(17.10·17.11)이 임시 자원 파일을 놓았다 지웠는데, 같은 프로세스
    # 안에서 클래스가 살아남아 **자원이 8종인데 10종으로 세어졌고** 계약
    # 테스트 3건이 깨졌다.
    #
    # 그 실패는 «시끄러운» 쪽이라 드러났지만 **반대 방향이 더 위험하다** —
    # 유령 자원이 검증 케이스 없이 등록되면 NFR-106(순회 케이스 누락 검사)이
    # 없는 자원을 검사하려 들거나, 세지 말아야 할 것을 세고 통과한다.
    #
    # 그래서 이름 목록으로 좁힌다. **파일이 없으면 자원이 아니다.**
    live = {f"{package.__name__}.{name}"
            for name in load_package_modules(package)}
    prefix = f"{package.__name__}."

    registry: dict[str, type[T]] = {}
    owners: dict[str, str] = {}
    missing: list[str] = []

    for cls in _concrete_subclasses(contract, prefix):
        if cls.__module__ not in live:
            continue    # 파일이 사라진 모듈의 잔존 클래스 — 자원이 아니다
        where = f"{cls.__module__}.{cls.__qualname__}"
        # **표식은 선언한 클래스에만 적용된다** — `getattr` 로 보면 상속되어
        # `StandardCommonAsset` 을 상속한 CEMS·HEMS·공용 계량통신 **셋 전부가**
        # 등록에서 빠진다. 그 상태는 「공통설비가 없는 단지」로 계산되고, CEMS
        # 구축비·운영비가 통째로 사라지는데 결과는 그럴듯하다 (FR-106 근거).
        if cls.__dict__.get(REGISTRY_ABSTRACT_FLAG, False):
            continue    # 구상이지만 유형이 아닌 공유 기반 (표식으로 명시했다)
        tag = getattr(cls, "tag", None)
        if not isinstance(tag, str) or not tag:
            missing.append(where)
            continue
        if tag in registry:
            raise RegistryError(
                f"등록 충돌 — `tag` 가 중복됩니다: {tag!r}\n"
                f"  · {owners[tag]}\n"
                f"  · {where}\n"
                "둘 중 어느 것이 계산에 들어갔는지 결과만 보고는 알 수 없고, "
                "둘 다 그럴듯한 값을 냅니다 (NFR-207-AC2). "
                "`tag` 는 spec `FR-102-AC1.<키>` 와 같은 리터럴이므로 "
                "한쪽이 조항을 잘못 가리키고 있습니다"
            )
        registry[tag] = cls
        owners[tag] = where

    if missing:
        raise RegistryError(
            "`tag` 를 선언하지 않은 구현이 있습니다: " + ", ".join(sorted(missing))
            + "\n건너뛰면 그 자원은 레지스트리에 나타나지 않고, NFR-106(순회 "
            "케이스 누락 검사)이 그 자원을 보지 않은 채 통과합니다 — 누락 하나가 "
            "아니라 검사 자체가 무의미해집니다"
        )

    if not registry:
        raise RegistryError(
            f"{package.__name__} 에서 {contract.__name__} 구현을 하나도 찾지 "
            "못했습니다. 스캔이 성립하지 않은 것을 「구현이 없다」로 읽지 "
            "않습니다 (§13.0.1 ④)"
        )
    return registry
