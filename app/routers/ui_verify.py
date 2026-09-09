"""검증 모드 화면을 내보내는 라우터 — 사용자 판정 §1 「결과」.

## 왜 이 파일이 R63 에 생겼는가

중간값을 단계별로 늘어놓는 렌더러(`core/report/verification.py::
render_verification_markdown`)는 **R52 부터 있었다.** 그런데 저장소 전체에서
그것을 부르는 곳이 `app/run/report_cli.py`(CLI `--kind verification`) **하나**
였다 — 사용자가 요구한 *「순차적 중간값 제시」* 는 재료도 렌더러도 서 있고
**화면에만 안 붙어 있었다.** 이 저장소가 반복해 밟은 *「부품은 있는데 부르는
배포 코드가 없다」* 와 같은 형태이며(`app/routers/ui.py` 머리말이 R26·R51·R52b
를 적는다), 여기가 뚫는 것은 그 구멍이다.

## 이 라우터가 문맥을 조립하지 않는 이유

`web/render_verify.py::verify_context` 하나가 정본이다. 출구가 문맥까지 지으면
출구마다 다른 문맥이 생기고, 그중 하나가 걸음을 줄여 그려도 아무 검사도
걸리지 않는다 — `app/routers/ui.py` 가 같은 판단을 적어 두었다.

## 질의 파라미터가 `/ui/run` 과 같은 이유

**같은 실행을 두 화면으로 보는 것**이 검증 모드의 뜻이다. 결과 화면의 주소에
붙은 질의를 그대로 `/ui/verify` 에 붙이면 같은 실행의 중간값이 나와야 하며,
파라미터가 갈리면 화면의 수는 ⓒ 인데 중간값은 ⓑ 인 상태가 나오고 둘 다
그럴듯해 보인다. ⚠ 기본값을 여기 다시 적지 않고 `/ui/run` 과 같은 자리를
쓴다 — 빈 `arrangement` 는 **시나리오에 적지 않는다**는 뜻이며 그 판정은
`core/cba/baseline.py::resolve_baseline_arrangement` 하나가 갖는다.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from app.services.ui_run import run_ui_case
from app.services.verify_steps import VerificationStageError
from core.contracts.validation import ValidationError
from web.render import (
    chart_figures,
    chart_query,
    error_context,
    run_error_context,
)
from web.render_load_shape import SHIFTABLE_SHARE_FIELD, appliance_season_shares
from web.render_verify import render_verify, verify_context

router = APIRouter(tags=["ui"])

#: ① 걸음의 계절 표 아래에 세울 그림의 태그 (R65/WP-3 · 사용자 요구 —
#: *「검증 모드에서 확인이 어렵다」*). ⚠ 여기서 새로 정하는 이름이 아니라
#: 차트 레지스트리가 등록한 태그다(`core/report/charts/`). 검증 모드는 계절
#: 운전을 **대조하는** 자리이므로 일곱을 다 실으면 `/ui/run` 의 사본이 된다.
_SEASONAL_CHART_TAG = "seasonal_operation"


@router.get("/ui/verify", response_class=HTMLResponse)
def verify_case(
    # ⚠ `*` 는 **양식이 아니라 규칙**이다 (R64/WP-2 — R64/WP-1 이 그림
    # 라우트에서 세운 것과 같다). 기기 부하 질의 둘이 붙어 인자가 일곱이 되자
    # `PLR0917`(위치 인자 5 초과)이 울었다. FastAPI 는 키워드 전용 인자를
    # 그대로 받으므로 라우트의 동작은 한 글자도 바뀌지 않는다. **상한을 올려
    # 푸는 쪽을 고르지 않았다.**
    *,
    scenario: str = Query(
        default="scenario_unsubsidized",
        description="골든 시나리오 이름 — 목록에 있는 것만 연다",
    ),
    arrangement: str = Query(
        default="",
        description="기준선 갈래의 값 문면. **비우면 시나리오에 적지 않는다**",
    ),
    ownership_or_operation_transferred: bool = Query(
        default=False,
        description="ⓒ 전제 ① — 자가용 설비의 소유 또는 운영권 인계",
    ),
    metering_separated: bool = Query(
        default=False,
        description="ⓒ 전제 ② — 발전량·전기사용량의 구분 계측·정산",
    ),
    household_count: str = Query(
        default="",
        description=(
            "실증단지 참여 가구 수(호). **비우면 시나리오에 적지 않는다** — "
            "그때 가구 한 호 기준으로 돈다"
        ),
    ),
    heatpump_load_annual_kwh: str = Query(
        default="",
        description=(
            "가구 한 호의 히트펌프 연간 소비전력량(kWh/호·년). "
            "**비우면 시나리오에 적지 않는다** — 그때 0으로 돈다"
        ),
    ),
    ev_load_annual_kwh: str = Query(
        default="",
        description=(
            "가구 한 호의 전기차 충전 연간 전력량(kWh/호·년). "
            "**비우면 시나리오에 적지 않는다** — 그때 0으로 돈다"
        ),
    ),
    dr_shiftable_share_pct: str = Query(
        default="",
        alias=SHIFTABLE_SHARE_FIELD,
        description=(
            "하루 안에서 옮길 수 있는 가전 부하 비율(%). "
            "**비우면 오버라이드를 걸지 않는다** — 그때 분석 설정 대장의 "
            "가정값으로 돈다(0 을 적으면 「옮기지 않는다」라는 다른 실행이다)"
        ),
    ),
    # ★★ 계절 몫은 `Query(...)` 가 아니다 — 계절을 **자산**이 정하므로 칸
    # 이름이 자산과 함께 변한다(`app/routers/ui.py::run_case` 의 같은 주석).
    # ⚠ 이 라우트가 그것을 안 받으면 **결과 화면의 주소를 그대로 붙여도**
    # 중간값은 계절 몫 없이 돈 것이 되고, 이 파일 머리말이 적은 *「화면의
    # 수는 ⓒ 인데 중간값은 ⓑ」* 가 형상 축에서 다시 선다.
    request: Request,
) -> HTMLResponse:
    """분석 과정의 중간값을 **네 걸음으로 순차적으로** 낸다.

    ⚠ **거부를 JSON 으로 내지 않는다.** 이 라우트는 화면이고, JSON 을 받은
    브라우저는 3요소를 사람이 읽을 모양으로 그리지 못한다 (`NFR-303`).

    ⚠⚠ `VerificationStageError` 를 **삼키지 않는다.** 렌더러가 단계를 늘렸는데
    화면이 일부만 그리면 사용자는 없는 단계를 찾을 때까지 모른다 — 그래서
    「무엇이 어긋났는가」를 3요소로 적어 500 이 아닌 **읽을 수 있는 거부**로
    낸다. 조용히 여덟만 그리는 쪽을 고르지 않는다.
    """
    # ★ 계절 몫 질의를 **한 번만** 짓는다 (R65/WP-3). 아래 실행과 그림 주소가
    # 같은 것을 쓰며, 따로 짓면 어느 한쪽만 계절 몫이 든 그림/중간값이 선다.
    season_shares = appliance_season_shares(request.query_params)
    try:
        run = run_ui_case(
            scenario,
            arrangement=arrangement or None,
            ownership_or_operation_transferred=ownership_or_operation_transferred,
            metering_separated=metering_separated,
            # ★ 빈 문면을 `None` 으로 낮춘다 — 위 `arrangement` 와 같은 규약이며,
            # 「적지 않았다」가 그대로 내려가야 판정이 한 자리에 남는다
            # (`core/casegrid/household_scale.py::resolve_household_count`).
            household_count=household_count or None,
            # ★ 기기 부하 둘도 같은 규약이다 (R64/WP-2) — 판정은
            # `core/casegrid/appliance_load.py::resolve_appliance_load` 하나다.
            heatpump_load_annual_kwh=heatpump_load_annual_kwh or None,
            ev_load_annual_kwh=ev_load_annual_kwh or None,
            # ★ 부하의 형상 둘도 같은 규약이다 (R64/WP-WEB ⓐⓑ) — 판정은
            # `resolve_shiftable_share` ·
            # `resolve_appliance_season_shares` 하나씩이다. ⚠ 계절 몫은
            # 빈 칸까지 실어 보낸다(거두는 함수의 ⚠⚠ 절).
            dr_shiftable_share_pct=dr_shiftable_share_pct or None,
            appliance_load_season_shares=season_shares,
        )
    except ValidationError as exc:
        return HTMLResponse(render_verify(run_error_context(exc)), status_code=400)
    except KeyError as exc:
        # `str(KeyError)` 는 `repr` 이라 문면에 겹따옴표를 덧씌운다 —
        # `exc.args[0]` 이 저장소가 실제로 적은 문장이다(`ui.py` 의 D3 주석).
        return HTMLResponse(
            render_verify(
                error_context(
                    field="scenario",
                    reason=str(exc.args[0]),
                    action="목록에 있는 골든 시나리오 이름으로 여십시오",
                )
            ),
            status_code=404,
        )
    try:
        context = verify_context(run.report)
    except VerificationStageError as exc:
        return HTMLResponse(
            render_verify(
                error_context(
                    field="core.report.verification",
                    reason=str(exc),
                    action=(
                        "검증 보고서 렌더러의 단계 구성이 바뀌었습니다. "
                        "`app/services/verify_steps.py` 의 걸음 배치를 함께 "
                        "고치십시오 — 화면이 일부만 그리지 않도록 여기서 "
                        "멈춥니다"
                    ),
                )
            ),
            status_code=500,
        )
    # ★★ ① 걸음의 계절별 도표 (R65/WP-3). 칸을 짓는 것·질의를 잇는 것 모두
    # `/ui/run` 이 쓰는 함수를 그대로 부른다 — 여기서 새로 지면 같은 그림이
    # 두 곳에 살고, 화면의 수가 리포트와 갈릴 수 있다(그림 라우트 독스트링).
    context["seasonal_figure"] = _seasonal_figure(
        scenario=scenario,
        arrangement=arrangement,
        ownership_or_operation_transferred=ownership_or_operation_transferred,
        metering_separated=metering_separated,
        household_count=household_count,
        heatpump_load_annual_kwh=heatpump_load_annual_kwh,
        ev_load_annual_kwh=ev_load_annual_kwh,
        dr_shiftable_share_pct=dr_shiftable_share_pct,
        season_shares=season_shares,
    )
    return HTMLResponse(render_verify(context))


def _seasonal_figure(
    *,
    scenario: str,
    arrangement: str,
    ownership_or_operation_transferred: bool,
    metering_separated: bool,
    household_count: str,
    heatpump_load_annual_kwh: str,
    ev_load_annual_kwh: str,
    dr_shiftable_share_pct: str,
    season_shares: Mapping[str, str] | None,
) -> dict[str, Any] | None:
    """① 걸음의 그림 칸 — `chart_figures` 가 지은 것에서 **태그 하나만 고른다**.

    ⚠⚠ **그림을 여기서 다시 짓지 않는다.** 칸의 재료(라벨·alt·출처·배선 안 된
    칸의 사유)는 `web/render_run.py::chart_figures` 가 이미 짓고, 검증 라우트가
    하는 일은 일곱 칸에서 `seasonal_operation` 하나를 고르는 것뿐이다.
    필터 인자를 그 함수에 새로 다는 쪽을 고르지 않은 이유: 이 함수의 다른
    호출자(`run_result_context`)가 일곱 칸 전부를 쓰므로, 인자를 다는 순간
    그 호출자까지 함께 건드려야 한다 — 호출부에서 거르면 아무도 안 움직인다.

    ★★ 질의를 잇는 것도 `/ui/run` 이 부르는 `chart_query` 와 **인자가 한 칸씩
    같다** (`app/routers/ui.py::run_case`). 하나라도 빠뜨리면 화면의 표는
    `household_count=20` 로 돈 것인데 그림은 1호(또는 대장 기본값)로 그린다 —
    둘 다 그럴듯해 보이고, 그 어긋남은 아무 오류도 내지 않는다.

    ⚠ 레지스트리가 이 태그를 더는 싣지 않으면 `None` 을 돌려 템플릿이 칸을
    그리지 않는다. 조용히 사라지는 것처럼 보이나 **그때 빨간불을 내는 검사가
    이 화면의 `<img>` 를 세고 있다**(`tests/app/test_ui_verify.py` 의 R65/WP-3
    절) — 칸을 지키는 것은 검사 몫이다.
    """
    query = chart_query(
        scenario=scenario,
        arrangement=arrangement,
        ownership_or_operation_transferred=ownership_or_operation_transferred,
        metering_separated=metering_separated,
        household_count=household_count,
        heatpump_load_annual_kwh=heatpump_load_annual_kwh,
        ev_load_annual_kwh=ev_load_annual_kwh,
        dr_shiftable_share_pct=dr_shiftable_share_pct,
        appliance_season_shares=season_shares,
    )
    return next(
        (
            figure
            for figure in chart_figures(query=query)
            if figure["tag"] == _SEASONAL_CHART_TAG
        ),
        None,
    )
