"""**러너가 편익의 산식을 그대로 싣는가** — 붙임 4 의 한 줄 (R36).

## 무엇이 있었나

R36 이 `ValueStream.formula()` 를 세워 대입값을 편익 쪽으로 옮겼다. 그런데
**러너가 그것을 버리고 금액만 실어도 아무도 잡지 않았다** — 실측(변이 M9):
연간 편익 갈래의 문면을 `연 199,680원 (연간 수량으로 산정 · 연간화 없음)` 로
되돌려도 전건 초록불이었다. 계약 검사는 `formula()` **의 출력**을 보고, 붙임 4
회귀 검사는 **잉여판매 한 갈래**를 본다 — 그 사이에 *「러너가 그것을 쓰는가」*
가 비어 있었다.

이것이 R36 이 고치려던 결함 그 자체의 **반대쪽 가지**다. 원래 결함은 창 비례
갈래에서 대입값이 없었던 것이고, 이 자리는 연간 갈래에서 같은 일이 일어나도
막을 것이 없는 상태였다.

## 왜 비공개 도우미를 직접 부르는가

`CaseOutcome` 은 편익 **인스턴스**를 내보내지 않는다(자원과 운전 결과만 낸다).
그래서 진입점만으로는 *「편익이 낸 문면」* 과 *「리포트에 실린 문면」* 을 나란히
둘 수 없다. 인스턴스를 내보내게 고치는 것은 **밖에서 보이는 수가 한 자리도
움직이지 않는 변경**이라 R34 가 「붙들 수 없는 갈래」로 미뤄 둔 그 항목이며,
검사를 세우려고 산출물 자료형을 넓히는 것은 순서가 거꾸로다.

⚠ 그래서 **이 검사는 진입점 검사를 대신하지 않는다.** 금액이 맞는지는
`test_annualisation_convention.py` 가 대장과 자원 제원에서 따로 세워 본다.
"""
from __future__ import annotations

import pytest

from core.casegrid.e2e_runner import DAYS_PER_YEAR, _benefit_line
from core.contracts.der import DispatchResult
from tests.contract.valuestream_probes import (
    PROBES,
    assert_every_stream_has_a_probe,
    deployed_streams,
)

_ONE_DAY = tuple([1.5] * 24)
#: 산식의 어느 대입값과도 겹치지 않는 금액 — 겹치면 「산식이 실렸다」가 금액과
#: 우연히 맞아 통과할 수 있다.
_PROBE_AMOUNT = 987_654


def _result() -> DispatchResult:
    steps = len(_ONE_DAY)
    return DispatchResult(
        electric=list(_ONE_DAY),
        heat=[0.0] * steps,
        cool=[0.0] * steps,
        fuel=[0.0] * steps,
    )


@pytest.mark.req("FR-401-AC1")
def test_the_line_carries_the_benefit_formula_verbatim() -> None:
    """★★★ 편익이 낸 문면이 **글자 그대로** 붙임 4 의 줄 안에 있다.

    「포함」으로 보는 이유는 러너가 앞뒤에 연간화와 합계를 붙이기 때문이다.
    그 둘 **말고는 손대지 않는다** 가 이 검사가 지키는 것이다 — 러너가 문면을
    다듬기 시작하면 대입값을 편익 쪽에 둔 뜻이 사라진다.
    """
    assert_every_stream_has_a_probe()
    checked = 0
    for cls in deployed_streams():
        stream = cls(**PROBES[cls.tag])  # type: ignore[arg-type]
        dispatch = _result()
        body = stream.formula(dispatch, year=1)
        line = _benefit_line(stream, _PROBE_AMOUNT, "PV", dispatch)

        assert body in line.formula, (
            f"{cls.__qualname__}: 러너가 편익의 산식을 싣지 않는다 —\n"
            f"  편익  「{body}」\n  실린 것「{line.formula}」\n"
            "금액만 실으면 무엇에 얼마를 곱했는지가 붙임 4 에서 사라집니다"
        )
        checked += 1
    assert checked >= 8, f"실제로 대조한 편익이 {checked}건이다"


@pytest.mark.req("FR-401-AC1")
def test_the_line_adds_the_annualisation_only_where_it_is_declared() -> None:
    """★★ 러너가 붙이는 것은 **선언이 요구할 때만** 붙는다.

    창 비례 편익에는 `× 365일` 이 붙고 아닌 편익에는 붙지 않는다. 기대값은
    레지스트리의 선언에서 오고 실물은 인쇄된 문면에서 온다 — 두 층이다.
    """
    assert_every_stream_has_a_probe()
    for cls in deployed_streams():
        stream = cls(**PROBES[cls.tag])  # type: ignore[arg-type]
        line = _benefit_line(stream, _PROBE_AMOUNT, "PV", _result())
        printed = f"× {DAYS_PER_YEAR}일" in line.formula  # noqa: RUF001
        assert printed == cls.scales_with_dispatch_window, (
            f"{cls.__qualname__}: 선언은 "
            f"scales_with_dispatch_window={cls.scales_with_dispatch_window} "
            f"인데 문면은 「{line.formula}」다"
        )


@pytest.mark.req("FR-401-AC1")
def test_the_line_states_the_total_it_was_given() -> None:
    """★ 합계는 **러너가 받은 그 금액**이다 — 산식이 다시 세지 않는다.

    편익이 합계를 적지 않는 이유가 여기 있다(`ValueStream.formula` 계약).
    같은 수의 출처가 둘이면 갈릴 수 있고, 갈려도 표는 그럴듯하다.
    """
    assert_every_stream_has_a_probe()
    for cls in deployed_streams():
        stream = cls(**PROBES[cls.tag])  # type: ignore[arg-type]
        line = _benefit_line(stream, _PROBE_AMOUNT, "PV", _result())
        assert f"= {_PROBE_AMOUNT:,}원" in line.formula, (
            f"{cls.__qualname__}: 문면의 합계가 받은 금액과 다르다 — "
            f"「{line.formula}」"
        )
        assert line.annual_won == _PROBE_AMOUNT
