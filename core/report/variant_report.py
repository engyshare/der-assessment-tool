"""변형별 결과를 한 표로 — `FR-607-AC1` 「결과 상단에 표시」 / R31 (결정 §5).

조항 문면: *「**모든 실행에서** `지원 0` 케이스가 **자동 포함**되어 결과 **상단에
표시**된다」*

R21 이 「자동 포함」을 닫았다 — `run_order()` 가 등록된 변형 목록을 내고
`ordered_variants()` 가 **기준선이 정확히 하나이고 맨 위**임을 기계로 보증한다.
R31 이 `CaseResult.variants` 로 담을 자리를 만들었다. **남은 것이 「표시」다.**

## 왜 표시 층을 따로 두는가

배선만 하면 **소비자 없는 생산자**가 하나 더 생긴다. 그리고 조항이 요구하는 것은
「담고 있다」가 아니라 「상단에 표시된다」이므로, 담기만 하고 표를 내지 않으면 사람은
여전히 결과를 스스로 정렬해서 본다 — **리포트가 자기 나름대로 정렬하면 조항이
리포트마다 다르게 지켜진다.**

R23 이 `perspective_report.py` 에서 같은 판단을 했다: *「담고 있다」로는 조항이
닫히지 않는다*.

## 이 파일이 놓인 자리

`core/report/` 다. 정렬 순서(`CaseVariant.order`)는 `core.contracts` 가 갖고 결과는
`core.casegrid` 가 갖는데, 둘을 함께 읽는 것은 **그보다 위**여야 한다
(`.importlinter` 의 `layers` — `core.report` 가 최상위 계산 층이다).

`regulation_axis`(R20) · `dataset_axis`(R20) · `incentive_cases`(R21) ·
`perspective_report`(R23)에 이은 **다섯째 인스턴스**다 — 구획을 옳게 가르면
구획 사이에 아무도 소유하지 않는 일이 남는다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from core.casegrid.models import CaseResult
from core.casegrid.variants import run_order
from core.contracts.validation import ValidationError


@dataclass(frozen=True)
class VariantRow:
    """표의 한 행 = 변형 하나."""

    tag: str
    label: str
    #: 기준선인가 — 표시 층이 강조에 쓴다. **순서로만 알 수 없다**(다음 라운드가
    #: 정렬을 고치면 첫 행이 기준선이 아닐 수 있고, 그때 강조가 조용히 옮겨간다).
    baseline: bool
    metrics: Mapping[str, float]


@dataclass(frozen=True)
class VariantTable:
    """변형 × 지표 표 — **기준선이 맨 위인 것이 이 자료형의 계약이다.**"""

    rows: tuple[VariantRow, ...]
    #: 열 순서 = 지표 이름. 행마다 다른 순서로 그리면 사람이 열을 잘못 읽는다.
    metric_names: tuple[str, ...]

    @property
    def baseline_row(self) -> VariantRow:
        """기준선 행. **맨 위여야 한다** — `build_variant_table` 이 보증한다."""
        return self.rows[0]


def build_variant_table(result: CaseResult) -> VariantTable:
    """케이스 하나의 변형별 결과를 표로 세운다 — `FR-607-AC1`.

    ## 순서를 여기서 정하지 않는다

    `run_order()` 가 정본이다. 이 함수가 자기 나름대로 정렬하면 「상단에 표시」가
    리포트마다 다르게 지켜지고, `ordered_variants()` 가 보증하는 「기준선이 맨 위」가
    표시 층에서 무의미해진다.

    ## 결과에 없는 변형을 조용히 빼지 않는다

    등록된 변형인데 결과에 지표가 없으면 **거부한다.** 조용히 빼면 그 표는 「그
    변형이 산출되지 않았다」가 아니라 「그 변형이 없다」로 읽히고, 조항이 요구하는
    「모든 실행에서 자동 포함」이 표 위에서 깨진 것을 아무도 보지 못한다.

    ## 지표 열이 변형마다 다르면 거부한다

    한 변형만 `irr` 을 갖고 다른 변형은 없으면 그 열은 빈칸이 되고, 빈칸은
    「0」인지 「계산하지 않았다」인지 구별되지 않는다 — 그 구별이 이 저장소가
    `MissingAssumption` 에서 내린 판단이다.
    """
    registered = run_order()
    if not result.variants:
        raise ValidationError(
            field="casegrid.case_result.variants",
            reason=(
                f"케이스 {result.case_index} 에 변형별 결과가 없습니다 — "
                f"등록된 변형은 {len(registered)}개입니다"
            ),
            action=(
                "실행이 `run_order()` 의 변형 전부를 산출하고 그 지표를 "
                "`CaseResult.variants` 에 담게 하십시오. 빈 표를 그리면 "
                "「자동 포함」이 깨진 것을 아무도 보지 못합니다"
            ),
        )

    missing = [v.tag for v in registered if v.tag not in result.variants]
    if missing:
        raise ValidationError(
            field="casegrid.case_result.variants",
            reason=(
                f"등록된 변형의 결과가 빠졌습니다: {', '.join(missing)} "
                f"(케이스 {result.case_index})"
            ),
            action=(
                "빠진 변형을 산출하십시오. **표에서 조용히 빼지 않습니다** — "
                "빠진 행은 「산출되지 않았다」가 아니라 「그 변형이 없다」로 읽힙니다"
            ),
        )

    metric_names = _shared_metric_names(
        result.variants, registered_tags=[v.tag for v in registered]
    )
    rows = tuple(
        VariantRow(
            tag=variant.tag,
            label=variant.label,
            baseline=variant.baseline,
            metrics={name: result.variants[variant.tag][name] for name in metric_names},
        )
        for variant in registered
    )
    return VariantTable(rows=rows, metric_names=metric_names)


def _shared_metric_names(
    variants: Mapping[str, Mapping[str, float]], *, registered_tags: Sequence[str]
) -> tuple[str, ...]:
    """모든 변형이 공통으로 가진 지표 이름 — 하나라도 어긋나면 거부한다."""
    per_tag = {tag: frozenset(variants[tag]) for tag in registered_tags}
    names = set.intersection(*(set(v) for v in per_tag.values()))
    extra = {tag: sorted(set(keys) - names) for tag, keys in per_tag.items() if set(keys) - names}
    if extra:
        raise ValidationError(
            field="casegrid.case_result.variants",
            reason=(
                "변형마다 지표가 다릅니다: "
                + "; ".join(f"{tag} 만 가진 것 {keys}" for tag, keys in extra.items())
            ),
            action=(
                "모든 변형이 같은 지표를 산출하게 하십시오. 빈칸은 「0」인지 "
                "「계산하지 않았다」인지 구별되지 않으므로 비교 표에 둘 수 없습니다"
            ),
        )
    # **이름순으로 고정한다** — 사전 순회 순서에 기대면 파이썬 판올림이나 삽입
    # 순서 변화로 열 순서가 조용히 바뀌고, 그러면 사람이 열을 잘못 읽는다.
    return tuple(sorted(names))
