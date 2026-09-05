"""실행 화면이 쓰는 문맥 — **결과·거부·그림·실행 폼의 고를 거리**.

`web/render.py` 에서 갈라 나왔다 (`R62/WP-9`). 가른 선은 **`/ui/run` 이 지나는
길**이다: 실행 폼이 고르게 하는 것(갈래·계측 선언)과, 그 실행이 낸 결과·거부·그림을
화면 사전으로 옮기는 것이 여기 있고, 대시보드·자원 구성·제도 편집 화면과
**템플릿을 부르는 자리**는 저쪽에 남았다.

⚠ **자리만 옮겼다.** 값·키·문면을 하나도 바꾸지 않았다 — 옮기면서 바꾸면
어느 쪽이 원인인지 말할 수 없게 된다.

⚠ 부르는 쪽(`app/routers/ui.py`·`ui_forms.py`·`tests/`)은 여전히
`web.render` 를 본다. 그 모듈이 여기 이름을 **재수출**한다 —
`web/render.py` 의 `__all__` 이 그 목록이다.
"""

from __future__ import annotations

import dataclasses
from types import MappingProxyType
from typing import Any
from urllib.parse import urlencode

from app.services.ui_charts import chart_description, chart_source, unwired_reason
from core.cba.baseline import (
    POOL_PREREQUISITE_METERING,
    POOL_PREREQUISITE_TRANSFER,
    BaselineArrangement,
    PoolMeteringDeclaration,
)
from core.contracts.validation import ValidationError
from core.report._format import NO_VALUE, _won, _years
from core.report.case_influences import CONCLUSION_METRIC, HEADLINE_METRIC
from core.report.case_report import CaseReport
from core.report.charts import chart_registry

#: 영향도 인자에 **이을 대장 줄이 없을 때** 출처 칸이 인쇄하는 것.
#:
#: ⚠⚠ **빈칸으로 두지 않는다.** 빈칸은 「출처가 없다」와 「화면이 싣지 못했다」를
#: 같게 만든다(§13.0.1 ④ · `web/render.py::UNLABELLED` 가 라벨에서 같은 판단을
#: 했다). 그리고 「출처가 대장에 안 적혀 있다」와도 **다른 진술**이다 — 그쪽은
#: 대장이 자료로 「출처 미기재」를 갖고 있고, 이것은 **대장에 그 값의 줄 자체가
#: 없다**는 뜻이다(기본값 실행에서는 `discount_rate` 한 건이며, 대장에
#: 할인율 항목이 없다는 것이 실제 상태다).
#:
#: ⛔ **여기에 출처 문면을 짓지 마라.** 이것은 출처가 아니라 **자리의 상태**다.
NO_LEDGER_SOURCE = "대장 밖의 값"


def baseline_arrangement_choices() -> tuple[str, ...]:
    """고를 수 있는 갈래의 **값 문면** — `BaselineArrangement` 를 열거해 얻는다.

    ⚠ **목록을 소스에 박지 않는다.** 박으면 여덟 번째 갈래가 서는 날 화면만
    셋을 그린 채 남고, 그 상태는 사람이 없는 칸을 찾을 때까지 드러나지 않는다
    (`equipment_setting_groups` 가 같은 판단을 적어 두었다).

    ⚠ 값 문면 그대로인 이유: 시나리오 yaml 의 `baseline_arrangement` 필드가
    **문면 그대로**를 받는다 (`resolve_baseline_arrangement` 독스트링).
    """
    return tuple(item.value for item in BaselineArrangement)


#: ⓒ 계측 선언 둘의 **화면 문면**. 이름은 `PoolMeteringDeclaration` 의 필드에서,
#: 문면은 `core.cba.baseline` 의 상수에서 온다 — 어느 쪽도 여기서 짓지 않는다.
#: 거부 메시지와 화면이 **같은 문자열**을 봐야 사람이 *「어느 쪽이 빠졌는가」*
#: 를 대조할 수 있다(그 상수들의 ⚠ 주석이 같은 이유를 적는다).
#: ⚠ 읽기 전용으로 둔다 — 모듈 수준 가변 컨테이너는 `NFR-205` 가 막는 것이다
#: (`scripts/check_hardcoded_params.py` 는 `web/` 를 훑지 않지만 규칙은 같다).
#: `BASELINE_DECLARATIONS` 가 같은 자리에서 같은 모양을 쓴다.
_POOL_PREREQUISITE_LABELS = MappingProxyType({
    "ownership_or_operation_transferred": POOL_PREREQUISITE_TRANSFER,
    "metering_separated": POOL_PREREQUISITE_METERING,
})


def pool_prerequisite_fields() -> tuple[dict[str, str], ...]:
    """ⓒ 계측 선언 둘의 **화면 칸** — 이름은 자료형이, 문면은 상수가 정본이다.

    ⚠ 선언이 하나 늘면 여기서 `KeyError` 로 **멈춘다.** 조용히 빠지는 대신인
    이유: 안 그리면 새 선언을 아무도 세울 수 없고, 그 상태는 화면에서
    「ⓒ 를 고를 수 없다」로만 보인다 — 왜 못 고르는지는 보이지 않는다.
    """
    return tuple(
        {"name": field.name, "label": _POOL_PREREQUISITE_LABELS[field.name]}
        for field in dataclasses.fields(PoolMeteringDeclaration)
    )


def chart_query(
    *,
    scenario: str,
    arrangement: str,
    ownership_or_operation_transferred: bool,
    metering_separated: bool,
) -> str:
    """그림 주소에 붙일 질의 문자열 — **결과 화면과 같은 실행을 그리게 한다.**

    ⚠ 손으로 잇지 않는다(`urlencode`). 갈래 문면은 한국어라 그대로 이으면
    주소가 깨지고, 깨진 주소는 브라우저가 기본 갈래로 되돌아간 그림을 가져온다 —
    화면의 수는 ⓒ 인데 그림은 ⓑ 인 상태가 나오고 **둘 다 그럴듯해 보인다**.

    ⚠ 참·거짓 문면을 파이썬 것(`True`)으로 두지 않는다 — 받는 쪽은 FastAPI 의
    불리언 파서다.
    """
    return urlencode({
        "scenario": scenario,
        "arrangement": arrangement,
        "ownership_or_operation_transferred": (
            "true" if ownership_or_operation_transferred else "false"
        ),
        "metering_separated": "true" if metering_separated else "false",
    })


def chart_figures(*, query: str = "") -> tuple[dict[str, Any], ...]:
    """결과 그림 칸 — **레지스트리로 편다.**

    ⚠⚠ **제목을 손으로 적지 않는다.** 종전 `visual-grid` 는 `<h3>` 여섯 개를
    박아 두었고 그림은 하나도 없었다. 박아 두면 차트가 늘 때 그 목록이 낡고,
    낡은 것은 사람이 없는 칸을 찾을 때까지 드러나지 않는다
    (`equipment_setting_groups` 가 같은 판단을 적었다).

    ⚠ **못 그리는 칸을 빼지 않는다.** 빼면 「그릴 수 없다」와 「그런 그림이
    없다」가 화면에서 같아진다 — §13.0.1 ④ 가 금지한 형태다. 칸은 남기고
    사유를 글자로 싣는다.
    """
    suffix = f"?{query}" if query else ""
    figures: list[dict[str, Any]] = []
    for tag, chart in sorted(chart_registry().items()):
        reason = unwired_reason(tag)
        figures.append({
            "tag": tag,
            "label": chart.label,
            "wired": reason is None,
            "reason": reason,
            "src": f"/ui/chart/{tag}.png{suffix}",
            # `alt` 는 라벨 + **무엇을 보여 주는 그림인지**다. 라벨만 넣으면
            # 그림을 못 보는 사람에게 남는 것이 제목뿐이고, `UI-6` 이 막으려는
            # 것이 정확히 그 상태다 — 그림은 색으로만 말한다.
            "alt": f"{chart.label} — {chart_description(tag)}" if reason is None else "",
            "source": chart_source(tag) if reason is None else "",
        })
    return tuple(figures)


def run_result_context(
    report: CaseReport, *, scenario_text: str, chart_query: str = ""
) -> dict[str, Any]:
    """실행 결과 화면의 문맥 — `UI-7-AC1` · `FR-705-AC2`.

    ## ⚠⚠⚠ **여기서 계산을 새로 하지 않는다**

    `CaseReport` 가 준 값을 **옮겨 적기만** 한다. 화면이 인쇄하는 수가
    리포트와 어긋나면 **그것이 새 결함**이다 — 이 저장소가 `cost_benefit_
    section` 에서 이미 한 번 밟은 형태다(1년차 값으로 결손을 되지었더니 합이
    맞지 않았다).

    ⚠ 서식은 **`core/report/_format.py` 의 것을 그대로 쓴다.** 문면을 여기서
    다시 지으면 「500,000원」과 「500000원」이, 「분석기간 내 미회수」와 다른
    문면이 같은 저장소에 섞인다 — 그 파일이 존재하는 이유가 정확히 그것이다.
    반올림·부호 뒤집기·단위 환산은 하지 않는다.

    ⚠ **지표 키를 문자열로 박지 않는다** — `CONCLUSION_METRIC`(npv)·
    `HEADLINE_METRIC`(payback_years) 이 정본이다.

    ★ `npv_raw` 를 **날값 그대로** 함께 싣는다. 서식을 입힌 문면만 두면
    「화면의 수가 리포트의 수와 같은가」를 기계가 대조할 수 없고, 그때 그
    검사는 서식 문자열을 다시 짜 맞추게 된다.

    ## ★★ 인자마다 **출처**를 함께 싣는다 (착수 목록 53)

    심의에서 *「그 수가 어디서 왔나」* 를 묻는 자리가 반드시 온다
    (`app/services/ui_run.py::UiRun` 독스트링이 같은 사유를 적는다). 종전에
    이 화면이 인자마다 실은 것은 **이름·대장 키·영향액** 셋이었고, 대장 키는
    *어디를 보라*는 말이지 *무엇에 근거했는가*가 아니다.

    ⛔ **출처를 여기서 짓지 않는다.** `CaseReport.assumptions` 의 `source` 를
    인자의 `ledger_key` 로 **잇는다** — 손으로 적으면 대장이 출처를 갱신하는 날
    화면만 옛 글자를 인쇄하고, 그 상태는 아무 검사도 빨간불을 내지 않는다
    (`.orch/R63/result_V2.md` §2 `D12` 가 그 형태였다).

    ⚠ **대장 줄이 없는 인자를 빈칸으로 두지 않는다** — `NO_LEDGER_SOURCE` 를
    글자로 인쇄한다(그 상수의 ⚠ 주석).
    """
    ledger_sources = {row.key: row.source for row in report.assumptions}
    return {
        "error": None,
        "scenario_name": report.scenario_name,
        # ★ 영향도 순위 — 화면 **최상단**이다 (`UI-7-AC1`).
        "influences": tuple(
            {
                "rank": rank,
                "name": entry.variable,
                "ledger_key": entry.ledger_key or NO_VALUE,
                "impact": _won(entry.delta_won),
                # ⚠ `NO_VALUE`(「—」)를 쓰지 않는다. 이 자리의 「없다」는 두
                # 가지이며(대장에 줄이 없다 · 대장이 출처를 안 적었다) 뒤쪽은
                # 대장이 **자료로** 「출처 미기재」를 갖는다. 같은 기호로 덮으면
                # 그 둘이 화면에서 같아진다.
                "source": ledger_sources.get(
                    entry.ledger_key or "", NO_LEDGER_SOURCE
                ),
                "flips": entry.flips_conclusion,
            }
            for rank, entry in enumerate(report.influences, start=1)
        ),
        # ★ 어느 갈래로 돌았나 — 갈래를 고르게 해 놓고 결과가 그것을 안 적으면
        # 확인할 방법이 없다. 선언 다섯을 함께 싣는다(`CaseReport.
        # baseline_branch` 의 ⚠ — 이름만 실으면 검토자가 그 이름이 뜻하는
        # 기준선을 저장소 밖에서 찾아야 한다).
        "arrangement": report.baseline_arrangement.value,
        "branch": {
            "without": report.baseline_branch.without_description,
            "with": report.baseline_branch.with_description,
            "viability": report.baseline_branch.viability_condition or NO_VALUE,
            "self_consumption": (
                report.baseline_branch.self_consumption_treatment.value
            ),
            "clause": report.baseline_branch.clause,
        },
        "npv": _won(report.metrics[CONCLUSION_METRIC]),
        "npv_raw": report.metrics[CONCLUSION_METRIC],
        "payback": _years(report.metrics[HEADLINE_METRIC]),
        "annual_benefit": _won(report.basis.annual_benefit_won),
        "annual_cost": _won(report.basis.annual_cost_won),
        "benefits": tuple(
            {"label": line.label, "annual": _won(line.annual_won)}
            for line in report.basis.benefits
        ),
        "costs": tuple(
            {"label": line.label, "annual": _won(line.annual_won)}
            for line in report.basis.costs
        ),
        "scenario_text": scenario_text,
        # ★ 그림은 **이 실행의** 질의를 달고 나간다. 기본값으로 그리면 위의 수와
        # 아래 그림이 서로 다른 실행이 되고, 그 어긋남은 아무 오류도 내지 않는다.
        "charts": chart_figures(query=chart_query),
    }


def run_error_context(exc: ValidationError) -> dict[str, Any]:
    """거부 화면의 문맥 — **필드·사유·조치 3요소** (`NFR-303`).

    ⚠ **예외 문면을 여기서 새로 짓지 않는다.** `exc.field`·`exc.reason`·
    `exc.action` 을 옮긴다 — 새로 지으면 같은 거부가 JSON 출구
    (`app/routers/models.py::_bad_request`)와 화면에서 다른 말을 하게 되고,
    그때 어느 쪽이 맞는지는 아무 검사도 말하지 않는다.

    `rule` 도 함께 싣는다. ⓒ 거부는 `DV-15` 이며, 대장 ID 가 붙은 거부와
    일반 입력 검증을 화면이 가려 보여야 사람이 *「제도가 막은 것인가」* 를
    안다(`ValidationError` 독스트링의 「`rule` 은 선택이다」 절).
    """
    return error_context(
        field=exc.field, reason=exc.reason, action=exc.action, rule=exc.rule
    )


def error_context(
    *, field: str, reason: str, action: str, rule: str | None = None
) -> dict[str, Any]:
    """거부 화면의 문맥 — **3요소를 실은 사전 하나** (`NFR-303`).

    `ValidationError` 가 아닌 거부도 이 통로로 온다. 화면 폼이 없는 프로파일을
    가리키거나(`KeyError` → 404) 권한 없이 눌렀을 때(`PermissionError` → 403)
    라우터가 내는 것은 **문자열 한 줄**이며, 그것을 그대로 브라우저에 던지면
    사람에게 남는 것은 「무엇을 하라」가 없는 문장이다 — 그것이 `NFR-303` 이
    막으려는 상태다. 그래서 부르는 쪽이 셋을 갖춰 여기로 보낸다.

    ⚠ **새 거부 화면을 만들지 않는다.** 낼 것은 `run_result.html` 의
    `#validation` 절 하나이며, 이 함수는 그 절이 읽는 사전을 지을 뿐이다.
    """
    return {
        "error": {
            "field": field,
            "reason": reason,
            "action": action,
            "rule": rule or NO_VALUE,
        }
    }
