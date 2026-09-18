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
from core.casegrid.operating_lines import annualise
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


#: 곱하기 **전에** 원 단위로 반올림한다는 사실을 적는 문면 조각. 한 자리에서만
#: 정한다 — 두 검사가 각자 적으면 문면을 다듬는 날 한쪽만 낡는다.
_ROUNDING_NOTE = "원 단위로 반올림한 뒤"


@pytest.mark.req("FR-401-AC1")
def test_the_line_says_the_daily_amount_is_rounded_before_the_multiply() -> None:
    """★★ **창을 읽는 갈래만** 곱하기 전 반올림을 적는다 (R64/WP-FIX 결함 4).

    종전 문면은 `대표일 잉여 역송 2.95kWh × 판매단가 110원/kWh × 365일 =
    118,260원` 이었다. 인쇄된 피연산자를 그대로 곱하면 118,282.7 이라 **22.7원이
    남고**, 손계산으로 따라오는 검토자는 그 22원이 어디서 왔는지 물을 자리가
    없다. 실제 순서는 하루 금액을 원으로 만든 뒤 365를 곱하는 것이다.

    ⚠ **연간 수량으로 산정하는 갈래에는 붙이지 않는다** — 거기서는 참이 아니다
    (`cost_lines` 의 계통 구매도 연간 계산 뒤에 반올림하므로 정확히 닫힌다).
    기대값은 `× 365일` 검사와 같은 자리, 곧 **레지스트리의 선언**에서 온다.
    """
    assert_every_stream_has_a_probe()
    for cls in deployed_streams():
        stream = cls(**PROBES[cls.tag])  # type: ignore[arg-type]
        line = _benefit_line(stream, _PROBE_AMOUNT, "PV", _result())
        printed = _ROUNDING_NOTE in line.formula
        assert printed == cls.scales_with_dispatch_window, (
            f"{cls.__qualname__}: 선언은 "
            f"scales_with_dispatch_window={cls.scales_with_dispatch_window} "
            f"인데 문면은 「{line.formula}」다"
        )


@pytest.mark.req("FR-401-AC1")
def test_the_annual_amount_really_is_the_rounded_daily_times_the_days() -> None:
    """★★★ 그 문면이 **참인가** — 연간화가 실제로 그 순서로 곱한다.

    위 검사는 낱말이 있는가만 본다. 문면과 계산이 갈리면 그 문면은 거짓 진술이
    되므로, 여기서 `annualise()` 의 실물을 재서 *「하루 금액(정수 원) × 365」*
    임을 확인한다 — 반올림 자리가 `to_won()` 한 곳뿐이라는 `NFR-103` 경계가
    이 등식의 근거다.

    ⛔ 계산을 문면에 맞추는 것이 아니라 **문면을 계산에 맞춘** 것이므로, 이
    등식이 깨지면 결론축이 움직였다는 뜻이다.
    """
    assert_every_stream_has_a_probe()
    checked = 0
    for cls in deployed_streams():
        if not cls.scales_with_dispatch_window:
            continue
        stream = cls(**PROBES[cls.tag])  # type: ignore[arg-type]
        window = _result()
        daily = stream.annual_value(window, year=1)
        assert daily == int(daily), (
            f"{cls.__qualname__}: 하루 금액이 정수 원이 아니다 ({daily!r}) — "
            "`to_won()` 을 지나지 않았다면 이 문면의 전제가 깨진다"
        )
        ((_, annual),) = annualise([stream], window)
        assert annual == int(daily) * DAYS_PER_YEAR, (
            f"{cls.__qualname__}: 연간 금액 {annual:,}원이 "
            # RUF001: 실패 메시지가 산식 문면과 같은 모양이어야 대조가 된다.
            f"하루 {int(daily):,}원 × {DAYS_PER_YEAR}일 과 다르다 — "  # noqa: RUF001
            "문면이 적은 순서와 계산이 갈렸다"
        )
        checked += 1
    assert checked >= 2, f"실제로 대조한 창 편익이 {checked}건이다"
