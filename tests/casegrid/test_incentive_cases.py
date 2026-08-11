"""`FR-607-AC1` — 등록된 변형 목록이 곧 실행 목록이다.

**이 파일이 `tests/incentive/` 가 아니라 여기 있는 이유는 검사 대상이 위층에
있기 때문이다.** R21 에 `core/incentive/calculator.py` 가
`core.casegrid.variants.run_order()` 를 직접 import 하자 `lint-imports` 가
`NFR-208-AC1`(역방향 import 금지) 위반으로 빨간불을 냈다 — `core.casegrid` 가
`core.incentive` 위 계층이다. 합성을 위층
(`core/casegrid/incentive_cases.py`)으로 옮겨 풀었고, 검사도 함께 왔다.

네 테스트가 **두 층을 따로** 붙든다:

    ① 자동 포함  호출자가 「기준선」이라는 말을 하지 않아도 결과에 들어온다
    ② 상단 표시  그 케이스가 목록 **맨 앞**이고, 태그만이 아니라 **값도** 기준선이다

②를 따로 두는 이유: 맨 앞 원소가 기준선 태그를 달고 있으면서 지원이 적용된
현금흐름을 나르면 「상단 표시」는 이름만 지킨 것이다. 한 층만 검사하면 그
상태가 초록불이다.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.casegrid import incentive_cases
from core.casegrid.incentive_cases import build_capex_cashflows_for_all_cases
from core.contracts.units import Money
from core.incentive.schemas import IncentiveScheme


def _scheme(**kwargs: Any) -> IncentiveScheme:
    """검사용 스킴 — 지정하지 않은 칸은 「효과 없음」으로 둔다."""
    defaults: dict[str, Any] = {
        "subsidy_rate": 0.0,
        "subsidy_fixed": None,
        "subsidy_limit": None,
        "loan_rate": 0.0,
        "loan_interest": 0.0,
        "loan_grace_years": 0,
        "loan_repayment_years": 0,
        "loan_repayment_type": "원리금균등",
        "tax_credit_rate": 0.0,
        "sponsor": "국비",
        "funding_program": None,
        "is_prefunded": False,
        "prefunded_status": None,
    }
    defaults.update(kwargs)
    return IncentiveScheme(**defaults)


@pytest.mark.req("FR-607-AC1")
def test_all_cases_includes_baseline_without_being_asked() -> None:
    """호출자가 «기준선도 계산해 달라»를 요청하지 않아도 포함된다.

    손계산 오라클:
    - 입력 스킴(보조율 40%) 그대로의 사업자 CAPEX = **-600원**
      (1,000원 × (1 − 0.4))
    - 기준선(무지원) 사업자 CAPEX = **-1,000원** (지원 0)

    호출자는 스킴 하나만 넘겼을 뿐 「기준선」이라는 말을 한 적이 없다 —
    그런데도 결과에 나온다면 그것이 「자동 포함」이다.
    """
    cases = build_capex_cashflows_for_all_cases(_scheme(subsidy_rate=0.4), 1000, "OWNER")

    tags = [c.tag for c in cases]
    assert "unsupported" in tags, "호출자가 요청하지 않았는데도 기준선이 빠졌다"

    baseline_case = next(c for c in cases if c.tag == "unsupported")
    assert baseline_case.rows[0].amounts[1] == Money(-1000)

    planned_case = next(c for c in cases if c.tag == "as_planned")
    assert planned_case.rows[0].amounts[1] == Money(-600)


@pytest.mark.req("FR-607-AC1")
def test_all_cases_puts_baseline_first_by_value_not_only_by_tag() -> None:
    """「결과 상단에 표시」— 기준선이 반환 목록의 **맨 앞**이다.

    `run_order()` 가 순서를 보증하는 것과 이 함수의 **반환값이 그 순서를
    실제로 지키는 것**은 별개 층이다. 이 테스트는 후자를 본다.
    """
    cases = build_capex_cashflows_for_all_cases(_scheme(subsidy_rate=0.4), 1000, "OWNER")

    assert cases[0].tag == "unsupported"
    assert cases[0].rows[0].amounts[1] == Money(-1000), (
        "맨 앞 원소가 기준선 태그를 달고 있어도 실제로 무지원 현금흐름이 "
        "아니면 「상단 표시」가 이름만 지킨 것이다"
    )


@pytest.mark.req("FR-607-AC1")
def test_all_cases_refuses_when_baseline_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ 일부러 망가뜨려 확인 — 변형 목록에서 기준선을 빼면 빨간불이다.

    `run_order` 를 몽키패치해 기준선이 하나도 없는 목록으로 바꾼다 (실제
    `core/casegrid/variants/` 파일은 건드리지 않는다). 「자동 포함」의 핵심은
    **빠뜨릴 수 없다**이므로, 빠뜨렸는데 초록불이면 이 함수는 여전히 깃발과
    같은 것이다.
    """

    class _NoBaseline:
        tag = "only_variant"
        label = "기준선 아님"
        baseline = False

    monkeypatch.setattr(incentive_cases, "run_order", lambda: (_NoBaseline,))

    with pytest.raises(ValueError, match="기준선"):
        build_capex_cashflows_for_all_cases(_scheme(subsidy_rate=0.4), 1000, "OWNER")


@pytest.mark.req("FR-607-AC1")
def test_all_cases_refuses_when_baseline_is_not_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ 일부러 망가뜨려 확인 — 기준선이 맨 위가 아니면 빨간불이다.

    기준선은 목록에 **있지만** 두 번째 자리다. 「자동 포함」은 됐어도
    「상단 표시」가 깨진 경우이므로 이 역시 잡혀야 한다.
    """

    class _NotFirst:
        tag = "as_planned_like"
        label = "지원안"
        baseline = False

    class _BaselineSecond:
        tag = "unsupported"
        label = "무지원 기준선"
        baseline = True

    monkeypatch.setattr(
        incentive_cases, "run_order", lambda: (_NotFirst, _BaselineSecond)
    )

    with pytest.raises(ValueError, match="맨 위"):
        build_capex_cashflows_for_all_cases(_scheme(subsidy_rate=0.4), 1000, "OWNER")
