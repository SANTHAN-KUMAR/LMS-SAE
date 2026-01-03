# Examination Middleware Setup Guide

This guide covers setting up the Examination Middleware project, including ngrok configuration, database setup, and initial user creation.

## Prerequisites
- Python 3.8+
- PostgreSQL installed and running
- Redis (for sessions and queue)
- Moodle LMS instance
- ngrok account and CLI

## 1. Environment Configuration

### Update .env File
1. Copy `.env.example` to `.env`:
   ```
   cp .env.example .env
   ```

2. Update the following variables in `.env`:
   - `MOODLE_BASE_URL`: Set to your ngrok URL (e.g., `https://your-ngrok-subdomain.ngrok-free.app`)
   - Database settings: Ensure `DATABASE_URL` points to your PostgreSQL instance (e.g., `postgresql+asyncpg://postgres:password@localhost:5432/exam_middleware`)
   - Other settings as needed (Redis, etc.)

## 2. Moodle Setup with ngrok

### Install and Configure ngrok
1. Download and install ngrok from [ngrok.com](https://ngrok.com).
2. Authenticate: `ngrok config add-authtoken YOUR_TOKEN`
3. Start tunnel to Moodle: `ngrok http 80` (adjust port if Moodle isn't on 80)
4. Note the generated URL (e.g., `https://abc123.ngrok-free.app`)

### Update Moodle config.php
1. Open Moodle's `config.php`.
2. Update `$CFG->wwwroot` to your ngrok URL:
   ```php
   $CFG->wwwroot = 'https://your-ngrok-subdomain.ngrok-free.app';
   ```
3. Add proxy settings for external access:
   ```php
   $CFG->sslproxy = true;
   $CFG->reverseproxy = true;
   ```

### Fix Moodle Database Issues
If you encounter "Database connection failed":
- Ensure MySQL/MariaDB is running (via XAMPP, WAMP, or standalone).
- Check `config.php` for correct DB credentials.
- If using XAMPP and MySQL won't start:
  - Stop XAMPP.
  - Delete `mysql/data/ibdata1`, `ib_logfile0`, `ib_logfile1`, `mysql.pid`.
  - Restart MySQL; if fails, reinitialize: `mysqld --initialize-insecure --user=mysql`

## 3. Install Dependencies
```
pip install -r requirements.txt
```

## 4. Database Setup

### Initialize Database
```
python init_db.py
```

### Wipe Database for Fresh Start (PostgreSQL)
If you need to reset the database:
1. Connect to PostgreSQL:
   ```
   psql -h localhost -p 5432 -U postgres -d exam_middleware
   ```
2. Drop tables:
   ```sql
   DROP TABLE IF EXISTS audit_logs CASCADE;
   DROP TABLE IF EXISTS submission_queue CASCADE;
   DROP TABLE IF EXISTS examination_artifacts CASCADE;
   DROP TABLE IF EXISTS subject_mappings CASCADE;
   DROP TABLE IF EXISTS staff_users CASCADE;
   DROP TABLE IF EXISTS student_sessions CASCADE;
   DROP TABLE IF EXISTS system_config CASCADE;
   ```
3. Or drop and recreate the database:
   ```sql
   \c postgres
   DROP DATABASE IF EXISTS exam_middleware;
   CREATE DATABASE exam_middleware;
   ```
4. Reinitialize: `python init_db.py`

### Create Admin User
1. Generate password hash (Python):
   ```python
   import bcrypt
   password = 'admin123'
   hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
   print(hashed.decode())
   ```
2. Insert into database:
   ```sql
   INSERT INTO staff_users (username, email, hashed_password, full_name, role, is_active) 
   VALUES ('admin', 'admin@example.com', 'YOUR_HASH_HERE', 'Administrator', 'admin', true);
   ```

## 5. Clear Storage (Optional)
Delete contents in `storage/uploads/failed/`, `pending/`, `processed/`, `temp/` for a clean start.

## 6. Run the Application
```
python run.py
```

Access:
- Staff Portal: `http://localhost:8000/portal/staff`
- Student Portal: `http://localhost:8000/portal/student`
- Health Check: `http://localhost:8000/health`

## 7. Moodle LMS Admin Setup

As a Moodle admin, configure Moodle for API interactions with the middleware:

1. **Enable Web Services**:
   - Site Administration > Advanced features > Enable web services: Yes.
   - Site Administration > Plugins > Web services > Manage protocols > Enable REST.

2. **Create a Dedicated User**:
   - Create a new user (e.g., "middleware_user") with access to relevant courses.

3. **Configure Permissions**:
   - Assign capabilities: `moodle/webservice:createtoken`, `mod/assign:view`, `mod/assign:submit`, `webservice/rest:use`.

4. **Create a Web Service**:
   - Add service "Exam Middleware Service" with functions: `mod_assign_get_assignments`, `mod_assign_get_submissions`, `core_files_upload`, etc.

5. **Generate API Token**:
   - Create token for the user; update `MOODLE_ADMIN_TOKEN` in `.env`.

6. **Set Up Assignments**:
   - Create assignments in courses with file submission enabled.

7. **Test Connectivity**:
   - Verify API calls and middleware health.

## Troubleshooting
- **401 Login Error**: Ensure admin user exists in DB.
- **DB Connection Issues**: Verify PostgreSQL is running and credentials are correct.
- **Moodle API Errors**: Confirm ngrok URL and Moodle token in `.env`.

For more details, refer to the main README.md.