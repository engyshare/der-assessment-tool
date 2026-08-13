"""FR-201-AC1 자원 구성 편집 — WP-16.

조항: *「**GUI에서 자원 추가/삭제/복제**로 구성 가능하며, 구성 변경 시 **엔진
코드 변경이 발생하지 않는다**」*

**뒷 절반을 어떻게 검사하는가가 이 파일의 요점이다.** 「엔진 파일이 안 바뀌었다」는
실행 시점에 볼 수 있는 사실이 아니므로, **바뀌게 만드는 원인** 둘을 붙든다.

① 편집기가 자원 `tag` 를 문면으로 안다 → 자원 1종 추가가 편집기 수정을 부른다
② 편집 결과가 데이터가 아니라 코드 경로다 → 구성마다 엔진 분기가 늘어난다

①은 `ast` 로 편집기 소스의 **문자열 상수**를 훑어 대조한다 (독스트링은 뺀다 —
이 저장소는 「검사 도구를 설명하는 문장이 그 검사에 걸린다」를 여섯 번 만났다).
②는 편집한 구성을 **손대지 않은 `Model`** 에 넣어 실물 인스턴스를 만들어 본다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import core.der
from core.contracts.assumptions import AssumptionProvider, AssumptionValue
from core.contracts.der import DER
from core.contracts.registry import discover
from core.contracts.validation import ValidationError
from core.model.composition import (
    add_resource,
    available_resource_tags,
    duplicate_resource,
    remove_resource,
    resource_names,
)
from core.model.model import Model
from core.model.schemas import DERConfig, ModelConfig

_COMPOSITION_SOURCE = Path(__file__).resolve().parents[2] / "core/model/composition.py"


class _Assumptions(AssumptionProvider):
    """정책 파라미터 하나만 내는 최소 전제 — 엔진이 구성을 짓는 데 필요한 것."""

    @property
    def set_name(self) -> str:
        return "test"

    @property
    def set_version(self) -> str:
        return "1.0"

    def get(self, key: str) -> AssumptionValue | None:
        if key != "tax.vat_rate":
            return None
        return AssumptionValue(
            key=key,
            value=0.1,
            value_unit="소수",
            base_year="2026",
            applicable_scope="",
            derivation_method="가정",
            source="",
            verified_at=None,
            confidence="가정",
        )


def _base_config() -> ModelConfig:
    return ModelConfig(
        name="구성 편집 대상",
        resources=[
            DERConfig(
                tag="PV",
                params={"name": "옥상PV", "capacity_kw": 100.0, "capacity_factor": 0.15},
            )
        ],
    )


def _string_constants_excluding_docstrings(source: Path) -> tuple[str, ...]:
    """소스의 문자열 상수 — **독스트링과 주석은 제외한다.**

    독스트링을 포함하면 「자원 종류를 문면으로 알지 않는다」를 설명하는 문장
    자신이 위반으로 잡힌다. 주석은 `ast` 에 아예 남지 않으므로 저절로 빠진다.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"))
    docstring_nodes: set[int] = set()
    for node in ast.walk(tree):
        # 독스트링은 «값이 문자열 상수인 Expr 문» 이다 — 모듈·클래스·함수 공통
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            docstring_nodes.add(id(node.value))
    return tuple(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstring_nodes
    )


@pytest.mark.req("FR-201-AC1")
def test_add_delete_duplicate_edit_the_configuration() -> None:
    """세 연산이 구성을 바꾸고, 원본은 그대로 남는다."""
    base = _base_config()

    added = add_resource(
        base, tag="ESS", params={"name": "지하ESS", "capacity_kwh": 200.0}
    )
    assert resource_names(added) == ("옥상PV", "지하ESS")
    assert resource_names(base) == ("옥상PV",), "편집이 원본을 제자리에서 고쳤다"

    duplicated = duplicate_resource(added, "옥상PV", new_name="차양PV")
    # 복제본은 원본 **바로 뒤**에 놓인다 — GUI 목록에서 나란히 보여야 한다
    assert resource_names(duplicated) == ("옥상PV", "차양PV", "지하ESS")

    removed = remove_resource(duplicated, "지하ESS")
    assert resource_names(removed) == ("옥상PV", "차양PV")


@pytest.mark.req("FR-201-AC1")
def test_duplicate_copies_parameters_without_sharing_them() -> None:
    """복제본은 원본과 값이 같고, 고쳐도 원본이 따라 바뀌지 않는다."""
    base = _base_config()
    duplicated = duplicate_resource(base, "옥상PV", new_name="차양PV")

    original, clone = duplicated.resources[0], duplicated.resources[1]
    assert clone.tag == original.tag
    assert clone.params["capacity_kw"] == original.params["capacity_kw"]

    clone.params["capacity_kw"] = 999.0
    assert original.params["capacity_kw"] == 100.0, (
        "복제본을 고쳤는데 원본이 함께 바뀌었다 — 파라미터를 얕게 복사했다"
    )


@pytest.mark.req("FR-201-AC1")
def test_engine_builds_the_edited_configuration_without_engine_changes() -> None:
    """편집한 구성을 **손대지 않은 엔진**이 그대로 짓는다.

    조항의 「엔진 코드 변경이 발생하지 않는다」의 실물 절반이다 — 세 연산을 거친
    구성이 `Model` 의 기존 경로 하나로 실물 인스턴스가 된다.
    """
    provider = _Assumptions()
    edited = remove_resource(
        duplicate_resource(
            add_resource(
                _base_config(),
                tag="ESS",
                params={"name": "지하ESS", "capacity_kwh": 200.0},
            ),
            "옥상PV",
            new_name="차양PV",
        ),
        "지하ESS",
    )

    model = Model(edited, provider)

    assert [r.name for r in model.resources] == ["옥상PV", "차양PV"]
    # 복제본도 정책 파라미터 주입을 받는다 — 엔진 경로를 함께 지났다는 증거다
    Model.validate_injection(model.resources, provider)
    assert all(r.vat_rate == 0.1 for r in model.resources)


@pytest.mark.req("FR-201-AC1")
def test_editor_does_not_name_any_resource_tag() -> None:
    """편집기 소스에 자원 `tag` 문면이 하나도 없다.

    있으면 자원 1종 추가가 **편집기 수정**을 부르고, 그 순간 조항의 「구성 변경
    시 엔진 코드 변경이 발생하지 않는다」가 깨진다.
    """
    tags = set(discover(core.der, DER))  # type: ignore[type-abstract]
    assert len(tags) > 1, "레지스트리가 비었으면 이 검사는 아무것도 붙들지 않는다"

    literals = set(_string_constants_excluding_docstrings(_COMPOSITION_SOURCE))
    offending = sorted(tags & literals)
    assert not offending, (
        f"편집기가 자원 종류를 문면으로 알고 있다: {offending}. "
        "목록은 `available_resource_tags()` 로 레지스트리에서 가져와야 한다"
    )


@pytest.mark.req("FR-201-AC1")
def test_available_tags_are_exactly_the_registry_tags() -> None:
    """추가 가능한 종류 목록이 레지스트리와 **같다**.

    부분집합만 검사하면 고정 목록을 들고 있어도 통과한다 — 새 자원 파일을 놓아도
    목록이 늘지 않는 상태가 초록불이 된다.
    """
    registry_tags = tuple(sorted(discover(core.der, DER)))  # type: ignore[type-abstract]
    assert available_resource_tags() == registry_tags


@pytest.mark.req("FR-201-AC1")
def test_unknown_tag_is_refused_with_three_elements() -> None:
    """등록되지 않은 종류는 GUI 단계에서 거부된다 (NFR-303 3요소)."""
    with pytest.raises(ValidationError) as caught:
        add_resource(_base_config(), tag="가상자원", params={"name": "X"})

    error = caught.value
    assert error.field == "model.resource_tag"
    assert "가상자원" in error.reason
    # 조치 칸이 «어떻게 고치는가» 를 말한다 — 등록된 종류가 사유에 실려 있다
    assert "PV" in error.reason
    assert error.action.strip()


@pytest.mark.req("FR-201-AC1")
def test_name_collisions_and_missing_names_are_refused() -> None:
    """이름이 겹치거나 없으면 «어느 자원인가» 를 지목할 수 없으므로 거부한다."""
    base = _base_config()

    with pytest.raises(ValidationError, match="이미 같은 이름"):
        add_resource(base, tag="ESS", params={"name": "옥상PV"})

    with pytest.raises(ValidationError, match="이미 같은 이름"):
        duplicate_resource(base, "옥상PV", new_name="옥상PV")

    with pytest.raises(ValidationError, match="name"):
        add_resource(base, tag="ESS", params={"capacity_kwh": 200.0})

    with pytest.raises(ValidationError, match="구성에 없습니다"):
        remove_resource(base, "없는자원")

    with pytest.raises(ValidationError, match="구성에 없습니다"):
        duplicate_resource(base, "없는자원", new_name="사본")
