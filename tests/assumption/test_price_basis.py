"""가격 기준을 집합이 **1회 선언하고 전 항목에 강제**하는가 — `DV-7` / R31.

`DV-7` 원문: *「모든 금액은 명목 원(KRW), **실질/명목 구분을 `AssumptionSet`
수준에서 1회 선언하고 전 항목에 강제**」*

R24 가 이 규칙을 `NOT_YET_THROWN` 으로 되돌리며 남긴 판정이 정확했다 —
*「발동시킬 사건이 없는 것이 아니라 강제가 아직 없다」*. 없던 것은 **선언할
자리**였고 이 라운드가 그것을 만들었다.

**왜 이 규칙이 중요한가.** 같은 `2.5` 가 실질이면 물가 위의 실질 상승이고
명목이면 물가를 포함한 상승이다 — **수치는 같고 20년 누계가 크게 달라진다.**
그리고 어느 쪽으로 읽었는지는 **결과에 나타나지 않는다.**

붙드는 것 넷:

    ① 선언이 없으면 대장을 읽지 않는다        「1회 선언」의 「선언」
    ② 알 수 없는 값은 거부한다                 오타가 조용히 통과하지 않는다
    ③ 항목이 다시 선언하면 거부한다            「전 항목에 강제」
    ④ 오버라이드가 기준을 바꾸지 못한다        기준은 값이 아니라 규약이다

**③이 이 파일의 핵심이다.** ①②만 두면 「선언이 있다」를 확인할 뿐이고, 항목이
자기 기준을 따로 갖는 것을 아무도 막지 않는다 — 그러면 집합 선언은 있는데
대장은 두 기준을 담게 되고, 그 상태가 정확히 「선언은 있고 강제는 없다」다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.assumption.item import AssumptionItem, ConfidenceLevel
from core.assumption.provider import AssumptionSet
from core.contracts.assumptions import PriceBasis, assert_basis_is_declared_once
from core.contracts.validation import ValidationError

LEDGER = Path(__file__).resolve().parents[2] / "docs/assumptions.yaml"


def _item(key: str, *, value_unit: str) -> AssumptionItem:
    return AssumptionItem(
        key=key,
        value=1.0,
        value_unit=value_unit,
        base_year="2026",
        applicable_scope="검사용",
        derivation_method="검사용",
        source=None,
        verified_at=None,
        confidence=ConfidenceLevel.ASSUMED,
    )


# ── ① 선언이 없으면 대장을 읽지 않는다 ───────────────────────────────

@pytest.mark.req("NFR-303-M1")
def test_a_ledger_without_a_declaration_is_refused(tmp_path: Path) -> None:
    """최상위 `price_basis` 가 없는 대장은 거부된다.

    **기본값으로 메우지 않는 이유**는 `MissingAssumption` 이 값에 대해 하는
    판단과 같다 — 메우면 「선언하지 않았다」가 「명목이라고 선언했다」와
    구별되지 않고, 그 상태는 결과가 그럴듯해서 스스로 드러나지 않는다.
    """
    path = tmp_path / "no_basis.yaml"
    path.write_text("version: 1\nassumptions: []\n", encoding="utf-8")

    with pytest.raises(ValidationError) as caught:
        AssumptionSet.load_from_yaml(str(path))

    assert caught.value.rule == "DV-7"
    assert caught.value.field == "assumption_set.price_basis"
    # 조치가 **무엇을 적어야 하는지**를 말한다 (NFR-303 3요소)
    assert "price_basis" in caught.value.action


@pytest.mark.req("NFR-303-M1")
def test_the_real_ledger_declares_nominal(tmp_path: Path) -> None:
    """실물 대장이 **명목**을 선언한다 — 그리고 그 선언이 읽힌다.

    이 단언이 없으면 위 거부만 있고 「정상 경로가 실제로 선언을 나른다」를
    아무도 확인하지 않는다. `tmp_path` 는 쓰지 않지만 실물 대장을 건드리지
    않는다는 뜻으로 서명에 남긴다.
    """
    assumptions = AssumptionSet.load_from_yaml(str(LEDGER))

    assert assumptions.price_basis is PriceBasis.NOMINAL


# ── ② 알 수 없는 값은 거부한다 ───────────────────────────────────────

@pytest.mark.req("NFR-303-M1")
def test_an_unknown_basis_is_refused(tmp_path: Path) -> None:
    """`실질`·`명목` 밖의 문면은 거부된다 — 오타가 조용히 통과하지 않는다.

    통과시키면 그 대장의 기준이 무엇인지 아무도 모르는 채 계산이 돈다.
    """
    path = tmp_path / "bad_basis.yaml"
    path.write_text(
        'version: 1\nprice_basis: "실질명목"\nassumptions: []\n', encoding="utf-8"
    )

    with pytest.raises(ValidationError) as caught:
        AssumptionSet.load_from_yaml(str(path))

    assert caught.value.rule == "DV-7"
    assert "실질명목" in caught.value.reason


# ── ③ 항목이 다시 선언하면 거부한다 (「전 항목에 강제」) ──────────────

@pytest.mark.req("NFR-303-M1")
def test_an_item_that_redeclares_the_basis_is_refused() -> None:
    """★★★ 항목의 단위 문면이 실질/명목을 다시 말하면 집합이 서지 못한다.

    그 자리가 **집합 선언과 갈릴 수 있는 유일한 자리**다. 갈리면 어느 기준으로
    계산했는지 결과만 보고는 알 수 없다.

    ⚠ **집합이 명목인데 항목이 「명목」이라 적어도 거부한다** — 아래 둘째
    단언이 그것이다. 같은 사실이 두 곳에 있으면 집합 선언을 바꿀 때 항목 문면이
    따라오지 않고, **바꾼 사람은 성공했다고 믿는다.** R31 이 실물 대장에서
    그 사본 하나를 지웠다(`escalation.electricity_tariff` 가 「%/년 (명목)」).
    """
    # 어긋난 경우 — 집합은 명목, 항목은 실질
    with pytest.raises(ValidationError) as caught:
        AssumptionSet(
            name="검사", version="1",
            items={"a.key": _item("a.key", value_unit="실질원/kWh")},
            price_basis=PriceBasis.NOMINAL,
        )
    assert caught.value.rule == "DV-7"
    assert "a.key" in caught.value.reason

    # ★ 같은 경우도 거부한다 — 사본이기 때문이다
    with pytest.raises(ValidationError, match=r"a\.key"):
        AssumptionSet(
            name="검사", version="1",
            items={"a.key": _item("a.key", value_unit="%/년 (명목)")},
            price_basis=PriceBasis.NOMINAL,
        )


@pytest.mark.req("NFR-303-M1")
def test_a_plain_unit_passes() -> None:
    """단위가 기준을 말하지 않으면 통과한다 — 무엇이든 거부하지 않는다.

    거부만 검사하면 **모든 항목을 거부하는** 구현도 통과한다.
    """
    assumptions = AssumptionSet(
        name="검사", version="1",
        items={"a.key": _item("a.key", value_unit="원/kWh")},
        price_basis=PriceBasis.REAL,
    )

    assert assumptions.price_basis is PriceBasis.REAL


def test_the_rule_lives_in_the_contract_not_the_implementation() -> None:
    """규칙 함수가 계약 층에 있고 직접 부를 수 있다.

    구현이 둘 이상 생기면 각자 이 판정을 지어내고, v1.1 에서 여섯 자원이
    `capex_vat()` 를 각자 지어낸 것과 같은 일이 일어난다.
    """
    # 통과 경로
    assert_basis_is_declared_once(
        price_basis=PriceBasis.NOMINAL, items=[("a", "원"), ("b", None)]
    )
    # 거부 경로 — 두 기준 토큰 모두 잡는다
    for unit in ("실질 원", "명목 원"):
        with pytest.raises(ValidationError):
            assert_basis_is_declared_once(
                price_basis=PriceBasis.NOMINAL, items=[("a", unit)]
            )


# ── ④ 오버라이드가 기준을 바꾸지 못한다 ──────────────────────────────

@pytest.mark.req("NFR-303-M1")
def test_override_carries_the_basis_and_cannot_change_it() -> None:
    """★ 오버라이드는 **값**을 바꾸고 **기준**은 그대로 나른다.

    시나리오가 기준을 바꿀 수 있으면 두 시나리오의 금액이 서로 다른 뜻을 갖고,
    `FR-202`(같은 전제 위 비교)가 성립하지 않는다 — 표는 그려지고 숫자는
    비교 불가능해진다.

    복제가 기준을 **잃는** 쪽도 이 단언이 함께 막는다(그때는 `TypeError` 가
    아니라 조용한 기본값이 문제였을 것이다 — 그래서 기본값을 두지 않았다).
    """
    base = AssumptionSet(
        name="검사", version="1",
        items={"a.key": _item("a.key", value_unit="원/kWh")},
        price_basis=PriceBasis.REAL,
    )

    overridden = base.override({"a.key": 99.0})

    assert overridden.price_basis is PriceBasis.REAL
    value = overridden.get("a.key")
    assert value is not None and value.value == 99.0
