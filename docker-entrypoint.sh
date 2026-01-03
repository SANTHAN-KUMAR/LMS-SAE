#!/bin/bash
# ================================================
# Docker Entrypoint Script
# ================================================
# Handles initialization before starting the app

set -e

echo "================================================"
echo "  LMS-SAE Examination Middleware"
echo "  Starting up..."
echo "================================================"

# Wait for database to be ready
echo "Waiting for database..."
while ! pg_isready -h "${POSTGRES_HOST:-db}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-postgres}" -q; do
    echo "Database is unavailable - sleeping"
    sleep 2
done
echo "Database is ready!"

# Run database migrations/initialization
echo "Initializing database..."
python -c "
import asyncio
from app.db.database import init_db
asyncio.run(init_db())
print('Database initialized successfully!')
" || echo "Database initialization skipped (may already exist)"

# Initialize default data if needed
echo "Checking for initial data..."
python init_db.py || echo "Initial data setup skipped (may already exist)"

echo "================================================"
echo "  Startup complete! Starting server..."
echo "================================================"

# Execute the main command (uvicorn)
exec "$@"
