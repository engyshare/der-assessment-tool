"""FastAPI 앱 진입점 — 작업 14.6.

라우터는 ``collect_routers(app.routers)`` 로 **자동 수집**한다 (NFR-207-AC1).
중앙 등록 파일 없음 — 새 라우터는 ``app/routers/<name>.py`` 를 놓기만 하면 된다.
"""
from __future__ import annotations

from fastapi import FastAPI

import app.routers as routers_pkg
from app.routers import collect


def create_app() -> FastAPI:
    """FastAPI 앱 — 라우터 자동 수집으로 구성.

    팩토리 함수로 두는 이유: 테스트가 매번 새 앱을 만들 수 있고, ``collect_routers``
    가 «파일을 놓으면 늘어난다» 는 것을 검증 케이스가 직접 확인한다.
    """
    application = FastAPI(title="DER Evaluator API")
    routers = collect.collect_routers(routers_pkg)
    collect.assert_routers_present(routers)
    for r in routers:
        application.include_router(r)
    # «수집이 성립하지 않은 것» 을 «라우터가 없다» 로 읽지 않기 위해
    # 총 경로 수를 앱 state 에 기록 — 테스트가 접근한다.
    application.state.route_count = collect.count_routes(routers)
    return application


#: 모듈 import 시 앱을 만든다 — uvicorn ``app.main:app`` 으로 실행.
app = create_app()
