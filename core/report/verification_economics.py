"""검증 **4단계 「경제성 입력」** — 요금 · REC 단가 · 할인율 · 지원율과 대장 전건
(R69/WP-1 · 검토서 §3.1 · §5 · §6-2).

## 왜 새 단계가 생겼나

검토서 §3.1: *「`01-전제 대장에서 읽은 값.md` 는 116행으로 가장 길고, **핵심
수요값과 REC 단가·설비 단가·할인율·정책 가정이 한 파일에 함께 있다**」*. 그리고
§6-2 가 그 조치를 *「수요 단계 분리 — 일반용·HP·EV 의 구성과 산출식을 경제성
입력에서 분리한다」* 로 못 박았다.

⇒ 옛 1단계 하나가 **1「가구 수요」와 4「경제성 입력」으로 갈렸다.** 이 모듈은
뒤쪽의 재료를 갖는다.

## ⚠⚠ 왜 «물리 검증 뒤»인가 — 2·3단계가 이 표의 키를 쓰는데

어긋남이 아니라 **이 배열의 뜻**이다. 검토서 §3.6 · §6-2 가 *「물리 검증이 끝난
뒤에 편익·비용·현금흐름·지표를 계산하는 흐름을 문서와 코드에서 동일하게 한다」*
를 요구했고, 그래서 경제성 «입력»이 용량(2단계)·운전(3단계) **뒤에** 선다.
2·3단계가 실제로 쓰는 부하·설계 행은 **1단계가 부분 표로 먼저** 싣는다.

## ⛔ 대장 전건 표를 주제별로 쪼개지 않는다

이 단계가 *「1 의 나머지」* 이므로 전건 표(ⓑ)와 `uncertain_influences` 표(ⓒ)가
**여기 한 덩어리로** 온다. 주제별로 쪼개 여러 단계에 흩으면 어느 단계에도 안
실리는 접두가 생기고 **행이 조용히 사라진다** — 앞머리의 부분 표는 그 전건에서
*「이 단계가 새로 세우는 것」* 만 골라 앞세운 것이며, **행을 짓지 않는다.**

## ★ 설비 단가(`capex.*`)는 여기 «없다» — 2단계에 남는다

검토서 §3.1 은 *「REC 단가, PV·ESS 단가, 할인율, 지원율은 경제성 입력 파일로
이동한다」* 라 적었으나 **R68 판정이 그 하나를 뒤집었고 이쪽이 정본이다**:
초기투자가 설비 단가로 계산되므로 그 단가는 자원 구성과 같은 자리에 서야 한다.
⛔ 그 판정을 이 모듈에서 되돌리지 않는다.

## ⚠ 할인율과 지원율은 **대장 항목이 아니다**

- **할인율** — `docs/assumptions.yaml` 에 0건이다. 케이스 수준표
  (`core/casegrid/ledger_levels.py`)가 *「평가자가 고르는 모형 파라미터」* 로
  갖는다. 그래서 아래 표가 대장 표와 **따로** 선다: 같은 표에 넣으면 대장에
  있는 값과 없는 값이 한 표에서 같아 보인다.
- **지원율** — 시나리오가 정하는 정책 축(`CaseReport.subsidy_rate`)이다.
  10단계가 그 변형을 비교하고, 이 단계는 *「이 실행이 무엇으로 돌았는가」* 만
  적는다. ⛔ 여기서 변형을 다시 계산하지 않는다.

## ⚠ 사람이 읽는 자리의 낱말

표 제목·열 제목에 「전제」를 세우지 않는다 — 그 낱말은 사람이 읽는 자리에서
0건이 규약이고(판정 R63b §1 · `tests/app/test_screen_words.py`), 이 표의 머리는
`/ui/verify` 에서 `th` 가 된다. 대장을 부르는 말은 「분석 설정 대장」이다.
"""
from __future__ import annotations

from core.casegrid.ledger_levels import LEVEL_NAMES
from core.report._format import _num
from core.report.case_report import MAX_SUBSIDY_RATE, CaseReport
from core.report.verification_ledger import ledger_table, rows_with_prefix

#: **4단계가 앞머리에 부분 표로 세우는 접두** — 요금과 REC 단가.
#:
#: ⚠ 근거는 대장 자신의 `group_titles` 다: `tariff` 가 「전기요금·거래단가」이고
#: REC 는 `benefit` 아래의 두 항목(`benefit.rec_price` · `benefit.rec_weight_pv`)
#: 이다. `benefit.*` 를 통째로 넣지 않은 이유는 그 군이 **편익 단가 전체**여서
#: 5단계 편익이 쓰는 값까지 끌어오고, 그러면 이 부분 표가 *「이 단계가 새로
#: 세우는 것」* 이 아니라 편익 표의 사본이 된다.
#:
#: ⚠⚠ **`DEMAND_LEDGER_PREFIXES` 와 겹치지 않아야 한다** — 겹치면 같은 항목이 두
#: 단계에서 「이 단계가 읽은 값」으로 선다(`verification_demand.py` 의 같은 ⚠).
ECONOMIC_LEDGER_PREFIXES: tuple[str, ...] = ("tariff.", "benefit.rec")

#: 부분 표의 제목. ⚠ 「전제」를 쓰지 않는다.
ECONOMIC_LEDGER_TITLE = (
    "**이 단계가 분석 설정 대장에서 읽은 값 — 요금과 REC 단가** "
    "(접두 `tariff.*` · `benefit.rec*`)"
)

#: 대장 밖 두 축의 표 제목.
ECONOMIC_AXIS_TITLE = "**대장이 갖지 않는 두 축 — 할인율과 지원율**"


def economic_axis_lines(report: CaseReport) -> list[str]:
    """할인율·지원율 표 — **대장 항목이 아닌 것을 대장 표와 갈라 싣는다**.

    ## ★★ 할인율이 왜 이 표에 있는가 (R64/WP-FIX 결함 1 · R69/WP-1 이 옮겼다)

    9단계 ⓐ 가 *「4단계 할인율」* 을 가리키므로 그 행이 어딘가 서 있어야 한다.
    R64 가 그것을 옛 1단계의 「이 실행이 받은 입력」 표에 세웠고, R69/WP-1 이
    단계를 가르면서 **경제성 쪽으로 옮겼다** — 할인율은 수요가 아니다.

    ⚠ **참조를 지우는 대신 참으로 만든다**는 판단은 그대로다. 그 행이 사라지면
    9단계의 가리킴이 다시 거짓이 된다.
    """
    return [
        "",
        ECONOMIC_AXIS_TITLE,
        "",
        "| 항목 | 이 실행의 값 | 어디서 오나 |",
        "|---|---|---|",
        f"| 할인율 (9단계 `NPV` 의 r) | {report.basis.discount_rate:.1%} "
        "| **대장에 없다** — 케이스 수준표 `core/casegrid/ledger_levels.py` 의 "
        f"모형 파라미터이며 갈래 셋({' · '.join(LEVEL_NAMES)}) 중 이 실행의 "
        "케이스 값이 고른 것 |",
        f"| 지원율 | {report.subsidy_rate:.0%} "
        "| **대장에 없다** — 시나리오 yaml 의 `subsidy_rate` 가 정하는 정책 "
        f"축이다. 상한은 {MAX_SUBSIDY_RATE:.0%}(사업비 전액)이며 변형 비교는 "
        "10단계가 싣는다 |",
        "",
        "- 이 둘은 **분석 설정 대장 항목이 아니다** — 그래서 아래 대장 표에 "
        "행이 없고, 같은 표에 섞지 않는다(섞으면 대장이 정한 값과 평가자가 고른 "
        "값이 한 표에서 같아 보인다)",
        f"- 분석기간 {report.basis.horizon_years}년은 대장 항목이다"
        "(`analysis.period_years`) — 아래 전건 표에 그 행이 있다",
    ]


def economic_ledger_lines(report: CaseReport) -> list[str]:
    """4단계 ⓐ — 요금·REC 단가 **부분 표**. ⛔ 행을 짓지 않는다.

    앞머리에 이 표를 세우는 것은 검토서 §3.1 의 요구다 — *「REC 단가 … 할인율,
    지원율은 경제성 입력 파일로」*. 아래 ⓑ 전건 표가 같은 행을 다시 싣는 것은
    사본이 아니라 **다른 진술**이다: 앞은 「이 단계가 새로 세우는 값」이고 뒤는
    「대장이 무엇을 갖고 있는가」다.
    """
    rows = rows_with_prefix(report, ECONOMIC_LEDGER_PREFIXES)
    return [
        "",
        ECONOMIC_LEDGER_TITLE,
        "",
        *ledger_table(rows),
        "",
        f"- {len(rows)}건이며 전건 {len(report.assumptions)}건은 아래 ⓑ 가 한 "
        "덩어리로 싣는다",
        "- ⛔ 설비 단가(`capex.*`)는 이 표에 **없다** — 2단계에 남는다. "
        "초기투자가 그것으로 계산되므로 자원 구성과 같은 자리에 서야 한다"
        "(검토서 §3.1 은 그것도 옮기라 적었으나 R68 판정이 정본이다)",
    ]


def ledger_all_lines(report: CaseReport) -> list[str]:
    """4단계 ⓑ — 대장 **전건 표**. 「1 의 나머지」가 한 덩어리로 여기 선다.

    ⛔ 주제별로 쪼개 여러 단계에 흩지 않는다 — 흩으면 어느 단계에도 안 실리는
    접두가 생기고 행이 조용히 사라진다(모듈 머리말 ⛔ 절).
    """
    return [
        f"외부 대장 파일 `{report.assumption_set_name}` 판 "
        f"{report.assumption_set_version}(`docs/assumptions.yaml`).",
        "",
        f"그 파일에서 **값을 읽어 온** 항목 {len(report.assumptions)}건 — "
        "값·단위·기준연도·출처·신뢰도·최종확인일을 각 행이 함께 나른다. "
        "**대장 파일의 항목 수가 아니다** — 값이 비어 있는 항목은 여기 없다.",
        "",
        *ledger_table(report.assumptions),
    ]


def influence_lines(report: CaseReport) -> list[str]:
    """4단계 ⓒ — 파이프라인이 **실제로 읽어 결론에 반영한** 대장 키.

    ⚠ 문면이 스스로 이름 부른 단계가 목차의 의존 연결표 오른쪽 칸이 된다
    (`core/report/verification_chain.py::named_stages`) — 그래서 이 절의 문장이
    어느 단계로 가는지를 **글자로** 적는다.
    """
    return [
        # ⚠ 「1·2·3단계」로 적지 않는다 — 목차의 의존 연결표는 이 문면에서
        #   `\d+(?:~\d+)?단계` 를 세므로 가운뎃점으로 이은 앞의 둘을 놓친다
        #   (`verification_chain.py::named_stages`). 낱개로 적으면 그 칸이
        #   실제로 이름 부른 단계를 전부 싣는다.
        "이 표의 키가 이 보고서 전체에서 대입값으로 쓰인다 — 부하·설계는 "
        "1단계 · 2단계 · 3단계가 이미 썼고(경제성 입력을 물리 검증 뒤에 두는 "
        "것이 이 배열의 뜻이다) 요금·REC 단가·할인율·지원율은 5~10단계가 "
        "받는다. 아래는 파이프라인이 "
        "**실제로 읽어 결론에 반영한** 대장 키만 골라낸 것이다(5.1 영향도 분석이 "
        "대장과 결선된 것으로 확인한 인자 — `report.uncertain_influences`):",
        "",
        "| 변수 | 대장 키 | 사용값 | 단위 |",
        "|---|---|---|---|",
        *(
            f"| {entry.variable} | `{entry.ledger_key}` | {_num(entry.used_value)} "
            f"| {entry.value_unit or '—'} |"
            for entry in report.uncertain_influences
        ),
    ]
