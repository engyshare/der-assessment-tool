"""**거부가 조치를 말하는가** — `core/der/ess_schedule.py` 의 3요소 (R64/WP-8b).

`NFR-303` 은 입력 검증 오류가 **필드·사유·조치** 셋을 갖기를 요구한다. 그 셋 중
「조치」는 *「받은 사람이 할 수 있는 일」* 이어야 한다 — 할 수 있는 일이 0개인
문면은 형식만 3요소이고, 화면은 그것을 그대로 사람에게 보여 준다.

## 무엇이 문제였나 (R64/WP-4 · R64/WP-8b 실측)

가구 수를 3호 이상으로 적으면 낮에도 부하가 태양광을 넘어 `max(0, 발전 − 부하)`
가 하루 스물넷 전부 0 이 되고, `check_pv_surplus_profile` 이 *「충전원이 태양광
잉여인데 잉여 시계열이 없거나 전부 0입니다」* 로 거부한다. 종전 조치 문면은

    「pv_surplus_profile_kwh 에 시각별(0~23) PV 잉여 kWh 를 지정하십시오」

였다. **그 시계열은 러너가 만들어 넣는 것**이라(`core/casegrid/
seasonal_dispatch.py::_setup_one_season`) 화면·시나리오에 그것을 적는 칸이 없다 —
화면(`web/templates/dashboard.html` 의 「분석 실행」 폼)에 있는 것은 **가구 수 ·
히트펌프 부하 · 전기차 부하**이고, 조치가 그 어느 것도 말하지 않았다.

⛔ **거부 자체는 느슨해지지 않았다** — 그 불변을 이 파일이 함께 잰다. 한 해 내내
PV 잉여가 없는 단지에 태양광 연계 ESS 를 놓는 것은 사업 설계의 오류일 수 있고,
조용히 통과시키면 **없는 충전으로 편익이 난다.**
"""
from __future__ import annotations

import pytest

from core.contracts.validation import ValidationError
from core.der.ess_schedule import HOURS_PER_DAY, check_pv_surplus_profile

#: 화면(「분석 실행」 폼)이 실제로 갖는 입력 칸의 이름. ⚠ **화면에 없는 조치를
#: 조치라고 부르지 않기 위한 목록이며, 폼이 칸을 늘리면 여기도 늘어난다.**
_LEVERS_ON_THE_SCREEN: tuple[str, ...] = ("가구 수", "히트펌프", "전기차")


@pytest.mark.req("NFR-303-M1")
@pytest.mark.parametrize("profile", [None, [0.0] * HOURS_PER_DAY])
def test_the_empty_surplus_rejection_still_refuses(profile: list[float] | None) -> None:
    """★★ **거부는 그대로다** — 문면을 고쳤을 뿐 문턱을 옮기지 않았다.

    ⛔ 예외 인자를 달아 통과시키지 않았다(R64/WP-4 가 같은 판단을 이미 받았다).
    """
    with pytest.raises(ValidationError) as excinfo:
        check_pv_surplus_profile(profile, uses_pv_surplus=True, name="탐침")
    parts = excinfo.value.as_dict()
    assert parts["field"] == "ess.pv_surplus_profile_kwh"
    assert "없거나 전부 0" in parts["reason"]
    assert parts["rule"] is None


@pytest.mark.req("NFR-303-M1")
def test_the_action_names_something_the_screen_user_can_actually_do() -> None:
    """★★★ **조치가 화면에 있는 손잡이를 가리킨다.**

    화면 사용자가 할 수 있는 일은 부하를 줄이는 것(가구 수 · 히트펌프 · 전기차)
    이다. ⛔ **`pv_surplus_profile_kwh` 를 지정하라고 말하지 않는다** — 그 시계열은
    러너가 만드는 것이고 화면에 그 칸이 없다.
    """
    with pytest.raises(ValidationError) as excinfo:
        check_pv_surplus_profile(None, uses_pv_surplus=True, name="탐침")
    action = excinfo.value.as_dict()["action"]
    for lever in _LEVERS_ON_THE_SCREEN:
        assert lever in action, f"조치가 「{lever}」를 말하지 않는다: {action!r}"
    assert "pv_surplus_profile_kwh" not in action, (
        "조치가 화면에 없는 칸을 지정하라고 말한다"
    )


@pytest.mark.req("NFR-303-M1")
def test_the_action_offers_the_honest_way_out_not_a_silent_one() -> None:
    """★★ 잉여로 충전할 수 없는 구성이면 **충전원을 「계통」으로 바꾸라**고 말한다.

    ⛔ 저장소가 **몰래** 계통 충전으로 바꾸지 않는다 — 그러면 리포트의 「충전원:
    태양광 잉여」가 거짓이 된다. 바꾸는 것은 사용자의 선언이고, 바꾸면 산출물이
    그 사실을 인쇄한다. 조치는 그 길을 **알려 주기만** 한다.
    """
    with pytest.raises(ValidationError) as excinfo:
        check_pv_surplus_profile(None, uses_pv_surplus=True, name="탐침")
    action = excinfo.value.as_dict()["action"]
    assert "계통" in action
    assert "태양광 용량" in action


@pytest.mark.req("NFR-303-M1")
def test_the_other_two_rejections_keep_their_own_actions() -> None:
    """★ 형태 검사 나머지 둘의 조치는 **손대지 않았다.**

    그 둘(충전원=계통인데 시계열을 받음 · 행 수가 다름)은 **호출측이 실제로 고칠
    수 있는 것**을 이미 말한다 — 이 WP 가 고친 것은 빈 잉여 하나뿐이다.
    """
    with pytest.raises(ValidationError) as excinfo:
        check_pv_surplus_profile(
            [1.0] * HOURS_PER_DAY, uses_pv_surplus=False, name="탐침"
        )
    assert "charge_source" in excinfo.value.as_dict()["action"]

    with pytest.raises(ValidationError) as excinfo:
        check_pv_surplus_profile(
            [1.0] * (HOURS_PER_DAY - 1), uses_pv_surplus=True, name="탐침"
        )
    parts = excinfo.value.as_dict()
    assert f"{HOURS_PER_DAY}행이어야" in parts["reason"]
    assert f"{HOURS_PER_DAY}행 시계열" in parts["action"]
