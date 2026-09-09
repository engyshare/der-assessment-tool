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
    EV_LOAD_LEDGER_KEY,
    EV_LOAD_TITLE,
    HEATPUMP_LOAD_FIELD,
    HEATPUMP_LOAD_LEDGER_KEY,
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
from core.report.capacity import (
    ECONOMIC_SENSITIVITY_TITLE,
    CapacityFinding,
    best_value_text,
    binding_constraint_text,
    search_range_note,
)
from core.report.case_report import CaseReport
from core.report.ess_sizing_section import (
    ADOPTED_HEAD,
    CAPACITY_KIND_APPLIED,
    CAPACITY_KIND_DIAGNOSTIC,
    PER_HOUSEHOLD_HEAD,
    SELF_SUFFICIENT_HEAD,
    ESSSizingReview,
    adopted_value_note,
    capacity_kind_lines,
    per_household_scaled,
    per_household_scaled_notes,
    relaxation_reach_note,
    within_range_head,
)
from core.report.sizing import (
    SelfSufficiencySizing,
    household_first_notes,
)
from core.report.unreflected import build_unreflected, unreflected_direction_tally
from core.report.verification_dispatch import resource_labels, season_step_tables

#: 「그렇다/아니다」 두 글자를 한 자리에서만 정한다 — 표마다 다른 낱말을 쓰면
#: 훑는 눈이 다른 판정으로 읽는다(`core/report/_format.py::_recovery` 와 같은
#: 사유다).
_YES = "예"
_NO = "아니오"

#: 일반용 전력의 **대장 자리** — 가구가 기본으로 쓰는 전기, 추가 전력사용기기
#: 이전의 기본 소비(대장 제목 «가구당 연간 전력사용량»). `HEATPUMP_LOAD_LEDGER_KEY`
#: · `EV_LOAD_LEDGER_KEY` 와 같은 규약의 열쇠인데 정본 상수가 아직
#: `core/casegrid/` 에 없어 여기서 정의한다 — 같은 형태의 전례가
#: `tests/report/test_shaped_run_invariants.py::_LOAD_LEDGER_KEY` 다.
#: ⚠ 값은 대장이 갖는다 — 이 모듈이 수를 세우는 것이 아니다.
HOUSEHOLD_LOAD_LEDGER_KEY = "load.household.annual"


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


def _household_base_kwh(report: CaseReport) -> float | None:
    """일반용 전력 — 이 실행이 읽은 대장 값, 행이 없으면 `None`(미지정).

    ## 왜 대장 행에서 읽나

    일반용은 히트펌프·전기차와 달리 **실행 입력의 칸이 없다** — 값은 대장
    `load.household.annual` 이 갖고, 바꾸는 통로는 오버라이드(시나리오 yaml 의
    `assumption_overrides` · 설정 화면의 대장 항목 칸)다. `report.assumptions`
    의 행은 **실행이 쓴 값**을 싣는(R48-E1 — `case_report.py::_appendix`) —
    그대로 읽으면 이 표의 「이 실행의 값」 칸과 어긋나지 않는다.

    ⚠ 여기서 판정을 새로 세우지 않는다 — 러너가 이미 같은 대장 축으로
    돌았고(`case_report.py` 의 `household_load_annual_kwh`), 이 함수는 그
    사실을 인쇄할 뿐이다. 행이 없으면 `None` 이고 칸은 문장이 된다(모듈 머리말 ★★).
    """
    for row in report.assumptions:
        if row.key == HOUSEHOLD_LOAD_LEDGER_KEY:
            return float(row.value)
    return None


def _stated_sum(number: str, missing: tuple[str, ...]) -> str:
    """합계 칸에 「미지정」 진술을 얹는다 — 미지정이 없으면 그대로 둔다.

    ⚠⚠ **미지정 항목이 끼면 확정값만으로 적지 않는다.** «9,673» 처럼 인쇄하면
    읽는 사람이 그 미지정 항목이 계산에서 빠졌다고 읽는다 — 빠지지 않았고
    **0으로 들어갔다**. 그 진술은 기존 상수 `APPLIANCE_LOAD_UNSPECIFIED` 의
    문면 그대로 얹는다(새 문면을 짓지 않는다), 항목 이름은 위 표의 행 이름과
    같은 낱말로 쓴다.
    """
    if not missing:
        return number
    return f"{number} ({' · '.join(missing)}: {APPLIANCE_LOAD_UNSPECIFIED})"


def _estate_total_cell(
    per_household_kwh: float, count: int | None, missing: tuple[str, ...]
) -> str:
    """단지 총 전력 칸 — 가구 수가 미지정이면 **곱하지 않고 진술을 적는다.**

    미지정에 곱할 수를 지으면 «모든 가구가 같다»는 뜻이 되고, 이 보고서의
    모든 수량이 한 호의 것이라는 사실이 그 칸에서 사라진다 — 그때 칸은
    `HOUSEHOLD_COUNT_UNSPECIFIED` 문면으로 채운다. 부하 쪽 미지정은 위
    `_stated_sum` 과 같은 괄호를 얹는다.

    ⚠ 단위가 위 칸들과 다르다 — `kWh/호·년` 이 아니라 **`kWh/년`**(단지의
    합계)이다. 가구 수를 곱하는 순간 «호당» 이 아니다.
    """
    if count is None:
        number: str = HOUSEHOLD_COUNT_UNSPECIFIED
    else:
        number = f"{per_household_kwh * count:,.0f} kWh/년"
    return _stated_sum(number, missing)


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

    이 표의 행들은 계산의 결과가 아니라 **이 실행이 받은 전제와 그 산수**다.
    대장 표(위 ⓑ)는 *「대장이 무엇을 갖고 있는가」*를 적고 이 표는 *「이 실행이
    무엇으로 돌았는가」*를 적는다 — **둘은 다른 진술이며 값이 같아도 그렇다.**

    ## ★★ R65 — 앞의 넷은 이제 대장·자산에서도 온다

    종전에는 앞의 넷이 대장에서 `track: blocked` · 값 없음이라 **애초에
    대장에서 올 수 없었다.** R65 가 그 셋에 값을 세웠다
    (`load.household.count` 20 · `load.heatpump.annual` **3,289.0**(R66/WP-5 가
    2,675 에서 갈았다 — 급탕이 섰다) · `load.ev.annual` 2,784)이고, 계절 몫은 형상 자산의
    `appliance_season_shares:` 절이 갖는다. ⇒ **통로가 둘 이상이 되었고
    실행 입력이 이긴다** — 시나리오·화면이 적으면 그것이, 적지 않으면
    대장·자산이 답한다(`core/casegrid/appliance_load.py::
    with_ledger_defaults` · `household_scale.py::ledger_household_count`).

    ⇒ 그러므로 이 표가 여전히 필요하다. **어느 쪽이 이겼는지**는 산출물이
    말해 주지 않으면 알 수 없고, 「대장에 20이 있다」와 「이 실행이 20으로
    돌았다」는 다른 진술이다.

    ## ⚠ 화면과 시나리오의 통로가 항목마다 다르다

    가구 수·히트펌프·전기차는 화면(`/ui/run`)에도 칸이 있고, **계절 몫은
    시나리오 yaml 에만 있다.** 일반용 전력은 둘 다 아니다 — 대장 항목이라
    오버라이드로만 바꾼다(위 `_household_base_kwh`). 「시나리오에서도 못
    바꾼다」로 적으면 거짓이므로 통로 칸이 그 차이를 그대로 나른다.

    ## ★★ 할인율이 **여기** 있는 이유 (R64/WP-FIX 결함 1)

    8단계 ⓐ 가 *「1단계 할인율」* 을 가리키는데 1단계에 그 행이 없었다 —
    할인율은 대장 항목이 **아니다**(`docs/assumptions.yaml` 에 0건 ·
    `core/casegrid/ledger_levels.py`: *「평가자가 고르는 모형 파라미터」*). 곧
    이 표의 정의에 드는 값이므로 **참조를 지우는 대신 참으로 만든다.**

    ## ★★ R67/WP-2 — 소계와 총계는 «다른 이름»을 쓴다

    종전의 「한 호에 더해진 합계」는 히트펌프+전기차(러너의
    `extra_appliance_load_kwh`)인데 «합계» 라는 이름이 붙어, 읽는 사람이
    **가구 총 전력이 그 수이고 일반용이 빠졌다**고 읽었다(사용자 판정
    `docs/decisions-2026-09-08-R67.md` §4-2). 빠지지 않았다 — 일반용은 위
    대장 표(ⓑ)에 따로 서 있고 가구 총량은 `일반+HP+EV` 다. 이제 세 항목과
    두 합계가 **이름을 달리** 인쇄된다: «추가 부하 소계(HP+EV)» 는 러너로
    가는 수, «가구 총 전력(일반+HP+EV)» 은 가구가 실제로 쓰는 전기,
    «단지 총 전력» 은 거기에 가구 수를 곱한 것이다.
    """
    loads = report.appliance_loads
    base_kwh = _household_base_kwh(report)
    # 합계 칸에 얹을 「미지정」 항목 이름 — 짝 지어 늦추지 않는다: 이름과
    # `is None` 판정이 어긋나면 없는 항목을 미지정으로 인쇄한다.
    missing_extra = tuple(
        name
        for name, value in (("히트펌프", loads.heatpump_kwh), ("전기차", loads.ev_kwh))
        if value is None
    )
    missing_total = (("일반용",) if base_kwh is None else ()) + missing_extra
    household_total_kwh = (base_kwh or 0.0) + loads.total_kwh
    subtotal_cell = _stated_sum(
        f"{loads.total_kwh:,.0f} {APPLIANCE_LOAD_UNIT}", missing_extra
    )
    household_total_cell = _stated_sum(
        f"{household_total_kwh:,.0f} {APPLIANCE_LOAD_UNIT}", missing_total
    )
    estate_total_cell = _estate_total_cell(
        household_total_kwh, report.household_count, missing_total
    )
    return [
        "",
        "**이 실행이 받은 입력 — 실행 입력이 정하는 값** (사용자 요구 1·2·3)",
        "",
        "| 항목 | 이 실행의 값 | 실행 입력의 통로 |",
        "|---|---|---|",
        f"| 단지 가구 수 | {_household_cell(report.household_count)} "
        f"| 시나리오 yaml `{HOUSEHOLD_COUNT_FIELD}` · 화면 `/ui/run` 칸 — "
        f"안 적으면 대장 `{HOUSEHOLD_COUNT_LEDGER_KEY}` |",
        f"| 일반용 전력 | {_appliance_cell(base_kwh)} "
        f"| 대장 `{HOUSEHOLD_LOAD_LEDGER_KEY}` — 가구가 기본으로 쓰는 전기"
        "(추가 전력사용기기 이전의 기본 소비). 시나리오 yaml 의 "
        "`assumption_overrides` · 설정 화면의 대장 항목 칸 |",
        f"| {HEATPUMP_LOAD_TITLE} | {_appliance_cell(loads.heatpump_kwh)} "
        f"| 시나리오 yaml `{HEATPUMP_LOAD_FIELD}` · 화면 `/ui/run` 칸 — "
        f"안 적으면 대장 `{HEATPUMP_LOAD_LEDGER_KEY}` |",
        f"| {EV_LOAD_TITLE} | {_appliance_cell(loads.ev_kwh)} "
        f"| 시나리오 yaml `{EV_LOAD_FIELD}` · 화면 `/ui/run` 칸 — "
        f"안 적으면 대장 `{EV_LOAD_LEDGER_KEY}` |",
        f"| **추가 부하 소계 (HP+EV)** | {subtotal_cell} "
        "| 히트펌프 + 전기차 — 러너의 `extra_appliance_load_kwh` 로 가는 것은 "
        "**이 수**다 |",
        f"| **가구 총 전력 (일반+HP+EV)** | {household_total_cell} "
        "| 일반용 전력 + 추가 부하 소계 — 가구가 실제로 쓰는 전기 |",
        f"| 단지 총 전력 | {estate_total_cell} "
        "| 가구 총 전력 × 단지 가구 수 — "  # noqa: RUF001
        "**더한 뒤에 곱한다** |",
        f"| {APPLIANCE_SEASON_SHARE_TITLE} "
        f"| {_season_share_cell(loads.season_shares)} "
        f"| 시나리오 yaml `{APPLIANCE_SEASON_SHARE_FIELD}` — **화면 칸은 아직 "
        "없다.** 안 적으면 형상 자산의 `appliance_season_shares:` 절 |",
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
        "미지정이면 그 기기를 **0으로 얹고** 돌았다는 뜻이다. **대장에도 값이 "
        "없을 때만** 그렇게 인쇄된다",
        "- 위 넷은 **실행 입력이 먼저**이고, 적지 않은 칸만 대장·자산이 "
        f"답한다(R65) — 예컨대 `{HOUSEHOLD_COUNT_LEDGER_KEY}` 는 사용자 지시로 "
        "값이 섰다. ⚠ 저장소가 **소스의 기본값으로 메우는 자리는 없다**: 그 "
        "기기를 가구가 갖는지는 사업 계획이 정하는 사실이므로, 값은 대장이나 "
        "실행 입력이 갖는다",
        "- 산식 — 추가 부하 소계 = 히트펌프 + 전기차",
        "- 산식 — 가구 총 전력 = 일반용 전력 + 추가 부하 소계",
        "- 산식 — 단지 총 전력 = 가구 총 전력 × 단지 가구 수 — "  # noqa: RUF001
        "**더한 뒤에 곱한다**(곱한 뒤에 더하면 추가 기기가 단지에 딱 한 대 "
        "있는 사업이 된다)",
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
    """**경제성 민감도** 표 — 점이 없어도 표를 지우지 않는다.

    ## ★★★ 이 표는 「얼마가 적정한가」에 답하지 않는다 (R67/WP-N2)

    종전 마지막 칸은 *「적정값이 이 모델 안에서 정해지는가」* 였다. 사용자가
    산출물을 읽고 그것을 반려했다 — *「적정용량 산정은 전력수요에 맞는
    설비용량을 산출하는 것이고, 용량 범위 제한이 없어야 하며, 경제성으로
    평가하는 것이 아님」*(`docs/decisions-2026-09-08-R67b.md` §1). 그 칸은
    **이 표가 질 물음이 아니다.**

    그 자리에 **「걸린 제약」**을 인쇄한다. 정보를 지우는 것이 아니라 *맞는
    물음*으로 바꾸는 것이다 — 종전 「예 / 아니오」가 모순으로 읽힌 이유가
    **판정 근거(걸린 제약)가 표에 없었던 것**이기 때문이다(판정 §2-4 ·
    `capacity.py::binding_constraint_text` 독스트링).

    ⚠ **`bounded` 속성을 지우지 않았다** — 그 판정(내부 최적점 · 제약)은
    참이고 본문 4.4 가 계속 쓴다. 지운 것은 **그것을 「적정값」이라 부르는
    문면**이다.
    """
    if not findings:
        return ["- 설계 변수 — 없음 (이 실행에는 훑을 용량 축이 서지 않았다)"]
    rows = [
        "| 설계 변수 | 사용값 | 탐색 구간 | 한계 기여 | 결론 축의 형태 "
        "| 구간 내 최선 (경제성) | 걸린 제약 |",
        "|---|---|---|---|---|---|---|",
    ]
    for finding in findings:
        values = [point.value for point in finding.points]
        marginal = (
            f"{_won(finding.marginal_won_per_unit)}/{finding.unit}"
            if finding.marginal_won_per_unit is not None
            else NO_VALUE
        )
        rows.append(
            f"| {finding.label} (`{finding.variable}`) "
            f"| {finding.used_value:g} {finding.unit} "
            f"| {min(values):g}~{max(values):g} {finding.unit} "
            f"({len(values)}점) | {marginal} | {finding.shape} "
            f"| {best_value_text(finding, missing=NO_VALUE)} "
            f"| {binding_constraint_text(finding)} |"
        )
    return rows


def _self_sufficiency_table(sizing: SelfSufficiencySizing) -> list[str]:
    """100% 자립 역산 — 부하 수준마다 필요한 태양광 용량.

    ⚠ **이 표의 답은 ①의 탐색 구간에 매이지 않는다** (R67/WP-N2 · 판정 §2-2).
    칸 이름이 그 구간의 **소유자**를 말하고, 표 아래 주가 *「밖」이 무슨
    뜻인가* 를 적는다 — 종전에는 「탐색 구간 안인가」라고만 적어 두 표가
    같은 구간을 공유하는 것처럼 읽혔다.

    ## ★★★ **1가구 두 칸이 «앞에» 선다** (R67/WP-③ · 사용자 판정 §4-3)

    사용자 문면이 *「2단계는 **1가구 적정 용량을 먼저 제시한 뒤** 20가구 확대
    구성을 설명한다」* 다. 종전 이 표는 **단지 값(20호)만** 실었고, 그래서
    심의자가 「가구 하나에 얼마가 필요한가」를 읽으려면 **표의 수를 20으로
    나눠야** 했다 — 산출물이 답해야 하는 물음을 독자의 나눗셈으로 넘긴 자리다.

    ⚠⚠ **1가구 값은 «나눠서» 만든 것이 아니다** — `core/report/sizing.py::
    build_self_sufficiency_sizing` 이 `required_pv_capacity_kw` 를 **1호분
    부하로 한 번 더 돌린다.** 값의 소유자가 그 함수 하나이므로 이 표는
    나눗셈도 반올림도 하지 않는다.

    ⚠ **가구 한 호 실행에서는 단지 열을 접는다**
    (`SelfSufficiencySizing.scales_to_estate`) — 두 벌이 같은 수인데 두 번
    인쇄하면 검토자가 **둘이 다른 것을 재는 줄로** 읽는다. 접었다는 사실은
    `sizing.py::household_first_notes` 가 글자로 적는다.

    ## ⚠ 짝 렌더러가 있다 — **한쪽만 고치지 마라**

    `core/report/sizing.py::self_sufficiency_section` 이 같은 자료를 심의
    리포트 붙임 10 에 그린다. 두 표는 칸 이름과 단위 표기가 달라 합치지
    않았으나(이 표는 단위를 값에 붙여 쓴다) **열의 순서와 접는 규칙은 같다.**
    """
    span = f"{sizing.search_low_kw:g}~{sizing.search_high_kw:g}kW"
    estate = sizing.scales_to_estate
    head = ["부하 수준", "연간 부하(1가구)", "필요 태양광(1가구)"]
    if estate:
        head += [
            f"연간 부하({sizing.estate_label})",
            f"필요 태양광({sizing.estate_label})",
        ]
    head.append("①의 경제성 스윕 구간 안인가")
    rows = [
        "| " + " | ".join(head) + " |",
        "|" + "|".join(["---"] * len(head)) + "|",
    ]
    for point in sizing.points:
        within = _YES if point.within_search_range else f"{_NO} — 구간 {span} 밖"
        cells = [
            point.source_label,
            f"{_num(point.household_load_kwh)}kWh",
            f"{point.household_capacity_kw:,.2f}kW",
        ]
        if estate:
            cells += [
                f"{_num(point.annual_load_kwh)}kWh",
                f"{point.required_capacity_kw:,.2f}kW",
            ]
        cells.append(within)
        rows.append("| " + " | ".join(cells) + " |")
    rows += [
        "",
        "- 산식 — 필요 용량(kW) = 연간 부하(kWh) ÷ (8,760h × 이용률 "  # noqa: RUF001
        f"{sizing.capacity_factor:.0%})",
        "- 1가구 칸과 "
        + (f"{sizing.estate_label} 칸" if estate else "단지 칸")
        + " — **같은 산식을 각자의 부하로 돌린 결과**다. 단지 값을 가구 수로 "
        "나눈 것이 아니므로 두 칸의 반올림이 서로를 끌지 않는다",
        f"- 이용률의 출처 — {sizing.capacity_factor_source}",
        f"- {search_range_note(sweep_where='위 ①')}",
        *household_first_notes(sizing),
    ]
    return rows


def _ess_sizing_table(
    review: ESSSizingReview, household_count: int | None
) -> list[str]:
    """하루 결손 역산 — 계절마다 필요한 저장장치 용량·출력.

    ⚠ **못 한 것을 「없음」으로 두지 않는다** — 역산할 수 없는 실행에서는
    `ESSSizingReview.unmeasurable_reason` 이 그 사유를 글자로 갖는다.

    ## ★★★ 두 값을 나란히 싣는다 — **역산 채택안이 빠져 있었다** (R67/WP-N3-fix)

    R67/WP-N3 가 완화분(역산 채택안)을 세우고 **심의 리포트 붙임 10 에만** 실었다.
    그동안 이 표는 완전 자립분만 실어, 두 산출물이 같은 물음에 다르게 답했다 —
    실측: 붙임 10 은 겨울 **642.07kWh**(역산 채택안), 이 표는 **917.25kWh** 하나.
    검증 리포트는 **사용자가 지금 읽는 산출물**이므로 그 상태는 *「ESS 적정용량이
    917 kWh 다」* 로 읽힌다.

    ## ⚠⚠ 같은 자료를 그리는 렌더러가 **둘로 남아 있다**

    `core/report/ess_sizing_section.py::ess_daily_sizing_section` 이 그 짝이다.
    ⛔ **한쪽만 고치지 마라.** 합치지 않은 이유는 표 자체가 다르기 때문이다 —
    이 표는 **단위를 값에 붙여** 쓰고(`564.17kWh`) 절 번호가 `①` 다.
    ⇒ **낱말은 합쳐 두었다**: `ADOPTED_HEAD` · `SELF_SUFFICIENT_HEAD` ·
    `within_range_head` · `adopted_value_note` · `relaxation_reach_note` ·
    `PER_HOUSEHOLD_HEAD` · `per_household_scaled` ·
    `per_household_scaled_notes` 가 그 파일 머리에 있고 여기서 들여와 쓴다.
    **베껴 적지 않는다.**

    ## ★★★ **1가구 두 칸이 «앞에» 선다 — 그리고 「비례 환산」이라 적는다**

    R67/WP-③-fix · 사용자 판정 §4-3 *「1가구 적정 용량을 **먼저** 제시한 뒤 20가구
    확대 구성을 설명한다」*. ②(자립 PV)와 **성질이 다르므로 이름도 다르다:**

    | | ② 자립 PV | **③ 이 표** |
    |---|---|---|
    | 역산의 입력 | 대장 부하 수준의 **수** | **20호로 돈 운전의 스텝별 시계열** |
    | 1호분 입력이 있나 | 있다(곱하기 **전** 부하) | ⛔ **없다** |
    | 1가구 값을 어떻게 얻나 | 산식을 **1호분으로 다시 돈다** | **나눈다**(비례 환산) |

    ⚠⚠ **그 성질을 표가 스스로 말한다** — 열 이름이 `PER_HOUSEHOLD_HEAD`
    (「1가구(비례 환산)」)이고 표 아래 세 줄이 *왜 환산인지* · *환산의 근거* ·
    *②와 무엇이 다른지* 를 적는다(`per_household_scaled_notes`). 적지 않으면
    다음 사람은 이 열을 **역산 결과로 읽는다.**

    ⚠ **역산 채택안만 환산한다** — 이 표가 「답」이라 말하는 열이 그것이고
    (`ADOPTED_HEAD`), 완전 자립분까지 환산하면 열이 열셋이 되어 읽히지 않는다.
    완전 자립분은 **견줌**이므로 단지 값 하나로 족하다.

    ⚠ 가구 수 1(또는 미지정)이면 ② 와 **같은 규칙**으로 열을 접는다 —
    같은 수를 두 번 인쇄하지 않는다(지시문 §2-5).
    """
    if review.unmeasurable_reason is not None:
        return [f"- 역산하지 못했다 — {review.unmeasurable_reason}"]
    span = f"{review.search_low_kwh:g}~{review.search_high_kwh:g}kWh"
    scaled = household_count is not None and household_count > 1
    head = ["계절", "일수"]
    if scaled:
        head += [
            f"{PER_HOUSEHOLD_HEAD} {ADOPTED_HEAD} 정격용량",
            f"{PER_HOUSEHOLD_HEAD} {ADOPTED_HEAD} 정격출력",
        ]
    head += [
        "하루 필요 방전량",
        "최대 결손(스텝)",
        f"{SELF_SUFFICIENT_HEAD} 정격용량",
        f"{SELF_SUFFICIENT_HEAD} 정격출력",
        f"{ADOPTED_HEAD} 정격용량",
        f"{ADOPTED_HEAD} 정격출력",
        within_range_head(sweep_where="①의"),
    ]
    rows = [
        "| " + " | ".join(head) + " |",
        "|" + "|".join(["---"] * len(head)) + "|",
    ]
    for season in review.seasons:
        sizing = season.sizing
        # ★ **구간 판정의 대상은 역산 채택안이다** — 붙임 10 과 같다. 완전 자립분에
        # 붙이면 표가 「답」이 아닌 수를 구간과 견준다.
        adopted = season.relaxed
        within = _YES if adopted.within_search_range else f"{_NO} — 구간 {span} 밖"
        cells = [season.season_name, f"{season.days}일"]
        if scaled:
            # ⛔ **나눗셈을 여기서 하지 않는다** — 산식의 소유자는
            # `per_household_scaled` 하나이고, 그 함수의 독스트링이 *왜 나누는가*
            # 와 *그것이 옳다는 실측*을 진다. 여기 적으면 그 근거가 사본이 된다.
            cells += [
                f"{per_household_scaled(adopted.required_capacity_kwh, household_count):,.2f}kWh",
                f"{per_household_scaled(adopted.required_power_kw, household_count):,.2f}kW",
            ]
        cells += [
            f"{sizing.required_discharge_kwh:,.2f}kWh",
            f"{sizing.peak_shortfall_kwh:,.2f}kWh",
            f"{sizing.required_capacity_kwh:,.2f}kWh",
            f"{sizing.required_power_kw:,.2f}kW",
            f"{adopted.required_capacity_kwh:,.2f}kWh",
            f"{adopted.required_power_kw:,.2f}kW",
            within,
        ]
        rows.append("| " + " | ".join(cells) + " |")
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
        # ★ 완화 비율의 **출처**를 잃지 않는다 — 문면의 정본은 그 함수다.
        f"- {adopted_value_note(review)}",
        f"- {relaxation_reach_note(review)}",
        f"- 어느 해의 결손인가 — 분석기간 말({review.year}년차). 열화가 가장 "
        "진행된 해라 필요한 용량이 가장 크다",
        f"- {search_range_note(sweep_where='위 ①')}",
        # ★★ **1가구 열의 성질을 표가 말한다** — 낱말도 문면도 정본은
        # `ess_sizing_section.py` 다(위 독스트링 ⚠⚠).
        *per_household_scaled_notes(household_count),
    ]
    return rows


def run_used_values(report: CaseReport) -> list[str]:
    """이 실행이 **실제로 세우고 돌린** 용량 — 「설비 이름 **값 단위**」 조각들.

    ⚠ **두 자리가 이 목록을 나눠 갖는다** — 구분 표의 「실행 용량」 칸
    (`core/report/ess_sizing_section.py::capacity_kind_lines`)과 그 아래
    `_run_configuration_lines` 의 문장이다. 베껴 적으면 한쪽만 고쳐지고, 그때
    같은 절이 **실행 용량을 두 가지로** 말한다.

    ⚠ 수를 이 파일이 갖지 않는다 — 설계 변수의 사용값은 `report.capacity_review`
    의 `used_value` 이고 정격출력은 `report.ess_sizing.run_power_kw` 다.
    """
    used = [
        f"{finding.label} **{finding.used_value:g} {finding.unit}**"
        for finding in report.capacity_review
    ]
    power_kw = report.ess_sizing.run_power_kw
    if power_kw is not None:
        used.append(f"저장장치 정격출력 **{power_kw:g} kW**")
    return used


def _run_configuration_lines(report: CaseReport) -> list[str]:
    """**지금 도는 구성**을 수로 적는다 — 아래 역산값과 견줄 대상 (R67/WP-③).

    ## 왜 이 줄이 필요한가 (사용자 판정 §4-3 *「진단값과 실제 실행값을 구분한다」*)

    아래 ①②③ 이 모두 **진단**인데, 그 위에 *「진단이지 결론이 아니다」* 만
    있고 **지금 무엇으로 돌고 있는지가 수로 없었다.** 그러면 검토자는 아래
    역산값이 실행 구성과 얼마나 다른지를 다른 절로 넘어가 맞춰 봐야 하고,
    맞춰 보지 않으면 **역산값을 이 실행의 구성으로 읽는다.**

    ⚠ **수를 이 파일이 갖지 않는다** — 설계 변수의 사용값은
    `report.capacity_review` 의 `used_value`(경제성 스윕이 훑은 그 축의 기준
    점)이고 정격출력은 `report.ess_sizing.run_power_kw` 다. 여기 적으면
    실행이 다른 용량으로 도는 날 이 줄만 옛 수를 들고 있게 된다.

    ⛔ **그냥 「채택」이라 쓰지 않는다** (판정 §4-4). 이 구성은 역산의 **결과가
    아니고**, 역산값을 적용한 것도 아니다 — 그 둘을 한 낱말로 묶으면 산출물이
    *「역산대로 세웠다」* 를 주장하게 된다. ⇒ 이 구성을 부르는 이름은
    `core/report/ess_sizing_section.py::CAPACITY_KIND_RUNNING`(「실행 용량」)이고
    위 구분 표가 그것을 진단 용량·채택 용량과 갈라 세운다(R68/WP-1).
    """
    used = run_used_values(report)
    if not used:
        return [
            "⚠⚠ **지금 도는 구성** — 이 실행에는 설계 변수가 서지 않아 적을 "
            "용량이 없다. 아래 역산값은 **어느 구성에도 적용되지 않았다.**",
        ]
    return [
        "⚠⚠ **지금 도는 구성과 아래 역산값은 다른 수다.** 이 실행이 실제로 "
        f"세우고 돌린 것은 {' · '.join(used)} 이며, 그것은 **역산의 결과가 "
        "아니다**(위 ⓐ 자원 표가 그 자원의 제원을 진다). 아래 ②③ 이 내는 수는 "
        "**진단값**이고 이 실행에 적용되지 않았다 — 적용하면 결론축이 움직이며 "
        "그것은 이 리포트가 한 일이 아니다.",
    ]


def capacity_review_lines(report: CaseReport) -> list[str]:
    """2단계 ⓑ 뒤 — **적정 용량 검토와 역산** (사용자 요구 4).

    ## ⚠⚠ 진단이지 결론이 아니다

    아래 셋은 이 실행의 자원 구성을 **바꾸지 않는다.** 역산 결과를 실행에
    되먹이지 않으므로 8단계 지표는 이 수에 움직이지 않으며, 그 사실을 표 위에
    글자로 적는다 — 적지 않으면 검토자가 「이 용량으로 돌렸다」로 읽는다
    (`core/report/ess_sizing_section.py` 머리말 ★★★ 이 같은 판단을 적었다).

    ## ★★★ ①과 ②③ 을 **물음으로 갈랐다** (R67/WP-N2 · 판정 R67b §2)

    종전에는 셋이 번호만 달고 나란히 섰고, ①이 *「적정값이 이 모델 안에서
    정해지는가」* 를 인쇄했다 — 즉 **경제성 스윕이 적정값을 정한다고 주장**
    했다. 사용자가 그것을 반려했다(*「경제성으로 평가하는 것이 아님」*).
    이제 ①은 이름으로 **경제성 민감도**임을 말하고, ②③ 이 **수요 기반 적정
    용량**임을 말한다. ⚠ **표를 없애지 않았다** — ①은 민감도로서 값이 있다.
    """
    return [
        "",
        "**적정 용량 검토 — 이 용량이 적정한가 · 얼마면 되는가** (사용자 요구 4)",
        "",
        "⚠ **진단이지 결론이 아니다.** 아래 셋은 이 실행의 자원 구성을 바꾸지 "
        "않는다 — 역산 결과를 실행에 되먹이지 않으므로 8단계 지표는 이 수에 "
        "움직이지 않는다. 위 ⓐ·ⓑ 가 이 실행이 **실제로 세운** 자원이다.",
        "",
        # ★★★ **절 머리에 구분 표가 먼저 선다** (R68/WP-1 · 검토서 §3.2).
        # 「채택」이 ⓐ 역산 갈래 둘 중 답으로 고른 쪽과 ⓑ 실행에 반영하기로
        # 결정한 값을 함께 가리켰고, 그래서 겨울 역산값이 *「이 용량으로
        # 돌렸다」* 로 읽혔다. ⇒ 셋을 **읽는 순서의 맨 앞에서** 갈라 세운다.
        # ⚠ 표의 수를 이 파일이 갖지 않는다 — 렌더러가 `report` 에서 읽는다.
        *capacity_kind_lines(
            review=report.ess_sizing,
            pv=report.self_sufficiency,
            run_used=run_used_values(report),
        ),
        "",
        # ★★★ **진단값과 실행값을 «한 자리에서» 갈라 적는다** (R67/WP-③ ·
        # 사용자 판정 §4-3 *「진단값과 실제 실행값을 구분한다」*). 종전에는
        # 「진단이지 결론이 아니다」만 있고 **지금 도는 구성이 수로 없어서**,
        # 검토자가 아래 역산값과 견줄 대상을 다른 절에서 찾아야 했다.
        # ⛔ **「채택했다」로 적지 않는다** — 판정 §4-4 가 *「적용 전이면 결과를
        # 만들어 낸 것처럼 표시하지 않는다」* 로 금했다. 그래서 문면은
        # **「지금 도는 구성」**(= 실행 용량)이고 「역산 채택안」이 아니다.
        # ⚠ 수를 리터럴로 적지 않는다 — `capacity_review` 의 설계 변수 사용값과
        # `ess_sizing.run_power_kw` 가 정본이다.
        *_run_configuration_lines(report),
        "",
        f"⚠⚠ **①과 ②③ 은 서로 다른 물음에 답한다.** ①은 {ECONOMIC_SENSITIVITY_TITLE}"
        "이고 *「용량을 흔들면 결론축이 얼마나 움직이나」* 를 재며, **얼마가 "
        "적정한가에 답하지 않는다.** ②③ 이 적정 용량을 내고 그 축은 **전력수요와 "
        "그 시간 분포**다 — 경제성 지표로 정하지 않는다. 나란히 서 있으므로 "
        "적어 둔다: 어느 것이 「적정값」인지 독자가 고르게 두지 않는다.",
        "",
        f"① **{ECONOMIC_SENSITIVITY_TITLE}** — 설계 변수를 탐색 구간에서 훑은 "
        "결과(1변수 스윕 · 나머지는 기준값 고정). **적정값을 정하는 표가 "
        "아니다**:",
        "",
        *_capacity_table(report.capacity_review),
        "",
        "② **수요 기반 적정 용량** · 경우 「가」 — 100% 자립에 필요한 태양광 "
        "용량 **역산**:",
        "",
        *_self_sufficiency_table(report.self_sufficiency),
        "",
        # ★ **역산 채택안이 어느 열인지 절 머리가 먼저 말한다** (R67/WP-N3-fix).
        # 표만 보면 두 값 중 어느 것이 답인지 고르는 일이 독자에게 넘어간다 —
        # ⚠⚠ 위 절 머리가 이미 *「진단이지 결론이 아니다」* 를 적었으므로, 그
        # 둘을 함께 읽어야 「역산 채택안이지만 실행 구성은 아니다」가 성립한다.
        f"③ **수요 기반 적정 용량** · 경우 「ESS」 — 하루 결손을 감당하는 "
        f"저장장치 용량 **역산**(계절별). **{ADOPTED_HEAD} 열이 역산이 고른 "
        f"답**이고 완전 자립분은 견줌으로 함께 싣는다 — 위 구분 표의 "
        f"{CAPACITY_KIND_DIAGNOSTIC}이며 {CAPACITY_KIND_APPLIED}이 아니다:",
        "",
        *_ess_sizing_table(report.ess_sizing, report.household_count),
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
#
# ⚠⚠ **3단계 ⓐ 자원 표를 짓는 `dispatch_note_rows()` 도 여기 있었다가
# 옮겨졌다**(R68/WP-2) — 정본은 `core/report/verification_dispatch.py` 다.
# R68 이 그 한 칸을 **선언 열과 실제 배분 열 둘로** 가르면서 표 아래 세 줄까지
# 함께 서야 했고, 이 파일은 그 시점에 코드 **486/500** 줄이라(NFR-206 ·
# `scripts/check_file_size.py --code-strict`) 새 코드를 쌓을 자리가 없었다.
# ⚠ 이 파일이 그 모듈에서 가져오는 것은 **열 이름 규칙**(`resource_labels`)
# 하나이며, 아래 계절 기여 표가 그것으로 사람용 이름과 조인 키를 병기한다.


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
        # ★ **사람용 이름을 앞에 · 조인 키를 뒤에** (R68/WP-2 · 검토서 §3.3
        # 마지막 항목). `e2e-pv` 는 조인 키이고 심의자가 읽을 이름이 아니다 —
        # ⚠ 그렇다고 키를 **갈아 끼우지** 않는다(같은 종류 자원이 둘이면 이름이
        # 겹쳐 열 하나가 사라진다). 값을 찾는 것은 여전히 아래 `names` 의 키다.
        "| 계절 | " + " | ".join(resource_labels(names, report.basis.resources)) + " |",
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
        # ⚠ **부호 규약 줄은 여기 있었다가 ⓓ(계산 수식) 칸으로 내려갔다**
        # (R68/WP-2 · 검토서 §4.3). 사람이 읽는 표를 **규약을 먼저 읽지 않고**
        # 읽을 수 있어야 한다는 요구이며, **표 자체의 부호는 그대로다** —
        # 자원 수지는 부호가 뜻이다. 정본은
        # `core/report/verification_dispatch.py::SIGN_CONVENTION_NOTE` 다.
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
    # ★★ **계절마다 하루 스텝 전건** (R68/WP-3 · 검토서 §3.4). 위 두 표는 계절의
    # **연간 합계**이고, 검토서가 요구한 것은 *「계절마다 하루 24스텝 + 대조」*
    # 다. ⚠ 표를 짓는 기계는 이 파일에 두지 않았다 — 이 파일은
    # `scripts/check_file_size.py --code-strict` 의 코드 500줄 상한(NFR-206)에
    # 스물 몇 줄을 남기고 있고, 붙임 7 의 스텝 표 기계
    # (`core/report/dispatch_sections.py::step_table`)를 **두 벌로 만들지 않는
    # 것**이 그 요구의 다른 절반이다(WP-2 가 `dispatch_note_rows` 를 옮긴 것과
    # 같은 판단이다 · `core/report/verification_dispatch.py` 머리말).
    lines += season_step_tables(report)
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
