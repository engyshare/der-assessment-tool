"""**`grid_support.py::GRID_DIRECTED_MODES`·`grid_support.py::peak_shaving_enabled` 을
직접 붙든다** (R54/WP-1-fix).

## 왜 이 파일이 있는가 — `NFR-105`

R54/WP-1 이 술어를 세울 때 동반 검사는 `tests/casegrid/test_nwas_cp_wiring.py`
하나뿐이었다 — 그 파일은 `core.casegrid.e2e_runner` 만 import 하므로, 술어가
사는 `core/casegrid/grid_support.py` 를 **직접** import 하는 검사가 한 건도
없었다. 남은 것은 러너를 통과하는 간접 검사뿐이다. 이 파일이 그 공백을
메운다 — 술어와 집합을 전건 러너 없이 **직접** 잰다.

## 어떻게 재는가 — 운전 방법 **전수 열거**

일곱 멤버를 손으로 나열해 대조하지 않는다. `ESSOperatingMode` 를 **순회**해
「`GRID_DIRECTED_MODES` 에 있으면 `False`, 없으면 `True`」를 재고, **별도로**
「방식 「나」는 정확히 둘이며 그 둘이 무엇인가」를 못박는다. 그래야 **다음
사람이 운전 방법을 하나 더 늘렸을 때** 그것이 방식 가인지 나인지 판정하지
않고 넘어가는 일을 이 검사가 막는다 — 그것이 이 검사의 값이다.

`ess` 는 `test_ess.py::_p1_ess` 팩토리로 세운다 — 그 파일이 `ESS` 를 세우는
방식을 그대로 따르며, 새 헬퍼를 발명하지 않는다.
"""
from __future__ import annotations

import pytest

from core.casegrid.grid_support import GRID_DIRECTED_MODES, peak_shaving_enabled
from core.der.ess import ESSOperatingMode
from tests.der.test_ess import _p1_ess


def test_grid_directed_modes_is_a_frozenset() -> None:
    """★ `GRID_DIRECTED_MODES` 는 `frozenset` 이다 — 모듈 수준 상태가 불변임을 잰다 (`NFR-205`).

    평범한 `set` 은 모듈 수준 가변 상태다 — 케이스 그리드 병렬 실행에서 한 번의
    변형이 다른 케이스의 결과를 **조용히** 바꾼다. 술어
    `grid_support.py::peak_shaving_enabled` 가 이 집합을 읽는 순간, 집합의
    가변성은 곧 모든 케이스의 `PeakShaving` 판정의 가변성이다.
    """
    assert isinstance(GRID_DIRECTED_MODES, frozenset), (
        f"GRID_DIRECTED_MODES 의 형이 {type(GRID_DIRECTED_MODES).__name__} 다 — "
        "모듈 수준 가변 상태는 케이스 그리드 병렬 실행에서 다른 케이스의 "
        "PeakShaving 판정을 조용히 바꾼다 (NFR-205)"
    )


@pytest.mark.req("FR-105-AC1")
def test_grid_directed_modes_are_exactly_two_named_modes() -> None:
    """★★ 방식 「나」는 **정확히 둘** — 「계통 방전」·「준중앙급전 등록」이다.

    사용자 판정 §1(`docs/decisions-2026-09-02-R54.md`)의 표를 그대로 못박는다.
    아래 전수 순회 검사는 「집합에 있으면 `False`」만 잰다 — **집합 자체가
    무엇인지**는 이 단언이 잰다. 둘이 함께여야 순회 단언과 이 단언이 폐쇄된다.
    """
    assert len(GRID_DIRECTED_MODES) == 2, (
        f"방식 「나」는 정확히 둘이어야 한다 — 지금 {len(GRID_DIRECTED_MODES)} 개: "
        f"{sorted(m.name for m in GRID_DIRECTED_MODES)}. 새 운전 방법을 늘렸다면 "
        "그것이 방식 가인지 나인지 판정하고 집합을 갱신하라 (사용자 판정 §1)"
    )
    assert frozenset(
        {
            ESSOperatingMode.GRID_DISCHARGE,
            ESSOperatingMode.SEMI_CENTRAL_DISPATCH,
        }
    ) == GRID_DIRECTED_MODES, (
        f"방식 「나」의 두 멤버가 어긋났다 — {sorted(m.name for m in GRID_DIRECTED_MODES)}"
    )


@pytest.mark.req("FR-105-AC1")
@pytest.mark.req("FR-402-AC2.E")
def test_peak_shaving_enabled_sweeps_the_whole_operating_mode_enum() -> None:
    """★★ `ESSOperatingMode` **전수 순회** — 집합에 있으면 `False`, 없으면 `True`.

    일곱을 손으로 나열하지 않고 `ESSOperatingMode` 를 그대로 순회한다. 다음
    사람이 운전 방법을 하나 더 늘리면 이 검사가 자동으로 그 모드까지 잰다 —
    그 모드가 방식 가인지 나인지 판정하지 않고 넘어가면 여기서 빨간불이 난다.

    `HYBRID` 는 `mode_weights` 없이는 세워지지 않는다(`ValidationError`) —
    `test_ess.py` 의 혼합 제례 그대로 가중치를 준다.
    """
    for mode in ESSOperatingMode:
        weights = (
            {
                ESSOperatingMode.SELF_CONSUMPTION: 0.5,
                ESSOperatingMode.GRID_DISCHARGE: 0.5,
            }
            if mode is ESSOperatingMode.HYBRID
            else None
        )
        ess = _p1_ess(operating_mode=mode, mode_weights=weights)
        if mode in GRID_DIRECTED_MODES:
            assert peak_shaving_enabled(ess) is False, (
                f"{mode.name} 은 방식 「나」다 — PeakShaving 이 켜졌다. "
                "애초에 만들지 않아야 한다 (사용자 판정 §1)"
            )
        else:
            assert peak_shaving_enabled(ess) is True, (
                f"{mode.name} 은 방식 「가」(또는 혼합의 판단 보류)다 — "
                "PeakShaving 이 꺼졌다 (사용자 판정 §1)"
            )


@pytest.mark.req("FR-402-AC2.E")
def test_hybrid_keeps_peak_shaving_on_as_a_deliberate_deferral() -> None:
    """★★ `HYBRID` → `True` 를 **따로 한 번 더** — 이것은 의도된 판단 보류다.

    전수 순회에 이미 들어가 있지만, 이 케이스는 **판단 보류**라서 눈에 보이게
    못박는다. 혼합 모드에서 `NWAs`·`CP` 와 `PeakShaving` 이 함께 켜지는 경우의
    배타는 `ESS.value_streams()` 독스트링이 적어 둔 **별개 자리**이며 이 술어의
    범위 밖이다 — 술어가 혼합까지 함께 끄면 **결론축이 움직일 수 있다**
    (사용자 판정 §1 ⚠).

    가중치는 방식 가 하나와 방식 나 하나를 섞는다(`test_ess.py` 의 혼합
    제례 그대로) — 혼합이 실제로 방식 「나」를 품고 있어도 이 단언은 `True` 다.
    """
    mixed = _p1_ess(
        operating_mode=ESSOperatingMode.HYBRID,
        mode_weights={
            ESSOperatingMode.SELF_CONSUMPTION: 0.5,
            ESSOperatingMode.GRID_DISCHARGE: 0.5,
        },
    )
    assert peak_shaving_enabled(mixed) is True, (
        "HYBRID 에서 PeakShaving 이 꺼졌다 — 판단 보류가 아니라 판단이 바뀐 것이다. "
        "혼합 배타는 ESS.value_streams() 의 별개 자리다 (사용자 판정 §1 ⚠ — "
        "함께 끄면 결론축이 움직일 수 있다)"
    )
