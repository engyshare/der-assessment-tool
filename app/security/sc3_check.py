"""SC-3 준수 검증 — 작업 14.11 / SC-3.

16.3 절차(``docs/privacy-procedure.md``, WP-14 소유)가 **지켜졌는지를 DB 스키마에서
기계로 확인**한다. 절차 자체는 여기서 만들지 않는다.

**«가구 개별 식별정보가 DB 에 저장되지 않음»** — 스키마에 그런 **컬럼 자리**가
없는가를 검사한다. 값이 비어 있는 것과 자리가 없는 것은 다르다:
- 컬럼이 있고 값이 비어 있으면 → 나중에 채울 수 있다 (위반)
- 컬럼 자체가 없으면 → 채울 수 없다 (준수)

``scripts/check_disclosure.py`` 가 «저장소» 를 보고, 이 검사는 «DB 스키마» 를 본다.
둘은 다른 축이다.
"""
from __future__ import annotations

from dataclasses import dataclass

#: 가구 개별 식별정보로 쓰일 수 있는 컬럼명 — SC-3 이 «실증 참여 가구의 개별
#: 식별정보 미저장» 을 요구하므로, 이 이름들이 스키마에 자리하면 위반이다.
#:
#: **«일반 테이블의 name» 과 «사용자 name» 을 구분한다.** User.email·User.role 은
#: 인증 대상이지 가구 식별이 아니다 — SC-1·SC-3 은 다른 축이다. 그래서 검사는
#: «부하 데이터» 관련 테이블(time_series_datasets·der_instances)에 한정한다.
IDENTIFYING_COLUMN_PATTERNS: tuple[str, ...] = (
    "household_name",
    "household_address",
    "resident_name",
    "resident_phone",
    "meter_serial",
    "customer_number",
    "account_number",
)


@dataclass(frozen=True)
class SchemaViolation:
    """SC-3 위반 1건 — 테이블·컬럼·사유."""

    table: str
    column: str
    reason: str


def check_schema_for_identifying_columns(
    table_columns: dict[str, tuple[str, ...]],
) -> list[SchemaViolation]:
    """스키마에서 가구 식별정보 컬럼 자리를 찾는다.

    ``table_columns``: {테이블명: (컬럼명, ...)}. SQLAlchemy ``inspect`` 또는
    테스트 더미에서 만들어 넘긴다.

    **«자리가 없는 것» 이 준수다.** 컬럼이 있고 값이 비어 있으면 위반 —
    나중에 채울 수 있기 때문이다.
    """
    violations: list[SchemaViolation] = []
    for table, columns in table_columns.items():
        col_lower = {c.lower() for c in columns}
        for pattern in IDENTIFYING_COLUMN_PATTERNS:
            if pattern in col_lower:
                violations.append(SchemaViolation(
                    table=table,
                    column=pattern,
                    reason="가구 식별정보 컬럼이 자리하고 있다 — 값이 비어 있어도 "
                    "나중에 채울 수 있으므로 SC-3 위험이다",
                ))
    return violations


def assert_sc3_compliant(table_columns: dict[str, tuple[str, ...]]) -> None:
    """SC-3 위반 시 예외. 기동 시점 또는 CI 에서 돈다."""
    violations = check_schema_for_identifying_columns(table_columns)
    if violations:
        details = "; ".join(f"{v.table}.{v.column}" for v in violations)
        raise ValueError(
            f"SC-3 위반 — 가구 개별 식별정보 컬럼이 DB 스키마에 있다: {details}. "
            "16.3 절차가 «반입 전 차단» 을 요구하는데, 컬럼이 자리하면 나중에 "
            "채울 수 있다 — 값이 비어 있는 것과 자리가 없는 것은 다르다"
        )


def user_table_is_authentication_not_household(table_name: str) -> bool:
    """``users`` 테이블의 email·password_hash·role 은 인증용이지 가구 식별이 아니다.

    SC-1(인증) 과 SC-3(가구 식별) 은 다른 축이다 — User.email 은 로그인 대상이고,
    가구 식별정보는 «실증 참여 가구» 의 이름·주소·전화번호다. 혼동하면
    인증 컬럼을 SC-3 위반으로 오판한다.
    """
    return table_name.lower() in {"users", "user"}
