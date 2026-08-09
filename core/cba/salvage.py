"""잔존가치 — 작업 10.8.

잔존 수명 비례. **명목액**이다 — ``salvage_value`` 가 할인율 인자를 받지 않는
것이 계약이며, **할인은 CBA 가 최종연도에 한다** (NPV 산출 시 해당 연도의
현금흐름으로 들어가 (1+r)^year 로 나눠진다).

분석 종료 시점에 자원이 남은 수명이 있으면, 그 잔존 가치를 «잔존 수명 비례» 로
추정한다. 선형 감가상각 가정. 100% 잔존도 가능(분석 종료 직전 교체 등).
"""
from __future__ import annotations

from core.contracts.units import Money, to_won


def salvage_value(
    capex_won: int,
    asset_lifetime_years: int,
    elapsed_years_at_analysis_end: int,
) -> Money:
    """잔존가치 — 잔존 수명 비례, 명목액 (10.8).

    ``elapsed_years_at_analysis_end`` 는 분석 종료 연도 기준으로 자원이 이미
    사용된 년 수. 교체 시점이면 elapsed 가 0에 가깝게 리셋된다(교체 직후 자원은
    새 것).

    잔존 수명 비례:
        remaining = lifetime - elapsed
        salvage = capex × max(0, remaining) / lifetime

    **음수가 될 수 없다.** remaining < 0 이면 0 — 수명 종료 자원의 잔존가치는 0.
    """
    if asset_lifetime_years <= 0:
        raise ValueError(
            f"자산 수명은 양수여야 합니다: {asset_lifetime_years}. "
            "잔존 수명 비례 산출이 정의되지 않는다"
        )
    remaining = asset_lifetime_years - elapsed_years_at_analysis_end
    if remaining <= 0:
        # 수명 종료 — 잔존가치 0 (FR-701-AC4 와 일관)
        return to_won(0)
    # elapsed 가 음수(미래 교체 예정 자원)이면 100% 잔존
    fraction = min(1.0, remaining / asset_lifetime_years)
    salvage_float = capex_won * fraction
    return to_won(salvage_float)


def salvage_as_final_year_flow(
    capex_won: int,
    asset_lifetime_years: int,
    elapsed_years_at_analysis_end: int,
) -> Money:
    """최종연도 계상용 잔존가치 — ``salvage_value`` 의 별칭.

    **계상 후 할인** — 이 값은 최종연도(year=N)의 현금흐름으로 들어가,
    NPV 산출 시 (1+r)^N 으로 나눠진다. ``salvage_value`` 자체는 명목액.
    """
    return salvage_value(
        capex_won, asset_lifetime_years, elapsed_years_at_analysis_end
    )
