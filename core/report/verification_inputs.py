"""검증 보고서가 채우는 네 자리 — 실행 입력 · 역산 · 계절 · 미반영 (R64/WP-TXT).

## 무엇을 여는가

사용자 지적(2026-09-06): *「현재 검증 모드라는 기능이 구현되어 있을 텐데 그
내용은 텍스트로 구성되어 있습니다」*. 그래서 **새 렌더러를 세우지 않았다** —
`core/report/verification.py::render_verification_markdown` 이 이미 내는 9단계
마크다운에 **빠져 있던 다섯 자리**를 채운다. 그 다섯은 실측으로 골랐다(그
379줄에서 「히트펌프」·「전기차」·「적정」·「역산」·「미반영」이 **0건**이었고
계절은 낱말 하나뿐이었다).

## 왜 `verification.py` 에서 갈라 나왔는가

그 파일은 488줄이었고 여기 담은 네 자리를 그 안에 두면 `NFR-206`(파일 500줄)을
넘긴다. **상한을 올려 풀지 않았다** — 이 저장소는 같은 자리에서 이미 두 번
모듈을 뗐다(`core/report/case_influences.py` · `core/report/case_formulas.py`).

## ⚠⚠ 출구는 `render_verification_markdown()` **하나다**

여기 있는 함수는 **줄 목록만** 낸다. 밖에서 직접 부르면 화면(`/ui/verify`)이
싣는 문면과 파일로 떨군 문면이 갈리고, 그것이
`app/services/verify_steps.py` 머리말이 경고한 「통로가 둘」이다.

## ⛔ 새로 계산하지 않는다 — `CaseReport` 를 **읽기만** 한다

`verification.py` 머리말의 규약 그대로다. 계절별 운전은 `CaseReport.seasons`,
가구 수는 `CaseReport.household_count`, 기기 부하와 계절 몫은
`CaseReport.appliance_loads`, 역산은 `CaseReport.capacity_review` ·
`CaseReport.self_sufficiency` · `CaseReport.ess_sizing` 이 이미 갖고 있다.
여기서 다시 세우면 **인쇄된 값과 결론이 선 값이 갈린다.**

## ★★ `None` 은 빈칸이 아니라 «진술»이다

`CaseReport.household_count` 와 `ApplianceLoads` 주석이 그것을 세 번 경고한다.
빈칸·`-`·`None` 을 인쇄하지 않고 **그 사실을 글자로** 적는다 —
`core/casegrid/household_scale.py::HOUSEHOLD_COUNT_UNSPECIFIED` ·
`core/casegrid/appliance_load.py::APPLIANCE_LOAD_UNSPECIFIED` ·
`core/casegrid/appliance_load.py::APPLIANCE_SEASON_SHARE_UNSPECIFIED` 가 그
문면의 정본이며, 베껴 적지 않고 들여와 쓴다.

## ⚠ 단계를 «늘리지» 않는다

네 자리는 전부 **기존 단계 본문 안**에 실린다(1·2·3단계와 9단계 뒤).
화면은 `app/services/verify_steps.py::STAGE_COUNT` 로 9를 기대하고
`app/services/verify_steps.py::split_stages` 가 단계 머리글로 쪼갠다 — 그래서
이 모듈이 내는 어떤 줄도 `## N단계 — ` 로 시작하지 않는다. 미반영 절만
`###` 을 쓰며, 그것은 그 정규식에 걸리지 않는다.

## ⚠ 해설을 붙이지 않는다

`verification.py` 판정 §6 이 이 모듈에도 그대로 걸린다 — 「이 사업은 …이다」류
판정 문장은 싣지 않는다. 적는 것은 **무엇으로 돌았는가**와 **무엇을 세지
않았는가** 뿐이다.
"""
from __future__ import annotations

from core.casegrid.appliance_load import (
    APPLIANCE_LOAD_UNIT,
    APPLIANCE_LOAD_UNSPECIFIED,
    APPLIANCE_SEASON_SHARE_FIELD,
    APPLIANCE_SEASON_SHARE_TITLE,
    APPLIANCE_SEASON_SHARE_UNSPECIFIED,
    EV_LOAD_FIELD,
    EV_LOAD_TITLE,
    HEATPUMP_LOAD_FIELD,
    HEATPUMP_LOAD_TITLE,
    ApplianceSeasonShares,
)
from core.casegrid.household_scale import (
    HOUSEHOLD_COUNT_FIELD,
    HOUSEHOLD_COUNT_LEDGER_KEY,
    HOUSEHOLD_COUNT_UNSPECIFIED,
)
from core.casegrid.ledger_levels import LEVEL_NAMES
from core.casegrid.load_shift import (
    DR_SHIFT_NOTHING_MOVED,
    DR_SHIFTABLE_SHARE_LEDGER_KEY,
    DR_SHIFTABLE_SHARE_TITLE,
    DR_SHIFTABLE_SHARE_UNIT,
)
from core.casegrid.models import SeasonRun
from core.report._format import NO_VALUE, _num, _won
from core.report.capacity import UNBOUNDED_NOTE, CapacityFinding
from core.report.case_report import CaseReport
from core.report.dispatch_notes import resolved_operating_mode
from core.report.ess_sizing_section import ESSSizingReview
from core.report.sizing import SelfSufficiencySizing
from core.report.unreflected import build_unreflected, unreflected_direction_tally

#: 「그렇다/아니다」 두 글자를 한 자리에서만 정한다 — 표마다 다른 낱말을 쓰면
#: 훑는 눈이 다른 판정으로 읽는다(`core/report/_format.py::_recovery` 와 같은
#: 사유다).
_YES = "예"
_NO = "아니오"


# ── 1단계 — 대장이 갖지 않는 실행 입력 (사용자 요구 1·2·3) ─────────────────


def _household_cell(count: int | None) -> str:
    """가구 수 칸 — **없으면 문장을 적는다**(모듈 머리말 ★★)."""
    return f"{count:,}호" if count is not None else HOUSEHOLD_COUNT_UNSPECIFIED


def _appliance_cell(value: float | None) -> str:
    """기기 부하 칸 하나.

    ⚠ `0` 과 「미지정」이 **다르게** 인쇄된다 — 더해지는 값은 둘 다 0 이지만
    앞의 것은 *「그 기기가 없다고 적었다」*이고 뒤의 것은 *「있는지 아직
    모른다」*다(`ApplianceLoads` 머리말).
    """
    if value is None:
        return APPLIANCE_LOAD_UNSPECIFIED
    return f"{value:,.0f} {APPLIANCE_LOAD_UNIT}"


def _season_share_cell(shares: ApplianceSeasonShares | None) -> str:
    """계절 몫 칸 — 적었으면 계절마다의 몫을, 안 적었으면 그 사실을 적는다.

    ⚠ **몫을 정규화해 보이지 않는다.** 사용자가 적은 수를 그대로 인쇄한다 —
    합이 1 이 아닌 값은 `resolve_appliance_season_shares` 가 이미 거부했으므로
    여기 도착하는 것은 합이 1 인 것뿐이다.
    """
    if shares is None:
        return APPLIANCE_SEASON_SHARE_UNSPECIFIED
    return " · ".join(f"{name} {share:.1%}" for name, share in shares.by_season)


def execution_input_lines(report: CaseReport) -> list[str]:
    """1단계 ⓐ 뒤 — **대장이 아니라 실행 입력이 정한 값** (요구 1·2).

    ## 왜 1단계인가

    이 일곱은 계산의 결과가 아니라 **이 실행이 받은 전제**다. 대장 표(위 ⓑ)는
    *「대장이 무엇을 갖고 있는가」*를 적고 이 표는 *「이 실행이 무엇으로
    돌았는가」*를 적는다 — 둘은 다른 진술이며, 앞의 넷은 대장이 `track:
    blocked` · 값 없음으로 두어 **애초에 대장에서 올 수 없다.**

    ## ⚠ 화면과 시나리오의 통로가 항목마다 다르다

    가구 수·히트펌프·전기차는 화면(`/ui/run`)에도 칸이 있고, **계절 몫은
    시나리오 yaml 에만 있다.** 「시나리오에서도 못 바꾼다」로 적으면 거짓이므로
    통로 칸이 그 차이를 그대로 나른다.

    ## ★★ 할인율이 **여기** 있는 이유 (R64/WP-FIX 결함 1)

    8단계 ⓐ 가 *「1단계 할인율」* 을 가리키는데 1단계에 그 행이 없었다 —
    할인율은 대장 항목이 **아니다**(`docs/assumptions.yaml` 에 0건 ·
    `core/casegrid/ledger_levels.py`: *「평가자가 고르는 모형 파라미터」*). 곧
    이 표의 정의에 드는 값이므로 **참조를 지우는 대신 참으로 만든다.**
    """
    loads = report.appliance_loads
    return [
        "",
        "**이 실행이 받은 입력 — 대장이 갖지 않는 값** (사용자 요구 1·2·3)",
        "",
        "| 항목 | 이 실행의 값 | 실행 입력의 통로 |",
        "|---|---|---|",
        f"| 단지 가구 수 | {_household_cell(report.household_count)} "
        f"| 시나리오 yaml `{HOUSEHOLD_COUNT_FIELD}` · 화면 `/ui/run` 칸 |",
        f"| {HEATPUMP_LOAD_TITLE} | {_appliance_cell(loads.heatpump_kwh)} "
        f"| 시나리오 yaml `{HEATPUMP_LOAD_FIELD}` · 화면 `/ui/run` 칸 |",
        f"| {EV_LOAD_TITLE} | {_appliance_cell(loads.ev_kwh)} "
        f"| 시나리오 yaml `{EV_LOAD_FIELD}` · 화면 `/ui/run` 칸 |",
        f"| 한 호에 더해진 합계 | {loads.total_kwh:,.0f} {APPLIANCE_LOAD_UNIT} "
        "| 위 둘의 합 — 러너의 `extra_appliance_load_kwh` 로 간다 |",
        f"| {APPLIANCE_SEASON_SHARE_TITLE} "
        f"| {_season_share_cell(loads.season_shares)} "
        f"| 시나리오 yaml `{APPLIANCE_SEASON_SHARE_FIELD}` — "
        "**화면 칸은 아직 없다** |",
        f"| {DR_SHIFTABLE_SHARE_TITLE}(「AI 가전」) "
        f"| {report.dr_shiftable_share_pct:,.1f} {DR_SHIFTABLE_SHARE_UNIT} "
        f"| 대장 `{DR_SHIFTABLE_SHARE_LEDGER_KEY}` — 시나리오 yaml 의 "
        "`assumption_overrides` · 설정 화면의 대장 항목 칸 |",
        f"| 할인율 (8단계 `NPV` 의 r) | {report.basis.discount_rate:.1%} "
        "| **대장에 없다** — 케이스 수준표 `core/casegrid/ledger_levels.py` 의 "
        f"모형 파라미터이며 갈래 셋({' · '.join(LEVEL_NAMES)}) 중 이 실행의 "
        "케이스 값이 고른 것 |",
        "",
        "- 「미지정」은 **빈칸이 아니라 진술**이다 — 가구 수가 미지정이면 이 "
        "보고서의 모든 수량과 금액이 **가구 한 호의 것**이고, 기기 부하가 "
        "미지정이면 그 기기를 **0으로 얹고** 돌았다는 뜻이다",
        f"- 위 넷의 대장 자리는 값이 비어 있다(예: `{HOUSEHOLD_COUNT_LEDGER_KEY}` "
        "— `track: blocked`) — 그 기기를 가구가 갖는지는 **사업 계획이 정하는 "
        "사실**이므로 저장소가 기본값으로 메우지 않는다",
        "- 단지 총부하 = 가구 수 × (가구 한 호의 연간 사용량 + 그 호의 추가 "  # noqa: RUF001
        "전력사용기기 소비량) — **더한 뒤에 곱한다**",
        "- ⚠ **부하이지 설비가 아니다.** 히트펌프·전기차의 설치비·유지보수비와 "
        "그 설비가 만드는 편익은 이 표에 없다 — 2단계 자원 목록이 세운 것만이 "
        "설비이며, 부하에 편익을 붙이면 같은 흐름이 두 번 계상된다",
        "- 「AI 가전」은 **더해지는 부하가 아니라 옮기는 부하**다 — 그 비율이 "
        "커져도 연간 부하 총량은 한 kWh 도 변하지 않고, 옮겨 가는 곳은 그 계절 "
        "하루의 태양광 잉여가 있는 시각이다(3단계 계절별 표의 「옮긴 몫」)",
        f"- {APPLIANCE_SEASON_SHARE_TITLE}을 적으면 냉난방 부하가 **자기 계절 "
        "몫**으로 갈리고, 적지 않으면 기본 부하와 같은 계절 몫으로 돈다 — 어느 "
        "쪽이든 연간 총량은 같다(옮겨 갈 뿐이다)",
    ]


# ── 2단계 — 적정 용량 검토와 역산 (사용자 요구 4) ───────────────────────────


def _capacity_table(findings: tuple[CapacityFinding, ...]) -> list[str]:
    """설계 변수 스윕 표 — **점이 없어도 표를 지우지 않는다.**"""
    if not findings:
        return ["- 설계 변수 — 없음 (이 실행에는 훑을 용량 축이 서지 않았다)"]
    rows = [
        "| 설계 변수 | 사용값 | 탐색 구간 | 한계 기여 | 결론 축의 형태 "
        "| 구간 내 최선 | 적정값이 이 모델 안에서 정해지는가 |",
        "|---|---|---|---|---|---|---|",
    ]
    for finding in findings:
        values = [point.value for point in finding.points]
        marginal = (
            f"{_won(finding.marginal_won_per_unit)}/{finding.unit}"
            if finding.marginal_won_per_unit is not None
            else NO_VALUE
        )
        best = (
            f"{finding.best_value:g} {finding.unit}"
            if finding.best_value is not None
            else NO_VALUE
        )
        bounded = _YES if finding.bounded else f"{_NO} · {UNBOUNDED_NOTE}"
        rows.append(
            f"| {finding.label} (`{finding.variable}`) "
            f"| {finding.used_value:g} {finding.unit} "
            f"| {min(values):g}~{max(values):g} {finding.unit} "
            f"({len(values)}점) | {marginal} | {finding.shape} | {best} "
            f"| {bounded} |"
        )
    return rows


def _self_sufficiency_table(sizing: SelfSufficiencySizing) -> list[str]:
    """100% 자립 역산 — 부하 수준마다 필요한 태양광 용량."""
    span = f"{sizing.search_low_kw:g}~{sizing.search_high_kw:g}kW"
    rows = [
        "| 부하 수준 | 연간 부하 | 100% 자립에 필요한 태양광 | 탐색 구간 안인가 |",
        "|---|---|---|---|",
    ]
    for point in sizing.points:
        within = _YES if point.within_search_range else f"{_NO} — 구간 {span} 밖"
        rows.append(
            f"| {point.source_label} | {_num(point.annual_load_kwh)}kWh "
            f"| {point.required_capacity_kw:,.2f}kW | {within} |"
        )
    rows += [
        "",
        "- 산식 — 필요 용량(kW) = 연간 부하(kWh) ÷ (8,760h × 이용률 "  # noqa: RUF001
        f"{sizing.capacity_factor:.0%})",
        f"- 이용률의 출처 — {sizing.capacity_factor_source}",
    ]
    return rows


def _ess_sizing_table(review: ESSSizingReview) -> list[str]:
    """하루 결손 역산 — 계절마다 필요한 저장장치 용량·출력.

    ⚠ **못 한 것을 「없음」으로 두지 않는다** — 역산할 수 없는 실행에서는
    `ESSSizingReview.unmeasurable_reason` 이 그 사유를 글자로 갖는다.
    """
    if review.unmeasurable_reason is not None:
        return [f"- 역산하지 못했다 — {review.unmeasurable_reason}"]
    span = f"{review.search_low_kwh:g}~{review.search_high_kwh:g}kWh"
    rows = [
        "| 계절 | 일수 | 하루 필요 방전량 | 최대 결손(스텝) | 필요 정격용량 "
        "| 필요 정격출력 | 탐색 구간 안인가 |",
        "|---|---|---|---|---|---|---|",
    ]
    for season in review.seasons:
        sizing = season.sizing
        within = _YES if sizing.within_search_range else f"{_NO} — 구간 {span} 밖"
        rows.append(
            f"| {season.season_name} | {season.days}일 "
            f"| {sizing.required_discharge_kwh:,.2f}kWh "
            f"| {sizing.peak_shortfall_kwh:,.2f}kWh "
            f"| {sizing.required_capacity_kwh:,.2f}kWh "
            f"| {sizing.required_power_kw:,.2f}kW | {within} |"
        )
    per_capacity = (
        f"{review.usable_per_capacity_kwh:,.4f}"
        if review.usable_per_capacity_kwh is not None
        else NO_VALUE
    )
    rows += [
        "",
        f"- 산식 — 필요 정격용량(kWh) = 하루 필요 방전량 ÷ {per_capacity} "
        f"(정격용량 1kWh 가 {review.year}년차에 낼 수 있는 양 = SOC 창 × SOH "  # noqa: RUF001
        "× (1 − 백업 예비))",  # noqa: RUF001
        f"- 어느 해의 결손인가 — 분석기간 말({review.year}년차). 열화가 가장 "
        "진행된 해라 필요한 용량이 가장 크다",
    ]
    return rows


def capacity_review_lines(report: CaseReport) -> list[str]:
    """2단계 ⓑ 뒤 — **적정 용량 검토와 역산** (사용자 요구 4).

    ## ⚠⚠ 진단이지 결론이 아니다

    아래 셋은 이 실행의 자원 구성을 **바꾸지 않는다.** 역산 결과를 실행에
    되먹이지 않으므로 8단계 지표는 이 수에 움직이지 않으며, 그 사실을 표 위에
    글자로 적는다 — 적지 않으면 검토자가 「이 용량으로 돌렸다」로 읽는다
    (`core/report/ess_sizing_section.py` 머리말 ★★★ 이 같은 판단을 적었다).
    """
    return [
        "",
        "**적정 용량 검토 — 이 용량이 적정한가 · 얼마면 되는가** (사용자 요구 4)",
        "",
        "⚠ **진단이지 결론이 아니다.** 아래 셋은 이 실행의 자원 구성을 바꾸지 "
        "않는다 — 역산 결과를 실행에 되먹이지 않으므로 8단계 지표는 이 수에 "
        "움직이지 않는다. 위 ⓐ·ⓑ 가 이 실행이 **실제로 세운** 자원이다.",
        "",
        "① 설계 변수를 탐색 구간에서 훑은 결과 — 1변수 스윕(나머지는 기준값 고정):",
        "",
        *_capacity_table(report.capacity_review),
        "",
        "② 경우 「가」 — 100% 자립에 필요한 태양광 용량 **역산**:",
        "",
        *_self_sufficiency_table(report.self_sufficiency),
        "",
        "③ 경우 「ESS」 — 하루 결손을 감당하는 저장장치 용량 **역산**(계절별):",
        "",
        *_ess_sizing_table(report.ess_sizing),
        "",
        "- 점별 결론 축과 걸린 제약은 심의용 리포트 붙임 10 이 싣는다 — 이 표는 "
        "그 요약이며, 두 문서가 같은 `CaseReport` 를 읽는다",
    ]


# ── 3단계 — 자원 표와 계절별 운전 (사용자 요구 3·5·6) ───────────────────────

# ⚠ 운전 방법 없는 자원의 칸 문면과 그 판정은 **여기 있었다가 옮겨졌다**(R64) —
# 정본은 `core/report/dispatch_notes.py` 의 `NO_OPERATING_MODE` ·
# `resolved_operating_mode()` 다. 붙임의 「자원별 배정」 표가 **같은 판정**을
# 필요로 했고, 문면을 두 곳에 두면 **한쪽만 고쳐진다** — 이 저장소가 형상·
# 기준선·REC·가구 수에서 이미 네 번 밟은 형태다.


def dispatch_note_rows(report: CaseReport) -> list[str]:
    """3단계 ⓐ 자원 표의 **데이터 행** — 운전방식 칸이 배분까지 싣는다 (요구 5).

    `DispatchNote.operating_mode` 는 자원이 **선언한** 짧은 라벨이고(「전량
    판매」), 이 실행이 실제로 무엇을 우선했는지는 `CaseBasis.resources` 의 긴
    문면에만 있다 — 「전량 판매 (선언) · **본 실행 배분: 집 우선**」·「자가소비
    우선 · **방전 배분: 부하 추종 (방전창 …)**」(`e2e_runner.py` 가 짓는다).
    짧은 라벨만 실으면 ① 요구 5(ESS 가 가구 부하를 보고 방전한다)를 이 문서
    어디에서도 가릴 수 없고 ② 3단계 「전량 판매」와 2단계 「자가소비율 56%」가
    초독자에게 **모순으로 읽힌다**(R64/WP-FIX 결함 2).

    ⚠ **이름으로 맞춘다 — 차례로 맞추지 않는다**(두 목록의 길이가 다르다).
    못 찾으면 **종전 값**으로 떨어지고, 그마저 비면 위 상수가 문장을 적는다.
    """
    modes = {line.name: line.operating_mode for line in report.basis.resources}
    return [
        f"| {n.resource_name} | {resolved_operating_mode(n, modes)} "
        f"| `{n.dispatch_rule.value}` | {n.dispatch_priority} "
        f"| {'예' if n.price_linked else '아니오'} |"
        for n in report.dispatch_notes
    ]


def _moved_cell(season: SeasonRun) -> str:
    """옮긴 몫 칸 — **`0` 을 빈칸으로 두지 않는다.**

    그 계절 하루에 태양광 잉여가 하루 종일 없으면 옮길 자리가 없어 0 이 되고,
    그것은 「옮기지 않기로 했다」와 다른 진술이다
    (`core/casegrid/load_shift.py::DR_SHIFT_NOTHING_MOVED`).
    """
    if season.load_shift_annual_kwh <= 0.0:
        return DR_SHIFT_NOTHING_MOVED
    return f"{_num(season.load_shift_annual_kwh)}kWh"


def _resource_names(seasons: tuple[SeasonRun, ...]) -> list[str]:
    """자원 열 이름 — **첫 계절에 나온 차례** 그대로 모은다.

    ⚠ 손으로 적지 않는다 — 적으면 자원이 늘어도 표가 영영 옛 둘만 그린다
    (`app/services/verify_steps.py::net_demand_rows` 가 같은 판단을 적었다).
    """
    names: list[str] = []
    for season in seasons:
        for name in season.per_resource_annual_kwh:
            if name not in names:
                names.append(name)
    return names


def season_lines(report: CaseReport) -> list[str]:
    """3단계 ⓑ 뒤 — **계절마다 «따로» 돌린 결과** (사용자 요구 3·6).

    ## ⚠ 위 대표일 표를 «대신하지» 않는다

    대표일 하루는 R64/WP-4 뒤로 **연간등가 하루**이며 계절별 하루를 계절
    일수로 가중 평균한 것이다(`CaseReport.dispatch_hours` 주석). 계절 간 차이는
    그 하루에서 되돌릴 수 없으므로 **뒤에 잇는다** — 앞의 표를 이것으로 바꾸면
    결론(프로포마)이 선 하루가 보고서에서 사라진다.
    """
    seasons = report.seasons
    head = [
        "",
        "**계절별 운전 — 계절마다 따로 돌린 결과** (사용자 요구 3·6)",
        "",
        "⚠ 위 대표일은 **연간등가 하루**다 — 계절별 하루를 계절 일수로 가중 "
        "평균한 것이라 계절 간 차이를 거기서 되돌릴 수 없다. 아래가 그 차이이며, "
        "결론(7·8단계)은 이 계절들을 계절일수로 가중 합산한 것 위에 선다.",
        "",
    ]
    if not seasons:
        return [
            *head,
            "- 계절이 서지 않았다 — 형상 자산 없이 도는 실행이라 대표일 한 벌뿐이다. "
            "그때 「계절마다 다른 하루」라는 개념 자체가 성립하지 않는다",
        ]
    names = _resource_names(seasons)
    lines = [
        *head,
        "| 계절 | 일수 | 그 계절의 연간 계통 송전 | 연간 계통 수전 "
        "| 하루 안에서 옮긴 가전 부하(연간) |",
        "|---|---|---|---|---|",
        *(
            f"| {s.name} | {s.days}일 | {_num(s.grid_export_annual_kwh)}kWh "
            f"| {_num(s.grid_import_annual_kwh)}kWh | {_moved_cell(s)} |"
            for s in seasons
        ),
        f"| **합** | **{sum(s.days for s in seasons)}일** "
        f"| **{_num(sum(s.grid_export_annual_kwh for s in seasons))}kWh** "
        f"| **{_num(sum(s.grid_import_annual_kwh for s in seasons))}kWh** "
        f"| **{_num(sum(s.load_shift_annual_kwh for s in seasons))}kWh** |",
        "",
        "자원별 — 그 계절이 한 해에 보태는 몫(kWh):",
        "",
        "| 계절 | " + " | ".join(names) + " |",
        "|---|" + "---|" * len(names),
        *(
            f"| {s.name} | "
            + " | ".join(
                _num(s.per_resource_annual_kwh[name])
                if name in s.per_resource_annual_kwh
                else NO_VALUE
                for name in names
            )
            + " |"
            for s in seasons
        ),
        "",
        "- 부호 규약 — **양수는 내보냄 · 음수는 받아들임**이다(부하는 음수로 "
        "나타난다)",
        "- ⚠ **위 대표일 표와 단위가 다르다** — 저것은 하루의 합(kWh/일)이고 "
        "이것은 한 해의 합(kWh/년)이다. 연간등가 하루가 계절별 하루를 계절 "
        "일수로 가중 평균한 것이므로 **대표일 합 × 365 와 이 표의 합이 같은 "  # noqa: RUF001
        "수여야 한다**",
        "- 계절 일수의 합은 형상 자산이 선언한 달력이 정하며, 여기서 다시 "
        "세지 않는다",
    ]
    shares = report.appliance_loads.season_shares
    if shares is None:
        lines.append(
            "- 이 실행은 냉난방 계절 몫을 적지 않았다 — 냉난방 부하가 **기본 "
            "부하와 같은 계절 몫**으로 갈렸다(1단계 표). 몫을 적으면 계절마다 "
            "부하가 실제로 갈리며 연간 총량은 변하지 않는다"
        )
    else:
        lines.append(
            "- 이 실행은 냉난방 계절 몫을 적었다 — 냉난방 부하가 **기본 부하와 "
            f"다른 계절 몫**으로 갈렸다: {_season_share_cell(shares)}(1단계 표). "
            "연간 총량은 그대로이고 계절 사이에서 옮겨 갔을 뿐이다"
        )
    return lines


# ── 맨 끝 — 미반영 항목 ─────────────────────────────────────────────────────


def unreflected_lines(report: CaseReport) -> list[str]:
    """9단계 뒤 — **이 실행이 세지 않은 것**.

    ## 왜 `unreflected_section()` 을 그대로 부르지 않는가

    그 함수는 `## 붙임 8. 미반영 항목` 이라는 **머리글을 지어 낸다.** 이
    보고서에는 붙임이 없으므로 그 머리글은 여기서 거짓 좌표가 되고, 더욱이
    `##` 머리글을 늘리면 화면이 단계를 세는 정규식 근처에 새 머리글이 선다.
    ⇒ 같은 항목(`build_unreflected`)을 읽되 **머리글만 이 문서의 것**으로 짓는다.

    ⚠ 항목 자체는 **한 자리에서만** 판정된다 — `core/report/unreflected.py` 다.
    여기서 「무엇이 미반영인가」를 다시 고르면 심의용 리포트와 이 보고서가
    서로 다른 건수를 인쇄한다.
    """
    items = build_unreflected(report)
    lines = [
        "### 미반영 항목 — 이 실행이 세지 않은 것",
        "",
        "⚠ 위 아홉 단계의 **어느 수에도 들어 있지 않은** 항목이다. 「영향이 "
        "없다」가 아니라 「이 실행이 재지 않았다」이며, 방향이 갈린다는 사실 "
        "자체가 검토에 필요한 정보다.",
        "",
        f"- 요약 — {unreflected_direction_tally(items)}",
        "- 위 요약이 가리키는 「붙임 8」은 **심의용 리포트**의 같은 표다 — 이 "
        "보고서에서는 바로 아래 표이며, 둘은 같은 판정을 읽는다",
        "",
    ]
    if not items:
        return [*lines, "- 미반영으로 판정된 항목 — 없음", ""]
    lines += [
        "| 항목 | 방향 | 크기 | 비어 있는 자리 | 해소 조건 | 판정 |",
        "|---|---|---|---|---|---|",
        *(
            f"| {item.label} | {item.direction} | {item.magnitude} "
            f"| {item.reason} | {item.resolves_when} | {item.judged} |"
            for item in items
        ),
        "",
        "- 크기가 「미정량」인 항목은 **작다는 뜻이 아니다** — 재지 못했다는 뜻이다",
        "",
    ]
    return lines
