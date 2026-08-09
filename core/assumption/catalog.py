import re
from datetime import date

from pydantic import BaseModel, model_validator

from core.assumption.item import ConfidenceLevel, _has_external_source


class TechCatalogItem(BaseModel):
    """기술 카탈로그 항목 (FR-603).

    부기 7종을 ``AssumptionItem`` 과 동일하게 가지며, 추가로 자원 종류와
    규격을 식별한다. ``usage_terms`` (SC-7 이용조건) 규칙도 동일 — 외부
    출처 항목은 이용조건이 필수.
    """
    resource_type: str
    specification: str

    value: float | int
    value_unit: str
    base_year: str
    applicable_scope: str
    derivation_method: str
    source: str | None
    verified_at: date | None
    confidence: ConfidenceLevel

    # SC-7 이용조건 — ``AssumptionItem`` 과 동일 규칙.
    usage_terms: str | None = None

    @model_validator(mode="after")
    def _usage_terms_required_for_external_source(self) -> "TechCatalogItem":
        if _has_external_source(self.source) and not (
            self.usage_terms and self.usage_terms.strip()
        ):
            raise ValueError(
                "source 가 외부 출처이면 usage_terms (이용조건) 가 필수입니다 "
                "(SC-7). 카탈로그값의 출처·재사용 조건을 적으십시오."
            )
        return self

    def escalate(self, target_year: int, inflation_rate: float) -> float | int:
        """기준연도로부터 목표 연도까지 물가를 조정한다."""
        # base_year 문자열에서 연도를 추출 (e.g. "2026 (전망)" -> 2026)
        match = re.search(r'\d{4}', self.base_year)
        if not match:
            raise ValueError(f"기준연도를 추출할 수 없습니다: {self.base_year}")

        base_y = int(match.group())
        diff_years = target_year - base_y

        if diff_years == 0:
            return self.value

        factor = (1 + inflation_rate) ** diff_years
        return type(self.value)(self.value * factor)
