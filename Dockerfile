FROM python:3.11-slim

WORKDIR /app

# SC-5: DB 경로는 DER_DB_URL 환경변수로 설정
ENV DER_DB_URL=sqlite:///der.db

# FR-902: 시나리오 저장 자리도 환경변수로 설정 (SC-5 와 같은 규약).
# ⚠ 이름이 두 곳에 산다 — Dockerfile 은 파이썬을 import 할 수 없어 문자열이
# 불가피하다(위 DER_DB_URL 이 같은 처지다). 이 이름이 app/services/
# scenario_store_file.py 의 SCENARIO_STORE_ENV("DER_SCENARIO_STORE") 와 어긋나면
# 앱은 오류로 죽지 않고 저장을 조용히 인메모리로 되돌린다 — 프로세스가 죽는
# 순간 저장이 사라진다. tests/infra/test_scenario_store_deployment.py 가 그
# 어긋남을 이름 상수와 대조해 잡는다.
# 자리는 WORKDIR(/app) 밖이다 — COPY . . 로 소스가 /app 에 들어가므로 안에
# 두면 사용자 데이터가 소스 트리에 섞이고 이미지 재빌드에 덮인다.
ENV DER_SCENARIO_STORE=/data/scenarios

# 저장 자리를 미리 만든다. resolve_scenario_store_dir() 는 경로만 돌려주고
# 디렉터리를 만들지 않는다(첫 저장 때 저장소가 스스로 부모를 만들긴 하나,
# 마운트 자리를 이미지 안에 못박아 두는 것이 아래 VOLUME 선언의 짝이다).
RUN mkdir -p /data/scenarios

# 「여기가 영속해야 하는 자리다」를 사람과 도구에 알린다. docker run 에 -v 를
# 붙이지 않으면 익명 볼륨이 붙고 컨테이너를 지우는 순간 함께 사라진다 —
# README 의 실행 예시가 호스트 자리를 붙이는 형태다.
VOLUME ["/data/scenarios"]

# Install pip and any OS dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

# Install dependencies (only core + prod for runtime, maybe dev for testing)
# According to the brief, single container local run.
RUN pip install --no-cache-dir -e ".[persistence,api]"

COPY . .

# NFR-503-AC1: 단일 컨테이너로 로컬 실행 가능 (docker run 1회)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
