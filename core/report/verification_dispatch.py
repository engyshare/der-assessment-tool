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

from core.casegrid.models import ResourceLine
from core.report._format import _num
from core.report.case_report import CaseReport
from core.report.dispatch_notes import (
    NO_APPLIED_ALLOCATION,
    applied_allocation,
    declared_operating_mode,
    split_by_direction,
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

    사람용 이름은 `ResourceLine.kind` 하나에서만 온다. `kind` 가 없는 키
    (`e2e-load` — 부하는 `CaseBasis.resources` 에 **없다**)는 **키만** 인쇄한다.
    여기서 이름을 지으면 같은 항목을 부르는 말이 두 곳에서 갈린다.

    ⚠ **화면은 같은 자리를 다르게 적는다** — `app/services/ui_charts.py::
    resource_labels` 는 겹칠 때만 키를 덧붙이고, `kind` 가 없는 키에는
    「가구 전력수요」를 쓴다. 그 낱말은 `app/` 에 있어 이 계층이 import 할 수
    없고(NFR-208 계층 계약), 두 규칙을 한 자리로 모으는 것은 이 WP 의 파일
    밖이다 — 남은 자리다.
    """
    kind = kinds.get(name)
    return f"{kind} (`{name}`)" if kind else f"`{name}`"


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
