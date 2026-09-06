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

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from app.services.ui_run import run_ui_case
from app.services.verify_steps import VerificationStageError
from core.contracts.validation import ValidationError
from web.render import error_context, run_error_context
from web.render_load_shape import SHIFTABLE_SHARE_FIELD, appliance_season_shares
from web.render_verify import render_verify, verify_context

router = APIRouter(tags=["ui"])


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
            appliance_load_season_shares=appliance_season_shares(
                request.query_params
            ),
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
    return HTMLResponse(render_verify(context))
