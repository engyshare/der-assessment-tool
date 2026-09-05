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


def _item(key: str, value: float) -> AssumptionItem:
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
        items={_KEY: _item(_KEY, 10.0), "b.key": _item("b.key", 20.0)},
        price_basis=PriceBasis.NOMINAL,
    )


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
        resolve_assumption_overrides(raw, known_keys=(_KEY, "b.key"))
    assert what


@pytest.mark.req("NFR-303-M1")
def test_a_refusal_carries_the_three_elements() -> None:
    """거부 문면이 **필드·사유·조치** 셋을 갖는다 (`NFR-303`).

    셋 중 하나라도 빠지면 사람에게 남는 선택은 값을 하나씩 바꿔 보는 것이고,
    그때 가장 쉬운 선택이 「오버라이드를 지우기」다 — 고치려던 값을 포기한다.
    """
    with pytest.raises(ValidationError) as caught:
        resolve_assumption_overrides({_KEY: 99.0}, known_keys=(_KEY,))

    assert caught.value.field
    assert caught.value.reason
    assert caught.value.action
