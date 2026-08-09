"""제약 합성·충돌 검출 — 작업 8.9 / FR-403.

편익이 자원에 거는 ``ConstraintDecl`` 을 모아 **유형별 단일 시계열로 min/max
합성** 한다(FR-403-AC1). 합성 결과에 **어느 편익이 기여했는지**를 기록해
충돌 시 원인 편익을 보고한다(FR-403-AC2·AC3).

**``math.inf`` 를 sentinel 로 쓴다** (FR-403-AC4). ``1e30`` 같은 유한 대형
상수를 쓰면 min/max 합성에서 **조용히 유효 제약이 되어** «제약 없음» 이
«매우 큰 제약» 이 된다. ``ConstraintDecl._finite`` 가 NaN 은 거부하지만
``inf`` 는 허용한다 — 그 이유가 여기서 드러난다.

합성 규칙
---------
같은 ``target`` 의 제약을 모은 뒤:

* ``min`` 끼리는 **각 시각의 ``max``** 가 유효 min 이다 — 가장 강한(큰) 하한이
  모든 하한을 만족시킨다. ``max(a, b)`` 가 ``min`` 제약의 합성이다.
* ``max`` 끼리는 **각 시각의 ``min``** 이 유효 max 이다 — 가장 강한(작은) 상한이
  모든 상한을 만족시킨다.

충돌은 합성된 ``(유효 min[i], 유효 max[i])`` 에서 ``min[i] > max[i]`` 인 시각.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from core.contracts.schemas import ConstraintDecl


@dataclass(frozen=True)
class ConflictAt:
    """한 시각의 충돌 — 원인 편익들을 함께 든다 (FR-403-AC3)."""

    target: str
    step: int
    bound_min: float
    bound_max: float
    min_contributors: tuple[str, ...]
    max_contributors: tuple[str, ...]

    def render(self) -> str:
        """충돌을 사람이 읽는 문장으로 — ``step`` 을 시각으로 환산은 호출부."""
        return (
            f"{self.target} 의 제약 충돌: 하한 {self.bound_min} > 상한 "
            f"{self.bound_max}. 하한을 건 편익 "
            f"{sorted(self.min_contributors)} 와 상한을 건 편익 "
            f"{sorted(self.max_contributors)} 가 어긋난다"
        )


@dataclass
class _Composed:
    """한 target 의 합성 결과. step 별 유효 min/max 와 기여자."""

    bound_min: list[float] = field(default_factory=list)
    bound_max: list[float] = field(default_factory=list)
    min_contributors: list[list[str]] = field(default_factory=list)
    max_contributors: list[list[str]] = field(default_factory=list)


class ConstraintRegistry:
    """제약 선언을 모아 합성하고 충돌을 검출한다.

    레지스트리는 **불변 합성 결과**를 낸다 — 같은 선언 목록에서 같은 결과.
    실행 중 동적 가변 제약은 이 객체의 책임이 아니다 (NFR-205).
    """

    def __init__(self) -> None:
        # target → { "min": [ConstraintDecl,...], "max": [...] }
        self._decls: dict[str, dict[str, list[ConstraintDecl]]] = {}

    def register(self, decl: ConstraintDecl) -> None:
        """제약 1건 등록. 같은 target·kind 가 여러 편익에서 올 수 있다."""
        bucket = self._decls.setdefault(decl.target, {"min": [], "max": []})
        bucket[decl.kind].append(decl)

    def compose(self) -> dict[str, _Composed]:
        """등록된 제약을 target 별로 합성한다.

        min 제약이 여럿이면 각 시각의 ``max`` 가 유효 min, max 제약이 여럿이면
        각 시각의 ``min`` 이 유효 max. **기여자 기록**은 동점인 편익을 모두
        담는다(FR-403-AC2) — 단일 기여자만 적으면 동점에서 누락이 생긴다.

        ``math.inf`` 값은 «그 시각 제약 없음» sentinel 이다 (FR-403-AC4).
        합성에서 무시된다 — 그래야 «제약 없음» 이 «매우 큰 제약» 으로 바뀌지
        않는다. ``1e30`` 을 썼다면 유한이라 유효 제약이 되어 거짓 결과를 낸다.
        """
        out: dict[str, _Composed] = {}
        for target, bucket in self._decls.items():
            steps = self._step_count(bucket)
            composed = _Composed()
            # min: 각 시각의 max (유한 값만). 전부 inf 면 -inf (하한 없음).
            composed.bound_min = [-math.inf] * steps
            composed.min_contributors = [[] for _ in range(steps)]
            for decl in bucket["min"]:
                for i, v in enumerate(decl.values):
                    if math.isinf(v):
                        continue  # «제약 없음» sentinel — 합성에서 무시
                    if v > composed.bound_min[i] or math.isinf(composed.bound_min[i]):
                        composed.bound_min[i] = v
                        composed.min_contributors[i] = [decl.source_tag]
                    elif v == composed.bound_min[i]:
                        composed.min_contributors[i].append(decl.source_tag)
            # max: 각 시각의 min (유한 값만). 전부 inf 면 +inf (상한 없음).
            composed.bound_max = [math.inf] * steps
            composed.max_contributors = [[] for _ in range(steps)]
            for decl in bucket["max"]:
                for i, v in enumerate(decl.values):
                    if math.isinf(v):
                        continue
                    if v < composed.bound_max[i] or math.isinf(composed.bound_max[i]):
                        composed.bound_max[i] = v
                        composed.max_contributors[i] = [decl.source_tag]
                    elif v == composed.bound_max[i]:
                        composed.max_contributors[i].append(decl.source_tag)
            out[target] = composed
        return out

    def detect_conflicts(self) -> list[ConflictAt]:
        """min > max 충돌을 **실행 전에** 검출 (FR-403-AC3).

        ``math.inf`` 가 sentinel 이므로:
        - min 제약이 없으면 bound_min[i] = -inf → 유한 max 와 충돌하지 않는다.
        - max 제약이 없으면 bound_max[i] = +inf → 유한 min 과 충돌하지 않는다.
        - 둘 다 없으면 (-inf, +inf) — 충돌 아님.

        ``1e30`` sentinel 을 썼다면 min 제약 없는 시각이 ``bound_min=1e30`` 이
        되어 유한 max 와 거짓 충돌을 일으킨다 — ``math.inf`` 가 이것을 막는다.
        """
        conflicts: list[ConflictAt] = []
        for target, composed in self.compose().items():
            for i, (lo, hi) in enumerate(
                zip(composed.bound_min, composed.bound_max, strict=True)
            ):
                # inf 비교: -inf < 유한 < +inf 이므로, 한 쪽이 inf 면 충돌 불가.
                if lo > hi:
                    conflicts.append(ConflictAt(
                        target=target,
                        step=i,
                        bound_min=lo,
                        bound_max=hi,
                        min_contributors=tuple(composed.min_contributors[i]),
                        max_contributors=tuple(composed.max_contributors[i]),
                    ))
        return conflicts

    @staticmethod
    def _step_count(bucket: dict[str, list[ConstraintDecl]]) -> int:
        """길이 정합 — 같은 target 의 모든 제약은 step 수가 같아야 한다."""
        lengths = {len(d.values) for d in bucket["min"] + bucket["max"]}
        if not lengths:
            return 0
        if len(lengths) != 1:
            raise ValueError(
                f"같은 target 의 제약 시계열 길이가 다릅니다: {sorted(lengths)}. "
                "min/max 합성은 같은 시각끼리 더해야 하므로 길이가 같아야 한다"
            )
        return lengths.pop()
