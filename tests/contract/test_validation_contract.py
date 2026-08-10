"""`ValidationError` 계약 테스트 — NFR-303 · §7.3.

**이 파일이 붙드는 것은 «메시지가 예쁜가» 가 아니라 «3요소가 구조로 남는가» 다.**
사람이 읽어 셋이 다 들어 있어 보이는 문자열은 지금까지도 있었다. 없던 것은
기계가 셋을 분리해 확인할 수 있는 형태였고, 그래서 NFR-303-M1 이 「검사 함수
자신만 검사하는」 상태로 남아 있었다 (R15 WP-26F 판정, `test_dashboard.py:95`).
"""

from __future__ import annotations

import pytest

from core.contracts.validation import DV_RULES, ValidationError


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_three_parts_are_a_construction_condition_not_a_check() -> None:
    """**셋 중 하나가 비면 예외가 만들어지지 않는다.**

    검사로 두면 「검사를 돌리지 않은 경로」가 생긴다 — 그 경로로 만들어진
    오류는 조치가 빈 채 사용자에게 도달하고, 그때는 이미 늦다.
    """
    for missing in ("field", "reason", "action"):
        kwargs: dict[str, str] = {
            "field": "ess.soc_min",
            "reason": "하한이 상한보다 큽니다",
            "action": "하한을 낮추십시오",
        }
        kwargs[missing] = "   "        # 공백만 있는 것도 «없음» 이다
        with pytest.raises(ValueError, match="필드·사유·조치"):
            ValidationError(**kwargs)  # type: ignore[arg-type]


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_message_carries_all_three_and_survives_structurally() -> None:
    """문자열에도 셋이 들어가고, **구조로도 따로 꺼낼 수 있다.**

    표시 쪽이 `str()` 을 쪼개 쓰면 메시지 형식이 바뀔 때 표시가 조용히
    깨진다. 그래서 `as_dict()` 를 함께 둔다.
    """
    err = ValidationError(
        field="ess.soc_min",
        reason="SOC 하한(80)이 상한(20)보다 큽니다",
        action="하한을 상한보다 작은 값으로 고치십시오",
        rule="DV-2",
    )
    text = str(err)
    assert "ess.soc_min" in text
    assert "상한(20)보다" in text
    assert "고치십시오" in text
    assert "DV-2" in text

    assert err.as_dict() == {
        "field": "ess.soc_min",
        "reason": "SOC 하한(80)이 상한(20)보다 큽니다",
        "action": "하한을 상한보다 작은 값으로 고치십시오",
        "rule": "DV-2",
    }


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_existing_handlers_still_catch_it() -> None:
    """**`except ValueError` 로 받던 자리가 그대로 받는다.**

    새 기반 예외를 만들었다면 그 호출부들이 조용히 통과시키게 되고, 그
    변화는 «아무 오류도 나지 않는» 형태로 나타난다 — 가장 찾기 어려운 종류다.
    """
    with pytest.raises(ValueError):
        raise ValidationError(field="f", reason="r", action="a")


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_rule_id_must_exist_in_the_spec_catalogue() -> None:
    """대장에 없는 규칙 ID 는 **매달린 참조**다 (NFR-107).

    달아 두면 추적표가 그 규칙을 검증된 것으로 세지만 실제로는 어느 조항도
    가리키지 않는다. 형식만 맞는 `DV-99` 도 마찬가지로 막는다.
    """
    with pytest.raises(ValueError, match="형식이 아닙니다"):
        ValidationError(field="f", reason="r", action="a", rule="dv2")
    with pytest.raises(ValueError, match="대장에 없는"):
        ValidationError(field="f", reason="r", action="a", rule="DV-99")

    assert "DV-12" in DV_RULES      # 배타 위반 시 실행 거부 — FR-402-AC2.A
    assert "DV-13" in DV_RULES      # 지불 주체 미특정 — FR-402-AC5


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_a_new_rule_needs_no_change_in_the_consumer() -> None:
    """★ **확장점 증명** — 규칙을 더해도 표시·직렬화 쪽은 그대로다.

    「확장점이 있다」와 「그 경로로 실제로 확장된다」는 다르다. 그래서 서로
    **다른 두 규칙**을 같은 소비자 코드에 통과시켜 본다. 소비자는 규칙이
    무엇인지 모른 채 셋을 꺼내며, 열다섯 번째 규칙이 와도 이 함수는 바뀌지
    않는다.
    """

    def render_for_user(exc: ValidationError) -> str:
        """표시 쪽 대역 — 규칙 종류를 전혀 모른다."""
        parts = exc.as_dict()
        return f"{parts['field']}: {parts['reason']} → {parts['action']}"

    soc = ValidationError(
        field="ess.soc_min",
        reason="하한이 상한보다 큽니다",
        action="하한을 낮추십시오",
        rule="DV-2",
    )
    rows = ValidationError(
        field="timeseries.rows",
        reason="행수가 8,760 이 아닙니다 (실측 8,000)",
        action="8760 또는 35040 행으로 맞추십시오",
        rule="DV-4",
    )

    assert render_for_user(soc).startswith("ess.soc_min: ")
    assert render_for_user(rows).startswith("timeseries.rows: ")
    # 소비자가 규칙별 분기를 갖지 않는다 — 둘 다 같은 경로로 표시된다
    assert render_for_user(soc).count("→") == render_for_user(rows).count("→") == 1
