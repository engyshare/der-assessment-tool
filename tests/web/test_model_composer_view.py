"""FR-201-AC1 「GUI에서」의 화면 — 자원 추가·삭제·복제 조작이 실제로 있는가.

경로가 있어도 화면에 조작이 없으면 조항의 「GUI에서 … 구성 가능」이 성립하지
않는다. 그래서 여기서 붙드는 것은 셋이다.

① 세 조작이 각각 **자기 폼과 자기 경로**를 갖는다 — 하나가 빠지면 걸린다
② 자원 종류 목록이 **레지스트리와 같다** — 화면이 종류를 자기 안에 적지 않는다
③ 템플릿 소스에 자원 `tag` 문면이 없다 — ②를 우연히 만족하는 하드코딩을 막는다

②만 검사하면 템플릿에 여섯 종을 적어 두고도 통과한다. ③이 그것을 막는다.
"""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

import pytest

import core.der
from core.contracts.der import DER
from core.contracts.registry import discover
from core.model.schemas import DERConfig, ModelConfig
from web.render import model_composer_context, render_model_composer

_TEMPLATE = Path(__file__).resolve().parents[2] / "web/templates/model_composer.html"


class _ComposerParser(HTMLParser):
    """화면에서 조작·목록만 뽑는다 — 문자열 검색으로는 폼 경계를 볼 수 없다."""

    def __init__(self) -> None:
        super().__init__()
        self.form_actions: list[str] = []
        self.buttons: list[tuple[str, str]] = []  # (value, 소속 폼 action)
        self.option_values: list[str] = []
        self.resource_rows: list[str] = []
        self._current_action = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {k: (v or "") for k, v in attrs}
        if tag == "form":
            self._current_action = attributes.get("action", "")
            self.form_actions.append(self._current_action)
        elif tag == "button":
            self.buttons.append((attributes.get("value", ""), self._current_action))
        elif tag == "option":
            self.option_values.append(attributes.get("value", ""))
        elif tag == "tr" and "data-resource-name" in attributes:
            self.resource_rows.append(attributes["data-resource-name"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._current_action = ""


def _config() -> ModelConfig:
    return ModelConfig(
        name="화면모델",
        resources=[
            DERConfig(
                tag="PV",
                params={"name": "옥상PV", "capacity_kw": 100.0, "capacity_factor": 0.15},
            ),
            DERConfig(tag="ESS", params={"name": "지하ESS", "capacity_kwh": 200.0}),
        ],
    )


def _parse(html: str) -> _ComposerParser:
    parser = _ComposerParser()
    parser.feed(html)
    return parser


@pytest.mark.req("FR-201-AC1")
def test_view_offers_add_delete_and_duplicate_each_with_its_own_path() -> None:
    """세 조작이 화면에 있고 서로 다른 경로를 누른다."""
    parsed = _parse(render_model_composer(model_composer_context(_config())))

    actions_by_operation = {value: action for value, action in parsed.buttons}
    for operation in ("add", "delete", "duplicate"):
        assert operation in actions_by_operation, (
            f"화면에 {operation} 조작이 없다 — 조항이 요구하는 세 조작 중 하나가 빠졌다"
        )

    # 세 경로가 **서로 다르다.** 같으면 버튼만 셋이고 조작은 하나다
    assert len(set(actions_by_operation.values())) == 3, actions_by_operation
    assert actions_by_operation["add"].endswith("/resources")
    assert actions_by_operation["duplicate"].endswith("/duplicate")
    assert "지하ESS" in actions_by_operation["delete"] or "옥상PV" in (
        actions_by_operation["delete"]
    )


@pytest.mark.req("FR-201-AC1")
def test_view_lists_every_configured_resource() -> None:
    """구성의 자원이 모두 행으로 나온다 — 없는 자원은 삭제·복제할 수 없다."""
    parsed = _parse(render_model_composer(model_composer_context(_config())))
    assert parsed.resource_rows == ["옥상PV", "지하ESS"]


@pytest.mark.req("FR-201-AC1")
def test_resource_type_choices_are_exactly_the_registry_tags() -> None:
    """「추가」 목록이 레지스트리와 같다."""
    parsed = _parse(render_model_composer(model_composer_context(_config())))
    registry_tags = sorted(discover(core.der, DER))  # type: ignore[type-abstract]
    assert parsed.option_values == registry_tags
    assert len(registry_tags) > 1, "레지스트리가 비면 이 검사는 아무것도 붙들지 않는다"


@pytest.mark.req("FR-201-AC1")
def test_template_does_not_name_any_resource_tag() -> None:
    """템플릿 소스에 자원 종류 문면이 없다.

    적혀 있으면 자원 1종 추가가 **화면 수정**을 부르고, 조항의 「엔진 코드 변경이
    발생하지 않는다」가 서버에서만 성립한다.
    """
    source = _TEMPLATE.read_text(encoding="utf-8")
    offending = sorted(
        tag
        for tag in discover(core.der, DER)  # type: ignore[type-abstract]
        if tag in source
    )
    assert not offending, (
        f"템플릿이 자원 종류를 문면으로 들고 있다: {offending}. "
        "목록은 문맥(`available_tags`)으로 받아야 한다"
    )


@pytest.mark.req("FR-201-AC1")
def test_validation_errors_are_shown_with_their_field() -> None:
    """거부된 편집이 «어느 칸이 왜» 인지 화면에 남는다 (NFR-303)."""
    errors = (
        {
            "field": "model.resource_tag",
            "reason": "등록되지 않은 자원 종류입니다",
            "action": "등록된 종류 중에서 고르십시오",
            "rule": None,
        },
    )
    html = render_model_composer(model_composer_context(_config(), errors=errors))
    assert "model.resource_tag" in html
    assert "등록되지 않은 자원 종류입니다" in html
    assert "등록된 종류 중에서 고르십시오" in html
