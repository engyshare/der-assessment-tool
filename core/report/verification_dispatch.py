"""검증 3단계 ⓐ — **선언한 운전방식과 본 실행이 실제로 적용한 배분을 두 열로**
가른다 (R68/WP-2 · 검토서 §3.3 · §4.3).

## 무엇이 어긋나 있었나

3단계 ⓐ 표의 「운전방식」 한 칸에 이렇게 적혔다:

    전량 판매 (선언) · 본 실행 배분: 집 우선

그리고 2단계 ⓐ 는 같은 자원을 「자가소비율 … (본 실행 실측)」이라 적는다.
검토서 §3.3 이 그 병치를 짚었다 — *「전량 판매와 집 우선 자가소비는 같은
실행에서 동시에 참일 수 없다」*. 실제로는 **둘 다 참**이다: 선언은 잉여의
처분 방침이고 배분은 낮 동안 그 잉여가 무엇이 되는가를 정한다(판정 §4 ⚠ ·
`core/der/pv.py` 가 전량 판매에서 자가소비율을 0 으로 덮고 `pv_allocation_
priority` 축이 행선지를 따로 정한다). **엔진이 아니라 읽는 자리가 문제였다.**

⇒ 두 축을 **각자의 열**에 싣는다. 그러면 한 칸 안의 모순이 두 열의 사실이 된다.

## ⛔ 왜 문자열을 쪼개지 않는가

합친 문면을 ` · ` 로 가르면 **조용히 틀린다** — 배분 문면 «안에도» 그 구분자가
있다(「자가소비 우선 · 방전 배분: 부하 추종 (방전창 18~21시 안)」). 그래서
러너가 두 조각을 각자의 칸에 실어 오고(`ResourceLine.applied_allocation`),
이 모듈은 **파싱 없이** 두 열을 그린다.

## 왜 `verification_inputs.py` 가 아니라 새 모듈인가

`scripts/check_file_size.py --code-strict` 가 코드 500줄에서 CI 를 차단하는데
(NFR-206) `core/report/verification_inputs.py` 는 그 시점에 코드 **486줄**이었다
— 남은 자리가 열넷이다. 상한을 올리는 것은 spec 개정이므로(§16.5) 새 코드는
여기 쌓는다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.casegrid.models import ResourceLine, SeasonRun
from core.contracts.units import ENERGY_TOLERANCE_KWH
from core.report._format import _num
from core.report.case_report import CaseReport
from core.report.dispatch_notes import (
    NO_APPLIED_ALLOCATION,
    DispatchHour,
    applied_allocation,
    build_hourly_profile,
    declared_operating_mode,
    resource_display_name,
    split_by_direction,
    split_three_ways,
)
from core.report.dispatch_sections import (
    GENERATION_HEAD,
    GRID_EXPORT_HEAD,
    GRID_IMPORT_HEAD,
    LOAD_HEAD,
    STORAGE_CHARGE_HEAD,
    STORAGE_DISCHARGE_HEAD,
    human_step_columns,
    step_table,
)

#: 3단계 ⓐ 표의 머리. **두 열이 여기서 갈린다.**
#:
#: ⚠ 「전제」를 쓰지 않는다 — 사람이 읽는 자리(표 머리 `th`)의 그 낱말은 0건이
#: 규약이다(판정 R63b §1 · `tests/app/test_screen_words.py`).
DISPATCH_TABLE_HEAD: tuple[str, ...] = (
    "| 자원 | 선언한 운전방식 | 본 실행이 실제로 적용한 배분 | 디스패치 규칙 "
    "| 우선순위 | 가격신호 필요 |",
    "|---|---|---|---|---|---|",
)

#: ⓓ(계산 수식) 칸으로 **옮겨 온** 부호 규약 (검토서 §4.3).
#:
#: ## 왜 ⓑ 에서 내렸는가
#:
#: 종전에는 계절별 자원 표 바로 아래에 있었고, 그래서 **사람이 읽는 표를 읽기
#: 전에 부호 규약을 먼저 읽어야** 했다. 검토서 §4.3 이 그것을 짚었다 —
#: *「사람용 표에서는 한전 수전·역송을 양의 수량으로 별도 열에 두고, 내부
#: 부호는 수식 설명에만 남기는 편이 안전하다」*.
#:
#: ⚠ **표 자체의 부호는 그대로 둔다.** 자원 수지는 **부호가 뜻**이다(충전과
#: 방전이 한 열에 서야 「스텝 합계가 계통 송전량과 맞는가」를 눈으로 셀 수
#: 있다 — `core/report/dispatch_notes.py::DispatchHour` 의 ⚠). 옮긴 것은
#: **규약 줄**이고 표가 아니다.
#: ⚠ 계통 수전·역송은 ⓑ 첫 표가 **이미 양수 별도 열**로 싣는다(실물 확인:
#: 「그 계절의 연간 계통 송전」·「연간 계통 수전」 두 열이 양수다) — 그래서
#: 검토서가 요구한 「부호 의존성 제거」는 그 표에서 이미 성립해 있다.
SIGN_CONVENTION_NOTE = (
    "- 부호 규약 — ⓑ 의 「자원별 — 그 계절이 한 해에 보태는 몫」 표는 **양수를 "
    "내보냄 · 음수를 받아들임**으로 싣는다(부하가 음수로 나타난다). 자원 수지는 "
    "**부호가 뜻**이라 표에서 부호를 걷지 않고 규약을 이 칸에 두었다 — 계통 "
    "수전·역송은 ⓑ 첫 표가 **이미 양수 별도 열**이므로 그 표는 부호를 읽지 "
    "않고도 읽을 수 있다"
)


def resource_label(name: str, kinds: Mapping[str, str]) -> str:
    """**사람용 이름을 앞에 · 조인 키를 뒤에** — 「태양광 (옥상 고정형) (`e2e-pv`)」.

    ## ⛔ 키를 «갈아 끼우는» 함수가 아니다 — «병기»다

    `e2e-pv` 는 리포트·귀속 행·붙임·시험이 서로를 맞추는 **조인 키**이고
    (`core/casegrid/models.py::ResourceLine.name`), 사람이 읽을 이름은 아니다
    (`core/report/method_sections.py::_earner_cell` 이 같은 판단을 적었다).
    그렇다고 키를 라벨로 **갈아 끼우면** 같은 종류 자원이 둘인 실행에서 두 줄이
    한 이름이 되고, 그림에서는 사전 키가 겹쳐 **계열 하나가 사라진다**
    (`core/report/charts/seasonal_operation.py` 독스트링이 그 사유를 적었다).
    ⇒ 이 문서는 **검증 문서**이므로 둘을 함께 싣는다: 이름으로 읽고 키로 대조한다.

    ## ⚠ 이름을 새로 짓지 않는다

    사람용 이름의 갈래 셋은 **한 곳**이 정한다 —
    `core/report/dispatch_notes.py::resource_display_name()` 이며 여기서 다시
    고르지 않는다. 이 함수가 하는 일은 그 이름에 **조인 키를 병기**하는 것뿐이다.

    ## ★★ R68/WP-3 — **`e2e-load` 가 키만 인쇄되던 것을 닫았다**

    WP-2 는 이 자리를 반만 닫았다. 부하는 `CaseBasis.resources` 에 **없어서**
    `kind` 가 없고, 화면이 쓰는 낱말 「가구 전력수요」는 `app/services/
    ui_charts.py` 에 있어 이 계층이 import 할 수 없었다(NFR-208-AC1 —
    `core` 가 `app` 을 알 수 없다). 그래서 이 표에서 부하 한 줄만 **`e2e-load`**
    였다. R68/WP-3 이 그 낱말의 정본을 `core/report/dispatch_notes.py::
    DEMAND_LABEL` 로 내렸고(사유는 그 상수의 주석), 그러므로 지금은 **세 갈래가
    모두 사람 말을 얻는다.** ⛔ 그렇다고 **이름을 여기서 짓지는 않는다** — 위
    한 곳이 정본이다.
    """
    human = resource_display_name(name, kinds)
    return f"{human} (`{name}`)" if human else f"`{name}`"


def resource_labels(
    names: Sequence[str], resources: Sequence[ResourceLine]
) -> list[str]:
    """계절 기여 표의 **열 이름** — 키 차례 그대로 위 규칙을 건다.

    ⚠ **키 자체는 그대로 남는다** — 값을 찾는 것은 여전히 `names` 의 키다
    (`SeasonRun.per_resource_annual_kwh`). 이 함수가 내는 것은 인쇄할 글자뿐이다.
    """
    kinds = {line.name: line.kind for line in resources}
    return [resource_label(name, kinds) for name in names]


def _mode_cells(report: CaseReport) -> list[tuple[str, str, str]]:
    """자원마다 (인쇄할 이름, 선언, 실제 배분) — **표와 아래 세 줄이 같은 판정을 읽는다.**

    ⚠ 갈래를 두 곳에서 정하면 표의 열과 그 아래 「갈렸다/안 갈렸다」 문장이
    서로 다른 답을 적을 수 있고, 그때 둘 다 그럴듯해 보인다.
    """
    kinds = {line.name: line.kind for line in report.basis.resources}
    allocations = {
        line.name: line.applied_allocation for line in report.basis.resources
    }
    return [
        (
            resource_label(note.resource_name, kinds),
            declared_operating_mode(note),
            applied_allocation(note, allocations),
        )
        for note in report.dispatch_notes
    ]


def dispatch_note_rows(report: CaseReport) -> list[str]:
    """3단계 ⓐ 자원 표의 **데이터 행** — 선언과 실제가 **다른 열**에 선다.

    종전에는 한 칸에 합쳐 실었고(`resolved_operating_mode()`), 그래서 같은
    문서의 「전량 판매」와 「자가소비율 … (본 실행 실측)」이 초독자에게
    **모순으로 읽혔다**(검토서 §3.3 · R64/WP-FIX 결함 2 의 나머지 절반).
    합친 칸은 심의 리포트 붙임 6 이 계속 읽으므로 **그 문면은 그대로 있다** —
    이 표만 두 열로 간다.

    ⚠ 운전 방법을 고르지 않는 자원(부하)은 두 칸에 같은 문장을 되풀이하지
    않는다 — 선언 칸이 그 문장을 갖고 실제 칸은 `NO_APPLIED_ALLOCATION` 이다.
    """
    return [
        f"| {label} | {declared} | {applied} | `{note.dispatch_rule.value}` "
        f"| {note.dispatch_priority} "
        f"| {'예' if note.price_linked else '아니오'} |"
        for (label, declared, applied), note in zip(
            _mode_cells(report), report.dispatch_notes, strict=True
        )
    ]


def _divergence_line(diverged: Sequence[tuple[str, str]]) -> str:
    """① 선언과 실제가 갈린 자원이 있는가 — **갈려도 결함이 아닌 사유까지.**"""
    if not diverged:
        return (
            "- **선언과 본 실행 배분이 갈린 자원 — 없다.** 이 실행은 자원마다 "
            "선언한 운전방식 그대로 배분했다"
        )
    who = " · ".join(label for label, _ in diverged)
    return (
        f"- **선언과 본 실행 배분이 갈린 자원 — {who}.** 갈려도 **결함이 아니다**: "
        "선언은 잉여의 **처분 방침**이고, 배분은 낮 동안 **그 잉여가 무엇이 "
        "되는가**를 정한다. 두 축이 따로 서 있으므로 이 표가 둘을 각자의 열에 "
        f"싣는다 — 운전 방법을 고르지 않는 자원은 실제 칸이 "
        f"`{NO_APPLIED_ALLOCATION}` 이며 「아직 안 적었다」가 아니라 「고를 배분이 "
        "없다」다"
    )


def _realization_line(declared: Sequence[str], grid_export_kwh: float) -> str:
    """② 그 선언이 **이 실행에서** 실현됐는가 — 수와 함께.

    ⚠⚠ **「0」을 리터럴로 박지 않는다.** 계통 송전이 있는가 없는가를 이 함수가
    실행의 수로 판정하고, 인쇄하는 수도 그 실행의 것이다. 박으면 송전이 생기는
    실행에서 이 줄이 조용히 거짓이 된다.

    ⚠⚠⚠ **「갈린 자원 전부」로 재면 거짓이 실린다** — 계통 송전이 재는 것은
    **내보내는 자원의 선언**뿐이다. 저장장치의 「자가소비 우선」은 계통 송전이
    0 이어도 **실현된 것**이므로, 그 라벨까지 이 줄에 끌어들이면 *「자가소비
    우선 선언이 실현되지 않았다」* 라는 거짓 문장이 인쇄된다. ⇒ 부르는 쪽이
    `split_by_direction()` 으로 **발전 쪽 자원만** 골라 넘긴다.

    ⚠ 라벨 뒤에 조사를 붙이지 않는다 — 라벨이 무엇으로 끝나는지에 따라
    「를/을」이 갈리고, 문장을 짓는 자리는 그 낱말을 모른다.
    """
    total = f"{_num(grid_export_kwh)}kWh"
    if not declared:
        return (
            "- **이 실행에서 그 선언이 실현됐는가** — 계통 송전 합계는 "
            f"{total} 다(아래 ⓑ 가 같은 수를 싣는다). 이 실행에는 배분이 선언과 "
            "갈린 **발전 자원**이 없어 이 물음이 서지 않는다 — 계통 송전으로 "
            "잴 수 있는 선언은 내보내는 자원의 것뿐이다"
        )
    what = " · ".join(f"「{label}」" for label in declared)
    if grid_export_kwh > 0.0:
        return (
            "- **이 실행에서 그 선언이 실현됐는가** — 이 실행의 계통 송전 합계는 "
            f"**{total}** 다(아래 ⓑ 가 같은 수를 싣는다). 계통으로 나간 양이 "
            f"있으므로 {what} 선언이 이 실행에서 **적어도 일부 실현됐다** — "
            "얼마가 그 선언대로였는지는 이 표가 재지 않는다(4단계 잉여 판매 "
            "편익이 그 수량을 싣는다)"
        )
    return (
        "- **이 실행에서 그 선언이 실현됐는가 — 아니다.** 이 실행의 계통 송전 "
        f"합계는 **{total}** 다(아래 ⓑ 가 같은 수를 싣는다) — 계통으로 나간 "
        f"양이 없으므로 {what} 선언은 **이 실행에서 실현되지 않았다.** 이 실행이 "
        "실현한 것은 오른쪽 「본 실행이 실제로 적용한 배분」 열이다"
    )

#: ③ 이 열이 움직이면 **무엇이 함께 움직이는가** (검토서 §3.3 세째 항목).
#:
#: ⚠ 이 줄이 없으면 두 열이 「표기 문제」로만 읽힌다. 배분은 표기가 아니라
#: **편익의 대입값**을 정한다.
LINKAGE_NOTE = (
    "- **연결** — 운전 배분이 바뀌면 **4단계의 잉여 판매·REC·자가소비 회피 "
    "편익이 함께 바뀐다.** 배분이 낮 동안 잉여의 행선지를 정하고 그 수량이 그 "
    "세 편익의 대입값이므로, 이 열이 다른 실행은 4단계 표도 함께 읽어야 한다"
)


def declaration_lines(report: CaseReport, *, grid_export_kwh: float) -> list[str]:
    """위 표 **바로 아래 세 줄** — 갈렸는가 · 실현됐는가 · 무엇과 이어지는가.

    ## ⚠ 왜 계산된 수가 ⓐ 아래에 서는가

    두 번째 줄은 계통 송전 합계를 **수와 함께** 적어야 하는데(WP-2 §2ⓑ-2) 그
    수는 ⓑ 의 것이다. 그래서 그 줄은 *「아래 ⓑ 가 같은 수를 싣는다」* 를 함께
    적는다 — 표 아래에 두라는 요구와 「ⓐ 는 전제한 수치」라는 이 문서의 틀을
    둘 다 지키는 방법은 **어느 칸의 수인지 글자로 가리키는 것**뿐이다.
    """
    diverged = [
        (note.resource_name, label, declared)
        for (label, declared, applied), note in zip(
            _mode_cells(report), report.dispatch_notes, strict=True
        )
        if applied not in (NO_APPLIED_ALLOCATION, declared)
    ]
    # ★ **계통 송전이 재는 것은 «내보내는» 자원의 선언뿐이다** — 가름은 이
    # 저장소의 하나뿐인 규칙(`split_by_direction`)이 한다. 이름으로 가르면
    # 자원이 늘 때마다 여기를 고쳐야 하고, 고치지 않으면 조용히 0 이 된다.
    generation, _load = split_by_direction(report.dispatch_hours)
    return [
        "",
        _divergence_line([(label, declared) for _, label, declared in diverged]),
        _realization_line(
            [declared for name, _, declared in diverged if name in generation],
            grid_export_kwh,
        ),
        LINKAGE_NOTE,
    ]


# ── 3단계 ⓑ — 계절마다 **하루 스텝 전건** (R68/WP-3 · 검토서 §3.4 · 판정 §4-4) ──
#
# ## 무엇이 없었나
#
# 3단계는 계절별 **연간 합계만** 실었다(봄 18,073kWh …). 검토서 §3.4 가 요구한
# 것은 *「계절마다 하루 24스텝 표 + 그 아래 «하루 합계 × 계절 일수 = 계절
# 연간값» 대조」* 이며, 그 표는 **심의 리포트 붙임 7 에만** 있었다. 재료는 이미
# 있었다 — `SeasonRun.dispatch` 가 계절마다 하루를 나르고
# `build_hourly_profile()` 이 그것을 스텝으로 편다. **새 계산을 짓지 않았다.**
#
# ## ⚠ 표를 두 벌로 그리지 않았다 — 기계는 하나, 열 구성은 인자
#
# 붙임 7 의 표는 자원별 **부호** 표이고 이 표는 사람용 **양수** 표다(검토서
# §4.3). 열이 다르지만 그리는 기계는 `dispatch_sections.py::step_table()`
# 하나이며, 열 구성만 `human_step_columns()` 에서 온다 —
# `_hour_table()` 독스트링이 *「계절 쪽에 사본을 만들지 마라」* 라고 이미 적었다.

#: SOC 열의 자리 — **글자로 적는다.** 지어낼 수 있는 수가 아니다.
#:
#: ## ⛔ 왜 충·방전에서 역산하지 않는가
#:
#: 검토서 §3.4 의 표는 일곱째 열로 SOC 를 요구한다. 그런데 이 층에 도착하는
#: 운전 결과에는 **SOC 계열이 없다** — `core/contracts/der.py::DispatchResult`
#: 는 매체 4종과 미충족 계열뿐이고 `core/contracts/engine.py::SystemDispatch` 는
#: 자원별 결과·수전·송전뿐이며 `DispatchHour` 는 그 셋을 스텝으로 편 것이다.
#: 충·방전에서 되짚으려면 **초기 SOC 와 효율 배분 규약**을 알아야 하는데 그 둘은
#: 자원 안에 있다(`core/der/ess.py::soc_bounds_kwh` · RTE). 표시 층이 그것을
#: 가정해 그리면 **지어낸 수**이고, 사용자 판정
#: `docs/decisions-2026-09-08-R67.md` §4-4 가 그 자리를 금한다 — *「적용 전이면
#: 결과를 만들어 낸 것처럼 표시하지 않는다」*.
#: ⇒ 이 저장소의 ★★ 규약(*「`None` 은 빈칸이 아니라 진술이다」*)대로 **없다는
#: 사실을 인쇄한다.** 빈 열을 세우면 「0% 였다」로 읽힌다.
SOC_NOT_CARRIED = (
    "- **SOC(충전 상태) 열 — 미산출.** 이 실행의 운전 결과가 SOC 시계열을 "
    "나르지 않는다(`DispatchResult` 는 매체 4종과 미충족 계열뿐 · "
    "`SystemDispatch` 는 자원별 결과와 계통 수·송전뿐이다). 충·방전에서 "
    "**역산해 그리지 않았다** — 초기 SOC 와 효율 배분 규약은 자원 안에 있고 "
    "표시 층이 그것을 가정하면 지어낸 수가 된다. 지금 실을 수 있는 것은 위 "
    "「저장장치 충전」·「저장장치 방전」 두 열이며, 그 둘은 실행이 실제로 "
    "주고받은 양이다"
)

#: 구성별(일반용 전력·히트펌프·전기차) 시간 형상의 자리 — 역시 **글자로** 적는다.
#:
#: ## 실물로 확인한 것
#:
#: `core/casegrid/e2e_runner.py::run_single_case_e2e` 의 인자가
#: **`extra_appliance_load_kwh: float` — 합계 하나**이고, 그 파일이 스스로 적었다:
#: *「⚠ 인자를 기기별로 쪼개지 않았다 — 쪼개면 러너가 기기 목록을 알게 되고
#: 셋째 기기가 오는 날 시그니처가 늘어난다. 갈래는 산출물에서만 갈린다」*.
#: 히트펌프와 전기차는 `resolve_appliance_loads()` 를 지나 **합계로** 러너에
#: 도착하고, 부하 자원은 그 합계 하나로 세워진다.
#: ⇒ **하루 안에서** 셋을 갈라 인쇄할 재료가 없다. ⛔ 비율로 쪼개 그리면 판정
#: §4-4 가 금한 「만들어 낸 결과」다. 지금 있는 가장 가까운 답은 **계절 몫**이며
#: 1단계가 그것을 싣는다(냉난방 계절 몫 · `ApplianceSeasonShares`).
APPLIANCE_SHAPE_NOT_CARRIED = (
    "- **일반용 전력·히트펌프·전기차의 «시간대별» 갈래 — 미산출.** 러너가 그 "
    "셋을 **합계 하나**로 받는다(`core/casegrid/e2e_runner.py` 의 "
    "`extra_appliance_load_kwh` — 그 파일이 *「인자를 기기별로 쪼개지 않았다」*"
    "라고 적었다). 그래서 위 「총부하」 열은 셋이 **합쳐진 뒤**의 값이고, 하루 "
    "안에서 되돌릴 수 없다. **비율로 쪼개 그리지 않았다** — 없는 갈래를 "
    "지어내는 것이기 때문이다. 지금 있는 가장 가까운 답은 **1단계가 싣는 냉난방 "
    "계절 몫**이며, 그것은 계절 사이의 갈래이지 하루 안의 갈래가 아니다"
)

#: 대조가 어긋났을 때의 태도 — **맞춰 놓지 않는다.**
RECONCILIATION_NOTE = (
    "- 대조가 어긋나면 **맞춰 놓지 않고 그대로 인쇄한다** — 어긋남은 하루 표와 "
    "계절 연간값이 서로 다른 실행을 보고 있다는 뜻이고, 어느 쪽이 옳은지는 이 "
    "표가 정하지 않는다. 오른쪽 「그 계절 연간값」은 **러너가 이미 곱해 실어 온 "
    "값**(`SeasonRun`)이며 표시 층이 다시 곱한 것이 아니다"
)

#: 대조 표에서 저장장치 행의 이름 — 충전·방전 **두 열의 순액**이다.
#:
#: ⚠ 두 열을 따로 대조할 수 없다. `SeasonRun.per_resource_annual_kwh` 가 나르는
#: 것은 그 계절의 **순액 하나**이고(부호 규약 그대로), 충전과 방전을 갈라 나르는
#: 칸이 없다. 순액으로 대조하면서 그 사실을 이름에 적어 둔다 — 「충전이 대조되지
#: 않았다」와 「대조를 뺐다」가 구별돼야 한다.
STORAGE_NET_HEAD = "저장장치 순(방전에서 충전을 뺀 값)"


def _label_map(report: CaseReport) -> dict[str, str]:
    """조인 키 → 인쇄할 글자. 규칙은 `resource_label()` 하나가 갖는다."""
    kinds = {line.name: line.kind for line in report.basis.resources}
    names = {name for hour in report.dispatch_hours for name in hour.per_resource}
    return {name: resource_label(name, kinds) for name in names}


def _who(names: Sequence[str], labels: Mapping[str, str]) -> str:
    """그 갈래에 든 자원들 — **비면 「해당 자원 없음」**이며 빈칸이 아니다."""
    return " · ".join(labels.get(name, f"`{name}`") for name in names) or (
        "해당 자원 없음"
    )


def _pairing_line(
    generation: Sequence[str],
    storage: Sequence[str],
    load: Sequence[str],
    labels: Mapping[str, str],
) -> str:
    """★★ **어느 열이 어느 자원인가** — 표 위에 한 줄로 적는다.

    ⚠ 이 줄이 없으면 「발전」 열이 무엇의 발전인지 산출물만 보고 알 수 없고,
    가름이 어긋난 날(저장장치가 부하 열에 섞이는 등) 그 사실이 **보이지 않는다.**
    열 이름을 자원 이름으로 갈아 쓰지 않는 이유는 같은 종류 자원이 둘인 실행에서
    열 이름이 겹치기 때문이다(`resource_label()` 의 ⛔ 절).
    """
    return (
        f"- **열과 자원의 짝짓기** — 「{LOAD_HEAD}」 ← {_who(load, labels)} · "
        f"「{GENERATION_HEAD}」 ← {_who(generation, labels)} · "
        f"「{STORAGE_CHARGE_HEAD}·{STORAGE_DISCHARGE_HEAD}」 ← "
        f"{_who(storage, labels)}. 가름은 **이름이 아니라 부호**가 한다"
        "(`core/report/dispatch_notes.py::split_three_ways` — 전 스텝 0 이상이면 "
        "발전 · 0 이하면 부하 · 둘을 함께 하면 저장장치). 이름으로 가르면 자원이 "
        "늘 때마다 이 자리를 고쳐야 하고, 고치지 않으면 그 자원이 조용히 0 이 된다"
    )


def _absent_role_lines(
    generation: Sequence[str], storage: Sequence[str], load: Sequence[str]
) -> list[str]:
    """자원이 셋이 아닌 실행 — **없는 열을 0 으로 세우지 않고 그렇게 적는다.**

    ⚠ 0 열을 스물넷 인쇄하면 *「그 설비가 있는데 하루 종일 안 움직였다」* 로
    읽힌다. 열을 빼는 것만으로도 「빠뜨렸다」와 구별되지 않으므로 **둘을 함께**
    한다 — 열은 세우지 않고 사유는 글자로 남긴다.
    """
    absent = [
        (LOAD_HEAD, load, "부하 자원"),
        (GENERATION_HEAD, generation, "발전 자원"),
        (f"{STORAGE_CHARGE_HEAD}·{STORAGE_DISCHARGE_HEAD}", storage, "저장장치"),
    ]
    return [
        f"- 「{head}」 열 — **세우지 않았다**: 이 실행에 {what}이 없다. 0 으로 "
        "채우면 「있는데 안 움직였다」로 읽히므로 열을 세우지 않고 그 사실을 "
        "여기 적는다"
        for head, names, what in absent
        if not names
    ]


def _reconciliation_rows(
    season: SeasonRun,
    hours: tuple[DispatchHour, ...],
    generation: Sequence[str],
    storage: Sequence[str],
    load: Sequence[str],
) -> list[tuple[str, float, float]]:
    """대조할 (항목, 하루 합계, 그 계절 연간값) — **연간값은 `SeasonRun` 에서 읽는다.**

    ⚠⚠ **오른쪽을 여기서 곱해 만들지 않는다.** 계절마다 다른 일수를 곱하는 것이
    계절 축이 여는 것 그 자체이고 러너가 이미 그 곱을 해 실어 왔다
    (`SeasonRun.per_resource_annual_kwh` 등). 표시 층이 다시 곱하면 왼쪽과
    오른쪽이 **같은 계산의 두 사본**이 되어 대조가 아무것도 재지 않는다 —
    `dispatch_sections.py::_season_annual_table` 의 ⚠ 가 같은 판단을 적었다.

    ⚠ 없는 키는 `0.0` 으로 읽는다 — 그러면 대조가 **어긋남으로 인쇄되어**
    보이게 된다. 예외를 던지면 산출물이 통째로 서지 않는다.
    """
    def daily(names: Sequence[str], *, sign: float) -> float:
        return sign * sum(
            hour.per_resource.get(name, 0.0) for hour in hours for name in names
        )

    def annual(names: Sequence[str], *, sign: float) -> float:
        return sign * sum(
            season.per_resource_annual_kwh.get(name, 0.0) for name in names
        )

    rows: list[tuple[str, float, float]] = []
    if load:
        rows.append((LOAD_HEAD, daily(load, sign=-1.0), annual(load, sign=-1.0)))
    if generation:
        rows.append((
            GENERATION_HEAD,
            daily(generation, sign=1.0),
            annual(generation, sign=1.0),
        ))
    if storage:
        rows.append((
            STORAGE_NET_HEAD,
            daily(storage, sign=1.0),
            annual(storage, sign=1.0),
        ))
    rows += [
        (
            GRID_IMPORT_HEAD,
            sum(hour.grid_import for hour in hours),
            season.grid_import_annual_kwh,
        ),
        (
            GRID_EXPORT_HEAD,
            sum(hour.grid_export for hour in hours),
            season.grid_export_annual_kwh,
        ),
    ]
    return rows


def _reconciliation_table(
    season: SeasonRun,
    hours: tuple[DispatchHour, ...],
    generation: Sequence[str],
    storage: Sequence[str],
    load: Sequence[str],
) -> list[str]:
    """★ 계절 표 아래 **대조** — 세 수를 다 보인다 (검토서 §3.4 마지막 문단).

    ⚠ 단위를 제목과 열 머리에 함께 적는다(검토서 §4.2) — 한 절에 **하루 표와
    연간 표가 나란히** 서므로, 없으면 독자가 어느 수가 하루이고 어느 수가 한
    해인지 되짚어야 한다.
    """
    lines = [
        f"{season.name} 대조 — 하루 합계에 그 계절 일수를 곱한 값이 "
        "**그 계절 연간값**과 같은가:",
        "",
        "| 항목 | 하루 합계 (kWh/일) | 계절 일수 (일) "
        "| 하루 합계에 일수를 곱한 값 (kWh/년) | 그 계절 연간값 (kWh/년) | 대조 |",
        "|---|---|---|---|---|---|",
    ]
    for head, day_total, annual_value in _reconciliation_rows(
        season, hours, generation, storage, load
    ):
        product = day_total * season.days
        gap = product - annual_value
        # ⚠ 절대 허용오차만 쓰면 10만 kWh 규모에서 배정 정밀도에 걸린다 —
        # 그러면 **옳은 실행이 어긋남으로 인쇄된다.** 규모에 따라 늘린다.
        tolerance = max(ENERGY_TOLERANCE_KWH, abs(annual_value) * 1e-9)
        verdict = "같다" if abs(gap) <= tolerance else f"**어긋남 {gap:,.4f}**"
        lines.append(
            f"| {head} | {day_total:,.2f} | {season.days} | {product:,.2f} "
            f"| {annual_value:,.2f} | {verdict} |"
        )
    lines.append("")
    return lines


def season_step_tables(report: CaseReport) -> list[str]:
    """★★★ 3단계 ⓑ 맨 뒤 — **계절마다 하루 스텝 전건 + 대조** (검토서 §3.4).

    ## ⚠ 계절이 서지 않은 실행에서는 **아무것도 세우지 않는다**

    그 갈래의 문장은 부르는 쪽(`core/report/verification_inputs.py::
    season_lines`)이 이미 갖고 있다 — *「계절이 서지 않았다 — 형상 자산 없이
    도는 실행이라 대표일 한 벌뿐이다」*. 여기서 같은 사유를 다시 지으면 산출물이
    한 사실을 두 번 말하고, 문면이 갈리는 날 어느 쪽이 정본인지 알 수 없다.

    ## ⚠⚠ 가름은 **연간등가 하루로 한 번**만 한다

    계절마다 다시 가르면 그 계절에 충전만 한 저장장치가 「부하」로 떨어져
    총부하에 섞인다(`split_three_ways()` 의 ⚠⚠). 한 번 가른 결과를 계절 전부에
    쓰면 열이 서로 같아 **검토자가 계절을 위아래로 맞대 볼 수 있다.**

    ## ⚠ 계절 사이를 이어 그리지 않는다

    계절 넷은 **같은 하루를 네 번** 그린 것이지 96시간이 이어진 것이 아니다 —
    그래서 표를 계절마다 따로 세우고 제목에 그 계절의 일수를 적는다
    (`core/report/charts/seasonal_operation.py` 가 그림에서 같은 판단을 한다 —
    계절 사이에 칸막이를 세운다).
    """
    seasons = report.seasons
    if not seasons:
        return []
    profiles = [build_hourly_profile(season.dispatch) for season in seasons]
    head = [
        "",
        "**계절별 하루 스텝 운전 — 부호를 읽지 않고 읽는 표** (검토서 §3.4·§4.3)",
        "",
    ]
    if not all(profiles):
        empty = " · ".join(
            season.name
            for season, hours in zip(seasons, profiles, strict=True)
            if not hours
        )
        return [
            *head,
            f"- 계절별 스텝 표 미산출 — 스텝이 0인 계절이 있다 ({empty}). 빈 표를 "
            "세우면 「그 계절은 아무 일도 하지 않았다」로 인쇄된다",
        ]

    generation, storage, load = split_three_ways(report.dispatch_hours)
    labels = _label_map(report)
    columns = human_step_columns(generation, storage, load)
    lines = [
        *head,
        "⚠ 위 두 표는 그 계절이 **한 해에** 보태는 몫이고, 아래는 그 계절 "
        "**대표일 하루**다. 단위는 표 제목과 열 머리가 진다.",
        "",
        _pairing_line(generation, storage, load, labels),
        *_absent_role_lines(generation, storage, load),
        SOC_NOT_CARRIED,
        APPLIANCE_SHAPE_NOT_CARRIED,
        RECONCILIATION_NOTE,
        "",
    ]
    for season, hours in zip(seasons, profiles, strict=True):
        lines += [
            f"**{season.name} — 대표일 {len(hours)}스텝** (연 {season.days}일 · "
            "단위 kWh/스텝)",
            "",
            *step_table(hours, columns, step_head="시각"),
            *_reconciliation_table(season, hours, generation, storage, load),
        ]
    return lines
