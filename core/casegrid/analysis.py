from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.casegrid.models import CaseResult, FeasibleCell, TornadoInfluence
from core.contracts.validation import ValidationError

#: 슬라이스 기본 수준의 이름. 프리셋이 `low`/`base`/`high` 세 수준을 쓴다
#: (`core/casegrid/grid.py`). **여기 한 번만 적는다** — 호출부마다 적으면 갈린다.
BASE_LEVEL = "base"


def feasible_region(
    results: Sequence[CaseResult],
    *,
    x: str,
    y: str,
    metric: str,
    target: float,
    comparator: str = ">=",
    slice_at: Mapping[str, object] | None = None,
    axis_levels: Mapping[str, Sequence[object]] | None = None,
) -> tuple[FeasibleCell, ...]:
    """달성영역 격자 — `FR-803-AC1`.

    ## ★ 축 2개 밖 변수를 **고정한다(슬라이스). 집계하지 않는다** (R31 결정 §8)

    `docs/clause-recheck-2026-08-14.md` 판정: *「축 2개 외 변수를 집계·슬라이스하지
    않아 **27케이스에 3×3 격자를 주면 좌표당 3중복**이 된다」*. 종전 구현은 결과
    하나당 칸 하나를 만들었으므로 같은 (x, y) 좌표에 칸이 여럿 생겼고, 그 격자를
    그리면 **마지막에 그려진 칸이 앞의 것을 덮는다** — 어느 케이스가 보이는지는
    정렬 순서가 정한다.

    **평균하지 않은 이유**: 평균하면 각 점이 **서로 다른 전제의 평균**이 되어
    「이 조건에서 달성되는가」를 말하지 못한다 — 달성영역 음영의 뜻 자체가 사라진다.
    슬라이스는 「나머지 변수를 기준값에 고정한 단면」이라고 정직하게 말할 수 있다.

    ``slice_at`` 을 주지 않으면 나머지 변수를 **`base` 수준**에 고정한다. `base`
    수준이 없는 변수가 있으면 **거부한다** — 아무 값이나 고르면 그 격자는 어떤
    단면인지 아무도 모르는 채 그럴듯하게 그려진다.

    ## `axis_levels` — 수치 축

    프리셋 축의 값은 문자열이라 등고선 차트가 원리상 그려지지 않는다. 선언된 수준
    순서를 받으면 칸에 **수준 인덱스**를 싣는다. **문자열을 정렬해 만들지 않는다** —
    사전순은 `base < high < low` 이고 중간 수준이 맨 앞에 온다.
    """
    ordered = sorted(results, key=lambda item: item.case_index)
    if not ordered:
        return ()

    other = _other_variables(ordered, x=x, y=y)
    chosen = _resolve_slice(ordered, other, slice_at=slice_at, x=x, y=y)
    in_slice = [
        result for result in ordered
        if all(result.values.get(name) == value for name, value in chosen.items())
    ]
    if not in_slice:
        raise ValidationError(
            field="casegrid.feasible_region.slice_at",
            reason=(
                f"고정한 단면에 해당하는 케이스가 없습니다: {dict(chosen)!r}. "
                f"케이스 {len(ordered)}건 중 0건이 맞습니다"
            ),
            action="케이스 그리드에 실제로 존재하는 수준으로 단면을 지정하십시오",
        )

    return tuple(
        FeasibleCell(
            x_value=result.values[x],
            y_value=result.values[y],
            metric_value=result.metrics[metric],
            achieved=compare_metric(result.metrics[metric], target, comparator),
            case_index=result.case_index,
            x_index=_level_index(axis_levels, x, result.values[x]),
            y_index=_level_index(axis_levels, y, result.values[y]),
        )
        for result in in_slice
    )


def _other_variables(
    results: Sequence[CaseResult], *, x: str, y: str
) -> tuple[str, ...]:
    """축 둘을 뺀 변수 이름 — 이름순으로 고정해 메시지가 흔들리지 않게 한다."""
    return tuple(
        sorted({name for result in results for name in result.values} - {x, y})
    )


def _resolve_slice(
    results: Sequence[CaseResult],
    other: Sequence[str],
    *,
    slice_at: Mapping[str, object] | None,
    x: str,
    y: str,
) -> dict[str, object]:
    """고정할 값을 정한다 — 주어지지 않으면 `base` 수준, 없으면 거부."""
    if slice_at is not None:
        unknown = sorted(set(slice_at) - set(other))
        if unknown:
            raise ValidationError(
                field="casegrid.feasible_region.slice_at",
                reason=(
                    f"축이거나 존재하지 않는 변수를 단면으로 지정했습니다: "
                    f"{unknown}. 축은 {x!r}·{y!r} 이고 고정 대상은 {list(other)} 입니다"
                ),
                action="축 변수는 고정 대상이 아닙니다 — 나머지 변수만 지정하십시오",
            )
        return dict(slice_at)

    chosen: dict[str, object] = {}
    undecidable: list[str] = []
    for name in other:
        values = {result.values.get(name) for result in results}
        if len(values) == 1:
            # 값이 하나뿐이면 그것이 곧 단면이다 — 고를 것이 없다
            chosen[name] = next(iter(values))
        elif BASE_LEVEL in values:
            chosen[name] = BASE_LEVEL
        else:
            undecidable.append(name)

    if undecidable:
        raise ValidationError(
            field="casegrid.feasible_region.slice_at",
            reason=(
                f"축 밖 변수 {undecidable} 에 `{BASE_LEVEL}` 수준이 없어 단면을 "
                "정할 수 없습니다"
            ),
            action=(
                "`slice_at` 으로 고정할 수준을 지정하십시오. **집계하지 않는 이유**: "
                "평균하면 격자의 각 점이 서로 다른 전제의 평균이 되어 「이 조건에서 "
                "달성되는가」를 말하지 못합니다"
            ),
        )
    return chosen


def _level_index(
    axis_levels: Mapping[str, Sequence[object]] | None, name: str, value: object
) -> int | None:
    """선언된 수준 순서에서의 위치. 순서를 받지 못했으면 `None`.

    **`None` 은 「0번 수준」이 아니다** — 둘을 같은 값으로 두면 축을 못 그린 격자가
    첫 수준에 뭉치고, 그 그림은 오류 없이 그려진다.
    """
    if axis_levels is None or name not in axis_levels:
        return None
    levels = list(axis_levels[name])
    return levels.index(value) if value in levels else None


def filter_results(
    results: Sequence[CaseResult],
    *,
    metric: str,
    target: float,
    achieved: bool,
    comparator: str = ">=",
) -> tuple[CaseResult, ...]:
    return tuple(
        result
        for result in sorted(results, key=lambda item: item.case_index)
        if compare_metric(result.metrics[metric], target, comparator) is achieved
    )


def tornado_ranking(results: Sequence[CaseResult], *, metric: str) -> tuple[TornadoInfluence, ...]:
    variable_names = sorted({name for result in results for name in result.values})
    influences: list[TornadoInfluence] = []
    for variable_name in variable_names:
        averages = _metric_averages_by_value(results, variable_name, metric)
        influence = max(averages) - min(averages) if averages else 0.0
        influences.append(TornadoInfluence(variable_name=variable_name, influence=influence))
    return tuple(sorted(influences, key=lambda item: (-item.influence, item.variable_name)))


def compare_metric(value: float, target: float, comparator: str = ">=") -> bool:
    if comparator == ">=":
        return value >= target
    if comparator == ">":
        return value > target
    if comparator == "<=":
        return value <= target
    if comparator == "<":
        return value < target
    if comparator == "==":
        return value == target
    raise ValueError(f"unsupported comparator: {comparator!r}")


def _metric_averages_by_value(
    results: Sequence[CaseResult],
    variable_name: str,
    metric: str,
) -> tuple[float, ...]:
    grouped: dict[object, list[float]] = {}
    for result in results:
        grouped.setdefault(result.values[variable_name], []).append(result.metrics[metric])
    return tuple(sum(values) / len(values) for values in grouped.values())
