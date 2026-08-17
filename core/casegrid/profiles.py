"""대표일 **형상**을 읽는다 — `fixtures/profiles/representative-day.yaml`.

## 왜 형상이 따로 있는가

파이프라인은 지금 PV 에 **이용률 하나**만 주고, 그러면 하루 발전량이 24스텝에
**균등 배분**된다 — 즉 심야에도 태양광이 발전한다(붙임 8 「일중 발전 프로파일」).
가구 부하는 아예 없다. 둘 다 *「형상을 모른다」* 가 아니라 *「형상을 줄 통로를
쓰지 않았다」* 였다: `PV(generation_profile_kwh=…)` 와 `Load(hourly_kwh=…)` 는
이미 있다.

## ⚠ 형상은 **총량을 정하지 않는다**

자산이 정하는 것은 하루 안의 배분뿐이다. 총량은 그대로 대장과 설계 변수가
정한다 — 발전은 `pv_capacity_kw × 이용률`, 부하는 대장 `load.household.annual`.
그래서 형상을 바꿔도 **연간 에너지는 변하지 않고 시간대만 옮겨간다.**

## ⚠ 이것으로 프로포마를 다시 계산하지 않는다

부하를 편익 계산에 태우면 잉여판매가 줄어드는데, 그 대가인 자가소비 절감은
소매 단가가 없어 계상할 수 없다(요금 엔진 미착수). 한쪽만 반영하면 **사업에
불리한 쪽으로 틀린다** — NSPM 대칭성이며 양식 4절이 금지하는 것이다. 그래서
읽는 쪽은 **운전(물리량)만** 다시 그린다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import yaml  # type: ignore[import-untyped]

#: 자산의 자리. 대장(`docs/assumptions.yaml`)이 아니다 — 값이 아니라 형상이라
#: 대장 항목의 꼴(`value` + `sensitivity` 3수준)에 맞지 않는다.
PROFILE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "profiles" / (
    "representative-day.yaml"
)

LOAD_SHAPE_KEY = "shape.load.household.daily"
GENERATION_SHAPE_KEY = "shape.pv.generation.daily"


@dataclass(frozen=True)
class DailyShape:
    """대표일 한 자원의 형상 — **합이 1로 정규화된** 가중치."""

    key: str
    title: str
    confidence: str
    derivation_method: str
    weights: tuple[float, ...]

    def spread(self, total: float, *, days: int) -> list[float]:
        """연간 총량을 **대표일을 되풀이해** 스텝별로 편다.

        ⚠ 여기서 총량을 만들지 않는다 — 받은 총량을 배분할 뿐이다. 형상이
        총량까지 정하면 대장을 고쳐도 그 값이 따라오지 않는다.
        """
        per_day = total / days
        return [per_day * weight for _day in range(days) for weight in self.weights]


@dataclass(frozen=True)
class DailyShapes:
    """읽는 쪽이 받는 한 벌."""

    load: DailyShape
    generation: DailyShape


def _normalised(raw: list[float], *, key: str) -> tuple[float, ...]:
    if not raw:
        raise ValueError(f"형상 {key!r} 의 가중치가 비어 있습니다")
    if any(weight < 0.0 for weight in raw):
        raise ValueError(f"형상 {key!r} 에 음수 가중치가 있습니다")
    total = math.fsum(raw)
    if total <= 0.0:
        raise ValueError(
            f"형상 {key!r} 의 가중치 합이 0 입니다 — 배분할 곳이 없어 "
            "그 자원의 에너지가 통째로 사라집니다"
        )
    return tuple(weight / total for weight in raw)


def load_daily_shapes(path: Path | None = None) -> DailyShapes:
    """자산을 읽어 정규화한다. **없으면 메우지 않고 거부한다.**"""
    source = path or PROFILE_PATH
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    by_key = {item["key"]: item for item in data.get("profiles", [])}

    def one(key: str) -> DailyShape:
        item = by_key.get(key)
        if item is None:
            raise ValueError(
                f"형상 자산에 {key!r} 이(가) 없습니다 ({source}). "
                "기본 형상으로 메우지 않습니다 — 메우면 「자산이 비었다」와 "
                "「이 형상을 골랐다」가 구별되지 않습니다"
            )
        return DailyShape(
            key=key,
            title=str(item["title"]),
            confidence=str(item["confidence"]),
            derivation_method=str(item["derivation_method"]).strip(),
            weights=_normalised([float(w) for w in item["weights"]], key=key),
        )

    load = one(LOAD_SHAPE_KEY)
    generation = one(GENERATION_SHAPE_KEY)
    if len(load.weights) != len(generation.weights):
        raise ValueError(
            f"두 형상의 스텝 수가 다릅니다 — 부하 {len(load.weights)} · "
            f"발전 {len(generation.weights)}. 같은 대표일을 그려야 합니다"
        )
    return DailyShapes(load=load, generation=generation)
