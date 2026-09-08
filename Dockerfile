FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

RUN groupadd --gid 1000 app && useradd --uid 1000 --gid 1000 --create-home app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_NO_SYNC=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Keep src/claims/ and data/ as siblings so DEFAULT_POLICY_DATA still resolves.
# uv sync installs the project editable; a wheel into site-packages would break that path.
COPY src ./src
COPY data ./data
RUN uv sync --frozen --no-dev && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "claims.api.routes:app", "--host", "0.0.0.0", "--port", "8000"]
