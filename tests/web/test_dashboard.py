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
def test_wizard_and_equipment_settings_are_both_reachable() -> None:
    """UI-1-AC1: 마법사 방식으로 초심자를 안내하되,
    숙련자용 전체 파라미터 단일 화면(고급 모드) 병행

    ⚠ 위 인용은 **spec 조항 문면 그대로**다 — R63 이 화면 낱말을 「설비 설정」
    으로 옮겼으나 **조항 개정은 `spec §16.5` 절차**이고 이 라운드의 표적이
    아니었다(판정 정본 `docs/decisions-2026-09-05-R63b.md` §2ⓓ)."""
    parser = parse(render_dashboard())
    ids = element_ids(parser)

    # 조각 ③: 병행 — 둘 다 도달 가능
    assert "wizard" in ids
    assert "equipment-settings" in ids


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

    # 현재 템플릿에 4단계가 있음: 시나리오 선택, 설비 설정 확인, 실행, 내보내기
    # ⚠ 둘째 걸음 이름은 **목적지 절의 이름을 그대로 싣는다** — 누르면
    #   「설비 설정」 절로 간다(판정 정본 `docs/decisions-2026-09-05-R63b.md`
    #   §1 정정). 「설정 확인」으로 두면 도착한 절의 이름과 갈린다.
    expected_steps = ["시나리오 선택", "설비 설정 확인", "실행", "내보내기"]
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


#: ⚠⚠ **이 이름을 R63 이 일부러 바꾸지 않았다.** 같은 라운드의 다른 축
#: (R63/P1 교정)이 `core/model/parameters.py` 머리말에 *「지금 그 자리를 재는
#: 것은 `tests/web/test_dashboard.py::
#: test_advanced_mode_shows_every_parameter_the_configuration_has` 다」* 를
#: 세웠고, 그 파일은 R63/WP-S1 의 **금지 파일**이다(판정 ⑤ — `core/` 는 읽기만).
#: 이름을 바꾸면 그 인용이 없는 이름을 가리켜 `scripts/check_docstring_references.py`
#: 가 CI 에서 빨간불이 되고, **고칠 자리가 이 축의 손 밖에 있다.**
#: ⇒ 이름을 두고 **`.orch/R63/result_S1.md` 에 적었다** — 축 사이 조정 사항이다.
@pytest.mark.req("UI-1-AC1")
def test_advanced_mode_shows_every_parameter_the_configuration_has() -> None:
    """설비 설정이 **전체 파라미터**를 그린다 — UI-1-AC1 의 「전체」.

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
        "설비 설정이 그리는 파라미터가 카탈로그와 다릅니다. "
        f"화면에 없음: {sorted(expected - on_screen)}, "
        f"카탈로그에 없음: {sorted(on_screen - expected)}"
    )
    # 「전체」가 자원 한 종의 것이 아니라 **구성 전체**의 것이다
    assert len(DEMO_MODEL.resources) > 1


@pytest.mark.req("UI-1-AC1")
def test_equipment_settings_follow_the_configuration_not_a_fixed_list() -> None:
    """구성이 바뀌면 화면도 바뀐다 — 템플릿이 필드를 하드코딩하지 않는다.

    자원을 하나 더 놓으면 그 자원의 파라미터가 **한 벌 더** 나와야 한다.
    고정 목록을 그리는 템플릿은 위 테스트를 통과할 수 있어도 이것은 못 한다.
    """
    from web.render import equipment_setting_groups

    grown = DEMO_MODEL.model_copy(
        update={
            "resources": [
                *DEMO_MODEL.resources,
                DERConfig(tag="PV", params={"name": "벽면 BIPV", "capacity_kw": 4.0}),
            ]
        }
    )
    context = demo_context()
    context["parameter_groups"] = equipment_setting_groups(grown)

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
    setting_inputs = [
        element
        for element in parser.elements
        if element.tag == "input" and element.attrs.get("type") == "number"
    ]
    assert setting_inputs

    for inp in setting_inputs:
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

    ⚠ **수를 박지 않는다.** 「전건」의 기준은 `equipment_setting_fields(DEMO_MODEL)`
    를 **열거한 것**이며, 몇 개인지는 카탈로그가 정한다(`core/model/parameters.py`).
    39 이나 11 을 적어 두면 자원이 늘거나 생성자가 바뀌는 날 이 검사가
    「화면이 틀렸다」가 아니라 「검사가 낡았다」로 빨간불이 된다.

    ⚠ **단위를 여기서 짓지 않는다.** 기대값은 `ParameterSpec.unit` 이 준 것
    그대로이고, 그것이 비면 **「단위 없음」**이다 — 빈칸과 「없다」는 다른
    진술이며 이 검사가 가르는 것이 그 둘이다.
    """
    from web.render import equipment_setting_fields

    html = render_dashboard()
    cells = _unit_cells(html)
    labels = _tooltip_labels(html)

    fields = equipment_setting_fields(DEMO_MODEL)
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
        if not any(str(item["label"]) in label for label in labels):
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


# ─────────────────────────────────────────────────────────────────────────────
# R63/WP-S1 — **화면의 말·라벨·그룹.** 아래는 **더한 것만** 있다.
#
# 판정 정본: `docs/decisions-2026-09-05-R63b.md`(낱말표·§0 의 가르는 물음) ·
# `docs/decisions-2026-09-05-R63.md` §1 「용어」·「디자인」.
#
# ★★ **이 절의 검사들이 가르는 것은 「사람이 읽는 자리」와 「기계가 읽는
#    자리」다.** 파라미터 이름(`spec.name`)은 **폼 제출의 키**이므로
#    `id`·`name`·`for`·`data-parameter` 에는 **있어야 한다** — 지우면 폼이
#    아무 값도 받지 못한 채 성공을 낸다(`app/routers/ui_forms.py::_submissions`).
#    없어야 하는 곳은 `<label>` 글자·툴팁 문면처럼 **사람이 눈으로 읽는 자리**다.
#    한쪽만 재면 「변수명을 지웠다」와 「폼을 부쉈다」가 검사에서 같아진다.
# ─────────────────────────────────────────────────────────────────────────────

#: 사람이 읽는 **속성**. 나머지 속성은 기계가 읽는 것으로 본다.
#: ⚠ 여기에 `title` 이 있는 이유: 마우스를 올리면 브라우저가 그대로 인쇄한다.
_HUMAN_ATTRS = ("title", "aria-label", "alt", "placeholder")


class _HumanText(HTMLParser):
    """화면이 **사람에게 인쇄하는 글자만** 모은다.

    ⚠ **렌더된 문자열을 그대로 훑지 않는다.** 그렇게 하면 `id="res0-tilt_deg"`
    같은 **기계용 속성**이 함께 걸리고, 그때 이 검사는 「변수명이 안 보인다」가
    아니라 「변수명이 아예 없다」를 요구하게 된다 — 그것은 폼을 부수는 요구다.
    """

    def __init__(self) -> None:
        super().__init__()
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if key in _HUMAN_ATTRS and value:
                self.chunks.append(value)

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.chunks.append(data)


def human_text(html: str) -> str:
    parser = _HumanText()
    parser.feed(html)
    return "\n".join(parser.chunks)


def machine_attribute_text(html: str) -> str:
    """기계가 읽는 속성값만 모은다 — 폼 제출이 이것으로 된다."""
    return "\n".join(
        value
        for element in parse(html).elements
        for key, value in element.attrs.items()
        if key not in _HUMAN_ATTRS and value
    )


def _parameter_names(config: ModelConfig) -> set[str]:
    """구성이 펴는 파라미터 이름 — **기준은 카탈로그가 갖는다.**"""
    return {
        spec.name
        for resource in config.resources
        for spec in resource_parameters(resource.tag)
    }


@pytest.mark.req("UI-1-AC1", "NFR-302-M1")
def test_no_parameter_variable_name_is_printed_where_people_read() -> None:
    """★★ **변수명이 사람이 읽는 자리에 하나도 없다** — 사용자 판정 §1 「용어」.

    사용자 문면: *「"옥상 태양광 · azimuth_deg" 와 같이 coding 상의 변수명을
    병기하지 않음」*(`docs/decisions-2026-09-05-R63.md` §1).

    ⚠ **「하나만 확인」으로 두지 않는다 — 전건을 센다.** 한 자리만 보면 라벨
    한 줄을 고치고 툴팁 39개에 변수명이 남은 상태가 초록불이 된다. 그것이
    R63 착수 시점의 실측이었다(사람이 읽는 자리에 이름 41종 · 235회).

    ⚠ **수를 박지 않는다.** 모집단은 `resource_parameters` 가 펴는 이름 전건이며
    몇 개인지는 카탈로그가 정한다.
    """
    corpus = human_text(render_dashboard())

    leaked = sorted(name for name in _parameter_names(DEMO_MODEL) if name in corpus)
    assert not leaked, (
        f"사람이 읽는 자리에 파라미터 변수명이 {len(leaked)}종 남아 있다: {leaked}"
    )


@pytest.mark.req("UI-1-AC1")
def test_the_variable_name_is_still_in_the_places_the_form_reads() -> None:
    """★ **그런데 기계가 읽는 자리에는 남아 있다** — 폼 제출이 그것으로 된다.

    ⚠ 위 검사만 두면 「변수명을 지웠다」의 가장 싼 통과 방법이 **`id`·`name`
    까지 지우는 것**이고, 그때 폼은 아무 값도 못 받은 채 303 을 낸다
    (`app/routers/ui_forms.py::_submissions` 가 그 사고를 적어 두었다).
    ⇒ **두 방향을 함께 잰다.**
    """
    machine = machine_attribute_text(render_dashboard())

    missing = sorted(
        name for name in _parameter_names(DEMO_MODEL) if name not in machine
    )
    assert not missing, (
        f"폼이 읽는 속성(`id`·`name`·`data-parameter`)에서 사라진 파라미터: "
        f"{missing} — 이 상태의 폼은 아무 값도 받지 못한 채 성공을 낸다"
    )


@pytest.mark.req("UI-1-AC1", "NFR-302-M1")
def test_every_field_carries_a_human_label_and_never_the_variable_name() -> None:
    """★ **필드마다 사람이 읽는 라벨이 서 있다** — 전건.

    라벨 원천은 `core/model/parameters.py`(`LABEL_BY_NAME`·`resolve_label` ·
    R63/P1 이 세웠다)이며 **화면이 손으로 적지 않는다**.

    ⚠ **빈 라벨이면 파라미터 이름으로 되돌아가지 않는다** — 되돌아가면 변수명이
    조용히 다시 나오고 그것이 사용자가 지적한 그 자리다. 화면은 「라벨 미등록」을
    **글자로** 인쇄한다(빈칸과 「없다」는 다른 진술이다 · §13.0.1 ④).
    """
    from web.render import equipment_setting_fields

    fields = equipment_setting_fields(DEMO_MODEL)
    assert fields, "데모 구성에 파라미터가 하나도 없다 — 검사가 성립하지 않는다"

    blank = [item["parameter"] for item in fields if not str(item["label"]).strip()]
    assert not blank, f"라벨이 비어 있는 필드: {blank}"

    underscored = [item["parameter"] for item in fields if "_" in str(item["label"])]
    assert not underscored, (
        f"라벨에 밑줄이 있다 — 변수명이 라벨로 새고 있다: {underscored}"
    )

    # 화면에도 그 라벨이 실제로 서 있는가 — 문맥만 맞고 템플릿이 안 그리는
    # 상태를 가른다
    drawn = {
        element.attrs["for"]: element.text.strip()
        for element in elements_by_tag(parse(render_dashboard()), "label")
        if "for" in element.attrs
    }
    for item in fields:
        if not item["scalar"]:
            continue
        assert drawn.get(str(item["id"])), (
            f"{item['parameter']} 의 라벨이 화면에 없거나 비어 있다"
        )


@pytest.mark.req("UI-1-AC1")
def test_the_unlabelled_case_is_printed_and_never_falls_back_to_the_name() -> None:
    """★ **라벨이 없으면 「라벨 미등록」이 인쇄된다** — 판정 ③.

    ⚠ 앞 축(R63/P1)의 검사가 빈 라벨 수를 **0** 으로 묶었으므로 **이 경로는 안
    도는 것이 정상이다.** 그래도 눈에 보이게 두는 것이 규약이다 — 되돌아가는
    구현은 카탈로그에 라벨 없는 이름이 하나 생기는 날 **조용히** 변수명을
    화면에 되돌린다.

    ⚠ **카탈로그를 흔들지 않는다.** 라벨이 빈 `ParameterSpec` 을 이 검사가
    **직접 지어** `_field` 에 먹인다 — 실물 카탈로그를 monkey-patch 하면 그
    변이가 다른 검사로 새어 나간다.
    """
    from core.model.parameters import ParameterSpec
    from web.render import UNLABELLED, _field

    spec = ParameterSpec(
        tag="PV",
        name="azimuth_deg",
        label="",
        kind=ParameterKind.NUMBER,
        unit="도",
        required=False,
        default=180.0,
        type_text="float",
    )
    field = _field(0, DEMO_MODEL.resources[0], spec)

    assert field["label"] == UNLABELLED, field["label"]
    assert "azimuth_deg" not in field["label"]
    assert "azimuth_deg" not in field["help"]
    # 기계가 읽는 자리는 그대로다 — 폼 제출이 이것으로 된다
    assert field["id"] == "res0-azimuth_deg"


@pytest.mark.req("UI-1-AC1")
def test_grouping_loses_not_a_single_field() -> None:
    """★★ **묶은 뒤에도 필드 총수가 묶기 전과 같다** — `UI-1-AC1` 의 「전체」.

    ⚠ **수를 박지 않는다.** 기준은 `resource_parameters` 가 구성마다 펴는
    개수이며, 박아 두면 카탈로그가 늘거나 자원이 늘 때 이 검사가 「화면이
    틀렸다」가 아니라 「검사가 낡았다」로 빨간불이 된다.

    ★ **그룹 안의 합계와 화면에 그려진 자리를 둘 다 센다.** 문맥만 맞고
    템플릿이 한 묶음을 안 그리면 앞의 합계는 통과한다.
    """
    from web.render import equipment_setting_fields, equipment_setting_groups

    expected = sum(
        len(resource_parameters(resource.tag)) for resource in DEMO_MODEL.resources
    )
    grouped_total = sum(
        len(group["fields"]) for group in equipment_setting_groups(DEMO_MODEL)
    )

    assert grouped_total == expected, (
        f"묶는 동안 필드가 사라졌다 — 묶기 전 {expected} · 묶은 뒤 {grouped_total}"
    )
    assert len(equipment_setting_fields(DEMO_MODEL)) == expected
    assert len(_fields_on_screen(render_dashboard())) == expected


@pytest.mark.req("UI-1-AC1")
def test_one_group_per_resource_instance_even_when_two_share_a_kind() -> None:
    """★ **자원 인스턴스마다 그룹이 하나씩이고, 같은 종류가 둘이면 그룹도 둘이다.**

    사용자 문면: *「그루핑이 가능한 아이템은 그룹화 — 예시: 태양광, ESS는 각각을
    그룹화하여 제시」*(`docs/decisions-2026-09-05-R63.md` §1 「디자인」).

    ⚠ **종류별로 묶지 않는다.** `PV` 를 둘 놓으면 **어느 자원의 값인지 알 수
    없다** — `equipment_setting_groups` 독스트링이 그 사유를 적어 두었다.
    """
    from web.render import equipment_setting_groups

    grown = DEMO_MODEL.model_copy(
        update={
            "resources": [
                *DEMO_MODEL.resources,
                DERConfig(tag="PV", params={"name": "벽면 BIPV", "capacity_kw": 4.0}),
            ]
        }
    )
    groups = equipment_setting_groups(grown)

    assert len(groups) == len(grown.resources)
    assert [group["name"] for group in groups] == ["옥상 태양광", "공용 ESS", "벽면 BIPV"]
    # 같은 종류가 둘이면 그룹도 둘 — 종 단위로 한 벌만 그리면 이 단언이 진다
    assert len([group for group in groups if group["tag"] == "PV"]) == 2

    # 화면에도 묶음이 그만큼 서고, 각 묶음이 자기 자원 이름을 인쇄한다
    context = demo_context()
    context["parameter_groups"] = groups
    html = render_dashboard(context)

    drawn = [
        element
        for element in parse(html).elements
        if "data-resource-group" in element.attrs
    ]
    assert len(drawn) == len(grown.resources), (
        f"화면의 묶음이 {len(drawn)} 개 — 자원은 {len(grown.resources)} 개다"
    )

    corpus = human_text(html)
    for group in groups:
        assert group["name"] in corpus, (
            f"묶음이 자기 자원 이름(「{group['name']}」)을 인쇄하지 않는다 — "
            "그러면 어느 자원의 값인지 알 수 없다"
        )


#: 화면에서 물러난 낱말 — `.orch/R63/result_P2.md` 의 「바꾼다」 행이 짚은 것들이다.
#: ⚠ **「전제」를 저장소 전체에서 세지 않는다.** 그 낱말은 일반 국어로 270줄,
#: 전제 대장 뜻으로 328줄 쓰이며 그것들은 **바꿀 것이 아니다**(판정 ⓐ).
#: 여기서 재는 것은 **대시보드가 사람에게 인쇄하는 글자**뿐이다.
_RETIRED_SCREEN_WORDS = ("고급 모드", "고급모드", "전제")

#: 그 자리에 선 낱말 — 판정 정본 `docs/decisions-2026-09-05-R63b.md` §1 낱말표.
#:
#: ⚠ **낱말표의 다섯째(결과 화면 출처 칸)는 여기 없다.** 그 값은
#: `demo_context()["inputs"][…]["source"]` 이고 **어느 템플릿도 인쇄하지 않는다** —
#: 대시보드의 「입력값 부록」은 `label`·`value`·`unit` 만 그리고 `run_result.html`
#: 에는 `inputs` 순회가 없다(R63/WP-S1 실측). 화면에 없는 것을 「화면에 서라」로
#: 재면 그 검사는 **없는 자리를 세우라고 요구한다** ⇒ 아래
#: `test_the_ledger_source_word_moved_in_the_context` 가 **문맥에서** 잰다.
_NEW_SCREEN_WORDS = ("설비 설정", "설비 설정 확인", "계측 선언")


@pytest.mark.req("UI-1-AC1")
def test_the_retired_words_are_gone_from_where_people_read() -> None:
    """★ **종전 낱말이 사람이 읽는 자리에 0건이다** — 사용자 판정 §1 「용어」.

    사용자 문면: *「'고급 모드'나 '전제'나 동일하게 설비 설정을 변경하는 것을
    가르키는데 동일한 내용에 대해서 단일 단어를 사용해야 함」*.

    ⚠ **전건을 센다.** 절 제목만 고치고 탐색 링크·마법사 걸음·`<legend>` 에
    남은 상태가 「하나만 확인」에서는 초록불이다 — 착수 시점 실측이 그 넷이었다.
    """
    corpus = human_text(render_dashboard())

    left = {word: corpus.count(word) for word in _RETIRED_SCREEN_WORDS}
    assert not any(left.values()), (
        "물러난 낱말이 화면에 남아 있다: "
        f"{ {word: count for word, count in left.items() if count} }"
    )


@pytest.mark.req("UI-1-AC1")
def test_the_new_words_stand_on_the_screen() -> None:
    """★ **새 낱말이 실제로 서 있다** — 지운 것과 세운 것을 함께 잰다.

    ⚠ 위 검사만 두면 「낱말을 지웠다」의 가장 싼 통과 방법이 **그 자리를 통째로
    지우는 것**이다. 그때 사용자는 설비 설정으로 가는 입구를 잃는다.
    """
    corpus = human_text(render_dashboard())

    missing = [word for word in _NEW_SCREEN_WORDS if word not in corpus]
    assert not missing, f"새 낱말이 화면에 서지 않았다: {missing}"


@pytest.mark.req("UI-1-AC1")
def test_the_ledger_source_word_moved_in_the_context() -> None:
    """★ **출처 칸의 「전제 대장」이 「분석 설정 대장」으로 옮겨졌다** — 문맥에서 잰다.

    ⚠⚠ **이 값은 화면에 인쇄되지 않는다.** 「입력값 부록」은 `label`·`value`·
    `unit` 만 그리고 `run_result.html` 에는 `inputs` 순회가 없다 — 즉 전수 목록
    (`.orch/R63/result_P2.md` §1-2)이 이 두 줄을 「화면 인쇄물」로 분류한 것은
    **실물과 다르다**(R63/WP-S1 이 실측했다). 그래도 낱말을 옮긴 이유: 이 값이
    부록의 출처 칸으로 그려지는 날 옛 낱말이 되살아나며, 그때는 아무 검사도
    빨간불을 내지 않는다.
    ⇒ **화면이 아니라 문맥을 잰다** — 없는 자리를 세우라고 요구하지 않는다.
    """
    sources = {str(item["source"]) for item in demo_context()["inputs"]}

    assert "전제 대장" not in sources, sources
    assert "분석 설정 대장" in sources, sources


# ── R63 종료 — 대시보드에서 새 화면 셋으로 **닿는가** ─────────────────────
#
# R63 이 화면 셋(`/ui/scenarios`·`/ui/settings`·`/ui/verify`)을 세웠고, 그
# 셋은 **축마다 다른 워커**가 만들었다. 이 파일은 낱말 축이 단독으로 소유했으므로
# 링크는 오케스트레이터가 병합 뒤 한 커밋으로 넣었다 — 그 한 줄이 유일한 공유
# 자리였고 그래서 병합에서 만나지 않았다.
#
# ⚠⚠ 링크 주소는 템플릿에 **손으로 적혀 있다**(라우트 상수를 템플릿이 읽을 길이
# 없다). 손으로 적은 주소는 낡는다 — 그래서 아래 검사가 **앱 자신의 OpenAPI 문서**
# 와 대조한다. 박아 두고 대조하지 않으면 화면이 늘어도 목록은 그대로이고, 그
# 상태는 「닿는다」와 구별되지 않는다. `tests_e2e/test_axe_accessibility.py::
# test_the_scanned_list_is_every_html_screen_the_app_serves` 가 같은 판단이다.


@pytest.mark.req("UI-1-AC1")
def test_every_html_screen_the_app_serves_is_reachable_from_the_dashboard() -> None:
    """★★ **앱이 내놓는 화면 전건이 대시보드에서 닿는다.**

    ⚠ **「하나 이상 링크가 있다」로 두지 않는다** — 그러면 화면 하나가 늘어도
    초록불이고, 사용자는 주소를 손으로 쳐야 한다. 그것이 이 저장소가 R62/WP-5 에
    `D6` 으로 잡은 상태이며 `MC-8`(핵심 시나리오 완주)이 여기 걸린다.

    ⚠ `app.routes` 를 파이썬으로 뒤지지 않는다 — 그 자료구조의 모양은 FastAPI
    판마다 다르고(R62/WP-1 이 CI 에서 실측했다) 여기서 재려는 것은 **밖으로
    나가는 것**이다.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        spec = client.get("/openapi.json").json()

    served = {
        path
        for path, operations in spec["paths"].items()
        if "{" not in path
        and "text/html"
        in (
            (operations.get("get") or {})
            .get("responses", {})
            .get("200", {})
            .get("content", {})
        )
    }
    assert served, "앱이 내놓는 화면을 한 건도 찾지 못했다 — 대조할 것이 없다"

    body = render_dashboard()
    linked = set(re.findall(r'href="(/[^"#]*)"', body))
    # 대시보드 자신(`/`)은 링크로 서지 않아도 닿는다 — 지금 보고 있는 화면이다.
    unreachable = sorted(served - linked - {"/"})

    assert not unreachable, (
        "앱이 내놓는데 대시보드에서 닿지 않는 화면이 있다: "
        f"{unreachable}\n  대시보드가 링크한 것: {sorted(linked)}"
    )
