"""화면을 내보내는 라우터 — UI-1-AC1 · FR-201-AC1 · FR-504-AC3.

## 왜 이 파일이 R62 에 생겼는가

`web/render.py` 는 세 화면을 이미 다 그려 놓고도 **시험에서만** 불렸다.
`grep -rn "HTMLResponse" app/` 이 0건이었다 — 앱이 화면을 아예 서빙하지 않았고,
그래서 「화면이 있다」를 말하던 검사들은 **배포 코드가 부르지 않는 함수**를 직접
불러 통과하고 있었다(이 저장소가 R26·R51·R52b 에 세 번 밟은 형태). 여기가
뚫는 것은 **그 함수들이 HTTP 로 나가는 구멍**이다.

## 이 라우터가 문맥을 조립하지 않는 이유

화면 문맥은 `web/render.py` 의 `*_context()` 하나씩이 정본이다. 출구가 문맥까지
지으면 출구마다 다른 문맥이 생기고, 그중 하나가 카탈로그를 줄여 그려도 아무
검사도 걸리지 않는다. 여기가 하는 일은 **경로를 고르고 문맥을 건네는 것**뿐이다.

## 데모 값을 여기 두는 이유 (지금뿐이다)

`role` 과 제도 프로파일은 아직 **요청에서 오지 않는다**. 세션에서 역할을 끌어
오는 것은 `FR-901` 인증 층의 일이고 그 층이 아직 역할을 들고 있지 않다
(`app/routers/regulation.py` 가 같은 사유로 역할을 질의 파라미터로 받는다).
여기서 세션 파싱을 흉내내면 **인증이 붙는 순간 두 곳이 역할을 판정**한다.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse, HTMLResponse

from app.routers.ui_forms import (
    DEMO_PROFILE_NAME,
    composer_config,
    refusal,
    regulation_view,
)
from app.security.authorization import ADMIN_ROLE
from app.services.ui_charts import chart_data
from app.services.ui_run import UiRun, run_ui_case
from core.contracts.validation import ValidationError
from core.report.charts import chart_registry, render_charts
from web.render import (
    chart_query,
    error_context,
    model_composer_context,
    regulation_admin_view_context,
    render_dashboard,
    render_model_composer,
    render_regulation_admin,
    render_run_result,
    run_error_context,
    run_result_context,
)

router = APIRouter(tags=["ui"])

#: 저장소 뿌리 — `app/routers/ui.py` 에서 두 단계 위. `reports.py` 와 같은 셈이다.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_STATIC_DIR = _REPO_ROOT / "web" / "static"

#: 목록 밖 이름을 열지 않을 때 알려 줄 media type — 확장자를 못 알아본 경우.
_FALLBACK_MEDIA_TYPE = "application/octet-stream"


@router.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    """대시보드 — 마법사와 고급 모드 (UI-1-AC1).

    **뿌리에 둔다.** 이 화면 뒤에 있는 것이 `NFR-301`(비개발자가 30분 안에 첫
    결과)이며, 뿌리에 아무것도 없으면 사람이 앱에서 처음 만나는 것이 `404` 다.
    """
    return HTMLResponse(render_dashboard())


@router.get("/ui/model-composer", response_class=HTMLResponse)
def model_composer() -> HTMLResponse:
    """자원 구성 화면 — FR-201-AC1 「GUI에서」.

    ⚠ `web.render.DEMO_MODEL` 을 **그대로** 그리지 않는다. 그러면 화면이 늘
    편집 전 구성을 보여 주고, 사용자가 방금 누른 복제·추가·삭제가 아무 데도
    나타나지 않는다 — R62/WP-5 가 브라우저로 확인한 것이 그 상태다. 그릴
    것은 **자원 편집 API 가 보관하는 그것**이며 `composer_config()` 가 같은
    서비스에서 가져온다.
    """
    return HTMLResponse(
        render_model_composer(model_composer_context(composer_config()))
    )


@router.get("/ui/regulation-admin", response_class=HTMLResponse)
def regulation_admin(
    profile: str = Query(
        default=DEMO_PROFILE_NAME,
        description="열어 볼 제도 프로파일 이름 — 보관된 것만 연다",
    ),
) -> HTMLResponse:
    """제도 프로파일 편집 화면 — FR-504-AC3 「웹 UI 에서」.

    역할을 `ADMIN_ROLE` 로 두는 것은 데모 값이다. **문자열 `"admin"` 을 여기
    적지 않는다** — 인가 규칙의 정본은 `app/security/authorization.py` 이고,
    화면이 역할 이름을 스스로 적으면 그 규칙이 두 곳에 생긴다.

    ⚠ **어느 프로파일을 볼지 질의 파라미터로 받는다.** 늘 데모 한 벌만 그리면
    화면에서 만든 프로파일이 어디에도 나타나지 않고, 사용자에게 그것은
    「생성이 안 됐다」와 구별되지 않는다. 폼이 성공하면 그 이름으로 되돌아온다
    (`app/routers/ui_forms.py::_regulation_url`).
    """
    try:
        view = regulation_view(profile)
    except HTTPException as exc:
        return refusal(
            exc,
            field="regulation.profile_name",
            action="보관된 프로파일 이름으로 여십시오",
        )
    return HTMLResponse(
        render_regulation_admin(
            regulation_admin_view_context(
                view, role=ADMIN_ROLE, versions=(str(view["version"]),)
            )
        )
    )


@router.get("/ui/run", response_class=HTMLResponse)
def run_case(
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
) -> HTMLResponse:
    """고른 갈래로 한 번 돌려 결과 화면을 낸다 — `FR-705-AC2` · `UI-7-AC1`.

    ## ⚠⚠⚠ `POST` 가 아니라 `GET` 이다 — 세 이유가 함께 선다

    ① **새 의존성이 안 든다.** FastAPI 의 `POST` 폼(`Form(...)`)은
    `python-multipart` 를 요구하고 그것은 `pyproject.toml` 에 없다.
    ② **의미가 맞다.** 실행은 읽기 전용이며 저장소·대장에 아무것도 쓰지
    않는다(임시 시나리오는 `TemporaryDirectory` 안에서 나고 죽는다).
    ③ **결과가 링크가 된다.** `/ui/run?scenario=…&arrangement=…` 하나로 그
    결과를 다시 열 수 있고, 심의에서 이것이 값을 한다.

    ⚠ **빈 `arrangement` 를 기본 갈래 문면으로 바꾸지 않는다.** 화면의
    「고르지 않음」이 그대로 *「필드를 적지 않았다」* 로 내려가야
    `resolve_baseline_arrangement` 하나가 기본값을 정한다 — 여기서 채우면
    기본값이 두 곳에 살고, 한쪽만 고쳐지는 날 층마다 다른 갈래로 돌면서
    아무 예외도 나지 않는다.

    ⚠ **거부를 `_bad_request()` 처럼 JSON 으로 내지 않는다.** 이 라우트는
    화면이고, JSON 을 받은 브라우저는 3요소를 사람이 읽을 모양으로 그리지
    못한다. **낮추는 것은 형식뿐이고 내용은 같다** — 필드·사유·조치 셋을
    `web/render.py::run_error_context` 가 그대로 옮긴다 (`NFR-303`).
    """
    try:
        run = _run(
            scenario,
            arrangement,
            ownership_or_operation_transferred,
            metering_separated,
        )
    except ValidationError as exc:
        return HTMLResponse(render_run_result(run_error_context(exc)), status_code=400)
    except KeyError as exc:
        # ★ **D3** — 목록 밖 시나리오도 화면으로 온다. 전에는 `_run()` 이 이것을
        # `HTTPException(404, str(exc))` 로 바꿨고, 그래서 브라우저가 받은 것은
        # 영어 JSON 이었다. `str(KeyError)` 는 `repr` 이므로 **문면에 겹따옴표를
        # 덧씌운다** — `exc.args[0]` 이 저장소가 실제로 적은 문장이다.
        return HTMLResponse(
            render_run_result(_missing_scenario(exc)), status_code=404
        )
    return HTMLResponse(
        render_run_result(
            run_result_context(
                run.report,
                scenario_text=run.scenario_text,
                # ★ 그림도 **이 실행의** 것이어야 한다. 기본값으로 그리면 화면의
                # 수는 ⓒ 인데 그림은 ⓑ 인 상태가 나오고, 둘 다 그럴듯해 보인다.
                chart_query=chart_query(
                    scenario=scenario,
                    arrangement=arrangement,
                    ownership_or_operation_transferred=(
                        ownership_or_operation_transferred
                    ),
                    metering_separated=metering_separated,
                ),
            )
        )
    )


def _run(
    scenario: str,
    arrangement: str,
    ownership_or_operation_transferred: bool,
    metering_separated: bool,
) -> UiRun:
    """폼 값으로 한 번 돌린다 — **거부도 「없다」도 그대로 올린다.**

    ⚠ 여기서 `HTTPException` 으로 낮추지 않는다. 거부의 표현 형식(화면이냐
    JSON 이냐)은 부르는 라우트가 정할 일이고, 여기서 정하면 화면 라우트가
    사람이 못 읽는 JSON 을 내게 된다 — R62/WP-5 가 브라우저로 잡은 **D3** 이
    정확히 그 상태였다. `ValidationError` 를 이미 그렇게 다루고 있었고,
    `KeyError` 만 예외였다.
    """
    return run_ui_case(
        scenario,
        arrangement=arrangement or None,
        ownership_or_operation_transferred=ownership_or_operation_transferred,
        metering_separated=metering_separated,
    )


def _missing_scenario(exc: KeyError) -> dict[str, object]:
    """목록 밖 시나리오를 **3요소로** 옮긴다 (`NFR-303`).

    ⚠ **사유를 새로 짓지 않는다.** `app/services/ui_run.py` 가 「무엇이 없고
    고를 수 있는 것은 무엇인가」를 이미 적었다. 여기서 다시 지으면 같은 거부가
    그림 라우트(`/ui/chart/<태그>.png`)와 화면에서 다른 말을 한다.

    ⚠ `str(exc)` 를 쓰지 않는다. `KeyError.__str__` 은 `repr(args[0])` 이라
    문면에 **겹따옴표가 덧씌워진다** — 사람이 읽는 문장에 그 따옴표가 실린
    것이 WP-5 가 인용한 실측이다.
    """
    return error_context(
        field="run.scenario",
        reason=str(exc.args[0]),
        action="화면의 시나리오 목록에서 고르십시오",
    )


@router.get("/ui/chart/{tag}.png", response_class=Response)
def chart_png(
    tag: str,
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
) -> Response:
    """차트 한 장을 **PNG 로** 낸다 — `FR-1004-AC1` · `FR-803-AC2`.

    ## ★ 그림을 여기서 다시 그리지 않는다

    `core/report/charts/` 의 7종이 이미 `Chart` 계약을 지키고 matplotlib 으로
    PNG 바이트를 낸다. 손으로 SVG 를 다시 그리면 **같은 그림이 두 곳에 살고**
    그 순간 「화면의 수가 리포트와 어긋난다」가 구조적으로 가능해진다.
    이 라우트가 하는 일은 **입력을 리포트에서 지어 넘기고 바이트를 내보내는
    것**뿐이다.

    ⚠ `media_type` 을 여기 박지 않는다 — `ChartArtifact.mime` 이 갖고 있고,
    그 계약은 *「지금은 전부 PNG 이나 SVG 차트가 섞일 수 있어 선언으로 둔다」*
    고 적었다. 박으면 SVG 차트가 서는 날 브라우저가 SVG 를 PNG 라고 듣는다.

    ## 상태 코드 셋과 그 근거

    | 형편 | 코드 | 근거 |
    |---|---|---|
    | 모르는 `tag` | **404** | 그런 그림이 **없다**. 등록 태그 목록을 문면에 |
    |  |  | 싣는다 — `render_charts` 가 쓰는 관용구다 |
    | 목록 밖 시나리오 | **404** | `_run()` — `/ui/run` 과 같은 판정이다 |
    | 갈래·전제가 틀렸다 | **400** | 보낸 쪽이 고칠 수 있다 (`DV-15` 가 든다) |
    | 재료가 없어 못 그린다 | **501** | 아래 ★ |

    ★ **500 이 아니다.** 500 은 「우리가 깨졌다」이고 이것은 「**아직 배선되지
    않았다**」이다. 404 도 아니다 — 404 로 내면 「그런 차트가 없다」와 같아져
    §13.0.1 ④ 가 금지한 「구현이 없다와 수집이 안 됐다를 같게 읽기」가 된다.
    501(Not Implemented)이 그 뜻을 그대로 갖는 유일한 칸이다.

    ⚠ 재료가 없을 때 **빈 PNG 를 내지 않는다.** 빈 그림은 「그렸다」로 집계되고
    그 빈자리는 심의자료가 인쇄된 뒤에 발견된다 (`ChartArtifact.__post_init__`
    가 같은 자리에서 같은 판단을 한다).
    """
    registry = chart_registry()
    if tag not in registry:
        raise HTTPException(
            status_code=404,
            detail=(
                f"차트 {tag!r} 이(가) 없습니다. 등록된 차트는 "
                f"{', '.join(sorted(registry))} 입니다"
            ),
        )
    try:
        run = _run(
            scenario,
            arrangement,
            ownership_or_operation_transferred,
            metering_separated,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=_three_parts(exc)) from exc
    except KeyError as exc:
        # `app/routers/models.py::_not_found` 와 같은 모양이다 — 목록 밖 이름은
        # 「틀린 입력」이 아니라 **없는 것**이므로 404 다. 이 라우트는 `<img>`
        # 자리에 들어가므로 화면이 아니라 JSON 으로 낸다.
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc

    try:
        # ⚠ `registry[tag]().render(...)` 로 질러가지 않는다. `render_charts` 가
        # **배포 코드가 부르지 않는 함수**였다는 것이 이 WP 가 뚫는 구멍이고,
        # 질러가면 그 함수는 여전히 시험만 부르는 채로 남는다. 태그를 명시해
        # 부르는 것이 그 함수가 요구하는 사용법이다.
        artifact = render_charts(chart_data(run.report, tag), tags=(tag,))[tag]
    except ValidationError as exc:
        # 「재료가 없다」와 「차트가 입력을 거부했다」를 가르지 않는다 — 둘 다
        # *이 리포트로는 이 그림을 그릴 수 없다* 이고, 사유 문면이 어느 쪽인지
        # 말한다. 가르면 사유는 같은데 코드만 둘이 된다.
        raise HTTPException(status_code=501, detail=_three_parts(exc)) from exc

    return Response(content=artifact.payload, media_type=artifact.mime)


def _three_parts(exc: ValidationError) -> dict[str, str]:
    """거부를 **필드·사유·조치 셋 그대로** 옮긴다 (`NFR-303`).

    ⚠ 문면을 새로 짓지 않는다 — 새로 지으면 같은 거부가 화면
    (`web/render.py::run_error_context`)과 여기서 다른 말을 하게 되고, 그때
    어느 쪽이 맞는지는 아무 검사도 말하지 않는다.
    """
    return {"field": exc.field, "reason": exc.reason, "action": exc.action}


@router.get("/static/{filename}", response_class=FileResponse)
def static_file(filename: str) -> FileResponse:
    """`web/static/` 의 파일 하나 — 템플릿 머리가 `/static/wp12.css` 를 가리킨다.

    ⚠ **이름을 경로로 그대로 잇지 않는다.** `../` 이 섞이면 저장소 밖 파일을
    내보내게 된다. `reports.py::_scenario_path()` 와 같은 모양으로 **목록에
    있는 것만 연다** — 경로 정규화로 막으면 다음 사람이 정적 파일을 늘릴 때
    그 정규화를 다시 짜야 하고, 그 사이 어긋남은 아무도 보지 못한다.

    `StaticFiles` 를 `app/main.py` 에 mount 하지 않는 것은 그것이 **중앙 등록
    파일을 고치게** 만들기 때문이다 — 「`app/routers/<name>.py` 를 놓기만 하면
    된다」가 `NFR-207-AC1` 이다.
    """
    available = sorted(path.name for path in _STATIC_DIR.iterdir() if path.is_file())
    if filename not in available:
        raise HTTPException(
            status_code=404,
            detail=(
                f"정적 파일 {filename!r} 이(가) 없습니다. 사용할 수 있는 것: "
                f"{', '.join(available)}"
            ),
        )
    # 확장자로 정한다. 못 알아보면 `text/plain` 이 아니라 옥텟 스트림이다 —
    # 알아보지 못한 것을 텍스트라고 말하면 브라우저가 그대로 믿는다.
    media_type, _ = mimetypes.guess_type(filename)
    return FileResponse(
        _STATIC_DIR / filename, media_type=media_type or _FALLBACK_MEDIA_TYPE
    )
