import re
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, model_validator

from core.assumption.item import ConfidenceLevel, _has_external_source
from core.contracts.validation import ValidationError


class TechCatalogItem(BaseModel):
    """기술 카탈로그 항목 (FR-603).

    부기 7종을 ``AssumptionItem`` 과 동일하게 가지며, 추가로 자원 종류와
    규격을 식별한다. ``usage_terms`` (SC-7 이용조건) 규칙도 동일 — 외부
    출처 항목은 이용조건이 필수.

    ``FR-603-AC1`` (v0.5 정정) 은 부기 7종에 ``기준일``·``버전``(``기준일·
    기준연도·버전``)과 ``조건``·``표본``(``적용 범위·조건``·``산출 방법·
    표본``)을 추가로 요구한다 — v0.4 는 이 중 뒤 두 그룹이 빠져 있었다.
    """
    resource_type: str
    specification: str

    value: float | int
    value_unit: str
    #: 기준일 — 단가가 조사·확정된 특정 일자. ``base_year``(기준연도)와
    #: 별개다 — 연도는 조정 계산의 입력이고, 기준일은 그 값이 «언제
    #: 조사됐는지» 를 리포트에 밝히는 출처 정보다.
    as_of_date: date | None
    base_year: str
    #: 버전 — 같은 항목이라도 카탈로그 개정판이 바뀌면 값이 바뀐다.
    version: str
    applicable_scope: str
    #: 적용 조건 — 적용 범위(대상)와 별개로, 그 범위 안에서도 성립하는
    #: 전제조건(예: 시공 방식·규모 구간)을 적는다.
    condition: str | None
    derivation_method: str
    #: 산출 표본 — 산출 방법이 근거한 표본의 크기·구성을 적는다.
    #: 표본이 없는 산출(순수 추정)이면 그 사실 자체가 표본 설명이다.
    sample: str | None
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
            raise ValidationError(
                field="techcatalog.usage_terms",
                reason=f"source({self.source!r})가 외부 출처인데 usage_terms "
                       "(이용조건)가 없습니다 (SC-7)",
                action="카탈로그값의 출처·재사용 조건(라이선스·재배포 조건·"
                       "출처 표기 의무 등)을 usage_terms 에 적으십시오",
            )
        return self

    def escalate(self, target_year: int, inflation_rate: float) -> float | int:
        """기준연도로부터 목표 연도까지 물가를 조정한다."""
        return self.escalate_with_detail(target_year, inflation_rate).escalated_value

    def escalate_with_detail(
        self, target_year: int, inflation_rate: float
    ) -> "EscalationDetail":
        """물가 조정과 함께 **조정 내역**을 함께 낸다 (FR-603-AC3 후단).

        ``escalate()`` 는 조정된 값만 돌려주어 리포트가 «무엇을 근거로
        얼마를 조정했는지» 를 다시 계산해야 했다. 이 메서드가 그 내역
        (기준연도·목표연도·연차·인상률·계수·조정 전후 값)을 한 번에 낸다.
        """
        # base_year 문자열에서 연도를 추출 (e.g. "2026 (전망)" -> 2026)
        match = re.search(r'\d{4}', self.base_year)
        if not match:
            raise ValidationError(
                field="techcatalog.base_year",
                reason=f"base_year 에서 4자리 연도를 찾을 수 없습니다: "
                       f"{self.base_year!r}",
                action="base_year 에 4자리 연도를 포함하십시오 "
                       "(예: '2026' 또는 '2026 (전망)')",
                rule="DV-8",
            )

        base_y = int(match.group())
        diff_years = target_year - base_y

        if diff_years == 0:
            escalated = self.value
            factor = 1.0
        else:
            factor = (1 + inflation_rate) ** diff_years
            escalated = type(self.value)(self.value * factor)

        return EscalationDetail(
            base_year=base_y,
            target_year=target_year,
            diff_years=diff_years,
            inflation_rate=inflation_rate,
            factor=factor,
            base_value=self.value,
            escalated_value=escalated,
        )


@dataclass(frozen=True)
class EscalationDetail:
    """물가 조정 내역 — 조정 사실뿐 아니라 **어떻게 조정했는지**를 나른다
    (FR-603-AC3). 리포트가 "얼마에서 얼마로, 몇 %로 조정했는지"를 표시할
    수 있어야 조정이 «표시» 된 것이다 — 조정된 값만 있으면 표시가 아니라
    결과만 남는다.
    """

    base_year: int
    target_year: int
    diff_years: int
    inflation_rate: float
    factor: float
    base_value: float | int
    escalated_value: float | int

    def describe(self) -> str:
        """리포트에 그대로 얹을 수 있는 한 줄 조정 내역."""
        return (
            f"{self.base_year} 기준값 {self.base_value} → {self.target_year} "
            f"조정값 {self.escalated_value} "
            f"(연 {self.inflation_rate:.1%} x {self.diff_years}년, "
            f"계수 {self.factor:.4f})"
        )


@dataclass(frozen=True)
class CatalogValueResolution:
    """카탈로그 값과 사용자 변경값을 구분해 나른다 (FR-603-AC2).

    리포트가 "이 값이 카탈로그 기본값인지, 사용자가 바꾼 값인지" 를
    시각적으로 구분하려면(예: 배지·색) 그 판정 자체가 어딘가에 있어야
    한다. ``effective_value`` 만 넘기면 리포트가 그 출처를 다시 추적해야
    하고, 추적하지 않으면 구분이 사라진다.
    """

    catalog_value: float | int
    effective_value: float | int
    is_overridden: bool


def resolve_catalog_value(
    item: TechCatalogItem, override: float | int | None = None
) -> CatalogValueResolution:
    """사용자 오버라이드가 있으면 그것을, 없으면 카탈로그 값을 유효값으로 낸다.

    ``override`` 가 주어졌다는 사실 자체가 "사용자가 바꿨다"이다 — 그 값이
    우연히 카탈로그 값과 같더라도 사용자가 명시적으로 지정했다는 사실은
    바뀌지 않으므로 ``is_overridden`` 은 값의 일치 여부가 아니라 **오버라이드
    존재 여부**로 판정한다.
    """
    if override is None:
        return CatalogValueResolution(
            catalog_value=item.value, effective_value=item.value, is_overridden=False
        )
    return CatalogValueResolution(
        catalog_value=item.value, effective_value=override, is_overridden=True
    )
