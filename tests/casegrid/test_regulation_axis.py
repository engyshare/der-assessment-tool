"""제도 프로파일이 **실제로 그리드 축이 되는가** — `FR-504-AC8`.

조항: *「"현행 / 개정안 / 메가특구 준용" 등 **복수 프로파일을 케이스 그리드의
탐색 변수로 지정**하여 **한 번의 실행으로** 제도 시나리오를 비교할 수 있다」*

**두 층이고 층마다 따로 붙든다.**

    ① 축이 된다      — 케이스 수가 프로파일 수만큼 곱해지는가
    ② 한 번의 실행   — `generate()` **한 번**이 모든 프로파일 케이스를 내는가

> **왜 이 파일이 따로 있는가.** `tests/regulation/` 쪽 검사는 축의 **재료**
> (`ProfileCaseVariable` 의 이름·값)만 본다. 그것은 그리드를 거치지 않으므로
> **「축을 만들 수 있다」까지만** 붙들고 「축이 된다」는 붙들지 못한다.
> 실제로 R20 에 재료 타입이 그리드와 평행한 별개 타입이라 아무도 소비하지
> 않는 상태였고, 그때도 재료 쪽 검사는 초록불이었다.
"""

from __future__ import annotations

from datetime import date

import pytest

from core.casegrid.grid import CaseGrid
from core.casegrid.models import CaseVariable
from core.casegrid.regulation_axis import PROFILE_TARGET, profile_axis
from core.contracts.regulation import RegulationItem
from core.regulation.profile import DataRegulationProfile, profile_case_variable


def _profile(name: str, version: str, ratio: float) -> DataRegulationProfile:
    return DataRegulationProfile(
        name=name,
        version=version,
        entries=(
            RegulationItem(
                key="supply_duty.required_ratio",
                value=ratio,
                unit=None,
                source="테스트 고시",
                valid_from=date(2026, 1, 1),
            ),
        ),
    )


#: 조항이 예로 드는 셋 — 현행 / 개정안 / 메가특구 준용.
_PROFILES = (
    _profile("current", "2026", 0.70),
    _profile("reform", "2027", 0.75),
    _profile("mega", "2027", 0.60),
)


@pytest.mark.req("FR-504-AC8")
def test_profile_axis_is_a_case_grid_variable() -> None:
    """① 제도 프로파일이 그리드가 **소비하는 타입**으로 온다.

    `CaseVariable` 이 아니면 `CaseGrid` 생성자에 넣을 수 없고, 넣을 수
    없으면 탐색 변수로 「지정」이 성립하지 않는다.
    """
    axis = profile_axis(profile_case_variable("regulation_profile", _PROFILES))

    assert isinstance(axis, CaseVariable)
    assert axis.name == "regulation_profile"
    assert axis.values == (("current", "2026"), ("reform", "2027"), ("mega", "2027"))
    assert axis.target == PROFILE_TARGET, (
        "축 종류가 기본값 'scalar' 로 남으면 소비 쪽이 (이름, 버전) 튜플을 "
        "스칼라로 읽습니다"
    )


@pytest.mark.req("FR-504-AC8")
def test_same_profile_name_with_different_versions_stays_two_cases() -> None:
    """개정판을 이름으로 뭉개지 않는다.

    제도 비교는 «현행 70% ↔ 개정안 75%» 처럼 **같은 제도의 다른 판**을 가르는
    일이다. 값에 이름만 실으면 두 판이 한 값이 되어 비교가 사라진다.
    """
    same_name = (_profile("supply_duty", "2026", 0.70), _profile("supply_duty", "2027", 0.75))
    axis = profile_axis(profile_case_variable("regulation_profile", same_name))

    assert len(set(axis.values)) == 2, f"두 개정판이 한 값으로 뭉개졌습니다: {axis.values}"


@pytest.mark.req("FR-504-AC8")
def test_one_generate_call_produces_every_profile_case() -> None:
    """② **한 번의 실행**으로 세 제도 × 두 할인율 = 여섯 케이스가 나온다.

    손 계산: 프로파일 3종 × 할인율 2종 = 6. 곱집합이므로 축을 더할 때마다
    곱해진다 — 이것이 「한 번의 실행으로 비교」의 기계적 내용이다.

    **`generate()` 를 한 번만 부른다.** 프로파일마다 그리드를 따로 만들어
    돌리면 조항이 말하는 「한 번의 실행」이 아니라 세 번의 실행이다.
    """
    axis = profile_axis(profile_case_variable("regulation_profile", _PROFILES))
    discount = CaseVariable(name="discount_rate", values=(0.045, 0.055))
    grid = CaseGrid((axis, discount))

    assert grid.case_count() == 6

    cases = grid.generate()
    assert len(cases) == 6

    seen_profiles = {case.values["regulation_profile"] for case in cases}
    assert seen_profiles == {("current", "2026"), ("reform", "2027"), ("mega", "2027")}, (
        "한 번의 generate() 가 세 제도를 모두 내지 못했습니다"
    )

    # 각 제도가 할인율 둘과 **짝지어져** 나온다 — 제도만 바뀌고 나머지가
    # 고정되면 비교가 아니라 나열이다.
    for profile in seen_profiles:
        rates = {
            case.values["discount_rate"]
            for case in cases
            if case.values["regulation_profile"] == profile
        }
        assert rates == {0.045, 0.055}, f"{profile} 이 할인율 두 값과 짝지어지지 않았습니다"
