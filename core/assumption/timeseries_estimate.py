"""FR-905-AC4 — 8760 실측 시계열이 없을 때의 대체 입력.

월사용량(12개월 총량)과 하루 단위 표준 프로파일(24시간 가중치)을 결합해
8760 시간 시계열을 추정한다. 표준 프로파일에 평평한(균등) 가중치를 주면
그대로 **이용률 기반 추정**(하루 안에서 등속 소비)이 된다 — 두 대체입력
경로("표준 프로파일" / "이용률")를 한 함수로 만족시킨다. 난방도일 기반
추정은 이번 라운드 범위 밖이며, 표준 프로파일 대체입력으로 이미
"실측 시계열 없이도 대체 입력 가능"(AC4 핵심)이 성립한다.

추정 결과는 ``is_estimated=True`` 를 달아 나온다 — 나중에
``TimeSeriesBinding.swap()`` 으로 실측 시계열로 교체하는 것은 기존
경로 그대로다(교체 자체는 추정 여부를 가리지 않는다).
"""

from __future__ import annotations

from collections.abc import Sequence

from core.assumption.timeseries import TimeSeriesDataset

MONTHS_PER_YEAR = 12
HOURS_PER_DAY = 24

#: 비윤년 기준 월별 일수. 대체 입력은 실측이 아니라 근사이므로 윤년 보정을
#: 별도로 두지 않는다 — 이 근사 자체가 AC4 가 허용하는 "표준 프로파일"의
#: 성격이다.
DAYS_PER_MONTH: tuple[int, ...] = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

HOURS_PER_YEAR = sum(d * HOURS_PER_DAY for d in DAYS_PER_MONTH)


def estimate_from_monthly_usage(
    dataset_id: str,
    name: str,
    monthly_usage: Sequence[float],
    daily_profile_weights: Sequence[float],
) -> TimeSeriesDataset:
    """월사용량 + 표준(일간) 프로파일로 8760 시계열을 대체 입력한다.

    ``daily_profile_weights`` 는 24개 가중치이며 합이 1.0 이어야 한다 —
    그 날의 몫을 24시간에 나누는 형상이다. 균등 가중치([1/24]*24)를 주면
    "이용률 기반"(하루 등속) 추정과 동일해진다.
    """
    if len(monthly_usage) != MONTHS_PER_YEAR:
        raise ValueError(
            f"월사용량은 12개월분이어야 합니다: {len(monthly_usage)}개 주어짐"
        )
    if len(daily_profile_weights) != HOURS_PER_DAY:
        raise ValueError(
            f"일간 프로파일은 24시간분이어야 합니다: {len(daily_profile_weights)}개 주어짐"
        )
    weight_total = sum(daily_profile_weights)
    if abs(weight_total - 1.0) > 1e-9:
        raise ValueError(f"일간 프로파일 가중치 합이 1.0 이 아닙니다: {weight_total}")

    hourly: list[float] = []
    for month_usage, days in zip(monthly_usage, DAYS_PER_MONTH, strict=True):
        daily_usage = month_usage / days
        for _day in range(days):
            hourly.extend(daily_usage * w for w in daily_profile_weights)

    return TimeSeriesDataset(
        id=dataset_id,
        name=name,
        data=hourly,
        is_estimated=True,
    )
