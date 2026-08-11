"""시계열 데이터셋이 **실제로 그리드 축이 되는가** — `FR-905-AC5`.

조항: *「데이터셋 자체를 케이스 그리드의 탐색 변수로 지정하여 여러 연도·지역
시계열을 **한 번에** 비교할 수 있다」*

`tests/casegrid/test_regulation_axis.py` 와 **같은 형태의 두 번째 검사**다.
두 조항이 같은 말을 하고 같은 자리에서 끊겨 있었다 — 하위 구획이 축 재료를
만들었으나 그리드가 소비하는 타입으로 바뀌지 않았다.

두 층을 층마다 따로 붙든다.

    ① 축이 된다      — `CaseVariable` 로 와서 `CaseGrid` 에 들어가는가
    ② 한 번의 실행   — `generate()` **한 번**이 모든 데이터셋 케이스를 내는가
"""

from __future__ import annotations

import pytest

from core.assumption.timeseries import TimeSeriesDataset
from core.assumption.timeseries_explore import TimeSeriesExploreAxis
from core.casegrid.dataset_axis import DATASET_TARGET, dataset_axis
from core.casegrid.grid import CaseGrid
from core.casegrid.models import CaseVariable


def _dataset(dataset_id: str) -> TimeSeriesDataset:
    return TimeSeriesDataset(id=dataset_id, name=dataset_id, data=[1.0, 2.0, 3.0])


#: 조항이 예로 드는 「여러 연도·지역」.
_AXIS = TimeSeriesExploreAxis(
    tag="load_profile",
    datasets=(
        _dataset("load-2024-seoul"),
        _dataset("load-2025-seoul"),
        _dataset("load-2025-busan"),
    ),
)


@pytest.mark.req("FR-905-AC5")
def test_dataset_axis_is_a_case_grid_variable() -> None:
    """① 데이터셋 축이 그리드가 **소비하는 타입**으로 온다."""
    axis = dataset_axis(_AXIS)

    assert isinstance(axis, CaseVariable)
    assert axis.name == "load_profile"
    assert axis.values == ("load-2024-seoul", "load-2025-seoul", "load-2025-busan")
    assert axis.target == DATASET_TARGET, (
        "축 종류가 기본값 'scalar' 로 남으면 소비 쪽이 데이터셋 id 를 스칼라로 읽습니다"
    )


@pytest.mark.req("FR-905-AC5")
def test_axis_carries_ids_not_the_series_bodies() -> None:
    """값은 **id** 다 — 시계열 본문이 케이스마다 복사되면 안 된다.

    `Case.values` 는 실행 매니페스트로 그대로 흘러간다. 본문을 실으면 케이스
    수만큼 8760개 실수가 복제되고, 그것은 `FR-905-AC7`(중복 저장 금지)와
    정면으로 어긋난다.
    """
    axis = dataset_axis(_AXIS)

    assert all(isinstance(value, str) for value in axis.values), (
        f"축 값에 문자열 아닌 것이 있습니다 — 본문을 실었을 수 있습니다: {axis.values}"
    )


@pytest.mark.req("FR-905-AC5")
def test_one_generate_call_produces_every_dataset_case() -> None:
    """② **한 번의 실행**으로 세 데이터셋 × 두 할인율 = 여섯 케이스가 나온다.

    손 계산: 데이터셋 3종 × 할인율 2종 = 6. 곱집합이므로 축을 더할 때마다
    곱해진다 — 이것이 「한 번에 비교」의 기계적 내용이다.
    """
    discount = CaseVariable(name="discount_rate", values=(0.045, 0.055))
    grid = CaseGrid((dataset_axis(_AXIS), discount))

    assert grid.case_count() == 6

    cases = grid.generate()
    assert len(cases) == 6
    assert {case.values["load_profile"] for case in cases} == {
        "load-2024-seoul",
        "load-2025-seoul",
        "load-2025-busan",
    }, "한 번의 generate() 가 세 데이터셋을 모두 내지 못했습니다"
