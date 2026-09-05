"""오버라이드한 키를 **이 실행이 정말 읽었는가** — 사용 이력은 provider 가 센다.

## 왜 이 파일이 생겼는가 (R63/N3)

`tax.vat_rate` 는 대장 **안**에 있으나 아무도 읽지 않는다
(`core/contracts/der.py` ⑦ · `core/contracts/assumptions.py` 머리말). R63 이
오버라이드 통로를 열자 `vat_rate: 1e9` 가 관문을 정당하게 통과하고 붙임은
`0.1 → 1000000000.0` 을 인쇄하는데 **수는 한 푼도 안 움직인다** — 화면은 고친
값을 인쇄하고 수는 옛 값으로 돈다. `scenario_overrides.py` 머리말이 그 상태를
「가장 나쁘다」로 지목한 자리다.

**거부가 답이 아니다**(어느 키가 읽히는지는 갈래·자원 구성에 따라 실행마다
다르고, 목록을 코드에 박으면 낡는다). **값을 계산에 배선하는 것도 이 축의
몫이 아니다**(취득가에 부가세를 넣는가는 경제 모형 판정이다). 그래서 이 축이
세우는 것은 **「거부도 통과도 아닌 표시」**다 — 통과시키되 그 실행이 그 값을
읽었는지를 산출물에 적는다.

이 파일은 그 표시의 **재료**를 잰다 — `AssumptionSet` 이 자기를 지나간 읽기를
세는가, 그리고 그 이력이 **새 객체로 따라가지 않는가**.

⚠ **조항 마커를 달지 않았다.** `FR-602-AC2`·`AC3` 은 「변경 항목」과 「사유」를
요구하고 이 표시는 그 둘 중 어느 것도 아니다 — 근거 없는 마커를 달면
`docs/traceability.md` 가 거짓 인용을 싣는다(R63/N3 판정).
"""

from __future__ import annotations

from pathlib import Path

from core.assumption.provider import AssumptionSet

_ASSUMPTIONS = Path(__file__).resolve().parents[2] / "docs" / "assumptions.yaml"
_VAT = "tax.vat_rate"
_PV = "capex.pv.rooftop"


def _ledger() -> AssumptionSet:
    return AssumptionSet.load_from_yaml(str(_ASSUMPTIONS))


def test_the_set_counts_the_keys_it_handed_out() -> None:
    """`get()` 이 값을 내준 키만 이력에 선다 — 세지 않으면 표시할 재료가 없다."""
    ledger = _ledger()

    assert ledger.keys_read() == frozenset(), "아무것도 안 물었는데 이력이 섰다"

    ledger.get(_VAT)

    assert _VAT in ledger.keys_read()
    assert _PV not in ledger.keys_read(), "묻지 않은 키가 이력에 섰다"


def test_the_history_is_a_snapshot_and_not_a_live_view() -> None:
    """`keys_read()` 가 내준 것은 **그때의 사본**이다.

    살아 있는 집합을 그대로 내주면 조립부가 이력을 굳힌 뒤에도 붙임의 읽기가
    그 안으로 흘러들어 오고, 그때 「계산이 읽었다」와 「붙임이 읽었다」가
    같은 집합에 섞인다 — 표시가 조용히 거짓이 된다.
    """
    ledger = _ledger()
    ledger.get(_VAT)

    frozen = ledger.keys_read()
    ledger.get(_PV)

    assert _PV not in frozen, "굳힌 이력에 나중 읽기가 흘러들었다"
    assert _PV in ledger.keys_read()


def test_a_new_set_from_override_starts_counting_afresh() -> None:
    """★ `override()` 가 만든 새 객체에 **앞 객체의 이력이 따라오지 않는다.**

    provider 는 값이 불변이고 `override()` 는 **새 객체**를 돌려준다. 이력이
    따라가면 「앞 실행이 읽었다」가 「이 실행이 읽었다」로 읽히고, 그것은 이
    축이 막으려는 바로 그 어긋남(인쇄된 것과 실제가 다르다)을 표시 쪽에
    다시 만든다.
    """
    ledger = _ledger()
    ledger.get(_VAT)
    assert _VAT in ledger.keys_read()

    edited = ledger.override({_VAT: 1e9})

    assert edited.keys_read() == frozenset(), "새 실행이 앞 실행의 이력을 물려받았다"
    assert _VAT in ledger.keys_read(), "앞 객체의 이력이 사라졌다"


def test_the_history_does_not_join_equality_or_hash() -> None:
    """이력은 **값이 아니라 사용 이력**이다 — 같은 대장은 읽어도 같은 대장이다.

    `AssumptionSet` 은 자기 `__eq__`·`__hash__` 를 두지 않으므로 동치는
    동일성이고 이력이 끼어들 자리가 없다. 그 사실을 검사로 붙들어 둔다 —
    나중에 dataclass 로 바꾸는 사람이 `compare=False` 를 잊으면 여기서 선다.
    """
    ledger = _ledger()
    before = hash(ledger)
    same = ledger

    ledger.get(_VAT)

    assert hash(ledger) == before
    assert ledger == same
