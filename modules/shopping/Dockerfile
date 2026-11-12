FROM node:22-slim AS app

ENV PNPM_HOME="/pnpm" \
    PATH="/pnpm:$PATH"
RUN corepack enable

WORKDIR /src

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages/ui/package.json packages/ui/package.json
COPY packages/app/package.json packages/app/package.json
COPY modules/shopping/ui/package.json modules/shopping/ui/package.json
RUN pnpm install --frozen-lockfile --filter @openarga/shopping...

COPY tsconfig.base.json ./
COPY packages/ui packages/ui
COPY packages/app packages/app
COPY modules/shopping/ui modules/shopping/ui
RUN pnpm --filter @openarga/shopping build

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /src

COPY pyproject.toml uv.lock ./
COPY modules/shopping/pyproject.toml modules/shopping/pyproject.toml
COPY packages/tenancy/pyproject.toml packages/tenancy/pyproject.toml
COPY packages/module/pyproject.toml packages/module/pyproject.toml
COPY packages/widgets/pyproject.toml packages/widgets/pyproject.toml
COPY packages/agenda/pyproject.toml packages/agenda/pyproject.toml
COPY packages/contracts/pyproject.toml packages/contracts/pyproject.toml
RUN uv sync --frozen --no-dev --package shopping --no-install-workspace

COPY modules/shopping/src modules/shopping/src
COPY packages/tenancy/src packages/tenancy/src
COPY packages/module/src packages/module/src
COPY packages/widgets/src packages/widgets/src
COPY packages/agenda/src packages/agenda/src
COPY packages/contracts/src packages/contracts/src
RUN uv sync --frozen --no-dev --package shopping --no-editable

FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UI_DIST=/opt/shopping/ui

RUN useradd --system --uid 10001 --no-create-home modulo

COPY --from=builder /opt/venv /opt/venv
COPY modules/shopping/manifest.yaml /opt/module/manifest.yaml
COPY modules/shopping/schema /opt/module/schema

COPY --from=app /src/modules/shopping/ui/dist /opt/shopping/ui

USER modulo
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/readyz').status == 200 else 1)"

CMD ["sh", "-c", "python -m arga_module && exec uvicorn shopping.main:app --host 0.0.0.0 --port 8000"]
