"""app — 구획 WP-11.

Application 서비스 + FastAPI 라우터 (FR-901, FR-902, NFR-004, SC-1~SC-4)

소유 경로 밖 파일을 건드리지 않는다 (§16.1 W-1).

앱 진입점은 ``app.main:app`` — ``uvicorn app.main:app``. ``app/__init__`` 이
``app.main`` 을 import 하면 순환이 생기므로 여기서 import 하지 않는다.
"""
