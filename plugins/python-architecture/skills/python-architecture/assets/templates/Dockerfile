# syntax=docker/dockerfile:1
# Multi-stage build: uv resolves from the lockfile in the builder,
# the runtime image only gets the virtualenv and the source.

FROM python:{{python_version}}-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Install dependencies first (cached layer, only rebuilt when the lockfile changes)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Then install the project itself
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

FROM python:{{python_version}}-slim AS runtime
RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app
COPY --from=builder --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
CMD ["uvicorn", "{{package_name}}.main:app", "--host", "0.0.0.0", "--port", "8000"]
