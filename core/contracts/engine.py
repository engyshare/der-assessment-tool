"""`DispatchEngine` 계약 — 작업 1.4 / spec FR-301 · FR-302.

`RuleBasedEngine`(Phase 1)과 `MilpEngine`(Phase 2)은 **동일 입출력 계약**을
따르므로 상호 교체 가능하며, **두 엔진 결과 비교가 곧 검증 수단이 된다**
(spec §4.3 머리말). 그래서 계약이 흔들리면 검증 수단 하나를 통째로 잃는다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.contracts.der import DER, DispatchContext, DispatchResult
from core.contracts.units import ENERGY_TOLERANCE_KWH


@dataclass(frozen=True)
class SystemDispatch:
    """한 해 전체 운전 결과 — 자원별 결과 + 계통 수·송전.

    자원별 결과를 **합치지 않고 보관하는** 이유: 프로포마가 자원별 행을
    요구하고(FR-701-AC1), 편익 배타 판정이 어느 자원의 어느 kWh인지를
    봐야 하기 때문이다(FR-402-AC2.A). 합쳐 두면 되돌릴 수 없다.
    """

    per_resource: dict[str, DispatchResult]
    grid_import: list[float]
    grid_export: list[float]

    def electric_balance_error(self) -> list[float]:
        """스텝별 전력 수지 오차 (kWh).

        `Σ 자원 전력 + 수전 − 송전 = 0` 이어야 한다. 부호 규약상 자원의
        양수는 내보냄, 음수는 받아들임이므로 수전은 더하고 송전은 뺀다.
        """
        steps = len(self.grid_import)
        errors: list[float] = []
        for i in range(steps):
            total = sum(r.electric[i] for r in self.per_resource.values())
            errors.append(total + self.grid_import[i] - self.grid_export[i])
        return errors


class DispatchEngine(ABC):
    """운전 시뮬레이션 엔진 계약 (FR-301)."""

    @abstractmethod
    def run(self, resources: list[DER], ctx: DispatchContext) -> SystemDispatch:
        """매 스텝 자원별 충·방전·발전·소비량과 계통 수·송전량을 산출한다
        (FR-301-AC1).

        구현체는 반환 전에 `verify_balance()` 를 통과시켜야 한다.
        """

    @staticmethod
    def verify_balance(dispatch: SystemDispatch) -> None:
        """전력·열 수지 균형식이 모든 스텝에서 오차 < 1e-6 kWh (FR-301-AC2).

        **위반 스텝을 전부 세지 않고 첫 건에서 멈추지 않는 이유**: 오차가
        한 스텝에만 있는지 전 구간에 퍼져 있는지가 원인 진단을 가른다.
        첫 건만 보고하면 부호 규약 실수(전 구간)와 경계 처리 실수(한 스텝)를
        구분할 수 없다.
        """
        errors = dispatch.electric_balance_error()
        bad = [(i, e) for i, e in enumerate(errors) if abs(e) >= ENERGY_TOLERANCE_KWH]
        if bad:
            head = ", ".join(f"스텝 {i}: {e:+.3e} kWh" for i, e in bad[:5])
            raise ValueError(
                f"전력 수지 균형 위반 {len(bad)}/{len(errors)} 스텝 "
                f"(허용 {ENERGY_TOLERANCE_KWH:g} kWh) — {head}"
                + (" …" if len(bad) > 5 else "")
                + ". 전 구간이면 부호 규약(양수=내보냄)을, 일부 스텝이면 "
                "경계 처리를 먼저 보십시오"
            )
