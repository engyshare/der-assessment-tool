"""시나리오가 실은 **전제 오버라이드**가 실행 경로에 닿는가 — `FR-602` · §7.2 O-2.

## 무엇이 없었는가

`AssumptionSet.override()`·`overridden_items()` 는 R22 부터 있었고
`CaseReport.overrides` 도 필드로 서 있었다. **없던 것은 통로 하나**다 —
시나리오가 「이 값을 이렇게 바꿔 돌린다」를 적을 자리가 없어서
`build_case_report()` 는 늘 대장을 그대로 실었고, 그래서 붙임의 「기준 전제
대비 변경 항목」은 **영영 비어 있었다.**

## ★★★ 통로는 시나리오 필드 하나다 — 새 통로를 내지 않는다

`baseline_arrangement`(갈래)·`pool_metering`(ⓒ 선언)이 이미 그 모양이고
(`app/services/ui_run.py` 머리말이 정본이다), 전제 오버라이드도 **같은 자리**로
들어온다. 목록의 한 원소는 `{key, value, reason}` 이며 그것은
`infra/orm/scenario.py::ScenarioOverride` 의 컬럼(`assumption_key`·
`value_json`·`reason`)과 **같은 모양**이다 — 저장 층과 실행 층이 같은 모양을
쓰면 왕복에서 사유가 사라지지 않는다.

⚠ **평평한 매핑으로 두지 않는다.** 키에 값을 바로 붙이면 `reason` 을 실을
자리가 없어지고, `FR-602-AC3`(사유는 권장 필드)이 **통로에서** 사라진다 —
자료형에는 남아 있는데 아무도 채울 수 없는 상태가 된다.

## ⚠ 대장을 무르게 만들지 않는다 (`NFR-202`)

오버라이드는 **대장 위에 얹는 층**이지 대장을 여는 문이 아니다. 그래서
대장에 없는 키는 거부한다 — **조용히 무시하지 않는다.** 사용자가 값을 고쳤는데
안 먹는 것이 가장 나쁘다: 화면은 고친 값을 인쇄하고 계산은 옛 값으로 돈다.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.assumption.item import AssumptionItem, ConfidenceLevel
from core.assumption.provider import AssumptionSet
from core.assumption.scenario_overrides import (
    ASSUMPTION_OVERRIDES_FIELD,
    apply_scenario_overrides,
    resolve_assumption_overrides,
)
from core.contracts.assumptions import PriceBasis
from core.contracts.validation import ValidationError

#: 대장에 **있는** 키. 이 파일은 `docs/assumptions.yaml` 을 읽지 않는다 —
#: 읽으면 대장이 항목을 늘리거나 줄이는 날 이 검사가 함께 흔들리고, 여기서
#: 재는 것은 대장의 내용이 아니라 **통로**다.
_KEY = "a.key"

#: 대장 값이 **정수**인 항목. 실물의 `analysis.period_years`(`20` · `int`)가 이
#: 모양이고 R1 이 결론축을 움직인 자리가 정확히 여기다 — `true` 가 스칼라로
#: 통과하면 `int(True) == 1` 이 되어 분석기간이 **1년**이 된다.
_INT_KEY = "c.int"

#: 대장 값이 **문자열**인 항목(= 참조형 · `FR-601-AC6`). 실물 대장에는 지금
#: 참조형이 0건이지만 `AssumptionItem.value` 는 `float | int | str` 이고
#: `is_scalar()` 가 그 갈래를 가른다 — 형 대조는 그 갈래도 함께 져야 한다.
_REF_KEY = "d.ref"


def _item(key: str, value: float | int | str) -> AssumptionItem:
    return AssumptionItem(
        key=key,
        value=value,
        value_unit="원/kWh",
        base_year="2026",
        applicable_scope="검사",
        derivation_method="검사",
        source=None,
        verified_at=None,
        confidence=ConfidenceLevel.ASSUMED,
    )


def _ledger() -> AssumptionSet:
    return AssumptionSet(
        name="검사",
        version="1",
        items={
            _KEY: _item(_KEY, 10.0),
            "b.key": _item("b.key", 20.0),
            _INT_KEY: _item(_INT_KEY, 20),
            _REF_KEY: _item(_REF_KEY, "tariff.hv_single_contract.avg"),
        },
        price_basis=PriceBasis.NOMINAL,
    )


def _base_values() -> dict[str, Any]:
    """`resolve_assumption_overrides` 의 두 번째 인자 — 대장의 `키 → 값`.

    ⚠ **키 집합만 넘기지 않는다.** 키만 보면 「대장에 있는 키인가」까지만
    답하고 「그 자리에 이 형의 값이 들어갈 수 있는가」는 아무도 안 본다 —
    그 상태가 D-4 다(문자열이 기간 자리로 들어가 계산 깊은 곳에서 맨
    `TypeError` 로 터진다). 여기서 값을 함께 넘기는 것이 그 판정의 근거다.
    """
    return {key: item.value for key, item in _ledger().items().items()}


def _row(key: str, value: Any, reason: str | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {"key": key, "value": value}
    if reason is not None:
        row["reason"] = reason
    return row


# ── ① 오버라이드가 실제로 값을 바꾼다 ──────────────────────────────────


@pytest.mark.req("FR-602-AC1")
def test_an_override_actually_changes_the_value_that_is_read() -> None:
    """★ 시나리오가 적은 값이 **조회되는 값**이 된다.

    자료형이 오버라이드를 «담는» 것과 계산이 그 값을 «읽는» 것은 다르다.
    담기만 하면 붙임은 「바꿨다」를 인쇄하고 수는 옛 값으로 나온다.
    """
    provider = apply_scenario_overrides(_ledger(), [_row(_KEY, 99.0)])

    value = provider.get(_KEY)
    assert value is not None
    assert value.value == 99.0

    untouched = provider.get("b.key")
    assert untouched is not None and untouched.value == 20.0


# ── ② 사유가 함께 선다 (FR-602-AC2 · AC3) ──────────────────────────────


@pytest.mark.req("FR-602-AC2", "FR-602-AC3")
def test_the_changed_item_carries_base_and_override_and_reason() -> None:
    """★★ `overridden_items()` 에 셋이 **다** 선다.

    `base` 가 없으면 「변경」이 성립하지 않고(그 메서드 독스트링), `reason` 이
    없으면 `FR-602-AC3` 이 자료형에만 남고 통로에서 사라진다. 그래서 셋을
    **함께** 본다 — 둘만 보면 사유를 떨어뜨리는 통로가 초록불로 지나간다.
    """
    provider = apply_scenario_overrides(
        _ledger(), [_row(_KEY, 99.0, "사용자가 최근 계약단가로 고쳤다")]
    )

    changed = provider.overridden_items()
    assert set(changed) == {_KEY}
    assert changed[_KEY]["base"] == 10.0
    assert changed[_KEY]["override"] == 99.0
    assert changed[_KEY]["reason"] == "사용자가 최근 계약단가로 고쳤다"


@pytest.mark.req("FR-602-AC3")
def test_a_reason_is_optional_and_its_absence_is_carried_as_none() -> None:
    """사유는 **권장** 필드다 — 없어도 오버라이드는 성립한다.

    ⚠ 없는 것을 빈 문자열로 메우지 않는다. 「사유를 적지 않았다」와 「사유를
    빈 칸으로 적었다」는 다른 진술이고, 메우면 붙임이 둘을 구별하지 못한다.
    """
    provider = apply_scenario_overrides(_ledger(), [_row(_KEY, 99.0)])

    assert provider.overridden_items()[_KEY]["reason"] is None


# ── ③ 대장에 없는 키는 거부된다 (NFR-202 · 판정 ⓐ) ─────────────────────


def test_a_key_that_is_not_in_the_ledger_is_refused_not_ignored() -> None:
    """⚠ 대장 밖 키로 **새 전제를 만들 수 없다.**

    `overridden_items()` 는 `if key in self._items` 로 대장 밖 키를 이미
    걸러 낸다 — 즉 조용히 무시하면 **계산에도 안 먹고 붙임에도 안 뜬다.**
    사용자가 값을 고쳤는데 아무 데도 안 나타나는 것이 가장 나쁜 상태다.

    ⚠ **`req()` 마커를 달지 않았다.** 「대장 밖 키 거부」에 대응하는 수용기준이
    spec 에 없다 — `NFR-202-M1` 은 소스 리터럴 스캔이고 이 판정이 아니다.
    없는 조항을 지어 붙이면 추적표가 거짓 진술을 싣는다.
    """
    with pytest.raises(ValidationError) as caught:
        apply_scenario_overrides(_ledger(), [_row("없는.키", 1.0)])

    assert "없는.키" in caught.value.reason
    assert caught.value.field == f"scenario.{ASSUMPTION_OVERRIDES_FIELD}"


# ── ④ 가격 기준은 오버라이드로 바뀌지 않는다 ────────────────────────────


def test_the_price_basis_cannot_be_overridden() -> None:
    """⚠ `price_basis` 는 **값이 아니라 규약**이다 (`DV-7` · `FR-202`).

    시나리오가 기준을 바꿀 수 있으면 두 시나리오의 금액이 서로 다른 뜻을 갖고,
    표는 그려지는데 숫자가 비교 불가능해진다. `override()` 는 애초에 기준을
    인자로 받지 않으므로 자료형 쪽은 이미 막혀 있다 — 여기서 재는 것은
    **통로가 그 이름을 받아 주지 않는가**이다.

    ⚠ **`req()` 마커를 달지 않았다** — 위 ③과 같은 사유다.
    """
    ledger = _ledger()

    with pytest.raises(ValidationError):
        apply_scenario_overrides(ledger, [_row("price_basis", "실질")])

    overridden = apply_scenario_overrides(ledger, [_row(_KEY, 99.0)])
    assert overridden.price_basis is PriceBasis.NOMINAL


# ── ⑤ ★★★ 필드가 없으면 **같은 객체**다 — 결론축 불변의 근거 ───────────


def test_a_scenario_without_the_field_gets_the_very_same_provider_object() -> None:
    """★★★ 필드가 없으면 `provider` 를 **그대로** 돌려준다 — 동일성으로 잰다.

    같은 값을 가진 **새 객체**를 돌려주면 기본값 실행이 다른 객체로 다른 경로를
    돌게 되고, 그때 결론축이 움직여도 「오버라이드 때문인가 복제 때문인가」를
    산출물에서 가릴 수 없다. `is` 로 재는 이유가 그것이다 — 동등성(`==`)은
    복제를 통과시킨다.

    ⚠ **`req()` 마커를 달지 않았다** — 이것은 조항 검증이 아니라 **회귀 불변**
    단언이다(무보조 `npv` −11,552,270 이 움직이지 않는 근거).
    """
    ledger = _ledger()

    assert apply_scenario_overrides(ledger, None) is ledger


# ── ⑥ 모양이 틀린 입력은 거부된다 ───────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "what"),
    [
        ({_KEY: 99.0}, "평평한 매핑 — 사유를 실을 자리가 없다"),
        ([{"value": 99.0}], "`key` 가 없는 원소"),
        ([{"key": _KEY}], "`value` 가 없는 원소"),
        ("a.key=99", "목록이 아닌 것"),
        ([[_KEY, 99.0]], "매핑이 아닌 원소"),
        ([_row(_KEY, [1, 2])], "스칼라가 아닌 값"),
        ([_row(_KEY, 1.0), _row(_KEY, 2.0)], "같은 키를 두 번"),
        ([{"key": _KEY, "value": 1.0, "resaon": "오타"}], "모르는 필드"),
    ],
)
def test_a_malformed_overrides_field_is_refused(raw: object, what: str) -> None:
    """모양이 틀리면 **멈춘다** — 읽을 수 있는 부분만 읽지 않는다.

    ⚠ 특히 마지막 둘이 중요하다. 같은 키를 두 번 적으면 사전 갱신으로 **뒤가
    이기고** 앞 줄은 흔적 없이 사라진다. `reason` 의 오타(`resaon`)를 모르는
    필드로 흘려보내면 사유가 조용히 없어지고, 그 상태는 「사유를 적지 않았다」와
    붙임에서 구별되지 않는다.

    ⚠ **`req()` 마커를 달지 않았다** — 입력 모양 검증에 대응하는 수용기준이
    spec 에 없다(`NFR-303` 은 오류 **문면**의 3요소를 요구하며, 그것은 아래
    검사가 따로 본다).
    """
    with pytest.raises(ValidationError):
        resolve_assumption_overrides(raw, base_values=_base_values())
    assert what


@pytest.mark.req("NFR-303-M1")
def test_a_refusal_carries_the_three_elements() -> None:
    """거부 문면이 **필드·사유·조치** 셋을 갖는다 (`NFR-303`).

    셋 중 하나라도 빠지면 사람에게 남는 선택은 값을 하나씩 바꿔 보는 것이고,
    그때 가장 쉬운 선택이 「오버라이드를 지우기」다 — 고치려던 값을 포기한다.
    """
    with pytest.raises(ValidationError) as caught:
        resolve_assumption_overrides({_KEY: 99.0}, base_values=_base_values())

    assert caught.value.field
    assert caught.value.reason
    assert caught.value.action


# ── ⑦ D-3 참·거짓은 값이 아니다 — YAML 이 `yes`·`on` 을 그리로 읽는다 ────


@pytest.mark.parametrize("value", [True, False])
def test_a_boolean_is_refused_because_yaml_reads_yes_and_on_as_true(
    value: bool,
) -> None:
    """★★★★ `bool` 은 대장 값이 될 수 없다 — **결론축이 움직인 자리**다.

    ⚠⚠ YAML 은 따옴표 없는 `yes`·`on`·`true`(그리고 `no`·`off`·`false`)를
    **참·거짓으로 읽는다.** 그래서 사용자가 `analysis.period_years: true` 라고
    적으면 대장 값 자리에 `True` 가 앉고, `analysis_years()` 가 `int(True) == 1`
    을 받아 **분석기간이 1년**이 된다.

    R1 실측(`.orch/R63/result_R1.md` D-3) — 무보조 `npv` `-11,552,270` 에서
    `period_years: true (bool) -> npv=-924,900  Δ=+10,627,370`. 그리고 붙임 1 의
    「기준 전제 대비 변경 항목」은 `20 → True` 로 인쇄하므로 **검토자는 그것이
    「1년」이라는 것을 산출물에서 알 수 없다.** 예외는 어디에서도 나지 않았다.

    ⚠ **거짓(`False`)도 함께 잰다.** `no`·`off`·`false` 가 같은 자리로 들어오고
    `int(False) == 0` 은 「0년」이다 — 참만 막으면 반쪽이다.
    """
    with pytest.raises(ValidationError) as caught:
        apply_scenario_overrides(_ledger(), [_row(_INT_KEY, value)])

    assert caught.value.field == f"scenario.{ASSUMPTION_OVERRIDES_FIELD}"
    assert caught.value.reason
    assert caught.value.action


def test_the_scalar_tuple_alone_cannot_be_the_gate_for_a_boolean() -> None:
    """⚠⚠ `isinstance(True, int)` 가 **참**이다 — 스칼라 목록은 관문이 아니다.

    `_SCALARS` 에서 `bool` 을 빼는 것만으로는 **아무것도 달라지지 않는다.**
    `bool` 이 `int` 의 하위형이라 `isinstance(True, (int, float, str))` 는
    여전히 참이고, 그것이 D-3 이 어느 검사에도 안 걸린 이유다. 관문은
    `type(v) is bool` 로 **먼저** 서야 한다.

    이 검사가 붙드는 것은 그 순서다 — 아래 첫 단언이 참인 채로 둘째 단언이
    성립해야 하고, 누가 `type(...) is bool` 줄을 「스칼라 목록이 이미 본다」며
    지우면 둘째가 즉시 빨간불이 된다.
    """
    assert isinstance(True, int)
    assert isinstance(True, (int, float, str))

    with pytest.raises(ValidationError):
        resolve_assumption_overrides(
            [_row(_INT_KEY, True)], base_values=_base_values()
        )


# ── ⑧ D-4 대장 값의 **형**과 맞댄다 — 계산 깊은 곳에서 터지지 않게 ──────


@pytest.mark.parametrize(
    ("key", "value", "what"),
    [
        (_INT_KEY, "스무해", "정수 자리에 문자열 — 실측 `TypeError`"),
        (_KEY, "비싸다", "실수 자리에 문자열 — 실측 `ValueError`"),
    ],
)
def test_a_string_in_a_numeric_slot_is_refused_at_the_gate(
    key: str, value: str, what: str
) -> None:
    """★★★ 수 자리에 문자열이 오면 **관문이 거부한다.**

    고치기 전에는 문자열이 스칼라라서 통과했고, 값의 형을 대장과 맞대 보는
    자리가 없어 **계산 깊은 곳에서 맨 예외**로 터졌다 — R1 실측
    (`.orch/R63/result_R1.md` D-4):

        period_years: '스무해' -> TypeError: 전제 analysis.period_years 의 값이
          문자열입니다: '스무해'. … (FR-601-AC6)
        rec_price: '비싸다' -> ValueError: could not convert string to float: '비싸다'
        문자열을 기간에: TypeError | field=— | action=—

    ⚠ 그 자리는 `build_case_report()` 안이라 `NFR-303` 3요소가 **없다.** 같은
    파일의 다른 거부 다섯은 전부 3요소를 갖는데 이 갈래만 맨 예외였다.
    """
    with pytest.raises(ValidationError) as caught:
        apply_scenario_overrides(_ledger(), [_row(key, value)])

    assert caught.value.field == f"scenario.{ASSUMPTION_OVERRIDES_FIELD}"
    assert key in caught.value.reason
    assert what


def test_a_number_in_a_reference_slot_is_refused() -> None:
    """참조형(문자열) 자리에 수를 넣으면 거부한다 — 대칭이다.

    `AssumptionItem.is_scalar()` 가 「값이 스칼라인가 참조(문자열)인가」로
    갈래를 가른다. 참조 자리에 수가 앉으면 그 항목을 **해석하는** 층이
    문자열을 기대하고 수를 받는다 — 수 자리에 문자열이 온 것과 같은 사고이며,
    한쪽만 막으면 다른 쪽으로 들어온다.
    """
    with pytest.raises(ValidationError) as caught:
        apply_scenario_overrides(_ledger(), [_row(_REF_KEY, 99)])

    assert _REF_KEY in caught.value.reason


def test_a_string_override_on_a_reference_item_is_allowed() -> None:
    """⚠ **문자열 자체를 막는 것이 아니다.** 참조형 자리에는 문자열이 맞다.

    「스칼라가 아니면 거부」로 뭉뚱그리면 참조형 항목을 아무도 못 고치게 된다.
    관문이 보는 것은 「값의 형이 **그 자리와** 맞는가」이지 「문자열인가」가
    아니다 — 그 구별이 없으면 이 검사가 빨간불이 된다.
    """
    provider = apply_scenario_overrides(
        _ledger(), [_row(_REF_KEY, "tariff.hv_single_contract.energy_only")]
    )

    value = provider.get(_REF_KEY)
    assert value is not None
    assert value.value == "tariff.hv_single_contract.energy_only"


@pytest.mark.parametrize(
    ("key", "value", "what"),
    [
        (_INT_KEY, 25.5, "정수 자리에 실수 — 대장의 `int` 는 표기의 흔적이다"),
        (_INT_KEY, 25, "정수 자리에 정수"),
        (_KEY, 25, "실수 자리에 정수"),
        (_KEY, 25.5, "실수 자리에 실수"),
    ],
)
def test_a_number_slot_takes_any_number_int_and_float_are_not_split(
    key: str, value: float, what: str
) -> None:
    """★★ **수 자리에는 수를 받는다** — `int`/`float` 를 가르지 않는다(판정).

    갈래가 둘이었다. 대장 값이 `int` 일 때 `float` 오버라이드를 거부할 것인가:

    ⓐ **거부한다** — `analysis.period_years` 에 `2.7` 을 넣으면 소비자가
       `int()` 로 자를 수 있고, 「2.7년」이 조용히 「2년」이 된다
    ⓑ **받는다** — 대장의 `int`/`float` 는 **선언된 계약이 아니라 yaml 이 그
       값을 어떻게 적었는가의 흔적**이다. 실물 대장에서 같은 「%」 축인데
       `escalation.electricity_tariff` 는 `2.5`(float)이고
       `capex.modular_house.premium` 은 `15`(int)다. 같은 「원/kWh」 축인데
       `benefit.rec_price` 는 `70`(int)이고 아무도 그것을 「정수만 받는
       단가」로 선언하지 않았다 — ⓐ 로 가면 `rec_price: 120.5` 같은 **정당한
       편집이 31개 정수 항목에서 막힌다.**

    **ⓑ 를 골랐다.** 「2.7년」이 잘리는 것은 *형*이 아니라 *정수성*의 문제이고,
    그것을 판정하는 자리는 `DV-5` 다 — 여기서 흉내내면 판정하는 자리가 둘이
    되고, 그것이 이 관문의 경계 규약(*「형만 본다」*)이 막으려는 것이다.

    ⚠ **그래서 못 잡는 것이 남는다**: 뒤에 정수 검사가 없는 정수 항목에
    `2.7` 을 넣으면 소비자가 자를 수 있다. `.orch/R63/result_F2.md` §7 에
    적었다.
    """
    provider = apply_scenario_overrides(_ledger(), [_row(key, value)])

    resolved = provider.get(key)
    assert resolved is not None
    assert resolved.value == value
    assert what


@pytest.mark.parametrize("value", [-100.0, 0, 1e9])
def test_the_gate_judges_type_only_and_leaves_range_to_the_clauses(
    value: float,
) -> None:
    """⚠ **범위는 여기서 보지 않는다** — 음수·0·상한은 각 조항의 몫이다.

    `DV-5`(분석기간)·`REC 단가는 음수일 수 없습니다`(`ValueError`) 처럼 범위를
    판정하는 자리가 이미 있다. 관문이 그것을 흉내내면 같은 사실을 판정하는
    자리가 둘이 되고, 한쪽만 고쳐진 상태를 아무도 보지 않는다 — 이 저장소가
    반복해서 만난 형태다(`assert_basis_is_declared_once` 독스트링).

    ⚠ **이 검사는 「통과한다」를 붙드는 검사다.** 누가 관문에 범위 판정을 더하면
    빨간불이 되고, 그때 볼 것은 이 독스트링이다.
    """
    provider = apply_scenario_overrides(_ledger(), [_row(_KEY, value)])

    resolved = provider.get(_KEY)
    assert resolved is not None
    assert resolved.value == value


@pytest.mark.req("NFR-303-M1")
def test_a_type_refusal_carries_the_three_elements() -> None:
    """형 거부도 **필드·사유·조치** 셋을 갖는다 (`NFR-303`).

    D-4 의 본질은 「거부되지 않는다」가 아니라 **「거부가 3요소 없이 맨 예외로
    나온다」**였다 — `TypeError | field=— | action=—`. 그래서 거부되는 것만
    재면 반쪽이고, 문면이 셋을 갖는지 함께 본다.

    ⚠ 사유가 **대장 값을 함께 인쇄해야** 사람이 무엇에 맞춰 고칠지 안다 —
    「형이 다릅니다」만으로는 어느 형에 맞추라는 것인지 알 수 없다.
    """
    with pytest.raises(ValidationError) as caught:
        resolve_assumption_overrides(
            [_row(_INT_KEY, "스무해")], base_values=_base_values()
        )

    assert caught.value.field
    assert caught.value.reason
    assert caught.value.action
    assert "20" in caught.value.reason
