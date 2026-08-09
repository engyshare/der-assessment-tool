"""14.11 — SC-3 준수 검증 (스키마).

«가구 개별 식별정보가 DB 에 저장되지 않음» 을 스키마에서 기계로 확인.
절차(docs/privacy-procedure.md)는 16.3 소유, **검증이 여기**.
"""
from __future__ import annotations

import pytest

from app.security.sc3_check import (
    IDENTIFYING_COLUMN_PATTERNS,
    assert_sc3_compliant,
    check_schema_for_identifying_columns,
    user_table_is_authentication_not_household,
)


@pytest.mark.req("SC-3")
def test_clean_schema_passes() -> None:
    """양성 — 식별 컬럼이 없는 스키마는 통과.

    오라클: 순위 4 (정의 항등식). users(email/password_hash/role) + 시계열 데이터
    테이블(kind/checksum) — 가구 식별정보 자리가 없다.
    """
    schema = {
        "users": ("id", "email", "password_hash", "role"),
        "time_series_datasets": ("id", "kind", "checksum", "storage_path"),
        "scenarios": ("id", "name", "owner_id"),
    }
    violations = check_schema_for_identifying_columns(schema)
    assert violations == []


@pytest.mark.req("SC-3")
def test_identifying_column_in_schema_is_violation() -> None:
    """음성 — resident_name 컬럼이 자리하면 위반.

    **«값이 비어 있는 것» 과 «자리가 없는 것» 은 다르다.** 컬럼이 있고 값이
    비어 있으면 나중에 채울 수 있다 — 자리가 없어야 준수다.
    """
    schema = {
        "household_loads": ("id", "resident_name", "kwh"),  # 위반
    }
    violations = check_schema_for_identifying_columns(schema)
    assert len(violations) == 1
    assert violations[0].table == "household_loads"
    assert violations[0].column == "resident_name"


def test_meter_serial_in_schema_is_violation() -> None:
    """계량기 고유 번호 — 가구 식별정보."""
    schema = {"load_data": ("id", "meter_serial", "kwh")}
    violations = check_schema_for_identifying_columns(schema)
    assert any(v.column == "meter_serial" for v in violations)


def test_assert_sc3_compliant_raises_on_violation() -> None:
    """위반 시 예외 — 기동/CI 시점 검증."""
    schema = {"x": ("id", "customer_number")}
    with pytest.raises(ValueError, match="SC-3 위반"):
        assert_sc3_compliant(schema)


def test_users_table_email_is_authentication_not_household() -> None:
    """``users`` 테이블의 email 은 인증이지 가구 식별이 아니다.

    SC-1(인증) 과 SC-3(가구 식별) 은 다른 축 — 혼동하면 User.email 을 SC-3 위반으로
    오판한다. ``user_table_is_authentication_not_household`` 가 그것을 가른다.
    """
    assert user_table_is_authentication_not_household("users") is True
    assert user_table_is_authentication_not_household("household_loads") is False


def test_patterns_cover_key_identifying_fields() -> None:
    """식별 패턴이 핵심 가구 식별 필드를 덮는지 — 회귀 방지."""
    for key in (
        "household_name", "household_address", "resident_name",
        "resident_phone", "meter_serial", "customer_number",
    ):
        assert key in IDENTIFYING_COLUMN_PATTERNS


def test_check_is_case_insensitive() -> None:
    """컬럼명 대소문자 구분 안 함 — ``RESIDENT_NAME`` 도 잡는다."""
    schema = {"x": ("id", "RESIDENT_NAME")}
    violations = check_schema_for_identifying_columns(schema)
    assert len(violations) == 1
