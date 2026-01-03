# Docker Deployment Guide

This guide explains how to run the LMS-SAE Examination Middleware using Docker. With Docker, you can run the entire application stack with a single command, without installing Python, PostgreSQL, or any other dependencies on your machine.

## Prerequisites

- **Docker Desktop** (Windows/Mac) or **Docker Engine** (Linux)
  - Download: https://www.docker.com/products/docker-desktop
- **Docker Compose** (included with Docker Desktop)

## Quick Start

### Windows

1. Double-click `start.bat` and follow the menu prompts

### Linux/Mac

```bash
chmod +x start.sh
./start.sh
```

### Manual Commands

```bash
# 1. Copy environment template
cp .env.docker .env

# 2. Edit .env with your settings (at minimum: SECRET_KEY, POSTGRES_PASSWORD)
nano .env

# 3. Start the application
docker-compose up -d

# 4. View logs
docker-compose logs -f app

# 5. Access the application
# App:  http://localhost:8000
# Docs: http://localhost:8000/docs
```

## Configuration

### Required Settings

Edit `.env` file before starting:

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Application secret key (min 32 chars) | `your-very-long-random-secret-key-here` |
| `POSTGRES_PASSWORD` | Database password | `strongpassword123` |
| `MOODLE_BASE_URL` | Your Moodle instance URL | `https://moodle.university.edu` |
| `MOODLE_ADMIN_TOKEN` | Moodle API token | `abc123...` |

### Optional Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_PORT` | 8000 | Application port |
| `DB_PORT` | 5433 | PostgreSQL port (external) |
| `MAX_FILE_SIZE_MB` | 50 | Max upload size |
| `DEBUG` | false | Debug mode |

## Deployment Modes

### Development Mode

Includes pgAdmin for database management:

```bash
docker-compose --profile dev up -d
```

Access:
- Application: http://localhost:8000
- API Docs: http://localhost:8000/docs
- pgAdmin: http://localhost:5050 (login: admin@exam.local / admin)

### Production Mode

Includes Nginx reverse proxy with rate limiting:

```bash
docker-compose --profile production up -d
```

Access:
- Application: http://localhost (port 80)

## Common Operations

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f app
docker-compose logs -f db
```

### Stop Services

```bash
docker-compose down
```

### Restart Application

```bash
docker-compose restart app
```

### Rebuild After Code Changes

```bash
docker-compose build --no-cache app
docker-compose up -d app
```

### Access Database Shell

```bash
docker-compose exec db psql -U postgres -d exam_middleware
```

### Access Application Shell

```bash
docker-compose exec app /bin/bash
```

### Check Service Status

```bash
docker-compose ps
```

## Data Persistence

Data is stored in Docker volumes:

| Volume | Contents |
|--------|----------|
| `postgres_data` | Database files |
| `uploads_data` | Uploaded examination papers |
| `storage_data` | Processed files |
| `redis_data` | Cache data |

### Backup Database

```bash
docker-compose exec db pg_dump -U postgres exam_middleware > backup.sql
```

### Restore Database

```bash
cat backup.sql | docker-compose exec -T db psql -U postgres exam_middleware
```

### Backup Uploads

```bash
docker cp exam-middleware:/app/uploads ./uploads_backup
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs app

# Check if ports are in use
netstat -an | findstr 8000  # Windows
lsof -i :8000               # Linux/Mac
```

### Database connection failed

```bash
# Check if database is healthy
docker-compose ps db

# Restart database
docker-compose restart db
```

### Reset everything

```bash
# WARNING: This deletes all data!
docker-compose down -v --rmi all
docker-compose up -d
```

### Permission issues (Linux)

```bash
# Fix upload directory permissions
docker-compose exec app chown -R appuser:appgroup /app/uploads
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Docker Network                    │
│                                                      │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐         │
│  │  Nginx  │───▶│   App   │───▶│   DB    │         │
│  │  :80    │    │  :8000  │    │  :5432  │         │
│  └────┬────┘    └────┬────┘    └─────────┘         │
│       │              │                              │
│       │         ┌────▼────┐                         │
│       │         │  Redis  │                         │
│       │         │  :6379  │                         │
│       │         └─────────┘                         │
└───────┼─────────────────────────────────────────────┘
        │
    Internet
```

## Security Notes

1. **Change default passwords** in `.env` before deployment
2. **Use HTTPS** in production (configure SSL in Nginx)
3. **Firewall**: Only expose necessary ports (80/443)
4. **Updates**: Regularly update Docker images

## Production Checklist

- [ ] Changed `SECRET_KEY` to a strong random value
- [ ] Changed `POSTGRES_PASSWORD` to a strong password
- [ ] Configured `MOODLE_BASE_URL` and `MOODLE_ADMIN_TOKEN`
- [ ] Set `DEBUG=false`
- [ ] Configured SSL certificates for HTTPS
- [ ] Set up regular database backups
- [ ] Configured firewall rules
- [ ] Set up monitoring/alerting
