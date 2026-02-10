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
# Wait for database to be ready
echo "Waiting for database..."

if [ -n "$DATABASE_URL" ]; then
    # If DATABASE_URL is set (e.g., Render/Neon), check availability using connection string
    # We use -d to specify the dbname/connection string
    # We try up to 30 times (60 seconds)
    count=0
    while ! pg_isready -d "$DATABASE_URL" -q; do
        echo "Database is unavailable (via DATABASE_URL) - sleeping ($count/30)"
        sleep 2
        count=$((count+1))
        if [ $count -ge 30 ]; then
            echo "Timeout waiting for database!"
            exit 1
        fi
    done
else
    # Fallback for local Docker Compose
    while ! pg_isready -h "${POSTGRES_HOST:-db}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-postgres}" -q; do
        echo "Database is unavailable (via host) - sleeping"
        sleep 2
    done
fi

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
