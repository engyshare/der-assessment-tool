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

import pytest

from core.casegrid.appliance_load import (
    APPLIANCE_SEASON_SHARE_FIELD,
    APPLIANCE_SEASON_SHARE_FIELD_KEY,
    EV_LOAD_FIELD,
    HEATPUMP_LOAD_FIELD,
    ApplianceLoads,
    ApplianceSeasonShares,
    asset_appliance_season_shares,
    resolve_appliance_loads,
    resolve_appliance_season_shares,
)
from core.casegrid.e2e_runner import DAYS_PER_YEAR, run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.models import CaseOutcome
from core.casegrid.profiles import SHARE_TOLERANCE, DailyShape, load_daily_shapes
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
    """그 몫이 **계절마다 실제로 걸리는 값** — 형상과 맞춰 꺼낸다."""
    shape = _load_shape()
    return {
        season.name: share
        for season, (_weights, share) in zip(
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
