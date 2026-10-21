# syntax=docker/dockerfile:1
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1 PORT=3000

# Dependencies first (cached layer), then the project itself
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project
COPY README.md ./
COPY src ./src
COPY fixtures ./fixtures
RUN uv sync --locked --no-dev

RUN useradd --create-home coach
USER coach
EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:3000/health')"]

# uvicorn is PID 1: SIGTERM → graceful shutdown → spans flushed in the FastAPI lifespan
CMD ["/app/.venv/bin/coach-serve"]
