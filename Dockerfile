# Multi-stage build for FastAPI app without modifying code
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose uvicorn port
EXPOSE 8000

# Default to SQLite unless overridden
ENV ENV=production \
    DEBUG=false \
    UPLOAD_DIR=/data/uploads \
    DATABASE_URL=sqlite+aiosqlite:///./lms_sae.db \
    CORS_ORIGINS=http://localhost:3000;http://localhost:8000

# Create data dir
RUN mkdir -p /data/uploads

# Run uvicorn using the existing FastAPI app
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
