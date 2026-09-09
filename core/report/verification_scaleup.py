"""검증 2단계 ⓐ — **1가구가 단지로 커지는 규칙**을 한 표에 세운다
(R68/WP-4 · 검토서 §3.5).

## 무엇이 없었나

2단계는 자원의 **단지 값**(태양광 60 kW · 저장장치 200 kWh / 100 kW)만 싣고,
1단계는 부하의 확대(`단지 총 전력 = 가구 총 전력 × 단지 가구 수`)만 싣는다.
그래서 검토서 §3.5 가 여섯을 물었다:

    부하는 단순히 20배 하는가 · PV·ESS 용량도 20배 하는가 ·
    동시율은 어느 부하 또는 어느 설비에 적용하는가 ·
    가구별 ESS 를 합산하는가, 공용 ESS 하나로 구성하는가 ·
    ESS 출력은 용량과 같은 비율로 확대하는가 ·
    20가구에서 공통 수전 피크가 어떻게 변하는가

★ **여섯의 답은 전부 이미 코드에 있다.** 이 모듈은 **새로 정하지 않고 인쇄**
한다 — 어느 수도 여기서 짓지 않고 `CaseReport` 에서 읽는다.

## ★★★ 이 표의 축은 「20배인가 아닌가」가 **아니다**

부하·태양광 용량·저장장치 용량·저장장치 정격출력은 **넷 다 같은 배수**를 탄다
(`core/casegrid/household_scale.py::household_scale` 이 그 배수의 판정 자리
하나다). 갈리는 것은 배수가 아니라 **곱하는 자리**이며, 그 자리가 셋으로
흩어져 있다:

    가구 부하        `core/casegrid/seasonal_dispatch.py::_load_total_kwh`
    태양광·저장장치 용량   `core/casegrid/e2e_runner.py::run_single_case_e2e`
                     (설계 변수라 `_resolve` 직후에 곱한다)
    저장장치 정격출력  `core/casegrid/ess_build.py::_case_ess_spec`
                     (설계 변수가 아니라 그 모듈의 상수라 통로가 다르다)

⇒ 그래서 표의 열이 **「무엇 · 한 호 기준값 · 배수를 곱하는 자리 · 단지 값」**
이다. 「20배인가」로 묻는 표는 넷째 열만 답하고 **어디서 곱하는지를 잃는다.**

## ⚠⚠ 셋이 같은 배수를 타야 하는 이유 — 실측이 있다

R65/WP-2b 가 **용량 둘만** 곱했을 때 20호 실행이 `ess.power_kw` 로 **거부**됐다
(용량이 20배인데 정격출력이 한 호분이면 하루 방전량을 부하 시각에 실을 수
없다). 하나만 배수를 안 타면 **같은 실행 안에서 설비가 서로 다른 규모의 사업을
그린다** — 검토서 §3.5 의 다섯째 물음이 정확히 그것을 묻는다.

## ⚠⚠ 함께 인쇄하는 것 — **곱하지 «않는» 둘**

- **설비 단가**(원/kW · 원/kWh)는 곱하지 않는다. 총액은 자원 안에서
  `용량 × 단가` 로 나오므로 여기서 함께 곱하면 **두 번 곱해진다**
  (`core/casegrid/e2e_runner.py::run_single_case_e2e` 의 ⚠ 주석이 정본이다).
- **동시율**은 배수를 타는 값이 아니라 **걸리는 자리가 하나인** 값이다 —
  `core/casegrid/e2e_runner.py::_site_load_kw` 가 단지의 **시각별 최대수요(kW)**
  에 걸어 `core/der/ess.py::ESS.reducible_peak_kw` 로 보낸다.

## ⚠⚠⚠ 동시율을 안 건 자리를 **「누락」으로 인쇄하지 않는다**

`_site_load_kw` 독스트링이 그것을 못 박았다 — *「곱하지 않은 것이 「빠뜨린
것」이 아니다. 위 셋은 판정이 명시로 제외한 자리이며, 다음 사람이 「일관성」을
이유로 넣으면 그 순간 결론축이 조용히 좋아진다」*. 판정의 정본은
`docs/decisions-2026-09-07-R66.md` §3 이다. ⇒ 그 셋을 **「제외 — 판정이 정한
것」**으로 적는다(아래 `COINCIDENCE_EXCLUDED`).

## 왜 `verification_inputs.py` 가 아니라 새 모듈인가

`scripts/check_file_size.py --code-strict` 가 코드 500줄에서 CI 를 차단하는데
(NFR-206) `core/report/verification_inputs.py` 는 착수 시점에 코드 **477줄**
이었다 — 남은 자리가 스물셋이다. 상한을 올리는 것은 spec 개정이므로(§16.5)
새 코드는 여기 쌓는다. 앞선 R68/WP-2 가 같은 사유로
`core/report/verification_dispatch.py` 를 세웠고 이 모듈이 그 관용구를 따른다.

⇒ 그러면서 **일반용 전력의 대장 열쇠와 그 값을 읽는 함수도 여기로 옮겼다** —
가구 한 호의 총부하(`household_total_load_kwh`)를 이 표와 1단계 표가 **함께**
쓰기 때문이다. 두 곳에서 각자 더하면 한쪽만 고쳐지고, 그때 같은 문서가 가구
총 전력을 두 수로 말한다. 이름은 그대로이고 `verification_inputs.py` 가
재수출한다.

## ⛔ 새로 계산하지 않는다

`verification.py`·`verification_inputs.py` 머리말의 규약 그대로다. 단지 값은
`CaseReport.capacity_review`(설계 변수의 사용값) · `CaseReport.ess_sizing.
run_power_kw`(정격출력) · `CaseReport.appliance_loads`(부하)가 갖고, 동시율은
`CaseReport.assumptions` 의 대장 행이 갖는다. **한 호 기준값 열만 나눗셈**이며
그 나눗셈의 성질을 표가 스스로 적는다(`core/report/ess_sizing_section.py::
per_household_scaled` 가 같은 판단을 적어 둔 자리다).
"""
from __future__ import annotations

from core.casegrid.appliance_load import APPLIANCE_LOAD_UNIT
from core.casegrid.household_scale import (
    HOUSEHOLD_COUNT_LEDGER_KEY,
    HOUSEHOLD_COUNT_UNSPECIFIED,
)
from core.report.case_report import AssumptionRow, CaseReport
from core.report.ess_sizing_section import per_household_scaled

#: 일반용 전력의 **대장 자리** — 가구가 기본으로 쓰는 전기, 추가 전력사용기기
#: 이전의 기본 소비(대장 제목 «가구당 연간 전력사용량»).
#:
#: ⚠ R68/WP-4 가 `core/report/verification_inputs.py` 에서 **옮겨 왔다** — 아래
#: `household_total_load_kwh` 를 이 모듈의 표와 1단계 표가 함께 쓰기 때문이다.
#: 그 파일이 같은 이름으로 재수출하므로 이 열쇠를 가리키는 문면과 시험은
#: 그대로 참이다. ⚠ 값은 대장이 갖는다 — 이 모듈이 수를 세우는 것이 아니다.
HOUSEHOLD_LOAD_LEDGER_KEY = "load.household.annual"

#: 단지 설비 **동시율**의 대장 자리 (`R66` · 사용자 지시 2026-09-07).
#:
#: ⚠ 정본 상수가 아직 `core/casegrid/` 에 없어 여기서 정의한다 —
#: `core/casegrid/ledger_levels.py` 는 이 열쇠를 `_LEDGER_VARS` 의 한 줄로만
#: 갖는다(위 `HOUSEHOLD_LOAD_LEDGER_KEY` 와 같은 형태다).
#: ⚠⚠ **사용자가 이 값을 바꾸는 통로가 어디인가**가 검토서 §4.5 가 묻는 것이라
#: 표가 이 열쇠를 **글자로** 싣는다 — 값만 적으면 바꿀 자리가 산출물에 없다.
COINCIDENCE_FACTOR_LEDGER_KEY = "design.coincidence_factor"

#: 단지 총부하의 단위 — **`kWh/호·년` 이 아니다.** 가구 수를 곱하는 순간
#: «호당» 이 아니므로 단위가 갈린다(`verification_inputs.py` 의 단지 총 전력
#: 칸이 같은 상수를 쓴다 — 두 곳에 적으면 한쪽만 고쳐진다).
#:
#: ★★ **`kWh/년` 에서 옮겼다** (R68/WP-8 · 판정 `.orch/R68/JUDGMENT-wp7.md` ⓔ-1).
#: 같은 표에 `kWh/호·년` 이 나란히 서는데 맨 `kWh/년` 은 **호당인지 단지인지
#: 구별되지 않고**, 검토서 §4.2 가 겨냥한 것이 정확히 그 애매함이다.
#: ⚠ **분모가 바뀐 것이 아니라 이름이 바뀐 것**이다 — 값도 곱도 그대로다.
ESTATE_LOAD_UNIT = "kWh/단지·년"

#: 배수를 **곱하지 않는** 칸의 문면. 「없다」·빈칸으로 두지 않는다 — 빈칸은
#: 「곱한다」와 산출물에서 구별되지 않는다(`core/report/_format.py::NO_VALUE`
#: 가 같은 사유를 적는다).
NOT_MULTIPLIED = "⛔ 곱하지 않는다"

#: 단지 값이 한 호 값과 **같은** 칸의 문면 — 단가처럼 규모와 무관한 값이다.
SAME_AS_HOUSEHOLD = "같다"

#: ★★★ **바꾸는 통로가 «없는» 설비 축 둘을 신고하는 줄** (R68/WP-8 · 판정
#: `.orch/R68/JUDGMENT-wp7.md`).
#:
#: 검토서 §4.5 는 *「… **ESS 용량·출력** … 을 하나씩 바꿨을 때 … 움직이는지
#: 테스트해야 한다」* 를 요구하는데, 실물은 저장장치 정격출력이
#: `core/casegrid/ess_build.py::ESS_POWER_KW` **모듈 상수**이고 용량은 소스의
#: 설계 변수다 — **대장 키도 시나리오 필드도 아니다.**
#:
#: ⚠⚠ **「미반영 항목」 표는 이 둘을 못 센다.** 그 표는 *대장 스윕 축인데 안
#: 읽히는 것*만 세고(`core/report/unreflected.py::_unread_items`), 이 둘은 대장에
#: 아예 없어서 그 판정에 들지 않는다. ⇒ **그래서 이 줄이 필요하다** — 없으면
#: 산출물이 *「모든 수치는 변경 가능」* 을 말없이 참으로 만든다.
#:
#: ⚠ **「빠뜨렸다」가 아니다.** `ESS_POWER_KW` 옆 주석이 *「용량과 달리 설계
#: 변수로 올리지 않았다」* 로 사유까지 적어 두었다 — 정한 것이다. 뒤집을지는
#: 사업 계획이 정하는 사실에 가깝고(가구 수·전기차 대수와 같은 부류다) 사람
#: 판단 자리로 올라가 있다.
NO_CHANGE_PATH_NOTE = (
    "- ⚠⚠ **저장장치 용량·정격출력은 이 실행에서 «바꾸는 통로가 없다»** — "
    "대장 키도 시나리오 필드도 아니고, 용량은 소스의 설계 변수이며 정격출력은 "
    "`core/casegrid/ess_build.py::ESS_POWER_KW` 모듈 상수다. "
    "「미반영 항목」 표는 **대장 항목만** 세므로 이 둘을 신고하지 못한다 — "
    "그래서 여기 적는다. ⚠ **빠뜨린 것이 아니라 정한 것**이며(그 상수 옆 주석이 "
    "사유를 진다), 통로를 세울 것인가는 사람 판단 자리다"
)

#: 표 제목. ⚠ 「전제」를 쓰지 않는다 — 사람이 읽는 자리의 그 낱말은 0건이
#: 규약이다(판정 R63b §1).
SCALEUP_TITLE = "1가구 → 단지 확대 규칙 — 같은 배수를 «어디서» 곱하는가"

#: 동시율을 **걸지 않는** 자리 셋과 그 사유. 판정
#: (`docs/decisions-2026-09-07-R66.md` §3)이 **명시로 제외**한 자리이며
#: `core/casegrid/e2e_runner.py::_site_load_kw` 독스트링의 ⛔ 셋과 짝이다.
#:
#: ⚠⚠ **「누락」이 아니다.** 이것을 빠뜨린 것으로 적으면 다음 사람이 넣고, 그
#: 순간 결론축이 **좋아지는 쪽으로** 조용히 틀린다(모듈 머리말 ⚠⚠⚠).
COINCIDENCE_EXCLUDED: tuple[tuple[str, str], ...] = (
    (
        "연간 부하 kWh 총량",
        "스무 집이 1년에 쓰는 전기의 **합**은 동시성과 무관하다 — 곱하면 "
        "**부하를 20% 지우는 것**이고, 쓰지 않은 전기를 안 쓴 것으로 만든다",
    ),
    (
        "부하 추종 방전의 `load_profile_kwh`",
        "그것은 kW 가 아니라 **에너지**다 — 곱하면 같은 부하가 계산 안에서 두 "
        "크기를 갖고(방전량은 줄고 수전량은 안 줄어) 잔차가 어디로도 가지 않는다",
    ),
    (
        "태양광 용량 역산",
        "연간 총량 ÷ (8,760 × 이용률) 의 역산이라 **동시성이 들어올 자리가 "  # noqa: RUF001
        "없다** — 총량 기준이다",
    ),
)

#: 제외 칸의 판정 문면 — 한 자리에서만 정한다.
EXCLUDED_BY_DECISION = "제외 — 판정이 정한 것"


def _ledger_row(report: CaseReport, key: str) -> AssumptionRow | None:
    """이 실행이 **실제로 읽은** 대장 행 하나 — 없으면 `None`(미지정).

    `report.assumptions` 의 행은 실행이 쓴 값을 싣는다(R48-E1 ·
    `core/report/case_report.py` 의 부록 조립) — 그대로 읽으면 다른 표의
    「이 실행의 값」 칸과 어긋나지 않는다. ⚠ 여기서 기본값으로 메우지 않는다.
    """
    for row in report.assumptions:
        if row.key == key:
            return row
    return None


def household_base_kwh(report: CaseReport) -> float | None:
    """일반용 전력 — 이 실행이 읽은 대장 값, 행이 없으면 `None`(미지정).

    ## 왜 대장 행에서 읽나

    일반용은 히트펌프·전기차와 달리 **실행 입력의 칸이 없다** — 값은 대장
    `load.household.annual` 이 갖고, 바꾸는 통로는 오버라이드(시나리오 yaml 의
    `assumption_overrides` · 설정 화면의 대장 항목 칸)다.

    ⚠ 여기서 판정을 새로 세우지 않는다 — 러너가 이미 같은 대장 축으로 돌았고
    (`core/report/case_report.py` 의 `household_load_annual_kwh`), 이 함수는 그
    사실을 인쇄할 뿐이다. 행이 없으면 `None` 이고 칸은 문장이 된다.

    ⚠ R68/WP-4 가 `core/report/verification_inputs.py` 에서 옮겨 왔다(모듈
    머리말 ⇒ 절). **이름과 반환값은 한 글자도 바뀌지 않았다.**
    """
    row = _ledger_row(report, HOUSEHOLD_LOAD_LEDGER_KEY)
    return None if row is None else float(row.value)


def household_total_load_kwh(report: CaseReport) -> float:
    """가구 **한 호**의 총 전력 (kWh/호·년) = 일반용 + 히트펌프 + 전기차.

    ⚠⚠ **더한 뒤에 곱한다.** 곱한 뒤에 더하면 추가 기기가 단지에 딱 한 대
    있는 사업이 된다 — 러너도 같은 순서다
    (`core/casegrid/seasonal_dispatch.py::_load_total_kwh`).

    ⚠ 미지정 항목은 **0으로 더한다** — 그 사실은 값이 아니라 **글자로** 남는다
    (`core/casegrid/appliance_load.py::APPLIANCE_LOAD_UNSPECIFIED` 를 칸에
    싣는 자리가 1단계 표다). 여기서 미지정을 숨기지도, 지어내지도 않는다.

    ⚠ **두 표가 이 함수를 함께 부른다** — 1단계의 「가구 총 전력」 칸과 2단계의
    확대 규칙 표다. 각자 더하면 한쪽만 고쳐지고, 그때 같은 문서가 가구 총
    전력을 두 수로 말한다.
    """
    return (household_base_kwh(report) or 0.0) + report.appliance_loads.total_kwh


def estate_load_kwh(report: CaseReport) -> float | None:
    """단지 총부하 (`ESTATE_LOAD_UNIT`) — 가구 수가 **미지정이면 `None`**.

    미지정에 곱할 수를 지으면 *「모든 가구가 같다」* 는 뜻이 되고, 이 보고서의
    모든 수량이 한 호의 것이라는 사실이 그 칸에서 사라진다.
    """
    count = report.household_count
    return None if count is None else household_total_load_kwh(report) * count


def _estate_column_head(count: int | None) -> str:
    """넷째 열의 이름 — 가구 수를 **리터럴로 적지 않는다**(NFR-202)."""
    return f"{count}호 값" if count is not None else "단지 값"


def _load_row(report: CaseReport) -> str:
    """부하 행 — 한 호의 총 전력과 단지 총부하, 그리고 곱하는 자리."""
    estate = estate_load_kwh(report)
    estate_cell = (
        HOUSEHOLD_COUNT_UNSPECIFIED
        if estate is None
        else f"{estate:,.0f} {ESTATE_LOAD_UNIT}"
    )
    return (
        f"| 가구 부하(연간) | {household_total_load_kwh(report):,.0f} "
        f"{APPLIANCE_LOAD_UNIT} "
        "| `core/casegrid/seasonal_dispatch.py::_load_total_kwh` — 더한 뒤에 "
        f"곱한다 | {estate_cell} |"
    )


def _design_rows(report: CaseReport) -> list[str]:
    """설계 변수 행들 — 태양광 용량·저장장치 용량. **수는 실행에서 읽는다.**

    ⚠ 정본은 `report.capacity_review` 의 `used_value` 다 —
    `core/report/verification_inputs.py::run_used_values` 가 같은 필드에서
    「실행 용량」 문면을 짓는다. 여기서 다시 세우지 않는다.
    """
    count = report.household_count
    return [
        f"| {finding.label} "
        f"| {per_household_scaled(finding.used_value, count):g} {finding.unit} "
        "| `core/casegrid/e2e_runner.py::run_single_case_e2e` — 설계 변수라 "
        f"`_resolve` 직후에 곱한다 | {finding.used_value:g} {finding.unit} |"
        for finding in report.capacity_review
    ]


def _ess_power_row(report: CaseReport) -> list[str]:
    """저장장치 **정격출력** 행 — 곱하는 자리가 위 둘과 다르다 (R65/WP-2c).

    설계 변수가 아니라 `core/casegrid/ess_build.py::ESS_POWER_KW`(한 호분)
    모듈 상수이므로 `_resolve` 를 지나지 않고, 같은 배수를
    `core/casegrid/ess_build.py::_case_ess_spec` 이 그 상수에 곱한다.

    ⚠ 실행이 저장장치를 세우지 않았으면(`run_power_kw` 가 `None`) **행을 짓지
    않는다** — 없는 설비의 확대 규칙을 인쇄하면 그 설비가 있다는 뜻이 된다.
    """
    power_kw = report.ess_sizing.run_power_kw
    if power_kw is None:
        return []
    count = report.household_count
    return [
        "| 저장장치 정격출력 "
        f"| {per_household_scaled(power_kw, count):g} kW "
        "| `core/casegrid/ess_build.py::_case_ess_spec` — 설계 변수가 아니라 "
        f"그 모듈의 상수라 통로가 다르다 | {power_kw:g} kW |"
    ]


def _unit_cost_rows(report: CaseReport) -> list[str]:
    """단가 행들 — **곱하지 않는다.** 문면은 자원이 든 것을 그대로 싣는다.

    ⚠ 총액은 자원 안에서 `용량 × 단가` 로 나온다 — 여기서 함께 곱하면 두 번
    곱해진다(`core/casegrid/e2e_runner.py::run_single_case_e2e` 의 ⚠ 주석).
    """
    return [
        f"| {line.kind} 단가 | {line.unit_capex} "
        f"| {NOT_MULTIPLIED} — 원/kW · 원/kWh 이므로 규모와 무관하다 "
        f"| {SAME_AS_HOUSEHOLD} |"
        for line in report.basis.resources
    ]


def _coincidence_row(report: CaseReport) -> list[str]:
    """동시율 행 — **배수를 타는 값이 아니라 걸리는 자리가 하나인 값**이다.

    ⚠ 대장 행이 없으면 행을 짓지 않는다 — 이 실행이 그 값을 읽지 않았다는
    뜻이고, 읽지 않은 값의 적용 자리를 인쇄하면 걸렸다는 뜻이 된다.
    """
    row = _ledger_row(report, COINCIDENCE_FACTOR_LEDGER_KEY)
    if row is None:
        return []
    return [
        f"| 설비 동시율 (`{COINCIDENCE_FACTOR_LEDGER_KEY}`) "
        f"| {float(row.value):,.1f} {row.value_unit} "
        "| `core/casegrid/e2e_runner.py::_site_load_kw` — 단지의 **시각별 "
        "최대수요(kW)** 에만 걸린다 "
        f"| {SAME_AS_HOUSEHOLD} — {NOT_MULTIPLIED} |"
    ]


def _scale_notes(report: CaseReport) -> list[str]:
    """표 아래 줄들 — **표가 스스로 말해야 하는 것**만 적는다.

    답하는 것은 검토서 §3.5 의 여섯 중 표의 칸으로 답이 되지 않는 셋이다:
    ⓐ 한 호 기준값 열이 무엇인가(나눈 값인가 원값인가) ⓑ 저장장치가 가구별
    합산인가 공용 하나인가 ⓒ 공통 수전 피크가 어떻게 정해지는가.
    """
    count = report.household_count
    if count is None:
        scale_note = (
            f"- 단지 규모 — **{HOUSEHOLD_COUNT_UNSPECIFIED}**. 배수가 **1** 이라 "
            "두 열이 같은 수이며, 이 보고서의 모든 수량과 금액이 **가구 한 호의 "
            f"것**이다(통로는 시나리오 yaml 과 대장 `{HOUSEHOLD_COUNT_LEDGER_KEY}` 다)"
        )
    else:
        scale_note = (
            f"- 단지 규모 — **{count}호**이고 위 넷은 **같은 배수**를 탄다. 그 "
            "배수를 판정하는 자리는 "
            "`core/casegrid/household_scale.py::household_scale` 하나다"
        )
    return [
        scale_note,
        "- **한 호 기준값 열의 성질이 행마다 다르다** — 부하는 곱하기 «전»의 "
        "원값(1단계의 「가구 총 전력」과 같은 수)이고, 설비 셋은 **단지 값을 "
        "가구 수로 나눈** 수다. 설비의 한 호 값을 갖고 있는 자리는 "
        "`core/casegrid/ledger_levels.py` 의 설계 변수 기준값과 "
        "`core/casegrid/ess_build.py::ESS_POWER_KW` 이며, 배수가 정수라 그 "
        "나눗셈은 곱하기 전 값으로 정확히 돌아온다",
        "- **저장장치는 가구별 저장장치의 «합산»이다** — 모형에는 저장장치 자원이 "
        "하나 서지만 그 용량과 출력이 「한 호분 × 가구 수」이며, 별도로 설계한 "  # noqa: RUF001
        "공용 설비가 아니다. 가구마다 나눠 놓을 것인가는 이 모형이 답하지 않는다",
        "- ⚠ **설비 셋이 같은 배수를 타야 한다** — 하나만 안 타면 같은 실행 안에서 "
        "설비가 서로 다른 규모의 사업을 그린다. 실측으로 그랬다: 용량 둘만 곱했을 "
        "때 20호 실행이 `ess.power_kw` 로 **거부**됐다(R65/WP-2b·2c — 용량이 "
        "20배인데 정격출력이 한 호분이면 하루 방전량을 부하 시각에 실을 수 없다)",
        "- **공통 수전 피크** — 가구 부하 시계열 × 가구 수 × 동시율 로 정해지고, "  # noqa: RUF001
        "그 수가 가는 곳은 `core/der/ess.py::ESS.reducible_peak_kw`(첨두 저감이 "
        "깎을 수 있는 최대 kW)다. 3단계 운전이 그 결과를 싣는다",
        f"- 동시율을 **바꾸는 통로** — 대장 `{COINCIDENCE_FACTOR_LEDGER_KEY}` 이며, "
        "시나리오 yaml 의 `assumption_overrides` · 설정 화면의 대장 항목 칸이 그 "
        "자리다(검토서 §4.5)",
        # ★★★ **감시의 사각지대를 글자로 신고한다** (R68/WP-8 · 판정
        # `.orch/R68/JUDGMENT-wp7.md` 「WP-8 이 새로 올린 판정 요청」).
        # 「미반영 항목」 표는 이것을 **못 센다** — 그 표는 *대장 스윕 축인데 안
        # 읽히는 것*만 세고, 이 둘은 **대장에 없어서** 그 판정에 들지 않는다.
        # ⛔ 이 라운드가 통로를 세우지 않는다(대장에 올리면 `sensitivity` 삼수를
        # 지어야 하고 그 근거가 없다 — 지어 넣으면 대장이 「조사값」의 얼굴로
        # 가정을 싣는다). ⇒ **없다는 사실을 적는 것**이 검토서 §4.5 가 물은
        # *「정말 변경 가능한가」* 에 거짓 없이 답하는 길이다.
        NO_CHANGE_PATH_NOTE,
    ]


def _excluded_lines() -> list[str]:
    """동시율을 **걸지 않는** 자리 표 — 「제외」와 「누락」을 가른다."""
    return [
        "",
        "**동시율을 «걸지 않는» 자리 — 제외이며 누락이 아니다** "
        "(판정 `docs/decisions-2026-09-07-R66.md` §3)",
        "",
        "| 걸지 않는 자리 | 판정 | 왜 |",
        "|---|---|---|",
        *(
            f"| {where} | {EXCLUDED_BY_DECISION} | {why} |"
            for where, why in COINCIDENCE_EXCLUDED
        ),
        "",
        "- ⚠⚠ 위 셋을 **「빠뜨렸다」로 읽지 마라** — 판정이 **명시로 제외**한 "
        "자리다. 다음 사람이 「일관성」을 이유로 넣으면 그 순간 결론축이 "
        "**좋아지는 쪽으로** 조용히 틀린다",
    ]


def scaleup_lines(report: CaseReport) -> list[str]:
    """2단계 ⓐ 뒤 — **확대 규칙 표 + 그 아래 줄 + 제외 표** (검토서 §3.5).

    ## ⚠ 이 절은 자원 구성을 **바꾸지 않는다**

    위 ⓐ 표가 이 실행이 실제로 세운 자원이고, 이 절은 *「그 수가 한 호
    기준값에서 어떻게 나왔는가」* 만 인쇄한다. 산식도 적용 자리도 여기서
    갈지 않는다.

    ## ⚠ 단계를 늘리지 않는다

    `## N단계 — ` 로 시작하는 줄을 내지 않는다 —
    `app/services/verify_steps.py::split_stages` 가 그 머리글로 쪼개고
    `app/services/verify_steps.py::STAGE_COUNT` 는 9 그대로다.
    """
    return [
        "",
        f"**{SCALEUP_TITLE}** (검토서 §3.5)",
        "",
        "| 무엇 | 한 호 기준값 | 배수를 곱하는 자리 "
        f"| {_estate_column_head(report.household_count)} |",
        "|---|---|---|---|",
        _load_row(report),
        *_design_rows(report),
        *_ess_power_row(report),
        *_unit_cost_rows(report),
        *_coincidence_row(report),
        "",
        *_scale_notes(report),
        *_excluded_lines(),
    ]
