"""관점별 CAPEX 행 빌더 — 부호 규약과 4×4 문면·금액 고정.

## 왜 이 파일이 따로 있는가

`core/incentive/calculator.py` 의 네 자리가 `CashFlowRow` 를 **빌더 밖에서
직접** 짓고 있었고, 그 넷을 `capex_viewpoint_row()` 로 모았다. 그 이동에서
가장 위험한 것은 **부호**다 — 넷은 관점별 현금흐름(유출)이라 **음수**인데,
같은 자료형을 짓는 `core/cba/proforma.py::capex_row` 는 *「비용은 양수」* 라는
**반대 규약**이다. 그 규약을 끌어다 쓰면 초기투자비가 유입이 되고,
`core/cba/proforma.py::salvage_row` 가 적어 둔 대로 **아무 예외도 나지 않는다.**

그래서 이 파일은 두 가지를 붙든다.

1. **빌더가 부호를 뒤집지 않는다** — 넘긴 값 그대로 싣고, 양수는 거부한다.
2. **스킴 4종 × 관점 4종의 라벨·태그·1년차 금액 전건**을 아래 표에 **밖에서
   고정**한다. 표의 값은 빌더를 세우기 **전** 커밋에서 뜬 스냅숏이다 —
   검사가 오라클을 스스로 계산하면 리팩터가 무엇을 바꿨든 늘 초록불이 된다.

⚠ 표의 문면(`label`·`tag`)은 리포트가 그대로 읽는 문자열이다. 여기서
초록불을 얻으려고 표를 고치는 것은 **리포트 문면을 고치는 것**이다.
"""
from decimal import Decimal
from typing import Any

import pytest

from core.contracts.validation import ValidationError
from core.incentive.calculator import build_capex_cashflows, capex_viewpoint_row
from core.incentive.schemas import IncentiveScheme

CAPEX = 100_000_000


def _scheme(**kwargs: Any) -> IncentiveScheme:
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


def _schemes() -> dict[str, IncentiveScheme]:
    return {
        "baseline": IncentiveScheme.create_baseline(),
        "rate_subsidy_loan": _scheme(
            subsidy_rate=0.5,
            loan_rate=0.3,
            loan_interest=0.02,
            loan_grace_years=1,
            loan_repayment_years=5,
        ),
        "fixed_subsidy": _scheme(subsidy_fixed=Decimal(30_000_000), sponsor="지방비"),
        "prefunded_confirmed": _scheme(
            funding_program="타 사업 A",
            is_prefunded=True,
            prefunded_status="확정 지원",
        ),
    }


#: `(스킴, 관점) → (label, tag, 1년차 금액)`. **밖에서 고정한 값**이다 —
#: 빌더 도입 전 커밋의 `build_capex_cashflows()` 출력 스냅숏이며, 총사업비는
#: 위 `CAPEX`(1억원). 음수는 유출이고 `0` 은 「행은 있는데 지출이 없다」이다
#: (`FR-611-AC2`: 행까지 없애면 리포트에서 설비가 통째로 사라진다).
EXPECTED: dict[tuple[str, str], tuple[str, str, str]] = {
    ("baseline", "OWNER"): ("초기투자비(자부담)", "capex.equity", "-100000000"),
    ("baseline", "PARTICIPANT"): ("초기투자비(자부담)", "capex.equity", "-100000000"),
    ("baseline", "GOV"): ("본 사업 정부 지원(보조금)", "capex.gov_subsidy", "0"),
    ("baseline", "SOCIAL"): ("취득원가(사회 전체 비용)", "capex.social_cost", "-100000000"),
    ("rate_subsidy_loan", "OWNER"): ("초기투자비(자부담)", "capex.equity", "-20000000"),
    ("rate_subsidy_loan", "PARTICIPANT"): ("초기투자비(자부담)", "capex.equity", "-20000000"),
    ("rate_subsidy_loan", "GOV"): (
        "본 사업 정부 지원(보조금)", "capex.gov_subsidy", "-50000000",
    ),
    ("rate_subsidy_loan", "SOCIAL"): (
        "취득원가(사회 전체 비용)", "capex.social_cost", "-100000000",
    ),
    ("fixed_subsidy", "OWNER"): ("초기투자비(자부담)", "capex.equity", "-70000000"),
    ("fixed_subsidy", "PARTICIPANT"): ("초기투자비(자부담)", "capex.equity", "-70000000"),
    ("fixed_subsidy", "GOV"): ("본 사업 정부 지원(보조금)", "capex.gov_subsidy", "-30000000"),
    ("fixed_subsidy", "SOCIAL"): (
        "취득원가(사회 전체 비용)", "capex.social_cost", "-100000000",
    ),
    ("prefunded_confirmed", "OWNER"): ("초기투자비(자부담)", "capex.equity", "0"),
    ("prefunded_confirmed", "PARTICIPANT"): ("초기투자비(자부담)", "capex.equity", "0"),
    ("prefunded_confirmed", "GOV"): (
        "타 사업 기지원 (타 사업 A)", "capex.prefunded_subsidy", "-100000000",
    ),
    ("prefunded_confirmed", "SOCIAL"): (
        "취득원가(사회 전체 비용)", "capex.social_cost", "-100000000",
    ),
}


@pytest.mark.req("FR-611-AC1", "FR-611-AC2", "FR-611-AC3.OWNER", "FR-611-AC3.GOV",
                 "FR-611-AC3.SOCIAL")
def test_capex_cashflows_match_externally_fixed_table() -> None:
    """스킴 4종 × 관점 4종 **전건**이 표와 문면·태그·금액까지 같다.

    금액은 `str()` 로 비교한다 — `Decimal('-0')` 과 `Decimal('0')` 은 `==` 이지만
    프로포마에 실리는 문면이 다르다. 부호가 뒤집히면 이 단언이 **16건 중
    12건**에서 깨진다(나머지 넷은 0원 행이라 부호가 없다).
    """
    schemes = _schemes()
    assert set(EXPECTED) == {
        (s, v) for s in schemes for v in ("OWNER", "PARTICIPANT", "GOV", "SOCIAL")
    }

    for (scheme_name, viewpoint), (label, tag, amount) in sorted(EXPECTED.items()):
        rows = build_capex_cashflows(schemes[scheme_name], CAPEX, viewpoint)  # type: ignore[arg-type]
        assert len(rows) == 1, f"{scheme_name}/{viewpoint}: 행 개수가 1이 아니다"
        row = rows[0]
        assert row.label == label, f"{scheme_name}/{viewpoint}: 라벨 문면"
        assert row.tag == tag, f"{scheme_name}/{viewpoint}: 태그 문면"
        assert list(row.amounts) == [1], f"{scheme_name}/{viewpoint}: 1년차만 실린다"
        assert str(row.amounts[1]) == amount, f"{scheme_name}/{viewpoint}: 금액"


@pytest.mark.req("FR-611-AC3.OWNER")
def test_capex_viewpoint_row_does_not_flip_sign() -> None:
    """빌더는 **받은 부호를 그대로** 싣는다 — 뒤집는 자리는 호출자다.

    `core/cba/proforma.py::salvage_row` 와 정반대 규약이다. 여기서 한 번 더
    뒤집으면 호출자의 `-` 와 겹쳐 다시 양수가 되고, 유출이 유입이 된다.
    """
    row = capex_viewpoint_row(
        label="초기투자비(자부담)",
        tag="capex.equity",
        signed_amount_won=Decimal(-70_000_000),
    )
    assert row.amounts == {1: Decimal(-70_000_000)}
    assert row.label == "초기투자비(자부담)"
    assert row.tag == "capex.equity"


@pytest.mark.req("FR-611-AC2")
def test_capex_viewpoint_row_keeps_zero_row() -> None:
    """0원이어도 행을 만든다 — `FR-611-AC2` 의 「전액 계상」이 걸린 자리다."""
    row = capex_viewpoint_row(
        label="초기투자비(자부담)", tag="capex.equity", signed_amount_won=Decimal(0)
    )
    assert row.amounts == {1: Decimal(0)}


@pytest.mark.req("FR-611-AC3.OWNER")
def test_capex_viewpoint_row_rejects_positive_amount() -> None:
    """양수를 거부한다 — 「호출자가 뒤집었는가」를 문턱에서 잡는다.

    거부가 없으면 `-` 하나를 빠뜨린 호출이 **아무 예외 없이** 유출을 유입으로
    바꾸고, 그 관점의 결론이 그 금액의 두 배만큼 좋아진다.
    """
    with pytest.raises(ValidationError) as exc:
        capex_viewpoint_row(
            label="초기투자비(자부담)",
            tag="capex.equity",
            signed_amount_won=Decimal(70_000_000),
        )
    assert exc.value.field == "incentive.capex_viewpoint_row.signed_amount_won"
    assert "capex.equity" in exc.value.reason
    assert exc.value.action
