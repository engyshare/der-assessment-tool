"""단위 규약과 Decimal/float 경계 — 작업 1.7 / spec §7.5 · NFR-103.

**이 모듈이 존재하는 이유는 반올림이 일어나는 곳을 한 군데로 묶기 위해서다.**

pandas/numpy는 Decimal을 실질적으로 지원하지 않는다. 그래서 계층을 나눈다
(NFR-103 경계 정의):

    시계열 계층   8760 디스패치·에너지 수지 → float64. 허용 오차 1e-6 kWh
    ─────────── to_won() ─────────────  ← **반올림은 여기서만 일어난다**
    재무 계층     프로포마·NPV·IRR      → Decimal 정수 원

경계가 여러 곳이면 같은 값이 경로에 따라 다르게 반올림되고, 20년 프로포마
합계와 항목별 합계가 어긋난다(NFR-103-M1). 그 어긋남은 **화면상 정상으로
보이므로 사후 발견이 어렵다** — 본 시스템의 산출물이 정책 판단 근거라는
점에서 이것이 가장 위험한 오류 유형이다.

§7.5 단위 규약
    전력 kW · 전력량 kWh · 열 kWth/kWh_th · 금액 원(KRW, 명목)
    비율은 **코드 내부에서 소수(0~1)로 정규화**한다. 화면·입력은 %(0~100).
    기간은 년(정수), 시간스텝은 초.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final

# ── 금액 ─────────────────────────────────────────────────────────────
#
# `Money` 는 Decimal 의 별칭이 아니라 하위 클래스다. 별칭으로 두면
# isinstance(x, Money) 가 아무 Decimal 이나 통과시켜, 반올림되지 않은 값이
# 재무 계층에 들어와도 계약 테스트가 잡지 못한다.


class Money(Decimal):
    """정수 원(KRW). 재무 계층의 유일한 금액 타입.

    **원 미만을 담을 수 있다는 점이 함정이다.** 타입이 막아 주지 않으므로
    계약 테스트(`test_money_methods_return_whole_won`)가 정수임을 강제한다.
    여기서 생성 시 강제하지 않는 이유는, 중간 계산(예: 20년 합계를 20으로
    나눈 평균)에서 소수가 정당하게 생기기 때문이다. 금지해야 하는 것은
    **경계를 넘는 값**이지 모든 Decimal 연산이 아니다.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - 표시용
        return f"Money({super().__str__()})"


ZERO: Final[Money] = Money(0)


def to_won(value: float | int | Decimal) -> Money:
    """시계열 계층 → 재무 계층. **반올림이 일어나는 유일한 지점.**

    사사오입(ROUND_HALF_UP), 원 단위. 은행가 반올림(ROUND_HALF_EVEN)을 쓰지
    않는 이유는 엑셀 대조(§13.3)와 어긋나기 때문이다 — 엑셀 ROUND()는
    사사오입이고, 대조군과 규칙이 다르면 0.01% 오차 기준을 만족해도
    개별 셀이 1원씩 어긋나 원인 추적이 불가능해진다.

    float 를 Decimal 로 바꿀 때 `str()` 을 경유한다. Decimal(0.1) 은
    0.1000000000000000055511151231257827021181583404541015625 이므로
    직접 넘기면 경계에서 미세 오차가 재무 계층으로 새어 든다.
    """
    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, bool):
        # bool 은 int 의 하위 클래스라 조용히 0/1 원이 된다. 금액 자리에
        # 플래그가 들어온 것이므로 오류다.
        raise TypeError("bool 은 금액이 될 수 없습니다")
    else:
        try:
            d = Decimal(str(value))
        except InvalidOperation as e:  # NaN·inf
            raise ValueError(f"금액으로 변환할 수 없는 값입니다: {value!r}") from e

    if not d.is_finite():
        raise ValueError(f"금액이 유한하지 않습니다: {value!r}")

    return Money(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def won_sum(values: Iterable[float | int | Decimal]) -> Money:
    """원 단위 합계. **각 항을 반올림한 뒤 더한다.**

    합계를 먼저 내고 마지막에 반올림하면 항목별 합계와 총계가 어긋난다 —
    NFR-103-M1 이 검증하는 바로 그 불일치다. 프로포마는 행별 값을 사람이
    보고 더해 보는 문서이므로, 눈으로 더한 값과 총계가 같아야 한다.
    """
    total = Decimal(0)
    for v in values:
        total += to_won(v)
    return Money(total)


# ── 비율 ─────────────────────────────────────────────────────────────

def pct_to_fraction(percent: float) -> float:
    """%(0~100) → 소수(0~1). 입력 경계에서만 쓴다 (§7.5).

    범위를 검사하는 이유: 3%를 `0.03` 으로 이미 정규화해 둔 값을 다시
    통과시키면 0.0003 이 되고, 20년 뒤 결과는 그럴듯하지만 틀린다.
    """
    if not 0.0 <= percent <= 100.0:
        raise ValueError(
            f"비율은 0~100 %(퍼센트)로 입력합니다: {percent}. "
            "코드 내부 값(0~1 소수)을 다시 넘기고 있지 않은지 확인하십시오"
        )
    return percent / 100.0


def fraction_to_pct(fraction: float) -> float:
    """소수(0~1) → %(0~100). 표시 경계에서만 쓴다."""
    if not 0.0 <= fraction <= 1.0:
        raise ValueError(f"내부 비율은 0~1 소수입니다: {fraction}")
    return fraction * 100.0


# ── 기간·시간 인덱스 ─────────────────────────────────────────────────

HOURS_PER_YEAR: Final[int] = 8760
STEPS_15MIN_PER_YEAR: Final[int] = 35_040
SECONDS_PER_HOUR: Final[int] = 3600


class Year(int):
    """분석 연도. **1-base다** (건설 후 첫 해가 1년차).

    0-base와 섞이면 20년 분석이 19년이 되거나 잔존가치가 한 해 밀린다.
    두 오류 모두 결과가 그럴듯해서 눈으로는 잡히지 않으므로 타입으로 막는다.
    """

    __slots__ = ()

    def __new__(cls, value: int) -> Year:
        v = int(value)
        if v < 1:
            raise ValueError(
                f"분석 연도는 1부터 셉니다 (받은 값 {v}). "
                "0-base 인덱스를 그대로 넘기고 있지 않은지 확인하십시오"
            )
        return super().__new__(cls, v)


def steps_per_year(dt_seconds: int) -> int:
    """시간스텝(초) → 연간 스텝 수.

    8760·35040 만 허용한다. 임의 해상도를 허용하면 시계열 CSV의 행수가
    맞지 않을 때 "그런 해상도인가 보다" 로 통과해 버린다 (FR-301-AC3).
    """
    if dt_seconds == SECONDS_PER_HOUR:
        return HOURS_PER_YEAR
    if dt_seconds == SECONDS_PER_HOUR // 4:
        return STEPS_15MIN_PER_YEAR
    raise ValueError(
        f"지원하지 않는 시간 해상도입니다: {dt_seconds}초. "
        f"{SECONDS_PER_HOUR}(1시간) 또는 {SECONDS_PER_HOUR // 4}(15분)만 씁니다 "
        "(spec §7.5 · FR-301)"
    )


# ── 에너지 허용 오차 ─────────────────────────────────────────────────
#
# NFR-102: 에너지 수지 균형 오차는 모든 시간스텝에서 1e-6 kWh 미만.
ENERGY_TOLERANCE_KWH: Final[float] = 1e-6
