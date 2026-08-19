"""**편익 산식이 대입값을 싣는가** — `ValueStream.formula` 계약 (R36).

## 무엇이 있었나

양식 §3 붙임 4 는 *「편익별 산식·**대입값**(발전량·단가)」* 을 요구하는데 실물은
갈래마다 **`대표일 1,771원 × 365일`** 한 줄이었다 — 곱해서 나온 금액만 있고
**무엇에 얼마를 곱했는지가 없다.** 같은 리포트의 비용 쪽은 같은 자리에
`대표일 수전 6.19kWh × 365일 × 120원/kWh` 로 수량과 단가를 갈라 적는다.

그래서 **영향도 1위 인자(잉여 판매단가 110원/kWh)의 값이 붙임 4 어디에도
없었다.** 검토자가 「이 편익이 왜 646,415원인가」를 물으면 붙임 4 가 답하지
못하고, 수량이 틀렸는지 단가가 틀렸는지도 가릴 수 없다 — **둘은 서로 다른
사람이 고친다**(단가는 대장, 수량은 운전).

## 이 파일이 붙드는 것 넷

    계약을 지키는가        ← 빠뜨리면 인스턴스를 못 만든다
    대입값을 다 싣는가     ★ 생성자에 넘긴 값 전건이 문면에 있는가
    값을 **읽는가**        ★ 값을 바꾸면 문면이 함께 바뀌는가 — 상수 문면을 잡는다
    남의 몫을 적지 않는가  ← 연간화(× 365)와 합계(= N원)는 호출측의 것이다

⚠ **기대값이 검사 대상에서 오지 않는다.** 대입값은 탐침 표(검사 소유)가 정하고
문면은 편익(구현)이 낸다 — 두 층이다. 한 층에서만 읽으면 동어반복이 된다
(R35 ① 의 초록불 변이가 그것이었다).
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import fields, is_dataclass
from typing import Any

import pytest

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.valuestream import Payer, ValueStream
from tests.contract.valuestream_probes import (
    PROBES,
    assert_every_stream_has_a_probe,
    deployed_streams,
)

#: 대표일 24스텝. 값은 **역송**(양수)이며 창을 읽는 편익만 이것을 본다.
#: 24라는 수가 산식에 나오지 않도록 1.0 이 아닌 값을 쓴다 — 합이 24가 되면
#: 「대입값이 실렸다」가 스텝 수와 우연히 맞을 수 있다.
_ONE_DAY = tuple([1.5] * 24)


def _result(electric: tuple[float, ...]) -> DispatchResult:
    steps = len(electric)
    return DispatchResult(
        electric=list(electric),
        heat=[0.0] * steps,
        cool=[0.0] * steps,
        fuel=[0.0] * steps,
    )


def _numeric_terms(kwargs: dict[str, object]) -> Iterator[tuple[str, float]]:
    """탐침 인자에서 **산식에 실려야 할 수**를 뽑는다.

    셋을 다르게 다룬다 —

        스칼라      그 값이 그대로 실려야 한다
        수열        **합**이 실려야 한다 (`PeakShaving` 의 12개월 감축량은
                    `kW·월` 합으로 실린다. 열두 값을 낱개로 요구하면 산식이
                    표가 되고, 그것은 붙임 4 가 지는 몫이 아니다)
        데이터클래스 **각 필드**가 실려야 한다 (`DistributedSubItems` 다섯은
                    합만 적으면 「0원」과 「항목이 없다」가 같은 모양이 된다)
    """
    for name, value in kwargs.items():
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            yield name, float(value)
        elif isinstance(value, (list, tuple)):
            yield name, float(sum(value))
        elif is_dataclass(value) and not isinstance(value, type):
            for field in fields(value):
                yield f"{name}.{field.name}", float(getattr(value, field.name))


def _renderings(value: float) -> tuple[str, ...]:
    """이 수가 문면에 적힐 수 있는 모양들.

    ⚠ **정밀도를 하나로 못 박지 않는다.** 단가는 `110원/kWh`, 물리량은
    `16.10kWh` 처럼 갈래마다 자리수가 다르고, 그것을 여기서 정하면 이 검사가
    **표기 규정을 겸하게** 된다. 이 검사가 묻는 것은 *「그 값이 실렸는가」*
    뿐이다.
    """
    return (f"{value:,.0f}", f"{value:,.1f}", f"{value:,.2f}", f"{value:g}")


def _formula_of(cls: type[ValueStream], **overrides: Any) -> str:
    kwargs = {**PROBES[cls.tag], **overrides}
    stream = cls(**kwargs)  # type: ignore[arg-type]
    return stream.formula(_result(_ONE_DAY), year=1)


@pytest.mark.contract
@pytest.mark.req("FR-401-AC1")
def test_forgetting_the_formula_is_refused() -> None:
    """★ 산식을 빠뜨린 편익은 **인스턴스를 만들 수 없다.**

    `scales_with_dispatch_window` 는 클래스 생성 시점에 막지만 이쪽은 추상
    메서드라 **인스턴스 생성 시점**이다. 그 차이를 감수하는 이유는, 빠진 산식이
    만드는 결함이 *「붙임 4 의 한 줄이 비어 있다」* 로 **눈에 보이는** 것이기
    때문이다 — 365배처럼 그럴듯한 수로 조용히 지나가지 않는다.
    """
    class _NoFormula(ValueStream):
        tag = "_TestNoFormula"
        scales_with_dispatch_window = False
        payer = Payer.OPERATOR

        def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
            return to_won(0)

    with pytest.raises(TypeError, match="formula"):
        _NoFormula(name="산식 없는 편익")  # type: ignore[abstract]


@pytest.mark.contract
@pytest.mark.req("FR-401-AC1")
def test_every_formula_carries_every_substituted_value() -> None:
    """★★ 생성자에 넘긴 대입값 **전건**이 산식 문면에 있다.

    이것이 R36 이 고친 결함 그 자체다 — 잉여 판매단가가 붙임 4 어디에도 없었다.
    """
    assert_every_stream_has_a_probe()
    checked = 0
    for cls in deployed_streams():
        text = _formula_of(cls)
        for name, value in _numeric_terms(PROBES[cls.tag]):
            assert any(shape in text for shape in _renderings(value)), (
                f"{cls.__qualname__}.formula() 가 대입값 «{name}={value:,}» 을 "
                f"싣지 않는다 — 실린 문면: 「{text}」\n"
                "붙임 4 는 산식의 대입값(수량·단가)을 요구한다. 금액만 적으면 "
                "수량이 틀렸는지 단가가 틀렸는지 검토자가 가릴 수 없다"
            )
            checked += 1
    assert checked >= 8, (
        f"실제로 대조한 대입값이 {checked}건이다 — 탐침이 비면 이 검사는 "
        "아무것도 보지 않는다"
    )


@pytest.mark.contract
@pytest.mark.req("FR-401-AC1")
def test_the_formula_reads_the_value_rather_than_reciting_it() -> None:
    """★★★ 값을 바꾸면 **문면이 함께 바뀐다** — 상수 문면을 잡는다.

    위 검사는 *「그 수가 문면에 있는가」* 만 본다. 그래서 산식을 **탐침 값이
    박힌 상수 문자열**로 써 두면 전건 통과한다 — 대입값을 「읽어서」 적는 것과
    「적어 둔 것이 마침 같은 것」이 같은 모양이 된다. R35 ① 이 만난
    *「검사가 자기 검사 대상에서 정본을 읽어 왔다」* 와 같은 결의 함정이다.

    그래서 **스칼라 인자를 하나씩 바꿔** 문면이 따라 움직이는지 본다.

    ⚠ 수열·데이터클래스 인자는 여기서 건너뛴다 — 자료형마다 바꾸는 법이 달라
    이 검사가 자료형 목록을 들게 되고, 그 목록은 편익이 늘 때 낡는다. 그쪽은
    위 검사가 **합·필드별로** 이미 본다.
    """
    assert_every_stream_has_a_probe()
    checked = 0
    for cls in deployed_streams():
        base = _formula_of(cls)
        for name, value in PROBES[cls.tag].items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            moved = _formula_of(cls, **{name: float(value) * 2 + 1})
            assert moved != base, (
                f"{cls.__qualname__}.formula() 가 «{name}» 을 바꿔도 그대로다 — "
                f"「{base}」\n산식이 대입값을 읽지 않고 적어 둔 것이다"
            )
            checked += 1
    assert checked >= 8, f"실제로 흔들어 본 인자가 {checked}건이다"


@pytest.mark.contract
@pytest.mark.req("FR-401-AC1")
def test_the_formula_leaves_annualisation_and_the_total_to_the_caller() -> None:
    """★★ 산식은 **연간화와 합계를 적지 않는다.**

    창 비례 여부는 `scales_with_dispatch_window` 가 선언하고 `× 365일` 은
    호출측이 붙인다. 편익도 함께 적으면 두 곳이 갈릴 수 있고 **갈린 쪽이
    365배**다 — R34 가 실제로 밟은 그 자리다.

    합계(`= N원`)도 마찬가지로 `annual_value()` 의 몫이다. 여기서 또 내면 같은
    수의 출처가 둘이 되고, 둘이 갈려도 표는 그럴듯하다.
    """
    assert_every_stream_has_a_probe()
    for cls in deployed_streams():
        text = _formula_of(cls)
        assert "365" not in text, (
            f"{cls.__qualname__}.formula() 가 연간화를 적었다 — 「{text}」\n"
            "호출측이 선언을 보고 붙인다. 두 곳이 적으면 갈린 쪽이 365배다"
        )
        assert "=" not in text, (
            f"{cls.__qualname__}.formula() 가 합계를 적었다 — 「{text}」\n"
            "합계는 annual_value() 가 낸다"
        )
