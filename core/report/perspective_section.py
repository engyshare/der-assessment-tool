"""리포트 4.5 「관점 넷 병렬 비교」 — R52/WP-A · R52/WP-A-fix.

사용자 문면(`docs/decisions-2026-09-02-R52b.md` §1·§5) — *「경제성 평가는
다양한 관점에서 평가가 가능해야 함 … 각 관점별로 분석 보고서가 다르게
산출되야 함」*. 배선은 `core/casegrid/perspectives.py::build_perspective_wiring()`
이 하고, 이 모듈은 그 결과(`CaseReport.perspectives`)를 절 하나로 그린다.

⚠ **4.1 의 결론축을 다시 계산하지 않는다.** 사업자 열의 NPV 는
`build_perspective_wiring()` 이 이미 결론축과 같은 값으로 지어 두었다 — 이
모듈은 그 값을 표로 옮길 뿐이다.

## ★★★ NPV·비용 합계를 **비용 배분이 정의된 관점에서만** 인쇄한다 (WP-A-fix 결함 1)

WP-A 검수가 잡은 결함: 참여 주민 NPV 974,035원이 「전기사용자가 97만원
이득」으로 읽히지만 실제로는 **비용을 한 원도 안 붙인 편익 현가**이고,
사회·정부 NPV 0원은 「손익 0」이 아니라 **아무것도 계산하지 않은 것**이다.
「0」과 「산출하지 않았다」가 구분되지 않는 표는 이 저장소가 반복해서
경계해 온 형태다.

**고치는 자리는 `core/report/perspective_report.py` 의
`PerspectiveColumn.cost_basis_defined`다** — `ParallelPerspectiveReport`
(그 열을 만드는 쪽)가 「이 관점에 비용·초기투자가 실제로 배분됐는가」를
스스로 판정해 알고 있어야, 이 모듈이 관점 이름을 하드코딩해 「사업자만
특별하다」고 적지 않아도 된다. 이 모듈은 그 판정을 읽어 **인쇄할지
말지만** 정한다 — `compute_perspective_npv()`·`PerspectiveResult` 의
계산은 그대로다.
"""
from __future__ import annotations

from types import MappingProxyType

from core.cba.perspective import Perspective
from core.report._format import _won
from core.report.case_report import CaseReport
from core.report.perspective_report import (
    METRIC_NPV,
    METRIC_TOTAL_BENEFIT,
    METRIC_TOTAL_COST,
    PerspectiveColumn,
    build_parallel_perspective_report,
)

#: NPV 행에서 비용 배분이 없는 관점에 인쇄하는 문면. **「0」을 쓰지 않는다**
#: — 「0」은 「계산해 보니 0」으로 읽히고, 이 칸은 애초에 계산하지 않았다.
NOT_COMPUTED = "미산출"
#: 비용 합계 행의 같은 자리. **「0원」을 쓰지 않는다** — 「0원」은 「비용이
#: 없다」로 읽히고, 이 칸은 「이 관점이 비용을 얼마나 부담하는지 아직 정한
#: 바 없다」다.
NOT_ALLOCATED = "미배분"

#: 표 머리 — 사용자 어휘(`docs/decisions-2026-09-02-R52b.md` §1: 국가 ·
#: 전기 사용자 · 분산e사업자)를 이 저장소 어휘 옆에 병기한다. `Perspective`
#: 열거 값 자체는 고치지 않는다 — 표시 전용 사전이다. `MappingProxyType` —
#: 모듈 수준 가변 컨테이너 금지(`tests/ci/test_ci_gates.py::test_no_
#: module_or_class_level_mutable_containers`, FR-805 병렬 실행 안전 —
#: `core/casegrid/perspectives.py::_PAYER_TO_PERSPECTIVE` 와 같은 함정).
_HEADER_LABEL: MappingProxyType[Perspective, str] = MappingProxyType({
    Perspective.SOCIETY: "사회(국가)",
    Perspective.RESIDENT: "참여 주민(전기사용자)",
    Perspective.OPERATOR: "사업자(분산E)",
    Perspective.GOVERNMENT: "정부",
})


def _npv_cell(column: PerspectiveColumn) -> str:
    return _won(float(column.npv)) if column.cost_basis_defined else NOT_COMPUTED


def _cost_cell(column: PerspectiveColumn) -> str:
    return _won(float(column.total_cost)) if column.cost_basis_defined else NOT_ALLOCATED


def perspective_section(report: CaseReport) -> list[str]:
    """4.5 절 — 관점 넷 병렬표(비용 배분 없는 관점은 NPV·비용을 안 낸다)."""
    wiring = report.perspectives
    table = build_parallel_perspective_report(wiring.results)
    headers = [_HEADER_LABEL[column.perspective] for column in table.columns]
    lines = [
        "### 4.5 관점 넷 병렬 비교",
        "",
        "사용자 판정(`docs/decisions-2026-09-02-R52b.md` §1·§5) — 국가(사회) · "
        "전기사용자(참여 주민) · 분산E사업자(사업자) · 정부 순서로 편익을 나눠 "
        "본다. **4.1 의 결론축(사업자 열)은 이 표에서도 그대로다.**",
        "",
        "★ 이 표는 관점별 **편익 귀속**을 나눠 본 것이다 — 사업자 열 외에는 "
        "이 사업의 비용·초기투자를 그 관점이 얼마나 부담하는지 선언한 자료가 "
        f"없어 `{NOT_COMPUTED}`/`{NOT_ALLOCATED}` 로 적는다. **편익 합계만 "
        "참인 수다.**",
        "",
        "| 지표 | " + " | ".join(headers) + " |",
        "|---|" + "|".join(["---"] * len(headers)) + "|",
        "| " + " | ".join([METRIC_NPV, *(_npv_cell(c) for c in table.columns)]) + " |",
        "| " + " | ".join(
            [METRIC_TOTAL_BENEFIT, *(_won(float(c.total_benefit)) for c in table.columns)]
        ) + " |",
        "| " + " | ".join([METRIC_TOTAL_COST, *(_cost_cell(c) for c in table.columns)]) + " |",
        "",
    ]

    lines += [
        f"- **사회·참여 주민·정부 열의 NPV·비용 합계가 `{NOT_COMPUTED}`/"
        f"`{NOT_ALLOCATED}` 인 이유** — 이 저장소는 이 세 관점이 이 사업의 "
        "비용을 얼마나 부담하는지 선언한 자료가 없다. 없는 것을 지어 넣지 "
        "않는다 — 대신 그 관점에 귀속되는 **편익**만 합산해 보인다.",
        "- **사회 열의 편익 합계가 0원인 이유** — `DistributedBenefit`(사회 "
        "편익)을 이 실행에 넘기는 배포 코드가 없다. **화폐화 결함이 아니라 "
        "배선 공백**이다.",
        "- **정부 열의 편익 합계가 0원인 이유** — `Payer.GOVERNMENT` 를 가진 "
        "편익이 이 저장소에 없다. `FR-704-AC3` 의 재정효율 지표(투입 국비 "
        "1억원당 확보 설비용량 등)는 편익 귀속 합산과 **다른 산식**이며 아직 "
        "배선되지 않았다.",
        "",
    ]

    resident_column = table.column_for(Perspective.RESIDENT)
    lines += [
        "**참여 주민(전기사용자) 관점에 있는 것과 없는 것** — 실제로 귀속되는 "
        f"편익은 `PeakShaving`(첨두 절감) {_won(float(resident_column.total_benefit))}"
        "이다. `SelfConsumption`(자가소비 절감)은 이 사업이 아직 화폐화하지 "
        "않아(붙임 8 「미반영」) 이 표에 없다 — 채우지 않고 그대로 드러낸다.",
        "",
    ]

    notes = table.exclusion_notes()
    if notes:
        lines.append("**관점 전환 시 제외된 항목과 사유** (FR-704-AC7):")
        lines.append("")
        lines += [f"- {label} 열: `{tag}` — {why}" for label, tag, why in notes]
        lines.append("")

    if wiring.outside:
        lines.append(
            "**관점 넷 밖의 지갑** — 다음 편익은 배전사업자·전력시장 지갑에서 "
            "나오며 어느 관점 열에도 들어가지 않는다(`Payer` 독스트링 R50):"
        )
        lines.append("")
        lines += [
            f"- `{item.tag}`({item.payer.value}) — {_won(item.annual_won)}"
            for item in wiring.outside
        ]
        lines.append("")
    else:
        lines += [
            "**관점 넷 밖의 지갑** — 이 실행에서 `NWAs`·`CP` 는 0원이지만, "
            "0원이 아니게 되어도 배전사업자·전력시장 지갑은 관점 넷 어디에도 "
            "들어가지 않는다(`Payer` 독스트링 R50).",
            "",
        ]
    return lines
