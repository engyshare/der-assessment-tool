"""FR-905-AC6 — CSV 업로드 시계열의 스키마·행수·결측·이상치 검증과 요약 통계.

``validate_csv_upload``(NFR-404-AC1, ``timeseries.py``) 는 MIME·용량·줄수
상한만 본다 — 파일이 "받아들일 만한 크기인가"만 답하고, "내용이 시계열로
쓸 만한가"는 답하지 않는다. 이 모듈이 그 다음 단계다: 열 구성과 행수가
기대와 맞는지, 결측·이상치가 얼마나 있는지 세고, **결측을 처리하는 방식을
호출자가 고른다**(AC6 후단 — 선형보간 / 전월 평균 / 오류).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

#: 시계열 CSV 가 가져야 하는 열 구성. 늘리거나 순서를 바꾸면 다른 스키마다.
EXPECTED_COLUMNS: tuple[str, ...] = ("timestamp", "value")

MissingPolicy = Literal["interpolate", "prior_month_mean", "error"]


class TimeSeriesSchemaError(ValueError):
    """열 구성 또는 행수가 기대와 다르다."""


class TimeSeriesMissingValueError(ValueError):
    """결측 처리 방식이 ``error`` 인데 결측값이 있다."""


@dataclass(frozen=True)
class TimeSeriesValidationSummary:
    """검증 후 표시할 요약 통계 (AC6 "검증 후 요약 통계 표시")."""

    row_count: int
    missing_count: int
    outlier_count: int
    mean: float
    minimum: float
    maximum: float


def _linear_interpolate(values: list[float | None], index: int) -> float:
    """``index`` 위치의 결측을 좌우 최근접 실값으로 선형보간한다.

    한쪽 끝에 실값이 없으면(선행·후행 전체 결측) 반대쪽 최근접 값을
    그대로 쓴다 — 등속 추정의 경계 처리다.
    """
    left_i: int | None = None
    left_v = 0.0
    for i in range(index - 1, -1, -1):
        v = values[i]
        if v is not None:
            left_i, left_v = i, v
            break

    right_i: int | None = None
    right_v = 0.0
    for i in range(index + 1, len(values)):
        v = values[i]
        if v is not None:
            right_i, right_v = i, v
            break

    if left_i is None and right_i is None:
        raise TimeSeriesMissingValueError(
            "전 구간이 결측이라 선형보간할 실값이 없습니다"
        )
    if left_i is None:
        return right_v
    if right_i is None:
        return left_v

    ratio = (index - left_i) / (right_i - left_i)
    return left_v + (right_v - left_v) * ratio


def _apply_missing_policy(
    values: Sequence[float | None],
    policy: MissingPolicy,
    *,
    window_size: int | None,
) -> list[float]:
    if policy == "error":
        missing_idx = [i for i, v in enumerate(values) if v is None]
        if missing_idx:
            raise TimeSeriesMissingValueError(
                f"결측값이 {len(missing_idx)}건 있습니다 (행: {missing_idx}). "
                "결측 처리 방식을 `error` 로 선택하면 결측이 있으면 멈춥니다 — "
                "다른 방식(interpolate/prior_month_mean)을 고르십시오."
            )
        return [float(v) for v in values]  # type: ignore[arg-type]

    filled: list[float | None] = list(values)

    if policy == "interpolate":
        for i, v in enumerate(filled):
            if v is None:
                filled[i] = _linear_interpolate(filled, i)
        return [float(v) for v in filled]  # type: ignore[arg-type]

    if policy == "prior_month_mean":
        if window_size is None or window_size <= 0:
            raise ValueError(
                "`prior_month_mean` 정책은 window_size(직전 구간 길이) 가 필요합니다"
            )
        for i, v in enumerate(filled):
            if v is None:
                start = max(0, i - window_size)
                window = [x for x in filled[start:i] if x is not None]
                filled[i] = sum(window) / len(window) if window else 0.0
        return [float(v) for v in filled]  # type: ignore[arg-type]

    raise ValueError(f"알 수 없는 결측 처리 방식: {policy}")


def validate_and_summarize(
    columns: Sequence[str],
    values: Sequence[float | None],
    *,
    expected_row_count: int,
    missing_policy: MissingPolicy,
    outlier_z_threshold: float,
    window_size: int | None = None,
) -> tuple[list[float], TimeSeriesValidationSummary]:
    """스키마·행수·결측·이상치를 검증하고 (채워진 값, 요약통계) 를 낸다."""
    if tuple(columns) != EXPECTED_COLUMNS:
        raise TimeSeriesSchemaError(
            f"열 구성이 다릅니다: {tuple(columns)} (기대: {EXPECTED_COLUMNS})"
        )
    if len(values) != expected_row_count:
        raise TimeSeriesSchemaError(
            f"행수가 다릅니다: {len(values)}행 (기대: {expected_row_count}행)"
        )

    missing_count = sum(1 for v in values if v is None)

    filled = _apply_missing_policy(values, missing_policy, window_size=window_size)

    n = len(filled)
    mean = sum(filled) / n
    variance = sum((x - mean) ** 2 for x in filled) / n
    stdev = variance ** 0.5

    if stdev == 0.0:
        outlier_count = 0
    else:
        outlier_count = sum(
            1 for x in filled if abs(x - mean) / stdev > outlier_z_threshold
        )

    summary = TimeSeriesValidationSummary(
        row_count=n,
        missing_count=missing_count,
        outlier_count=outlier_count,
        mean=mean,
        minimum=min(filled),
        maximum=max(filled),
    )
    return filled, summary
