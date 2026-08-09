"""감사 로그 기록 — 작업 14.9 / SC-4.

**저장 계층은 WP-13 이 만들었다** (``infra/audit.py`` — 테이블과 ``write_audit()``
통로). SC-4 마커도 WP-13 은 달지 않았다 — 그 판단이 맞으므로 **다시 만들지 않는다**.
여기서 정하는 것은 **«무엇을 기록할 것인가»** 이다.

기록 대상 (SC-4):
    · 로그인(성공·실패)
    · 시나리오·전제 생성·수정·삭제 (CRUD)
    · 카탈로그 변경 (관리자)

**개인정보는 넣지 않는다** (SC-3). 감사 로그이 우회로가 되면 16.3 절차가
무의미해진다 — ``before_json``/``after_json`` 에 이름·주소·전화번호를 넣지 않는다.
"""
from __future__ import annotations

from enum import StrEnum

from sqlalchemy.orm import Session

from infra.audit import write_audit


class AuditAction(StrEnum):
    """감사 로그에 기록하는 행위 유형 (SC-4).

    어휘는 ``infra/audit.py`` 가 «영속성은 그릇만 제공하고 액션 enum 은 app 이
    정의한다» 는 원칙에 따라 **여기서 정의한다**.
    """

    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGOUT = "auth.logout"
    SCENARIO_CREATE = "scenario.create"
    SCENARIO_UPDATE = "scenario.update"
    SCENARIO_DELETE = "scenario.delete"
    SCENARIO_RESTORE = "scenario.restore"
    ASSUMPTION_CREATE = "assumption.create"
    ASSUMPTION_UPDATE = "assumption.update"
    ASSUMPTION_DELETE = "assumption.delete"
    CATALOG_UPDATE = "catalog.update"  # 관리자 카탈로그 변경


def record(
    session: Session,
    *,
    action: AuditAction,
    actor_user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    before_json: str | None = None,
    after_json: str | None = None,
    note: str | None = None,
) -> None:
    """감사 로그 1행 기록 — ``infra.audit.write_audit`` 의 얇은 래퍼.

    ``action`` 은 ``AuditAction`` enum 으로 제한한다 — 임의 문자열이 들어가면
    기록 대상 정의가 의미 없어진다. ``write_audit`` 자체는 임의 action 을 받지만,
    이 통로가 유일한 호출 경로여야 한다.

    **개인정보 검사**: ``before_json``/``after_json`` 에 식별 패턴이 있으면 예외.
    """
    _assert_no_pii(before_json, "before_json")
    _assert_no_pii(after_json, "after_json")
    write_audit(
        session,
        action=str(action),
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        before_json=before_json,
        after_json=after_json,
        note=note,
    )


#: SC-3 — 감사 로그에 들어가면 안 되는 가구 식별 패턴.
_PII_PATTERNS: tuple[str, ...] = (
    "resident_name", "household_address", "resident_phone",
    "meter_serial", "customer_number",
)


def _assert_no_pii(payload: str | None, field_name: str) -> None:
    """``before_json``/``after_json`` 에 가구 식별정보 키가 있으면 예외.

    감사 로그가 SC-3 의 우회로가 되는 것을 막는다. 값이 아닌 «키 이름» 으로
    잡는다 — 값이 비어 있어도 나중에 채워지면 이미 늦다.
    """
    if payload is None:
        return
    lower = payload.lower()
    for pattern in _PII_PATTERNS:
        if pattern in lower:
            raise ValueError(
                f"감사 로그 {field_name} 에 가구 식별정보 키({pattern!r}) 가 있다 — "
                "감사 로그는 SC-3 의 우회로가 될 수 없다 (SC-4 가 SC-3 에 종속)"
            )
