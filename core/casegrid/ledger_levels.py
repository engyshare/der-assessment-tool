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
)

#: 대장 항목이 **아닌** 모형 파라미터. 위 독스트링 참조.
_MODELLING_VARS: tuple[tuple[str, tuple[tuple[str, float], ...]], ...] = (
    ("discount_rate", (("low", 0.030), ("base", 0.045), ("high", 0.060))),
)

#: 수준 이름. 대장의 `sensitivity` 가 이 셋을 갖지 않으면 거부한다.
LEVEL_NAMES: tuple[str, str, str] = ("low", "base", "high")


def modelling_only_variables() -> tuple[str, ...]:
    """대장에서 오지 않는 변수 이름 — 검사가 이 목록을 읽는다."""
    return tuple(name for name, _ in _MODELLING_VARS)


def ledger_backed_variables() -> Mapping[str, str]:
    """케이스 변수 → 대장 키. 리포트가 부기 7종을 붙일 때 쓴다."""
    return MappingProxyType({name: key for name, key, _ in _LEDGER_VARS})


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

    return MappingProxyType(level_map)
