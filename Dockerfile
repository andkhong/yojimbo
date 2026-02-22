FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[all]"

# Copy app
COPY . .

# Run Alembic migrations on start, then launch
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

EXPOSE 8000
