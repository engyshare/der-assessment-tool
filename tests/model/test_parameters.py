"""「전체 파라미터」의 기준 — UI-1-AC1 / WP-16.

R29 가 이 조항의 항진 테스트를 걷어내면서 *「「전체」의 기준이 코드에 없으므로
어떤 검사도 그것을 말할 수 없다」* 를 남겼다. **R31 이 기준을 정했고**(레지스트리에
등록된 자원의 생성자 시그니처), 이 파일이 그 기준 자신을 붙든다.

무엇을 붙드는가:

    ① 기준이 **레지스트리를 돈다** — 손으로 둔 목록이 아니다
    ② 기준이 **줄지 않는다** — 시그니처의 인자가 카탈로그에서 빠지지 않는다
    ③ 기준이 **거짓이 될 때 멈춘다** — 열거 불가 시그니처 · 단위 없는 수치
    ④ 단위표 둘이 **겹치지 않는다** — 겹치면 우선순위가 조용히 뒤집힌다
    ⑤ 파라미터마다 **한국어 라벨이 있다** — 없으면 화면이 변수명으로 돌아간다

**③이 이 파일의 핵심이다.** ①②만 두면 「지금 맞다」를 고정할 뿐이고, 새 자원이
규약을 벗어날 때 카탈로그가 조용히 반쪽을 내주는 것을 아무도 보지 못한다.

**⑤가 세는 것으로 있는 이유는 ③과 다르기 때문이다.** 라벨 부재는 계산 오류가
아니라 표시 결함이므로 카탈로그를 멈추게 두지 않는다(라벨 하나가 없어서 앱이
못 뜨면 그것이 더 나쁘다). 대신 **세지 않으면 조용히 변수명으로 되돌아가므로**
아래 셋이 전건을 요구한다.
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence

import pytest

import core.der
from core.contracts.der import DER
from core.contracts.registry import discover
from core.model.parameters import (
    LABEL_BY_NAME,
    UNIT_BY_NAME,
    UNIT_BY_SUFFIX,
    ParameterCatalogueError,
    ParameterKind,
    catalogue,
    parameters_of,
    resolve_unit,
    resource_parameters,
)


class _Enumerable:
    """이름으로 인자를 선언한 가짜 자원 — 카탈로그가 읽을 수 있는 형태."""

    tag = "가짜자원"

    def __init__(self, *, name: str, rated_kw: float, spare_count: int = 0) -> None:
        self.name = name


class _NotEnumerable:
    """`**kwargs` 를 받는 가짜 자원 — 받는 이름을 열거할 수 없다.

    ⚠ **가변 인자의 이름을 `_kw` 로 끝나게 둔 것이 의도적이다.** 단위가 풀리지
    않는 이름을 쓰면 **단위 거부가 먼저 발동해** 이 자원이 거부되고, 그러면
    「열거 불가를 거부하는가」를 물었는데 **다른 거부가 대신 답한다** — 열거
    거부를 통째로 지워도 초록불이 된다(R31 변이에서 실측했다).
    """

    tag = "이름미상"

    def __init__(self, *, name: str, **extras_kw: float) -> None:
        self.name = name


class _UnitlessNumber:
    """이름이 단위를 담지 않은 수치 인자를 받는 가짜 자원."""

    tag = "단위없음"

    def __init__(self, *, name: str, surplus_coefficient: float = 1.0) -> None:
        self.name = name


class _SeriesOrScalar:
    """수치도 시계열도 받는 인자 — 히트펌프 `heat_load_kwh` 와 같은 꼴."""

    tag = "합집합"

    def __init__(self, *, name: str, demand_kwh: float | Sequence[float] = 0.0) -> None:
        self.name = name


# ── ① 기준이 레지스트리를 돈다 ────────────────────────────────────────

@pytest.mark.req("UI-1-AC1")
def test_catalogue_keys_are_exactly_the_registry_tags() -> None:
    """카탈로그가 다루는 자원이 레지스트리와 **같다**.

    부분집합만 보면 고정 목록을 들고 있어도 통과한다 — `core/der/<tag>.py` 를
    새로 놓아도 고급 모드에 그 자원의 칸이 생기지 않는 상태가 초록불이 된다.
    그것이 이 저장소가 확장성이라 부르는 것의 반대다.
    """
    registry_tags = sorted(discover(core.der, DER))  # type: ignore[type-abstract]
    assert sorted(catalogue()) == registry_tags


@pytest.mark.req("UI-1-AC1")
def test_catalogue_reads_a_class_that_is_not_in_the_repository() -> None:
    """저장소에 없는 클래스도 시그니처만으로 읽힌다 — 목록이 아니라 규약이다.

    카탈로그가 어딘가에 적힌 이름 목록이라면 이 가짜 자원은 읽힐 수 없다.
    """
    specs = {spec.name: spec for spec in parameters_of(_Enumerable)}

    assert set(specs) == {"name", "rated_kw", "spare_count"}
    assert specs["rated_kw"].kind is ParameterKind.NUMBER
    assert specs["rated_kw"].unit == "kW"
    assert specs["rated_kw"].required is True
    assert specs["spare_count"].unit == "개"
    assert specs["spare_count"].required is False
    # `self` 는 파라미터가 아니다
    assert "self" not in specs


# ── ② 기준이 줄지 않는다 ──────────────────────────────────────────────

@pytest.mark.req("UI-1-AC1")
def test_catalogue_drops_no_constructor_argument() -> None:
    """자원마다 카탈로그의 이름 집합이 **시그니처 전부**와 같다.

    이 단언이 붙드는 것은 「카탈로그가 걸러내지 않는가」다. 시계열·구조처럼
    수치 칸으로 그릴 수 없는 인자를 카탈로그가 조용히 빼면 화면은 그럴듯해지고
    「전체」는 거짓이 된다 — **그리는 방법이 없는 것과 자리가 없는 것은 다르다.**
    """
    registry = discover(core.der, DER)  # type: ignore[type-abstract]
    for tag, cls in registry.items():
        declared = {
            name
            for name in inspect.signature(cls.__init__).parameters
            if name != "self"
        }
        catalogued = {spec.name for spec in resource_parameters(tag)}
        assert catalogued == declared, (
            f"{tag} 의 카탈로그가 시그니처와 다릅니다. "
            f"빠짐: {declared - catalogued}, 지어냄: {catalogued - declared}"
        )


@pytest.mark.req("UI-1-AC1")
def test_a_union_admitting_a_series_is_not_drawn_as_a_number() -> None:
    """`float | Sequence[float]` 는 수치 칸이 아니다.

    수치로 그리면 시계열을 넣을 방법이 사라지고, 그 자원은 「전체 파라미터」
    화면에서 반쪽만 조작된다 — 칸은 있는데 값을 넣을 수 없는 상태다.
    """
    spec = next(s for s in parameters_of(_SeriesOrScalar) if s.name == "demand_kwh")
    assert spec.kind is ParameterKind.SERIES

    # 실물에서도 같다 — 히트펌프 열부하가 그 꼴이다
    heat_load = next(s for s in resource_parameters("HeatPump") if s.name == "heat_load_kwh")
    assert heat_load.kind is ParameterKind.SERIES


# ── ③ 기준이 거짓이 될 때 멈춘다 ──────────────────────────────────────

@pytest.mark.req("UI-1-AC1")
def test_a_signature_that_cannot_be_enumerated_is_refused() -> None:
    """`**kwargs` 자원은 거부한다 — 아는 것만 돌려주지 않는다.

    통과시키면 그 자원의 파라미터 일부가 고급 모드에 영영 나타나지 않고, 그
    사실은 사용자가 없는 칸을 찾을 때까지 드러나지 않는다.
    """
    with pytest.raises(ParameterCatalogueError) as caught:
        parameters_of(_NotEnumerable)

    message = str(caught.value)
    assert "이름미상" in message
    # **다른 거부가 대신 답하지 않는지**를 문면으로 가른다 — 단위 거부도 같은
    # 예외형이고 같은 자원 이름을 싣는다
    assert "열거할 수 없" in message


@pytest.mark.req("UI-1-AC1", "UI-2-AC1")
def test_a_numeric_parameter_without_a_unit_is_refused() -> None:
    """단위를 모르는 수치 파라미터는 거부한다.

    `UI-2-AC1` 은 「모든 수치 입력 옆에 단위 상시 표시」를 요구한다. 카탈로그가
    단위 없이 내보내면 화면이 단위 없는 칸을 그리고, **두 조항이 동시에 조용히
    깨진다** — 하나는 「전체」가 거짓이 되고 하나는 단위가 사라진다.
    """
    with pytest.raises(ParameterCatalogueError) as caught:
        parameters_of(_UnitlessNumber)

    message = str(caught.value)
    assert "surplus_coefficient" in message
    # 조치를 말한다 — 이름을 고치거나 표에 선언하거나
    assert "UNIT_BY_NAME" in message


@pytest.mark.req("UI-2-AC1")
def test_every_numeric_parameter_in_the_catalogue_has_a_unit() -> None:
    """실물 카탈로그의 수치 파라미터가 **전건** 단위를 갖는다.

    위 거부 경로가 있으므로 `catalogue()` 가 성공한 것만으로 이미 참이지만,
    **그 사실을 이름으로 적어 둔다** — 거부를 나중에 경고로 낮추면 이 단언이
    남아서 빨간불을 낸다.
    """
    unitless = [
        f"{spec.tag}.{spec.name}"
        for specs in catalogue().values()
        for spec in specs
        if spec.kind is ParameterKind.NUMBER and not spec.unit
    ]
    assert unitless == []


def test_both_escalation_rates_reach_the_screen_with_the_same_unit() -> None:
    """★ 물가 계수가 **둘**이 됐다 — 화면이 둘 다 그리고 단위가 같다 (R42).

    `Q-17`(교체 설비단가의 실질 추세)을 스윕 축으로 배선하면서 자원 계약이
    `escalation_rate`(O&M)와 `replacement_escalation_rate`(교체 재취득)를 갈라
    갖게 됐다. 고급 모드 화면(UI-1-AC1)은 **열거한 것만 그리므로**, 자원
    생성자가 새 인자를 이름으로 내놓지 않으면 사용자는 그 값을 넣을 통로가
    없는 채 그 존재도 모른다.

    ⚠ **단위가 같고 뜻이 다르다** — 둘 다 `비율/년` 이며 구별은 **이름이**
    진다. 그래서 접미어 규칙에 맡기지 않고 `UNIT_BY_NAME` 에 갈라 적었고,
    여기서 *같은 단위로 함께 나온다*는 것을 못 박는다: 한쪽만 단위를 잃으면
    화면에 단위 없는 입력이 생기고(UI-2-AC1), 한쪽이 아예 빠지면 그 축을
    흔들 수 없다.

    ⚠ **붙들지 못하는 것**: 화면이 두 값을 **구별해 설명하는가**는 재지 않는다
    (그것은 라벨·도움말의 몫이다). 여기서 재는 것은 열거와 단위뿐이다.
    """
    wired = {"PV", "ESS"}  # `Q-17` 적용범위가 명시한 둘 — 대장 항목의 applicable_scope
    seen: dict[str, set[str]] = {}

    for tag, specs in catalogue().items():
        by_name = {spec.name: spec for spec in specs}
        found = {
            name for name in ("escalation_rate", "replacement_escalation_rate")
            if name in by_name
        }
        seen[tag] = found
        for name in found:
            assert by_name[name].kind is ParameterKind.NUMBER, (
                f"{tag}.{name} 이 수치로 그려지지 않습니다"
            )
            assert by_name[name].unit == "비율/년", (
                f"{tag}.{name} 의 단위가 `비율/년` 이 아닙니다: "
                f"{by_name[name].unit!r} — 두 계수는 단위가 같고 뜻이 다르며, "
                "구별은 이름이 집니다"
            )

    missing = sorted(tag for tag in wired if len(seen.get(tag, set())) != 2)
    assert not missing, (
        f"{missing}: 교체 계수를 생성자 인자로 내놓지 않습니다 — 대장의 "
        "`capex.replacement_real_trend` 가 적용 대상으로 명시한 자원이며, "
        "열거하지 않으면 고급 모드 화면에 나타나지 않습니다 (UI-1-AC1)"
    )


# ── ④ 단위표 둘이 겹치지 않는다 ───────────────────────────────────────

def test_unit_tables_do_not_overlap() -> None:
    """접미어로 이미 풀리는 이름을 `UNIT_BY_NAME` 이 다시 선언하지 않는다.

    겹치면 그 자리는 **접미어 규칙을 고칠 때 어느 쪽이 이기는지가 조용히
    뒤집히는 자리**가 된다. 값이 같아도 마찬가지다 — 같은 사실이 두 곳에 있으면
    한쪽만 고쳐진 상태를 아무도 보지 않는다.
    """
    shadowed = [
        name
        for name in UNIT_BY_NAME
        if any(name.endswith(suffix) for suffix in UNIT_BY_SUFFIX)
    ]
    assert shadowed == [], (
        f"접미어로 이미 풀리는 이름이 `UNIT_BY_NAME` 에 있습니다: {shadowed}. "
        "이름이 단위를 담고 있다면 접미어 규칙이 정본입니다"
    )


def test_the_longest_suffix_wins() -> None:
    """`_won_per_kwh` 는 `_kwh` 가 아니라 자기 자신으로 풀린다.

    짧은 접미어가 먼저 맞으면 **원/kWh 단가가 kWh(전력량)로 표시된다** — 값은
    그대로이고 뜻만 틀리며, 화면은 아무 오류도 내지 않는다.
    """
    assert resolve_unit("capex_unit_won_per_kwh") == "원/kWh"
    assert resolve_unit("unit_cost_won_per_kw") == "원/kW"
    assert resolve_unit("fixed_om_won_per_year") == "원/년"
    assert resolve_unit("battery_kwh") == "kWh"
    assert resolve_unit("바깥이름") == ""


# ── ⑤ 파라미터마다 한국어 라벨이 있다 ─────────────────────────────────

@pytest.mark.req("UI-1-AC1")
def test_every_label_key_names_a_parameter_that_exists() -> None:
    """`LABEL_BY_NAME` 에 **죽은 키**가 없다 — 모든 키가 실재하는 인자 이름이다.

    이름을 고치거나 인자를 걷어내면 그 라벨은 남는데 아무도 쓰지 않는다. 쓰이지
    않는 라벨은 **틀린 것을 알아차릴 방법이 없고**, 다음 사람은 그것을 보고
    「이 파라미터는 있는데 화면에 왜 없지」를 묻게 된다. 겹침 검사(④)와 달리 이
    검사는 표 **바깥**을 본다 — 표끼리의 모순이 아니라 표와 실물의 어긋남이다.
    """
    catalogued = {spec.name for specs in catalogue().values() for spec in specs}
    dead = sorted(set(LABEL_BY_NAME) - catalogued)
    assert dead == [], (
        f"`LABEL_BY_NAME` 의 키가 어떤 자원의 인자도 아닙니다: {dead}. "
        "이름이 바뀌었거나 인자가 없어진 자리이며, 그 라벨은 영영 쓰이지 "
        "않습니다 — 지우거나 지금 이름으로 고치십시오"
    )


@pytest.mark.req("UI-1-AC1")
def test_no_parameter_reaches_the_screen_without_a_label() -> None:
    """실물 카탈로그의 파라미터가 **전건** 라벨을 갖는다.

    ⚠ **「하나 이상 있다」로 두면 안 된다.** 하나만 채워도 초록불이 되고, 나머지
    여든몇 개는 화면에서 변수명 그대로 인쇄된다 — 사용자가 지우라고 한 바로 그
    상태다(*「"옥상 태양광 · azimuth_deg" 와 같이 coding 상의 변수명을 병기하지
    않음」*). 카탈로그는 라벨이 없다고 멈추지 않으므로 **세는 것은 여기뿐이다.**
    """
    unlabelled = [
        f"{spec.tag}.{spec.name}"
        for specs in catalogue().values()
        for spec in specs
        if not spec.label
    ]
    assert unlabelled == [], (
        f"라벨이 없는 파라미터가 {len(unlabelled)}개 있습니다: {unlabelled}. "
        "`LABEL_BY_NAME` 에 한국어 라벨을 선언하십시오 — 라벨이 없으면 화면은 "
        "변수명으로 되돌아가고 그 사실은 아무 오류도 내지 않습니다"
    )


@pytest.mark.req("UI-1-AC1")
def test_no_label_leaks_the_variable_name() -> None:
    """라벨이 **변수명을 담지 않는다** — 병기 금지는 문면 안에서도 성립한다.

    라벨을 `"방위각(azimuth_deg)"` 로 적으면 위 검사는 초록불인데 화면에는
    변수명이 그대로 남는다. 그래서 셋을 함께 요구한다: 비어 있지 않고 · 인자
    이름을 부분 문자열로 담지 않고 · `_` 를 담지 않는다. 마지막 것은 라벨이
    **사람이 읽는 말**임을 붙드는 값싼 대리 지표다 — 밑줄은 이 저장소의 인자
    이름 규약이지 한국어 낱말의 것이 아니다.
    """
    for specs in catalogue().values():
        for spec in specs:
            assert spec.label, f"{spec.tag}.{spec.name} 의 라벨이 비어 있습니다"
            assert spec.name not in spec.label, (
                f"{spec.tag}.{spec.name} 의 라벨 {spec.label!r} 이 인자 이름을 "
                "담고 있습니다 — 그것이 곧 변수명 병기입니다"
            )
            assert "_" not in spec.label, (
                f"{spec.tag}.{spec.name} 의 라벨 {spec.label!r} 에 밑줄이 "
                "있습니다 — 라벨은 사람이 읽는 말이어야 합니다"
            )
