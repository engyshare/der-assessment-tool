"""달성영역 격자가 **좌표당 한 칸**인가 — `FR-803-AC1` / R31 (결정 §8).

`docs/clause-recheck-2026-08-14.md` 판정: *「`analysis.feasible_region()` 이 축 2개
외 변수를 집계·슬라이스하지 않아 **27케이스에 3×3 격자를 주면 좌표당 3중복**이
된다」*. 그리고 *「프리셋 축은 `"low"/"base"/"high"` 문자열인데 차트는 수치만
받는다」*.

## 왜 슬라이스이고 집계가 아닌가

평균하면 격자의 각 점이 **서로 다른 전제의 평균**이 되어 「이 조건에서 달성되는가」를
말하지 못한다 — **달성영역 음영의 뜻 자체가 사라진다.** 슬라이스는 「나머지 변수를
기준값에 고정한 단면」이라고 정직하게 말할 수 있다.

붙드는 것 다섯:

    ① 좌표당 칸이 **하나**다                27케이스 3변수 → 9칸
    ② 고정한 단면의 케이스만 온다            어느 단면인지 말할 수 있다
    ③ 단면을 정할 수 없으면 **거부한다**     아무 값이나 고르지 않는다
    ④ 수치 축이 **선언 순서**에서 온다       사전순은 중간 수준을 맨 앞에 놓는다
    ⑤ 순서를 못 받으면 `None` 이다           「0번 수준」과 구별된다

**①이 종전 결함이고 ④가 그다음이다.** 중복 칸은 그려질 때 뒤 칸이 앞 칸을 덮으므로
**어느 케이스가 보이는지는 정렬 순서가 정한다** — 오류 없이 틀린 그림이 나온다.
"""

from __future__ import annotations

import pytest

from core.casegrid.analysis import BASE_LEVEL, feasible_region
from core.casegrid.models import CaseResult
from core.contracts.validation import ValidationError

#: 세 변수 × 세 수준 = 27케이스. 프리셋(`quick_preset_grid`)과 같은 모양이다.
_LEVELS = ("low", BASE_LEVEL, "high")
_VARIABLES = ("discount_rate", "tariff_escalation", "capex")


def _results() -> list[CaseResult]:
    """27케이스 — 지표는 세 변수 수준 인덱스의 합으로 둔다(단면마다 다르게)."""
    out: list[CaseResult] = []
    index = 0
    for a in _LEVELS:
        for b in _LEVELS:
            for c in _LEVELS:
                out.append(
                    CaseResult(
                        case_index=index,
                        values=dict(zip(_VARIABLES, (a, b, c), strict=True)),
                        metrics={
                            "npv": float(
                                _LEVELS.index(a) + _LEVELS.index(b) * 10
                                + _LEVELS.index(c) * 100
                            )
                        },
                    )
                )
                index += 1
    return out


# ── ①② 좌표당 한 칸, 고정한 단면만 ──────────────────────────────────

@pytest.mark.req("FR-803-AC1")
def test_a_three_variable_grid_yields_one_cell_per_coordinate() -> None:
    """★★★ 27케이스 3변수에 2축을 주면 **9칸**이다 — 종전에는 27칸(좌표당 3중복)이었다.

    중복 칸은 그려질 때 뒤 칸이 앞 칸을 덮으므로 **어느 케이스가 보이는지는 정렬
    순서가 정한다** — 오류 없이 틀린 그림이 나온다.
    """
    cells = feasible_region(
        _results(), x="discount_rate", y="tariff_escalation", metric="npv", target=0.0
    )

    assert len(cells) == 9, f"좌표당 한 칸이 아닙니다: {len(cells)}칸"
    coordinates = [(cell.x_value, cell.y_value) for cell in cells]
    assert len(set(coordinates)) == len(coordinates), "같은 좌표에 칸이 둘 이상 있습니다"
    assert set(coordinates) == {(a, b) for a in _LEVELS for b in _LEVELS}


@pytest.mark.req("FR-803-AC1")
def test_the_default_slice_fixes_the_other_variables_at_base() -> None:
    """★ 기본 단면은 나머지 변수를 `base` 에 고정한 것이다.

    지표를 수준 인덱스로 지었으므로 세 번째 변수(`capex`)가 `base`(인덱스 1)로
    고정됐으면 모든 칸의 지표에 `1 * 100` 이 들어 있다 — **어느 단면인지 값으로
    확인한다.** 「9칸이다」만 보면 다른 단면을 골라도 통과한다.
    """
    cells = feasible_region(
        _results(), x="discount_rate", y="tariff_escalation", metric="npv", target=0.0
    )

    for cell in cells:
        hundreds = int(cell.metric_value) // 100
        assert hundreds == _LEVELS.index(BASE_LEVEL), (
            f"단면이 `{BASE_LEVEL}` 이 아닙니다 — capex 수준 인덱스 {hundreds}"
        )


@pytest.mark.req("FR-803-AC1")
def test_an_explicit_slice_selects_a_different_cross_section() -> None:
    """★ 단면을 지정하면 **다른 값**이 나온다 — 인자가 실제로 쓰인다.

    기본 단면만 검사하면 `slice_at` 을 받아서 버리는 구현도 통과한다.
    """
    base = feasible_region(
        _results(), x="discount_rate", y="tariff_escalation", metric="npv", target=0.0
    )
    high = feasible_region(
        _results(), x="discount_rate", y="tariff_escalation", metric="npv", target=0.0,
        slice_at={"capex": "high"},
    )

    assert len(high) == 9
    assert {c.metric_value for c in high} != {c.metric_value for c in base}


@pytest.mark.req("FR-803-AC1")
def test_a_grid_without_extra_variables_is_unchanged() -> None:
    """축 둘뿐인 격자는 종전대로다 — 슬라이스가 기존 사용을 깨지 않는다."""
    results = [
        CaseResult(case_index=i, values={"a": a, "b": b}, metrics={"npv": float(i)})
        for i, (a, b) in enumerate([(a, b) for a in ("low", "high") for b in ("low", "high")])
    ]

    cells = feasible_region(results, x="a", y="b", metric="npv", target=0.0)

    assert len(cells) == 4


# ── ③ 단면을 정할 수 없으면 거부한다 ─────────────────────────────────

@pytest.mark.req("FR-803-AC1", "NFR-303-M1")
def test_a_variable_without_a_base_level_is_refused() -> None:
    """★★ `base` 수준이 없는 변수가 있으면 거부한다 — 아무 값이나 고르지 않는다.

    고르면 그 격자는 **어떤 단면인지 아무도 모르는 채** 그럴듯하게 그려진다.
    사유가 「집계하지 않는 이유」까지 말한다 — 다음 사람이 평균으로 메우려 할 자리다.
    """
    results = [
        CaseResult(
            case_index=i, values={"a": a, "b": "low", "c": c}, metrics={"npv": float(i)}
        )
        for i, (a, c) in enumerate(
            [(a, c) for a in ("low", "high") for c in ("min", "max")]
        )
    ]

    with pytest.raises(ValidationError) as caught:
        feasible_region(results, x="a", y="b", metric="npv", target=0.0)

    assert "'c'" in caught.value.reason or "c" in caught.value.reason
    assert "집계하지 않는 이유" in caught.value.action


@pytest.mark.req("FR-803-AC1", "NFR-303-M1")
def test_slicing_on_an_axis_variable_is_refused() -> None:
    """축 변수를 단면으로 지정하면 거부한다.

    통과시키면 그 축의 한 수준만 남아 격자가 **한 줄**이 되고, 그 그림은 등고선이
    아니라 선 하나다 — 그런데 오류는 나지 않는다.
    """
    with pytest.raises(ValidationError, match="축은"):
        feasible_region(
            _results(), x="discount_rate", y="tariff_escalation", metric="npv",
            target=0.0, slice_at={"discount_rate": "low"},
        )


@pytest.mark.req("FR-803-AC1", "NFR-303-M1")
def test_a_slice_matching_no_case_is_refused() -> None:
    """단면에 해당하는 케이스가 없으면 거부한다 — 빈 격자를 내지 않는다."""
    with pytest.raises(ValidationError, match="0건"):
        feasible_region(
            _results(), x="discount_rate", y="tariff_escalation", metric="npv",
            target=0.0, slice_at={"capex": "없는수준"},
        )


# ── ④⑤ 수치 축 ──────────────────────────────────────────────────────

@pytest.mark.req("FR-803-AC1")
def test_axis_indices_come_from_the_declared_level_order() -> None:
    """★★★ 수치 축이 **선언 순서**에서 온다 — 사전순으로 만들지 않는다.

    사전순은 `base < high < low` 이므로 **중간 수준이 맨 앞에 오고**, 그 격자는
    좌표가 뒤섞인 채 그럴듯하게 그려진다. 그래서 선언 순서를 받는다.
    """
    levels = {name: list(_LEVELS) for name in _VARIABLES}

    cells = feasible_region(
        _results(), x="discount_rate", y="tariff_escalation", metric="npv",
        target=0.0, axis_levels=levels,
    )

    by_coordinate = {(c.x_value, c.y_value): c for c in cells}
    for x_value in _LEVELS:
        for y_value in _LEVELS:
            cell = by_coordinate[(x_value, y_value)]
            assert cell.x_index == _LEVELS.index(x_value)
            assert cell.y_index == _LEVELS.index(y_value)

    # ★ 사전순이면 `base` 가 0 이 된다 — 그것과 다름을 값으로 고정한다
    assert _LEVELS.index(BASE_LEVEL) == 1
    assert sorted(_LEVELS).index(BASE_LEVEL) == 0


@pytest.mark.req("FR-803-AC1")
def test_missing_level_order_gives_none_not_zero() -> None:
    """★ 수준 순서를 못 받으면 `None` 이다 — 「0번 수준」과 구별된다.

    둘을 같은 값으로 두면 축을 못 그린 격자가 **첫 수준에 뭉치고**, 그 그림은
    오류 없이 그려진다.
    """
    cells = feasible_region(
        _results(), x="discount_rate", y="tariff_escalation", metric="npv", target=0.0
    )

    assert all(cell.x_index is None and cell.y_index is None for cell in cells)
