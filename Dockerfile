# ChainLens 服務映像：同一映像可跑 FastAPI 或 Streamlit，由啟動指令決定。
# Render / Railway 皆會注入 $PORT，容器須綁 0.0.0.0:$PORT。
FROM python:3.11-slim

# uv：沿用 uv.lock 做可重現安裝
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# 先只複製依賴宣告 → 安裝依賴（利用 Docker layer 快取，程式碼改動不必重裝 torch）
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# 再放程式碼並把 smelens 套件裝進 venv
COPY smelens ./smelens
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# 預設啟動 FastAPI；Streamlit 服務在 render.yaml 以 dockerCommand 覆寫本行。
CMD ["sh", "-c", "uvicorn smelens.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
