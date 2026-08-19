"""**연간화 규약이 선언되어 있고 실물과 맞는가** — `ValueStream` 계약 (R34).

## 무엇이 있었나

`annual_value()` 라는 이름 아래 **두 갈래**가 섞여 있었다. 잉여판매·REC 는
주어진 디스패치 창에서 물리량을 읽어 계산하고(대표일을 주면 대표일치가 나온다),
나머지 여섯은 생성자에서 받은 **연간** 수량으로 계산한다. 그 차이가 **어디에도
선언되어 있지 않았고**, 호출측(`core/casegrid/e2e_runner.py`)이 *정산 편익에는
365를 곱하고 첨두 절감에는 곱하지 않는다* 는 암묵 규약을 들고 있었다.

그 규약은 잉여판매·상계 둘에서만 맞았다. 실측:

    집합 PPA          502,605원/년  →  183,450,825원  (365배)
    분산특구 직접거래   59,130원/년  →   21,582,450원  (365배)

**아무 예외도 나지 않았다.** 케이스 그리드가 그 두 구조를 돌지 않았고, 배선
검사는 「구조를 넣으면 NPV 가 달라진다」만 보므로 전건 초록불이었다.

## 이 파일이 붙드는 것 넷

    선언이 있는가          ← 빠뜨리면 기동 시점에 막힌다
    선언이 실물과 맞는가   ★ **재어** 판정한다 — 창을 두 배로 주고 값을 본다
    호출측이 그것을 읽는가  ← 태그 목록을 들고 있으면 편익이 늘 때 낡는다
    진입점의 금액이 맞는가  ← 발전량 × 단가와 대조한다
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.assumption.provider import AssumptionSet
from core.casegrid.e2e_runner import DAYS_PER_YEAR, run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.contracts.der import DispatchResult
from core.contracts.units import to_won
from core.contracts.valuestream import Payer, ValueStream
from core.valuestream.settlement import PPA_RATIO_KEY, TARIFF_KEY
from tests.contract.valuestream_probes import (
    PROBES,
    assert_every_stream_has_a_probe,
    deployed_streams,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"

#: 대표일 24스텝. 값은 **역송**(양수)이며 창을 읽는 편익만 이것을 본다.
_ONE_DAY = tuple([1.0] * 24)


def _result(electric: tuple[float, ...]) -> DispatchResult:
    steps = len(electric)
    return DispatchResult(
        electric=list(electric),
        heat=[0.0] * steps,
        cool=[0.0] * steps,
        fuel=[0.0] * steps,
    )


@pytest.mark.req("FR-401-AC1")
def test_every_deployed_value_stream_declares_the_convention() -> None:
    """배포 편익 전건이 규약을 **선언한다** — 레지스트리를 순회해 본다.

    목록을 손으로 적지 않는 이유는 그것이 편익이 늘 때 낡기 때문이다.
    """
    classes = deployed_streams()
    assert classes, "편익 레지스트리가 비어 있다 — 순회가 0회 돌면 이 검사는 무의미하다"
    for cls in classes:
        assert "scales_with_dispatch_window" in vars(cls), (
            f"{cls.__qualname__} 이 연간화 규약을 선언하지 않았다"
        )
        assert isinstance(cls.scales_with_dispatch_window, bool)


@pytest.mark.req("FR-401-AC1")
def test_forgetting_the_declaration_is_refused_at_class_creation() -> None:
    """★ 선언을 빠뜨리면 **기동 시점에** 막힌다 — 계산이 끝난 뒤가 아니라.

    금액이 365배로 어긋나도 예외가 나지 않는 종류의 결함이므로, 늦게 알리는
    것은 알리지 않는 것과 크게 다르지 않다.
    """
    with pytest.raises(ValueError, match="scales_with_dispatch_window"):

        class _Forgot(ValueStream):
            tag = "_TestForgot"
            payer = Payer.OPERATOR

            def annual_value(self, dispatch: DispatchResult, *, year: int):
                return to_won(0)


@pytest.mark.req("FR-401-AC1")
def test_the_declaration_matches_what_the_class_actually_does() -> None:
    """★★ **선언과 구현이 갈리지 않는가 — 재어 본다.**

    창을 두 배로 주었을 때

        값이 두 배가 된다   → 창에서 읽는다 → `True` 여야 한다
        값이 그대로다       → 연간 수량이다 → `False` 여야 한다

    선언만 보는 검사는 *「`True` 라고 적어 두고 창을 읽지 않는」* 반대 방향의
    어긋남을 잡지 못한다. 그 어긋남은 365분의 1 을 만들며, 작아진 쪽이라
    **보수적으로 보이기까지 한다.**
    """
    streams = deployed_streams()
    assert_every_stream_has_a_probe()

    checked = 0
    for cls in streams:
        stream = cls(**PROBES[cls.tag])  # type: ignore[arg-type]
        one = float(stream.annual_value(_result(_ONE_DAY), year=1))
        two = float(stream.annual_value(_result(_ONE_DAY * 2), year=1))
        if not one and not two:
            continue  # 이 탐침 창으로는 0원인 편익 — 비례 여부를 잴 수 없다
        scales = two == pytest.approx(one * 2)
        assert scales == cls.scales_with_dispatch_window, (
            f"{cls.__qualname__}: 선언은 "
            f"scales_with_dispatch_window={cls.scales_with_dispatch_window} "
            f"인데 실물은 창을 두 배로 주었을 때 {one:,.0f} → {two:,.0f} 이다"
        )
        checked += 1
    assert checked >= 2, (
        f"비례 여부를 실제로 잰 편익이 {checked}건이다 — 탐침 창에서 전부 0원이면 "
        "이 검사가 아무것도 보지 않는다"
    )


@pytest.mark.req("FR-401-AC2.AggregatedPPA", "FR-205-AC1.AggregatedPPA")
def test_the_entry_point_does_not_multiply_an_already_annual_benefit() -> None:
    """★★ **진입점의 금액이 「전량 × 단가」와 같은가** — 365배가 되지 않는가.

    이 검사가 없으면 「집합 PPA」를 케이스 그리드로 돌릴 수 있게 된 것이 곧
    **365배로 틀린 수를 심의보고서에 싣는 통로**가 된다. 기대값을 러너에서
    가져오지 않고 **대장과 자원 제원에서 다시 세워** 대조한다.
    """
    provider = AssumptionSet.load_from_yaml(str(_ASSUMPTIONS))
    level_map = build_level_map(_ASSUMPTIONS)
    outcome = run_single_case_e2e(
        {},
        level_map=level_map,
        horizon_years=20,
        structure="집합 PPA",
        provider=provider,
    )
    (line,) = [b for b in outcome.basis.benefits if b.tag == "AggregatedPPA"]

    (pv,) = [r for r in outcome.resources if type(r).__name__ == "PV"]
    generation = pv.annual_generation_kwh(year=1)
    price = provider.require_float(TARIFF_KEY) * provider.require_float(PPA_RATIO_KEY)

    assert line.annual_won == pytest.approx(int(generation * price), abs=1), (
        f"집합 PPA 편익이 전량 × 단가와 다르다 — 리포트 {line.annual_won:,}원 · "  # noqa: RUF001
        f"대조 {generation:,.0f}kWh × {price:,.1f}원/kWh = {generation * price:,.0f}원"  # noqa: RUF001
    )
    assert "연간화 없음" in line.formula, (
        "산식이 연간화 규약을 말하지 않는다 — 검토자가 365를 다시 곱한다"
    )


@pytest.mark.req("FR-401-AC1")
def test_the_printed_formula_says_whether_it_was_annualised() -> None:
    """★★★ **인쇄된 산식이 연간화 여부를 말하는가** — 선언과 대조한다 (R36).

    ## 왜 금액 검사만으로는 부족한가

    위 검사들은 **금액**이 맞는지 본다. 그런데 R36 이 편익 산식에 대입값을
    싣게 하면서 **문면이 스스로 산술을 주장하게** 됐고, 그 주장은 금액과
    따로 틀릴 수 있다. 실측(변이 M4): 러너가 문면에서 `× 365일` 만 빼면

        대표일 잉여 역송 16.10kWh × 판매단가 110원/kWh = 646,415원

    이 실린다 — **금액은 맞는데 문장이 거짓**이다(16.10 × 110 = 1,771). 검토자가
    붙임 4 를 손으로 검산하면 365배 어긋난 값을 얻고, 그러면 **틀린 것은 리포트가
    아니라 자기 계산이라고 읽는다.** R35 ② 가 「두 끝의 값을 서로 바꿔 실어도
    거리만 보는 검사 일곱이 통과했다」에서 만난 것과 같은 형태다.

    ## 어떻게 다른 층에서 보는가

    기대값을 **레지스트리의 선언**(`scales_with_dispatch_window`)에서 가져오고
    실물은 **인쇄된 문면**에서 읽는다. 태그 목록을 적지 않는 이유는 늘 같다 —
    편익이 늘면 낡는다.
    """
    outcome = run_single_case_e2e(
        {}, level_map=build_level_map(_ASSUMPTIONS), horizon_years=20
    )
    declared = {cls.tag: cls.scales_with_dispatch_window for cls in deployed_streams()}
    assert outcome.basis.benefits, "편익 항목이 0건이면 이 검사는 아무것도 보지 않는다"

    for line in outcome.basis.benefits:
        printed = f"× {DAYS_PER_YEAR}일" in line.formula  # noqa: RUF001
        assert printed == declared[line.tag], (
            f"«{line.label}» 의 산식이 연간화 여부를 잘못 말한다 — "
            f"선언 {declared[line.tag]} · 문면 「{line.formula}」\n"
            "금액이 맞아도 문면이 거짓이면 검토자의 손검산이 365배 어긋나고, "
            "그러면 틀린 것은 리포트가 아니라 자기 계산이라고 읽습니다"
        )
