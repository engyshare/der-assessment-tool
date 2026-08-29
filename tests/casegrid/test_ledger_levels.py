"""수준표를 **대장에서** 만드는가 — NFR-202 · NFR-205.

종전에 이 변환은 `tests/acceptance2/test_17_2_dod2.py` 안에만 있었다. 그래서
*「금액의 정본은 대장이다」* 가 **그 인수 테스트가 도는 동안에만** 성립했고,
러너를 부르는 배포 코드에는 대장을 읽는 자리가 없었다 — R32 가 세 번 만난
「선언은 있는데 읽는 쪽이 없다」의 변형이며, 읽는 쪽이 테스트였으므로 매핑표는
초록불이었다.

이 파일이 붙드는 것은 함수가 아니라 **어디서 값이 오는가**다.

    대장 값이 그대로 온다              ← 사본을 두지 않았다
    `%/년` 은 비율로 환산된다          ← 환산이 호출부에 흩어지지 않는다
    수준표는 읽기 전용이다             ← 병렬 실행이 서로를 바꾸지 않는다 (NFR-205)
    3수준이 없으면 거부한다            ← ±20% 로 조용히 메우지 않는다
    ★ 대장에 할인율이 생기면 빨간불    ← 사본이 남는 유일한 자리를 지킨다
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.casegrid.ledger_levels import (
    LEVEL_NAMES,
    build_level_map,
    ledger_backed_variables,
    modelling_only_variables,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS_YAML = _REPO_ROOT / "docs" / "assumptions.yaml"


def _ledger_items() -> dict[str, dict]:
    data = yaml.safe_load(_ASSUMPTIONS_YAML.read_text(encoding="utf-8"))
    return {item["key"]: item for item in data["assumptions"]}


@pytest.mark.req("NFR-202-M1")
def test_levels_come_from_the_ledger_not_from_a_copy() -> None:
    """대장 값이 **그대로** 수준표에 온다 — 기대값을 여기 적지 않는다.

    기대 수치를 이 파일에 적으면 그것이 사본이 되고, 대장을 고칠 때 여기가
    따라오지 않아도 아무 일이 없다. 그래서 대장을 **다시 읽어** 대조한다.
    """
    level_map = build_level_map(_ASSUMPTIONS_YAML)
    items = _ledger_items()

    for var_name, ledger_key in ledger_backed_variables().items():
        sensitivity = items[ledger_key]["sensitivity"]
        levels = level_map[var_name]
        assert set(levels) == set(LEVEL_NAMES), (
            f"{var_name}: 3수준 전건이 아니다 — {sorted(levels)}"
        )
        assert levels["low"] < levels["base"] < levels["high"], (
            f"{var_name}: 수준 순서가 무너졌다 — {dict(levels)}"
        )
        # 배율을 여기서 다시 적지 않는다. 비율이 일정한지만 본다.
        #
        # ⚠ **0 인 수준은 비율을 낼 수 없다** — `Q-17`
        # (`capex.replacement_real_trend`)의 `base` 가 0 이고, R42 가 그것을
        # 스윕 축으로 올리며 이 자리를 처음 밟았다(`ZeroDivisionError`).
        # 0 은 어떤 배율을 곱해도 0 이므로 그 수준으로는 「배율이 일정한가」를
        # 물을 수 없다. **0 은 0 으로 오는 것만 확인**하고, 비율은 0 이 아닌
        # 수준끼리 본다 — 확인 못 하는 것을 확인한 척하지 않는다.
        zero_levels = [n for n in LEVEL_NAMES if float(sensitivity[n]) == 0.0]
        for name in zero_levels:
            assert levels[name] == 0.0, (
                f"{var_name}: 대장의 {name} 이 0 인데 수준표가 "
                f"{levels[name]} 을 냈다 — 환산이 0 을 0 이 아닌 것으로 바꿨다"
            )
        ratios = {
            name: levels[name] / float(sensitivity[name])
            for name in LEVEL_NAMES
            if name not in zero_levels
        }
        assert len(set(round(r, 12) for r in ratios.values())) == 1, (
            f"{var_name}: 수준마다 다른 배율이 걸렸다 — {ratios}"
        )


@pytest.mark.req("NFR-202-M1")
def test_percent_per_year_is_converted_once() -> None:
    """`%/년` 항목은 **비율**로 온다 — 환산이 호출부로 새지 않는다.

    새면 호출부마다 `/ 100` 이 흩어지고, 그중 하나가 빠져도 「2.5% 대신
    250%」가 아니라 **그럴듯한 큰 수**가 나온다.
    """
    items = _ledger_items()
    level_map = build_level_map(_ASSUMPTIONS_YAML)

    for var_name, ledger_key in ledger_backed_variables().items():
        unit = items[ledger_key].get("value_unit", "")
        if not unit.startswith("%"):
            continue
        ledger_base = float(items[ledger_key]["sensitivity"]["base"])
        assert level_map[var_name]["base"] == pytest.approx(ledger_base / 100.0), (
            f"{var_name}({ledger_key}): 단위가 {unit!r} 인데 환산되지 않았다"
        )
        assert level_map[var_name]["base"] < 1.0, (
            f"{var_name}: 비율이 1.0 이상이다 — 퍼센트가 그대로 들어왔다"
        )


@pytest.mark.req("NFR-205-M1")
def test_level_map_is_read_only() -> None:
    """수준표를 밖에서 고칠 수 없다 — 케이스 그리드는 병렬로 돈다.

    한 번의 변형이 **다른 케이스의 결과를 조용히 바꾼다**. 읽기 전용으로
    쓰고 있다는 것은 다음 사람도 그럴 것이라는 보장이 아니다.
    """
    level_map = build_level_map(_ASSUMPTIONS_YAML)
    with pytest.raises(TypeError):
        level_map["pv_unit_cost"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        level_map["pv_unit_cost"]["base"] = 1.0  # type: ignore[index]


@pytest.mark.req("NFR-202-M1")
def test_missing_sensitivity_is_refused_not_filled(tmp_path: Path) -> None:
    """3수준이 없으면 **거부한다** — ±20% 로 메우지 않는다.

    메우면 「대장이 3수준을 잃었다」와 「±20% 를 골랐다」가 구별되지 않고,
    그 상태로 27 케이스가 돈다.
    """
    ledger = tmp_path / "assumptions.yaml"
    ledger.write_text(
        "price_basis: 명목\nassumptions:\n"
        '  - key: "capex.pv.rooftop"\n    value: 1\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as excinfo:
        build_level_map(ledger)
    message = str(excinfo.value)
    assert "capex.pv.rooftop" in message, "어느 항목인지 말하지 않는다"
    assert "sensitivity" in message, "왜 거부됐는지 말하지 않는다"
    assert "assumptions.yaml" in message, "어디를 고치라는지 말하지 않는다"


@pytest.mark.req("NFR-202-M1")
def test_modelling_parameters_are_not_in_the_ledger() -> None:
    """★ **래칫.** 대장에 할인율 항목이 생기면 이 검사가 빨간불이 된다.

    `discount_rate` 는 지금 대장 항목이 아니므로 `ledger_levels.py` 가 값을
    들고 있다. 대장에 등재되는 날 그 값은 **사본**이 되고, 사본은 한쪽만
    고쳐진다. 그때 아무도 모르는 것이 유일하게 나쁜 결말이므로 여기서 잡는다.
    """
    ledger_keys = set(_ledger_items())
    for var_name in modelling_only_variables():
        suffix = var_name.replace("_", ".")
        offenders = [key for key in ledger_keys if key.endswith(suffix)]
        assert not offenders, (
            f"대장에 {offenders} 가 생겼습니다 — 모형 파라미터 {var_name!r} 의 "
            "값이 이제 사본입니다. core/casegrid/ledger_levels.py 의 "
            "_MODELLING_VARS 에서 그 줄을 지우고 _LEDGER_VARS 로 옮기십시오"
        )
