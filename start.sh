#!/bin/bash
# ================================================
# Quick Start Script for Linux/Mac
# ================================================
# This script helps you get started quickly

set -e

echo ""
echo "================================================"
echo "  LMS-SAE Examination Middleware"
echo "  Quick Start Script"
echo "================================================"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed"
    echo "Please install Docker from: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if docker-compose is available
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
else
    echo "ERROR: Docker Compose is not available"
    exit 1
fi

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env from template..."
    cp .env.docker .env
    echo ""
    echo "IMPORTANT: Please edit .env file with your configuration!"
    echo "At minimum, change:"
    echo "  - SECRET_KEY"
    echo "  - POSTGRES_PASSWORD"
    echo "  - MOODLE_BASE_URL"
    echo ""
    read -p "Press Enter to continue after editing .env..."
fi

echo ""
echo "Choose an option:"
echo "  1. Start (Development mode - with pgAdmin)"
echo "  2. Start (Production mode - with Nginx)"
echo "  3. Stop all containers"
echo "  4. View logs"
echo "  5. Rebuild and start"
echo "  6. Clean everything (removes data!)"
echo ""

read -p "Enter choice (1-6): " choice

case $choice in
    1)
        echo "Starting in development mode..."
        $COMPOSE_CMD --profile dev up -d
        echo ""
        echo "Services started:"
        echo "  - App:     http://localhost:8000"
        echo "  - pgAdmin: http://localhost:5050"
        echo ""
        ;;
    2)
        echo "Starting in production mode..."
        $COMPOSE_CMD --profile production up -d
        echo ""
        echo "Services started:"
        echo "  - App (via Nginx): http://localhost:80"
        echo ""
        ;;
    3)
        echo "Stopping all containers..."
        $COMPOSE_CMD --profile dev --profile production down
        echo "Done!"
        ;;
    4)
        echo "Showing logs (Ctrl+C to exit)..."
        $COMPOSE_CMD logs -f app
        ;;
    5)
        echo "Rebuilding and starting..."
        $COMPOSE_CMD build --no-cache
        $COMPOSE_CMD --profile dev up -d
        echo "Done!"
        ;;
    6)
        echo "WARNING: This will delete all data including the database!"
        read -p "Are you sure? (yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            $COMPOSE_CMD --profile dev --profile production down -v --rmi all
            echo "All containers and data removed!"
        else
            echo "Cancelled."
        fi
        ;;
    *)
        echo "Invalid choice."
        ;;
esac

echo ""
