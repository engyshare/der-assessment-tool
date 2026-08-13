"""세 관점 병렬 리포트 — WP-10 / FR-704-AC4.

조항: *「**세 관점이 하나의 리포트에 병렬 표시**」*

**왜 이 합성이 `core/cba/` 가 아니라 여기 있는가.** `core/cba/perspective.py` 는
관점 **하나**의 결과(`PerspectiveResult`)를 낸다 — 그것이 재료다. 재료 셋을 한
표로 나란히 놓는 것은 리포트 층의 일이고, `core/cba` 가 하려면 리포트를
import 해야 해서 계층 역방향이 된다.

> **R20·R21 이 같은 자리를 두 번 찾았다.** 「하위 구획이 만든 재료를 상위가
> 소비한다」는 조항은 **합성이 놓일 상위 자리**를 요구하고, 그 자리가 비어 있으면
> 하위 구획의 검사는 재료의 필드만 보며 초록불이 된다
> (`core/casegrid/regulation_axis.py` · `core/casegrid/incentive_cases.py` 가
> 각각 그 자리였다). **이것이 세 번째다.**

**「병렬」을 무엇으로 붙드는가.** 「세 결과를 담은 객체」로는 부족하다 — 담기만
하고 한 표로 내지 않으면 사람은 여전히 세 리포트를 나란히 놓고 봐야 한다.
그래서 표를 낸다: **지표 한 줄에 관점 셋의 값이 같은 순서로 실린다.** 관점이
하나라도 빠지면 표가 만들어지지 않는다.

**관점 순서는 spec 문면 순서다** — *「사업자 / 참여 주민 / 정부(재정)」*. 순서를
호출부가 정하게 두면 리포트마다 열 순서가 달라지고, 두 리포트를 비교하는 사람이
열을 잘못 읽는다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.cba.perspective import Perspective, PerspectiveResult
from core.contracts.units import Money
from core.contracts.validation import ValidationError

#: 조항이 열거한 세 관점과 **그 순서** (spec FR-704 본문).
REQUIRED_PERSPECTIVES: tuple[Perspective, ...] = (
    Perspective.OPERATOR,
    Perspective.RESIDENT,
    Perspective.GOVERNMENT,
)

#: 지표 행의 이름 — 표의 첫 칸에 들어간다.
METRIC_NPV = "NPV"
METRIC_TOTAL_BENEFIT = "편익 합계"
METRIC_TOTAL_COST = "비용 합계"


@dataclass(frozen=True)
class PerspectiveColumn:
    """리포트의 한 열 — 관점 하나의 값.

    `PerspectiveResult` 를 그대로 열로 쓰지 않는 이유: 열은 **표시할 값**만
    들고 있어야 한다. 결과 객체를 그대로 노출하면 표시 층이 편익 행을 다시
    합산하게 되고, 그때 표의 합계와 상세의 합계가 어긋날 수 있다.
    """

    perspective: Perspective
    npv: Money
    total_benefit: Money
    total_cost: Money
    included_tags: tuple[str, ...]
    excluded_tags: tuple[str, ...]
    #: FR-704-AC7 — 왜 포함/제외했는가. 관점 전환 시 리포트가 표시한다.
    exclusion_rationale: dict[str, str]

    @property
    def label(self) -> str:
        """열 머리 문자열 — 관점 어휘를 그대로 쓴다."""
        return str(self.perspective.value)


@dataclass(frozen=True)
class ParallelPerspectiveReport:
    """세 관점을 나란히 담은 **하나의** 리포트 (FR-704-AC4)."""

    columns: tuple[PerspectiveColumn, ...]

    @property
    def perspectives(self) -> tuple[Perspective, ...]:
        return tuple(column.perspective for column in self.columns)

    def column_for(self, perspective: Perspective) -> PerspectiveColumn:
        for column in self.columns:
            if column.perspective is perspective:
                return column
        raise KeyError(perspective)

    def header_row(self) -> tuple[str, ...]:
        """표 머리행 — 첫 칸은 지표 이름 자리이고 그 뒤가 관점 열이다."""
        return ("지표", *(column.label for column in self.columns))

    def metric_rows(self) -> tuple[tuple[str, ...], ...]:
        """지표 행들 — **한 줄에 관점 전부의 값**이 열 순서대로 실린다.

        이것이 「병렬 표시」의 실물이다. 관점별로 표를 따로 내면 지표를 관점
        사이에서 비교하려면 사람이 두 표를 번갈아 봐야 한다.
        """
        return (
            (METRIC_NPV, *(str(int(column.npv)) for column in self.columns)),
            (
                METRIC_TOTAL_BENEFIT,
                *(str(int(column.total_benefit)) for column in self.columns),
            ),
            (METRIC_TOTAL_COST, *(str(int(column.total_cost)) for column in self.columns)),
        )

    def as_table(self) -> tuple[tuple[str, ...], ...]:
        """머리행 + 지표 행 — 표 하나."""
        return (self.header_row(), *self.metric_rows())

    def exclusion_notes(self) -> tuple[tuple[str, str, str], ...]:
        """(관점, 제외된 tag, 사유) — FR-704-AC7 「왜 제외되었는지」."""
        notes: list[tuple[str, str, str]] = []
        for column in self.columns:
            for tag in column.excluded_tags:
                notes.append(
                    (column.label, tag, column.exclusion_rationale.get(tag, ""))
                )
        return tuple(notes)


def build_parallel_perspective_report(
    results: Sequence[PerspectiveResult],
) -> ParallelPerspectiveReport:
    """관점 결과들을 한 리포트로 합성한다 (FR-704-AC4).

    세 관점이 **전부** 있어야 한다. 빠진 채로 표를 내면 사람은 그 관점의 값이
    「0」인지 「산출하지 않았다」인지 알 수 없고, 관점 섞기는 이 도메인에서 가장
    흔한 중복 오류다 (원칙 2-3).

    **네 번째 관점(사회 등)은 뒤에 붙는다.** 조항이 요구하는 셋을 앞에 고정하고
    나머지를 그 뒤에 두면, 관점을 늘려도 앞 세 열의 자리가 바뀌지 않는다 —
    `Perspective.SOCIETY` 가 그 두 번째 인스턴스다 (FR-704-AC5 의 기준 관점).
    """
    by_perspective: dict[Perspective, PerspectiveResult] = {}
    for result in results:
        if result.perspective in by_perspective:
            raise ValidationError(
                field="report.perspectives",
                reason=(
                    f"같은 관점이 두 번 들어왔습니다: {result.perspective.value}. "
                    "어느 값을 표에 실어야 하는지 판정할 수 없습니다"
                ),
                action="관점마다 결과를 하나씩 주십시오",
            )
        by_perspective[result.perspective] = result

    missing = [p for p in REQUIRED_PERSPECTIVES if p not in by_perspective]
    if missing:
        raise ValidationError(
            field="report.perspectives",
            reason=(
                "세 관점 중 빠진 것이 있습니다: "
                f"{', '.join(p.value for p in missing)}. 빠진 열은 「0」인지 "
                "「산출하지 않았다」인지 읽는 사람이 구분할 수 없습니다"
            ),
            action=(
                "사업자·참여 주민·정부 세 관점의 결과를 모두 주십시오 (FR-704-AC4)"
            ),
        )

    extra = [p for p in by_perspective if p not in REQUIRED_PERSPECTIVES]
    ordered = [*REQUIRED_PERSPECTIVES, *sorted(extra, key=lambda p: str(p.value))]
    return ParallelPerspectiveReport(
        columns=tuple(_column(by_perspective[p]) for p in ordered)
    )


def _column(result: PerspectiveResult) -> PerspectiveColumn:
    return PerspectiveColumn(
        perspective=result.perspective,
        npv=result.npv_value,
        total_benefit=result.total_benefit(),
        total_cost=result.total_cost(),
        included_tags=result.inclusions.included_tags,
        excluded_tags=result.inclusions.excluded_tags,
        exclusion_rationale=dict(result.inclusions.exclusion_rationale),
    )
