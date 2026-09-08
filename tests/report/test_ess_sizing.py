"""**ESS 적정용량 역산**(경우 「ESS」 · 겨울 하루) — R64/WP-8a.

검토서(`docs/적정용량-산출방법-검토.md`) §5-④ 가 *「다루지 않는다」* 고 적어 둔
자리를 `core/report/ess_sizing.py` 가 채웠는지를 잰다. PV 쪽의 같은 검사는
`tests/report/test_sizing.py` 다.

★ **이 파일은 「사용 가능 비율」을 베껴 적지 않는다.** 비율은 언제나 실제
`core/der/ess.py::ESS.usable_capacity_kwh` 를 불러서 얻고, 왕복은 그 함수가 낸
값으로 판정한다 — 산식을 이 파일에 옮겨 적으면 정본이 바뀌는 날 이 검사가 조용히
낡은 산식을 지키게 된다.
"""
from __future__ import annotations

import math
from collections.abc import Callable

import pytest

from core.casegrid.ledger_levels import design_variables
from core.contracts.validation import ValidationError
from core.der.ess import ESS, ESSOperatingMode
from core.report.ess_sizing import (
    build_ess_daily_sizing,
    relaxed_shortfall_kwh_by_step,
    required_ess_capacity_kwh,
    required_ess_power_kw,
    shortfall_kwh_by_step,
)

#: 겨울 저녁에 결손이 몰린 하루(24스텝) — **값이 아니라 형상을 위한 탐침**이다.
#: 자산의 계절 넷은 가정값이고(`docs/decisions-2026-09-06-R64.md` §2) 이 모듈은
#: 「겨울이 얼마인가」를 고르지 않으므로, 여기 수도 자산에서 오지 않는다.
_PROBE_LOAD_KWH = tuple([0.5] * 7 + [1.0] * 5 + [0.8] * 6 + [2.0] * 4 + [0.6] * 2)
_PROBE_PV_KWH = tuple([0.0] * 7 + [1.5] * 5 + [1.2] * 6 + [0.0] * 4 + [0.0] * 2)


def _usable_capacity_of(**ess_kwargs: object) -> Callable[..., float]:
    """정격용량을 바꿔 가며 `ESS.usable_capacity_kwh` 를 부를 수 있게 싼 탐침.

    `core/report/ess_sizing.py::UsableCapacityKwh` 가 요구하는 모양이며, 다음 WP 가
    배선할 때 쓰는 것도 이 모양이다.
    """

    def probe(*, capacity_kwh: float, year: int) -> float:
        ess = ESS(name="탐침", capacity_kwh=capacity_kwh, power_kw=3.0, **ess_kwargs)
        return ess.usable_capacity_kwh(year=year)

    return probe


# ── 성질 「가」 — 왕복 ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("ess_kwargs", "year"),
    [
        ({}, 1),
        ({"soc_min_pct": 20.0, "soc_max_pct": 95.0}, 1),
        ({"soc_min_pct": 5.0, "soc_max_pct": 80.0}, 12),
        # 사용후배터리는 초기 SOH 가 0.8 이라 EOL 기본값(80%)을 그대로 두면
        # 취득 즉시 EOL 이 되어 `ESS` 가 거부한다 — 낙폭이 남도록 낮춰 준다.
        ({"second_life": True, "eol_soh_pct": 60.0}, 3),
        (
            {
                "operating_mode": ESSOperatingMode.BACKUP_RESERVE,
                "backup_reserve_pct": 30.0,
            },
            7,
        ),
        # ★ 이 갈래는 **나눗셈이 아래로 떨어지는** 자리다 — 되먹임 올림이 없으면
        # 왕복의 「이상」 쪽이 깨진다. `test_the_inverse_lifts_a_capacity_that_
        # rounded_down` 이 그 사실을 따로 증명한다.
        ({"soc_min_pct": 0.0, "soc_max_pct": 50.0}, 20),
    ],
)
def test_the_inverse_closes_on_both_sides_of_the_boundary(
    ess_kwargs: dict[str, object], year: int
) -> None:
    """★★★ **왕복 — 경계 양쪽을 잰다.** 「대충 같다」로 재지 않는다.

    역산한 용량으로 `ESS` 를 세우면 `usable_capacity_kwh` 가 필요 방출 에너지
    **이상**이고, 그보다 작은 용량은 **미달**이다. 이것이 「`usable_capacity_kwh`
    의 역함수다」의 유일한 증거다.

    ⚠ SOC 창·SOH(연차·사용후배터리)·백업 예비를 흔들어도 성립해야 한다 — 셋 중
    하나라도 역산이 빠뜨리면 그 갈래에서만 용량이 조용히 작아진다.
    """
    usable = _usable_capacity_of(**ess_kwargs)
    sizing = build_ess_daily_sizing(
        load_kwh_by_step=_PROBE_LOAD_KWH,
        pv_kwh_by_step=_PROBE_PV_KWH,
        step_hours=1.0,
        usable_capacity_kwh=usable,
        year=year,
        search_low_kwh=0.0,
        search_high_kwh=1_000.0,
        grid_supply_allowance=0.0,
    )
    needed_kwh = sizing.required_discharge_kwh
    assert needed_kwh > 0.0, "탐침 하루에 결손이 없어 왕복을 잴 것이 없다"

    enough = usable(capacity_kwh=sizing.required_capacity_kwh, year=year)
    assert enough >= needed_kwh, (
        f"역산 용량 {sizing.required_capacity_kwh}kWh 가 낼 수 있는 양 {enough}kWh 는 "
        f"필요 방출 {needed_kwh}kWh 에 미달이다"
    )

    smaller_kwh = sizing.required_capacity_kwh * (1.0 - 1e-6)
    assert usable(capacity_kwh=smaller_kwh, year=year) < needed_kwh, (
        "역산 용량보다 작은 용량이 필요 방출을 감당한다 — 「최소」가 아니다"
    )


def test_the_inverse_lifts_a_capacity_that_rounded_down() -> None:
    """★★ **나눗셈이 아래로 떨어지는 자리를 실제로 밟는다.**

    `필요 방출 / 비율` 을 그대로 내면 그 용량으로 세운 `ESS` 가 필요 방출량에
    **미달**하는 입력이 있다. 그런 자리에서 역산이 「최소 용량」이라며 미달을 내면
    그것은 반올림 오차가 아니라 **틀린 답**이다.

    ⚠ 이 검사는 되먹임 올림이 **없으면 실제로 빨간불이 되는** 입력이어야 뜻이
    있으므로, 먼저 `naive` 가 미달임을 확인하고 나서 역산 결과를 본다. 그리고
    올린 폭이 **표현 가능한 마지막 자리**임도 함께 본다 — 넉넉한 안전 여유로
    덮은 것이라면 그것은 역함수가 아니라 다른 값이다.
    """
    usable = _usable_capacity_of(soc_min_pct=0.0, soc_max_pct=50.0)
    year = 20
    needed_kwh = 12.7

    naive_kwh = needed_kwh / usable(capacity_kwh=1.0, year=year)
    assert usable(capacity_kwh=naive_kwh, year=year) < needed_kwh, (
        "탐침이 낡았다 — 이 입력에서는 나눗셈이 아래로 떨어지지 않으므로 "
        "이 검사가 아무것도 지키지 않는다"
    )

    required_kwh = required_ess_capacity_kwh(
        required_discharge_kwh=needed_kwh, usable_capacity_kwh=usable, year=year
    )
    assert required_kwh > naive_kwh
    assert usable(capacity_kwh=required_kwh, year=year) >= needed_kwh
    assert required_kwh <= math.nextafter(math.nextafter(naive_kwh, math.inf), math.inf), (
        f"올린 폭 {required_kwh - naive_kwh} 이 마지막 자리 두 칸을 넘는다 — "
        "안전 여유를 얹은 것이지 역함수가 아니다"
    )


def test_the_inverse_follows_the_state_of_health_down_the_years() -> None:
    """★ **연차가 필수 인자인 이유** — 같은 결손이라도 20년차에는 더 큰 용량이
    필요하다. SOH 가 떨어지면 같은 정격용량이 덜 내기 때문이다.

    ⚠ 기본값을 두면 이 차이가 조용한 가정이 된다.
    """
    usable = _usable_capacity_of()
    needed_kwh = 5.0
    first = required_ess_capacity_kwh(
        required_discharge_kwh=needed_kwh, usable_capacity_kwh=usable, year=1
    )
    twentieth = required_ess_capacity_kwh(
        required_discharge_kwh=needed_kwh, usable_capacity_kwh=usable, year=20
    )
    assert twentieth > first, (
        f"20년차 필요 용량 {twentieth}kWh 가 1년차 {first}kWh 보다 크지 않다 — "
        "열화가 역산에 반영되지 않았다"
    )
    assert usable(capacity_kwh=twentieth, year=20) >= needed_kwh


# ── 성질 「나」 — 결손이 없으면 정확히 0 ──────────────────────────────


def test_pv_covering_the_load_all_day_needs_exactly_zero() -> None:
    """★ **PV 가 종일 부하를 웃돌면 필요 용량이 정확히 0** 이다.

    저장할 이유가 없는데 0 이 아닌 값이 나오면, 그것은 어디선가 「최소한 이만큼은
    필요하다」를 지어낸 것이다. `pytest.approx` 로 재지 않는다 — 0 은 근사값이
    아니다.
    """
    load = (1.0, 2.0, 3.0, 0.0)
    pv = (1.0, 2.5, 4.0, 0.0)
    sizing = build_ess_daily_sizing(
        load_kwh_by_step=load,
        pv_kwh_by_step=pv,
        step_hours=1.0,
        usable_capacity_kwh=_usable_capacity_of(),
        year=1,
        search_low_kwh=0.0,
        search_high_kwh=30.0,
        grid_supply_allowance=0.0,
    )

    assert sizing.shortfall_by_step_kwh == (0.0, 0.0, 0.0, 0.0)
    assert sizing.required_discharge_kwh == 0.0
    assert sizing.required_capacity_kwh == 0.0
    assert sizing.required_power_kw == 0.0


# ── 성질 「다」 — 음수로 상계하지 않는다 ──────────────────────────────


def test_daytime_surplus_does_not_cancel_the_evening_shortfall() -> None:
    """★★ **낮에 남은 PV 가 저녁 결손을 줄이지 않는다.**

    상계하면 **저장 없이 시간을 건너뛴 것**이 되어 ESS 를 세우는 이유 자체가
    사라진다. 하루 총합끼리 뺀 값(`net`)과 시각별 결손의 합을 나란히 놓고, 둘이
    다르며 결손 쪽이 크다는 것을 본다.
    """
    load = (0.0, 4.0)
    pv = (10.0, 0.0)
    shortfall = shortfall_kwh_by_step(load_kwh_by_step=load, pv_kwh_by_step=pv)

    assert shortfall == (0.0, 4.0), "낮의 잉여가 저녁 결손을 깎았다"
    net_kwh = sum(load) - sum(pv)
    assert net_kwh < 0.0, "탐침이 잘못됐다 — 총합끼리 빼면 잉여여야 한다"
    assert sum(shortfall) > net_kwh

    sizing = build_ess_daily_sizing(
        load_kwh_by_step=load,
        pv_kwh_by_step=pv,
        step_hours=1.0,
        usable_capacity_kwh=_usable_capacity_of(),
        year=1,
        search_low_kwh=0.0,
        search_high_kwh=30.0,
        grid_supply_allowance=0.0,
    )
    assert sizing.required_capacity_kwh > 0.0, (
        "하루 총합이 잉여라는 이유로 필요 용량이 0 이 됐다 — 저녁 결손이 사라졌다"
    )


# ── 성질 「라」 — 해상도를 쪼개도 에너지는 같고 첨두는 커질 수 있다 ────


def test_halving_the_step_keeps_the_energy_and_raises_the_power() -> None:
    """★★ **24스텝을 48스텝으로 쪼갠다** — 필요 저장용량은 같고 정격출력은 커진다.

    한 시간의 사용량이 그 시간 안에서 앞쪽 30분에 몰려 있었다면, 에너지 합은
    그대로지만 첨두 출력은 두 배다. 둘을 한 값으로 뭉치면 **정격출력이 조용히
    작아진다.**
    """
    usable = _usable_capacity_of()
    hourly = build_ess_daily_sizing(
        load_kwh_by_step=_PROBE_LOAD_KWH,
        pv_kwh_by_step=_PROBE_PV_KWH,
        step_hours=1.0,
        usable_capacity_kwh=usable,
        year=1,
        search_low_kwh=0.0,
        search_high_kwh=1_000.0,
        grid_supply_allowance=0.0,
    )

    # 각 시간의 부하·발전을 앞쪽 30분에 몰아 넣는다 — 시간별 «에너지»는 그대로다.
    half_load = [value for kwh in _PROBE_LOAD_KWH for value in (kwh, 0.0)]
    half_pv = [value for kwh in _PROBE_PV_KWH for value in (kwh, 0.0)]
    half_hourly = build_ess_daily_sizing(
        load_kwh_by_step=half_load,
        pv_kwh_by_step=half_pv,
        step_hours=0.5,
        usable_capacity_kwh=usable,
        year=1,
        search_low_kwh=0.0,
        search_high_kwh=1_000.0,
        grid_supply_allowance=0.0,
    )

    assert len(half_hourly.shortfall_by_step_kwh) == 2 * len(hourly.shortfall_by_step_kwh)
    assert half_hourly.required_discharge_kwh == hourly.required_discharge_kwh, (
        "해상도를 쪼갰더니 하루치 에너지가 달라졌다"
    )
    assert half_hourly.required_capacity_kwh == hourly.required_capacity_kwh, (
        "해상도를 쪼갰더니 필요 저장용량이 달라졌다 — 에너지는 해상도에 안 변한다"
    )
    assert half_hourly.required_power_kw == pytest.approx(2.0 * hourly.required_power_kw), (
        "첨두가 반 스텝에 몰렸는데 정격출력이 따라 커지지 않았다"
    )


# ── 성질 「마」 — 못 세우는 입력은 3요소로 거부한다 ────────────────────


def test_unbuildable_inputs_are_rejected_with_field_reason_and_action() -> None:
    """★★ **조용한 폴백을 만들지 않는다** — 길이가 다르다 · 음수가 있다 ·
    가용 비율이 0 이다 · 스텝 시간이 0 이하다 · 탐색 구간이 뒤집혔다.

    다섯 모두 `ValidationError` 가 나고 `as_dict()` 의 `field`·`reason`·`action` 이
    셋 다 비어 있지 않은지 본다 (NFR-303).

    ⚠ **가용 비율 0 은 지어낸 입력이 아니다.** `ESS` 는 SOC 하한 >= 상한을 스스로
    거부하므로(DV-2) 그 창은 0 이 될 수 없지만, **SOH 가 바닥난 연차**에서는 실제로
    0 이 된다 — 그 연차를 실물 `ESS` 에서 찾아 넣는다.
    """
    usable = _usable_capacity_of()

    dead_year = next(
        year
        for year in range(1, 200)
        if usable(capacity_kwh=1.0, year=year) == 0.0
    )

    with pytest.raises(ValidationError) as length_mismatch:
        shortfall_kwh_by_step(load_kwh_by_step=(1.0, 2.0), pv_kwh_by_step=(1.0,))
    with pytest.raises(ValidationError) as negative_load:
        shortfall_kwh_by_step(load_kwh_by_step=(1.0, -2.0), pv_kwh_by_step=(1.0, 1.0))
    with pytest.raises(ValidationError) as negative_pv:
        shortfall_kwh_by_step(load_kwh_by_step=(1.0, 2.0), pv_kwh_by_step=(1.0, -1.0))
    with pytest.raises(ValidationError) as empty_day:
        shortfall_kwh_by_step(load_kwh_by_step=(), pv_kwh_by_step=())
    with pytest.raises(ValidationError) as no_usable_window:
        required_ess_capacity_kwh(
            required_discharge_kwh=5.0, usable_capacity_kwh=usable, year=dead_year
        )
    with pytest.raises(ValidationError) as zero_step:
        required_ess_power_kw(shortfall_by_step_kwh=(1.0,), step_hours=0.0)
    with pytest.raises(ValidationError) as inverted_range:
        build_ess_daily_sizing(
            load_kwh_by_step=(1.0,),
            pv_kwh_by_step=(0.0,),
            step_hours=1.0,
            usable_capacity_kwh=usable,
            year=1,
            search_low_kwh=30.0,
            search_high_kwh=2.0,
            grid_supply_allowance=0.0,
        )

    for excinfo, expected_field in (
        (length_mismatch, "pv.generation_profile_kwh"),
        (negative_load, "ess.load_profile_kwh"),
        (negative_pv, "pv.generation_profile_kwh"),
        (empty_day, "ess.load_profile_kwh"),
        (no_usable_window, "ess.usable_capacity_kwh"),
        (zero_step, "timeseries.step_hours"),
        (inverted_range, "ess.capacity_kwh"),
    ):
        payload = excinfo.value.as_dict()
        assert payload["field"] == expected_field
        assert payload["reason"], f"{expected_field}: reason 이 비어 있다"
        assert payload["action"], f"{expected_field}: action 이 비어 있다"


# ── 성질 「바」 — 탐색 구간 밖을 「밖이다」로 싣는다 ──────────────────


def test_a_capacity_beyond_the_search_range_is_kept_not_dropped() -> None:
    """★★ **구간을 넓히지 않고 「밖이다」를 값으로 싣는다.**

    `design_variables()` 에서 읽은 `ess_capacity_kwh` 의 `low`·`high` 를 그대로
    탐색 구간으로 넘긴다. ⚠ 2.0·30.0 을 리터럴로 적지 않는다 — 대장이 바뀌면 이
    검사가 조용히 낡는다.

    상한을 확실히 넘는 결손을 주고, 그 점이 **잘리지도 사라지지도 않고**
    `within_search_range=False` 로 남는지 본다.
    """
    variable = next(v for v in design_variables() if v.name == "ess_capacity_kwh")
    usable = _usable_capacity_of()
    unit_kwh = usable(capacity_kwh=1.0, year=1)

    beyond_kwh = variable.high * unit_kwh * 2.0
    inside_kwh = (variable.low + variable.high) / 2.0 * unit_kwh

    beyond = build_ess_daily_sizing(
        load_kwh_by_step=(beyond_kwh,),
        pv_kwh_by_step=(0.0,),
        step_hours=1.0,
        usable_capacity_kwh=usable,
        year=1,
        search_low_kwh=variable.low,
        search_high_kwh=variable.high,
        grid_supply_allowance=0.0,
    )
    inside = build_ess_daily_sizing(
        load_kwh_by_step=(inside_kwh,),
        pv_kwh_by_step=(0.0,),
        step_hours=1.0,
        usable_capacity_kwh=usable,
        year=1,
        search_low_kwh=variable.low,
        search_high_kwh=variable.high,
        grid_supply_allowance=0.0,
    )

    assert not beyond.within_search_range, "상한을 넘는 용량이 구간 안으로 세어졌다"
    assert beyond.required_capacity_kwh > variable.high, (
        f"역산 용량 {beyond.required_capacity_kwh}kWh 가 탐색 상한 {variable.high}kWh 로 "
        "잘렸다 — 구간에 맞춰 값을 깎았다"
    )
    assert inside.within_search_range
    assert variable.low <= inside.required_capacity_kwh <= variable.high


def test_the_shortfall_shape_survives_into_the_result() -> None:
    """★ **시각별 결손이 결과에서 사라지지 않는다.**

    합과 첨두만 남기면 「어느 시각이 얼마나 모자랐는가」를 다음 WP(배선)와 리포트가
    다시 계산해야 하고, 그 재계산이 사본이 된다.
    """
    sizing = build_ess_daily_sizing(
        load_kwh_by_step=_PROBE_LOAD_KWH,
        pv_kwh_by_step=_PROBE_PV_KWH,
        step_hours=1.0,
        usable_capacity_kwh=_usable_capacity_of(),
        year=1,
        search_low_kwh=0.0,
        search_high_kwh=1_000.0,
        grid_supply_allowance=0.0,
    )

    expected = shortfall_kwh_by_step(
        load_kwh_by_step=_PROBE_LOAD_KWH, pv_kwh_by_step=_PROBE_PV_KWH
    )
    assert sizing.shortfall_by_step_kwh == expected
    assert sizing.peak_shortfall_kwh == max(expected)
    assert sizing.required_power_kw == max(expected) / sizing.step_hours
    assert sizing.year == 1


# ── 성질 「마」 — 「계통 허용」 완화 (R67/WP-N3) ───────────────────────


def _sizing(allowance: float):
    """탐침 하루를 허용 비율 하나로 역산한다 — 그 밖의 인자는 한 값이다."""
    return build_ess_daily_sizing(
        load_kwh_by_step=_PROBE_LOAD_KWH,
        pv_kwh_by_step=_PROBE_PV_KWH,
        step_hours=1.0,
        usable_capacity_kwh=_usable_capacity_of(),
        year=1,
        search_low_kwh=0.0,
        search_high_kwh=1_000.0,
        grid_supply_allowance=allowance,
    )


def test_an_allowance_of_zero_is_the_self_sufficient_sizing_element_by_element() -> None:
    """★★★ **되돌림 성질** — 허용 비율 0 은 완전 자립분과 **원소 하나까지** 같다.

    완화가 결손 시계열에 `× (1 - 비율)` 로 걸리므로 비율 0 에서는 곱이 정확히
    1.0 이고 **부동소수 오차조차 없어야** 한다. `pytest.approx` 로 재지 않는
    이유가 그것이다 — 근사로 재면 「비율 0 인데 결손이 미세하게 달라진다」를
    통과시키고, 그 미세한 차이는 되먹임 보정(`required_ess_capacity_kwh` 의 ULP
    올림)을 지나 **용량의 마지막 자리**로 나온다.
    """
    relaxed_zero = _sizing(0.0)
    expected = shortfall_kwh_by_step(
        load_kwh_by_step=_PROBE_LOAD_KWH, pv_kwh_by_step=_PROBE_PV_KWH
    )
    assert relaxed_zero.grid_supply_allowance == 0.0
    assert relaxed_zero.shortfall_by_step_kwh == expected
    assert relaxed_zero.required_discharge_kwh == math.fsum(expected)
    assert relaxed_zero.peak_shortfall_kwh == max(expected)


@pytest.mark.parametrize("allowance", [0.0, 0.1, 0.24, 0.3, 0.36, 1.0])
def test_the_relaxation_scales_capacity_and_power_by_the_same_factor(
    allowance: float,
) -> None:
    """★★★ **용량과 출력이 «둘 다» 정확히 `1 - 비율` 배다.**

    스텝마다 같은 상수를 곱하므로 합(→ 용량)도 첨두(→ 출력)도 같은 비율로 준다.
    그것이 이 산식의 성질이며 **완화가 용량에만 걸리는 것이 아니다** — 그 뜻은
    `core/report/ess_sizing.py::relaxed_shortfall_kwh_by_step` 독스트링이 진다.

    ⚠ **기대값을 리터럴로 적지 않는다** — 완전 자립분에 `1 - 비율` 을 곱해
    짓는다. 0.7 을 적으면 비율이 바뀌는 날 이 검사가 낡은 수를 지킨다.
    ⚠ 용량은 되먹임 보정으로 마지막 한 자리가 올라갈 수 있으므로 `approx` 로
    잰다 — 위 되돌림 검사가 비율 0 에서 **정확히** 같음을 따로 붙든다.
    """
    kept = 1.0 - allowance
    full = _sizing(0.0)
    relaxed = _sizing(allowance)

    assert relaxed.grid_supply_allowance == allowance
    assert relaxed.required_discharge_kwh == pytest.approx(
        full.required_discharge_kwh * kept
    )
    assert relaxed.required_power_kw == pytest.approx(full.required_power_kw * kept)
    if allowance == 1.0:
        # 결손 전량을 계통에서 받으면 저장할 것이 없다 — 0 은 근사값이 아니다.
        assert relaxed.required_capacity_kwh == 0.0
        assert relaxed.required_power_kw == 0.0
    else:
        assert relaxed.required_capacity_kwh == pytest.approx(
            full.required_capacity_kwh * kept
        )


@pytest.mark.parametrize("allowance", [-0.01, 1.01, 30.0])
def test_an_allowance_outside_zero_to_one_is_refused(allowance: float) -> None:
    """★ 소수(0~1) 밖의 허용 비율은 **3요소로 거부한다** (NFR-303).

    `30` 을 그대로 넘기면 완화 결손이 **음수**가 되어 필요 용량이 조용히 0 이
    된다 — 「30% 를 30 으로 적었다」가 *「배터리가 필요 없다」* 로 돌아온다.
    """
    with pytest.raises(ValidationError) as excinfo:
        relaxed_shortfall_kwh_by_step(
            shortfall_by_step_kwh=(1.0, 2.0), grid_supply_allowance=allowance
        )
    assert excinfo.value.field == "policy.grid_supply_allowance"
    assert excinfo.value.reason and excinfo.value.action
