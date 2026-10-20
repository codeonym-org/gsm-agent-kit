# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.8.22 AS uv
FROM python:3.13-slim-bookworm AS python

FROM python AS build
COPY --from=uv /uv /bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /build
COPY pyproject.toml uv.lock ./
COPY libs/ libs/
COPY apps/server/ apps/server/
COPY apps/cli/ apps/cli/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --package gsm-agent-server \
      --extra zte-mf833t --extra inbox --extra sms --extra ai

FROM python AS zte-mf833t
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN groupadd --gid 10001 gsm && useradd --uid 10001 --gid gsm --no-create-home gsm \
    && mkdir -p /var/lib/gsm-agent /app \
    && chown gsm:gsm /var/lib/gsm-agent /app
COPY --from=build /opt/venv /opt/venv
COPY LICENSE NOTICE /usr/share/doc/gsm-agent-kit/
WORKDIR /app
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).close()"]
CMD ["gsm-agent-server", "--host", "0.0.0.0", "--port", "8000"]

# Fixture controls and test adapters are absent from the production target.
FROM zte-mf833t AS smoke
COPY deploy/smoke/ /smoke/
ENV PYTHONPATH=/smoke
