FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /src

COPY pyproject.toml uv.lock ./
COPY gateway/pyproject.toml gateway/pyproject.toml
RUN uv sync --frozen --no-dev --package gateway --no-install-workspace

COPY gateway/src gateway/src
RUN uv sync --frozen --no-dev --package gateway --no-editable

FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd --system --uid 10002 --no-create-home gateway

COPY --from=builder /opt/venv /opt/venv

USER gateway
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=5 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status == 200 else 1)"

CMD ["sh", "-c", "exec uvicorn gateway.main:app --host 0.0.0.0 --port 8000"]
