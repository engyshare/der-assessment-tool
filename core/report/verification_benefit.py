"""편익 단계의 **수량과 금액을 가른다** — 검증 4단계 (R68/WP-8 · 검토서 §3.6).

검토서 §3.6:

    「4단계 편익, 5단계 운영비, 6단계 생애주기, 7단계 현금흐름은 별도 파일로
      나뉘었지만, 각 파일의 첫 부분에 “**3단계의 어떤 물리 결과를
      금액화하는가**”가 더 명확해야 한다. 특히 다음을 구분해야 한다 —
      자가소비량과 잉여판매량 · 한전 수전량과 전력 구매비 · 피크 절감량과 피크
      기본요금 절감액 · PV·ESS 의 설치비와 교체비 · 물리적으로 측정하지 않은
      편익과 0원으로 설정한 편익」

## ★ 무엇이 문제였나 — 4단계 표에는 **금액만** 있었다

종전 4단계 ⓑ 는 `| 편익 | 1년차 금액 | 만든 자원 |` 셋이었다. 검토자는
「잉여전력 판매 0원」을 읽고 **얼마를 팔았는데 0원인지** 알 수 없었고, 그래서
그 0원이 *「팔 것이 없었다」* 인지 *「팔았는데 값이 0이었다」* 인지 갈리지 않았다.
그 둘은 고치는 사람이 다르다 — 앞은 운전(3단계)이고 뒤는 단가(1단계)다.

⇒ **수량 열과 금액 열을 나란히 세운다.** 수량은 3단계 운전에서 잰 것이고
(`core/report/measured_run.py::measured_over_seasons`) 금액은 4·5단계가 그 위에
곱한 것이다. 한 행에 세워야 검토자가 *어느 쪽이 0인가* 를 눈으로 가른다.

## ⚠⚠ **재료가 없는 쌍은 지어내지 않는다**

피크 절감량(kW)은 이 실행의 어느 자료형에도 없다 — `CaseBasis.benefits` 는
`tag·label·annual_won·resource_code·formula` 뿐이고 감축 출력은
`core/der/ess.py::ESS.reducible_peak_kw` 안에서 쓰이고 사라진다. 그 수를 4단계
ⓓ 의 **산식 문면에서 되뽑지 않는다** — 산문을 파싱해 수를 만드는 것은 이
저장소가 R68/WP-7 에서 명시로 금한 자리이고, 표기를 다듬는 날 그 수가 조용히
바뀐다(`core/casegrid/models.py::CaseBasis.grid_purchase_price_won_per_kwh`
주석이 같은 함정을 적어 두었다). ⇒ **「미산출」이라 글자로 적고 산식을 가리킨다.**

## ⚠ 0원은 **「효과 없음」이 아니다** (§3.6 마지막 문단)

이 실행에서 `SurplusSale`·`REC` 가 0원인데, 그것은 *「잉여가 없어서」*가 아니라
**하루 안의 부하 이동과 저장장치 충전이 그 잉여를 먼저 쓰기 때문**이다
(디스패치 차례에서 송전이 맨 끝 · `status.md` R67 종료 블록 ②). 그 사실을
글자로 적지 않으면 검토자는 0원을 *「이 사업에 그 편익이 없다」* 로 읽는다.

⛔ **어느 갈래가 「수량이 0」이고 어느 갈래가 「단가가 0」인지 이 모듈이
분류하지 않는다.** 갈래 이름으로 가르면 태그를 다듬는 날 조용히 틀리고, 그
답은 이미 4단계 ⓓ 의 그 갈래 산식이 **수량과 단가를 함께 싣는 것**으로 있다.
여기서 하는 일은 *「0을 어떻게 읽어야 하는가」* 를 세우는 것뿐이다.

## ⚠ 값을 여기서 짓지 않는다

수량은 `measured_over_seasons` 가, 금액은 러너가 만든 `CaseBasis` 가 갖는다.
이 모듈은 **자리만 정한다** — 곱하거나 나누는 자리가 하나라도 여기 생기면
같은 수를 두 곳이 갖게 되고 한쪽만 고쳐진다(R68/WP-4 가 `estate_load_kwh` 에서
내린 것과 같은 판단).
"""
from __future__ import annotations

from collections.abc import Sequence

from core.casegrid.models import (
    ONE_OFF_REPLACEMENT,
    ONE_OFF_SALVAGE,
    CaseBasis,
    OneOffLine,
)
from core.casegrid.operating_lines import DAYS_PER_YEAR
from core.report._format import NO_VALUE, _won
from core.report.case_report import CaseReport
from core.report.measured_run import MeasuredQuantities, measured_over_seasons

#: 이 단계가 답하는 것의 머리 — 검토서 §3.6 의 *「어떤 물리 결과를
#: 금액화하는가」* 를 표 제목으로 세운다. ⚠ 「전제」를 쓰지 않는다(판정 R63b §1).
#: ⚠ 굵게 표시는 «부르는 자리»가 씌운다 — 여기 `**` 를 겹치면 중첩이 되어
#: 마크다운이 별표를 그대로 인쇄한다(실측).
PAIR_TITLE = "3단계 물리 결과 → 금액 — 수량과 금액을 갈라 싣는다"

#: 재료가 없는 칸의 문면. **빈칸으로 두지 않는다** — 빈칸은 「0」과 구별되지
#: 않고, 0 은 「없다」로 읽힌다.
NOT_COMPUTED = "미산출"

#: 금액이 «있어야 할 자리»인데 이 실행이 화폐화하지 않은 칸. 0원과 다르다 —
#: 0원은 계산한 결과이고 이것은 계산하지 않은 상태다.
NOT_MONETISED = "현재 산정하지 않음"

#: 수량 단위. 표 제목이 지므로 칸에 되풀이하지 않는다(검토서 §4.2).
QUANTITY_UNIT = "kWh/년"

#: 이 표가 「4단계 것이 아닌 행」을 함께 싣는다는 표시. 한전 수전량·전력
#: 구매비는 5단계 소관인데, §3.6 이 **그 쌍도 갈라 보이라**고 요구한다.
STAGE5_MARK = "5단계"


def _annual(daily_kwh: float) -> str:
    """대표일 수량을 연간으로 편다 — 배수는 러너가 쓰는 그 상수 하나다."""
    return f"{daily_kwh * DAYS_PER_YEAR:,.0f} {QUANTITY_UNIT}"


def _amount_of(basis: CaseBasis, tag: str) -> str:
    """그 태그의 1년차 금액. 갈래가 없으면 **「없다」가 아니라 진술**이다."""
    for benefit in basis.benefits:
        if benefit.tag == tag:
            return _won(benefit.annual_won)
    for cost in basis.costs:
        if cost.tag == tag:
            return _won(cost.annual_won)
    return NOT_MONETISED


def _pair_rows(basis: CaseBasis, measured: MeasuredQuantities | None) -> list[str]:
    """네 쌍 — 수량 열과 금액 열. **잴 운전이 없으면 수량 칸이 진술이 된다.**"""
    if measured is None:
        self_use = surplus = purchased = NOT_COMPUTED
    else:
        self_use = _annual(measured.self_consumption)
        surplus = _annual(measured.grid_export)
        purchased = _annual(measured.grid_import)
    return [
        f"| 자가소비량 | {self_use} | 구매 회피액 | {NOT_MONETISED} | "
        "편익 갈래에 `SelfConsumption` 이 없다 — 자가소비는 수량 배분으로만 "
        "반영되고 화폐화되지 않는다. 크기는 「미반영 항목」 표가 잰다 |",
        f"| 잉여판매량 (계통 송전) | {surplus} | 판매 수입 (`SurplusSale`) | "
        f"{_amount_of(basis, 'SurplusSale')} | 아래 0원 주석 |",
        f"| 한전 수전량 | {purchased} | 전력 구매비 (`GridPurchase`) | "
        f"{_amount_of(basis, 'GridPurchase')} | {STAGE5_MARK} 운영비 행이 같은 "
        "수를 싣는다 — 이 표는 그 쌍을 갈라 보이려고 함께 세운다 |",
        f"| 피크 절감량 (kW) | {NOT_COMPUTED} | 기본요금 절감액 "
        f"(`PeakShaving`) | {_amount_of(basis, 'PeakShaving')} | 감축 출력을 "
        "이 실행의 자료형이 나르지 않는다 — 수는 아래 ⓓ 의 그 갈래 산식에 있고, "
        "산문에서 되뽑지 않는다 |",
    ]


def _capex_rows(basis: CaseBasis) -> list[str]:
    """자원마다 **설치비와 교체비를 갈라** 적는다 (§3.6 다섯째 쌍).

    ⚠ 연차를 함께 싣는다 — 없으면 검토자가 교체비를 연간액으로 읽는다
    (`core/casegrid/models.py::OneOffLine` 이 같은 사유로 연차를 필수로 뒀다).
    """
    rows = []
    for resource in basis.resources:
        flows = [
            line for line in basis.one_off_flows if line.resource_name == resource.name
        ]
        rows.append(
            f"| {resource.kind} | {_won(resource.capex_won)} "
            f"| {_one_off(flows, ONE_OFF_REPLACEMENT)} "
            f"| {_one_off(flows, ONE_OFF_SALVAGE)} |"
        )
    return rows


def _one_off(flows: Sequence[OneOffLine], kind: str) -> str:
    """그 자원의 그 갈래 일회성 흐름 — 금액과 **계상 연차**를 함께.

    ⚠ **비어 있는 것이 「없다」가 아니다** — 수명이 분석기간과 맞아 정말 없을
    수도, 배선이 끊겨 없을 수도 있다. 그 판정은 「미반영 항목」 표가 자원 수명과
    함께 보고 하며, 여기서는 **이 표에 실린 것이 없다**만 적는다.
    """
    picked = [line for line in flows if line.kind == kind]
    if not picked:
        return f"{NO_VALUE} (이 표에 실린 흐름 없음)"
    return " · ".join(f"{_won(line.amount_won)} ({line.year}년차)" for line in picked)


def _zero_notes(basis: CaseBasis, measured: MeasuredQuantities | None) -> list[str]:
    """0원 편익을 **어떻게 읽어야 하는가** — 「효과 없음」과 가른다 (§3.6)."""
    zeros = [line for line in basis.benefits if line.annual_won == 0]
    if not zeros:
        return []
    names = " · ".join(f"`{line.tag}`" for line in zeros)
    lines = [
        f"- **1년차 금액이 0원인 편익 갈래 {len(zeros)}건 — {names}.** 「이 사업에 "
        "그 편익이 없다」가 아니라 **「이 실행이 그것을 0으로 계산했다」**이다. "
        "0이 된 자리가 «수량»인지 «단가»인지는 아래 ⓓ 의 그 갈래 산식이 둘을 "
        "함께 실어 말한다",
    ]
    if measured is not None:
        lines.append(
            f"- ⚠ 이 실행의 계통 송전은 대표일 {measured.grid_export:,.2f}kWh 다 — "
            "잉여가 «없어서»가 아니라 **하루 안의 부하 이동(대장 "
            "`load.dr_shiftable_share`)과 저장장치 충전이 그 잉여를 먼저 쓰기 "
            "때문**이며, 디스패치 차례에서 계통 송전이 맨 끝이다(3단계가 그 "
            "차례를 싣는다)"
        )
    return lines


def benefit_pair_lines(report: CaseReport) -> list[str]:
    """4단계에 붙는 「수량 ↔ 금액」 블록 전부 — 표 둘 + 0원 주석.

    ⚠ **부르는 자리는 `core/report/verification.py::_stage4_benefits` 하나**다.
    두 곳에서 부르면 같은 표가 두 번 실리고, 그때 어느 쪽이 정본인지 산출물이
    말하지 못한다.
    """
    basis = report.basis
    measured = measured_over_seasons(report.dispatch_hours, report.seasons)
    return [
        "",
        f"**{PAIR_TITLE}** (검토서 §3.6)",
        "",
        "| 3단계 물리 수량 | 이 실행의 값 | 짝이 되는 금액 | 이 실행의 값 "
        "| 0·미산출이면 그 사유 |",
        "|---|---|---|---|---|",
        *_pair_rows(basis, measured),
        "",
        "**설치비와 교체비를 갈라 적는다** (금액 단위 `원`)",
        "",
        "| 자원 | 설치비 (t=0) | 교체비 (계상 연차) | 잔존가치 (계상 연차) |",
        "|---|---|---|---|",
        *_capex_rows(basis),
        "",
        *_zero_notes(basis, measured),
    ]
