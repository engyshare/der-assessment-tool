from datetime import date
from enum import Enum

from pydantic import BaseModel, model_validator


class ConfidenceLevel(str, Enum):  # noqa: UP042
    """신뢰도 등급 (근거 표기 기준 2절 축 2).

    `미확인` 은 축 1 전용이며 이 enum 에 없다 — 폐기 어휘가 이 코드에 남아
    있으면 실패한다 (4.3 DoD, ``tests/assumption/test_no_deprecated_vocabulary.py``
    가 ast 기반으로 강제).
    """
    CONFIRMED = "확정"
    ESTIMATED = "추정"
    ASSUMED = "가정"


def _has_external_source(source: str | None) -> bool:
    """source 가 외부 출처이면 참.

    ``None`` 이거나 공백이면 내부/미상 — 외부 출처가 아니므로 이용조건을
    요구하지 않는다. source 가 «문자열» 이면 외부 출처로 본다.
    """
    return source is not None and source.strip() != ""


class AssumptionItem(BaseModel):
    """전제 대장 항목 1건과 부기 7종 + 이용조건.

    부기 7종(value_unit·base_year·applicable_scope·derivation_method·source·
    verified_at·confidence)의 정본은 볼트의 근거 표기 기준 문서이며, 여기서는
    그 자리만 고정한다. **이용조건(usage_terms)은 부기 7종이 아니다** —
    SC-7 이 요구하는 «출처 + 이용조건 보관» 에서 부기 7종의 ``source`` 가
    출처를 담당하고 ``usage_terms`` 가 이용조건(라이선스·재배포 조건·출처 표기
    의무 등)을 담당한다. 외부 출처가 있으면 이용조건도 필수다.
    """
    key: str
    value: float | int | str

    # ── 부기 7종 (FR-601-AC5) ────────────────────────────────────────
    value_unit: str
    base_year: str
    applicable_scope: str
    derivation_method: str
    source: str | None
    verified_at: date | None
    confidence: ConfidenceLevel

    # ── SC-7 이용조건 — 부기 7종과 별개 축 ─────────────────────────
    # source 가 외부 출처이면 필수 (model_validator 로 강제).
    usage_terms: str | None = None

    @model_validator(mode="after")
    def _usage_terms_required_for_external_source(self) -> "AssumptionItem":
        """외부 출처 항목은 이용조건이 필수 (SC-7).

        부기 7종의 source 만으로 SC-7 이 충족되지 않는다 — «출처» 와
        «이용조건» 은 다른 축이며, 공개 단가표에는 출처 표기 의무·재배포
        금지 등 이용조건이 붙는다. source 가 있으면 이용조건도 함께 보관해야
        SC-7 마커가 형식적이지 않게 된다.
        """
        if _has_external_source(self.source) and not (
            self.usage_terms and self.usage_terms.strip()
        ):
            raise ValueError(
                "source 가 외부 출처이면 usage_terms (이용조건) 가 필수입니다 "
                "(SC-7). 라이선스·재배포 조건·출처 표기 의무 등을 적으십시오."
            )
        return self

    def is_scalar(self) -> bool:
        """값이 스칼라인지 참조(문자열)인지 확인한다."""
        return not isinstance(self.value, str)
