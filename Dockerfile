FROM python:3.11-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (separate layer for cache efficiency)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[all]"

# ---- Build stage: copy application code ----
FROM base AS app

COPY . .

# Create data directory for SQLite persistence
RUN mkdir -p /app/data && chmod 755 /app/data

# Default DATABASE_URL uses the data volume
ENV DATABASE_URL="sqlite+aiosqlite:////app/data/yojimbo.db"

# Run Alembic migrations then start the server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1
