"""**가구 수가 단지 총부하를 키운다** — 사용자 요구 1 (R64/WP-1 · 착수 47ⓐ).

사용자 문면: *「가구수를 변경할 수 있어야 함」*. 종전에는 바꿀 방법이 없었다 —
대장의 `load.household.annual` 이 **kWh/호·년**(한 호당)인데 러너가 그것을 단지
총량으로 그대로 썼기 때문이다.

## ★★★ 이 파일이 실제로 붙드는 것 — **안 준 실행이 종전과 같은가**

이 축에서 가장 위험한 것은 「가구 수를 키우는 것」이 아니라 **가구 수를 주지
않은 실행이 조용히 달라지는 것**이다. 배포 경로(골든 시나리오 셋)는 이 필드를
갖지 않으므로, 기본 갈래가 한 원이라도 움직이면 그것은 이 라운드가 결론축을
흔든 것이고 회귀 기준값 여섯이 전부 거짓이 된다.

⇒ 그래서 첫 검사가 **`household_count` 를 안 준 실행과 `None` 으로 준 실행이
같은 수를 낸다**이고, 그 위에서만 배수를 잰다. 파이프라인 전체의 동일성은
`tests/golden/test_regression_scenarios.py::
test_golden_scenarios_match_current_regression_snapshot` 이 `npv_won` 으로
잰다 — 이 파일은 **부하 자원 자체**를 재어 그 회귀가 왜 안 움직였는지를 말한다.

## ⚠ 값을 리터럴로 박지 않는다

기대 총부하는 대장 수준표(`build_level_map`)에서 읽어 곱해 만든다. 박으면
대장 판이 오르는 날 이 검사가 조용히 낡는다.

## ⚠ `req()` 마커를 달지 않았다 — **조항을 대조하고 내린 판정이다**

spec(`rslt/spec-분산특구-경제성평가.md`)에서 「가구수」는 **한 곳**에만
나오며(§ 화면 구조도의 *「Step 2. 사업모델 개요 (지역·대상 가구수·계약구조)」*)
그것은 수용기준이 아니라 **화면 구조 그림**이다. 가까워 보이는 ID 를 짐작해
붙이면 `docs/traceability.md` 에 *「이 조항이 검증됐다」* 는 거짓 인용이 실린다
— `tests/casegrid/test_household_load_gate.py`·`tests/app/test_ui_verify.py` 가
같은 자리에서 같은 판정을 적었다. 조항 신설은 spec 개정이므로 사람 몫이다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.household_scale import household_scale, resolve_household_count
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.profiles import load_daily_shapes
from core.contracts.validation import ValidationError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_LOAD = "e2e-load"

#: 단지 총부하가 커져도 **태양광 잉여가 남는** 규모. 셋 이상이면 잉여가 말라
#: 잉여 충전 ESS 가 `core/der/ess.py` 에서 거부된다 — 그것은 이 축의 결함이
#: 아니라 **설비 용량이 가구 수를 따라 자동으로 커지지 않는다**는 사실이며,
#: 크기를 함께 정하는 것은 값이 도착한 뒤의 일이다(대장 `load.household.count`
#: 의 `impact_note` 가 그 실측을 적는다).
_COUNT = 2


def _levels() -> dict[str, dict[str, float]]:
    return build_level_map(_ASSUMPTIONS)


def _annual_kwh(levels: dict[str, dict[str, float]]) -> float:
    return levels["household_load_annual_kwh"]["base"]


def _daily_load_kwh(outcome: object) -> float:
    """대표일 하루의 가구 소비(kWh) — **부호를 뒤집어** 양수로 낸다.

    부하는 디스패치에서 음수(소비)로 서므로 그대로 더하면 음수다.
    """
    return -sum(outcome.dispatch.per_resource[_LOAD].electric)  # type: ignore[attr-defined]


def _run(levels: dict[str, dict[str, float]], **extra: object):
    return run_single_case_e2e(
        {},
        level_map=levels,
        horizon_years=20,
        daily_shapes=load_daily_shapes(),
        annual_load_kwh=_annual_kwh(levels),
        **extra,  # type: ignore[arg-type]
    )


def test_not_giving_a_count_is_the_same_run_as_giving_none() -> None:
    """★★★ **미지정이 기본이고, 그때 수가 한 원도 움직이지 않는다.**

    인자를 아예 넘기지 않은 실행과 `household_count=None` 으로 넘긴 실행이
    **원소 하나까지** 같아야 한다. 여기가 어긋나면 골든 회귀 여섯이 전부
    거짓이 되고, 그 어긋남은 「가구 수 축을 열었다」가 아니라 **결론축을
    말없이 옮겼다**는 뜻이다.
    """
    levels = _levels()
    without = _run(levels)
    explicit_none = _run(levels, household_count=None)
    assert without.variants == explicit_none.variants, (
        "가구 수를 안 준 실행과 None 으로 준 실행의 지표가 다르다 — "
        "기본 갈래가 움직였다"
    )
    assert _daily_load_kwh(without) == _daily_load_kwh(explicit_none)


def test_one_household_is_the_same_as_unspecified() -> None:
    """★★ **`1` 은 미지정과 같은 수를 낸다** — 배수 1 이 항등이다.

    이 단언이 없으면 위 검사는 *「곱셈이 아예 안 걸렸다」* 로도 통과한다.
    """
    levels = _levels()
    assert _daily_load_kwh(_run(levels, household_count=1)) == pytest.approx(
        _daily_load_kwh(_run(levels)), abs=1e-9
    )


def test_the_site_load_grows_by_exactly_the_count() -> None:
    """★★★ **단지 총부하 = 가구 수 × 한 호의 총부하** — 정확히 배수다.

    ⚠ 기대값을 리터럴로 적지 않는다. 미지정 실행의 대표일 소비를 재고 거기에
    `_COUNT` 를 곱한 것이 기대값이다 — 대장 판이 올라도 이 검사는 산다.
    """
    levels = _levels()
    one = _daily_load_kwh(_run(levels))
    many = _daily_load_kwh(_run(levels, household_count=_COUNT))
    assert many == pytest.approx(one * _COUNT, rel=1e-12), (
        f"{_COUNT}호 단지의 대표일 소비가 {many}kWh 다 — 한 호의 {one}kWh 의 "
        f"{_COUNT}배가 아니다"
    )


def test_the_shape_does_not_move_with_the_count() -> None:
    """★★ **형상은 가구 수와 무관하다** — 총량만 커지고 하루의 모양은 그대로.

    형상은 합이 1 인 배분 벡터이므로 스텝별 몫이 배수와 무관해야 한다. 형상이
    함께 움직이면 계절 축(착수 순서 36번)이 그 위에 설 수 없다 — 그때 「가구
    수를 늘렸더니 저녁 봉우리가 옮겨갔다」가 되고, 그것을 설명할 근거가 없다.
    """
    levels = _levels()
    one = _run(levels).dispatch.per_resource[_LOAD].electric
    many = _run(levels, household_count=_COUNT).dispatch.per_resource[_LOAD].electric
    assert len(one) == len(many)
    for step, (single, scaled) in enumerate(zip(one, many, strict=True)):
        assert scaled == pytest.approx(single * _COUNT, rel=1e-12), (
            f"{step}스텝의 몫이 배수와 다르다 — 형상이 함께 움직였다"
        )


def test_the_extra_appliance_is_per_household_so_it_is_added_before_scaling() -> None:
    """★★ **추가 기기 소비량은 「호당」이다** — 더한 뒤에 곱한다 (판정 §2 ②).

    근거는 대장이다: `load.household.annual` 의 `applicable_scope` 가 *「그
    기기의 연간 소비전력량을 **이 값에 더해** 총량이 비례 증가하는 형태여야
    한다」* 라고 적고, 그 「이 값」의 단위가 **kWh/호·년** 이다.

    ⚠ 곱한 뒤에 더하면 **추가 기기가 단지에 딱 한 대 있는 사업**이 되고, 그
    실행은 「모든 가구에 히트펌프를 놓았다」와 산출물에서 구별되지 않는다.
    """
    levels = _levels()
    extra = 1_000.0
    scaled = _daily_load_kwh(
        _run(levels, extra_appliance_load_kwh=extra, household_count=_COUNT)
    )
    per_household = _daily_load_kwh(_run(levels, extra_appliance_load_kwh=extra))
    assert scaled == pytest.approx(per_household * _COUNT, rel=1e-12), (
        "추가 기기를 곱하지 않았다 — 단지 총량으로 다룬 것이며 대장의 "
        "`applicable_scope` 와 어긋난다"
    )


@pytest.mark.parametrize("bad", [0, -1, True, 40.5, "40.5", "", " ", "abc", "-3"])
def test_a_count_that_is_not_a_whole_number_of_households_is_refused(
    bad: object,
) -> None:
    """★★ **1 이상의 정수만 가구 수다** — 그 밖은 3요소로 거부한다 (`NFR-303`).

    ⚠ `True` 가 목록에 있는 이유: 파이썬에서 `bool` 은 `int` 의 하위형이라
    막지 않으면 *「가구 수 = 참」* 이 **1호**로 조용히 통과한다.

    ⚠ 빈 문자열 둘(`""`·`" "`)은 **거부가 아니라 「적지 않았다」**이므로 여기서
    갈라 단언한다 — 화면의 빈 칸이 그 모양으로 내려온다.
    """
    if isinstance(bad, str) and not bad.strip():
        assert resolve_household_count(bad) is None
        return
    with pytest.raises(ValidationError, match="가구 수"):
        resolve_household_count(bad)


def test_the_scale_of_an_unspecified_count_is_one() -> None:
    """★ 미지정의 배수는 **1** 이다 — 「곱하지 않는다」가 아니라 「1을 곱한다」."""
    assert household_scale(None) == 1
    assert household_scale(7) == 7


def test_a_digit_string_is_read_as_a_count() -> None:
    """★ 화면이 GET 질의로 보내는 것은 **문면**이다 — `"40"` 이 40호다.

    폼이 보낼 수 있는 모양은 빈 칸과 숫자 문면 둘뿐이며(`app/routers/ui.py::
    run_case` 의 `arrangement` 가 같은 규약을 따른다), 그 변환을 라우터가 아니라
    **판정하는 자리 하나**가 한다.
    """
    assert resolve_household_count("40") == 40
