FROM node:22-slim AS builder

ENV PNPM_HOME="/pnpm" \
    PATH="/pnpm:$PATH" \
    NEXT_TELEMETRY_DISABLED=1
RUN corepack enable

WORKDIR /src

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages/ui/package.json packages/ui/package.json
COPY shell/package.json shell/package.json
RUN pnpm install --frozen-lockfile --filter @openarga/shell...

COPY tsconfig.base.json ./
COPY packages/ui packages/ui
COPY scripts/make-pwa.mjs scripts/make-pwa.mjs
COPY shell shell
RUN pnpm --filter @openarga/shell build

FROM node:22-slim AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN useradd --system --uid 10003 --no-create-home shell

COPY --from=builder /src/shell/.next/standalone ./
COPY --from=builder /src/shell/.next/static ./shell/.next/static
COPY --from=builder /src/shell/public ./shell/public

USER shell
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=5 \
  CMD node -e "require('http').get('http://127.0.0.1:3000/',r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"

CMD ["node", "shell/server.js"]
