"""편익 8종의 **탐침 인자** — 계약 검사 둘이 함께 쓴다.

## 왜 한 표인가

연간화 규약 검사(`test_annualisation_convention.py`)와 산식 대입값 검사
(`test_benefit_formula.py`)가 둘 다 *「배포된 편익 전건을 세워 본다」* 를 한다.
표를 각자 들면 **편익이 늘 때 한쪽만 갱신되고**, 갱신되지 않은 쪽은 그 편익을
건너뛰면서 **초록불로 남는다** — 목록을 손으로 적지 않는 이 저장소의 규칙이
막으려는 것과 같은 형태다.

⚠ **대장 값을 쓰지 않는다.** 이 표가 대장을 읽으면 대장이 바뀔 때 두 검사의
판정이 함께 흔들리고, 그러면 계약 검사가 **금액 검사를 겸하게** 된다. 금액이
맞는지는 진입점 검사가 대장과 자원 제원으로 따로 본다.

⚠ **DoD 공장(`_create_valuestream_for_tag`)을 쓰지 않는다.** 그 공장은 배타
규칙표에 오르는 태그만 만들며 `HeatCostSaving` 에서 멈춘다 — 재지 못한 편익을
건너뛰면 그 선언은 아무도 확인하지 않은 채 남는다.

★ **값을 서로 다르게 둔다.** 두 인자가 같은 수면 산식이 한쪽만 싣고도
「전건 실렸다」로 통과한다 — 대입값 검사가 값의 **존재**를 보기 때문이다.
"""
from __future__ import annotations

from core.contracts.registry import discover
from core.contracts.valuestream import ValueStream
from core.valuestream.distributed_benefit import DistributedSubItems

#: 편익마다의 탐침 인자. 금액에 뜻은 없다 — 0이 아니고 서로 다르기만 하면 된다.
PROBES: dict[str, dict[str, object]] = {
    "SurplusSale": {"sale_price_won_per_kwh": 100.0},
    "REC": {"weight": 1.5, "rec_price_won_per_unit": 50_000.0},
    "SelfConsumption": {
        "baseline_annual_bill_won": 1_000_000.0,
        "new_annual_bill_won": 700_000.0,
    },
    "HeatCostSaving": {
        "baseline_fuel_cost_won_per_year": 900_000.0,
        "hp_electricity_cost_won_per_year": 400_000.0,
    },
    #: ★ **하위 항목에 실제 값을 준다** (R36). 종전 `None` 이라 이 편익은 두
    #: 검사 모두에서 **아무것도 재지 않은 채** 지나갔다 — 연간화 검사는 전부
    #: 0원이라 건너뛰었고, 산식 검사는 대조할 대입값이 없었다. 다섯을 서로 다른
    #: 수로 두어 산식이 **다섯을 다 싣는가**를 볼 수 있게 했다.
    "DistributedBenefit": {
        "sub_items": DistributedSubItems(
            transmission_avoidance_won=11_000.0,
            loss_reduction_won=22_000.0,
            grid_service_won=33_000.0,
            ghg_reduction_won=44_000.0,
            resilience_won=55_000.0,
        )
    },
    "DirectTrade": {
        "tariff_won_per_kwh": 150.0,
        "trade_price_won_per_kwh": 130.0,
        "trade_volume_kwh": 4_000.0,
        #: ★ **0을 두지 않는다.** 기본값 0이면 산식이 수수료 항을 빼먹어도
        #: 「0원이 실렸다」로 통과할 수 있다.
        "support_fee_won": 7_000.0,
    },
    "PeakShaving": {
        "monthly_peak_reduction_kw": [2.0] * 12,
        "demand_charge_won_per_kw_month": 8_000.0,
    },
    "AggregatedPPA": {
        "ppa_price_won_per_kwh": 120.0,
        "annual_generation_kwh": 4_000.0,
    },
}


def deployed_streams() -> tuple[type[ValueStream], ...]:
    """배포 편익 전건 — 레지스트리에서 온다.

    목록을 손으로 적으면 편익이 늘 때 낡고, 낡은 목록은 **새 편익을 검사에서
    빼면서 초록불로 남는다**(`NFR-207-AC1` 이 같은 이유로 레지스트리를 요구한다).
    """
    import core.valuestream

    return tuple(
        discover(core.valuestream, ValueStream).values()  # type: ignore[type-abstract]
    )


def assert_every_stream_has_a_probe() -> None:
    """탐침이 없는 편익이 있으면 **거기서 멈춘다**.

    건너뛰게 두면 새 편익의 계약 준수가 아무도 확인하지 않은 채 남는다.
    """
    missing = sorted(cls.tag for cls in deployed_streams() if cls.tag not in PROBES)
    assert not missing, (
        f"탐침 인자가 없는 편익이 있다: {', '.join(missing)} — 편익을 늘리면 "
        "이 표에 탐침을 함께 적는다"
    )
