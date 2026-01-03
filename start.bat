@echo off
REM ================================================
REM Quick Start Script for Windows
REM ================================================
REM This script helps you get started quickly

echo.
echo ================================================
echo   LMS-SAE Examination Middleware
echo   Quick Start Script
echo ================================================
echo.

REM Check if Docker is installed
docker --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not installed or not in PATH
    echo Please install Docker Desktop from: https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

REM Check if docker-compose is available
docker-compose --version >nul 2>&1
if errorlevel 1 (
    docker compose version >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Docker Compose is not available
        echo Please ensure Docker Desktop is properly installed
        pause
        exit /b 1
    )
)

REM Check if .env exists, if not copy from template
if not exist .env (
    echo Creating .env from template...
    copy .env.docker .env
    echo.
    echo IMPORTANT: Please edit .env file with your configuration!
    echo At minimum, change:
    echo   - SECRET_KEY
    echo   - POSTGRES_PASSWORD
    echo   - MOODLE_BASE_URL
    echo.
    pause
)

echo.
echo Choose an option:
echo   1. Start (Development mode - with pgAdmin)
echo   2. Start (Production mode - with Nginx)
echo   3. Stop all containers
echo   4. View logs
echo   5. Rebuild and start
echo   6. Clean everything (removes data!)
echo.

set /p choice="Enter choice (1-6): "

if "%choice%"=="1" (
    echo Starting in development mode...
    docker-compose --profile dev up -d
    echo.
    echo Services started:
    echo   - App:     http://localhost:8000
    echo   - pgAdmin: http://localhost:5050
    echo.
) else if "%choice%"=="2" (
    echo Starting in production mode...
    docker-compose --profile production up -d
    echo.
    echo Services started:
    echo   - App (via Nginx): http://localhost:80
    echo.
) else if "%choice%"=="3" (
    echo Stopping all containers...
    docker-compose --profile dev --profile production down
    echo Done!
) else if "%choice%"=="4" (
    echo Showing logs (Ctrl+C to exit)...
    docker-compose logs -f app
) else if "%choice%"=="5" (
    echo Rebuilding and starting...
    docker-compose build --no-cache
    docker-compose --profile dev up -d
    echo Done!
) else if "%choice%"=="6" (
    echo WARNING: This will delete all data including the database!
    set /p confirm="Are you sure? (yes/no): "
    if "%confirm%"=="yes" (
        docker-compose --profile dev --profile production down -v --rmi all
        echo All containers and data removed!
    ) else (
        echo Cancelled.
    )
) else (
    echo Invalid choice.
)

echo.
pause
