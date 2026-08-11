"""FR-905-AC5 — 시계열 데이터셋의 탐색 변수화.

케이스 그리드(FR-801)가 "여러 연도·지역 시계열을 한 번에 비교"하려면
데이터셋 목록에 **균일한 접근 이름**이 있어야 한다 — FR-105-AC5 가 자원의
운전 방법 목록(``OPERATING_MODES``)에 요구한 것과 같은 형태를 시계열에도
준다. 이 모듈은 그 목록 자료구조만 정의한다 — 실제 케이스 실행·비교표
생성은 케이스 그리드 구획(``core/casegrid/``) 의 몫이며, 여기서는 그
구획을 import 하지 않는다(구획 격리).
"""

from __future__ import annotations

from dataclasses import dataclass

from core.assumption.timeseries import TimeSeriesDataset


@dataclass(frozen=True)
class TimeSeriesExploreAxis:
    """같은 목적(예: 부하 시계열)의 데이터셋 여러 개를 탐색 변수 하나로 묶는다.

    ``datasets`` 의 각 항목은 보통 연도·지역만 다른 변형이다. 축 전체가
    하나의 ``tag`` 를 가지므로 케이스 그리드는 이 축을 순회하는 것만으로
    "여러 연도·지역 시계열을 한 번에 비교"할 수 있다.
    """

    tag: str
    datasets: tuple[TimeSeriesDataset, ...]

    def __post_init__(self) -> None:
        if not self.datasets:
            raise ValueError(f"탐색 변수 `{self.tag}` 에 데이터셋이 하나도 없습니다")
        ids = [ds.id for ds in self.datasets]
        if len(ids) != len(set(ids)):
            raise ValueError(f"탐색 변수 `{self.tag}` 의 데이터셋 id 가 중복됩니다: {ids}")

    def dataset_ids(self) -> tuple[str, ...]:
        """축을 이루는 데이터셋 id — 케이스 그리드가 순회하는 값 목록."""
        return tuple(ds.id for ds in self.datasets)

    def select(self, dataset_id: str) -> TimeSeriesDataset:
        """id 로 축 안의 데이터셋 하나를 고른다."""
        for ds in self.datasets:
            if ds.id == dataset_id:
                return ds
        raise KeyError(f"탐색 변수 `{self.tag}` 에 데이터셋 `{dataset_id}` 가 없습니다")
