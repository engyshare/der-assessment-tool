"""app.routers — FastAPI 라우터 자동 수집 대상.

**이 파일에 ``from .x import router`` 를 나열하지 않는다** (NFR-207-AC1 위반).
``collect_routers(app.routers)`` 가 패키지를 스캔해 자동으로 찾는다.

새 라우터를 추가하려면:
    1. 이 폴더에 ``<name>.py`` 를 만든다
    2. 그 안에 ``router = APIRouter(...)`` 를 선언한다
    3. 어느 «등록 파일» 도 고치지 않는다

이 빈 모듈은 «자동 수집이 패키지를 인식한다» 는 것의 최소 조건이다 — 라우터가
하나도 없으면 ``assert_routers_present`` 가 기동을 막는다.
"""
