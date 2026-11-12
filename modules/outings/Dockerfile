FROM node:22-slim AS app

ENV PNPM_HOME="/pnpm" \
    PATH="/pnpm:$PATH"
RUN corepack enable

WORKDIR /src

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages/ui/package.json packages/ui/package.json
COPY packages/app/package.json packages/app/package.json
COPY modules/outings/ui/package.json modules/outings/ui/package.json
RUN pnpm install --frozen-lockfile --filter @openarga/outings...

COPY tsconfig.base.json ./
COPY packages/ui packages/ui
COPY packages/app packages/app
COPY modules/outings/ui modules/outings/ui
RUN pnpm --filter @openarga/outings build

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /src

COPY pyproject.toml uv.lock ./
COPY modules/outings/pyproject.toml modules/outings/pyproject.toml
COPY packages/tenancy/pyproject.toml packages/tenancy/pyproject.toml
COPY packages/module/pyproject.toml packages/module/pyproject.toml
COPY packages/widgets/pyproject.toml packages/widgets/pyproject.toml
COPY packages/agenda/pyproject.toml packages/agenda/pyproject.toml
COPY packages/contracts/pyproject.toml packages/contracts/pyproject.toml
RUN uv sync --frozen --no-dev --package outings --no-install-workspace

COPY modules/outings/src modules/outings/src
COPY packages/tenancy/src packages/tenancy/src
COPY packages/module/src packages/module/src
COPY packages/widgets/src packages/widgets/src
COPY packages/agenda/src packages/agenda/src
COPY packages/contracts/src packages/contracts/src
RUN uv sync --frozen --no-dev --package outings --no-editable

FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UI_DIST=/opt/outings/ui

RUN useradd --system --uid 10001 --no-create-home modulo

COPY --from=builder /opt/venv /opt/venv
COPY modules/outings/manifest.yaml /opt/module/manifest.yaml
COPY modules/outings/schema /opt/module/schema

COPY --from=app /src/modules/outings/ui/dist /opt/outings/ui
COPY packages/ui/geo/countries.json /opt/outings/ui/geo/countries.json

USER modulo
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/readyz').status == 200 else 1)"

CMD ["sh", "-c", "python -m arga_module && exec uvicorn outings.main:app --host 0.0.0.0 --port 8000"]
