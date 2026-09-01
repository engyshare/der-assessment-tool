"""관점 넷 병렬 리포트 — WP-10 / FR-704-AC4 · R52/WP-A.

조항: *「**세 관점이 하나의 리포트에 병렬 표시**」*. **넷으로 늘린 것은 이
저장소가 아니라 사용자다** — 사용자 문면 *「중요한 순서는 국가적 관점, 전기
사용자 관점, 분산e사업자 관점임」*(`docs/decisions-2026-09-02-R52b.md` §1)이
spec 이 모르는 「국가적 관점」을 요구했고, 오케스트레이터가 그것을
`Perspective.SOCIETY` 로 판정해 필수 넷째로 올렸다(아래 `REQUIRED_PERSPECTIVES`
독스트링 참조). spec 문면과 사용자 어휘가 어긋난다는 사실은 spec 을 고치지
않고 `result_A.md` 에 적는다(§16.5 절차 밖).

**왜 이 합성이 `core/cba/` 가 아니라 여기 있는가.** `core/cba/perspective.py` 는
관점 **하나**의 결과(`PerspectiveResult`)를 낸다 — 그것이 재료다. 재료를 한
표로 나란히 놓는 것은 리포트 층의 일이고, `core/cba` 가 하려면 리포트를
import 해야 해서 계층 역방향이 된다.

> **R20·R21 이 같은 자리를 두 번 찾았다.** 「하위 구획이 만든 재료를 상위가
> 소비한다」는 조항은 **합성이 놓일 상위 자리**를 요구하고, 그 자리가 비어 있으면
> 하위 구획의 검사는 재료의 필드만 보며 초록불이 된다
> (`core/casegrid/regulation_axis.py` · `core/casegrid/incentive_cases.py` 가
> 각각 그 자리였다). **이것이 세 번째다.**

**「병렬」을 무엇으로 붙드는가.** 「결과를 담은 객체」로는 부족하다 — 담기만
하고 한 표로 내지 않으면 사람은 여전히 리포트를 나란히 놓고 봐야 한다.
그래서 표를 낸다: **지표 한 줄에 관점 전부의 값이 같은 순서로 실린다.** 관점이
하나라도 빠지면 표가 만들어지지 않는다.

**배선은 `core/casegrid/perspectives.py::build_perspective_wiring()` 이 한다**
— 배포 진입점(`run_single_case_e2e`)이 그것을 부르고, 이 파일은 그 결과를
받아 표로만 합성한다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.cba.perspective import Perspective, PerspectiveResult
from core.contracts.units import ZERO, Money
from core.contracts.validation import ValidationError

#: 리포트에 실을 관점 넷과 **그 순서**.
#:
#: ⚠⚠⚠ **이 순서는 spec FR-704 문면 순서가 아니다 — 사용자 판정 순서다**
#: (`docs/decisions-2026-09-02-R52b.md` §1, R52/WP-A 판정 아-1·아-2). spec
#: 본문은 「사업자 / 참여 주민 / 정부(재정)」 셋만 들고 사회(`SOCIETY`)를 모른다.
#: 사용자 문면 — *「중요한 순서는 국가적 관점, 전기 사용자 관점, 분산e사업자
#: 관점임」* — 을 이 저장소 어휘로 옮기면 **국가 = 사회**(보조금을 이전지출로
#: 처리하고 사회적 편익을 계상하는 관점)이고, 「국가 = 정부(재정)」로 읽을
#: 수도 있어 오케스트레이터가 **넷을 다 내는 쪽으로 판정했다**(그 물음 자체를
#: 지운다) — 되돌리려면 `SOCIETY` 를 빼고 `GOVERNMENT` 를 앞으로 옮긴다.
REQUIRED_PERSPECTIVES: tuple[Perspective, ...] = (
    Perspective.SOCIETY,
    Perspective.RESIDENT,
    Perspective.OPERATOR,
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
    #: ★★★ 이 관점에 **비용·초기투자가 실제로 배분됐는가** (R52/WP-A-fix
    #: 결함 1). 거짓이면 `npv`·`total_cost` 는 「그 관점 편익의 현재가치」일
    #: 뿐 순손익이 아니다 — 표시 층이 그 둘을 인쇄하면 안 된다.
    #:
    #: `PerspectiveResult`·`compute_perspective_npv()` 는 고치지 않는다
    #: (교정 지시). 대신 그 결과가 **이미 갖고 있는 신호**(`cost_rows`가
    #: 비었는가·`initial_investment` 가 0인가)에서 읽는다 — 새 계산이 아니라
    #: 표시 판정이다. 관점 이름을 하드코딩해 「사업자만 특별하다」고 적지
    #: 않는 이유이기도 하다 — 비용을 실제로 배분받은 관점이면 무엇이든
    #: 참이 된다.
    cost_basis_defined: bool

    @property
    def label(self) -> str:
        """열 머리 문자열 — 관점 어휘를 그대로 쓴다."""
        return str(self.perspective.value)


@dataclass(frozen=True)
class ParallelPerspectiveReport:
    """관점 넷을 나란히 담은 **하나의** 리포트 (FR-704-AC4)."""

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

    `REQUIRED_PERSPECTIVES` 넷(사회·참여 주민·사업자·정부)이 **전부** 있어야
    한다. 빠진 채로 표를 내면 사람은 그 관점의 값이 「0」인지 「산출하지
    않았다」인지 알 수 없고, 관점 섞기는 이 도메인에서 가장 흔한 중복
    오류다 (원칙 2-3).

    **다섯 번째 이후 관점은 뒤에 붙는다.** 필수 넷을 앞에 고정하고 나머지를
    그 뒤에 두면, 관점을 늘려도 앞 네 열의 자리가 바뀌지 않는다.
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
                "필수 관점 중 빠진 것이 있습니다: "
                f"{', '.join(p.value for p in missing)}. 빠진 열은 「0」인지 "
                "「산출하지 않았다」인지 읽는 사람이 구분할 수 없습니다"
            ),
            action=(
                "사회·참여 주민·사업자·정부 네 관점의 결과를 모두 주십시오 "
                "(FR-704-AC4, R52/WP-A 판정 아-1)"
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
        cost_basis_defined=bool(result.cost_rows) or result.initial_investment != ZERO,
    )
