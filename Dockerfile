FROM node:24-alpine AS web
WORKDIR /build
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.13-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY beanbot/ ./beanbot/
COPY --from=web /build/dist ./web/dist
EXPOSE 8000
# per-ledger 锁是进程内的，多开 worker 会丢并发写（ADR-0002）。
CMD ["uvicorn", "beanbot.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
