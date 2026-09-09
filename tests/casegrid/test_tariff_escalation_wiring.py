"""전기요금 인상률이 **비용과 편익 양쪽에 동시에** 닿는가 — R69/WP-2.

`escalation.electricity_tariff`(케이스 축 `tariff_escalation`)는 대장에도
케이스 그리드 프리셋(`core/casegrid/grid.py` 의 빠른·전체 탐색)에도 서 있었는데
**러너에 소비자가 0곳이었다.** 값을 끝에서 끝까지 흔들어도 결론축이 0원
움직였고, 「미반영 항목」 표가 그 사실을 신고하고 있었다
(`tests/report/test_ledger_axes_wired.py::DEAD_AXES` · R68/WP-8 실측).

## ★★★ 이 파일이 붙드는 것은 **배선**이 아니라 «대칭»이다

배선만 재는 검사는 *「인상률을 올리면 NPV 가 움직인다」* 로 초록불이 된다.
그런데 **비용에만 걸어도 그 검사는 통과한다** — 그리고 그것이 정확히 이
저장소가 피하려던 오류다. `core/cba/proforma.py::energy_purchase_row` 독스트링이
그 함정을 여러 라운드 적어 두었다:

    비용만 올리면 **편익은 그대로 둔 채 비용만 커져** 사업에 불리하게 틀린다.
    NSPM 대칭성이며, 요금 인상률은 비용·편익 **양쪽에 동시에** 배선한다.

실측(R69/WP-2)으로 그 크기가 나왔다 — 골든 시나리오 20년 NPV 에서 대칭으로
걸면 **−32,785,896원**, 비용에만 걸면 **−41,717,709원**이다. 즉 **약 890만원이
「대칭을 지켰는가」 하나에 달려 있고**, 어느 쪽도 단독으로는 이상해 보이지 않는다.

⇒ 그래서 이 파일은 반쪽씩 **따로** 잰다. 편익 쪽을 끄고 비용이 오르는지, 비용
쪽을 끄고 편익이 오르는지 — **두 검사가 서로의 반증**이다.

## 왜 그 「양쪽」이 상계 크레딧이 아닌가 (판정 근거를 남긴다)

배포 경로는 `_net_metering`(상계)을 지나지 않는다 — 실측: 골든 실행 한 벌 동안
`TariffEngine` 생성 0회 · `core/valuestream/settlement.py::assemble()` 호출
0회이며, `SurplusSale` 은 역송 0kWh 라 0원이다. 배포 경로에서 같은 요금표를
쓰는 **편익**은 하나뿐이다:

    비용  `GridPurchase`  ← `tariff.hv_single_contract.energy_only`
    편익  `PeakShaving`   ← `tariff.hv_single_contract.demand_charge`
                            (**회피한** 기본요금 — 요금이 오르면 함께 오른다)

두 대장 키가 **같은 요금표의 다른 칸**이라는 것이 이 대칭의 근거다. 조사 경위와
계측은 `.orch/R69/result_2.md` 와 오케스트레이터 판정 `.orch/R69/WP-2-fix.md` ②
가 갖는다.

## ⚠ `REC`·`SurplusSale` 에는 걸지 않는다

`annual_benefit` 에는 REC·NWAs·CP·잉여판매가 함께 들어 있고 **그것들은 요금표가
정하는 값이 아니다.** 편익 전액에 계수를 곱하면 REC 단가가 전기요금 인상률로
오르게 되는데, 그 상태도 「인상률을 올리면 NPV 가 움직인다」로는 초록불이다 —
아래 ③ 이 그 갈래를 가른다.

## ⚠ `@pytest.mark.req(...)` 를 이 파일에 달지 않은 것이 아니다

`FR-701-AC3`(*「항목별 상이한 에스컬레이션 적용 가능」*)이 이 배선의 조항이며
프로포마 쪽 계약(`tests/cba/test_proforma.py`)도 같은 수용기준을 짚는다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.models import CaseOutcome
from core.casegrid.profiles import load_daily_shapes
from core.report.case_influences import CONCLUSION_METRIC

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"

#: 흔든 인상률(비율). **대장 띠의 위 끝(4.0 %/년)과 같은 수를 일부러 쓰지
#: 않는다** — 이 파일이 재는 것은 「대장 값이 맞는가」가 아니라 **「축을 흔들면
#: 양쪽이 함께 움직이는가」**이고, 대장을 읽으면 띠를 옮기는 날 이 검사의 뜻이
#: 함께 흔들린다. 대장 값으로 축이 살아 있는지는 다른 검사가 잰다
#: (`tests/report/test_ledger_axes_wired.py`).
_SHAKEN = 0.05

#: **끈 값.** 계수가 전 연차 1.0 이 되어 이 축을 배선하기 전과 같다.
_OFF = 0.0

_PROBE_HORIZON = 20

#: 단지 규모 — 첨두 절감이 0 이 아니려면 **부하가 있어야** 한다. 정본은
#: `tests/casegrid/test_household_count.py::_COUNT` 가 갖는다.
_COUNT = 2


def _levels(
    *,
    escalation: float,
    purchase_price: float | None = None,
    demand_charge: float | None = None,
) -> dict[str, dict[str, float]]:
    """대장 수준표를 읽어 **이 파일이 흔드는 축만** 덮어쓴다.

    탐침 수준표를 손으로 짓지 않는 이유: 축이 하나 늘 때마다 그 사본이 낡고,
    낡은 사본은 「러너가 요구한다」는 오류로만 드러난다(형제 파일 열셋이 실제로
    그렇게 축마다 함께 고쳐져 왔다). 여기서는 **대장이 정본**이고 이 파일은
    흔드는 값만 갖는다.

    ⚠ 세 수준(`low`·`base`·`high`)을 **같은 값으로** 덮는다 — 러너 본 실행은
    `base` 만 읽지만, 한 수준만 덮으면 이 파일을 스윕 쪽에서 재사용할 때
    본문과 스윕이 다른 값으로 도는 함정이 생긴다.
    """
    level_map = {name: dict(levels) for name, levels in build_level_map(_ASSUMPTIONS).items()}
    overrides = {
        "tariff_escalation": escalation,
        "grid_purchase_price": purchase_price,
        "demand_charge": demand_charge,
    }
    for name, value in overrides.items():
        if value is not None:
            level_map[name] = dict.fromkeys(level_map[name], value)
    return level_map


def _run(
    *,
    escalation: float,
    purchase_price: float | None = None,
    demand_charge: float | None = None,
    horizon_years: int = _PROBE_HORIZON,
) -> CaseOutcome:
    """한 벌 돌린다 — **부하가 있는 단지**로.

    ⚠ **부하를 주지 않으면 첨두 절감이 0 원이다**(실측). 그러면 편익 쪽 절반을
    재는 ② 가 「배선되지 않았다」와 「깎을 첨두가 없었다」를 구별하지 못한 채
    빨간불이 된다 — 형상·부하·단지 규모를 함께 주는 이유가 그것이며,
    `tests/casegrid/test_coincidence_factor_wiring.py` 가 같은 구성을 쓴다.
    """
    level_map = _levels(
        escalation=escalation,
        purchase_price=purchase_price,
        demand_charge=demand_charge,
    )
    return run_single_case_e2e(
        {},
        level_map=level_map,
        horizon_years=horizon_years,
        daily_shapes=load_daily_shapes(),
        annual_load_kwh=level_map["household_load_annual_kwh"]["base"],
        household_count=_COUNT,
    )


def _npv(**kwargs: float | None) -> float:
    outcome = _run(**kwargs)  # type: ignore[arg-type]
    return float(outcome.metrics[CONCLUSION_METRIC])


@pytest.mark.req("FR-701-AC3")
def test_the_escalation_raises_the_cost_of_bought_electricity() -> None:
    """★★★ ① **비용 쪽 절반** — 편익 쪽을 끄고 잰다.

    기본요금 단가를 0 으로 두면 첨두 절감 편익이 0 이 되어 요금 연동 편익이
    사라진다. 그 상태에서 인상률을 올렸는데 결론축이 나빠지지 않으면
    **비용 쪽이 배선되지 않은 것**이다.
    """
    off = _npv(escalation=_OFF, demand_charge=0.0)
    shaken = _npv(escalation=_SHAKEN, demand_charge=0.0)

    assert shaken < off, (
        f"요금을 연 {_SHAKEN:.1%} 올렸는데 결론축이 {off:,.0f}원 → "
        f"{shaken:,.0f}원 으로 나빠지지 않는다 — 계통에서 사 오는 전력의 값이 "
        "인상률을 타지 않는다(`energy_purchase_row(escalation_rate=)`)"
    )


@pytest.mark.req("FR-701-AC3")
def test_the_same_escalation_raises_the_avoided_demand_charge() -> None:
    """★★★ ② **편익 쪽 절반** — 비용 쪽을 끄고 잰다. **이것이 대칭 검사다.**

    구매 단가를 0 으로 두면 요금 연동 **비용**이 사라진다. 그 상태에서
    인상률을 올렸는데 결론축이 좋아지지 않으면 **회피한 기본요금이 인상률을
    타지 않는 것**이고, 그러면 실행 전체는 「비용만 오르는」 비대칭이 된다 —
    ① 만 있으면 그 상태가 초록불로 통과한다.
    """
    off = _npv(escalation=_OFF, purchase_price=0.0)
    shaken = _npv(escalation=_SHAKEN, purchase_price=0.0)

    assert shaken > off, (
        f"요금을 연 {_SHAKEN:.1%} 올렸는데 결론축이 {off:,.0f}원 → "
        f"{shaken:,.0f}원 으로 좋아지지 않는다 — 회피한 기본요금(첨두 절감)이 "
        "인상률을 타지 않는다. 비용에만 걸린 상태이며, 그 비대칭은 합계만 "
        "보면 그럴듯하다"
    )


@pytest.mark.req("FR-701-AC3")
def test_the_escalation_does_not_touch_benefits_the_tariff_does_not_price() -> None:
    """★★ ③ **요금표가 정하지 않는 편익에는 걸지 않는다.**

    요금 연동 비용·편익을 **둘 다** 끄면(구매 단가 0 · 기본요금 단가 0) 남는
    편익은 REC·잉여판매처럼 요금표가 정하지 않는 것들뿐이다. 그때 인상률을
    끝까지 흔들어도 결론축은 **한 원도** 움직이지 않아야 한다.

    걸리는 구현: 편익 **전액**에 계수를 곱하는 것. 그러면 REC 단가가 전기요금
    인상률로 오르는데, ①②만 보면 그 상태도 초록불이다.
    """
    off = _npv(escalation=_OFF, purchase_price=0.0, demand_charge=0.0)
    shaken = _npv(escalation=_SHAKEN, purchase_price=0.0, demand_charge=0.0)

    assert shaken == pytest.approx(off, abs=1.0), (
        f"요금 연동 항을 둘 다 껐는데 결론축이 {off:,.0f}원 → {shaken:,.0f}원 "
        "으로 움직인다 — 요금표가 정하지 않는 편익(REC·잉여판매 등)에까지 "
        "요금 인상률이 걸려 있다"
    )


@pytest.mark.req("FR-701-AC3")
def test_the_first_year_is_the_base_year_so_a_one_year_run_does_not_move() -> None:
    """★★ ④ **1년차가 기준연도다** — 계수 `(1+r)^0 = 1.0`.

    분석기간을 1년으로 두면 프로포마에 1년차밖에 없으므로, 인상률을 끝까지
    흔들어도 결론축이 움직이면 **기준연도가 한 해 밀린 것**이다. 20년 실행에서
    그 밀림은 누계를 수 % 바꾸면서 **어느 행에도 이름으로 나타나지 않는다**
    (`core/contracts/der.py::DER.escalation_factor` 가 같은 판단을 갖는다).
    """
    off = _npv(escalation=_OFF, horizon_years=1)
    shaken = _npv(escalation=_SHAKEN, horizon_years=1)

    assert shaken == pytest.approx(off, abs=1.0), (
        f"1년 실행인데 인상률이 결론축을 {off:,.0f}원 → {shaken:,.0f}원 으로 "
        "움직인다 — 1년차에 이미 계수가 걸렸다(기준연도가 0년차로 밀렸다)"
    )
