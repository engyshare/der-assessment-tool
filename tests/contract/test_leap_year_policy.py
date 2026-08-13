"""`DV-4` 후반부 — **윤년 처리 규칙이 선언돼 있는가** (NFR-303-M1 · FR-301).

§7.3 대장 `DV-4` 는 *「시계열 행수 = 8760 (또는 35,040), **윤년 처리 규칙
명시**」* 다. R24 인수까지 **앞쪽만 강제되고 뒤쪽은 아무 데도 없었다.** 저장소
전체에 `8784`·`35136`·`isleap` 이 0건이었고, 윤년을 말하는 것은 「윤년을 쓰지
않는다」는 모듈 내부 주석 둘뿐이었다 — 둘 다 **자기 모듈의 사정**으로 적혀
있어 규칙의 선언이 아니었다.

그런데 `DV-4` 는 분류표에서 「배포 코드가 던진다 = 검증됨」이었다. **규칙의
절반만 붙들면서 규칙 전체를 검증한 것으로 세고 있었다.**

왜 「던진다」로 닫지 않는가
--------------------------
**「명시」는 던지는 일이 아니라 선언하는 일이다.** 발동시킬 사건을 찾아
`ValidationError` 를 놓는 것으로는 *「규칙이 적혀 있다」* 를 만들 수 없다.
그래서 이 파일이 붙드는 것은 예외가 아니라 **선언의 실재와 그 선언이 참인가**
다. 셋을 본다.

    ① 선언이 한 곳에 있고 규칙이 말해야 하는 것을 실제로 말한다
    ② 선언이 「연도와 무관」이라고 했으니 **스텝 수가 연도를 받을 수 없다**
    ③ 선언이 「366일은 받지 않는다」고 했으니 **윤년 행 수가 허용 목록에 없다**

②·③ 이 이 파일의 값이다. ① 만 두면 문자열이 있는지만 보게 되고, 그것은 이
저장소가 열일곱 번 만난 형태 — **주장은 있고 근거는 없는 검사** — 가 하나 더
느는 것이다. 선언이 거짓이 되는 두 경로를 각각 막는다.
"""

from __future__ import annotations

import inspect

import pytest

from core.contracts.units import (
    HOURS_PER_LEAP_YEAR,
    HOURS_PER_YEAR,
    LEAP_YEAR_POLICY,
    STEPS_15MIN_PER_LEAP_YEAR,
    STEPS_15MIN_PER_YEAR,
    steps_per_year,
)
from infra.tsstore import ALLOWED_ROW_COUNTS, LEAP_YEAR_ROW_COUNTS

HOURS_PER_DAY = 24
STEPS_15MIN_PER_DAY = 96


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_the_leap_year_rule_is_actually_stated() -> None:
    """① 선언이 있고, **규칙이 말해야 하는 것**을 말한다.

    빈 문자열이나 「윤년은 별도 처리」류의 한 줄은 선언이 아니다. `DV-4` 를
    근거로 판단하는 사람이 이 문면만 읽고 ⓐ 무엇을 쓰는지 ⓑ 366일 자료가
    오면 어떻게 되는지 ⓒ 그때 무엇을 해야 하는지를 알 수 있어야 한다.
    """
    assert LEAP_YEAR_POLICY.strip(), "윤년 규칙이 선언돼 있지 않다"

    # ⓐ 무엇을 쓰는가 — 평년 규약과 두 해상도
    assert "평년" in LEAP_YEAR_POLICY
    assert "8,760" in LEAP_YEAR_POLICY and "35,040" in LEAP_YEAR_POLICY

    # ⓑ 366일 자료는 어떻게 되는가 — 「받지 않는다」가 문면에 있어야 한다
    assert "366일" in LEAP_YEAR_POLICY
    assert "2월 29일" in LEAP_YEAR_POLICY, (
        "윤년 규칙이 그 하루를 언급하지 않으면, 읽는 사람은 스텝 수만 맞추면 "
        "되는지 그 하루를 버려야 하는지 알 수 없다"
    )

    # ⓒ 그때 무엇을 해야 하는가 — 조치가 호출측에 있다는 것까지
    assert "호출측" in LEAP_YEAR_POLICY


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
@pytest.mark.req("FR-301-AC3")
def test_the_step_count_cannot_depend_on_the_year() -> None:
    """★★ ② 선언이 「연도와 무관」이라고 했다 — **그것이 참이어야 한다.**

    `steps_per_year` 가 연도를 받기 시작하면 위 선언은 그 순간 거짓이 된다.
    그런데 그 변화는 아무 예외도 내지 않고, 기존 호출부도 기본값으로 계속
    통과한다 — **선언만 낡은 채로 남는다.** 서명을 붙들어 그 경로를 막는다.

    이것이 문자열 검사(①)와 다른 점이다. ① 은 문면이 지워지는 것을 막고,
    여기는 **문면이 그대로인 채 사실이 아니게 되는 것**을 막는다.
    """
    params = list(inspect.signature(steps_per_year).parameters)
    assert params == ["dt_seconds"], (
        f"`steps_per_year` 의 인자가 {params} 로 바뀌었습니다. 연도(또는 날짜)를 "
        "받는다면 `LEAP_YEAR_POLICY` 의 「연도와 무관하게 평년 규약을 쓴다」가 "
        "더는 참이 아닙니다 — 규칙을 먼저 고치십시오 (§16.5)."
    )

    # 해상도별 스텝 수는 상수이며, 그 상수가 평년 값이다
    assert steps_per_year(3600) == HOURS_PER_YEAR == 8760
    assert steps_per_year(900) == STEPS_15MIN_PER_YEAR == 35_040


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_leap_year_row_counts_are_the_leap_counts_and_are_not_allowed() -> None:
    """★★ ③ 선언이 「366일 시계열은 받지 않는다」고 했다 — 두 갈래로 붙든다.

    ⓐ **윤년 상수가 정말 윤년 값인가** — 아무 숫자나 적어 두고 「윤년 행 수」라
    부르면, 실제 366일 자료(8784행)는 그 목록에 걸리지 않아 **일반 거부 문장을
    받는다.** 그러면 선언은 있는데 닿지 않는다.
    ⓑ **그 값이 허용 목록에 들어가 있지 않은가** — 누가 `ALLOWED_ROW_COUNTS` 에
    8784 를 더하면 선언은 거짓이 되는데, 그 변경은 기존 검사를 **하나도**
    빨간불로 만들지 않는다(허용이 늘어나는 방향이므로).
    """
    # ⓐ 윤년 = 평년 + 하루
    assert HOURS_PER_LEAP_YEAR == HOURS_PER_YEAR + HOURS_PER_DAY == 8784
    assert (
        STEPS_15MIN_PER_LEAP_YEAR
        == STEPS_15MIN_PER_YEAR + STEPS_15MIN_PER_DAY
        == 35_136
    )
    assert {HOURS_PER_LEAP_YEAR, STEPS_15MIN_PER_LEAP_YEAR} == LEAP_YEAR_ROW_COUNTS

    # ⓑ 허용과 겹치지 않는다
    assert not (ALLOWED_ROW_COUNTS & LEAP_YEAR_ROW_COUNTS), (
        f"윤년 행 수가 허용 목록에 있습니다: "
        f"{sorted(ALLOWED_ROW_COUNTS & LEAP_YEAR_ROW_COUNTS)}. "
        "`LEAP_YEAR_POLICY` 는 366일 시계열을 받지 않는다고 선언합니다 — "
        "규약을 바꾸려면 선언을 먼저 고치십시오."
    )
    assert {HOURS_PER_YEAR, STEPS_15MIN_PER_YEAR} == ALLOWED_ROW_COUNTS
