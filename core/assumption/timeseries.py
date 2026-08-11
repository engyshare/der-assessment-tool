from datetime import date
from typing import Any

from pydantic import BaseModel

from core.assumption.item import ConfidenceLevel


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

    #: 대체 입력(FR-905-AC4)으로 만들어졌는지. 실측이 아니라는 표시이며,
    #: ``TimeSeriesBinding.swap()`` 으로 실측 시계열로 교체될 때까지
    #: 리포트가 "추정값" 임을 밝혀야 한다.
    is_estimated: bool = False

    # ── 출처 메타데이터 5종 (FR-905-AC8) ────────────────────────────────
    #: 출처
    source: str | None = None
    #: 계측기간
    measurement_period: str | None = None
    #: 해상도 (예: "1시간", "15분")
    resolution: str | None = None
    #: 신뢰도 — item.py 의 3단계 enum 을 그대로 쓴다. 시계열도 전제
    #: 대장의 다른 항목과 같은 신뢰도 축을 공유해야 리포트가 한 배지
    #: 체계로 표시할 수 있다.
    confidence: ConfidenceLevel | None = None
    #: 최종확인일
    verified_at: date | None = None

    def source_metadata(self) -> dict[str, str]:
        """리포트에 표기할 출처 메타데이터 5종 (FR-905-AC8 후단).

        값이 없는 항목은 빈칸이 아니라 **미보유**로 명시한다 — 빈 문자열은
        "확인했는데 없다"와 "확인하지 않았다"를 구별하지 못한다.
        """
        return {
            "출처": self.source if self.source else "미보유",
            "계측기간": self.measurement_period if self.measurement_period else "미보유",
            "해상도": self.resolution if self.resolution else "미보유",
            "신뢰도": self.confidence.value if self.confidence else "미보유",
            "최종확인일": self.verified_at.isoformat() if self.verified_at else "미보유",
        }


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
