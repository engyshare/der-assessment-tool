from __future__ import annotations

from html.parser import HTMLParser

import pytest

from web.render import render_dashboard


class Element:
    def __init__(self, tag: str, attrs: dict[str, str], index: int) -> None:
        self.tag = tag
        self.attrs = attrs
        self.index = index
        self.text_parts: list[str] = []

    @property
    def text(self) -> str:
        return " ".join(part.strip() for part in self.text_parts if part.strip())


class DashboardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[Element] = []
        self._stack: list[Element] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(
            tag=tag,
            attrs={key: value or "" for key, value in attrs},
            index=len(self.elements),
        )
        self.elements.append(element)
        self._stack.append(element)

    def handle_endtag(self, tag: str) -> None:
        for pos in range(len(self._stack) - 1, -1, -1):
            if self._stack[pos].tag == tag:
                del self._stack[pos:]
                break

    def handle_data(self, data: str) -> None:
        for element in self._stack:
            element.text_parts.append(data)


def parse(html: str) -> DashboardParser:
    parser = DashboardParser()
    parser.feed(html)
    return parser


def elements_by_tag(parser: DashboardParser, tag: str) -> list[Element]:
    return [element for element in parser.elements if element.tag == tag]


def element_ids(parser: DashboardParser) -> set[str]:
    return {element.attrs["id"] for element in parser.elements if "id" in element.attrs}


def numeric_inputs_without_units(html: str) -> list[str]:
    parser = parse(html)
    ids = element_ids(parser)
    missing: list[str] = []
    for input_element in elements_by_tag(parser, "input"):
        if input_element.attrs.get("type") != "number":
            continue
        field_id = input_element.attrs.get("id") or input_element.attrs.get("name") or "<unknown>"
        described_by = input_element.attrs.get("aria-describedby", "").split()
        has_described_unit = any(token in ids and token.endswith("-unit") for token in described_by)
        has_bound_unit = any(
            element.attrs.get("data-unit-for") == field_id and element.text
            for element in parser.elements
        )
        if not (has_described_unit and has_bound_unit):
            missing.append(field_id)
    return missing


@pytest.mark.req("UI-1-AC1")
def test_wizard_and_advanced_mode_are_both_reachable() -> None:
    parser = parse(render_dashboard())
    ids = element_ids(parser)

    assert "wizard" in ids
    assert "advanced" in ids


@pytest.mark.req("UI-2-AC1")
def test_all_numeric_inputs_have_persistent_units() -> None:
    assert numeric_inputs_without_units(render_dashboard()) == []


@pytest.mark.req("UI-2-AC1")
def test_unit_scanner_catches_a_number_input_without_unit() -> None:
    bad_html = """
    <form>
      <label for="capacity">용량</label>
      <input id="capacity" name="capacity" type="number" value="1">
    </form>
    """

    assert numeric_inputs_without_units(bad_html) == ["capacity"]


@pytest.mark.req("UI-3-AC1", "UI-6-AC1")
def test_assumption_badge_has_text_not_color_alone() -> None:
    badges = [
        element for element in parse(render_dashboard()).elements
        if "assumption-badge" in element.attrs.get("class", "")
    ]

    assert badges
    assert all("가정" in badge.text and "!" in badge.text for badge in badges)


@pytest.mark.req("UI-4-AC1")
def test_result_card_delta_matches_supported_minus_baseline() -> None:
    cards = [
        element for element in parse(render_dashboard()).elements
        if element.tag == "article" and "data-delta" in element.attrs
    ]

    assert cards
    for card in cards:
        supported = float(card.attrs["data-supported"])
        baseline = float(card.attrs["data-baseline"])
        delta = float(card.attrs["data-delta"])
        assert delta == pytest.approx(supported - baseline)


@pytest.mark.req("UI-7-AC1")
def test_impact_ranking_precedes_input_value_listing_in_dom() -> None:
    parser = parse(render_dashboard())
    positions = {
        element.attrs["id"]: element.index
        for element in parser.elements
        if "id" in element.attrs
    }

    assert positions["impact-ranking"] < positions["result-input-appendix"]


@pytest.mark.req("NFR-302-M1")
def test_inputs_have_tooltips_with_unit_description_and_source() -> None:
    tips = [
        element for element in elements_by_tag(parse(render_dashboard()), "button")
        if "도움말" in element.attrs.get("aria-label", "")
    ]

    assert tips
    assert all("단위" in tip.attrs["aria-label"] for tip in tips)
    assert all("기본값 출처" in tip.attrs["aria-label"] for tip in tips)


@pytest.mark.req("NFR-303-M1")
def test_error_messages_include_field_reason_and_action() -> None:
    messages = [
        element for element in parse(render_dashboard()).elements
        if "error-message" in element.attrs.get("class", "")
    ]

    assert messages
    assert all("필드:" in message.text for message in messages)
    assert all("사유:" in message.text for message in messages)
    assert all("조치:" in message.text for message in messages)


@pytest.mark.req("FR-504-AC2")
def test_regulation_management_shows_profile_version_and_diff() -> None:
    section = next(
        element for element in parse(render_dashboard()).elements
        if element.attrs.get("id") == "regulations"
    )

    assert "버전" in section.text
    assert "diff:" in section.text
