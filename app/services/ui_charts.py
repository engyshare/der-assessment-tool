"""`CaseReport` → 차트 입력 자료 — `FR-1004-AC1` · `FR-803-AC2`.

## 왜 이 파일이 R62 에 생겼는가

`core/report/charts/` 에 차트 7종이 클래스로 서 있고 전부 실제 PNG 바이트를
낸다. 그런데 **배포 코드가 부르는 곳이 0곳이었다** —
`grep -rn -e render_charts -e chart_registry core/ app/ web/` 이 레지스트리 자신과
주석 한 줄만 냈고, 호출자는 전부 `tests/` 안이었다. `case_report.py` 머리
주석이 R33 에 그 형태를 적어 두었으나(*「`render_charts()` 의 호출자가 전부
`tests/` 안이었다」*) 차트 쪽은 아직 안 고쳐진 채였다. 여기가 뚫는 것이 그
구멍이며, WP-1(화면이 HTTP 로 안 나갔다)·WP-2(폼이 실행에 안 닿았다)와 **같은
결함**이다.

## ★★★ 이 파일의 규칙 하나 — **수를 지어내지 않는다**

화면이 인쇄하는 수가 리포트와 어긋나면 그것이 새 결함이다. **그림도 수다.**
그래서 차트 입력은 전부 `CaseReport` 의 필드에서만 파생시키고, 모자란 값을
예시값·0·평균으로 채우지 않는다. `web/render.py::demo_context` 가 이미 그런
수(12kW·15800kWh·162원)를 갖고 있으나 **그 수는 그림에 오지 않는다.**

입력을 만들 수 없는 차트는 **조용히 건너뛰지 않는다.** `render_charts` 의
독스트링이 같은 판단을 이미 적었다 — *「입력이 모자란 차트를 조용히 건너뛰지
않는다 … 그 빈자리는 심의자료가 인쇄된 뒤에 발견된다」*. 여기서는 사유를
`UNWIRED` 에 글자로 두고 화면과 라우트가 그것을 **드러낸다**.

## 배선하지 못한 둘과 그 사유 (`UNWIRED`)

`energy_balance`(월별) 와 `feasible_region`(2변수 격자)이다. 둘 다 「그릴 수
있는데 안 그린 것」이 아니라 **`CaseReport` 에 재료가 없다**. 사유는 상수에
그대로 적었다 — 「구현이 없다」와 「수집이 안 됐다」를 같게 읽지 않기 위해서다.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any

from core.contracts.schemas import CashFlowRow
from core.contracts.validation import ValidationError
from core.report.case_influences import CONCLUSION_METRIC
from core.report.case_report import CaseReport

#: 결론 축의 화면 문면. 지표 **이름**은 `CONCLUSION_METRIC` 이 정본이고 여기는
#: 축에 적을 사람 말이다 — `model_comparison` 이 `comparison_metric_label` 로
#: 받는 자리이며, 안 주면 그 차트가 「지표값」이라고만 적는다.
_CONCLUSION_AXIS_LABEL = "순현재가치 (원)"

#: `CaseReport.metrics` 에서 **이 시나리오가 실제로 낸 돈**을 꺼내는 키.
#: ⚠ 상수가 없어 문자열을 적는다 — `core/casegrid/case_metrics.py` 가 이 이름을
#: 짓고 `core/report/shortfall.py`·`narrative.py`·`verification.py` 셋이 이미
#: 같은 리터럴로 읽는다. 어긋나면 조용하지 않다: `KeyError` 로 멈춘다.
_OUTLAY_METRIC = "initial_outlay_won"

#: 배선하지 못한 차트와 **그 사유**. 화면과 라우트가 이 문면을 그대로 낸다.
#:
#: ⚠ 읽기 전용으로 둔다 — 모듈 수준 가변 컨테이너는 `NFR-205` 가 막는다
#: (`core/report/charts/energy_balance.py::_LABELS` 가 같은 자리에서 같은 모양).
UNWIRED: Mapping[str, str] = MappingProxyType({
    "energy_balance": (
        "`CaseReport` 에 월별 시계열이 없다. 이 실행의 운전 해상도는 "
        "**대표일 24스텝 하나**(`CaseReport.dispatch_hours`)이고 저장소는 월별 "
        "변동을 모형화하지 않는다 — `core/casegrid/ess_share_benefits.py` 가 "
        "「월별 변동을 여기서 지어내지 않는다」고 적고 같은 값을 12개월로 펴 "
        "둔다. 대표일을 12로 펴면 열두 달이 전부 같은 막대가 되고, 그 그림은 "
        "「계절 변동이 없다」를 결과로 주장한다"
    ),
    "feasible_region": (
        "`CaseReport` 에 2변수 격자가 없다. 2변수 재료는 `coupled_sweeps` "
        "하나뿐인데 그것은 격자가 아니라 **별 모양 탐침**이다(기준점 + 한 "
        "인자씩 + 함께, low·high). 3수준 격자로 펴면 두 칸이 비고, 그 차트는 "
        "빈 칸을 거부한다 — 「일부만 실행했다면 등고선은 실행하지 않은 좌표의 "
        "값을 지어냅니다」. 채워지는 2수준 부분격자가 있으나 low 쪽과 high 쪽 "
        "중 어느 반쪽을 고르느냐가 「목표 달성 영역」의 넓이를 바꾸고, 그 "
        "선택을 정하는 규칙이 저장소에 없다"
    ),
})

#: 차트가 **무엇을 말하는 그림인지** 한 문장. `alt` 가 이것을 갖는다.
#:
#: ⚠ **`alt` 를 비우거나 라벨만 넣지 않는다.** `UI-6`(색상 단독 정보전달 금지 ·
#: WCAG 2.1 AA)이 Phase 1 이고 **그림은 색으로만 말한다** — 붉은 막대가 무엇을
#: 뜻하는지 글자로 갖고 있지 않으면 그림을 못 보는 사람에게 남는 것이 없다.
#: 문면은 각 차트 구현이 실제로 그리는 것에서 왔다(전환 인자·음수 막대의 붉은색,
#: 손익분기 세로선은 회수될 때만 찍는다 등).
_DESCRIPTIONS: Mapping[str, str] = MappingProxyType({
    "cashflow_line": (
        "연차별 누적 현금흐름 곡선이다. 0원 가로선을 처음 넘는 해에 붉은 "
        "세로선이 서고 그것이 손익분기 시점이며, 분석기간 안에 넘지 못하면 "
        "그 세로선이 아예 없다"
    ),
    "cost_benefit_pie": (
        "1년차 편익 항목과 비용 항목이 각각 전체에서 차지하는 비율을 부채꼴 "
        "크기와 백분율로 적은 원 그림이다"
    ),
    "dispatch_stack": (
        "대표일 시간대별로 자원이 낸 전력을 쌓아 올리고 그 위에 부하 곡선을 "
        "검은 파선으로 겹친 그림이다. 쌓은 높이가 파선에 못 미치는 시간대가 "
        "계통에서 사 온 몫이고, 0 아래로 내려간 자리는 저장장치가 충전한 "
        "시간대다"
    ),
    "energy_balance": (
        "월별로 공급(생산·구입)을 0 위에, 사용(자가소비·잉여판매)을 0 아래에 "
        "쌓아 대비시키는 그림이다"
    ),
    "feasible_region": (
        "두 인자를 두 축에 놓고 지표 등고선을 그린 뒤 목표를 달성한 칸만 "
        "초록으로 음영 처리하는 그림이다"
    ),
    "model_comparison": (
        "변형별 순현재가치를 막대로 나란히 놓은 그림이다. 0원 아래로 내려간 "
        "막대는 붉은색이며 분석기간 안에 회수하지 못한 변형이다"
    ),
    "tornado": (
        "인자를 하나씩 끝에서 끝까지 흔들었을 때 순현재가치가 움직인 폭을 큰 "
        "것부터 가로 막대로 놓은 그림이다. 결론이 뒤집히는 인자의 막대는 "
        "붉은색이고 나머지는 파란색이다"
    ),
})

#: 그 차트의 수가 **리포트의 어느 필드에서 왔는지**. `<figcaption>` 이 이것을
#: 인쇄한다 — 심의에서 「이 그림의 수는 어디서 왔나」가 반드시 나오고, 그때
#: 화면이 답을 갖고 있어야 한다.
_SOURCES: Mapping[str, str] = MappingProxyType({
    "cashflow_line": (
        f"CaseReport.cashflows (편익에서 운영비와 교체·잔존을 뺀 값) · t=0 은 "
        f"metrics[{_OUTLAY_METRIC!r}]"
    ),
    "cost_benefit_pie": "CaseReport.basis.benefits · basis.costs (1년차)",
    "dispatch_stack": "CaseReport.dispatch_hours · basis.resources",
    "model_comparison": "CaseReport.variants · variant_labels",
    "tornado": "CaseReport.influences",
})


def _unwired_error(tag: str, reason: str) -> ValidationError:
    """배선되지 않은 차트를 **3요소로** 거부한다 (`NFR-303`).

    사유만 던지면 받는 쪽에 「어떻게 고치는가」가 없다. 조치는 *「무엇이 있어야
    그릴 수 있는가」* 를 적는다 — 그것이 다음 라운드가 집을 자리다.
    """
    return ValidationError(
        field=f"chart.{tag}",
        reason=f"아직 배선되지 않았다 — {reason}",
        action=(
            "그 재료를 CaseReport 가 실어야 그릴 수 있습니다. 값을 지어내 "
            "채우지 마십시오 — 채운 그림은 정상으로 보이고, 심의에서 그것이 "
            "실제 결과로 읽힙니다"
        ),
    )


def unwired_reason(tag: str) -> str | None:
    """이 차트를 **왜 못 그리는지**. 그릴 수 있으면 `None`.

    리포트를 돌리지 않고 답한다 — 대시보드가 칸을 그릴 때 재료 유무를 알려면
    그림 7장을 미리 돌려야 하는데, 그것은 화면 한 번에 케이스 7회 실행이다.

    ⚠ `UNWIRED` 에 없더라도 **입력을 짓는 함수가 없으면 배선되지 않은 것**이다.
    차트가 하나 늘고 이 파일이 따라오지 않는 날 그 태그를 「그릴 수 있다」로
    답하면 화면이 깨진 그림 칸을 그리고, 왜 깨졌는지는 어디에도 적히지 않는다.
    """
    if tag in UNWIRED:
        return UNWIRED[tag]
    if tag not in _BUILDERS:
        return (
            f"차트 {tag!r} 의 입력을 CaseReport 에서 짓는 함수가 없다 — "
            "차트가 늘었는데 app/services/ui_charts.py 가 따라오지 않았다"
        )
    return None


def chart_description(tag: str) -> str:
    """그 차트가 **무엇을 말하는 그림인지** 한 문장 — `alt` 가 쓴다."""
    return _lookup(_DESCRIPTIONS, tag, what="설명")


def chart_source(tag: str) -> str:
    """그 차트의 수가 **리포트의 어느 필드에서 왔는지** — `figcaption` 이 쓴다."""
    return _lookup(_SOURCES, tag, what="자료 출처")


def _lookup(table: Mapping[str, str], tag: str, *, what: str) -> str:
    """표에서 꺼낸다. **없으면 멈춘다.**

    ⚠ 빈 문자열로 메우지 않는다. `alt` 가 비면 `UI-6` 이 요구하는 것이 사라지고,
    그 상태는 화면이 멀쩡해 보이므로 그림을 못 보는 사람이 만날 때까지 드러나지
    않는다 (`web/render.py::pool_prerequisite_fields` 가 같은 판단을 적었다).
    """
    if tag not in table:
        raise ValidationError(
            field=f"chart.{tag}",
            reason=f"차트 {tag!r} 의 {what} 이(가) 없습니다",
            action=(
                f"app/services/ui_charts.py 에 {tag!r} 의 {what} 을 적으십시오. "
                "빈 칸으로 두면 화면은 멀쩡해 보이고 그 그림만 말을 잃습니다"
            ),
        )
    return table[tag]


def _year_total(rows: Sequence[CashFlowRow], year: int) -> float:
    """그 해의 행 합계. **없는 해는 0 이다** — 교체·잔존은 특정 연차에만 있다."""
    return sum(float(row.amounts.get(year, 0)) for row in rows)


def _cashflow_line(report: CaseReport) -> dict[str, Any]:
    """연차별 순현금흐름 — **`core/report/shortfall.py` 와 같은 가름이다.**

    `build_shortfall()` 이 결손을 `-초기지출 + PV(편익) − PV(운영비) −
    PV(교체·잔존)` 로 갈라 두고 **합이 `npv` 와 원 단위로 같은지 확인한 뒤에만**
    표를 만든다. 여기서는 같은 가름을 **할인하지 않고 연차별로** 편다. 즉 이
    곡선을 할인해 더하면 화면의 NPV 가 그대로 나온다 — 새 분해가 아니다.

    ⚠ 초기지출은 `basis.initial_investment_won`(무지원 총사업비)이 아니라
    `metrics` 의 것이다. 화면이 인쇄하는 NPV 가 **지원을 반영한** 변형의 것이고
    (`CaseReport.metrics` 주석), 총사업비를 쓰면 지원받은 시나리오에서 곡선과
    결론이 지원액만큼 어긋난다 — `build_shortfall` 이 같은 ⚠ 를 적어 두었다.

    ⚠ 부호를 여기서 새로 정하지 않는다. 편익 행은 유입이 양수, 운영비·교체
    행은 **유출이 양수**이며(`CashflowSplit`) 그것을 한 번만 뒤집는다.
    """
    if _OUTLAY_METRIC not in report.metrics:
        raise _unwired_error(
            "cashflow_line",
            f"이 실행의 지표에 {_OUTLAY_METRIC!r} 이(가) 없다 — t=0 을 지어내면 "
            "곡선 전체가 그만큼 통째로 움직이고 손익분기 연차가 거짓이 된다",
        )
    split = report.cashflows
    flows = [-float(report.metrics[_OUTLAY_METRIC])]
    flows.extend(
        _year_total(split.benefit, year)
        - _year_total(split.operating_cost, year)
        - _year_total(split.lifecycle, year)
        for year in range(1, report.basis.horizon_years + 1)
    )
    return {"cashflows": flows}


def _cost_benefit_pie(report: CaseReport) -> dict[str, Any]:
    """1년차 편익·비용 항목의 구성비.

    ⚠ **부호로 둘을 가르지 않는다.** 그 차트는 음수를 거부하며 *「비용과 편익을
    각각 양수로 넘기십시오」* 라고 적는다. 그래서 금액은 행이 담은 그대로 두고
    **이름표에** 어느 쪽인지 적는다 — 부채꼴만 보고 비용을 편익으로 읽지
    않도록.

    ⚠ 금액이 음수인 행이 있으면 여기서 메우지 않는다. 그 차트가 3요소 오류로
    거부하고 라우트가 그 문면을 그대로 낸다 — 음수를 버리고 그리면 합계가 맞지
    않는 그림이 그럴듯하게 나온다(그 차트 머리말).
    """
    items = {
        f"편익 · {line.label}": float(line.annual_won)
        for line in report.basis.benefits
    }
    items.update({
        f"비용 · {line.label}": float(line.annual_won)
        for line in report.basis.costs
    })
    return {"items": items}


def _dispatch_stack(report: CaseReport) -> dict[str, Any]:
    """대표일 스텝별 자원 기여 + 부하 곡선.

    ## 부하를 **이름으로** 가른다 — 부호로 가르지 않는다

    `DispatchHour.per_resource` 는 자원과 부하를 한 사전에 담고 부호 규약은
    *「양수 = 내보냄 · 음수 = 받아들임」* 이다. 그런데 **저장장치의 충전도
    음수**라 부호만으로는 부하와 갈리지 않는다. 그래서 평가 대상 자원의 이름
    (`basis.resources`)에 **없는** 항목을 수요로 본다 — 두 곳이 같은 이름을
    쓴다는 것이 이 리포트 안의 실제 이음쇠다.

    ⚠ 그 이음쇠가 어긋나면 **멈춘다.** 스텝마다
    `Σ per_resource == grid_export − grid_import` 가 성립하는지 보고, 어긋나면
    거부한다. 어긋난 채로 그리면 스택과 부하선이 서로 다른 실행을 그리게 되고
    그림은 멀쩡해 보인다.

    ⚠ 값은 스텝당 kWh 이고 그 차트의 세로축 문면은 kW 다. 대표일이 24스텝이라
    스텝이 1시간이고 두 수가 같으므로 그대로 넘긴다 — 환산하지 않는다.
    """
    hours = report.dispatch_hours
    if not hours:
        raise _unwired_error("dispatch_stack", "이 실행에 대표일 운전 결과가 없다")

    resource_names = tuple(line.name for line in report.basis.resources)
    demand_names = sorted(
        {name for hour in hours for name in hour.per_resource}
        - set(resource_names)
    )
    if not demand_names:
        raise _unwired_error(
            "dispatch_stack",
            "대표일 운전에 수요 항목이 없다 — 자원별 기여만으로는 부하 곡선을 "
            "그릴 수 없고, 부하를 지어내면 스택이 무엇을 덮었는지가 거짓이 된다",
        )

    for hour in hours:
        drift = sum(hour.per_resource.values()) - (hour.grid_export - hour.grid_import)
        if abs(drift) > 1e-6:
            raise ValidationError(
                field="chart.dispatch_stack",
                reason=(
                    f"{hour.step}스텝의 자원 합계가 계통 수급과 어긋납니다 "
                    f"(차이 {drift:.6f} kWh)"
                ),
                action=(
                    "대표일 운전 결과가 한 실행에서 온 것인지 확인하십시오. "
                    "어긋난 채로 그리면 스택과 부하선이 서로 다른 실행을 그립니다"
                ),
            )

    return {
        "resource_dispatch": {
            name: [float(hour.per_resource[name]) for hour in hours]
            for name in resource_names
            if all(name in hour.per_resource for hour in hours)
        },
        "load": [
            -sum(float(hour.per_resource[name]) for name in demand_names)
            for hour in hours
        ],
    }


def _model_comparison(report: CaseReport) -> dict[str, Any]:
    """변형별 결론 축 — **등록 순서 그대로** (기준선이 맨 위다).

    ⚠ 표시명을 여기서 짓지 않는다. `variant_labels` 가 tag → 표시명을 이미
    갖고 있고 그 순서가 등록 순서다(`CaseReport.variant_labels`).
    ⚠ 지표 키를 박지 않는다 — `CONCLUSION_METRIC` 이 정본이다.
    """
    return {
        "model_comparison": {
            label: float(report.variants[tag][CONCLUSION_METRIC])
            for tag, label in report.variant_labels
        },
        "comparison_metric_label": _CONCLUSION_AXIS_LABEL,
    }


def _tornado(report: CaseReport) -> dict[str, Any]:
    """인자별 영향도 — `FR-803-AC2`.

    ⚠ **순위를 여기서 다시 매기지 않는다.** `CaseReport.influences` 가 이미
    내림차순이며(`FR-1002-AC1`), 화면의 「영향도 순위」 목록도 같은 순서를
    쓴다(`web/render.py::run_result_context`). 여기서 다시 정렬하면 그림과
    목록이 갈릴 수 있고, 갈려도 둘 다 그럴듯해 보인다.

    ⚠ `uncertain_influences`·`policy_influences` 로 가르지 않는다 — 가르면
    그림이 목록보다 짧아지고, 왜 짧은지는 그림에 적히지 않는다.
    """
    return {
        "influences": [
            {
                "name": entry.variable,
                "delta": float(entry.delta_won),
                "flips_conclusion": entry.flips_conclusion,
            }
            for entry in report.influences
        ]
    }


#: tag → 입력을 짓는 함수. **여기 없는 태그는 `UNWIRED` 가 사유를 갖는다.**
_BUILDERS = MappingProxyType({
    "cashflow_line": _cashflow_line,
    "cost_benefit_pie": _cost_benefit_pie,
    "dispatch_stack": _dispatch_stack,
    "model_comparison": _model_comparison,
    "tornado": _tornado,
})


def chart_data(report: CaseReport, tag: str) -> Mapping[str, Any]:
    """그 차트의 입력을 `CaseReport` 에서 짓는다.

    ⚠ 모르는 태그는 여기서 답하지 않는다 — 레지스트리가 정본이고, 그 판정은
    라우트가 `chart_registry()` 로 먼저 한다.
    """
    reason = unwired_reason(tag)
    if reason is not None:
        raise _unwired_error(tag, reason)
    return _BUILDERS[tag](report)
