"""대장 → 케이스 변수 **수준표**를 만드는 배포 경로 — NFR-202 · FR-801-AC7.quick.

## 왜 이 파일이 배포 코드에 있는가

`run_single_case_e2e()` 는 금액을 `level_map` 인자로만 받는다(모듈 상수를 두지
않은 것이 R31 의 판단이다 — 두면 대장을 고쳐도 러너가 옛 값을 쓰고 그 어긋남은
NPV 를 바꾸면서 아무 예외도 내지 않는다). **그런데 그 `level_map` 을 대장에서
만드는 코드가 테스트 안에만 있었다** — `tests/acceptance2/test_17_2_dod2.py`
의 `_build_level_map()`. 즉 *「대장이 정본이다」* 는 **인수 테스트가 도는
동안에만** 성립했고, 배포 경로에는 대장을 읽어 러너에 넘기는 자리가 아예
없었다.

R32 가 세 번 만난 형태와 같다 — **선언·계산은 있는데 읽는 쪽이 없다.** 여기서는
한 단계 더 나쁘다: 읽는 쪽이 *테스트* 였으므로 매핑표는 초록불이었다.

## 무엇이 대장에서 오고 무엇이 오지 않는가

`tariff_escalation` 은 대장에 **%/년** 으로 등재돼 있고 러너·엔진은 **비율**로
쓴다. 그래서 여기서 한 번 환산한다. 환산을 호출부에 맡기면 호출부마다 100 이
흩어지고, 그중 하나가 빠져도 「2.5% 대신 250%」가 아니라 **그럴듯한 큰 수**가
나온다.

`discount_rate` 는 대장 항목이 아니다 — 할인율은 시장에서 관측하는 단가가
아니라 **평가자가 고르는 모형 파라미터**다. 그래서 여기 적혀 있고, 그것이
사본이 되지 않도록 `tests/casegrid/test_ledger_levels.py` 가 *「대장에
할인율 항목이 생기면 빨간불」* 을 건다. 대장에 생기는 날 이 자리를 지우는 것이
맞고, 그때 아무도 모르는 것이 유일하게 나쁜 결말이다.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml  # type: ignore[import-untyped]

#: (케이스 변수, 대장 키, 배율). 배율은 **단위 환산**이며 값이 아니다 —
#: 대장의 `%/년` 을 러너가 쓰는 비율로 옮긴다.
_LEDGER_VARS: tuple[tuple[str, str, float], ...] = (
    ("pv_unit_cost", "capex.pv.rooftop", 1.0),
    ("ess_unit_cost", "capex.ess.new", 1.0),
    ("tariff_escalation", "escalation.electricity_tariff", 0.01),
    # ★ **계통에서 산 전력의 한계단가** — R34 에 배선했다.
    #
    # 이 변수가 없던 동안 러너의 비용 행은 고정 O&M 둘뿐이었고, 저장장치가
    # 심야에 계통에서 받아 온 전력을 **값 없이** 썼다. 그 결과 용량 검토가
    # *「저장장치를 키울수록 좋다」* 를 냈다 — 공짜로 받아 파는 기계였기
    # 때문이다. 대장 키가 `…energy_only` 인 이유는 그 항목의 주석에 있다
    # (기본요금은 첨두 절감 편익이 이미 세고 있어 실효단가를 쓰면 두 번 센다).
    ("grid_purchase_price", "tariff.hv_single_contract.energy_only", 1.0),
    # ★ **잉여를 파는 단가** — R35 에 올렸다. 종전에는 `e2e_runner` 안의
    # `SurplusSale(sale_price_won_per_kwh=120.0)` **리터럴**이었다.
    #
    # 그 리터럴이 위 구매 단가의 기준값(120원/kWh)과 **우연히 같았고**, 두 값은
    # 함께 움직이지 않았다. 저장장치가 심야에 사서 주간에 파는 이 구성에서
    # 왕복효율은 90% 이므로, 두 단가가 같은 동안 차익거래는 **정확히 손실효율만큼
    # 순손실**이었다 — 즉 「저장장치를 키우면 좋아지는가」의 답이 *두 리터럴이
    # 마침 같다*는 사실 위에 서 있었다. 한쪽만 대장에 있으면 대장을 고칠 때 그
    # 우연이 조용히 깨진다(`assumptions.yaml` 의 `energy_only` 항목 참조).
    #
    # ⚠ **`NFR-202` 검사가 이 리터럴을 잡지 못했다** — 판정이 |값| ≥ 1,000 만
    # 보므로 120 은 사각지대였다(「미해결」 표의 그 행). 즉 여기 올리는 것이
    # 검사를 통과시키는 일이 아니라, **검사가 볼 수 없는 자리를 없애는 일**이다.
    #
    # 대장 키를 `tariff.surplus_direct_sale`(Q-16)로 고른 근거: 구조를 주지 않은
    # 기본 경로는 상계도 특구 직접거래도 아닌 판매이며, 그것이 그 항목의
    # `applicable_scope` 문면 그대로다. 약관요금(`…avg`)을 쓰면 **소매가로 파는
    # 사업**이 되고, 그 값은 `_net_metering` 이 *회피한 요금*으로 쓰는 것이다
    # (`core/valuestream/settlement.py::TARIFF_KEY`). 새 항목을 세우지 않은 이유는
    # 같은 물리량의 단가가 대장에 둘이 되기 때문이다.
    ("surplus_sale_price", "tariff.surplus_direct_sale", 1.0),
    # ★ **교체 설비단가의 실질(물가 제외) 추세** — R42 에 배선했다 (`Q-17`).
    #
    # R41 이 대장 항목을 세웠으나 이 표가 그 키를 읽지 않아 **스윕 축이 아니었고**,
    # 그래서 5.1 영향도 표에 행으로 나오지 못했다. 가정이 대장에 보이는 것과
    # 그 가정을 흔들어 보는 것은 다르다 — 흔들지 않으면 *「0 을 골랐다」* 가
    # 결론에 얼마를 넣었는지 검토자가 알 수 없다.
    #
    # **하단 −2.0 이 이 축의 요점이다.** 실질 하락이 물가 상승과 같은 크기여서
    # **명목 교체단가가 불변**이 되는 지점이고, 그것이 곧 **R40 이전 구현**이다 —
    # 즉 그 행 하나가 *「물가 계수를 태운 판정이 결론을 얼마나 움직였는가」* 를
    # 리포트에 싣는다.
    #
    # ⚠ **배율 0.01 은 단위 환산이다** — 대장은 `%/년`, 자원은 소수를 쓴다.
    # ⚠ **이 값은 러너에서 물가 계수에 더해진다**(곱하지 않는다). 그 근거는
    # 대장 항목의 `applicable_scope` 문면이며 *「명목 변화율 = 물가 계수 + 이 값」*
    # 이라 적혀 있다 — 여기서 다시 정하지 않는다.
    ("replacement_real_trend", "capex.replacement_real_trend", 0.01),
    # ★ **PV 설비단가 중 인버터 몫** — R43 에 올렸다 (`Q-18`).
    #
    # 종전에는 `core/der/pv.py::DEFAULT_INVERTER_CAPEX_RATIO = 0.15` 라는
    # **소스 상수**였고 어느 케이스 축에도 없었다. 그런데 R39-E 가
    # 교체비·잔존가치를 배선하면서 **처음으로 결론에 들어왔다** —
    # 흔들어 보지 않으므로 5.1 영향도 표에 오르지 못했고, 그것은
    # *「0.15 를 골랐다」가 결론에 얼마를 넣었는지를 검토자가 알 수 없는*
    # 상태다. `surplus_sale_price` 의 리터럴 `120.0` 과 **같은 형태**이며
    # `NFR-202` 검사가 |값| ≥ 1,000 만 보므로 `0.15` 도 사각지대였다 —
    # 즉 이 줄은 검사를 통과시키는 일이 아니라 **검사가 볼 수 없는 자리를
    # 없애는 일**이다.
    #
    # ⚠ **배율 0.01 은 단위 환산이다** — 대장은 `%`, 자원은 소수를 쓴다.
    # ⚠ **이 값은 비율이지 금액이 아니다.** 러너가
    # `pv_unit_cost × 이 값` 으로 인버터 단가를 짓고 `PV(...)` 에 넘긴다 —
    # 그래서 용량·단가 스윙과 함께 움직인다. 모듈 상수는 지우지 않고
    # **자원 단독 사용 시의 기본값**으로 남겨 두었다.
    ("pv_inverter_share", "capex.pv.inverter_share", 0.01),
    # ★ **첨두 기본요금 단가** — R43 에 올렸다 (`Q-6`).
    #
    # 종전에는 `e2e_runner.DEMAND_CHARGE_WON_PER_KW_MONTH = 8_320.0` 이라는
    # **소스 상수**였고 대장에도 축에도 없었다. 그런데 이 단가는 첨두 절감
    # 편익 199,680원(**전체 편익의 21%**)을 혼자 정한다 — 즉 결론의 5분의 1이
    # *출처를 말하지 않는 수* 위에 서 있었다(문의사항 나-8).
    #
    # ⚠ **`NFR-202` 검사가 못 잡은 이유가 앞의 둘과 다르다.** `surplus_sale_price`
    # 의 `120.0` 과 인버터 몫의 `0.15` 는 |값| < 1,000 이라 **판정 대역 밖**
    # 이었다. 8,320 은 대역 **안**인데도 통과했다 — 그 검사가 재는 것은
    # *대장의 값이 소스에 복제되었는가*이고, **대장에 없는 값은 대조할 상대가
    # 없다.** 문턱을 낮춰도 잡히지 않는 형태이며, 잡히게 만드는 유일한 방법이
    # 대장에 올리는 것이다.
    #
    # ⚠ **배율 1.0 이다** — 대장도 러너도 `원/kW·월` 을 쓴다. 연 12개월을
    # 곱하는 것은 `ESS.peak_shaving_benefit()` 안이며 여기서 하지 않는다.
    # ⚠ **`grid_purchase_price` 와 반대 방향으로 상관된다.** 실효단가에서
    # 기본요금 안분을 뺀 것이 그 한계단가이므로(대장 `…energy_only` 의
    # `derivation_method`), 기본요금이 커지면 한계단가는 작아진다. 5.1 은
    # 1변수 스윕이라 그 상관을 재지 않는다 — 대장의 `impact_note` 가 그
    # 사실을 적어 둔다.
    ("demand_charge", "tariff.hv_single_contract.demand_charge", 1.0),
    # ★ **가구 부하 총량** — R48/WP-B 에 올렸다 (판정 B-1,
    # `docs/decisions-2026-08-31-R48.md` §5).
    #
    # 종전에는 이 값을 대장에서 읽어 스윕하는 자리가 없었다 — `case_report.py`
    # 가 붙임 7(가정 운전)에서만 `provider.get(LOAD_LEDGER_KEY)` 로 직접
    # 읽었고, 본 실행·5.1 영향도 스윕은 이 값을 아예 보지 않았다(부하 자원을
    # 세우지 않았다). 이제 본 실행도 부하를 세우므로(`case_report.py`) 이
    # 축이 없으면 그 결론이 3,600kWh 상수 위에 서고 흔들어 볼 수 없다 —
    # `surplus_sale_price`·`demand_charge` 가 올라온 것과 같은 이유다.
    #
    # ⚠ **배율 1.0 이다** — 대장·러너 둘 다 kWh/호·년 을 쓴다.
    ("household_load_annual_kwh", "load.household.annual", 1.0),
)

#: 대장 항목이 **아닌** 모형 파라미터. 위 독스트링 참조.
_MODELLING_VARS: tuple[tuple[str, tuple[tuple[str, float], ...]], ...] = (
    ("discount_rate", (("low", 0.030), ("base", 0.045), ("high", 0.060))),
)

#: **설계 변수** — 사업자가 *고르는* 설비 용량. 셋째 갈래이며 앞의 둘과 다르다.
#:
#:     대장 변수    시장에서 관측한다   → 틀릴 수 있다   → 확보 대상 (5.1)
#:     모형 파라미터 평가자가 정한다     → 선택이다      → 확보 대상 아님 (5.2)
#:     설계 변수    사업자가 고른다     → **설계다**    → 적정값을 묻는다 (4.4)
#:
#: ⚠ **여기 오기 전에는 `e2e_runner` 의 모듈 상수였다** — 즉 용량은 어느
#: 케이스 축에도 없었고, 리포트는 *「3kW·10kWh 가 맞는가」* 를 **묻지도
#: 답하지도 못했다.** 상수로 두면 27 케이스를 다 돌려도 용량은 한 값이다.
#:
#: 범위는 **탐색 구간**이지 불확실성이 아니다. 대장의 `sensitivity` 와 같은
#: 이름(low·base·high)을 쓰되 뜻이 다르므로, 리포트가 이 변수를 5.1 의
#: 불확실 인자와 **같은 표에 싣지 않는다** (`design_variables()` 로 가른다).
#: (변수, 단위, 사람이 읽는 이름, 탐색 구간)
_DESIGN_VARS: tuple[tuple[str, str, str, tuple[tuple[str, float], ...]], ...] = (
    (
        "pv_capacity_kw",
        "kW",
        "태양광 용량",
        (("low", 1.0), ("base", 3.0), ("high", 9.0)),
    ),
    (
        "ess_capacity_kwh",
        "kWh",
        "저장장치 용량",
        (("low", 2.0), ("base", 10.0), ("high", 30.0)),
    ),
)

#: 수준 이름. 대장의 `sensitivity` 가 이 셋을 갖지 않으면 거부한다.
LEVEL_NAMES: tuple[str, str, str] = ("low", "base", "high")


def modelling_only_variables() -> tuple[str, ...]:
    """대장에서 오지 않는 변수 이름 — 검사가 이 목록을 읽는다."""
    return tuple(name for name, _ in _MODELLING_VARS)


@dataclass(frozen=True)
class DesignVariable:
    """설계 변수 하나 — 리포트 4.4 의 한 행."""

    name: str
    unit: str
    label: str
    low: float
    base: float
    high: float


def design_variables() -> tuple[DesignVariable, ...]:
    """설계 변수와 탐색 구간. **리포트 4.4(적정 용량)가 이 목록을 읽는다.**

    밖으로 내놓는 이유는 5.1(확보 대상)·5.2(평가자 선택)와 **갈라 실어야**
    하기 때문이다. 셋을 한 표에 두면 *「단가를 더 알아보라」* 와 *「용량을 다시
    골라라」* 가 같은 우선순위 표에서 경쟁하고, 그 둘은 받는 사람이 다르다.
    """
    return tuple(
        DesignVariable(
            name=name,
            unit=unit,
            label=label,
            low=dict(levels)["low"],
            base=dict(levels)["base"],
            high=dict(levels)["high"],
        )
        for name, unit, label, levels in _DESIGN_VARS
    )


def design_levels() -> Mapping[str, Mapping[str, float]]:
    """설계 변수만의 수준표 — `build_level_map()` 이 넣는 것과 **같은 것**.

    ## 왜 따로 내놓는가

    러너는 용량을 `level_map` 에서만 읽고 **기본값을 두지 않는다**(모듈 상수를
    남기면 수준표를 고쳐도 옛 용량이 쓰이고 NPV 만 조용히 달라진다). 그래서
    대장을 읽지 않고 배선만 보는 호출부도 용량을 넘겨야 한다. 그 호출부가
    숫자를 **손으로 적으면 그것이 사본**이 되고, 탐색 구간을 옮기는 날 조용히
    갈라진다 — 여기서 내놓아 한 곳만 고치면 되게 한다.
    """
    return MappingProxyType(
        {
            name: MappingProxyType(dict(levels))
            for name, _unit, _label, levels in _DESIGN_VARS
        }
    )


def ledger_backed_variables() -> Mapping[str, str]:
    """케이스 변수 → 대장 키. 리포트가 부기 7종을 붙일 때 쓴다."""
    return MappingProxyType({name: key for name, key, _ in _LEDGER_VARS})


def ledger_unit_scales() -> Mapping[str, float]:
    """케이스 변수 → **대장 값에 곱한 배율**.

    ## 왜 밖으로 내놓는가 (R33 검토 반영)

    리포트가 인자의 사용값과 **대장의 단위 문면**을 같은 행에 싣는데, 값은
    여기서 환산된 것이고 단위는 대장 것이다. 그대로 두면
    **「0.025 %/년」** 처럼 값과 단위가 어긋난 표시가 나간다 — 실제 2.5%/년의
    100분의 1로 읽히는, 조용하고 치명적인 오독이다.

    배율을 리포트 쪽에 다시 적으면 사본이 되므로 **여기서 내놓는다.** 리포트는
    나눠서 대장 단위로 되돌려 표시하고, 계산에는 환산된 값이 그대로 쓰인다.
    """
    return MappingProxyType({name: scale for name, _, scale in _LEDGER_VARS})


def _index_by_key(path: Path) -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {item["key"]: item for item in data.get("assumptions", [])}


def _levels_of(item: Mapping[str, Any], key: str, scale: float) -> Mapping[str, float]:
    """대장 항목의 `sensitivity` 3수준을 꺼낸다.

    **없으면 기본 ±20% 로 메우지 않는다.** `FR-1002-AC2` 의 「없으면 기본
    ±20%」는 *영향도 산출* 의 폴백이지 *케이스 그리드 수준* 의 폴백이 아니다 —
    여기서 메우면 대장이 3수준을 잃은 것과 「±20% 를 골랐다」가 구별되지 않고,
    그 상태로 27 케이스가 돈다.
    """
    sensitivity = item.get("sensitivity")
    if not isinstance(sensitivity, Mapping):
        # 메시지가 「어느 항목이」·「왜」·「어떻게」 셋을 담는다 (NFR-303-M1).
        raise ValueError(
            f"대장 항목 {key!r} 에 sensitivity 3수준이 없습니다. "
            "케이스 그리드는 low·base·high 를 대장에서 읽습니다 — "
            "docs/assumptions.yaml 에 등재하십시오"
        )
    missing = [name for name in LEVEL_NAMES if name not in sensitivity]
    if missing:
        raise ValueError(
            f"대장 항목 {key!r} 의 sensitivity 에 {', '.join(missing)} 이(가) "
            f"없습니다. 3수준 전건({', '.join(LEVEL_NAMES)})이 있어야 합니다"
        )
    return MappingProxyType(
        {name: float(sensitivity[name]) * scale for name in LEVEL_NAMES}
    )


def build_level_map(assumptions_path: Path) -> Mapping[str, Mapping[str, float]]:
    """대장을 읽어 `run_single_case_e2e(level_map=...)` 에 넘길 수준표를 만든다.

    반환값은 전부 읽기 전용이다 — 케이스 그리드는 병렬로 돌고, 한 번의 변형이
    다른 케이스의 결과를 조용히 바꾼다 (NFR-205).
    """
    items = _index_by_key(assumptions_path)
    level_map: dict[str, Mapping[str, float]] = {}

    for var_name, ledger_key, scale in _LEDGER_VARS:
        item = items.get(ledger_key)
        if item is None:
            raise ValueError(
                f"대장에 {ledger_key!r} 항목이 없습니다 (케이스 변수 "
                f"{var_name!r}). docs/assumptions.yaml 을 확인하십시오"
            )
        level_map[var_name] = _levels_of(item, ledger_key, scale)

    for var_name, levels in _MODELLING_VARS:
        level_map[var_name] = MappingProxyType(dict(levels))

    for var_name, _unit, _label, levels in _DESIGN_VARS:
        level_map[var_name] = MappingProxyType(dict(levels))

    return MappingProxyType(level_map)
