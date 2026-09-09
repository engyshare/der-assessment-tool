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

from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType

from core.engine.rule_based import DispatchRule
from core.report.case_report import CaseReport
from core.report.dispatch_notes import (
    DispatchHour,
    DispatchNote,
    build_hourly_profile,
    resolved_operating_mode,
)

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
    # ★★ **칸 이름이 「선택한 운전 방법」이므로 「이 실행이 무엇을 우선했나」까지
    # 실어야 한다** (R64 · WP-VERIFY 결함 2 의 나머지 절반). 종전에는
    # `note.operating_mode`(자원이 **선언한** 짧은 라벨)만 실어서, 같은 리포트의
    # 본문 2.1 「운전 방식」 칸(`core/report/method_sections.py` — 긴 문면)과
    # **같은 물음에 다른 답**을 적고 있었다. 정본은 하나여야 한다.
    modes = {line.name: line.operating_mode for line in report.basis.resources}
    for note in report.dispatch_notes:
        lines.append(
            f"| `{note.resource_name}` | {resolved_operating_mode(note, modes)} | "
            f"`{note.dispatch_rule.value}` | {note.dispatch_priority + 1} | "
            f"{'예' if note.price_linked else '아니오'} |"
        )
    lines += [
        "",
        "- 「선택한 운전 방법」 — 자원이 **선언한** 방법과 이 실행의 **배분**"
        "(`ResourceLine.operating_mode`)",
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

    ## ★★ R64/WP-5 — 연간등가 하루 표 **하나 + 계절마다 하나**

    사용자 요구 6 이 *「계절별로 가구의 전력 수요, 발전, ESS 운전 등을 시간대별로
    수치와 도표로 확인할 수 있어야 함」* 이다. 이 절이 그 **수치**이며, 도표는
    `core/report/charts/seasonal_operation.py` 가 그린다.

    ⚠ **접힌 하루 표를 대신하지 않는다 — 옆에 선다.** 그 표는 연간 총량과 붙임 4
    의 산식에 이어져 있고, 계절별 표는 운전이 계절마다 어떻게 달랐는지를 보인다.
    ⚠ **모든 표를 `_hour_table()` 하나로 그린다** — 아래 그 함수의 ⚠ 참조.

    ## ★ 표가 둘이던 자리다 — R49/★A 가 하나로 줄였다

    종전 이 절은 표를 둘 실었다: 「파이프라인이 실제로 돈 운전」과 「부하·일사
    형상을 **가정한** 운전」. 둘째 표는 *「본 실행에는 없는 가구 부하를 넣어
    보면 어떻게 되는가」* 를 보이는 자리였고, 그 아래에 *「위 표와의 차이 —
    가구 부하 하나다」* 를 인쇄했다.

    **R48 이 본 실행에 가구 부하를 세우면서 두 표가 완전히 같아졌다**(송전·수전
    실측 동일값). 그러므로 그 「차이」 문장은 **거짓**이 됐고, 같은 표를 두 번
    싣는 상태가 남았다. 사용자 판정(2026-08-31 ·
    `docs/decisions-2026-08-31-R49.md` §1)이 둘째 표를 지웠다.

    ## ⚠⚠ 이 판정은 **되돌아올 수 있다** — 비교가 불필요해진 것이 아니다

    지금 지운 것은 *「같은 표를 두 번 싣지 않는다」* 이지 *「가정 부하와 실측
    부하를 견주는 일이 불필요하다」* 가 **아니다.** 가구 부하 총량은 여전히
    대장의 **가정값**(`load.household.annual`)이며, `Q-3` 실측 시계열이 오면
    *「가정 부하 ↔ 실측 부하」* 비교가 다시 의미를 갖는다 — **그때 둘째 표를
    다시 세운다.** 그 자리를 여기에 적어 두지 않으면 다음 사람이 이 절을
    「비교는 원래 없던 것」으로 읽고, 실측이 와도 견줄 자리를 만들지 않는다.

    ## 왜 스택 차트가 아니라 표인가

    `core/report/charts/dispatch_stack.py` 가 조항(`FR-1004-AC1`)이 말한
    스택 차트를 이미 갖고 있다. 그런데 그 차트는 `load`(부하 곡선)를 **필수
    입력**으로 요구하고, 이 실행이 세우는 부하는 **대표일 형상에 총량을 배분한
    가정 곡선**이지 실측 시계열이 아니다(`Q-3` 미확보 · 붙임 8). 그래서 지금
    낼 수 있는 것은 표다.
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

    lines += _hour_table(hours)
    lines += [
        "- 「계통 송전」 합계 — 붙임 4 잉여 판매 산식이 화폐로 바꾸는 수량",
        "- 「계통 수전」 합계 — 붙임 4 계통 전력 구매 산식이 화폐로 바꾸는 수량",
        # ★★ **R64/WP-4 가 더한 두 줄** — 이 표의 하루가 무엇인지 바뀌었다.
        # 계절마다 돌린 하루를 일수로 가중 평균한 하루이므로, 한 스텝에서
        # 송전과 수전이 **함께 0 이 아닐 수 있다.** 그것은 결함이 아니라
        # 「어떤 계절은 그 시각에 내보내고 어떤 계절은 받아들인다」는 뜻이며,
        # 적어 두지 않으면 검토자가 표의 결함으로 읽는다.
        "- 이 표의 하루 — 계절별 대표일을 **계절일수로 가중 평균한 연간등가 "
        "하루**다 (위 「시간 해상도」 참조). 계절 간 차이는 이 하루로 접히므로 "
        "여기서 되돌릴 수 없다",
        "- 같은 스텝에 송전과 수전이 함께 있을 수 있다 — 계절마다 그 시각의 "
        "수지가 달라 평균에 둘 다 남는 것이며, 스텝별 수지는 그대로 닫힌다",
        "- 반영 범위 — **이 표의 운전 위에 프로포마·결론이 선다** (본문 4·5절)",
        "- 부하 형상은 **배분이지 값이 아니다** — 연간 총량은 대장 "
        "`load.household.annual` 이 정하고, 형상은 자산 "
        "`fixtures/profiles/` 가 정한다",
        "- 스택 차트(`FR-1004-AC1`) — 미산출 (실측 부하 곡선 `Q-3` 부재 · 붙임 8)",
        # ★★ **R64/WP-5** — 아래 계절별 표가 이 표의 「옆에」 선다. 어느 쪽이
        # 틀린 것이 아니라 둘이 다른 것을 보인다는 사실을 여기서 한 줄로 적는다.
        "- 아래 계절별 표와의 차이 — 이 표의 하루는 계절을 평균한 하루라 한 "
        "스텝이 두 방향을 함께 가질 수 있고, 계절별 하루에는 그런 스텝이 없다. "
        "두 표는 서로 다른 것을 보이며 둘 다 이 실행의 결과다",
        "",
    ]
    lines += _season_sections(report)
    return lines


def _season_sections(report: CaseReport) -> list[str]:
    """붙임 7 의 **계절별 표** — 사용자 요구 6 (R64/WP-5 · 판정 ②③).

    ## ⚠⚠ 표를 그리는 코드를 두 벌 만들지 않는다

    계절별 표도 `_hour_table()` 로 그린다. 갈라 두면 한쪽만 열이 바뀌어 검토자가
    둘을 견줄 수 없고, 그 어긋남은 아무 예외도 내지 않는다 — 그 함수의
    독스트링이 같은 사유를 이미 적었다. 계절 하루를 스텝으로 펴는 것도
    `build_hourly_profile()` 이며, 연간등가 하루가 쓰는 **바로 그 함수**다.

    ## ⚠ 접힌 하루 표를 대신하지 않는다 — **옆에** 선다

    위 표는 연간 총량과 붙임 4 의 산식에 이어져 있고, 이 표들은 운전이 계절마다
    어떻게 달랐는지를 보인다. **둘 다 참이며 서로 다른 물음에 답한다.**

    ## 계절이 둘 미만이면 표를 세우지 않고 **그렇게 적는다**

    계절 하나짜리 자산(또는 형상 없는 실행)에서 계절별 표는 위 표를 그대로 한 번
    더 인쇄한 것이 된다. 조용히 건너뛰면 「계절이 없다」와 「계절 절이 빠졌다」가
    산출물에서 같아지므로 사유를 글자로 남긴다.
    """
    seasons = report.seasons
    lines = ["### 계절별 시간대별 운전", ""]
    if len(seasons) < 2:
        return [
            *lines,
            f"- 계절 갈래 없음 — 이 실행의 형상 자산이 계절을 {len(seasons)}개 "
            "선언했다. 위 표의 하루가 이 실행의 유일한 하루이므로 같은 표를 한 "
            "번 더 싣지 않는다",
            "",
        ]

    profiles = [build_hourly_profile(season.dispatch) for season in seasons]
    if not all(profiles):
        empty = [s.name for s, hours in zip(seasons, profiles, strict=True) if not hours]
        return [
            *lines,
            f"- 계절별 표 미산출 — 스텝이 0인 계절이 있다 ({' · '.join(empty)}). "
            "빈 표를 세우면 「그 계절은 아무 일도 하지 않았다」로 인쇄된다",
            "",
        ]

    total_days = sum(season.days for season in seasons)
    lines += [
        "- 계절 이름·일수·계절 몫 — 자산 "
        "`fixtures/profiles/representative-day.yaml` 이 정한 **가정값**이며 "
        "실측이 아니다 (붙임 8 의 「계절·요일 변동」 항목이 그 결손을 신고한다)",
        f"- 계절 {len(seasons)}개 · 일수 합계 {total_days}일",
        "",
    ]
    for season, hours in zip(seasons, profiles, strict=True):
        lines += [f"#### {season.name} — 대표일 (연 {season.days}일)", ""]
        lines += _hour_table(hours)

    lines += _season_annual_table(report, tuple(profiles[0][0].per_resource))
    return lines


def _season_annual_table(
    report: CaseReport, names: tuple[str, ...]
) -> list[str]:
    """계절별 **연간 기여** — 하루 합에 그 계절 일수를 곱한 것.

    ⚠ **여기서 `365` 를 곱하지 않는다.** 계절마다 다른 일수를 곱하는 것이 계절
    축이 여는 것 그 자체이고, 그 곱은 러너가 이미 해 `SeasonRun` 에 실어 왔다
    (`core/casegrid/models.py::SeasonRun`). 표시 층이 다시 곱하면 계절을 모르는
    종전 연간화로 조용히 되돌아간다.

    ⚠⚠ **열 차례를 여기서 정하지 않는다.** 스텝 표의 열 차례
    (`build_hourly_profile` 이 정렬한 것)를 그대로 받는다 — 두 표가 같은 절에
    서는데 열이 갈리면 검토자가 위아래를 맞대 볼 수 없고, `SeasonRun.
    per_resource_annual_kwh` 의 차례는 운전 결과의 삽입 차례라 그것과 다르다.

    ⚠ 합계 행은 **위 연간등가 하루 표 합계의 일수 합계배**와 같다 — 두 표가 같은
    실행을 보고 있다는 증거이며, 갈리면 한쪽이 거짓이다.
    """
    seasons = report.seasons
    lines = [
        "#### 계절별 연간 기여 (kWh/년)",
        "",
        "| 계절 | 일수 | " + " | ".join(f"`{name}`" for name in names)
        + " | 계통 송전 | 계통 수전 |",
        "|---|---|" + "---|" * (len(names) + 2),
    ]
    for season in seasons:
        cells = " | ".join(
            f"{season.per_resource_annual_kwh[name]:,.2f}" for name in names
        )
        lines.append(
            f"| {season.name} | {season.days} | {cells} | "
            f"{season.grid_export_annual_kwh:,.2f} | "
            f"{season.grid_import_annual_kwh:,.2f} |"
        )
    totals = " | ".join(
        f"**{sum(s.per_resource_annual_kwh[name] for s in seasons):,.2f}**"
        for name in names
    )
    lines += [
        f"| **합계** | **{sum(s.days for s in seasons)}** | {totals} | "
        f"**{sum(s.grid_export_annual_kwh for s in seasons):,.2f}** | "
        f"**{sum(s.grid_import_annual_kwh for s in seasons):,.2f}** |",
        "",
        "- 이 합계는 위 연간등가 하루 표의 합계에 일수 합계를 곱한 값과 같다 — "
        "두 표가 같은 실행을 보고 있다는 뜻이다",
        "",
    ]
    return lines


def _hour_table(hours: tuple[DispatchHour, ...]) -> list[str]:
    """붙임 7 의 스텝 표 — **자원별 부호 표**. 이 붙임의 모든 스텝 표가 이것이다.

    ⚠ 함수로 갈라 둔 것은 표가 둘이던 시절의 흔적이 아니다. `Q-3` 실측이 오면
    둘째 표가 돌아오고(위 독스트링), 그때 **두 표가 같은 기계로 그려져야**
    한다 — 갈라 두지 않으면 한쪽만 열이 바뀌어 검토자가 둘을 견줄 수 없다.

    ⚠⚠ **R64/WP-5 가 그날을 앞당겼다.** 계절별 표가 이 함수를 그대로 부르므로
    이 절에는 이제 `1 + 계절 수` 개의 스텝 표가 선다. 열을 바꾸려면 여기서
    바꾸면 전부 함께 바뀐다 — 계절 쪽에 사본을 만들지 마라.

    ## ★★ R68/WP-3 — **그리는 기계가 `step_table()` 로 내려갔다**

    검증 3단계가 같은 하루를 **사람용 양수 표**로도 실어야 했다(검토서 §3.4 ·
    §4.3). 그 표는 열 구성이 다르다 — 붙임 7 은 자원별 **부호** 표이고 검증
    3단계는 총부하·발전·충전·방전을 **양수 별도 열**로 가른 표다. 그렇다고
    표를 두 벌로 그리면 이 함수의 ⚠ 가 금한 상태가 정확히 돌아온다. ⇒ **그리는
    기계 하나 + 열 구성은 인자**로 갈랐고, 이 함수는 그 기계에 붙임 7 의 열
    구성(`_resource_columns`)을 먹인다. **붙임 7 의 열은 한 글자도 바뀌지 않았다.**
    """
    return step_table(hours, _resource_columns(tuple(hours[0].per_resource)))


#: 스텝 표의 열 하나 — (머리글, 그 스텝에서 값을 꺼내는 함수).
#:
#: ⚠ 머리글과 꺼내는 법을 **한 쌍으로** 묶는다. 두 목록으로 갈라 넘기면 길이나
#: 차례가 어긋나는 날 표가 **다른 열의 값을 그 이름 아래 인쇄하고**, 그것은 아무
#: 예외도 내지 않는다.
StepColumn = tuple[str, Callable[[DispatchHour], float]]


def _resource_columns(names: tuple[str, ...]) -> tuple[StepColumn, ...]:
    """붙임 7 의 열 구성 — **자원별 부호 열 + 계통 송·수전**.

    ⚠ **부호를 여기서 뒤집지 않는다.** `DispatchHour` 의 ⚠ 가 그 사유를 진다 —
    충전과 방전이 한 열에 서야 「스텝 합계가 계통 송전량과 맞는가」를 눈으로
    셀 수 있다. 부호를 걷은 표가 필요한 자리는 `human_step_columns()` 다.
    """
    return (
        *((f"`{name}`", _resource_value(name)) for name in names),
        ("계통 송전", lambda hour: hour.grid_export),
        ("계통 수전", lambda hour: hour.grid_import),
    )


def _resource_value(name: str) -> Callable[[DispatchHour], float]:
    """자원 하나의 스텝값을 꺼내는 함수. **없는 자원은 0 이 아니라 예외다** —
    붙임 7 의 열 목록은 그 하루가 정하므로 없는 이름이 오면 그것이 결함이다."""
    def get(hour: DispatchHour) -> float:
        return hour.per_resource[name]

    return get


def step_table(
    hours: tuple[DispatchHour, ...],
    columns: tuple[StepColumn, ...],
    *,
    step_head: str = "스텝",
) -> list[str]:
    """★ 스텝 표를 그리는 **하나뿐인 기계** — 열 구성은 인자로 받는다 (R68/WP-3).

    ## ⚠⚠ 여기 말고 다른 곳에서 스텝 표를 그리지 마라

    이 저장소에는 지금 스텝 표가 **두 종류**로 선다 — 붙임 7 의 자원별 부호 표
    (`_resource_columns`)와 검증 3단계의 사람용 양수 표(`human_step_columns`).
    둘은 **다른 물음에 답하므로 열이 다르지만**, 「스텝 라벨을 어떻게 적는가 ·
    합계 행을 어떻게 내는가 · 표의 서식이 무엇인가」는 같아야 한다. 사본을
    만들면 한쪽만 바뀌는 날 두 표를 맞대 볼 수 없고 그 어긋남은 조용하다.

    ⚠ **합계 행을 뺄 수 없게 두었다.** 이 저장소의 스텝 표는 전부 합계로
    검증된다 — 붙임 7 은 붙임 4 산식의 대입값과, 검증 3단계는 그 계절의 연간값과
    맞댄다(`season_step_tables`). 선택 인자로 두면 합계 없는 표가 생기고 그
    표는 대조할 수 없다.

    Args:
        hours: 그 하루의 스텝 전건. **표본이 아니라 전건이다.**
        columns: 열 구성. 차례가 그대로 인쇄 차례다.
        step_head: 첫 칸의 머리글. 붙임 7 은 「스텝」, 사람용 표는 「시각」이다 —
            `_hour_label()` 이 24스텝일 때만 시각으로 적으므로 머리글도 그
            갈래를 따라야 한다(24가 아닌 실행에서 「시각」은 없는 해상도를
            주장하는 것이 된다).
    """
    steps = len(hours)
    lines = [
        f"| {step_head} | " + " | ".join(head for head, _ in columns) + " |",
        "|---|" + "---|" * len(columns),
    ]
    for hour in hours:
        cells = " | ".join(f"{get(hour):,.2f}" for _, get in columns)
        lines.append(f"| {_hour_label(hour.step, steps)} | {cells} |")
    totals = " | ".join(
        f"**{sum(get(hour) for hour in hours):,.2f}**" for _, get in columns
    )
    lines += [f"| **합계** | {totals} |", ""]
    return lines


# ── 사람용 양수 열 — 검증 3단계가 쓰는 열 구성 (R68/WP-3 · 검토서 §3.4·§4.3) ──
#
# ## 왜 열이 붙임 7 과 다른가
#
# 검토서 §4.3 문면: *「사람용 표에서는 «한전 수전»·«한전 역송»을 양의 수량으로
# 별도 열에 두고, 내부 부호는 수식 설명에만 남기는 편이 안전하다」*. 붙임 7 은
# 그 반대 요구를 진다 — 자원 수지는 **부호가 뜻**이어야 「스텝 합계가 계통
# 송전량과 맞는가」를 눈으로 셀 수 있다(`DispatchHour` 의 ⚠).
#
# ⇒ **두 요구가 둘 다 참이므로 표가 둘**이다. 갈리는 것은 열 구성뿐이고 그리는
# 기계는 위 `step_table()` 하나다.
#
# ⚠ 머리글에 단위를 적지 않는다 — **표 제목이 진다**(검토서 §4.2 · 한 표 안에서
# 여섯 열이 같은 단위이므로 열마다 되풀이하면 표가 읽기 어려워진다).

#: 부하 쪽 자원의 소비량을 **양수로** 실는 열.
LOAD_HEAD = "총부하"
#: 발전 쪽 자원의 발전량을 실는 열.
GENERATION_HEAD = "발전"
#: 저장장치가 **받아들인** 양(음수의 절댓값).
STORAGE_CHARGE_HEAD = "저장장치 충전"
#: 저장장치가 **내보낸** 양(양수 그대로).
STORAGE_DISCHARGE_HEAD = "저장장치 방전"
GRID_IMPORT_HEAD = "한전 수전"
GRID_EXPORT_HEAD = "한전 역송"


def _role_sum(names: Sequence[str], *, sign: float) -> Callable[[DispatchHour], float]:
    """그 갈래 자원들의 스텝값 합에 `sign` 을 곱한다 — 부하는 `sign=-1` 로 양수가 된다.

    ⚠ **자르지 않는다.** 이 함수를 쓰는 갈래(발전·부하)는 `split_three_ways()`
    가 **전 스텝의 부호가 한쪽인 것**만 넣으므로 곱한 값이 이미 0 이상이다.
    여기서 `max(0, …)` 로 자르면 그 성질이 깨진 날 **음수가 조용히 0 으로**
    인쇄되고, 그때 표는 「그 시각에 부하가 없었다」를 주장한다.
    """
    frozen = tuple(names)
    def get(hour: DispatchHour) -> float:
        return sign * sum(hour.per_resource.get(name, 0.0) for name in frozen)

    return get


def _role_clipped(
    names: Sequence[str], *, sign: float
) -> Callable[[DispatchHour], float]:
    """그 갈래 자원들의 스텝값 중 **한쪽 방향만** 골라 양수로 합한다.

    저장장치는 같은 하루에 충전(음수)과 방전(양수)을 **함께** 하므로 두 열로
    가르려면 방향별로 잘라야 한다 — 자르지 않으면 두 열이 같은 순액을 두 번
    인쇄하고, 그러면 「그 시각에 얼마를 받아들였는가」에 답할 수 없다.
    """
    frozen = tuple(names)
    def get(hour: DispatchHour) -> float:
        return sum(
            max(0.0, sign * hour.per_resource.get(name, 0.0)) for name in frozen
        )

    return get


def human_step_columns(
    generation: Sequence[str],
    storage: Sequence[str],
    load: Sequence[str],
) -> tuple[StepColumn, ...]:
    """검증 3단계의 열 구성 — **부호를 읽지 않고 읽는 여섯 열**.

    ## ⚠⚠ 빈 갈래는 **0 열을 세우지 않고 아예 세우지 않는다**

    저장장치 없는 실행에서 「저장장치 충전 0.00」 열을 스물넷 인쇄하면 그것은
    *「저장장치가 있는데 하루 종일 안 움직였다」* 로 읽힌다 — 이 저장소의 ★★
    규약(*「`None` 은 빈칸이 아니라 진술이다」*)이 금하는 자리다. ⇒ 열을 세우지
    않고, **왜 없는지는 부르는 쪽이 글자로 적는다**
    (`core/report/verification_dispatch.py::season_step_tables`). 둘 중 하나만
    하면 「열이 빠졌다」와 「그 자원이 없다」가 산출물에서 같아진다.

    ⚠ 계통 두 열은 **갈래와 무관하게 언제나 선다** — 자원이 하나도 없는 실행도
    계통에서 받아 오거나 내보낼 수 있고, 그 둘은 `DispatchHour` 가 직접 나른다.

    Args:
        generation: 발전 쪽 자원 이름 · storage: 저장장치 · load: 부하 쪽.
            셋의 가름은 `split_three_ways()` 하나가 하며 여기서 다시 하지 않는다.
    """
    columns: list[StepColumn] = []
    if load:
        columns.append((LOAD_HEAD, _role_sum(load, sign=-1.0)))
    if generation:
        columns.append((GENERATION_HEAD, _role_sum(generation, sign=1.0)))
    if storage:
        columns.append((STORAGE_CHARGE_HEAD, _role_clipped(storage, sign=-1.0)))
        columns.append((STORAGE_DISCHARGE_HEAD, _role_clipped(storage, sign=1.0)))
    columns += [
        (GRID_IMPORT_HEAD, lambda hour: hour.grid_import),
        (GRID_EXPORT_HEAD, lambda hour: hour.grid_export),
    ]
    return tuple(columns)
