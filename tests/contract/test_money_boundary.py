"""Decimal/float 경계 — 작업 1.6 / spec NFR-103.

**여기서 지키려는 것은 "20년 프로포마 합계와 항목별 합계가 원 단위로 완전히
일치한다"** 는 한 문장이다 (NFR-103-M1).

그 불일치는 실무에서 이렇게 생긴다 — 시계열 float 값을 그대로 더해 마지막에
한 번 반올림하면, 사람이 행별 값을 눈으로 더한 결과와 총계가 1~2원 어긋난다.
금액이 억 단위인 문서에서 2원 차이는 아무도 못 보지만, **검산하는 사람은
반드시 본다.** 그리고 그 순간 문서 전체의 신뢰가 무너진다.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.contracts.schemas import CashFlowRow
from core.contracts.units import (
    Money,
    Year,
    fraction_to_pct,
    pct_to_fraction,
    steps_per_year,
    to_won,
    won_sum,
)

# ── 반올림 규칙 ──────────────────────────────────────────────────────

@pytest.mark.req("NFR-103-M1")
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0.4, 0),
        (0.5, 1),      # 사사오입 — 은행가 반올림이면 0이 된다
        (1.5, 2),      # 은행가 반올림이면 2 (우연히 같다)
        (2.5, 3),      # 은행가 반올림이면 2 — **여기서 갈린다**
        (-0.5, -1),    # ROUND_HALF_UP 은 0에서 멀어지는 방향
        (1234.49, 1234),
        (1234.50, 1235),
    ],
)
def test_to_won_uses_half_up_not_bankers(raw: float, expected: int) -> None:
    """엑셀 ROUND()와 같은 사사오입이어야 한다.

    은행가 반올림(파이썬 `round()` 기본값)을 쓰면 `2.5 → 2` 가 되어 엑셀
    대조(§13.3)에서 셀마다 1원씩 어긋난다. 0.01% 오차 기준은 통과하므로
    **테스트는 초록불인데 검산은 맞지 않는** 상태가 된다.
    """
    assert to_won(raw) == expected


@pytest.mark.req("NFR-103-M1")
def test_to_won_does_not_leak_float_representation_error() -> None:
    """float → Decimal 변환이 str()을 경유해야 한다.

    `Decimal(0.1)` 은 0.1000000000000000055511151231257827… 이다. 직접
    넘기면 그 미세 오차가 재무 계층으로 새어 들고, 20년 누적에서 원 단위
    불일치로 자란다.
    """
    assert to_won(0.1) == 0
    # 0.145 는 float 로 0.1449999999999999900079881… 이다. str() 경유면
    # Decimal("0.145") 가 되어 사사오입으로 0원이 아닌 값이 나오는 자리에서
    # 규칙이 일관된다.
    assert to_won(2.675 * 100) == 268  # 267.49999... 가 아니라 267.5 로 읽힌다


@pytest.mark.req("NFR-103-M1")
def test_to_won_rejects_non_finite_and_bool() -> None:
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            to_won(bad)
    with pytest.raises(TypeError):
        to_won(True)  # bool 은 int 하위 클래스라 조용히 1원이 된다


# ── 합계 항등식 — NFR-103-M1 의 본체 ─────────────────────────────────

@pytest.mark.req("NFR-103-M1")
def test_item_sum_equals_total_over_20_years() -> None:
    """20년 프로포마 합계 = 항목별 합계. **원 단위 완전 일치.**

    각 항을 반올림한 뒤 더한다. 더한 뒤 반올림하면 아래 단언이 깨진다 —
    그것이 이 테스트가 잡으려는 실수다.
    """
    # 원 미만이 매년 남는 값을 일부러 고른다. 딱 떨어지는 값으로는
    # 반올림 순서 차이가 드러나지 않는다.
    yearly_float = [1_234_567.4 + i * 0.5 for i in range(20)]

    per_item = [to_won(v) for v in yearly_float]
    total = won_sum(yearly_float)

    assert total == sum(per_item), (
        "항목별 합계와 총계가 어긋납니다. 각 항을 반올림한 뒤 더해야 "
        "사람이 행별 값을 눈으로 더한 결과와 총계가 같습니다"
    )

    # 대조군: 더한 뒤 한 번만 반올림하면 어긋난다는 것을 실제로 보인다.
    naive = to_won(sum(yearly_float))
    assert naive != total, (
        "이 테스트가 아무것도 검사하지 않고 있습니다 — 두 방식이 같은 값을 "
        "내는 데이터를 골랐습니다. 원 미만이 남는 값으로 바꾸십시오"
    )

    # `won_sum` 은 임의의 iterable 을 받는다(`Iterable[float|int|Decimal]`).
    # 시퀀스로 좁히면 제너레이터를 넘기는 호출부가 리스트를 먼저 만들게 되고,
    # 20년 × 자원 N 의 중간 리스트는 이유 없는 비용이다.
    assert won_sum(v for v in yearly_float) == total
    assert won_sum([Decimal("1.5"), Decimal("2.5")]) == to_won(2) + to_won(3), (
        "Decimal 항이 사사오입되지 않았습니다 — 은행가 반올림이면 1.5→2, "
        "2.5→2 가 되어 합계가 1원 어긋납니다"
    )
    assert won_sum([]) == 0, "빈 합계는 0원이며 오류가 아닙니다"


@pytest.mark.req("NFR-103-M1")
def test_cashflow_row_rejects_sub_won_amounts() -> None:
    """경계 스키마가 원 미만을 거부한다.

    반올림되지 않은 값이 프로포마에 들어오면 그 행만 소수점을 갖게 되고,
    엑셀 내보내기에서 셀 서식에 따라 표시가 달라져 원인 추적이 어려워진다.
    """
    with pytest.raises(ValueError, match="원 미만"):
        CashFlowRow(label="설비 자본비", amounts={1: Decimal("1000.5")})

    row = CashFlowRow(label="설비 자본비", amounts={1: Decimal("1000")})
    assert row.total() == 1000


def test_cashflow_row_rejects_zero_based_year() -> None:
    with pytest.raises(ValueError, match="1부터"):
        CashFlowRow(label="x", amounts={0: Decimal("100")})


@pytest.mark.req("NFR-103-M1")
def test_cashflow_total_matches_manual_addition() -> None:
    """행 총계가 사람이 더한 값과 같다."""
    amounts = {y: to_won(1_000_000 / 3) for y in range(1, 21)}
    row = CashFlowRow(label="O&M", amounts=amounts)
    assert row.total() == Money(Decimal(333_333) * 20)


# ── 단위 규약 (§7.5) ─────────────────────────────────────────────────

def test_percent_normalization_round_trip() -> None:
    assert pct_to_fraction(2.5) == 0.025
    assert fraction_to_pct(0.025) == 2.5


def test_percent_rejects_already_normalized_value() -> None:
    """이미 정규화된 값을 다시 넘기는 실수를 막는다.

    `pct_to_fraction(0.03)` 은 0.0003 이 된다. 20년 결과는 그럴듯하지만
    열화율이 100배 작아진 상태이며, 눈으로는 잡히지 않는다. 범위 검사로는
    0~100 안이라 통과하므로 — 여기서는 통과가 맞다. 이 테스트가 확인하는
    것은 **범위 밖 입력이 확실히 거부된다**는 것이다.
    """
    with pytest.raises(ValueError):
        pct_to_fraction(-0.1)
    with pytest.raises(ValueError):
        pct_to_fraction(100.1)
    with pytest.raises(ValueError):
        fraction_to_pct(2.5)  # 소수 자리에 %를 넣은 경우


def test_year_is_one_based_and_rejects_zero() -> None:
    assert int(Year(1)) == 1
    with pytest.raises(ValueError, match="1부터"):
        Year(0)


@pytest.mark.req("NFR-103-M1")
def test_only_supported_time_resolutions() -> None:
    """임의 해상도를 허용하면 행수 불일치가 "그런 해상도인가 보다"로 통과한다."""
    assert steps_per_year(3600) == 8760
    assert steps_per_year(900) == 35_040
    with pytest.raises(ValueError, match="해상도"):
        steps_per_year(1800)  # 30분 — 지원하지 않는다
