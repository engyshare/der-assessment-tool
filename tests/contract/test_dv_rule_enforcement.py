"""§7.3 대장의 규칙이 **실제 코드에서 구조로 던져지는가** — NFR-303-M1 · DV-14.

**이 파일이 붙드는 것은 `ValidationError` 가 아니다.** 그것은
`test_validation_contract.py` 가 이미 붙든다 — 다만 **그 파일은 예외를 손으로
만들어 검사한다.** 그래서 `rule="DV-2"` 가 그 안에 두 번 나오지만 `DV-2` 를
실제로 던지는 코드는 저장소에 한 줄도 없다. 사람이 읽으면 「DV-2 가 검증됐다」로
보이고, 추적표도 그렇게 센다.

R21 실측 — 대장 14규칙 중 **실제 코드가 `rule=` 로 던지는 것은 넷**이다:

    DV-4   infra/tsstore.py                 (R20 전환)
    DV-12  core/valuestream/exclusion_table.py
    DV-13  core/contracts/valuestream.py
    DV-14  core/contracts/der.py            ← R21 이 전환. 그전에는 맨 ValueError

`DV-14` 는 **강제하는 코드가 처음부터 있었다**(`_check_operating_mode`). 없던
것은 규칙 ID 를 나르는 형태였고, 그래서 `tests/der/test_pv.py` 의 독스트링이
*「선언 목록 밖의 운전 방법은 거부한다 (DV-14)」* 라 적으면서도 그 주장을
기계가 확인할 방법이 없었다. **주장은 독스트링에 있고 근거는 없었다.**

아래 둘째 테스트가 대장을 «던지는 것»과 «아직 아닌 것»으로 **가른다.** 열다섯
번째 규칙이 대장에 들어오면 그 테스트가 빨간불이 되어 분류를 요구한다 — 그것이
「대장에는 있는데 아무도 던지지 않는 규칙」이 조용히 늘지 않게 하는 유일한
방법이다 (`core/contracts/validation.py` 독스트링이 예고한 형태).
"""

from __future__ import annotations

import pytest

from core.contracts.validation import DV_RULES, ValidationError
from tests.contract.test_smoke_wave0 import ReferencePV


class ModelessPV(ReferencePV):
    """운전 방법을 **선언하지 않은** 자원 — 셋째 거부 경로를 위한 것.

    `OPERATING_MODES` 가 비었는데 `operating_mode` 를 받으면 그 값은 「선언
    목록에 속한다」를 만족할 수 없다. 이 경로를 빼면 남은 둘만 검사되고, 그
    사이 이 분기가 맨 `ValueError` 로 되돌아가도 초록불이다.
    """

    OPERATING_MODES = ()

# ── 대장의 분할 — **이 둘의 합집합이 대장 전체여야 한다** ──────────────────
#
# `실제로 던진다` 의 뜻: 배포 코드(`core/`·`infra/`·`app/`·`web/`)의 어느
# 지점이 `ValidationError(..., rule="DV-N")` 을 올리고, **그것을 실제 진입점으로
# 발동시키는 테스트가 있다.** 예외를 손으로 만들어 보는 것은 여기에 들지 않는다.
THROWN_BY_REAL_CODE: dict[str, str] = {
    "DV-4": "tests/infra/test_tsstore.py::test_write_rejects_wrong_row_count_"
            "carries_field_reason_action",
    "DV-12": "tests/contract/test_exclusion_rules_contract.py",
    "DV-13": "tests/contract/test_payer_structure_contract.py::"
             "test_structure_absent_falls_back_and_is_refused_when_unspecified",
    "DV-14": "tests/contract/test_dv_rule_enforcement.py::"
             "test_dv14_is_thrown_by_the_real_constructor",
}

#: 대장에 있으나 **아직 구조로 던지는 코드가 없는** 규칙.
#: 줄어들면 위 표에 옮긴다. `NOT_YET` 이 비는 날 이 상수를 지운다.
NOT_YET_THROWN: frozenset[str] = frozenset({
    "DV-1", "DV-2", "DV-3", "DV-5", "DV-6",
    "DV-7", "DV-8", "DV-9", "DV-10", "DV-11",
})


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
@pytest.mark.req("FR-105-AC1")
def test_dv14_is_thrown_by_the_real_constructor() -> None:
    """**실제 생성자를 지나야** 한다 — 예외를 손으로 만들지 않는다 (DV-14).

    세 거부 경로가 전부 규칙 ID 를 나른다. 셋을 한 표로 도는 이유는 **경로마다
    따로 붙들어야** 하기 때문이다 — 하나만 검사하면 나머지 둘이 맨
    `ValueError` 로 되돌아가도 초록불이다.
    """
    cases = [
        ("목록 밖", ReferencePV, "야간 발전"),
        ("미지정", ReferencePV, None),
        ("선언 없음", ModelessPV, "야간 발전"),
    ]
    for label, cls, mode in cases:
        with pytest.raises(ValidationError) as caught:
            cls(operating_mode=mode)  # type: ignore[arg-type]

        parts = caught.value.as_dict()
        assert parts["rule"] == "DV-14", f"{label}: 규칙 ID 가 붙지 않았다"
        # **필드는 어긋난 입력의 이름을 가리킨다** — 자원 이름만으로는
        # 사용자가 어느 칸을 고쳐야 하는지 알 수 없다
        assert parts["field"] == "der.PV.operating_mode", label
        # 인스턴스 이름은 **필드가 아니라 사유**에 있다 — 필드 키는 열거
        # 가능해야 하고 자원 이름은 사용자가 지은 자유 문자열이다
        assert "옥상PV" in (parts["reason"] or ""), f"{label}: 어느 인스턴스인지 없다"
        assert "옥상PV" not in (parts["field"] or ""), f"{label}: 필드에 이름이 섞였다"
        assert (parts["action"] or "").strip(), f"{label}: 조치가 비었다"

    # 지원 목록이 **있는** 경로는 조치에 그 목록을 실제로 넣는다. 「목록 안의
    # 값으로 고치십시오」만 적으면 그 목록을 찾으러 코드를 열어야 한다.
    # (`선언 없음` 경로는 목록이 없으므로 이 단언의 대상이 아니다)
    for mode_value in (None, "야간 발전"):
        with pytest.raises(ValidationError) as caught:
            ReferencePV(operating_mode=mode_value)  # type: ignore[arg-type]
        action = caught.value.as_dict()["action"] or ""
        for supported in ReferencePV.OPERATING_MODES:
            assert supported in action, f"{mode_value!r}: 조치에 {supported} 가 없다"


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_dv14_stays_catchable_as_valueerror() -> None:
    """`except ValueError` 로 받던 자리가 그대로 받는다.

    `tests/der/test_pv.py`·`test_ev_v2g.py` 가 `pytest.raises(ValueError,
    match="운전 방법")` 으로 물려 있다. 기반 예외를 갈아 끼우면 그 둘이
    **조용히 통과**하게 되고, 그 변화는 아무 오류도 내지 않는다.
    """
    with pytest.raises(ValueError, match="운전 방법"):
        ReferencePV(operating_mode="야간 발전")


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_the_catalogue_is_split_with_nothing_left_unclassified() -> None:
    """★ **대장 전체가 분류돼 있어야 한다** — 열다섯 번째가 오면 빨간불이다.

    이것이 이 파일의 요점이다. 「구조화된 오류를 쓴다」는 방침은 규칙이 늘 때
    조용히 새는데, 새는 자리가 **대장과 코드 사이**라 어느 테스트도 보지
    않는다. 합집합을 단언하면 그 자리가 검사 대상이 된다.
    """
    classified = set(THROWN_BY_REAL_CODE) | NOT_YET_THROWN
    catalogue = set(DV_RULES)

    assert not (THROWN_BY_REAL_CODE.keys() & NOT_YET_THROWN), (
        "한 규칙이 양쪽에 있습니다 — 던지는지 아닌지 하나로 정하십시오"
    )
    assert classified == catalogue, (
        "대장과 분류가 어긋납니다. 대장에만 있는 것: "
        f"{sorted(catalogue - classified)} / 분류에만 있는 것: "
        f"{sorted(classified - catalogue)}. 새 DV 규칙을 대장에 넣었다면 "
        "던지는 코드를 함께 놓고 THROWN_BY_REAL_CODE 에, 아직이면 "
        "NOT_YET_THROWN 에 적으십시오"
    )


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_every_rule_said_to_be_thrown_names_where_it_is_proven() -> None:
    """던진다고 적은 규칙은 **그것을 발동시키는 테스트 경로**를 함께 적는다.

    경로 없이 목록에 올리면 이 표가 곧 「손으로 유지되는 주장」이 되고, 그것이
    이 파일이 고치러 온 결함과 같은 형태다.
    """
    for rule, where in THROWN_BY_REAL_CODE.items():
        assert rule in DV_RULES, f"{rule} 은 대장에 없다 (매달린 참조)"
        assert where.startswith("tests/"), f"{rule}: 근거 경로가 테스트가 아니다"
        assert "::" in where or where.endswith(".py"), f"{rule}: 경로 형식"
