from typing import Any

from pydantic import BaseModel


def validate_csv_upload(content: bytes, size_bytes: int, mime_type: str, line_count: int) -> bool:
    """CSV 업로드 검증 (FR-905, NFR-404-AC1)."""
    if mime_type not in ("text/csv", "application/vnd.ms-excel"):
        raise ValueError(f"Invalid MIME type: {mime_type}. Must be text/csv.")

    if size_bytes > 10 * 1024 * 1024:
        raise ValueError(f"File size exceeds 10MB limit: {size_bytes} bytes")

    if line_count > 100000:
        raise ValueError(f"Line count exceeds 100,000 limit: {line_count}")

    return True


class TimeSeriesDataset(BaseModel):
    id: str
    name: str
    data: list[float]


class TimeSeriesBinding:
    """인스턴스 단위 시계열 바인딩 (FR-905)."""
    def __init__(self, instance_id: str, dataset: TimeSeriesDataset):
        self.instance_id = instance_id
        self._dataset = dataset

    def get_data(self) -> list[float]:
        return self._dataset.data

    def swap(self, new_dataset: TimeSeriesDataset) -> None:
        """무중단 교체."""
        self._dataset = new_dataset

    def preview_swap(self, new_dataset: TimeSeriesDataset) -> dict[str, Any]:
        """교체 영향 미리보기."""
        old_data = self._dataset.data
        new_data = new_dataset.data

        old_mean = sum(old_data) / len(old_data) if old_data else 0
        new_mean = sum(new_data) / len(new_data) if new_data else 0

        return {
            "old_mean": old_mean,
            "new_mean": new_mean,
            "diff_mean": new_mean - old_mean
        }
