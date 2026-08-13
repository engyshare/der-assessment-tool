"""DV-9(전환)·DV-10(신설) — R24 WP-34A.

DV-9 는 이미 있던 `_validate_coupled_sets` 검사를 `ValidationError` 로 전환한다
(문면은 §7.3 대장 그대로). DV-10 은 새로 강제한다 — 지금까지는
`RunPlan.requires_confirmation` 깃발만 계산되고 아무도 읽지 않았다
(`run_cases` 가 확인 여부를 받지 않았다). 그래서 케이스 수가 임계치를 넘어도
러너가 그대로 전부 실행됐다.
"""

from __future__ import annotations

import pytest

from core.casegrid import Case, CaseGrid, CaseVariable, CoupledSet, run_cases
from core.casegrid.execution import DEFAULT_CONFIRMATION_THRESHOLD
from core.contracts.validation import ValidationError


@pytest.mark.req("FR-802-AC3")
@pytest.mark.req("NFR-303-M1")
def test_dv9_mismatched_coupled_set_lengths_raise_structured_error() -> None:
    """FR-802-AC3 oracle: pv_cost 는 3수준, ess_cost 는 2수준 — 손으로 센 값이다.

    구조로 꺼내 `field`·`rule`·어긋난 길이(3, 2)가 사유에 있는지 단언한다.
    「예외가 났다」만 보면 메시지가 비어도 통과하므로 여기서 다루지 않는다.
    """
    with pytest.raises(ValidationError) as caught:
        CaseGrid(
            variables=(
                CaseVariable("pv_cost", ("low", "base", "high")),
                CaseVariable("ess_cost", ("low", "base")),
            ),
            coupled_sets=(CoupledSet("bad_cost_bundle", ("pv_cost", "ess_cost")),),
        )

    parts = caught.value.as_dict()
    assert parts["rule"] == "DV-9"
    assert parts["field"] == "casegrid.coupled_sets"
    assert "bad_cost_bundle" in (parts["reason"] or "")
    assert "3" in (parts["reason"] or "") and "2" in (parts["reason"] or ""), (
        f"어긋난 길이(3, 2)가 사유에 없다: {parts['reason']!r}"
    )
    assert (parts["action"] or "").strip()


@pytest.mark.req("FR-802-AC3")
def test_dv9_stays_catchable_as_valueerror() -> None:
    """기존 `except ValueError` 호출부가 그대로 잡아야 한다."""
    with pytest.raises(ValueError, match="길이"):
        CaseGrid(
            variables=(
                CaseVariable("pv_cost", ("low", "base", "high")),
                CaseVariable("ess_cost", ("low", "base")),
            ),
            coupled_sets=(CoupledSet("bad_cost_bundle", ("pv_cost", "ess_cost")),),
        )


def _many_cases(count: int) -> tuple[Case, ...]:
    return tuple(Case(index=i, values={"x": i}) for i in range(count))


@pytest.mark.req("FR-801-AC4")
@pytest.mark.req("NFR-303-M1")
def test_dv10_rejects_over_threshold_execution_without_confirmation_before_running() -> None:
    """FR-801-AC4 oracle: 501건(임계치 500 초과, 손으로 고른 최소 초과값) 은
    확인 없이는 **러너를 한 번도 부르지 않고** 거부해야 한다.

    `calls == []` 이 요점이다 — 이것이 없으면 「예외는 나지만 이미 다 돌린
    뒤」도 통과한다.
    """
    cases = _many_cases(DEFAULT_CONFIRMATION_THRESHOLD + 1)
    calls: list[int] = []

    def runner(case: Case) -> dict[str, float]:
        calls.append(case.index)
        return {"npv": 0.0}

    with pytest.raises(ValidationError) as caught:
        run_cases(cases, runner)

    assert calls == [], "확인 없이 케이스를 실행했습니다"
    parts = caught.value.as_dict()
    assert parts["rule"] == "DV-10"
    assert parts["field"] == "casegrid.case_count"
    assert str(DEFAULT_CONFIRMATION_THRESHOLD) in (parts["reason"] or "")
    assert str(len(cases)) in (parts["reason"] or "")
    assert (parts["action"] or "").strip()


@pytest.mark.req("FR-801-AC4")
def test_dv10_runs_when_confirmed_is_true() -> None:
    """`confirmed=True` 를 넘기면 실제로 돈다 — 거부만 검사하면
    `confirmed=True` 를 무시하고 항상 거부해도 초록불이므로 함께 확인한다.
    """
    cases = _many_cases(DEFAULT_CONFIRMATION_THRESHOLD + 1)
    calls: list[int] = []

    def runner(case: Case) -> dict[str, float]:
        calls.append(case.index)
        return {"npv": 0.0}

    results = run_cases(cases, runner, confirmed=True)

    assert len(calls) == len(cases)
    assert len(results) == len(cases)


@pytest.mark.req("FR-801-AC4")
def test_dv10_does_not_require_confirmation_at_or_below_threshold() -> None:
    """임계치(500) 이하는 확인 없이도 그대로 돈다 — quick 프리셋(27건)과 동일 형태."""
    cases = _many_cases(DEFAULT_CONFIRMATION_THRESHOLD)
    calls: list[int] = []

    def runner(case: Case) -> dict[str, float]:
        calls.append(case.index)
        return {"npv": 0.0}

    results = run_cases(cases, runner)

    assert len(calls) == len(cases)
    assert len(results) == len(cases)
