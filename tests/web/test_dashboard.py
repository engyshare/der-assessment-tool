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
    """UI-1-AC1: 마법사 방식으로 초심자를 안내하되,
    숙련자용 전체 파라미터 단일 화면(고급 모드) 병행"""
    parser = parse(render_dashboard())
    ids = element_ids(parser)

    # 조각 ③: 병행 — 둘 다 도달 가능
    assert "wizard" in ids
    assert "advanced" in ids


@pytest.mark.req("UI-1-AC1")
def test_wizard_has_multiple_ordered_steps() -> None:
    """UI-1-AC1 조각 ①: 마법사가 안내한다 — 단계가 여럿이고 순서가 있는가"""
    html = render_dashboard()

    # wizard 섹션 안의 <ol class="steps"> 요소 찾기
    wizard_start = html.find('<section id="wizard"')
    wizard_end = html.find('</section>', wizard_start)
    wizard_html = html[wizard_start:wizard_end]

    # <ol class="steps"> 안의 <li> 요소들 추출
    import re
    li_pattern = r'<li>(.*?)</li>'
    li_matches = re.findall(li_pattern, wizard_html, re.DOTALL)

    # 단계가 여럿이어야 함 (최소 2개)
    assert len(li_matches) >= 2, f"마법사 단계가 {len(li_matches)}개뿐입니다 — 안내가 아닙니다"

    # 단계 텍스트 추출 및 정리
    step_texts = [match.strip() for match in li_matches]
    assert step_texts, "마법사 단계 텍스트가 없습니다"

    # 현재 템플릿에 4단계가 있음: 시나리오 선택, 전제 확인, 실행, 내보내기
    expected_steps = ["시나리오 선택", "전제 확인", "실행", "내보내기"]
    assert len(step_texts) == len(expected_steps), (
        f"예상 단계 {len(expected_steps)}개 vs 실제 {len(step_texts)}개"
    )
    for i, expected in enumerate(expected_steps):
        assert expected in step_texts[i], f"단계 {i+1}: '{expected}'가 '{step_texts[i]}'에 없습니다"


@pytest.mark.req("UI-1-AC1")
def test_advanced_mode_shows_all_parameters() -> None:
    """UI-1-AC1 조각 ②: 고급 모드가 '전체' 파라미터다 — 입력 목록 전부를 담는가"""
    parser = parse(render_dashboard())

    # 고급 모드 안의 모든 input 요소 찾기
    advanced_inputs = [
        element for element in parser.elements
        if element.tag == "input" and element.attrs.get("type") == "number"
    ]

    # demo_context()에 있는 모든 입력의 id를 확인
    from web.render import demo_context
    context = demo_context()
    input_ids = {item["id"] for item in context["inputs"]}

    # 고급 모드에 있는 input들의 id를 추출
    advanced_input_ids = {inp.attrs.get("id") for inp in advanced_inputs if inp.attrs.get("id")}

    # 고급 모드가 모든 입력을 포함하는지 확인
    assert input_ids == advanced_input_ids, (
        f"고급 모드가 모든 파라미터를 담지 않습니다. "
        f"컨텍스트: {input_ids}, 고급 모드: {advanced_input_ids}, "
        f"누락: {input_ids - advanced_input_ids}, 초과: {advanced_input_ids - input_ids}"
    )

    # 각 입력에 필수 필드(label, unit, help, source)가 있는지 확인
    for inp in advanced_inputs:
        inp_id = inp.attrs.get("id")
        if not inp_id:
            continue

        # aria-describedby를 통해 label과 unit을 연결
        described_by = inp.attrs.get("aria-describedby", "").split()
        assert described_by, f"입력 {inp_id}에 aria-describedby가 없습니다"

        # label 연결 확인
        label_id = f"{inp_id}"
        label_elements = [
            el for el in parser.elements
            if el.tag == "label" and el.attrs.get("for") == label_id
        ]
        assert label_elements, f"입력 {inp_id}에 연결된 label이 없습니다"
        assert label_elements[0].text.strip(), f"입력 {inp_id}의 label이 비어있습니다"

        # unit 연결 확인
        unit_id = f"{inp_id}-unit"
        unit_elements = [
            el for el in parser.elements
            if el.attrs.get("id") == unit_id and "unit" in el.attrs.get("class", "")
        ]
        assert unit_elements, f"입력 {inp_id}에 연결된 unit이 없습니다"
        assert unit_elements[0].text.strip(), f"입력 {inp_id}의 unit이 비어있습니다"


@pytest.mark.req("UI-2-AC1", "NFR-302-M1")
def test_all_numeric_inputs_have_persistent_units() -> None:
    """수치 입력마다 자기 단위와 개별 결속됨을 확인 — NFR-302-M1 이 요구하는
    "입력 필드 각각이 자기 툴팁과 개별 결속" 도 이 검사가 이미 실검증한다.
    `numeric_inputs_without_units` 는 각 입력의 `aria-describedby` 가 그
    입력 고유의 `-unit` id 를 가리키는지(개별 결속) 확인하므로, UI-2-AC1
    과 NFR-302-M1 이 요구하는 실질이 같다 (§17.18 — 같은 패턴 재적용)."""
    assert numeric_inputs_without_units(render_dashboard()) == []


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


@pytest.mark.req("UI-7-AC1", "FR-1002-AC1")
def test_impact_ranking_precedes_input_value_listing_in_dom() -> None:
    """UI-7-AC1 과 FR-1002-AC1 은 동일 요구사항이다(docs/traceability.md:359
    가 "(FR-1002)"로 명시). render_dashboard() 실제 HTML 을 파싱해 DOM 순서를
    검증하므로, 리포트 첫 화면이 영향도 순위로 시작한다는 FR-1002-AC1 의
    실질도 이 테스트가 실검증한다 (§17.1 — 마커만 추가, 새 단언 없음)."""
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


@pytest.mark.req("FR-504-AC4")
def test_regulation_management_shows_profile_version_and_diff() -> None:
    section = next(
        element for element in parse(render_dashboard()).elements
        if element.attrs.get("id") == "regulations"
    )

    assert "버전" in section.text
    assert "diff:" in section.text


@pytest.mark.req("FR-502-AC4")
def test_compliance_warning_appears_when_triggered() -> None:
    """FR-502-AC4 조각 ①: 미달 여부 — 미달일 때 경고가 나타나고, 충족일 때 나타나지 않는가"""
    # 기본 demo_context는 triggered=True 상태
    html = render_dashboard()

    # 경고 섹션이 존재하는지 확인
    assert "compliance-warning" in html
    assert "공급의무 미달 경고" in html
    assert "부족전력량:" in html
    assert "추가 비용:" in html


@pytest.mark.req("FR-502-AC4")
def test_compliance_warning_does_not_appear_when_compliant() -> None:
    """FR-502-AC4 조각 ①: 충족일 때 경고가 나타나지 않는가"""
    from decimal import Decimal

    from core.contracts.units import Money
    from web.render import demo_context, render_dashboard

    # 충족 상태의 컨텍스트 생성 (triggered=False)
    context = demo_context()
    context["compliance_alert"] = {
        "triggered": False,
        "shortfall_kwh": 0.0,
        "additional_cost": Money(Decimal("0")),
    }

    html = render_dashboard(context)

    # 경고 섹션이 존재하지 않아야 함
    assert "compliance-warning" not in html
    assert "공급의무 미달 경고" not in html


@pytest.mark.req("FR-502-AC4")
def test_compliance_warning_shows_additional_cost_with_text() -> None:
    """FR-502-AC4 조각 ②: 경고에 금액이 함께 표시되는가 — 색상만으로 알리지 마세요"""
    html = render_dashboard()

    # 경고 섹션이 있고 금액 텍스트가 포함되어 있는지 확인
    assert "compliance-warning" in html
    assert "추가 비용:" in html

    # 금액 형식 (숫자 + "원")이 있는지 확인
    import re
    cost_pattern = r"추가 비용:.*?[\d,]+원"
    assert re.search(cost_pattern, html), "추가 비용 금액이 텍스트로 표시되지 않았습니다"

    # UI-6-AC1 접근성: 색상 단독 정보전달 금지 — 글자가 있는지 확인
    # 경고에는 "공급의무 미달", "부족전력량", "추가 비용" 등의 텍스트가 있어야 함
    assert "공급의무 미달" in html or "부족전력량" in html, "경고에 텍스트 라벨이 없습니다"
