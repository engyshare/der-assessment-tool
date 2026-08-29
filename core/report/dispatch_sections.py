"""붙임 6·7 — **엔진 규칙**과 **시간대별 운전** (검토 「1차 의견」 2·3 · R33).

## 두 의견이 같은 공백을 가리켰다

    「규칙 기반 엔진이 적용되었다는데 규칙이 붙임에 기재되지 않으면
      내용을 이해할 수 없음」                                    ← 의견 2
    「시간대별 디스패치 표」                                      ← 의견 3

리포트는 *「② 디스패치 — 규칙기반 엔진이 대표일 24스텝을 모의한다」* 한 줄로
계산 사슬을 적고 있었다. 규칙이 몇 개이고 어느 자원에 무엇이 붙었으며 그 결과
어느 시간대에 얼마가 나갔는지가 전부 리포트 밖에 있었다.

**재료는 이미 있었다.** `build_dispatch_notes()`(`FR-105-AC4`)와 24스텝 운전
결과가 그것이며, 둘 다 **배포 호출자가 0곳**이었다. 이 파일이 그 둘을 읽는
쪽이다.

## ⚠ 이 파일은 규칙을 **다시 선언하지 않는다**

순서의 정본은 `core/engine/rule_based.py::DEFAULT_RULE_ORDER`, 자원별 배정은
`rule_for()` 다. 여기서 하는 일은 그 선언에 **`FR-302-AC1` 의 문면을 붙이는
것**뿐이며, 이름표가 없는 규칙이 생기면 표가 조용히 비는 대신 그렇게 적힌다
(`_rule_text`).

⚠ **해설을 싣지 않는다** (양식 0절). 표와 「항목 — 값」 나열만 낸다.
⚠ **순서의 소유자는 여전히 `narrative.py` 하나다.**
"""
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from core.casegrid.e2e_runner import DAYS_PER_YEAR
from core.engine.rule_based import DispatchRule
from core.report.case_report import CaseReport
from core.report.dispatch_notes import DispatchHour, DispatchNote

#: 규칙 → 문면. **`FR-302-AC1` 의 일곱 줄을 그대로 옮긴 것**이며 여기서 새로
#: 쓴 말이 아니다 — 조항과 다른 말로 적으면 검토자가 읽는 규칙과 심의 대상
#: 조항이 갈린다.
#: ⚠ **읽기 전용으로 둔다** (`NFR-205`). 지금 아무도 고치지 않는다는 것은
#: 다음 사람도 고치지 않는다는 보장이 아니며, 병렬 실행에서 한 번의 변형은
#: 다른 케이스의 리포트를 조용히 바꾼다.
RULE_TEXT: Mapping[DispatchRule, str] = MappingProxyType({
    DispatchRule.PV_SELF_CONSUMPTION: "PV 발전 → 즉시 자가소비",
    DispatchRule.ESS_CHARGE: "잉여 → ESS 충전 (SOC 상한까지)",
    DispatchRule.V2G_CHARGE: "잉여 → V2G 차량 충전",
    DispatchRule.GRID_EXPORT: "잔여 잉여 → 계통 판매 (직접거래/상계)",
    DispatchRule.ESS_DISCHARGE: "부족 → ESS 방전 (SOC 하한까지)",
    DispatchRule.V2G_DISCHARGE: "부족 → V2G 방전 (최소 SOC 보장)",
    DispatchRule.GRID_IMPORT: "잔여 부족 → 계통 구매",
})

#: 이 구성에 해당 자원이 없어 돌지 않은 규칙의 표기. 빈칸으로 두면 「규칙이
#: 없다」와 「해당 자원이 없다」가 구별되지 않는다.
_NO_HOLDER = "해당 자원 없음"


def _rule_text(rule: DispatchRule) -> str:
    """규칙의 문면. **없으면 조용히 비우지 않고 그렇게 적는다.**"""
    return RULE_TEXT.get(rule, f"문면 미등록 (`{rule.value}`)")


def dispatch_rule_section(report: CaseReport) -> list[str]:
    """붙임 6 — **어떤 규칙으로 운전했는가** (`FR-105-AC4` · 의견 2).

    두 표를 싣는다. 앞은 **규칙 전건과 그 순서**(엔진이 무엇을 할 수 있는가),
    뒤는 **이 사업의 자원에 무엇이 배정됐는가**(이 실행이 무엇을 했는가).
    갈라 싣는 이유는 둘이 서로 다른 물음이기 때문이다 — 한 표로 뭉치면 돌지
    않은 규칙이 돈 것처럼 읽힌다.
    """
    by_rule: dict[DispatchRule, list[DispatchNote]] = {}
    for note in report.dispatch_notes:
        by_rule.setdefault(note.dispatch_rule, []).append(note)

    lines = [
        "## 붙임 6. 디스패치 규칙과 우선순위",
        "",
        "- 엔진 — 규칙기반 (`FR-302`) · 최적화(MILP) 아님",
        "- 규칙 순서 — 기본 순서 (`DEFAULT_RULE_ORDER`) · 변경 가능 "
        "(`FR-302-AC3`)",
        "- 규칙 문면의 출처 — spec `FR-302-AC1`",
        "",
        "### 규칙 순서",
        "",
        "| 순위 | 규칙 | 내용 | 이 실행에서 배정된 자원 |",
        "|---|---|---|---|",
    ]
    for priority, rule in enumerate(report.rule_order):
        holders = by_rule.get(rule, [])
        who = (
            " · ".join(f"`{note.resource_name}`" for note in holders)
            if holders
            else _NO_HOLDER
        )
        lines.append(
            f"| {priority + 1} | `{rule.value}` | {_rule_text(rule)} | {who} |"
        )
    lines += [
        "",
        "### 자원별 배정",
        "",
        "| 자원 | 선택한 운전 방법 | 묶인 규칙 | 순위 | 가격 신호 연동 |",
        "|---|---|---|---|---|",
    ]
    for note in report.dispatch_notes:
        lines.append(
            f"| `{note.resource_name}` | {note.operating_mode} | "
            f"`{note.dispatch_rule.value}` | {note.dispatch_priority + 1} | "
            f"{'예' if note.price_linked else '아니오'} |"
        )
    lines += [
        "",
        "- 「가격 신호 연동」 — 운전 방법이 요금·가격 신호를 입력으로 받는가 "
        "(`needs_price_signal`)",
        "",
    ]
    return lines


def _hour_label(step: int, steps: int) -> str:
    """스텝 라벨. 하루 24스텝일 때만 시각으로 적는다.

    스텝 수가 24가 아닌 실행에서 시각으로 적으면 **없는 해상도를 주장하게
    된다.** 그때는 스텝 번호로 남긴다.
    """
    if steps != 24:
        return f"{step}"
    return f"{step:02d}~{(step + 1) % 24:02d}시"


def dispatch_profile_section(report: CaseReport) -> list[str]:
    """붙임 7 — **시간대별 운전 결과** (의견 3).

    ## 왜 스택 차트가 아니라 표인가

    `core/report/charts/dispatch_stack.py` 가 조항(`FR-1004-AC1`)이 말한
    스택 차트를 이미 갖고 있다. 그런데 그 차트는 `load`(부하 곡선)를 **필수
    입력**으로 요구하고 이 파이프라인에는 가구 부하가 없다(붙임 8). 그래서
    지금 낼 수 있는 것은 표다.

    그 사실은 붙임 8 의 「계통 전력 구매 비용」 행이 이미 싣고 있으므로 여기서
    되풀이하지 않는다 — 같은 사실을 두 곳에 적으면 한쪽만 고쳐진다.
    """
    hours = report.dispatch_hours
    lines = [
        "## 붙임 7. 시간대별 운전 (대표일)",
        "",
        f"- 시간 해상도 — {report.basis.dispatch_note}",
        "- 부호 규약 — 양수: 내보냄(발전·방전) · 음수: 받아들임(소비·충전)",
        "- 단위 — kWh (스텝당)",
        "",
    ]
    if not hours:
        lines += ["- 운전 결과 — 없음 (스텝 0)", ""]
        return lines

    lines += ["### 파이프라인이 실제로 돈 운전", ""]
    lines += _hour_table(hours)
    lines += [
        "- 「계통 송전」 합계 — 붙임 4 잉여 판매 산식이 화폐로 바꾸는 수량",
        "",
    ]
    lines += _assumed_lines(report)
    return lines


def _hour_table(hours: tuple[DispatchHour, ...]) -> list[str]:
    """스텝별 표 하나. **두 운전이 같은 기계로 그려진다** — 갈라 두면 한쪽만
    열이 바뀌고 검토자는 두 표를 나란히 견줄 수 없게 된다."""
    names = tuple(hours[0].per_resource)
    steps = len(hours)
    lines = [
        "| 스텝 | " + " | ".join(f"`{name}`" for name in names)
        + " | 계통 송전 | 계통 수전 |",
        "|---|" + "---|" * (len(names) + 2),
    ]
    for hour in hours:
        cells = " | ".join(f"{hour.per_resource[name]:,.2f}" for name in names)
        lines.append(
            f"| {_hour_label(hour.step, steps)} | {cells} | "
            f"{hour.grid_export:,.2f} | {hour.grid_import:,.2f} |"
        )
    totals = " | ".join(
        f"**{sum(hour.per_resource[name] for hour in hours):,.2f}**"
        for name in names
    )
    lines += [
        f"| **합계** | {totals} | "
        f"**{sum(hour.grid_export for hour in hours):,.2f}** | "
        f"**{sum(hour.grid_import for hour in hours):,.2f}** |",
        "",
    ]
    return lines


def _assumed_lines(report: CaseReport) -> list[str]:
    """가정 운전 — **부하·일사 형상을 주고 다시 그린 것**.

    ## 왜 두 표를 나란히 두는가

    위 표는 파이프라인이 실제로 돈 운전이고 결론(NPV)이 그 위에 서 있다.
    그런데 그 운전에는 **가구 부하가 없다**(붙임 8). 그 상태의 표만 실으면
    검토자는 *부하 없는 단지*를 실물로 읽는다.

    ✔ **「태양광이 24시간 평탄」은 R37 에 해소됐다.** 일사 곡선이 결론에
    배선되어 위 표도 곡선이며, 붙임 8 의 「일중 발전 프로파일 (평탄)」 행은
    사라졌다. 그래서 두 표의 차이는 이제 **부하 하나**이고, 아래 표는 그
    사실을 한 줄로 밝힌다 — 밝히지 않으면 검토자는 무엇이 달라 두 표가 있는지
    알 수 없다.

    ⚠ **아래 표로 결론을 바꾸지 않는다.** 부하를 편익 계산에 태우면 잉여판매가
    줄어드는데 그 대가인 자가소비 절감은 **배타 규칙(유형 A)** 이 동시 계상을
    막고 실측 부하 곡선(`Q-3`)도 없어 켤 수 없다 — 한쪽만 반영한 NPV 는 사업에
    불리한 쪽으로 틀린다(NSPM 대칭성). 그래서 싣는 것은 **수량뿐**이며,
    화폐화 조건은 붙임 8 이 진다.

    ✔ **「소매 단가가 없어」는 이제 사유가 아니다 (R43-H).** 종전 이 자리는 그
    문면이었는데 R34·R35 가 구매·판매 단가를 대장에 세운 뒤 거짓이 됐다. 그
    사실이 실제로 무엇을 막고 있었는지는 붙임 8 이 답한다 — **이 표의 두 차이에
    두 단가를 곱해 방향과 크기를 재어 싣는다**(`unreflected.py::
    _self_consumption_item`). 막고 있는 것은 값이 아니라 배타 규칙과 부하 곡선이다.
    """
    hours = report.assumed_hours
    basis = report.assumed_basis
    if not hours or basis is None:
        # ⚠ **「형상 자산 부재」를 사유로 적지 않는다** (R37 후속).
        # 그 자산은 이제 결론의 입력이므로 없으면 **리포트 자체가 서지 않는다**
        # (`case_report.build_case_report` 가 형상을 먼저 읽는다). 여기까지
        # 왔다는 것은 자산이 있었다는 뜻이고, 남은 사유는 **대장 항목** 하나다.
        # 있을 수 없는 사유를 괄호에 남겨 두면 검토자가 「자산이 없어서 비었을
        # 수도 있다」로 읽는다 — 리포트가 스스로 세운 규칙과 어긋나는 안내다.
        return [
            "- 부하·일사 형상을 가정한 운전 — 미산출 (대장 항목 부재)",
            "",
        ]
    baseline_import = sum(hour.grid_import for hour in report.dispatch_hours)
    baseline_export = sum(hour.grid_export for hour in report.dispatch_hours)
    assumed_import = sum(hour.grid_import for hour in hours)
    assumed_export = sum(hour.grid_export for hour in hours)
    lines = [
        "### 부하·일사 형상을 가정한 운전",
        "",
        f"- 부하 총량 — {basis.load_annual_kwh:,.0f} kWh/년 "
        f"(대장 `{basis.load_ledger_key}` · 신뢰도 {basis.load_confidence})",
        f"- 부하 형상 — {basis.load_title} "
        f"(자산 `fixtures/profiles/` · 신뢰도 {basis.load_confidence})",
        f"- 발전 형상 — {basis.generation_title} "
        f"(자산 `fixtures/profiles/` · 신뢰도 {basis.generation_confidence})",
        "- 연간 발전량 · 부하 총량 — 위 표와 같다 (형상은 배분이지 값이 아니다)",
        "- 위 표와의 차이 — **가구 부하 하나**다. 발전 형상은 위 표에도 "
        "반영되어 있다 (프로포마·결론이 그 위에 선다)",
        "- 반영 범위 — **운전(물리량)만**. 프로포마·결론은 위 표 기준이다",
        "",
    ]
    lines += _hour_table(hours)
    lines += [
        "| 대표일 합계 | 파이프라인 | 형상 가정 | 차이 |",
        "|---|---|---|---|",
        f"| 계통 송전 (kWh) | {baseline_export:,.2f} | {assumed_export:,.2f} | "
        f"{assumed_export - baseline_export:+,.2f} |",
        f"| 계통 수전 (kWh) | {baseline_import:,.2f} | {assumed_import:,.2f} | "
        f"{assumed_import - baseline_import:+,.2f} |",
        f"| 계통 수전 (연간화, kWh) | {baseline_import * DAYS_PER_YEAR:,.0f} | "
        f"{assumed_import * DAYS_PER_YEAR:,.0f} | "
        f"{(assumed_import - baseline_import) * DAYS_PER_YEAR:+,.0f} |",
        "",
        "- 이 차이의 화폐화 조건 — 붙임 8 (자가소비 편익 · 계통 전력 구매 비용)",
        "- 스택 차트(`FR-1004-AC1`) — 미산출 (실측 부하 곡선 부재 · 붙임 8)",
        "",
    ]
    return lines
