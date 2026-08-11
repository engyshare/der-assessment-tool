FROM python:3.11-slim

WORKDIR /app

# SC-5: DB 경로는 DER_DB_URL 환경변수로 설정
ENV DER_DB_URL=sqlite:///der.db

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
