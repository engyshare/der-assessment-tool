"""FR-905-AC7 — 시계열 데이터셋의 공유 참조와 중복 저장 방지.

동일 데이터셋을 여러 시나리오·인스턴스가 참조해야 하며, 참조가 늘어도
데이터셋 자체는 한 번만 저장된다. 삭제는 참조가 남아 있는 동안 거부되고,
**누가 참조 중인지**를 먼저 알려야 한다 — 조용히 지우면 참조 중인
시나리오가 다음 실행에서야 깨진 참조를 만나 원인을 알 수 없다.
"""

from __future__ import annotations

from core.assumption.timeseries import TimeSeriesDataset


class DatasetInUseError(ValueError):
    """삭제하려는 데이터셋을 아직 참조 중인 시나리오가 있다."""


class TimeSeriesDatasetRegistry:
    """id 로 데이터셋을 중복 없이 저장하고, 시나리오 참조를 추적한다."""

    def __init__(self) -> None:
        self._datasets: dict[str, TimeSeriesDataset] = {}
        self._references: dict[str, set[str]] = {}

    def register(self, dataset: TimeSeriesDataset) -> None:
        """데이터셋을 등록한다. 같은 id 가 이미 있으면 그대로 둔다.

        **덮어쓰지 않는 이유.** 이미 참조 중인 데이터셋을 다른 내용으로
        조용히 바꾸면 "무중단 교체"(AC2)가 아니라 참조자가 모르는 변경이
        된다. 내용을 바꾸려면 새 id 로 등록하고 ``TimeSeriesBinding.swap()``
        을 쓴다.
        """
        self._datasets.setdefault(dataset.id, dataset)

    def is_registered(self, dataset_id: str) -> bool:
        return dataset_id in self._datasets

    def count(self) -> int:
        """중복 제거된 데이터셋 개수."""
        return len(self._datasets)

    def bind(self, dataset_id: str, scenario_id: str) -> None:
        """시나리오가 데이터셋을 참조하기 시작한다."""
        if dataset_id not in self._datasets:
            raise KeyError(f"등록되지 않은 데이터셋입니다: {dataset_id}")
        self._references.setdefault(dataset_id, set()).add(scenario_id)

    def unbind(self, dataset_id: str, scenario_id: str) -> None:
        """시나리오가 데이터셋 참조를 그만둔다."""
        self._references.get(dataset_id, set()).discard(scenario_id)

    def referencing_scenarios(self, dataset_id: str) -> frozenset[str]:
        """이 데이터셋을 참조 중인 시나리오 id 전체."""
        return frozenset(self._references.get(dataset_id, set()))

    def delete(self, dataset_id: str) -> None:
        """참조가 남아 있으면 거부하고 **누가 참조 중인지** 알린다."""
        refs = self.referencing_scenarios(dataset_id)
        if refs:
            raise DatasetInUseError(
                f"데이터셋 `{dataset_id}` 를 삭제할 수 없습니다 — "
                f"참조 중인 시나리오: {', '.join(sorted(refs))}"
            )
        self._datasets.pop(dataset_id, None)
        self._references.pop(dataset_id, None)
