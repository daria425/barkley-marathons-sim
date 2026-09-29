FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Dependencies first so this layer only rebuilds when pyproject.toml/uv.lock change, not on
# every source edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Invoke the pre-built venv's uvicorn directly, not `uv run uvicorn` — `uv run` re-syncs the
# environment against pyproject/uv.lock on every single container start (including default
# dependency groups, so it was re-downloading and reinstalling ruff/hypothesis on every boot
# despite --no-dev at build time), which is wasted time and a real memory/CPU spike on a
# 256MB machine, and contributed to an OOM crash loop in prod. The venv is already correct
# from the build step above; nothing at runtime should touch it again.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
