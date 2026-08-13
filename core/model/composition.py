"""자원 구성 편집 — WP-16 / FR-201-AC1.

조항 문면: *「**GUI에서 자원 추가/삭제/복제**로 구성 가능하며, 구성 변경 시
**엔진 코드 변경이 발생하지 않는다**」*

조항은 문장 하나지만 요구가 둘이고, **둘째가 검사하기 어려운 쪽이다.**

    앞 절반   추가·삭제·복제 세 연산이 있다              함수가 있으면 성립한다
    뒷 절반   구성이 바뀌어도 엔진 코드가 바뀌지 않는다   무엇을 단언하는가?

뒷 절반을 「엔진 파일이 안 바뀌었다」로 검사할 수는 없다 — 실행 시점에 볼 수
있는 사실이 아니다. 그래서 **바뀌게 만드는 원인**을 막는다:

1. **이 파일에 자원 `tag` 리터럴이 하나도 없다.** 편집기가 `if tag == "PV"` 를
   한 줄이라도 가지면 자원 1종 추가가 **이 파일 수정**을 부르고, 그 순간 조항이
   깨진다. 편집 가능한 자원 목록은 `discover()` 레지스트리에서 온다
   (NFR-207-AC1) — 파일을 놓으면 목록이 늘고 여기는 그대로다.
2. **편집 결과가 `ModelConfig` 데이터일 뿐이다.** 엔진(`Model._build_resources`)은
   편집 전과 **같은 코드**로 편집 후 구성을 짓는다.

`tests/model/test_composition.py` 가 1을 `ast` 로, 2를 실물 구성으로 대조한다.

**왜 제자리에서 고치지 않고 새 `ModelConfig` 를 돌려주는가.** 제자리 변경은
GUI 가 「편집 전」을 잃게 만든다. 그러면 FR-201-AC2(JSON export/import)와
FR-202(같은 전제 위 비교)가 편집 이력을 되짚을 수 없고, 되짚을 수 없는 편집은
사용자가 되돌릴 수 없다.
"""

from __future__ import annotations

import copy
from types import ModuleType
from typing import Any

import core.der
from core.contracts.der import DER
from core.contracts.registry import discover
from core.contracts.validation import ValidationError
from core.model.schemas import DERConfig, ModelConfig

#: 자원 인스턴스를 가리키는 키. 사용자가 짓는 자유 문자열이며 GUI 의 손잡이다.
#: **`field` 경로에는 넣지 않는다** — 열거 불가능한 키가 되기 때문이다
#: (`core/contracts/validation.py` 「경로 관례」).
RESOURCE_NAME_KEY = "name"


def available_resource_tags(package: ModuleType | None = None) -> tuple[str, ...]:
    """GUI 가 「추가」 목록에 내걸 자원 종류 — **레지스트리가 정본이다.**

    고정 목록을 두면 자원 1종 추가가 이 파일 수정을 부른다. `core/der/<tag>.py`
    를 놓으면 여기를 고치지 않고도 목록이 는다 (NFR-207-AC1).
    """
    scanned = package if package is not None else core.der
    return tuple(sorted(discover(scanned, DER)))  # type: ignore[type-abstract]


def resource_name(resource: DERConfig) -> str:
    """자원 인스턴스 이름. 없으면 GUI 가 그 자원을 가리킬 수 없다."""
    name = resource.params.get(RESOURCE_NAME_KEY)
    if not isinstance(name, str) or not name.strip():
        raise ValidationError(
            field="model.resource_name",
            reason=(
                f"자원(tag={resource.tag!r}) 에 {RESOURCE_NAME_KEY!r} 이 없습니다 — "
                "이름이 없으면 삭제·복제할 대상을 지목할 수 없습니다"
            ),
            action=f"자원 파라미터에 {RESOURCE_NAME_KEY!r} 를 빈 문자열이 아닌 값으로 주십시오",
        )
    return name


def resource_names(config: ModelConfig) -> tuple[str, ...]:
    """구성에 담긴 자원 이름 — 선언 순서 그대로. GUI 목록의 순서다."""
    return tuple(resource_name(r) for r in config.resources)


def add_resource(
    config: ModelConfig,
    *,
    tag: str,
    params: dict[str, Any],
    package: ModuleType | None = None,
) -> ModelConfig:
    """자원 추가 (FR-201-AC1 「추가」).

    등록되지 않은 `tag` 는 거부한다 — 통과시키면 엔진이 구성을 짓는 시점에야
    터지고, 그때는 GUI 가 이미 사용자에게 「추가됨」이라고 말한 뒤다.
    """
    known = available_resource_tags(package)
    if tag not in known:
        raise ValidationError(
            field="model.resource_tag",
            reason=(
                f"등록되지 않은 자원 종류입니다: {tag!r}. "
                f"등록된 종류: {', '.join(known) if known else '(없음)'}"
            ),
            action=(
                "등록된 종류 중에서 고르거나, 새 자원이라면 "
                "`core/der/<tag>.py` 를 놓아 등록하십시오"
            ),
        )
    new_resource = DERConfig(tag=tag, params=copy.deepcopy(params))
    name = resource_name(new_resource)
    _reject_duplicate_name(config, name)
    return config.model_copy(update={"resources": [*config.resources, new_resource]})


def remove_resource(config: ModelConfig, name: str) -> ModelConfig:
    """자원 삭제 (FR-201-AC1 「삭제」)."""
    kept = [r for r in config.resources if resource_name(r) != name]
    if len(kept) == len(config.resources):
        raise ValidationError(
            field="model.resource_name",
            reason=(
                f"삭제할 자원이 구성에 없습니다: {name!r}. "
                f"현재 구성: {', '.join(resource_names(config)) or '(비어 있음)'}"
            ),
            action="현재 구성에 있는 자원 이름을 지목하십시오",
        )
    return config.model_copy(update={"resources": kept})


def duplicate_resource(config: ModelConfig, name: str, *, new_name: str) -> ModelConfig:
    """자원 복제 (FR-201-AC1 「복제」) — 원본 **바로 뒤**에 놓는다.

    파라미터는 깊은 복사다. 얕게 복사하면 복제본의 값을 고칠 때 원본이 함께
    바뀌고, 그것은 사용자가 볼 수 없는 곳에서 일어난다.
    """
    source = _find(config, name)
    _reject_duplicate_name(config, new_name)

    clone_params = copy.deepcopy(source.params)
    clone_params[RESOURCE_NAME_KEY] = new_name
    clone = DERConfig(tag=source.tag, params=clone_params)

    resources: list[DERConfig] = []
    for r in config.resources:
        resources.append(r)
        if resource_name(r) == name:
            resources.append(clone)
    return config.model_copy(update={"resources": resources})


def _find(config: ModelConfig, name: str) -> DERConfig:
    for r in config.resources:
        if resource_name(r) == name:
            return r
    raise ValidationError(
        field="model.resource_name",
        reason=(
            f"복제할 자원이 구성에 없습니다: {name!r}. "
            f"현재 구성: {', '.join(resource_names(config)) or '(비어 있음)'}"
        ),
        action="현재 구성에 있는 자원 이름을 지목하십시오",
    )


def _reject_duplicate_name(config: ModelConfig, name: str) -> None:
    """이름 중복 거부 — 겹치면 삭제·복제가 **어느 것을** 가리키는지 모른다."""
    if name in resource_names(config):
        raise ValidationError(
            field="model.resource_name",
            reason=f"이미 같은 이름의 자원이 있습니다: {name!r}",
            action="구성 안에서 유일한 이름을 주십시오",
        )
