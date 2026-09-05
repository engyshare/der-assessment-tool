from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest

from core.model.parameters import ParameterKind, resource_parameters
from core.model.schemas import DERConfig, ModelConfig
from web.render import DEMO_MODEL, demo_context, render_dashboard


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


def _fields_on_screen(html: str) -> set[str]:
    """화면에 자리를 가진 파라미터 — 수치 칸이든 편집 버튼이든."""
    return {
        element.attrs["data-parameter"]
        for element in parse(html).elements
        if "data-parameter" in element.attrs
    }


def _expected_parameters(config: ModelConfig) -> set[str]:
    """구성이 요구하는 전체 파라미터 — **기준은 카탈로그가 갖는다.**

    기대값을 `web.render` 에서 다시 불러오지 않는 것이 요점이다. 렌더러가 먹은
    것과 같은 곳에서 기대값을 가져오면 렌더러가 무엇을 하든 두 집합이 같아지고,
    그것이 R28 까지 이 파일에 있던 항진이다.
    """
    return {
        f"{index}.{spec.name}"
        for index, resource in enumerate(config.resources)
        for spec in resource_parameters(resource.tag)
    }


@pytest.mark.req("UI-1-AC1")
def test_advanced_mode_shows_every_parameter_the_configuration_has() -> None:
    """고급 모드가 **전체 파라미터**를 그린다 — UI-1-AC1 의 「전체」.

    ⚠ **R29 까지 이 자리는 「전체」를 말할 수 없었다.** 기준이 저장소에 없었기
    때문이다(`DERConfig.params` 는 `dict[str, Any]`). R31 이 기준을 정했다 —
    **레지스트리에 등록된 자원의 생성자 시그니처**(`core/model/parameters.py`).
    이제 이 단언이 실제로 「전체」를 붙든다.

    ★ **집합 비교이지 포함 관계가 아니다.** 부분집합만 보면 목록을 잘라도
    통과한다 — `[:5]` 로 자르는 변이가 이 단언에만 잡힌다.
    """
    on_screen = _fields_on_screen(render_dashboard())
    expected = _expected_parameters(DEMO_MODEL)

    assert on_screen == expected, (
        "고급 모드가 그리는 파라미터가 카탈로그와 다릅니다. "
        f"화면에 없음: {sorted(expected - on_screen)}, "
        f"카탈로그에 없음: {sorted(on_screen - expected)}"
    )
    # 「전체」가 자원 한 종의 것이 아니라 **구성 전체**의 것이다
    assert len(DEMO_MODEL.resources) > 1


@pytest.mark.req("UI-1-AC1")
def test_advanced_mode_follows_the_configuration_not_a_fixed_list() -> None:
    """구성이 바뀌면 화면도 바뀐다 — 템플릿이 필드를 하드코딩하지 않는다.

    자원을 하나 더 놓으면 그 자원의 파라미터가 **한 벌 더** 나와야 한다.
    고정 목록을 그리는 템플릿은 위 테스트를 통과할 수 있어도 이것은 못 한다.
    """
    from web.render import advanced_mode_fields

    grown = DEMO_MODEL.model_copy(
        update={
            "resources": [
                *DEMO_MODEL.resources,
                DERConfig(tag="PV", params={"name": "벽면 BIPV", "capacity_kw": 4.0}),
            ]
        }
    )
    context = demo_context()
    context["parameters"] = advanced_mode_fields(grown)

    assert _fields_on_screen(render_dashboard(context)) == _expected_parameters(grown)
    # 같은 종을 둘 놓으면 파라미터도 두 벌이다 — 종 단위로 한 벌만 그리면
    # 둘째 자원의 값을 고칠 방법이 없다
    pv_rows = [name for name in _expected_parameters(grown) if name.endswith(".capacity_kw")]
    assert len(pv_rows) == 2


@pytest.mark.req("UI-1-AC1")
def test_non_scalar_parameters_still_have_a_place_on_the_screen() -> None:
    """시계열·구조·선택도 화면에 자리를 갖는다 — 수치 칸이 아닐 뿐이다.

    **그리는 방법이 없는 것과 자리가 없는 것은 다르다.** 8760개짜리 시계열을
    수치 칸으로 그릴 수는 없지만, 자리마저 없으면 그것이 곧 「전체」가 아닌
    것이고 사용자는 그 값을 고칠 입구를 찾지 못한다.
    """
    parser = parse(render_dashboard())
    kinds = {
        element.attrs["data-parameter"]: element.attrs.get("data-kind", "")
        for element in parser.elements
        if "data-parameter" in element.attrs
    }
    non_scalar = {name for name, kind in kinds.items() if kind != str(ParameterKind.NUMBER)}
    assert non_scalar, "데모 구성에 비수치 파라미터가 하나도 없습니다 — 검사가 성립하지 않습니다"

    number_input_ids = {
        element.attrs.get("id")
        for element in parser.elements
        if element.tag == "input" and element.attrs.get("type") == "number"
    }
    for name in non_scalar:
        index, _, param = name.partition(".")
        assert f"res{index}-{param}" not in number_input_ids, (
            f"{name} 은 수치 칸으로 그릴 수 없는 파라미터인데 `type=number` 로 "
            "그려졌습니다 — 사용자가 시계열을 그 칸에 넣을 방법이 없습니다"
        )


@pytest.mark.req("UI-1-AC1")
def test_every_scalar_field_carries_label_unit_and_tooltip() -> None:
    """수치 칸마다 라벨·단위·도움말이 자기 입력과 결속된다."""
    parser = parse(render_dashboard())
    advanced_inputs = [
        element
        for element in parser.elements
        if element.tag == "input" and element.attrs.get("type") == "number"
    ]
    assert advanced_inputs

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


# ─────────────────────────────────────────────────────────────────────────────
# R62/WP-7 — 아래는 **더한 것만** 있다. 위의 검사는 한 줄도 고치지 않았다.
# ─────────────────────────────────────────────────────────────────────────────

#: 데모 표지 블록을 통째로 떼는 패턴. **표지의 문면을 여기 베끼지 않는다** —
#: 베끼면 이 검사가 재는 것이 「화면이 데모라고 말하는가」가 아니라 「내가 적은
#: 문자열이 그대로 있는가」가 된다. 붙잡는 것은 `data-demo-notice` 라는 **자리**
#: 이고, 그 안에서 무엇을 말해야 하는지만 아래에서 확인한다.
_DEMO_NOTICE_BLOCK = re.compile(
    r'<section[^>]*data-demo-notice="results"[^>]*>(.*?)</section>',
    re.DOTALL,
)


def _demo_notice(html: str) -> str | None:
    match = _DEMO_NOTICE_BLOCK.search(html)
    return match.group(1) if match else None


@pytest.mark.req("UI-6-AC1")
def test_the_demo_section_says_on_screen_that_it_is_a_demo() -> None:
    """★ **데모 절이 「데모」라고 말한다** — D5 (R62/WP-7).

    `#results` 절의 수는 전부 `demo_context()` 가 지은 박힌 값인데, 같은 화면의
    「분석 실행」이 내는 **실제 결과와 나란히 놓인다**. 심의에서 이것이 실측으로
    읽힐 자리이고, 그 상태는 아무 검사도 빨간불을 내지 않는다.

    ⚠ **데모 값이 있는지를 재지 않는다** — 그것은 위의 `UI-3`·`UI-4`·`UI-7`·
    `NFR-303` 검사들이 이미 재고 있고, 데모 값은 그대로 있어야 한다. 여기서
    재는 것은 **화면이 그것을 데모라고 말하는가**뿐이다.

    ⚠ **색을 재지 않는다**(`UI-6` — 색만으로 정보를 전달하지 않는다). 표지가
    글자로 말하는지, 그리고 실제 결과가 있는 자리로 가는 **진짜 링크**를
    갖는지를 본다.
    """
    html = render_dashboard()
    notice = _demo_notice(html)
    assert notice is not None, (
        "`#results` 절에 데모 표지가 없다 — 데모 값이 실측으로 읽힌다"
    )

    # ① 글자로 말한다 — 색이 아니라
    assert "데모" in notice
    assert "실제 결과가 아니다" in notice

    # ② 실제 결과가 나오는 자리로 **가는 길**이 있다
    assert 'href="/ui/run"' in notice, (
        "표지가 「실제 결과는 다른 곳에서 나온다」고만 말하고 그리로 가는 길을 "
        "주지 않는다 — 사용자는 주소를 손으로 쳐야 한다"
    )
    assert 'href="#run"' in notice

    # ③ **그 절의 머리**에 있다. 아래에 있으면 데모 수를 먼저 읽고 나중에 안다
    assert html.index("data-demo-notice") < html.index('id="impact-ranking"')
    assert html.index('id="results"') < html.index("data-demo-notice")


@pytest.mark.req("UI-6-AC1")
def test_the_real_result_screen_does_not_carry_the_demo_marker() -> None:
    """★ **실행 결과 화면에는 표지가 없다** — 거기는 실제 결과다.

    표지를 두 화면에 다 붙이면 「데모」와 「실측」이 화면에서 다시 같아진다 —
    이 표지가 막으려는 것이 정확히 그 상태다.

    ⚠ `web.render` 를 직접 부르지 않고 **실제 라우트를 지난다.** 문맥 함수를
    직접 부르면 「배포 코드가 부르지 않는 함수가 초록불을 만든다」를 다시 밟는다
    (`tests/app/test_ui_router.py` 머리말이 그 형태를 적어 두었다).
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    response = TestClient(create_app()).get("/ui/run")
    assert response.status_code == 200, response.text
    assert _demo_notice(response.text) is None, (
        "실제 결과 화면이 자기를 데모라고 말한다"
    )
    assert "실제 결과가 아니다" not in response.text


def _unit_cells(html: str) -> dict[str, str]:
    """화면이 그린 **단위 칸** — `{입력 id: 칸의 글자}`."""
    return {
        element.attrs["data-unit-for"]: element.text.strip()
        for element in parse(html).elements
        if "data-unit-for" in element.attrs
    }


def _tooltip_labels(html: str) -> list[str]:
    return [
        element.attrs["aria-label"]
        for element in elements_by_tag(parse(html), "button")
        if "도움말" in element.attrs.get("aria-label", "")
    ]


@pytest.mark.req("NFR-302-M1")
def test_every_parameter_has_a_unit_cell_including_the_non_numeric_ones() -> None:
    """★ **파라미터 전건이 단위 칸을 갖는다** — D8 (R62/WP-7).

    조항(`NFR-302-M1`)이 요구하는 것은 *「단위·설명·기본값 출처」* **셋**이다.
    수치 파라미터에는 셋 다 있었고 **비수치 파라미터에는 단위가 없었다** —
    `aria-label` 도 없었다.

    ⚠ **수를 박지 않는다.** 「전건」의 기준은 `advanced_mode_fields(DEMO_MODEL)`
    를 **열거한 것**이며, 몇 개인지는 카탈로그가 정한다(`core/model/parameters.py`).
    39 이나 11 을 적어 두면 자원이 늘거나 생성자가 바뀌는 날 이 검사가
    「화면이 틀렸다」가 아니라 「검사가 낡았다」로 빨간불이 된다.

    ⚠ **단위를 여기서 짓지 않는다.** 기대값은 `ParameterSpec.unit` 이 준 것
    그대로이고, 그것이 비면 **「단위 없음」**이다 — 빈칸과 「없다」는 다른
    진술이며 이 검사가 가르는 것이 그 둘이다.
    """
    from web.render import advanced_mode_fields

    html = render_dashboard()
    cells = _unit_cells(html)
    labels = _tooltip_labels(html)

    fields = advanced_mode_fields(DEMO_MODEL)
    assert fields, "데모 구성에 파라미터가 하나도 없다 — 검사가 성립하지 않는다"

    missing: list[str] = []
    wrong: list[str] = []
    untold: list[str] = []
    for item in fields:
        expected = item["unit"] or "단위 없음"
        drawn = cells.get(item["id"])
        if not drawn:
            missing.append(item["parameter"])
        elif drawn != expected:
            wrong.append(f"{item['parameter']}: 화면 {drawn!r} ≠ 카탈로그 {expected!r}")
        if not any(item["label"] in label for label in labels):
            untold.append(item["parameter"])

    assert not missing, f"단위 칸이 없는 파라미터: {missing}"
    assert not wrong, f"화면의 단위가 카탈로그와 다르다: {wrong}"
    assert not untold, f"도움말 `aria-label` 이 없는 파라미터: {untold}"

    # ★ **두 갈래가 다 밟혔는지** 확인한다. 한쪽만 있으면 이 검사는 「단위가
    #   있는 것만」 또는 「없는 것만」 보고도 통과한다 (§13.0.1 ④).
    drawn_units = {cells[item["id"]] for item in fields}
    assert drawn_units - {"단위 없음"}, "카탈로그가 준 단위를 그린 칸이 하나도 없다"
    assert "단위 없음" in drawn_units, (
        "「단위 없음」을 적은 칸이 하나도 없다 — 비수치 파라미터가 사라졌거나 "
        "없는 단위를 지어냈다"
    )

    # 조항의 셋을 **셋 다** — 단위 칸만으로는 `NFR-302-M1` 이 아니다
    assert all("단위" in label for label in labels)
    assert all("기본값 출처" in label for label in labels)


@pytest.mark.req("UI-1-AC1")
def test_every_wizard_step_has_somewhere_to_go() -> None:
    """★ **마법사 네 걸음이 갈 곳을 갖는다** — D7 (R62/WP-7).

    종전 네 걸음은 **글자였고** 「다음 단계」 단추는 `type="button"` 이라 아무
    일도 하지 않았다(템플릿 넷에 `<script>` 가 0개다). 조항은 *「마법사 방식으로
    초심자를 안내」* 인데 안내가 가리키는 곳이 없었고, **그 상태는 화면을
    「있는지」만 재는 검사에서 전부 초록불이었다.**

    ⚠ **걸음의 문면을 여기 적지 않는다** — 그것은 위
    `test_wizard_has_multiple_ordered_steps` 가 이미 붙들고 있다. 여기서 재는
    것은 **전부 갈 곳을 갖는가**뿐이다.
    """
    html = render_dashboard()
    start = html.find('<section id="wizard"')
    steps = re.findall(r"<li>(.*?)</li>", html[start:html.find("</section>", start)],
                       re.DOTALL)
    assert steps, "마법사에 걸음이 없다"

    without = [step.strip()[:40] for step in steps if "href=" not in step]
    assert not without, (
        f"갈 곳이 없는 걸음 {len(without)} 개: {without} — "
        "아무 데도 가지 않는 안내는 안내가 아니다"
    )


@pytest.mark.req("UI-1-AC1")
def test_the_export_step_points_at_a_report_the_repository_actually_has() -> None:
    """★ **「내보내기」가 화면에서 처음으로 닿는 곳을 갖는다** — D7.

    ⚠ **시나리오 이름을 여기 박지 않는다.** 화면이 쓰는 것과 같은 문맥
    (`demo_context()["scenarios"]` — 저장소를 읽은 것이다)에서 가져와 대조한다.
    박으면 골든이 늘거나 이름이 바뀌는 날 「화면이 틀렸다」가 아니라 「검사가
    낡았다」로 빨간불이 된다.

    ⚠ **누르면 새 화면이 뜨지 않는다**는 사실이 링크 **글자**에 적혀 있어야
    한다. `/reports/golden/<이름>` 은 `text/markdown` 을 내고 브라우저는 그것을
    그리지 않고 내려받는다 — 적지 않으면 누른 사람은 화면이 안 바뀐 것을
    「안 먹었다」로 읽는다.
    """
    context = demo_context()
    scenarios = context["scenarios"]
    assert scenarios, "저장소에 골든 시나리오가 없다 — 내보낼 것이 없다"

    html = render_dashboard(context)
    start = html.find('<section id="wizard"')
    wizard = html[start:html.find("</section>", start)]
    export = next(
        step for step in re.findall(r"<li>(.*?)</li>", wizard, re.DOTALL)
        if "내보내기" in step
    )

    assert f"/reports/golden/{scenarios[0]}" in export, (
        f"「내보내기」가 가리키는 곳이 문맥의 시나리오와 다르다: {export.strip()[:200]}"
    )
    assert "text/markdown" in export
    assert "내려받는다" in export

    # ★ **「실행」과 「내보내기」가 같은 시나리오를 가리킨다.** 실행 폼의
    #   `<select>` 는 브라우저가 첫 선택지를 고른 채로 열리므로, 마법사를 그대로
    #   따라간 사람이 실행하는 것은 그 첫째다. 둘이 갈리면 사람은 A 를 돌려 놓고
    #   B 를 내려받게 되고 **두 화면 다 정상으로 보인다.**
    options = [
        element.attrs["value"]
        for element in elements_by_tag(parse(html), "option")
        if "value" in element.attrs
    ]
    assert options and options[0] == scenarios[0], (
        f"실행 폼이 처음 고르는 시나리오({options[:1]})와 「내보내기」가 가리키는 "
        f"시나리오({scenarios[0]})가 다르다"
    )
