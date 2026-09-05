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
_NET_DEMAND_CAPTION = (
    "대표일 하루를 24스텝(1시간 간격)으로 모의한 결과다 — "
    "계절·요일 변동을 반영하지 않으므로 이 표를 「계절 변동이 없다」로 읽으면 "
    "안 된다(착수 순서 36번이 선행이다). 값의 출처는 "
    "CaseReport.dispatch_hours[] 이며 순수요는 grid_import 필드 그 자체다 "
    "— 화면이 부하에서 자가공급을 다시 빼지 않는다."
)


#: **값이 서지 않는 다섯 칸** — `.orch/R63/result_P4.md` §7 이 이름으로 못 박은
#: 것들이다. 여기 적힌 사유가 화면에 그대로 나간다.
#:
#: ⚠ **하나라도 지우지 마라.** 지우면 사용자가 요구한 것이 화면에서 사라지고,
#: 사라진 것은 아무도 못 본다. 재료가 생기면 그때 이 칸을 값으로 바꾼다.
_GAPS: tuple[tuple[int, VerifyGap], ...] = (
    (
        1,
        VerifyGap(
            tag="households",
            title="기존 전기사용자 정보 — 가구 수 · 가구 유형",
            reason=(
                "가구 수와 가구 유형을 적는 자리가 이 저장소에 자료형 수준으로 "
                "없다. 분석 설정 대장은 부하를 「kWh/호·년」 단위로 갖지만 「호」의 "
                "개수를 세는 필드가 없고, CaseReport 어디에도 세대 수가 서지 "
                "않는다. 여기에 「30세대 단지」 같은 수를 적으면 그것은 지어낸 "
                "값이며 심의 자료가 된다. (착수 순서에 아직 번호가 없는 새 항목)"
            ),
        ),
    ),
    (
        1,
        VerifyGap(
            tag="seasonal_operation",
            title="가구별 전력소비패턴(계절별) — 계절이 가른 운전 결과",
            reason=(
                "계절 넷의 형상과 몫은 자산에 선언돼 있으나, 배포 실행이 "
                "그것을 「몫 가중 평균 대표일」 한 벌로 접어 쓴다 — 계절일수가 "
                "약분되어 계절 간 하루 차이가 운전에 남지 않는다. 그래서 "
                "계절별 소비·발전·수전 「결과」는 존재하지 않는 수다. 선행은 "
                "착수 순서 36번(계절 넷의 대표일을 각각 돌리는 운전)이며, "
                "그것을 세우면 결론축이 다시 움직인다. 「가구별」 분해는 위 "
                "가구 수 칸과 같은 사유로 따로 없다."
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
    """
    stages = {stage.number: stage for stage in split_stages(
        render_verification_markdown(report)
    )}
    columns = net_demand_columns(report)
    rows = net_demand_rows(report)
    groups: list[VerifyGroup] = []
    for number, title, carried_from, wanted in _GROUP_PLAN:
        is_net_demand = number == 3
        groups.append(
            VerifyGroup(
                number=number,
                title=title,
                carried_from=carried_from,
                stages=tuple(stages[n] for n in wanted),
                gaps=tuple(gap for at, gap in _GAPS if at == number),
                net_demand=rows if is_net_demand else (),
                net_demand_caption=_NET_DEMAND_CAPTION if is_net_demand else "",
                net_demand_columns=columns if is_net_demand else (),
            )
        )
    return tuple(groups)
