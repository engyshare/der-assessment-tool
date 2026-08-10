"""차트 레지스트리 — FR-1004-AC1 · FR-803 · NFR-207 과 같은 형태.

**차트를 더하는 방법은 파일 하나를 놓는 것이다.**

    core/report/charts/case_heatmap.py     ← 새 파일
      class CaseHeatmap(Chart):
          tag = "case_heatmap"
          ...

    이 파일은 **바뀌지 않는다.** `core/der/__init__.py` 를 고치지 않고 자원을
    더하는 것과 같은 근거다 (§16.1 W-3) — 중앙 목록을 두면 여러 사람이 같은
    줄을 편집하고, 그 순간 파일 단위 배타 소유가 선언만 남는다.

**레지스트리를 지연 생성하는 이유.** import 시점에 만들면 `core.report` 를
건드리는 모든 경로가 matplotlib 을 끌어온다 — 차트를 그리지 않는 실행(예:
JSON 내보내기)까지 느려진다.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping
from functools import lru_cache
from typing import Any

from core.contracts.chart import Chart, ChartArtifact
from core.contracts.registry import discover
from core.contracts.validation import ValidationError

#: 튜플이다 — `core/`·`app/`·`infra/` 는 모듈 수준 가변 컨테이너를 금지한다
#: (`test_no_module_or_class_level_mutable_containers`). 읽기 전용으로 쓰고
#: 있어도 위반이며, 그 규칙이 생긴 계기가 `core/der/ess.py` 였다.
__all__ = ("Chart", "ChartArtifact", "chart_registry", "render_charts")


@lru_cache(maxsize=1)
def chart_registry() -> Mapping[str, type[Chart]]:
    """등록된 차트 — `{tag: 클래스}`.

    `discover` 가 `tag` 중복·미선언을 **기동 시점에** 막는다. 늦게 발견되면
    어느 차트가 그려졌는지 그림만 보고는 알 수 없다.

    자기 패키지를 `sys.modules` 에서 꺼내는 이유: 여기서 `import
    core.report.charts` 를 하면 자기 자신을 import 하는 모양이 되고, 그것은
    함수 안 import 가 되어 `PLC0415` 에 걸린다. 이 모듈은 이미 적재돼 있으므로
    꺼내 쓰는 것으로 충분하다.
    """
    return discover(sys.modules[__name__], Chart)  # type: ignore[type-abstract]


def render_charts(
    data: Mapping[str, Any],
    *,
    tags: Iterable[str] | None = None,
) -> dict[str, ChartArtifact]:
    """차트를 그려 `{tag: 산출물}` 로 돌려준다.

    `tags` 를 주지 않으면 **등록된 전부**를 그린다. 입력이 모자란 차트를
    조용히 건너뛰지 않는다 — 건너뛰면 리포트에서 그림 한 장이 사라지는데
    아무 오류도 나지 않고, 그 빈자리는 심의자료가 인쇄된 뒤에 발견된다.
    필요한 것만 그리려면 `tags` 로 **명시**하십시오.
    """
    registry = chart_registry()
    wanted = list(registry) if tags is None else list(tags)

    unknown = sorted(tag for tag in wanted if tag not in registry)
    if unknown:
        raise ValidationError(
            field="chart.tags",
            reason=f"등록되지 않은 차트입니다: {', '.join(unknown)}",
            action=(
                "등록된 차트는 " + ", ".join(sorted(registry)) + " 입니다. "
                "새 차트라면 core/report/charts/<tag>.py 를 놓으십시오"
            ),
        )

    return {tag: registry[tag]().render(data) for tag in wanted}
