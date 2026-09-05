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
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

from app.security.authorization import ADMIN_ROLE
from app.services.ui_run import run_ui_case
from core.contracts.regulation import RegulationItem
from core.contracts.validation import ValidationError
from core.regulation.profile import RegulationProfileDraft
from web.render import (
    DEMO_MODEL,
    model_composer_context,
    regulation_admin_context,
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

#: 제도 편집 화면이 그리는 **데모 프로파일**. `RegulationProfileAdminService` 는
#: 빈 상태로 시작하므로(편집이 파일을 건드리지 않는 것이 FR-504-AC3 이다) 뿌리에서
#: 화면을 열면 그릴 것이 없다. 새 대장을 만들지 않고
#: `tests/app/test_regulation_admin_router.py` 가 지나는 것과 **같은 경로**
#: (`RegulationProfileDraft.create(...).upsert(...).publish()`) 로 한 벌 만든다.
_DEMO_PROFILE = (
    RegulationProfileDraft.create(name="현행", version="v2026.1")
    .upsert(
        RegulationItem(
            key="supply_duty.required_ratio",
            value=0.70,
            unit="비율",
            source="분산법 시행령",
        )
    )
    .publish()
)


@router.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    """대시보드 — 마법사와 고급 모드 (UI-1-AC1).

    **뿌리에 둔다.** 이 화면 뒤에 있는 것이 `NFR-301`(비개발자가 30분 안에 첫
    결과)이며, 뿌리에 아무것도 없으면 사람이 앱에서 처음 만나는 것이 `404` 다.
    """
    return HTMLResponse(render_dashboard())


@router.get("/ui/model-composer", response_class=HTMLResponse)
def model_composer() -> HTMLResponse:
    """자원 구성 화면 — FR-201-AC1 「GUI에서」."""
    return HTMLResponse(render_model_composer(model_composer_context(DEMO_MODEL)))


@router.get("/ui/regulation-admin", response_class=HTMLResponse)
def regulation_admin() -> HTMLResponse:
    """제도 프로파일 편집 화면 — FR-504-AC3 「웹 UI 에서」.

    역할을 `ADMIN_ROLE` 로 두는 것은 데모 값이다. **문자열 `"admin"` 을 여기
    적지 않는다** — 인가 규칙의 정본은 `app/security/authorization.py` 이고,
    화면이 역할 이름을 스스로 적으면 그 규칙이 두 곳에 생긴다.
    """
    return HTMLResponse(
        render_regulation_admin(
            regulation_admin_context(
                _DEMO_PROFILE,
                role=ADMIN_ROLE,
                when=date.today(),
                versions=(_DEMO_PROFILE.version,),
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
        run = run_ui_case(
            scenario,
            arrangement=arrangement or None,
            ownership_or_operation_transferred=ownership_or_operation_transferred,
            metering_separated=metering_separated,
        )
    except KeyError as exc:
        # `app/routers/models.py::_not_found` 와 같은 모양이다 — 목록 밖 이름은
        # 「틀린 입력」이 아니라 **없는 것**이므로 404 다.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        return HTMLResponse(render_run_result(run_error_context(exc)), status_code=400)
    return HTMLResponse(
        render_run_result(
            run_result_context(run.report, scenario_text=run.scenario_text)
        )
    )


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
