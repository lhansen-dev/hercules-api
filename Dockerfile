# ── Build stage ────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS build

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy project metadata first so dependency layer is cached separately.
COPY pyproject.toml uv.lock* ./
COPY src/ src/

# Build a virtual environment with production deps only (no dev group).
RUN uv sync --frozen --no-dev --no-editable

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# zbar is required by pyzbar for barcode decoding.
RUN apt-get update && apt-get install -y --no-install-recommends libzbar0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only the built venv and package source from the build stage.
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/src /app/src

# Make the venv the active Python.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uvicorn", "hercules_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
