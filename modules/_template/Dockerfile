FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /src

COPY pyproject.toml uv.lock ./
COPY modules/__MODULE_ID__/pyproject.toml modules/__MODULE_ID__/pyproject.toml
COPY packages/tenancy/pyproject.toml packages/tenancy/pyproject.toml
COPY packages/module/pyproject.toml packages/module/pyproject.toml
COPY packages/widgets/pyproject.toml packages/widgets/pyproject.toml
RUN uv sync --frozen --no-dev --package __MODULE_ID__ --no-install-workspace

COPY modules/__MODULE_ID__/src modules/__MODULE_ID__/src
COPY packages/tenancy/src packages/tenancy/src
COPY packages/module/src packages/module/src
COPY packages/widgets/src packages/widgets/src
RUN uv sync --frozen --no-dev --package __MODULE_ID__ --no-editable

FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd --system --uid 10001 --no-create-home modulo

COPY --from=builder /opt/venv /opt/venv
COPY modules/__MODULE_ID__/manifest.yaml /opt/module/manifest.yaml
COPY modules/__MODULE_ID__/schema /opt/module/schema

USER modulo
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/readyz').status == 200 else 1)"

CMD ["sh", "-c", "python -m arga_module && exec uvicorn __MODULE_ID__.main:app --host 0.0.0.0 --port 8000"]
