"""**동시율이 「최대수요」에만 걸린다** — 사용자 지시 (R66/WP-5).

사용자 문면(`docs/decisions-2026-09-07-R66.md` §1ⓑ):

    「동시율은 내가 임의로 정하기 어려움. **초기설정은 80%로 하고, 설정을
      통해 변경하는 한 것으로 설계해줘**」

## ★★★ 이 파일의 존재 이유 — **80% 라는 옳은 값이 틀린 계산을 만들 수 있다**

사용자는 **값**을 주었고 **적용 자리**를 말하지 않았다. 그 자리를 정한 것은
판정(`docs/decisions-2026-09-07-R66.md` §3)이며 표로 이렇게 적혀 있다:

    연간 전력량(kWh) 총합   ⛔ 아니다 — 스무 집이 1년에 쓰는 전기의 «합»은
                            동시성과 무관하다. 0.8 을 곱하면 «쓰지 않은
                            전기를 안 쓴 것으로» 만든다
    단지 최대수요(kW)       ✅ 그렇다 — PCS·ESS 정격출력 산정이 이 수를 쓴다
    ESS 용량(kWh)          ✅ 그렇다 (그 역산이 아직 없다 — 판정 §6 착수 4)
    태양광 용량(kW)         ⛔ 아니다 — 총량 ÷ (8,760 × 이용률) 의 역산이다

⇒ **틀리는 방향이 「좋은 쪽」이라서 위험하다.** 부하를 20% 지우면 결론축이
좋아지고, 그 개선은 결함처럼 보이지 않는다. 그래서 이 파일의 ★★ 시험
(`test_changing_the_factor_moves_no_annual_energy`)이 **가장 중요하다** —
그것이 초록불인 동안에만 「동시율을 반영했다」가 참이다.

## ★ 걸리는 자리는 코드에서 **한 곳**이다

`core/casegrid/e2e_runner.py::_site_load_kw` 의 반환값(시각별 kW)이다. 그
독스트링이 *어디에 곱하면 안 되는가*(연간 kWh 총량 · `load_profile_kwh` ·
태양광 역산)를 ⛔ 로 적어 두었다 — **곱하지 않은 것이 「빠뜨린 것」이 아니다.**

## ⚠ 탐침 수준표 13벌이 **동시율을 끈 값(1.0)** 을 갖는 이유

`_resolve` 는 기본값을 두지 않으므로(`grid_purchase_price` 와 같은 판단) 러너를
직접 부르는 시험은 이 축을 갖고 있어야 한다. 그 13벌에는 **1.0(=100%)** 을
주었다 — 그 표들이 재는 것이 동시율이 아니고, **100% 면 이 배선이 서기 전과
원소 하나까지 같아** 그 시험들의 기대값이 「동시율 때문에」 흔들리지 않는다.
그 동일성 자체는 아래 ⓕ 가 잰다. ⛔ **대장값(0.8)을 그 13벌에 박으면** 배선과
무관한 시험 수십 건의 기대값이 함께 움직이고, 그때 실패 문면은 *왜* 움직였는지
말하지 못한다.

## ⚠ 설정 화면에 칸이 서는지는 **여기서 재지 않는다**

사용자 판정으로 **웹 시험이 꺼졌고 웹 구현이 가장 마지막으로 밀렸다**
(`tests/web/conftest.py` 머리말). 대장 항목이 서면 설정 화면은 대장을 훑어
그리므로 통로는 열려 있고, 그 확인은 웹 라운드 몫이다.

## ⚠ `req()` 마커를 달지 않았다

spec 에 「동시율」을 요구하는 수용기준이 없다. 짐작한 ID 를 붙이면
`docs/traceability.md` 가 거짓 인용을 싣는다 —
`tests/casegrid/test_household_count.py` 머리말이 같은 판정을 적었다.
"""
from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

import pytest

from core.casegrid.e2e_runner import _site_load_kw, run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map, ledger_backed_variables
from core.casegrid.profiles import load_daily_shapes
from core.contracts.der import DispatchContext, DispatchResult, Year
from core.contracts.engine import SystemDispatch
from core.der.load import Load

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"

#: 대장 키와 케이스 변수 이름. 둘을 여기 적는 것은 **배선을 재기 위해서**이고
#: 값을 적는 것이 아니다 — 값은 대장에서 읽는다.
_LEDGER_KEY = "design.coincidence_factor"
_VAR = "coincidence_factor"

_SECONDS_PER_HOUR = 3600
_LOAD_NAME = "e2e-load"

#: 단지 총부하가 커져도 **태양광 잉여가 남는** 규모. 사유는
#: `tests/casegrid/test_household_count.py::_COUNT` 가 갖는다.
_COUNT = 2


def _levels(factor: float | None = None) -> dict[str, dict[str, float]]:
    """대장 수준표 — `factor` 를 주면 **동시율 한 축만** 그 값으로 덮는다."""
    level_map = {name: dict(levels) for name, levels in build_level_map(_ASSUMPTIONS).items()}
    if factor is not None:
        level_map[_VAR] = {"low": factor, "base": factor, "high": factor}
    return level_map


def _run(factor: float):
    return run_single_case_e2e(
        {},
        level_map=_levels(factor),
        horizon_years=20,
        daily_shapes=load_daily_shapes(),
        annual_load_kwh=_levels()["household_load_annual_kwh"]["base"],
        household_count=_COUNT,
    )


def _load_annual_kwh(outcome: object) -> float:
    """이 실행이 세운 부하 자원의 **1년차 연간 소비**(kWh, 양수)."""
    loads = [r for r in outcome.resources if isinstance(r, Load)]  # type: ignore[attr-defined]
    assert loads, "이 실행이 부하 자원을 세우지 않았다 — 재는 것이 성립하지 않는다"
    return sum(load.annual_energy_kwh(year=1) for load in loads)


def _peak_shaving_won(outcome: object) -> int:
    line = next(
        b for b in outcome.basis.benefits if b.tag == "PeakShaving"  # type: ignore[attr-defined]
    )
    return line.annual_won


def _fake_dispatch(kwh_per_step: list[float]) -> tuple[SystemDispatch, DispatchContext]:
    """부하 하나만 든 운전 결과 — **부호 규약대로 음수**로 싣는다.

    ⚠ 진짜 러너를 돌려서 재지 않는 이유: ⓓ 가 묻는 것은 *「반환값이 배수를
    타는가」* 하나이고, 파이프라인을 통과시키면 첨두 저감·ESS 운전이 함께
    움직여 **어느 항이 배수를 태웠는지** 실패 문면에서 읽히지 않는다.
    """
    steps = len(kwh_per_step)
    result = DispatchResult(
        electric=[-v for v in kwh_per_step],
        heat=[0.0] * steps,
        cool=[0.0] * steps,
        fuel=[0.0] * steps,
    )
    dispatch = SystemDispatch(
        per_resource={_LOAD_NAME: result},
        grid_import=[0.0] * steps,
        grid_export=[0.0] * steps,
    )
    ctx = DispatchContext(steps=steps, dt=_SECONDS_PER_HOUR, year=Year(1))
    return dispatch, ctx


def _household(name: str = _LOAD_NAME) -> Load:
    return Load(name=name, monthly_kwh=100.0)


def test_the_factor_is_a_ledger_backed_sweep_axis_converted_once() -> None:
    """배선의 앞머리 — **대장 항목이 스윕 축이고 환산이 한 번**이다.

    ⚠ 값을 여기 적지 않는다. 재는 것은 ⓐ 케이스 변수가 그 대장 키를 가리키고
    ⓑ 대장의 `%` 가 **배수**로 와서 1.0 을 넘지 않는다는 두 사실이다 —
    환산이 빠지면 「80% 대신 8000%」가 아니라 **그럴듯한 큰 수**가 나온다.
    """
    assert ledger_backed_variables()[_VAR] == _LEDGER_KEY
    levels = build_level_map(_ASSUMPTIONS)[_VAR]
    assert set(levels) == {"low", "base", "high"}
    assert levels["low"] < levels["base"] < levels["high"], dict(levels)
    assert 0.0 < levels["base"] < 1.0, f"`%` 가 배수로 환산되지 않았다 — {dict(levels)}"
    assert levels["base"] == pytest.approx(0.8), (
        "사용자 지시의 초기설정 80% 가 기준수준에 서 있지 않다"
    )
    assert levels["high"] == pytest.approx(1.0), (
        "상단이 100% 가 아니다 — 그 자리가 이 축의 «회귀 기준선»이다 (아래 ⓕ)"
    )


def test_eighty_percent_is_zero_point_eight_of_the_full_site_load() -> None:
    """ⓓ **동시율 80% 면 `_site_load_kw` 가 100% 대비 0.8배다.**

    스텝마다(0 인 스텝까지) 잰다 — 최대값 하나만 보면 *「피크만 깎고 나머지는
    안 깎았다」* 와 구별되지 않는다.
    """
    kwh = [0.0, 1.0, 4.0, 2.5, 0.0, 7.25]
    dispatch, ctx = _fake_dispatch(kwh)
    household = _household()

    full = _site_load_kw(household, dispatch, ctx, 1.0)
    eighty = _site_load_kw(household, dispatch, ctx, 0.8)
    assert full is not None and eighty is not None

    assert eighty == pytest.approx([v * 0.8 for v in full])
    assert max(eighty) == pytest.approx(max(full) * 0.8)


def test_a_hundred_percent_is_the_run_before_this_wiring_element_for_element() -> None:
    """ⓕ **동시율 100% 면 종전과 원소 하나까지 같다** (회귀 방어).

    「종전」은 `-v / hours_per_step` 뿐이었다. 배수를 1.0 으로 주면 그 식과
    **같은 목록**이 나와야 한다 — 여기가 어긋나면 배수 말고 다른 것이 함께
    들어온 것이고, 그때 이 축의 상단(100%)이 기준선 구실을 못 한다.

    ⚠ 부하가 없는 실행은 여전히 `None` 이다 — 첨두 저감은 그때 0 이 맞고,
    동시율이 그 판정을 바꾸지 않는다.
    """
    kwh = [0.0, 1.0, 4.0, 2.5, 0.0, 7.25]
    dispatch, ctx = _fake_dispatch(kwh)
    hours_per_step = ctx.dt / _SECONDS_PER_HOUR

    before = [v / hours_per_step for v in kwh]
    assert _site_load_kw(_household(), dispatch, ctx, 1.0) == before

    assert _site_load_kw(None, dispatch, ctx, 0.8) is None
    assert _site_load_kw(None, dispatch, ctx, 1.0) is None


def test_changing_the_factor_moves_no_annual_energy() -> None:
    """ⓔ ★★ **동시율을 바꿔도 연간 부하 kWh 총합이 1원도 안 바뀐다.**

    이 파일에서 **가장 중요한 시험**이다. 판정 §3 이 ⛔ 로 막은 것이 정확히
    이 자리이며, 어긋나면 결론축이 **좋아지는 쪽으로** 조용히 틀린다 —
    개선은 결함처럼 보이지 않으므로 사람 검수로는 잡히지 않는다.

    셋을 함께 잰다: ⓐ 세운 부하 자원의 1년차 연간 소비 ⓑ 대표일 운전에서
    부하가 받아들인 kWh ⓒ 그 하루의 계통 수전량. **ⓐ만 재면** 자원은 그대로
    두고 운전에서 깎는 구현이 통과한다.
    """
    full, eighty, sixty = _run(1.0), _run(0.8), _run(0.6)

    assert _load_annual_kwh(eighty) == pytest.approx(_load_annual_kwh(full))
    assert _load_annual_kwh(sixty) == pytest.approx(_load_annual_kwh(full))

    def daily_load(outcome: object) -> float:
        return -sum(outcome.dispatch.per_resource[_LOAD_NAME].electric)  # type: ignore[attr-defined]

    def daily_import(outcome: object) -> float:
        return sum(outcome.dispatch.grid_import)  # type: ignore[attr-defined]

    assert daily_load(eighty) == pytest.approx(daily_load(full))
    assert daily_load(sixty) == pytest.approx(daily_load(full))
    assert daily_import(eighty) == pytest.approx(daily_import(full))
    assert daily_import(sixty) == pytest.approx(daily_import(full))


def test_the_factor_shrinks_the_peak_shaving_benefit() -> None:
    """ⓖ **동시율이 첨두 저감 편익을 줄인다** — `reducible_peak_kw` 가 반응한다.

    걸리기만 하고 아무것도 움직이지 않으면 「반영했다」가 글자로만 성립한다 —
    이 저장소가 여섯 번 만난 형태(*선언·계산은 있는데 읽는 쪽이 없다*)의
    반대 방향이며, 그때 5.1 영향도 표는 이 축을 **변동폭 0원**으로 싣는다.

    ⚠ **비례를 요구하지 않는다.** `ESS.reducible_peak_kw` 는 부하 첨두와
    배터리 출력·에너지 중 **작은 쪽**을 취하므로, 부하를 0.8배로 낮추면
    구간에 따라 0.8배보다 덜 줄 수 있다. 재는 것은 **방향과 부호**다.
    """
    full, eighty, sixty = _run(1.0), _run(0.8), _run(0.6)

    assert _peak_shaving_won(full) > 0, (
        "100% 에서도 첨두 저감이 0 이다 — 이 실행에서는 ⓖ 를 잴 수 없다"
    )
    assert _peak_shaving_won(eighty) < _peak_shaving_won(full)
    assert _peak_shaving_won(sixty) < _peak_shaving_won(eighty)

    #: ★ 그리고 그 감소가 **결론축까지 간다** — 편익이 줄면 순현재가치도 준다.
    #: ⚠ 초기투자는 움직이지 않는다(동시율은 단가도 용량도 아니다) — 그 둘을
    #: 함께 재야 「편익만 움직였다」가 성립한다.
    assert eighty.metrics["npv"] < full.metrics["npv"]
    assert eighty.metrics["initial_outlay_won"] == pytest.approx(
        full.metrics["initial_outlay_won"]
    )


def test_the_level_map_stays_read_only_with_the_new_axis() -> None:
    """새 축이 붙어도 수준표는 읽기 전용이다 — 케이스 그리드는 병렬로 돈다.

    한 번의 변형이 **다른 케이스의 결과를 조용히 바꾼다**(NFR-205). 위
    `_levels()` 가 사본을 떠서 덮는 이유가 이것이다.
    """
    level_map = build_level_map(_ASSUMPTIONS)
    assert isinstance(level_map[_VAR], MappingProxyType)
    with pytest.raises(TypeError):
        level_map[_VAR]["base"] = 1.0  # type: ignore[index]
