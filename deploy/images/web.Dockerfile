# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS build
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH
RUN corepack enable && corepack prepare pnpm@11.26.0 --activate
WORKDIR /build
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/ apps/web/
RUN --mount=type=cache,id=gsm-pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile --store-dir /pnpm/store
RUN pnpm web:build

FROM node:24-bookworm-slim AS realtime
ENV NODE_ENV=production GSM_REALTIME_HOST=0.0.0.0 GSM_REALTIME_PORT=3001
WORKDIR /app
COPY --from=build /build/apps/web/dist-server/ ./
COPY --from=build /build/apps/web/public/third-party-notices.txt ./
COPY LICENSE NOTICE /usr/share/doc/gsm-agent-kit/
USER node
EXPOSE 3001
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=10 \
    CMD ["node", "--input-type=module", "-e", "const r = await fetch('http://127.0.0.1:3001/health', {signal: AbortSignal.timeout(2000)}); if (!r.ok) process.exit(1)"]
CMD ["node", "index.mjs"]

FROM caddy:2-alpine AS console
ENV XDG_CONFIG_HOME=/tmp/config XDG_DATA_HOME=/tmp/data
# Port 8080 needs no low-port capability; retaining the file capability would
# prevent exec under the Compose profile's cap_drop: ALL.
RUN setcap -r /usr/bin/caddy
COPY --from=build /build/apps/web/dist/ /srv/
COPY deploy/images/Caddyfile /etc/caddy/Caddyfile
COPY LICENSE NOTICE /usr/share/doc/gsm-agent-kit/
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=10 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/_console/health"]
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
