"""**함께 움직이는 인자**를 함께 흔든 결과 — 검토 「1차 의견」 1 (R33).

## 왜 이것이 서식이 아니라 방법론인가

검토 의견의 물음은 한 줄이었다 — *「ESS, PV 단가가 같이 움직여도 동일한 결과가
나오는가?」* 답은 **아니다**이고, 그것을 적지 않은 리포트는 **사업에 불리한
쪽으로 틀린다.**

1변수 스윕(`FR-1002-AC2`)은 인자 하나만 움직이고 나머지를 기준값에 둔다. 그래서
설비단가가 둘이면 표에는 *「PV 가 18% 내려가야 한다」* 와 *「ESS 가 17%
내려가야 한다」* 가 **따로** 실린다. 읽는 사람은 각각을 달성해야 하는 조건으로
읽지만, 실제로 설비단가는 함께 떨어진다 — 함께 20% 내려가면 훨씬 앞에서
뒤집힌다.

**저장소는 이미 그렇게 판정해 두었다.** `core/casegrid/grid.py` 의 두 프리셋이
설비단가 넷을 `equipment_cost_bundle` 한 축으로 묶어 흔든다(§FR-801 구성표).
즉 케이스 그리드는 결합으로 보는데 **리포트의 민감도만 독립**이었다. 이 파일은
새 판단을 만들지 않는다 — 이미 있는 결합 선언을 리포트로 가져올 뿐이다.

## ★ 상호작용을 **판정하지 않고 잰다**

「단독 효과를 더하면 결합 효과가 되는가」는 모형의 성질이지 상수가 아니다.
지금 구성에서는 설비단가 둘이 **`t=0` CAPEX 로만** 들어가므로 서로 곱해지지
않고 정확히 더해진다. 그러나 요금 인상률이 파이프라인에 배선되어 편익 시계열이
단가와 함께 움직이는 순간 그 성질은 깨진다.

그래서 여기서는 「더해진다」를 **가정하지 않고 잰다** — 결합 실행에서 단독 합을
뺀 잔차(`interaction_won`)를 함께 나른다. 잔차가 0 이면 리포트가 그렇게 적고,
0 이 아니면 그 값을 적는다. 「더해진다」를 코드가 단정하면, 배선이 바뀐 날
리포트는 **여전히 더해진다고 말하면서 틀린 수를 싣는다.**
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from core.casegrid.grid import coupled_variable_sets

#: 결합을 보여 줄 수준 — 기준값 양쪽이다. 한쪽만 보이면 「유리한 쪽만 실었다」가 된다.
MOVED_LEVELS: tuple[str, str] = ("low", "high")


@dataclass(frozen=True)
class CombinedPoint:
    """결합 시나리오 한 줄."""

    #: 움직인 변수. 비어 있으면 기준(전건 base) 행이다.
    moved: tuple[str, ...]
    level: str
    #: 변수 → **대장 단위로 되돌린** 값. 표에 그대로 실린다.
    values: Mapping[str, float]
    npv: float
    #: 기준 대비 결론 축의 이동폭.
    delta_won: float

    @property
    def is_base(self) -> bool:
        return not self.moved

    @property
    def is_combined(self) -> bool:
        """묶음 전건을 함께 움직인 행인가."""
        return len(self.moved) > 1

    @property
    def recovers(self) -> bool:
        return self.npv >= 0.0


@dataclass(frozen=True)
class CoupledSweep:
    """결합 집합 하나에 대한 스윕 결과."""

    bundle: str
    #: 이 리포트의 수준표에 **실제로 있는** 묶음 구성원만 담는다.
    variables: tuple[str, ...]
    base_npv: float
    points: tuple[CombinedPoint, ...]
    #: 수준 → (결합 효과 − 단독 효과의 합). 위 독스트링 「상호작용」 참조.
    interaction_won: Mapping[str, float]

    @property
    def additive(self) -> bool:
        """단독 효과의 합이 결합 효과와 **원 단위로** 같은가.

        1원의 여유도 두지 않는다. 이 값이 참인지 거짓인지에 따라 리포트가 다른
        문장을 적으므로, 「거의 같다」를 참으로 읽으면 리포트가 근거 없이
        단정하게 된다.
        """
        return all(round(value) == 0 for value in self.interaction_won.values())

    @property
    def flips_only_when_combined(self) -> tuple[CombinedPoint, ...]:
        """**함께 움직여야만** 결론이 뒤집히는 행.

        이것이 비어 있지 않으면 1변수 스윕만 실은 리포트는 *「어느 인자로도
        뒤집히지 않는다」* 로 읽힌다 — 검토 의견이 겨눈 자리다.
        """
        singles_recover = any(
            point.recovers for point in self.points if not point.is_combined
        )
        if singles_recover:
            return ()
        return tuple(
            point for point in self.points if point.is_combined and point.recovers
        )


def build_coupled_sweeps(
    *,
    level_map: Mapping[str, Mapping[str, float]],
    probe: Callable[[Mapping[str, float]], float],
    scales: Mapping[str, float],
    base_npv: float,
    bundles: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[CoupledSweep, ...]:
    """선언된 결합 집합마다 「단독 / 동반」을 나란히 재어 돌려준다.

    `level_map` 에 **둘 이상**의 구성원이 있는 묶음만 낸다. 하나뿐이면 결합이
    아니라 그냥 1변수 스윕이고, 그것은 이미 영향도 순위가 싣는다 — 같은 수를
    다른 이름으로 한 번 더 실으면 검토자는 두 표가 왜 다른지 찾게 된다.

    `bundles` 를 주면 그것을 선언으로 쓴다. **배포 경로는 주지 않는다** —
    기본값이 케이스 그리드의 선언이며, 그것이 이 파일이 있는 이유다. 인자를
    둔 것은 *「인자가 서로 곱해지는 모형에서도 잔차를 재는가」* 를 검사가 물을
    수 있게 하기 위해서다. 지금 대장 값으로는 그런 조합을 만들 수 없고, 재지
    않는 구현은 **오늘의 실물 리포트에서 옳게 보인다.**
    """
    declared = coupled_variable_sets() if bundles is None else bundles
    sweeps: list[CoupledSweep] = []
    for bundle, names in declared.items():
        members = tuple(name for name in names if name in level_map)
        if len(members) < 2:
            continue
        sweeps.append(
            _sweep_one(
                bundle=bundle,
                members=members,
                level_map=level_map,
                probe=probe,
                scales=scales,
                base_npv=base_npv,
            )
        )
    return tuple(sweeps)


def _display(
    scales: Mapping[str, float],
    assignment: Mapping[str, float],
) -> Mapping[str, float]:
    """대장 단위로 되돌린 표시값.

    계산에 쓰는 값은 환산된 것이지만 표는 대장 단위로 읽힌다 — 섞으면
    「0.025 %/년」처럼 값과 단위가 어긋나고 실제의 100분의 1로 조용히 읽힌다
    (`ledger_unit_scales` 가 같은 이유로 밖에 나와 있다).
    """
    return {
        name: value / (scales.get(name, 1.0) or 1.0)
        for name, value in assignment.items()
    }


def _sweep_one(
    *,
    bundle: str,
    members: tuple[str, ...],
    level_map: Mapping[str, Mapping[str, float]],
    probe: Callable[[Mapping[str, float]], float],
    scales: Mapping[str, float],
    base_npv: float,
) -> CoupledSweep:
    base_assignment = {name: float(level_map[name]["base"]) for name in members}
    points: list[CombinedPoint] = [
        CombinedPoint(
            moved=(),
            level="base",
            values=_display(scales, base_assignment),
            npv=base_npv,
            delta_won=0.0,
        )
    ]
    interaction: dict[str, float] = {}

    for level in MOVED_LEVELS:
        singles_delta = 0.0
        for name in members:
            assignment = {**base_assignment, name: float(level_map[name][level])}
            npv = probe(assignment)
            singles_delta += npv - base_npv
            points.append(
                CombinedPoint(
                    moved=(name,),
                    level=level,
                    values=_display(scales, assignment),
                    npv=npv,
                    delta_won=npv - base_npv,
                )
            )
        together = {name: float(level_map[name][level]) for name in members}
        combined_npv = probe(together)
        points.append(
            CombinedPoint(
                moved=members,
                level=level,
                values=_display(scales, together),
                npv=combined_npv,
                delta_won=combined_npv - base_npv,
            )
        )
        interaction[level] = (combined_npv - base_npv) - singles_delta

    return CoupledSweep(
        bundle=bundle,
        variables=members,
        base_npv=base_npv,
        points=tuple(points),
        interaction_won=interaction,
    )
