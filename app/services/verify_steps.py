"""검증 모드 — 렌더러의 9단계를 **사용자의 네 걸음 위에 얹는다**.

## ★★★ 이 파일이 새로 계산하지 않는 이유

중간값을 단계별로 늘어놓는 렌더러는 **이미 있다** —
`core/report/verification.py::render_verification_markdown` 이 9단계를 내고,
각 단계가 「ⓐ 전제값 → ⓑ 계산값 → ⓒ 다음 단계로 넘긴 값 → ⓓ 계산 수식」을
싣는다. 못 하던 것은 계산이 아니라 **화면에 붙이는 것**이었다: 그 함수를
부르는 곳이 `app/run/report_cli.py`(CLI `--kind verification`) 하나뿐이었다.
이 저장소가 반복해 밟은 *「부품은 있는데 부르는 배포 코드가 없다」* 와 같은
형태다(`core/report/case_report.py` 머리말이 R33 에 같은 사고를 적는다).

⇒ **같은 것을 두 번 계산하지 않는다.** 여기서 4단계 화면을 새로 계산해 지으면
통로가 둘이 되고, 그때 산출물만 봐서는 어느 쪽이 이겼는지 알 수 없다 —
`app/services/ui_run.py` 머리말과 `core/casegrid/models.py::CashflowSplit` 이
같은 판단을 이미 두 번 적어 두었다.

## 이 파일이 하는 일 — **가르고 묶는 것뿐이다**

    렌더러 markdown  →  ① 단계 경계에서 가른다(정규식 하나)
                     →  ② 사용자의 네 걸음으로 묶는다
                     →  ③ 재료가 없는 자리에 「빈 칸 + 사유」를 세운다

⛔ **markdown 라이브러리를 쓰지 않는다.** `markdown`·`markdown_it` 이 이
기계에 깔려 있으나 `pyproject.toml` 에 **선언돼 있지 않다**(전이 의존이다).
선언 안 된 의존을 쓰면 `pip install -e ".[api]"` 만 한 배포 환경에서 화면이
죽는다 — 그 파일 주석이 `jinja2` 로 **이미 그 사고를 겪었다**고 적는다.
그래서 아는 것은 **「단계 경계」 하나뿐**이고 본문은 고정폭으로 그대로 싣는다.
표·목록·굵게를 해석하기 시작하면 이 파일이 변환기가 되고, 변환기는 렌더러가
문법을 늘리는 날 낡는다.

## ⚠⚠ 화면에 나가는 문자열에 **markdown 표기를 쓰지 않는다**

아래 사유·캡션·이어짐 문면은 템플릿이 `<p>` 안에 그대로 싣는다. 이 화면은
markdown 을 해석하지 않으므로 `**굵게**` 의 별표와 코드 표기의 백틱이 **글자
그대로 인쇄된다** — 실제로 그렇게 나가는 것을 응답 HTML 에서 보고 고쳤다.
⇒ 강조가 필요하면 문장으로 하고, 자료형·필드 이름은 백틱 없이 그대로 적는다.
(단계 본문은 다르다 — 그것은 렌더러의 markdown 을 **고정폭 원문 그대로** 보이는
자리이므로 표기가 남아 있는 것이 맞다.)

## ⚠⚠ 단계가 9로 갈리지 않으면 **멈춘다**

렌더러가 단계를 늘리는 날 화면이 조용히 여덟만 그리면 사용자는 없는 단계를
찾을 때까지 모른다. `core/model/parameters.py::ParameterCatalogueError` 가 같은
판단을 적어 두었다 — *「아는 것만 돌려주는 쪽을 고르면 … 그 상태로 검사는
전부 초록불이다」*.

## ⚠ 재료가 없는 자리를 **지우지 않는다**

사용자가 든 네 걸음 중 일부는 이 저장소에 재료가 없다(`.orch/R63/
result_P4.md` §7 이 다섯을 이름으로 못 박았다). 단계를 조용히 빼면 사용자가
요구한 것이 화면에서 사라지고, **사라진 것은 아무도 못 본다.** 그래서 네
걸음을 다 세우고 못 그리는 칸만 **사유를 글자로** 채운다 — R62 가 차트 둘에
`501` 로 한 것과 같은 답이다(착수 순서 41번).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.report._format import _num
from core.report.case_report import CaseReport
from core.report.verification import render_verification_markdown

#: 렌더러가 내는 단계 수. **여기서 정하는 값이 아니라 렌더러와 맞춰야 하는
#: 값**이며, 어긋나면 `split_stages` 가 멈춘다(위 머리말 ⚠⚠).
STAGE_COUNT = 9

#: 단계 경계. `core/report/verification.py::_stage` 가 짓는 머리글 그대로다 —
#: ``## 3단계 — 대표일 운전(디스패치)``. **이 한 줄이 이 파일이 아는 markdown
#: 문법의 전부다.**
_STAGE_HEADING = re.compile(r"^## (\d+)단계 — (.+)$", re.MULTILINE)

#: 단계 본문 끝에 붙는 절 구분선. 렌더러가 단계 사이에 ``---`` 을 넣는다.
_TRAILING = ("---", "")


class VerificationStageError(Exception):
    """검증 보고서를 단계로 가르지 못했다 — 화면을 내지 않는다."""


@dataclass(frozen=True)
class VerifyStage:
    """렌더러 단계 하나 — 번호·제목·본문(markdown 원문 그대로)."""

    number: int
    title: str
    body: str


@dataclass(frozen=True)
class VerifyGap:
    """**값이 서지 않는 칸** — 빈 칸과 그 사유.

    ⚠ `reason` 은 화면에 **글자로** 나간다. 비워 두면 「없음」과 「빠뜨림」이
    구별되지 않는다(`core/report/_format.py::NO_VALUE` 가 같은 사유를 적는다).
    """

    tag: str
    title: str
    reason: str


@dataclass(frozen=True)
class VerifyFill:
    """**값이 선 칸** — 재료가 도착해 「빈 칸 + 사유」를 대신한 자리 (R64/WP-1).

    ## ★★ 왜 `VerifyGap` 을 「채운 칸」으로 겸용하지 않는가

    빈 칸은 *「왜 없는가」* 를 싣고 채운 칸은 *「무엇이며 어디서 왔는가」* 를
    싣는다 — 같은 자료형에 두 뜻을 담으면 화면이 `data-filled` 하나로 갈리고,
    그때 *「사유가 비었다」* 와 *「값이 비었다」* 를 검사가 구별하지 못한다.
    ⇒ 자료형을 갈라 두면 빈 칸 검사(`tests/app/test_ui_verify.py::
    test_blank_cells_print_no_number`)가 **채운 칸을 세지 않는다.**

    ⚠ `note` 는 *「이 수가 어디서 왔는가」* 다. 값만 인쇄하면 검토자가 그 수를
    저장소가 정한 것으로 읽고, 실제로는 **실행 입력이 정한 것**이다.
    """

    tag: str
    title: str
    value: str
    note: str


@dataclass(frozen=True)
class NetDemandRow:
    """순수요 표의 한 행 — `DispatchHour` 를 **읽기만** 한 것."""

    step: int
    per_resource: tuple[str, ...]
    grid_export: str
    grid_import: str


@dataclass(frozen=True)
class VerifyGroup:
    """사용자가 든 걸음 하나 — 그 안에 실린 렌더러 단계와 빈 칸."""

    number: int
    title: str
    #: 앞 걸음의 산출이 이 걸음의 입력임을 적는 글자. 첫 걸음은 비어 있다.
    carried_from: str
    stages: tuple[VerifyStage, ...]
    gaps: tuple[VerifyGap, ...]
    #: 재료가 도착해 **값이 선** 칸 (R64/WP-1). 빈 칸과 같은 걸음에 나란히
    #: 설 수 있다 — ①의 「가구 수·가구 유형」이 그렇다(수는 서고 유형은 없다).
    fills: tuple[VerifyFill, ...] = ()
    #: ③ 순수요만 갖는다 — 아래 `net_demand_rows` 참조.
    net_demand: tuple[NetDemandRow, ...] = ()
    net_demand_caption: str = ""
    net_demand_columns: tuple[str, ...] = ()


def split_stages(markdown: str) -> tuple[VerifyStage, ...]:
    """검증 보고서 markdown 을 **단계 경계에서만** 가른다.

    ⚠ 본문은 손대지 않는다 — 화면이 고정폭으로 그대로 싣는다. 검증 모드는
    수를 따라가며 대조하는 화면이고, 그 목적에는 렌더러가 맞춘 표 정렬이
    변환된 HTML 표보다 낫다.

    단계가 `STAGE_COUNT` 로 갈리지 않거나 번호가 1..N 순서가 아니면
    `VerificationStageError` 를 던진다 — **조용히 일부만 그리지 않는다.**
    """
    matches = tuple(_STAGE_HEADING.finditer(markdown))
    if len(matches) != STAGE_COUNT:
        raise VerificationStageError(
            f"검증 보고서가 {STAGE_COUNT}단계로 갈리지 않았다 — "
            f"{len(matches)}개를 찾았다. `core/report/verification.py` 가 단계를 "
            "늘렸거나 머리글 서식을 바꿨다. 화면이 일부만 그리면 사용자는 없는 "
            "단계를 찾을 때까지 모르므로 여기서 멈춘다"
        )
    stages: list[VerifyStage] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        stages.append(
            VerifyStage(
                number=int(match.group(1)),
                title=match.group(2).strip(),
                body=_trim(markdown[match.start() : end]),
            )
        )
    numbers = [stage.number for stage in stages]
    if numbers != list(range(1, STAGE_COUNT + 1)):
        raise VerificationStageError(
            f"단계 번호가 1..{STAGE_COUNT} 순서가 아니다: {numbers}"
        )
    return tuple(stages)


def _trim(section: str) -> str:
    """단계 본문 끝의 절 구분선과 빈 줄을 뗀다 — **글자는 고치지 않는다.**"""
    lines = section.rstrip().split("\n")
    while lines and lines[-1].strip() in _TRAILING:
        lines.pop()
    return "\n".join(lines)


def net_demand_rows(report: CaseReport) -> tuple[NetDemandRow, ...]:
    """③ 전력순수요 — `dispatch_hours` 를 **읽어** 스텝별로 편다.

    ⚠⚠ **화면이 뺄셈을 다시 하지 않는다.** 순수요는 계산해야 얻는 값이 아니라
    `DispatchHour.grid_import` **필드 그 자체**다(`.orch/R63/result_P4.md` §1).
    여기서 부하 − 자가공급을 다시 빼면 통로가 둘이 되고, 엔진의 배분 규칙이
    바뀌는 날 화면만 옛 뺄셈을 그럴듯하게 계속 인쇄한다.

    ⚠ 자원 열 이름을 손으로 적지 않는다 — `per_resource` 의 키에서 얻는다.
    적으면 자원이 늘어도 화면이 영영 둘만 그린다.
    """
    hours = report.dispatch_hours
    columns = net_demand_columns(report)
    return tuple(
        NetDemandRow(
            step=hour.step,
            per_resource=tuple(
                _num(hour.per_resource[name]) if name in hour.per_resource else "—"
                for name in columns
            ),
            grid_export=_num(hour.grid_export),
            grid_import=_num(hour.grid_import),
        )
        for hour in hours
    )


def net_demand_columns(report: CaseReport) -> tuple[str, ...]:
    """순수요 표의 자원 열 — 모든 스텝의 키 합집합을 정렬한 것."""
    names: set[str] = set()
    for hour in report.dispatch_hours:
        names.update(hour.per_resource)
    return tuple(sorted(names))


#: ③ 순수요 표의 캡션.
#:
#: ⚠⚠ **「대표일 하루」임을 글자로 적는다.** 안 적으면 24행짜리 표가
#: 「계절 변동이 없다」를 **결과로 주장한다** — 착수 순서 41번이
#: `energy_balance` 차트에서 만난 바로 그 함정이며, 그래서 그 차트는 지금
#: `501` 로 서 있다.
#: ⚠⚠ **R64/WP-4 가 이 캡션의 전제를 고쳤다.** 종전 문면은 *「계절·요일 변동을
#: 반영하지 않으므로 … (착수 순서 36번이 선행이다)」* 였는데, **그 앞 절이
#: 거짓이 됐다** — 계절은 운전에 반영된다(계절 넷의 대표일을 각각 돌려
#: 계절일수로 가중 합산한다). 뒤 절(*「이 표를 「계절 변동이 없다」로 읽으면
#: 안 된다」*)은 **여전히 참이고 여전히 중요하다**: 이 표가 그리는 24행은
#: 계절을 일수로 가중 평균한 한 벌이라 화면에서 계절이 보이지 않는다.
#: 그래서 경고는 남기고 근거만 바꾼다.
_NET_DEMAND_CAPTION = (
    "계절 넷의 대표일을 각각 24스텝(1시간 간격)으로 모의해 계절일수로 가중 "
    "합산한 결과이며, 이 표에 그리는 24행은 그것을 일수로 가중 평균한 "
    "「연간등가 하루」다 — 운전은 계절을 반영하지만 **이 표는 계절을 갈라 "
    "보여주지 않으므로** 「계절 변동이 없다」로 읽으면 안 된다(계절별 화면은 "
    "아직 없다 · 요일 변동은 운전에서도 미반영이다). 값의 출처는 "
    "CaseReport.dispatch_hours[] 이며 순수요는 grid_import 필드 그 자체다 "
    "— 화면이 부하에서 자가공급을 다시 빼지 않는다."
)


#: ①의 「가구 수·가구 유형」 칸의 이름. **두 갈래가 같은 이름을 쓴다** —
#: 가구 수를 안 준 실행에서는 「칸 + 사유」이고, 준 실행에서는 수가 서고 사유가
#: **가구 유형만** 남는다(R64/WP-1 · 착수 47ⓐ).
#:
#: ⚠ 이름을 갈래마다 다르게 두면 `GAP_TAGS` 가 실행에 따라 달라지고, 그때
#: 「빈 칸 목록이 다르다」를 재는 검사가 무엇을 세는지 알 수 없게 된다.
HOUSEHOLDS_TAG = "households"

#: **값이 서지 않는 다섯 칸** — `.orch/R63/result_P4.md` §7 이 이름으로 못 박은
#: 것들이다. 여기 적힌 사유가 화면에 그대로 나간다.
#:
#: ⚠ **하나라도 지우지 마라.** 지우면 사용자가 요구한 것이 화면에서 사라지고,
#: 사라진 것은 아무도 못 본다. 재료가 생기면 그때 이 칸을 값으로 바꾼다.
_GAPS: tuple[tuple[int, VerifyGap], ...] = (
    (
        1,
        VerifyGap(
            tag=HOUSEHOLDS_TAG,
            title="기존 전기사용자 정보 — 가구 수 · 가구 유형",
            reason=(
                "이 실행은 가구 수를 받지 않았다. 그래서 아래 모든 수량과 "
                "금액은 가구 한 호를 계산한 것이며, 단지 전체의 값이 아니다 — "
                "분석 설정 대장이 부하를 「kWh/호·년」 단위로 갖기 때문이다. "
                "화면의 「가구 수」 칸에 세대 수를 넣으면 이 자리에 그 수가 "
                "서고 단지 총부하가 그만큼 커진다. 저장소가 그 수를 스스로 "
                "채우지 않는 이유는 세대 수가 사업 계획이 정하는 사실이기 "
                "때문이다 — 여기에 「30세대 단지」 같은 수를 적으면 그것은 "
                "지어낸 값이며 심의 자료가 된다. 가구 유형(세대원 수·주택 "
                "형태 등 부하 형상을 가르는 축)은 값도 자료형도 아직 없다. "
                "(착수 순서 47ⓐ)"
            ),
        ),
    ),
    (
        1,
        VerifyGap(
            tag="seasonal_operation",
            title="가구별 전력소비패턴(계절별) — 계절이 가른 운전 결과",
            # ★★ **R64/WP-4 가 사유를 갈아 끼웠다 — 칸은 닫지 않았다.**
            # 종전 사유는 *「배포 실행이 몫 가중 평균 대표일 한 벌로 접어 쓴다 …
            # 계절별 결과는 존재하지 않는 수다」* 였고, 러너가 계절 넷을 각각
            # 돌리게 된 지금 **그 문면은 통째로 거짓**이다. 그런데 칸을 닫으면
            # 화면이 *「계절별 결과를 보여준다」* 를 주장하게 되는데 **아직 못
            # 보여준다** — 계산이 선 것과 화면이 그리는 것은 다른 일이고,
            # 그리는 것은 다음 자리의 몫이다. 그래서 **칸은 남고 사유가 바뀐다**
            # (위 `_HOUSEHOLD_TYPE_ONLY` 가 「지우지 않고 좁힌」 것과 같은 태도다).
            reason=(
                "계절 넷의 대표일을 각각 돌려 계절일수로 가중 합산하는 운전은 "
                "이제 선다(착수 순서 36번 · 계절 간 하루 차이가 결론에 반영된다). "
                "**아직 없는 것은 화면이다** — 이 검증 절차가 계절별 소비·발전·"
                "수전을 갈라 그리지 않으므로, 여기 서 있는 표와 수는 전부 "
                "계절을 일수로 가중 평균한 「연간등가 하루」의 것이다. 계절별 "
                "수치·도표를 세우는 것이 남은 일이며, 재료는 이미 산출물에 "
                "실려 있다(`CaseReport.seasons` — 계절마다 이름·일수·그 하루의 "
                "운전·그 계절 연간 기여). ⚠ 계절 몫·형상 자체는 여전히 자산의 "
                "**가정값**이라 실측이 오면 결론이 다시 움직인다. 「가구별」 "
                "분해는 위 가구 수 칸과 같은 사유로 따로 없다."
            ),
        ),
    ),
    (
        1,
        VerifyGap(
            tag="progressive_tariff",
            title="전력요금 — 누진 구간 · 시간대(TOU) 요금표",
            reason=(
                "누진·시간대 요금 엔진은 저장소에 있으나 배포 리포트 경로에 "
                "서지 않는다 — 이 실행이 쓴 요금이 아니다. 구간표를 화면에 "
                "그리면 계산에 쓰이지 않은 표가 근거처럼 보인다. 이 실행이 "
                "실제로 쓴 단가와 그 출처·신뢰도는 위 1단계 대장 표에 그대로 "
                "있다. (착수 순서에 아직 번호가 없는 새 항목)"
            ),
        ),
    ),
    (
        3,
        VerifyGap(
            tag="monthly",
            title="월별 전력순수요 · 월별 에너지 수지",
            reason=(
                "월별 시계열이 CaseReport 에 없다 — 운전 해상도가 대표일 "
                "24스텝 하나여서 열두 달을 가를 자료가 없다. 대표일을 12로 펴면 "
                "열두 달이 같은 막대가 되고, 그 그림은 「계절 변동이 없다」를 "
                "결과로 주장한다. 같은 사유로 energy_balance 차트가 "
                "착수 순서 41번에서 501 로 서 있다."
            ),
        ),
    ),
    (
        4,
        VerifyGap(
            tag="benefit_by_tag_by_year",
            title="편익 항목별 연차 시계열 — 어느 편익이 몇 년차에 얼마인가",
            reason=(
                "편익 현금흐름은 연차 20개를 갖되 행이 하나(E2EBenefit)다 "
                "— 러너가 다섯 편익을 한 행으로 합쳐 낸다. 항목별 분해는 "
                "1년차에만 있으므로(위 4단계 표 5행) 「어느 편익이 몇 년차에 "
                "얼마인가」는 그릴 수 없다. ⚠ 1년차 분해를 20년으로 되짚어 "
                "채우지 않는다 — 운영비는 연 2% 오르고 편익은 평탄이라 되짚은 "
                "표는 실제 장부와 어긋난다. 총액 20연차는 아래 7단계에 그대로 "
                "있다. (착수 순서에 아직 번호가 없는 새 항목)"
            ),
        ),
    ),
)

#: 화면이 세우는 빈 칸의 이름 — 검사가 **전건**을 세는 데 쓴다.
GAP_TAGS: tuple[str, ...] = tuple(gap.tag for _, gap in _GAPS)

#: ★★ **가구 수가 지정된 실행**에서 위 「가구 수·가구 유형」 칸을 대신하는 것.
#: 수는 `_household_count_fill` 이 값으로 세우고, **유형은 여전히 없다** —
#: 그래서 칸이 사라지지 않고 **좁아진다**(R64/WP-1 · 착수 47ⓐ).
#:
#: ⚠⚠ **칸을 통째로 지우지 않는다.** 지우면 사용자가 요구한 「가구 유형」이
#: 화면에서 사라지고, 사라진 것은 아무도 못 본다 — 이 파일 머리말의 ⚠ 가
#: 적은 그대로다. 대장의 `load.household.type_mix` 는 아직 `track: blocked` ·
#: `value: null` 이며 **표현할 자료형조차 정해지지 않았다**.
_HOUSEHOLD_TYPE_ONLY = VerifyGap(
    tag=HOUSEHOLDS_TAG,
    title="기존 전기사용자 정보 — 가구 유형",
    reason=(
        "가구 수는 이 실행이 받았고 위 칸에 서 있다. 남은 것은 가구 "
        "유형이다 — 세대원 수·주택 형태·난방 방식 중 무엇으로 가를지가 "
        "아직 정해지지 않아 값도 자료형도 없다. 그래서 이 실행은 모든 "
        "가구를 같은 한 벌의 소비 형상으로 돌렸고, 「가구별」 소비패턴은 "
        "가를 재료가 없다. 여기에 유형 구성을 적으면 그것은 지어낸 값이며 "
        "심의 자료가 된다. (착수 순서 47ⓐ)"
    ),
)


def _household_count_fill(count: int) -> VerifyFill:
    """①의 「가구 수」 칸 — **값이 선** 자리 (R64/WP-1 · 착수 47ⓐ).

    ⚠ **수를 여기서 짓지 않는다.** `CaseReport.household_count` 를 서식만
    입혀 옮긴 것이며, 그 값은 실행 입력(시나리오 yaml 의 `household_count`
    필드)이 정한 것이다 — 저장소가 고른 수가 아니라는 사실을 `note` 가
    글자로 적는다.
    """
    return VerifyFill(
        tag=HOUSEHOLDS_TAG,
        title="기존 전기사용자 정보 — 가구 수",
        value=f"{count:,}호",
        note=(
            "이 수는 실행 입력이 정했다 — 저장소가 가진 값이 아니다. 분석 "
            "설정 대장은 부하를 「kWh/호·년」 단위로 갖고, 단지 총부하는 이 "
            "수를 곱한 것이다. 아래 모든 수량과 금액이 그 총부하 위에 선다."
        ),
    )


#: 사용자의 네 걸음 ↔ 렌더러 9단계. **문면은 사용자 판정 §1 「결과」 그대로다.**
#:
#: ⚠ 3단계(운전)는 ② 「전력공급패턴」으로 **한 번만** 싣는다. ③ 은 같은 운전
#: 결과의 `grid_import` 를 스텝별로 펴는 자리이므로 본문을 두 벌 인쇄하지 않고
#: **이어짐 문단으로 가리킨다** — 두 벌 인쇄하면 어느 쪽이 최신인지 화면만
#: 봐서는 알 수 없다.
#:
#: ⚠⚠ ② 「전력공급비용」(5단계 · 1년차 한 벌)과 ④ 「연차별 비용」(7단계 ·
#: 연차 1~20)을 **같은 표로 합치지 않는다.** 합치면 물가·교체·잔존이 1년차
#: 값에 눌려 사라진다 — 앞의 것은 설비의 단가표이고 뒤의 것은 사업자의 20년
#: 장부다.
#:
#: ★★★ **4단계(편익 화폐화)는 ④ 에 싣는다.** 오케스트레이터가 넘긴 대응표
#: (`.orch/R63/WP-S3.md` ⓑ)는 ② 를 2·3·5, ④ 를 6·7·8·9 로 적었고 **4단계가
#: 어느 묶음에도 없었다** — 그대로 따르면 편익 화폐화가 화면에서 통째로
#: 사라진다(검사 `test_all_nine_renderer_stages_are_on_screen` 이 그 상태를
#: 잡았다). 함수를 열어 확인한 결과 `_stage4_benefits` 는 편익 5행의 1년차
#: 금액과 그 산식이며, 사용자의 ④ *「분산e사업자의 연차별 비용, **편익**」*
#: 이 그것을 요구한다. ② 는 **공급비용**의 자리이므로 편익이 갈 곳이 아니다.
#: ⇒ ④ = 4 · 6 · 7 · 8 · 9. 이 판단의 경위는 `.orch/R63/result_S3.md` §9.
#:
#: ## ⚠ 대장을 부르는 이름 — **이 파일이 지은 문면만** R63 낱말표를 따른다
#:
#: 아래 이어짐 문면과 위 `_GAPS` 의 사유는 **이 파일이 직접 쓴 글**이므로
#: 「분석 설정 대장」으로 옮겼다(`docs/decisions-2026-09-05-R63b.md` §1).
#: ⛔ 그러나 **단계 제목·본문은 옮기지 않는다** — 그것은 렌더러가 낸 리포트
#: 문면이고(1단계 제목이 「전제 대장에서 읽은 값」이다) 정본은
#: `core/report/verification.py` 다. 이 파일은 그것을 **가르고 묶을 뿐**이며,
#: 여기서 글자를 고치면 화면이 「렌더러가 낸 문면을 그대로 싣는다」는 이
#: 파일의 약속을 깬다.
#: ⇒ 그래서 아래 이어짐 문면이 가리키는 1단계의 제목과 **낱말이 갈린다.**
#: 갈린 채로 두는 것이 R63 판정이다 — 리포트 인쇄 문면은 이 라운드에서 바꾸지
#: 않고(착수 목록 51번), 렌더러까지 옮기는 것은 별도 라운드의 일이다.
#: 재는 자리는 `tests/app/test_screen_words.py` 이며, 그 검사가 단계 자리를
#: **통째로 걷어 내고** 화면이 지은 글자만 센다.
_GROUP_PLAN: tuple[tuple[int, str, str, tuple[int, ...]], ...] = (
    (
        1,
        "기존 전기사용자 정보 · 가구별 전력소비패턴(계절별) · 전력요금",
        "",
        (1,),
    ),
    (
        2,
        "전기사용자의 전력소비를 만족하기 위한 공급설비 · 전력공급패턴 · 전력공급비용",
        (
            "← ① 의 1단계가 분석 설정 대장에서 읽은 부하·단가·수명·할인율이 이 걸음의 "
            "입력이다. 2단계가 그것으로 자원 목록(용량·운전방식)을 세우고, "
            "3단계 운전이 그 목록을 그대로 받으며, 5단계 운영비가 3단계의 계통 "
            "수전 수량과 1단계의 요금 단가를 함께 쓴다."
        ),
        (2, 3, 5),
    ),
    (
        3,
        "해당 공급설비를 활용할 경우의 전력순수요",
        (
            "← ② 의 3단계 운전 결과에서 온다. 순수요는 부하에서 자가공급"
            "(태양광·ESS)을 뺀 나머지이며, 그 뺄셈의 결과가 "
            "CaseReport.dispatch_hours[].grid_import 다 — 아래 표는 그 "
            "필드를 스텝별로 읽은 것이고 화면이 다시 빼지 않는다. ② 의 3단계는 "
            "같은 운전의 합계를 싣는다."
        ),
        (),
    ),
    (
        4,
        "분산e사업자의 연차별 비용 · 편익",
        (
            "← ② 의 5단계 운영비(1년차)와 ③ 의 순수요(계통 구매량)가 이 걸음의 "
            "연차 장부로 들어간다. 4단계가 ③ 의 운전 수량과 ① 의 단가로 편익을 "
            "화폐로 바꾸고, 6단계가 교체·잔존을 세우고, 7단계가 그 둘을 현금흐름 "
            "행으로 옮기며 1년차 값끼리 대조하고, 8단계가 그 행 전체로 지표를 "
            "내고, 9단계가 지원율 변형을 비교한다. ⚠ ② 의 「전력공급비용」은 물가 "
            "반영 전 1년차 한 벌이고 이 걸음은 물가·교체·잔존을 반영한 "
            "연차 1~20 이다 — 둘을 같은 표로 합치지 않는다."
        ),
        (4, 6, 7, 8, 9),
    ),
)


def build_verify_groups(report: CaseReport) -> tuple[VerifyGroup, ...]:
    """검증 모드 화면이 그릴 것 — **네 걸음에 9단계를 얹은 것**.

    ⚠ 여기서 수를 하나도 짓지 않는다. 단계 본문은 렌더러 문자열 그대로이고,
    순수요 표는 `dispatch_hours` 필드를 서식만 입혀 옮긴 것이다.

    ★★ **①의 「가구 수」는 갈래가 둘이다** (R64/WP-1 · 착수 47ⓐ).
    `report.household_count` 가 `None` 이면 지금까지와 같은 「칸 + 사유」이고,
    수가 있으면 그 수가 **값으로 서고** 사유가 가구 유형만 남는다 — 칸이
    사라지는 것이 아니라 **좁아진다**.
    """
    stages = {stage.number: stage for stage in split_stages(
        render_verification_markdown(report)
    )}
    columns = net_demand_columns(report)
    rows = net_demand_rows(report)
    count = report.household_count
    groups: list[VerifyGroup] = []
    for number, title, carried_from, wanted in _GROUP_PLAN:
        is_net_demand = number == 3
        gaps = tuple(gap for at, gap in _GAPS if at == number)
        fills: tuple[VerifyFill, ...] = ()
        if count is not None:
            # ★ 이름이 같으므로 **자리를 바꿔 끼운다** — 목록에서 빼면
            # `GAP_TAGS` 와 화면의 칸 목록이 갈리고, 그때 「빈 칸 목록이
            # 다르다」를 재는 검사가 무엇을 세는지 알 수 없게 된다.
            gaps = tuple(
                _HOUSEHOLD_TYPE_ONLY if gap.tag == HOUSEHOLDS_TAG else gap
                for gap in gaps
            )
            fills = tuple(
                _household_count_fill(count)
                for gap in gaps
                if gap.tag == HOUSEHOLDS_TAG
            )
        groups.append(
            VerifyGroup(
                number=number,
                title=title,
                carried_from=carried_from,
                stages=tuple(stages[n] for n in wanted),
                gaps=gaps,
                fills=fills,
                net_demand=rows if is_net_demand else (),
                net_demand_caption=_NET_DEMAND_CAPTION if is_net_demand else "",
                net_demand_columns=columns if is_net_demand else (),
            )
        )
    return tuple(groups)
