"""**계절별로 냉난방수요를 차등하여 설정한다** — 사용자 요구 3 (R64/WP-3b-1).

사용자 문면(`docs/decisions-2026-09-06-R64.md` §0 3항): *「계절별로 냉난방수요를
차등하여 설정할 수 있어야 함」*. 요구의 절반(**운전이 계절을 안다**)은 R64/WP-4
가 닫았고, 이 파일이 재는 것은 나머지 절반 **「차등하여 설정한다」** 다.

## 종전에 무엇이 없었나 — 이 파일이 붙드는 것의 정체

히트펌프·전기차 부하는 러너에 **합계 하나**로 들어가 `annual_load_kwh` 와
**먼저 합쳐진 뒤** 자산이 선언한 **기본 부하의 계절 몫**으로 나뉘었다
(`core/casegrid/seasonal_dispatch.py::_season_inputs`). 그러므로 계절 `i` 의
부하 총량은 `(기본 + 냉난방) × 기본몫[i]` 였고 **냉난방 몫이 기본 몫과 강제로
같았다** — 곧 「차등할 자리가 없었다」.

## 재는 것 셋 — **하나만 재면 빈 구현이 통과한다**

    ① 동치   몫을 주지 않은 실행이 종전과 **원소 하나까지** 같다
    ② 차등   다른 몫을 준 계절의 **부하 총량이 실제로 갈린다** (수치를 꺼내 본다)
    ③ 거부   합 ≠ 1 · 자산과 다른 달력이 **거부**된다 — 고쳐 주지 않는다

①이 빠지면 이 축이 골든 셋을 조용히 움직인다. ②를 「예외 없이 돌았다」로
만족하면 *「인자를 나르기만 하고 계산에 안 쓴다」* 가 통과한다 — 이 저장소가
반복해 만난 「표시만 하는 구현」이다. ③이 빠지면 0.9 를 적은 실행에서 연간
에너지의 10%가 아무 말 없이 사라진다.

## ⚠ 계절 이름·개수를 이 파일에 박지 않는다

자산 머리말이 *「일수는 계절 수를 4로 못 박지 않는다 — 적은 개수를 그대로
쓴다」* 로 못 박았다. 그래서 아래 모든 몫은 **자산이 선언한 이름에서** 짓는다 —
박으면 자산을 월별(12)로 넓히는 날 이 검사가 조용히 낡는다.

## ⚠ 화면은 이 파일이 재지 않는다 — **다음 WP 의 몫이다**

거부는 러너·검증 층의 판정이고 화면은 그것을 **보여줄 뿐**이다. 여기서는
파이썬 층의 예외 객체로 재고(`ValidationError` 의 3요소), 그 문면이 화면에서
읽히는지는 다음 WP(`WP-WEB`)가 잇는다 — 사용자 지시로 웹을 한 WP 로 모았다.

## ⚠ `req()` 마커를 달지 않았다

spec 에 「계절별 냉난방 부하 차등」을 요구하는 수용기준이 없다. 가까워 보이는
ID 를 짐작해 붙이면 `docs/traceability.md` 에 거짓 인용이 실린다 — 사유는
`tests/casegrid/test_appliance_load.py` 머리말이 갖는다.
"""
from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import pytest

from core.assumption.provider import AssumptionSet
from core.casegrid.appliance_load import (
    APPLIANCE_SEASON_SHARE_FIELD,
    APPLIANCE_SEASON_SHARE_FIELD_KEY,
    EV_LOAD_FIELD,
    EV_LOAD_LEDGER_KEY,
    HEATPUMP_LOAD_FIELD,
    HEATPUMP_LOAD_LEDGER_KEY,
    ApplianceDailyShape,
    ApplianceDailyShapes,
    ApplianceLoads,
    ApplianceSeasonShares,
    asset_appliance_daily_shapes,
    asset_appliance_season_shares,
    resolve_appliance_loads,
    resolve_appliance_season_shares,
    with_ledger_defaults,
)
from core.casegrid.e2e_runner import DAYS_PER_YEAR, run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.models import CaseOutcome
from core.casegrid.profiles import (
    PROFILE_PATH,
    SHARE_TOLERANCE,
    DailyShape,
    load_daily_shapes,
    weights_from_hour_ranges,
)
from core.contracts.validation import ValidationError
from tests.casegrid.test_seasonal_dispatch_run import _ASSUMPTIONS, _load_kwh

#: 시험용 냉난방 부하(kWh/호·년). **참고자료의 값을 박지 않는다** — 사유는
#: `tests/casegrid/test_appliance_load.py::_HEATPUMP` 가 갖는다. 이 수가
#: 하는 일은 「기본 부하와 견줄 만큼 크다」 하나이며 사업 전망이 아니다.
_HEATPUMP = 3000.0

#: 마지막 계절에 몰아 주는 몫. 자산이 그 계절에 적은 몫보다 **커야** 차등의
#: 방향이 정해진다 — 아래 `_winter_heavy` 가 그것을 단언으로 붙든다.
_HEAVY = 0.7

#: 시험용 전기차 부하(kWh/호·년). 위 `_HEATPUMP` 와 같은 규약이며 — 이 수가
#: 하는 일은 **「히트펌프와 견줄 만큼 커서 `ev_ratio` 가 0 도 1 도 아니다」**
#: 하나다. 대장의 조사값(2,784)을 박지 않는 사유도 그쪽과 같다.
_EV = 2000.0


def _load_shape() -> DailyShape:
    """배포 자산의 **부하 형상**. 이름·개수를 여기서 세지 않는다."""
    return load_daily_shapes().load


def _season_names() -> list[str]:
    return [season.name for season in _load_shape().seasons]


def _winter_heavy() -> dict[str, float]:
    """**마지막 계절에 몰아 준** 몫 하나 — 합이 1 이다.

    ⚠ 「겨울」을 이름으로 박지 않는다. 자산이 적은 **마지막 계절**을 집고,
    그 계절에 자산이 적어 둔 몫보다 큰 값을 준다 — 그래야 *「그 계절의 부하가
    늘어야 한다」* 가 자산과 무관하게 성립한다.
    """
    names = _season_names()
    declared = {s.name: s.share for s in _load_shape().seasons}
    assert declared[names[-1]] < _HEAVY, (
        f"자산이 {names[-1]!r} 에 적은 몫이 {declared[names[-1]]!r} 로 이미 "
        f"{_HEAVY} 이상이다 — 이 시험의 차등 방향이 정해지지 않는다"
    )
    rest = (1.0 - _HEAVY) / (len(names) - 1)
    return {name: (_HEAVY if name == names[-1] else rest) for name in names}


def _run(shares: object | None, *, heatpump: float = _HEATPUMP) -> CaseOutcome:
    """배포 자산·대장으로 러너를 그대로 돌린다 — 자원을 손으로 세우지 않는다."""
    return run_single_case_e2e(
        {},
        level_map=build_level_map(_ASSUMPTIONS),
        horizon_years=20,
        daily_shapes=load_daily_shapes(),
        annual_load_kwh=_load_kwh(),
        extra_appliance_load_kwh=heatpump,
        appliance_season_shares=resolve_appliance_season_shares(shares),
    )


def _season_load(outcome: CaseOutcome) -> dict[str, float]:
    """계절 → 그 계절이 한 해에 쓰는 부하(kWh, **양수**).

    `per_resource_annual_kwh` 의 부호 규약은 `DispatchResult` 그대로라
    부하가 음수다(받아들임). 표로 읽으려고 뒤집을 뿐이며, 뒤집는 자리를
    한 곳에 둔다.
    """
    return {
        season.name: -season.per_resource_annual_kwh["e2e-load"]
        for season in outcome.seasons
    }


def _table(before: dict[str, float], after: dict[str, float]) -> str:
    """실패 문면이 **수를 그대로 보이게** 한다 — 「달랐다」만으로는 못 고친다."""
    return "\n".join(
        f"  {name:<6} {before[name]:>14,.1f} → {after[name]:>14,.1f} kWh/년"
        for name in before
    )


# ── ① 동치 — 몫을 주지 않은 실행이 종전과 같다 ─────────────────────────────


def test_no_shares_takes_the_untouched_path_element_for_element() -> None:
    """★★★ **몫이 없으면 자산의 메서드를 그대로 부른다** — 다시 계산하지 않는다.

    새 식으로 「같은 값이 나오도록」 계산하면 두 식이 부동소수 마지막 자리에서
    갈릴 수 있고, 그러면 몫을 주지 않은 실행(골든 셋 전부)이 조용히 움직인다.
    그래서 `pytest.approx` 가 아니라 **`==`** 로 잰다.
    """
    shape = _load_shape()
    total = _load_kwh()
    assert ApplianceSeasonShares.load_days(
        shape, total, None, days=DAYS_PER_YEAR
    ) == shape.representative_day_by_season(total, days=DAYS_PER_YEAR)
    assert ApplianceSeasonShares.folded_year(
        shape, total, None, days=DAYS_PER_YEAR
    ) == shape.spread_over_representative_day(total, days=DAYS_PER_YEAR)


def test_shares_equal_to_the_asset_reproduce_the_undifferentiated_run() -> None:
    """★★★ **자산의 몫을 그대로 적으면 종전과 같은 사업이 된다.**

    위 검사는 *「갈래를 안 탄다」* 를 재고 이것은 *「새 식이 옛 식의 일반화다」*
    를 잰다 — 둘은 다른 진술이다. 새 식이 틀렸어도 앞의 검사는 초록불이다
    (몫을 안 주면 그 식을 지나지 않으므로).
    """
    declared = {s.name: s.share for s in _load_shape().seasons}
    plain = _season_load(_run(None))
    same = _season_load(_run(declared))
    for name, want in plain.items():
        assert same[name] == pytest.approx(want, rel=1e-12), (
            f"자산이 적은 몫을 그대로 줬는데 {name!r} 의 연간 부하가 "
            f"{same[name]:,.4f} 다 (기대 {want:,.4f})\n{_table(plain, same)}"
        )


# ── ② 차등 — 계절별 부하 총량이 실제로 갈린다 ──────────────────────────────


def test_moving_the_heating_load_into_one_season_moves_that_season_s_load() -> None:
    """★★★★ **몫을 바꾸면 계절별 부하 총량이 실제로 갈린다** (WP-3b §5-2).

    「예외 없이 돌았다」로 만족하지 않는다 — 계절별 수치를 꺼내 대조하고,
    갈리지 않으면 그 표를 실패 문면에 그대로 싣는다.

    재는 것 둘:
      ⓐ 몰아 준 계절의 연간 부하가 **늘어난다**
      ⓑ 그 밖의 계절은 **줄어든다** ← 대조군. 없으면 ⓐ 는 「부하가 통째로
        늘었다」(총량이 변했다)와 구별되지 않는다
    """
    heavy = _winter_heavy()
    moved = max(heavy, key=lambda name: heavy[name])
    plain = _season_load(_run(None))
    after = _season_load(_run(heavy))
    assert after[moved] > plain[moved], (
        f"{moved!r} 에 몫 {heavy[moved]} 를 몰아 줬는데 그 계절의 연간 부하가 "
        f"늘지 않았다\n{_table(plain, after)}"
    )
    for name in plain:
        if name == moved:
            continue
        assert after[name] < plain[name], (
            f"{moved!r} 로 옮겼는데 {name!r} 의 부하가 줄지 않았다 — 총량이 "
            f"보존되지 않았다는 뜻이다\n{_table(plain, after)}"
        )


def test_the_annual_total_does_not_move_when_the_seasons_do() -> None:
    """★★★ **총량은 한 kWh 도 변하지 않는다** — 계절 사이에서 옮겨갈 뿐이다.

    몫의 합이 1 이라는 규약이 뜻하는 것이 이것이고, 이 성질이 깨지면 위
    「차등」 검사는 *「부하를 더 얹었다」* 로도 통과한다.
    """
    plain = _season_load(_run(None))
    after = _season_load(_run(_winter_heavy()))
    assert math.fsum(after.values()) == pytest.approx(
        math.fsum(plain.values()), rel=1e-9
    ), (
        f"연간 부하 총량이 {math.fsum(plain.values()):,.1f} 에서 "
        f"{math.fsum(after.values()):,.1f} 로 움직였다\n{_table(plain, after)}"
    )


def test_the_annual_equivalent_day_uses_the_same_split_as_the_seasons() -> None:
    """★★★ **인쇄하는 하루와 계절별 하루가 같은 분해 위에 선다.**

    러너는 계절별 하루와 별도로 「일수 가중 평균 하루」한 벌을 세우고, 연간등가
    배터리가 그 하루를 따라간다(`core/casegrid/seasonal_dispatch.py` 머리말
    ★★★). 두 자리가 다른 식으로 서면 **리포트가 인쇄하는 하루와 배터리가
    따라가는 하루가 갈리는데, 그 어긋남은 아무 예외도 내지 않는다.**

        연간등가 하루[j] × 365 == Σ_계절 ( 그 계절 하루[j] × 계절일수 )

    ⚠ 러너가 그 두 하루를 짓는 자리(`_household_load_if_total_given` ·
    `_season_inputs`)가 부르는 **두 함수를 같은 인자로** 부른다 — 항등식이
    성립하는 곳은 그 둘 사이이며, 운전 결과에서 재면 엔진이 함께 섞인다.
    """
    shape = _load_shape()
    base = _load_kwh()
    total = base + _HEATPUMP
    shares = ApplianceSeasonShares.of(
        ApplianceSeasonShares(by_season=tuple(_winter_heavy().items())),
        base,
        _HEATPUMP,
    )
    folded = ApplianceSeasonShares.folded_year(
        shape, total, shares, days=DAYS_PER_YEAR
    )
    by_season = ApplianceSeasonShares.load_days(
        shape, total, shares, days=DAYS_PER_YEAR
    )
    for step in range(shape.steps):
        want = math.fsum(day[step] * days for _s, day, days in by_season)
        got = folded[step] * DAYS_PER_YEAR
        assert got == pytest.approx(want, rel=1e-9), (
            f"스텝 {step}: 연간등가 하루의 365배가 {got:,.6f} 인데 계절별 "
            f"기여의 합은 {want:,.6f} 다 — 두 하루가 다른 분해 위에 섰다"
        )
    assert math.fsum(folded) == pytest.approx(total, rel=1e-9), (
        f"연간등가 시계열의 합이 {math.fsum(folded):,.4f} 다 (기대 {total:,.4f})"
    )


# ── ③ 거부 — 고쳐 주지 않는다 ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "shares",
    [
        pytest.param({"봄": 0.3, "여름": 0.3, "가을": 0.2, "겨울": 0.1}, id="합 0.9"),
        pytest.param({"봄": 0.3, "여름": 0.3, "가을": 0.3, "겨울": 0.3}, id="합 1.2"),
    ],
)
def test_shares_that_do_not_sum_to_one_are_refused(shares: dict[str, float]) -> None:
    """★★★ **합이 1 이 아니면 거부한다** — 정규화하지 않는다.

    자산 머리말의 `share` 규약 그대로다: *「0.9 를 적으면 연간 에너지의 10%가
    사라지므로 고쳐 주지 않고 거부한다」*. 정규화하면 「자산이 틀렸다」와
    「이렇게 쓰기로 했다」가 구별되지 않는다.
    """
    with pytest.raises(ValidationError) as raised:
        resolve_appliance_season_shares(shares)
    assert raised.value.field == APPLIANCE_SEASON_SHARE_FIELD_KEY
    assert "1 이어야 합니다" in raised.value.reason
    assert raised.value.action


def test_a_calendar_that_does_not_match_the_asset_is_refused() -> None:
    """★★★ **자산과 다른 계절 이름은 거부한다** — 짐작해 맞추지 않는다.

    이름이 다르면 **같은 몫이 다른 날에 걸린다.** 자산 머리말이 부하·발전
    달력에 대해 못 박은 것과 같은 규칙이며(*「읽는 쪽이 거부한다」*), 차례로
    맞추면 사용자가 계절을 적는 순서만 바꿔도 겨울 몫이 봄에 걸린다.
    """
    names = _season_names()
    renamed = {f"{name}철": 1.0 / len(names) for name in names}
    with pytest.raises(ValidationError) as raised:
        _run(renamed)
    assert raised.value.field == APPLIANCE_SEASON_SHARE_FIELD_KEY
    assert all(name in raised.value.reason for name in names)
    assert raised.value.action


def test_a_calendar_with_the_wrong_number_of_seasons_is_refused() -> None:
    """★★ **계절 개수가 자산과 다르면 거부한다** — 남은 계절이 조용히 0 이 된다.

    ⚠ 개수만 보고 판정하지 않는다(이름을 함께 본다) — 개수만 맞추면 자산이
    월별로 넓혀진 날 이름이 어긋난 채로 통과한다.
    """
    names = _season_names()
    short = {name: 1.0 / (len(names) - 1) for name in names[:-1]}
    with pytest.raises(ValidationError, match="달력"):
        _run(short)


def test_a_duplicate_season_name_is_refused() -> None:
    """★ 같은 계절을 두 번 적은 몫은 거부한다.

    매핑으로 오면 생길 수 없지만 자료형은 직접 세울 수 있고, 그때 `dict()` 가
    **뒤의 것으로 덮어** 합 검사를 지난 몫이 조용히 달라진다.
    """
    names = _season_names()
    duplicated = ApplianceSeasonShares(
        by_season=tuple([(names[0], 0.5), (names[0], 0.5)])
    )
    with pytest.raises(ValidationError, match="달력"):
        ApplianceSeasonShares.load_days(
            _load_shape(), _load_kwh(), duplicated, days=DAYS_PER_YEAR
        )


def test_a_partly_filled_calendar_is_refused() -> None:
    """★★ **일부만 적은 것은 거부한다** — 빈 칸을 0 으로 읽지 않는다.

    빈 칸을 0 으로 읽으면 그 계절의 냉난방이 통째로 사라지는데, 사용자는
    *「아직 안 적었다」* 를 뜻했을 수 있다. 둘을 가를 수 없으므로 묻는다.
    """
    names = _season_names()
    partial: dict[str, object] = {name: "" for name in names}
    partial[names[0]] = 1.0
    with pytest.raises(ValidationError) as raised:
        resolve_appliance_season_shares(partial)
    assert names[-1] in raised.value.reason


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(-0.5, id="음수"),
        pytest.param(True, id="참(bool 은 int 의 하위형이다)"),
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="inf"),
        pytest.param("스물", id="수가 아닌 글자"),
        pytest.param(object(), id="수도 글자도 아닌 것"),
    ],
)
def test_a_share_that_is_not_a_non_negative_number_is_refused(bad: object) -> None:
    """★★ 칸 하나가 수가 아니면 거부한다 — `resolve_appliance_load` 와 같은 엄격함.

    판정 자체는 `_non_negative` 하나가 지고 갈리는 것은 문면뿐이다. `bool` 을
    막는 이유는 파이썬에서 `True` 가 `int` 의 하위형이라 그냥 두면 **몫 1.0**
    으로 조용히 통과하기 때문이다.
    """
    names = _season_names()
    shares: dict[str, object] = {name: 0.25 for name in names}
    shares[names[0]] = bad
    with pytest.raises(ValidationError) as raised:
        resolve_appliance_season_shares(shares)
    assert raised.value.field == APPLIANCE_SEASON_SHARE_FIELD_KEY


def test_a_value_that_is_not_a_mapping_is_refused() -> None:
    """★ 계절 이름이 붙지 않은 나열은 거부한다.

    차례로 맞추면 위 「달력」 검사가 막으려는 어긋남이 검사 없이 통과한다.
    """
    with pytest.raises(ValidationError, match="매핑"):
        resolve_appliance_season_shares([0.25, 0.25, 0.25, 0.25])


# ── ④ 미지정 — 「적지 않았다」가 기본이다 ──────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(None, id="필드가 없다"),
        pytest.param({}, id="빈 매핑"),
        pytest.param({"봄": "", "여름": None, "가을": "  ", "겨울": ""}, id="칸이 전부 비었다"),
    ],
)
def test_an_unspecified_calendar_is_not_an_error(value: object) -> None:
    """★★★ **비우면 미지정이다** — 그때 냉난방이 기본 부하와 같은 몫으로 돈다.

    이것이 이 라운드 전의 유일한 갈래이며, 그 갈래로 도는 실행은 이 배선이
    생기기 전과 원소 하나까지 같다(위 ① 검사).
    """
    assert resolve_appliance_season_shares(value) is None


def test_an_already_resolved_value_passes_through() -> None:
    """★ 이미 세워진 자료형은 그대로 통과한다 — 층마다 다시 파싱하지 않는다."""
    built = ApplianceSeasonShares(by_season=tuple(_winter_heavy().items()))
    assert resolve_appliance_season_shares(built) is built


def test_the_scenario_field_is_the_only_channel() -> None:
    """★★ 시나리오 필드 하나가 통로다 — 두 필드와 같은 규약이다.

    통로가 둘이면 어느 것이 이겼는지 산출물에서 알 수 없다
    (`core/casegrid/appliance_load.py::HEATPUMP_LOAD_FIELD` 의 ⚠ 절).
    """
    heavy = _winter_heavy()
    loads = resolve_appliance_loads({
        HEATPUMP_LOAD_FIELD: _HEATPUMP,
        EV_LOAD_FIELD: 100.0,
        APPLIANCE_SEASON_SHARE_FIELD: heavy,
    })
    assert loads.season_shares is not None
    assert dict(loads.season_shares.by_season) == heavy
    assert resolve_appliance_loads({}).season_shares is None


def test_the_ratios_are_zero_when_there_is_no_load_to_split() -> None:
    """★★ **나눌 부하가 없으면 몫이 아무 수도 움직이지 않는다.**

    부하를 세우지 않는 실행(`annual_load_kwh is None`)과 총량이 0 인 실행이
    그렇다 — 그때 옮길 에너지 자체가 없어 어떤 몫을 적어도 결과가 같다.
    `core/casegrid/seasonal_dispatch.py::_appliance_ratio` 가 「AI 가전」축에서
    같은 판단을 적었다.
    """
    built = ApplianceSeasonShares(by_season=tuple(_winter_heavy().items()))
    empty = ApplianceSeasonShares.of(built, None, 0.0)
    assert empty is not None
    assert (empty.base_ratio, empty.appliance_ratio) == (1.0, 0.0)
    assert ApplianceSeasonShares.of(None, 1000.0, 100.0) is None
    filled = ApplianceSeasonShares.of(built, 900.0, 100.0)
    assert filled is not None
    assert filled.appliance_ratio == pytest.approx(0.1)
    assert filled.base_ratio == pytest.approx(0.9)


def test_a_run_with_no_appliance_load_is_unmoved_by_any_calendar() -> None:
    """★★★ **얹은 기기가 없으면 몫이 결론을 못 움직인다** — 나눌 것이 없다.

    이 성질이 없으면 계절 몫이 **기본 부하까지** 다시 나누고 있다는 뜻이며,
    그것은 자산이 정한 계절 몫을 화면이 덮어쓰는 것이다(자산은 화면에서 못
    고친다 — WP-3b §2 갈래 B 기각 사유의 반대 방향 위반).
    """
    plain = _season_load(_run(None, heatpump=0.0))
    after = _season_load(_run(_winter_heavy(), heatpump=0.0))
    for name, want in plain.items():
        assert after[name] == pytest.approx(want, rel=1e-12), (
            f"기기 부하가 0 인데 {name!r} 의 부하가 움직였다\n"
            f"{_table(plain, after)}"
        )


# ── ⑤ 기기별 배분 — **전기차에는 냉난방 몫을 씌우지 않는다** (R67/WP-N1) ────
#
# 위 ①~④ 가 재는 것은 *「합계 하나가 계절마다 갈린다」* 까지다. 그런데 그
# 합계는 **히트펌프 + 전기차**이고 자산이 적은 몫은 **히트펌프의 것**이라,
# 그대로 쓰면 히트펌프의 겨울 몫이 전기차 충전에도 씌워진다 — 전기차는 통상
# 심야·**연중 고른 충전**이므로 그때 겨울 부하가 과대해지고, 그 위에서 역산한
# 겨울 ESS 필요 용량이 부풀려진다. 자산 파일이 그 결손을 스스로 적어 두었다
# (`appliance_season_shares` 의 `derivation_method` 안 ⚠⚠ 절).


def _asset_shares() -> ApplianceSeasonShares:
    """배포 자산이 선언한 **냉난방** 계절 몫. 값을 여기 박지 않는다."""
    shares = asset_appliance_season_shares()
    assert shares is not None, (
        "배포 자산에 `appliance_season_shares:` 절이 없다 — 이 아래 검사들이 "
        "재는 것은 그 절이 있는 실행이다"
    )
    return shares


def _day_share() -> dict[str, float]:
    """자산 달력의 **일수 비례 몫** — 시험도 자산에서 «그 자리에서» 나눈다.

    ⚠ `0.2521` 처럼 네 자리로 끊어 적으면 합이 `1.0001` 이 되어
    `SHARE_TOLERANCE`(1e-9)를 넘고, 무엇보다 자산이 달력을 고치는 날 이 검사만
    낡는다 — 구현이 하는 것과 **같은 나눗셈**을 여기서도 한다.
    """
    seasons = _load_shape().seasons
    total = float(sum(season.days or 0 for season in seasons))
    return {season.name: (season.days or 0) / total for season in seasons}


def _effective(shares: ApplianceSeasonShares) -> dict[str, float]:
    """그 몫이 **계절마다 실제로 걸리는 값** — 형상과 맞춰 꺼낸다.

    ⚠ `_matched` 는 계절마다 **성분 목록**을 낸다(R67/WP-N1b — 기기마다 하루
    안의 형상이 다르다). 이 함수가 묻는 것은 *계절* 축이므로 그 계절의 성분
    몫을 **더한다** — 성분이 하나뿐인 실행(기기 형상 절이 없는 자산)에서도
    같은 수가 나온다.
    """
    shape = _load_shape()
    return {
        season.name: math.fsum(share for _weights, share in components)
        for season, components in zip(
            shape.seasons, shares._matched(shape), strict=True
        )
    }


def test_the_ev_ratio_is_the_ev_slice_of_the_appliance_load() -> None:
    """★★★ `ev_ratio` 는 **전기차 ÷ (히트펌프 + 전기차)** 이고 분모 0 이면 0.0 이다.

    ⚠ **`None`(적지 않았다)과 `0.0`(없다고 적었다)이 여기서는 같은 수를 낸다** —
    둘 다 더해지는 값이 0 이므로 *비중*도 0 이다. 둘을 가르는 것은 산출물의
    문면(`any_specified`)이고 그 판정은 이 속성이 지지 않는다.
    """
    assert ApplianceLoads(heatpump_kwh=300.0, ev_kwh=100.0).ev_ratio == pytest.approx(0.25)
    assert ApplianceLoads(heatpump_kwh=None, ev_kwh=None).ev_ratio == 0.0
    assert ApplianceLoads(heatpump_kwh=0.0, ev_kwh=0.0).ev_ratio == 0.0
    assert ApplianceLoads(heatpump_kwh=None, ev_kwh=0.0).ev_ratio == 0.0
    assert ApplianceLoads(heatpump_kwh=None, ev_kwh=_EV).ev_ratio == 1.0
    assert ApplianceLoads(heatpump_kwh=0.0, ev_kwh=_EV).ev_ratio == 1.0
    # ⚠ 몫을 안 적은 실행은 도장 찍을 것이 없다 — `None` 그대로여야 러너가
    # 종전 식을 지난다(위 ① 검사).
    assert ApplianceLoads(heatpump_kwh=_HEATPUMP, ev_kwh=_EV).blended_season_shares is None


def test_a_run_without_an_ev_is_element_for_element_what_it_was() -> None:
    """★★★★ **전기차가 없으면 오늘과 원소 하나까지 같다** (동일성 · 합격 조건).

    `None`(적지 않았다)과 `0.0`(없다고 적었다) 둘 다 그렇다. 섞는 식을 지나며
    「같은 값이 나오도록」 다시 계산하면 부동소수 마지막 자리가 갈릴 수 있고,
    그러면 전기차를 적지 않은 실행이 조용히 움직인다 — 그래서 `pytest.approx`
    가 아니라 **`==`** 로 잰다(위 ① 검사와 같은 사유).
    """
    asset = _asset_shares()
    shape = _load_shape()
    baseline = asset._matched(shape)
    for ev in (None, 0.0):
        stamped = ApplianceLoads(
            heatpump_kwh=_HEATPUMP, ev_kwh=ev, season_shares=asset
        ).blended_season_shares
        assert stamped is not None
        assert stamped._matched(shape) == baseline, (
            f"전기차가 {ev!r} 인데 계절 몫이 움직였다 — 그 실행은 오늘과 원소 "
            f"하나까지 같아야 한다\n  오늘 {[s for _w, s in baseline]}\n"
            f"  지금 {[s for _w, s in stamped._matched(shape)]}"
        )
    # 운전까지 내려가도 같다 — 위 단언은 몫 하나만 보고, 이것은 러너가 그 몫으로
    # 실제로 돌린 결과를 본다.
    plain = _season_load(_run(asset))
    same = _season_load(
        _run(
            ApplianceLoads(
                heatpump_kwh=_HEATPUMP, ev_kwh=0.0, season_shares=asset
            ).blended_season_shares
        )
    )
    assert same == plain, f"전기차가 0 인 실행이 움직였다\n{_table(plain, same)}"


def test_the_ev_pulls_the_heaviest_season_down_towards_the_day_count() -> None:
    """★★★★ **히트펌프와 전기차가 둘 다 있으면 겨울 몫이 «작아진다»** (WP-N1 §4-2).

    재는 것 셋:
      ⓐ 섞인 몫이 자산 값에서 계산한 기대값과 같다 — **리터럴을 박지 않는다**
      ⓑ 가장 무거운 계절의 몫이 **일수 비례와 적힌 몫 «사이»**에 있다.
         한쪽만 보면 「전부 일수 비례로 갈아치웠다」와 구별되지 않는다
      ⓒ 섞은 뒤에도 **합이 1** 이다 — 아니면 연간 에너지가 조용히 사라진다
    """
    asset = _asset_shares()
    declared = dict(asset.by_season)
    day = _day_share()
    heaviest = max(declared, key=lambda name: declared[name])
    assert declared[heaviest] > day[heaviest], (
        f"자산이 {heaviest!r} 에 적은 몫 {declared[heaviest]!r} 이 일수 비례 "
        f"{day[heaviest]!r} 보다 크지 않다 — 이 검사의 방향이 정해지지 않는다"
    )

    loads = ApplianceLoads(heatpump_kwh=_HEATPUMP, ev_kwh=_EV, season_shares=asset)
    stamped = loads.blended_season_shares
    assert stamped is not None
    ratio = loads.ev_ratio
    got = _effective(stamped)
    want = {
        name: (1.0 - ratio) * declared[name] + ratio * day[name] for name in declared
    }
    for name in declared:
        assert got[name] == pytest.approx(want[name], rel=1e-12), (
            f"{name!r} 의 유효 몫이 {got[name]!r} 인데 자산에서 계산한 기대값은 "
            f"{want[name]!r} 다 (ev_ratio={ratio!r})"
        )
    assert day[heaviest] < got[heaviest] < declared[heaviest], (
        f"{heaviest!r} 의 몫이 {got[heaviest]!r} 다 — 일수 비례 "
        f"{day[heaviest]!r} 와 적힌 몫 {declared[heaviest]!r} 사이여야 한다"
    )
    assert abs(math.fsum(got.values()) - 1.0) <= SHARE_TOLERANCE, (
        f"섞은 몫의 합이 {math.fsum(got.values())!r} 다 — 1 이어야 한다"
    )


def test_splitting_the_ev_out_moves_the_seasons_but_not_the_annual_total() -> None:
    """★★★★ **계절만 갈리고 연 총량은 한 kWh 도 움직이지 않는다** (WP-N1 §4-3).

    이 성질이 없으면 위 검사는 *「전기차 부하를 덜어 냈다」* 로도 통과한다 —
    위 `test_the_annual_total_does_not_move_when_the_seasons_do` 와 같은 축이며,
    거기서는 사용자가 몫을 바꾸었고 여기서는 **같은 합계의 기기 구성**이 바뀐다.
    """
    asset = _asset_shares()
    total = _HEATPUMP + _EV
    stamped = ApplianceLoads(
        heatpump_kwh=_HEATPUMP, ev_kwh=_EV, season_shares=asset
    ).blended_season_shares

    plain = _season_load(_run(asset, heatpump=total))
    after = _season_load(_run(stamped, heatpump=total))

    heaviest = max(dict(asset.by_season), key=lambda name: dict(asset.by_season)[name])
    assert after[heaviest] < plain[heaviest], (
        f"합계 {total:,.0f} 중 {_EV:,.0f} 이 전기차인데 {heaviest!r} 의 부하가 "
        f"줄지 않았다 — 냉난방의 겨울 몫이 전기차에도 씌워지고 있다\n"
        f"{_table(plain, after)}"
    )
    assert math.fsum(after.values()) == pytest.approx(
        math.fsum(plain.values()), rel=1e-9
    ), (
        f"연간 부하 총량이 {math.fsum(plain.values()):,.1f} 에서 "
        f"{math.fsum(after.values()):,.1f} 로 움직였다 — 계절 사이에서 옮겨 갈 "
        f"뿐이어야 한다\n{_table(plain, after)}"
    )

# ── ⑥ 하루 안의 형상 — **기기마다 자기 24스텝을 갖는다** (R67/WP-N1b) ──────
#
# ①~⑤ 가 재는 것은 **계절 축**까지다. 그런데 성분에 씌우는 가중치가 여전히
# **가구 부하의 24스텝 형상** 하나였다 — 즉 전기차 충전이 가구 부하와 같은
# 모양으로, 곧 「낮」에 깔렸다. R67/WP-N1 실측이 그것을 잡았다: 전기차 몫이
# 봄·여름으로 옮겨 가며 태양광 정오 봉우리와 겹쳐 **계통 송전이 0 kWh** 가
# 되고 잉여 판매·REC 편익이 통째로 0원이 됐다.
#
# ⚠ **아래 어떤 검사에도 시각(7·19·14 …)이나 24개 리터럴을 박지 않는다** —
# 기대값은 **자산이 적은 구간**에서 그 자리에서 짓는다. 박으면 자산을 갈아
# 끼우는 날(= 그 절의 `replace_when` 이 예고한 날) 이 검사만 낡는다.


def _daily_shapes() -> ApplianceDailyShapes:
    """배포 자산이 선언한 **기기별 하루 형상**. 값을 여기 박지 않는다."""
    shapes = asset_appliance_daily_shapes()
    assert shapes is not None, (
        "배포 자산에 `appliance_daily_shapes:` 절이 없다 — 이 아래 검사들이 "
        "재는 것은 그 절이 있는 실행이다"
    )
    return shapes


def _steps_in(ranges: tuple[tuple[int, ...], ...]) -> set[int]:
    """자산의 구간 목록이 덮는 **스텝 집합** — 시험도 자산에서 그 자리에서 편다."""
    return {step for first, last in ranges for step in range(first, last + 1)}


def _provider() -> AssumptionSet:
    """배포 대장. 기기 부하 두 칸을 늘 명시로 주므로 이 대장이 채우지 않는다."""
    return AssumptionSet.load_from_yaml(_ASSUMPTIONS)


def _stamped(
    *, heatpump: float | None, ev: float | None, profile_path: Path | None = None
) -> ApplianceSeasonShares:
    """**배포 경로와 같은 차례로** 도장 찍은 몫 (`with_ledger_defaults` → 비중).

    ⚠ 손으로 `replace(..., daily_shapes=...)` 하지 않는다 — 그러면 「배선이
    실제로 걸리는가」를 시험이 대신 해 버리고, 배선이 끊겨도 초록불이 된다.
    """
    loads = with_ledger_defaults(
        ApplianceLoads(
            heatpump_kwh=heatpump, ev_kwh=ev, season_shares=_asset_shares()
        ),
        _provider(),
        profile_path=profile_path,
    )
    shares = ApplianceSeasonShares.of(
        loads.blended_season_shares, _load_kwh(), loads.total_kwh
    )
    assert shares is not None
    return shares


def _appliance_increment(
    shares: ApplianceSeasonShares, *, total: float
) -> dict[str, tuple[float, ...]]:
    """계절마다 **기기 부하가 하루에 더한 몫** — 기본 부하를 뺀 나머지.

    빼는 기준은 `DailyShape.representative_day_by_season` 이 기본 부하만으로
    낸 하루이며, `load_days` 가 그 위에 더하는 것과 **같은 자리**다.
    """
    shape = _load_shape()
    got = ApplianceSeasonShares.load_days(shape, total, shares, days=DAYS_PER_YEAR)
    base = shape.representative_day_by_season(
        total * shares.base_ratio, days=DAYS_PER_YEAR
    )
    return {
        season.name: tuple(value - plain for value, plain in zip(day, base_day, strict=True))
        for (season, day, _days), (_base_season, base_day, _base_days) in zip(
            got, base, strict=True
        )
    }


def test_an_asset_without_the_appliance_shapes_is_element_for_element_what_it_was(
    tmp_path: Path,
) -> None:
    """★★★★ **기기 형상 절이 없으면 이 WP 전과 원소 하나까지 같다** (WP-N1b §2-6).

    기대값을 이 시험이 **이 WP 전의 식으로 다시 짓는다** — 성분을 둘로 쪼개
    `math.fsum` 으로 더하면 부동소수 마지막 자리가 갈릴 수 있고, 그러면 기기
    형상 절을 두지 않은 자산으로 도는 실행이 조용히 움직인다. 그래서
    `pytest.approx` 가 아니라 **`==`** 로 잰다.
    """
    text = PROFILE_PATH.read_text(encoding="utf-8")
    head, marker, _rest = text.partition("\nappliance_daily_shapes:")
    assert marker, (
        "배포 자산에 `appliance_daily_shapes:` 절이 없다 — 이 검사가 「그 절을 "
        "지운 자산」과 견주는 것이므로 지울 것이 있어야 한다"
    )
    stripped = tmp_path / "representative-day.yaml"
    stripped.write_text(head + "\n", encoding="utf-8")

    shape = _load_shape()
    shares = _stamped(heatpump=_HEATPUMP, ev=_EV, profile_path=stripped)
    assert shares.daily_shapes is None, (
        "기기 형상 절을 지운 자산인데 형상이 실렸다 — 그때는 가구 부하 형상 "
        "으로 돌아야 한다"
    )

    total = _load_kwh() + _HEATPUMP + _EV
    got = ApplianceSeasonShares.load_days(shape, total, shares, days=DAYS_PER_YEAR)

    # ── 기대값 — 「이 WP 전」의 식 그대로. 성분이 하나이고 가중치는 가구 부하다 ──
    declared = dict(_asset_shares().by_season)
    day_share = _day_share()
    ratio = _EV / (_HEATPUMP + _EV)
    base = shape.representative_day_by_season(
        total * shares.base_ratio, days=DAYS_PER_YEAR
    )
    extra_total = total * shares.appliance_ratio
    want = tuple(
        (
            season,
            tuple(
                value + extra_total * (
                    (1.0 - ratio) * declared[season.name]
                    + ratio * day_share[season.name]
                ) / season_days * weight
                for value, weight in zip(day, weights, strict=True)
            ),
            season_days,
        )
        for (season, day, season_days), (_season, weights) in zip(
            base, shape.by_season, strict=True
        )
    )
    assert got == want, (
        "기기 형상 절이 없는 자산의 하루가 이 WP 전의 식과 「원소 하나까지」 "
        "같지 않다"
    )


def test_the_heatpump_energy_lands_only_in_the_intervals_the_asset_declares() -> None:
    """★★★★ **히트펌프 에너지가 자산이 적은 구간에만 모인다** (WP-N1b §4-2).

    전기차를 `0.0` 으로 두면 하루의 증분이 **전부 히트펌프**다. 그 증분이
    ⓐ 자산이 그 계절에 적은 구간 **안에서만** 0 이 아니고 ⓑ 구간 **안에서는
    서로 같다**(「구간 안은 균등」 · 사용자 판정 §2-3)는 것을 잰다.

    ⚠ 계절 이름도 시각도 박지 않는다 — **자산이 적은 계절마다** 그 계절의
    구간을 읽어 기대값을 짓는다.
    """
    shape = _load_shape()
    declared = _daily_shapes().of(HEATPUMP_LOAD_LEDGER_KEY)
    assert declared is not None, "배포 자산이 히트펌프의 하루 형상을 적지 않았다"
    shares = _stamped(heatpump=_HEATPUMP, ev=0.0)
    increment = _appliance_increment(shares, total=_load_kwh() + _HEATPUMP)

    for season in shape.seasons:
        ranges = declared.ranges(season.name)
        assert ranges is not None
        inside = _steps_in(ranges)
        values = increment[season.name]
        lit = {step for step, value in enumerate(values) if abs(value) > 1e-9}
        assert lit == inside, (
            f"{season.name!r} 의 히트펌프 부하가 자산 구간 {sorted(inside)} 이 "
            f"아니라 {sorted(lit)} 에 깔렸다 (자산 구간 목록 {ranges!r})"
        )
        first = values[min(inside)]
        for step in sorted(inside):
            assert values[step] == pytest.approx(first, rel=1e-12), (
                f"{season.name!r} 구간 안이 균등하지 않다 — 스텝 {step} 이 "
                f"{values[step]!r} 인데 {min(inside)} 는 {first!r} 다"
            )


def test_the_ev_energy_is_spread_flat_across_the_whole_day() -> None:
    """★★★★ **전기차 에너지가 하루에 균등하게 깔린다** (WP-N1b §2-3 · §4-3).

    히트펌프를 `0.0` 으로 두면 증분이 **전부 전기차**다. 재는 것 둘:
      ⓐ 자산이 전기차에 적은 구간 **밖은 0** 이다
      ⓑ ★ 지금 자산이 적은 것은 **하루 전체**이므로 24스텝이 **서로 같다**

    ⚠ ⓑ 는 자산의 「현재 상태」에 걸린 검사다. **그것이 목적이다** — 충전 시각
    자료가 오면(그 절의 `replace_when` ⓑ) 이 줄이 그 자리에서 실패해
    *「전기차가 더 이상 균등이 아니다」* 를 말한다. 그때 함께 움직일 것은
    **결론축의 골든**이며, 조용히 지나가면 그 사실이 묻힌다.
    """
    shape = _load_shape()
    declared = _daily_shapes().of(EV_LOAD_LEDGER_KEY)
    assert declared is not None, "배포 자산이 전기차의 하루 형상을 적지 않았다"
    shares = _stamped(heatpump=0.0, ev=_EV)
    increment = _appliance_increment(shares, total=_load_kwh() + _EV)

    for season in shape.seasons:
        ranges = declared.ranges(season.name)
        assert ranges is not None
        inside = _steps_in(ranges)
        values = increment[season.name]
        lit = {step for step, value in enumerate(values) if abs(value) > 1e-9}
        assert lit == inside, (
            f"{season.name!r} 의 전기차 부하가 자산 구간 {sorted(inside)} 이 "
            f"아니라 {sorted(lit)} 에 깔렸다"
        )
        assert inside == set(range(shape.steps)), (
            f"자산이 전기차에 적은 구간이 하루 전체가 아니다 ({ranges!r}) — "
            "충전 시각 자료가 왔다면 골든 3종을 다시 뽑아야 한다"
        )
        for step, value in enumerate(values):
            assert value == pytest.approx(values[0], rel=1e-12), (
                f"{season.name!r} 의 전기차 부하가 스텝 {step} 에서 {value!r} "
                f"인데 스텝 0 은 {values[0]!r} 다 — 균등이 아니다"
            )


def test_the_daily_shapes_move_the_hours_but_not_the_annual_total() -> None:
    """★★★★ **형상만 갈리고 연 총량은 한 kWh 도 움직이지 않는다** (WP-N1b §4-4).

    이 성질이 없으면 위 두 검사는 *「기기 부하를 덜어 냈다」* 로도 통과한다 —
    ①~⑤ 의 `test_the_annual_total_does_not_move_when_the_seasons_do` 와 같은
    축이며, 거기서는 **계절**이 갈렸고 여기서는 **하루 안**이 갈린다.

    ★ 계절마다 따로 잰다 — 총합만 보면 계절 사이에서 옮겨 간 것과 구별되지
    않고, 이 WP 는 계절 몫을 한 자리도 건드리지 않았다.
    """
    shape = _load_shape()
    total = _load_kwh() + _HEATPUMP + _EV
    shaped = _stamped(heatpump=_HEATPUMP, ev=_EV)
    flat = replace(shaped, daily_shapes=None)

    got = ApplianceSeasonShares.load_days(shape, total, shaped, days=DAYS_PER_YEAR)
    plain = ApplianceSeasonShares.load_days(shape, total, flat, days=DAYS_PER_YEAR)

    moved = 0
    for (season, day, days), (_flat_season, flat_day, flat_days) in zip(
        got, plain, strict=True
    ):
        assert days == flat_days
        assert math.fsum(day) * days == pytest.approx(
            math.fsum(flat_day) * flat_days, rel=1e-12
        ), (
            f"{season.name!r} 의 연간 부하가 "
            f"{math.fsum(flat_day) * flat_days:,.4f} 에서 "
            f"{math.fsum(day) * days:,.4f} 로 움직였다 — 하루 안에서 자리만 "
            "바뀌어야 한다"
        )
        moved += sum(1 for a, b in zip(day, flat_day, strict=True) if a != b)
    assert moved > 0, (
        "하루 안의 형상을 실었는데 스텝이 한 칸도 안 움직였다 — 형상이 계산에 "
        "닿지 않고 실려만 다닌다는 뜻이다"
    )


def test_the_asset_shapes_reach_a_calendar_the_user_typed() -> None:
    """★★★ **화면에서 적은 계절 몫에도 기기 형상이 걸린다** (WP-N1b 배선).

    기기의 하루 형상은 **기기의 성질**이지 사용자가 적은 계절 몫의 성질이
    아니다. 한쪽만 걸면 사용자가 계절 몫을 손보는 순간 전기차 충전이 조용히
    「낮」으로 되돌아간다 — 그 결손이 R67/WP-N1 이 실측한 잉여 0 kWh 다.
    """
    typed = resolve_appliance_season_shares(_winter_heavy())
    assert typed is not None
    assert typed.daily_shapes is None
    loads = with_ledger_defaults(
        ApplianceLoads(heatpump_kwh=_HEATPUMP, ev_kwh=_EV, season_shares=typed),
        _provider(),
    )
    assert loads.season_shares is not None
    assert loads.season_shares.daily_shapes == _daily_shapes()
    assert dict(loads.season_shares.by_season) == _winter_heavy(), (
        "기기 형상을 실으면서 사용자가 적은 계절 몫까지 갈아 끼웠다 — 통로의 "
        "차례(①이 이긴다)가 깨졌다"
    )


def test_a_device_shape_that_misses_a_season_of_the_calendar_is_refused() -> None:
    """★★★ **달력의 계절 하나를 빠뜨린 기기 형상은 거부한다** — 메우지 않는다.

    메우면 그 계절만 조용히 가구 부하 형상으로 돌아가고, 그 어긋남은 아무
    예외도 내지 않는다 — `_matched` 의 계절 이름 대조와 **같은 판단**이다.
    ⚠ 여기서 나는 것은 `ValidationError` 가 아니라 `ValueError` 다. 어긋난 두
    값이 **둘 다 저장소의 자산**이고 사용자가 적은 것이 아니다.
    """
    shape = _load_shape()
    names = _season_names()
    short = ApplianceDailyShapes(shapes=(
        ApplianceDailyShape(
            ledger_key=HEATPUMP_LOAD_LEDGER_KEY,
            by_season=tuple((name, ((0, 0),)) for name in names[:-1]),
        ),
    ))
    shares = replace(_asset_shares(), ev_ratio=0.5, daily_shapes=short)
    with pytest.raises(ValueError, match=names[-1]):
        shares._matched(shape)


def test_an_interval_outside_the_step_grid_is_refused() -> None:
    """★★ **격자 밖 구간·뒤집힌 구간은 거부한다** — 조용히 잘라 주지 않는다.

    잘라 주면 `[19, 25]` 를 적었을 때 21시까지만 걸리는데 자산은 25시까지
    적었다고 말한다. ⚠ 스텝 수를 이 시험이 박지 않는다 — 자산의 `steps` 에서
    그 자리에서 짓는다.
    """
    steps = _load_shape().steps
    for bad in ([[0, steps]], [[9, 7]], [[-1, 3]], [[1, 2, 3]], []):
        with pytest.raises(ValueError):
            weights_from_hour_ranges(bad, steps=steps, key="시험")


def test_intervals_are_flat_inside_and_proportional_between() -> None:
    """★★★ **구간 안은 균등 · 구간 사이는 시간수 비례** (WP-N1b §2-2).

    합을 손으로 맞추지 않아도 **구조적으로 1** 이라는 것이 이 갈래를 고른
    사유다 — 24개를 적어 네 자리로 끊으면 `SHARE_TOLERANCE`(1e-9)를 넘는다.
    ⚠ 시각을 박지 않는다: 길이가 다른 두 구간을 그 자리에서 짓는다.
    """
    steps = _load_shape().steps
    short, long = 2, 4
    weights = weights_from_hour_ranges(
        [[0, short - 1], [steps - long, steps - 1]], steps=steps, key="시험"
    )
    assert len(weights) == steps
    assert math.fsum(weights) == pytest.approx(1.0, abs=SHARE_TOLERANCE)
    assert weights[0] == pytest.approx(weights[short - 1], rel=1e-12)
    assert math.fsum(weights[:short]) == pytest.approx(
        short / (short + long), rel=1e-12
    ), "구간 사이가 「시간수 비례」가 아니다"
    assert all(value == 0.0 for value in weights[short:steps - long])


def test_two_intervals_of_the_same_length_split_the_energy_in_half() -> None:
    """★★★ **같은 길이의 두 봉우리는 반반이다** — 겨울 히트펌프가 그 갈래다.

    사용자가 두 구간 「사이」의 배분을 정하지 않았고, 「구간 시간수 비례」로
    두면 길이가 같은 두 구간이 반반이 된다(WP-N1b §2-2 · **새 수를 발명하지
    않는 갈래**). ⚠ 시각을 박지 않는다 — 자산이 봉우리 둘을 적고 길이가 같은
    계절만 재며, 그런 계절을 하나도 못 찾으면 **검사가 조용히 빠지지 않도록**
    끝에서 실패한다.
    """
    shape = _load_shape()
    declared = _daily_shapes().of(HEATPUMP_LOAD_LEDGER_KEY)
    assert declared is not None
    measured = 0
    for season in shape.seasons:
        ranges = declared.ranges(season.name)
        assert ranges is not None
        if len(ranges) != 2:
            continue
        (first_a, last_a), (first_b, last_b) = ranges
        if last_a - first_a != last_b - first_b:
            continue
        weights = weights_from_hour_ranges(
            ranges, steps=shape.steps, key=season.name
        )
        assert math.fsum(weights[first_a:last_a + 1]) == pytest.approx(
            0.5, rel=1e-12
        ), (
            f"{season.name!r} 의 두 봉우리가 길이가 같은데 반반이 아니다 "
            f"({ranges!r})"
        )
        measured += 1
    assert measured >= 1, (
        "봉우리 둘짜리 계절을 자산에서 하나도 찾지 못했다 — 자산이 갈렸다면 "
        "이 검사가 무엇을 재는지 다시 정해야 한다"
    )
