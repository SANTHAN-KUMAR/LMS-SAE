#  Examination Middleware (LMS-SAE Bridge)

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-009688.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14%2B-336791.svg)
![Moodle](https://img.shields.io/badge/Integration-Moodle%20LMS-orange)

**Examination Middleware** is a robust, secure, and automated bridge designed to streamline the digitization and submission of physical examination answer sheets to the Moodle Learning Management System (LMS). It acts as an intelligent intermediary between the physical examination hall and the digital grading environment.

---

##  The Problem Statement

In academic institutions transitioning to digital grading, handling physical answer scripts presents significant logistical challenges:

1.  **Manual Labor**: Individually scanning, renaming, and uploading hundreds of answer scripts to specific Moodle assignments is time-consuming and inefficient.
2.  **Human Error**: Manual processes are prone to errors such as uploading the wrong file to a student's profile or mislabeling files.
3.  **Security & Integrity**: Direct database manipulation or unverified bulk uploads can compromise the chain of custody.
4.  **Student Verification**: Students often lack a mechanism to verify that their specific physical paper was scanned and submitted correctly before grading begins.

##  Proposed Solution & Architecture

This middleware solves these issues by decoupling the **scanning/uploading** process from the **submission** process, introducing a secure validation layer.

### Core Concept
The system utilizes a **3-Step "Upload-Verify-Push" Workflow**:
1.  **Bulk Ingestion**: Administrative staff upload bulk batches of scanned PDF/Images.
2.  **Intelligent Processing**: The system parses filenames (e.g., `123456_MATH101.pdf`) to extract the Student Register Number and Subject Code, automatically mapping them to the correct Moodle Assignment ID.
3.  **Student-Led Submission**: Students log in using their Moodle credentials. They view *only* their specific answer scripts and trigger the final submission to Moodle. This ensures non-repudiation and student verification.

### High-Level Architecture

```mermaid
graph LR
    A[Physical Scans] -->|Bulk Upload| B(Staff Portal / Middleware)
    B -->|Parse & Store| C{PostgreSQL DB}
    D[Student] -->|Login via Moodle Creds| E(Student Portal)
    E -->|Fetch Pending Papers| C
    E -->|Trigger Submission| F[Moodle LMS]
    F -->|Token Exchange| E
```
## Database Schema Overview

The database is designed for data integrity and auditability. Key models include:

| Model | Description |
| :--- | :--- |
| **`ExaminationArtifact`** | The core entity representing a scanned paper. Stores UUID, file path, hash (SHA-256), extracted metadata (Reg No, Subject), and current `WorkflowStatus` (e.g., `PENDING`, `SUBMITTED_TO_LMS`). |
| **`SubjectMapping`** | Configuration table mapping a Subject Code (e.g., `19AI405`) to a specific Moodle Course ID and Assignment ID. |
| **`StaffUser`** | Accounts for administrative staff authorized to perform bulk uploads. |
| **`StudentSession`** | Manages ephemeral student sessions. Stores encrypted Moodle access tokens used to perform submissions on behalf of the student. |
| **`AuditLog`** | A rigid ledger tracking every action (Upload, View, Submit) with IP addresses and timestamps to ensure a chain of custody. |
| **`SubmissionQueue`** | A buffer for handling Moodle API failures or maintenance windows, ensuring no submission is lost. |

---

## 🔄 Workflow of the Platform

### Phase 1: Administration & Setup
1.  **Mapping**: Admin configures the `SubjectMapping` table (e.g., Subject `CS101` targets Moodle Assignment `ID: 55`).
2.  **Scanning**: Examination cell scans answer sheets using the naming convention: `{RegisterNumber}_{SubjectCode}.pdf`.

### Phase 2: Staff Operations
1.  **Login**: Staff logs into the Staff Portal.
2.  **Bulk Upload**: Staff drags and drops folders of scanned files.
3.  **Validation**: The system instantly validates filenames. Invalid files are rejected; valid files are hashed and stored as `ExaminationArtifacts` with status `PENDING`.

### Phase 3: Student Operations
1.  **Login**: Student logs into the Student Portal using their university Moodle username and password.
2.  **Dashboard**: The system displays all papers tagged with their Register Number.
3.  **Review**: Student previews the PDF to ensure it is their paper.
4.  **Submit**: Student clicks "Submit".
    * *Backend Action*: The system authenticates with Moodle using the student's token.
    * *Backend Action*: Uploads the file to Moodle's draft area.
    * *Backend Action*: Finalizes the submission for grading.
5.  **Confirmation**: The status updates to `SUBMITTED_TO_LMS`.
   
## 📋 Prerequisites

- Python 3.10+
- PostgreSQL 14+
- Moodle LMS with Web Services enabled
- Redis (optional, for background tasks)

## 🚀 Quick Start

### 1. Clone and Setup

```bash
cd exam_middleware
```

### 2. Create Virtual Environment

```bash
python -m venv venv

# Windows
.\venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

Copy `.env.example` to `.env` and update the values:

```bash
copy .env.example .env
```

Edit `.env` with your settings:

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/exam_middleware

# Security
SECRET_KEY=your-super-secret-key-change-in-production
ENCRYPTION_KEY=your-32-byte-encryption-key-here

# Moodle Configuration
MOODLE_BASE_URL=https://your-moodle-site.com
MOODLE_ADMIN_TOKEN=your-admin-token

# Subject Mappings (subject_code:assignment_id)
SUBJECT_ASSIGNMENT_MAP=19AI405:4,19AI411:6,ML:2
```

### 5. Setup PostgreSQL Database

```bash
# Create database
psql -U postgres -c "CREATE DATABASE exam_middleware;"
```

### 6. Initialize Database

```bash
python init_db.py
```

This will:
- Create all required tables
- Create default admin user (username: `admin`, password: `admin123`)
- Seed subject-to-assignment mappings
- Configure system settings

### 7. Run the Application

```bash
python run.py
```

The server will start at `http://localhost:8000`

## 🔗 Access Points

| Portal | URL |
|--------|-----|
| Staff Upload Portal | http://localhost:8000/portal/staff |
| Student Portal | http://localhost:8000/portal/student |
| API Documentation | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Health Check | http://localhost:8000/health |

## 📁 File Naming Convention

Uploaded files must follow this naming pattern:

```
{RegisterNumber}_{SubjectCode}.{extension}
```

**Examples:**
- `611221104088_19AI405.pdf`
- `611221104089_ML.jpg`
- `611221104090_19AI411.png`

**Rules:**
- Register Number: Exactly 12 digits
- Subject Code: 2-10 alphanumeric characters
- Extensions: pdf, jpg, jpeg, png

## 🔐 Authentication

### Staff Authentication
- Username/password-based JWT authentication
- Default credentials: `admin` / `admin123`
- Token expires in 8 hours

### Student Authentication
- Moodle credential verification
- Token exchange with Moodle LMS
- Encrypted token storage for submissions

## 📊 API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/staff/login` | Staff login |
| POST | `/auth/student/login` | Student login with Moodle credentials |
| POST | `/auth/student/logout` | Student logout |

### Upload (Staff Only)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/upload/single` | Upload single file |
| POST | `/upload/bulk` | Upload multiple files |
| POST | `/upload/validate` | Validate filename |

### Student
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/student/dashboard` | Get assigned papers |
| GET | `/student/paper/{id}/view` | View paper content |
| POST | `/student/submit/{id}` | Submit paper to Moodle |
| GET | `/student/submission/{id}/status` | Check submission status |

### Admin
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/mappings` | List subject mappings |
| POST | `/admin/mappings` | Create mapping |
| GET | `/admin/queue` | View submission queue |
| GET | `/admin/stats` | System statistics |

## 🔧 Moodle Configuration

### Required Moodle Setup

1. **Enable Web Services**
   - Site administration → Advanced features → Enable web services

2. **Create External Service**
   - Site administration → Server → Web services → External services
   - Create service: "FileUpload"
   - Add functions:
     - `core_webservice_get_site_info`
     - `mod_assign_save_submission`
     - `mod_assign_submit_for_grading`

3. **Create Token**
   - Site administration → Server → Web services → Manage tokens
   - Create token for admin user with "FileUpload" service

4. **Enable Upload**
   - Ensure `webservice/upload.php` is accessible
   - Configure max upload size in Moodle settings

## 📦 Project Structure

```
exam_middleware/
├── app/
│   ├── api/
│   │   └── routes/
│   │       ├── admin.py      # Admin endpoints
│   │       ├── auth.py       # Authentication
│   │       ├── health.py     # Health check
│   │       ├── student.py    # Student endpoints
│   │       └── upload.py     # File upload
│   ├── core/
│   │   ├── config.py         # Configuration
│   │   └── security.py       # Security utilities
│   ├── db/
│   │   ├── database.py       # Database connection
│   │   └── models.py         # SQLAlchemy models
│   ├── schemas/
│   │   └── schemas.py        # Pydantic schemas
│   ├── services/
│   │   ├── artifact_service.py    # Artifact management
│   │   ├── file_processor.py      # File processing
│   │   ├── moodle_client.py       # Moodle API client
│   │   └── submission_service.py  # Submission workflow
│   ├── templates/
│   │   ├── staff_upload.html      # Staff portal
│   │   └── student_portal.html    # Student portal
│   └── main.py               # FastAPI application
├── uploads/                  # Temporary upload storage
├── storage/                  # Permanent file storage
├── .env                      # Environment configuration
├── .env.example              # Example configuration
├── init_db.py               # Database initialization
├── run.py                    # Application runner
└── requirements.txt          # Python dependencies
```

## 🧪 Testing

### Test with Sample Files

1. Create test files with correct naming:
   ```
   611221104088_19AI405.pdf
   611221104089_ML.pdf
   ```

2. Login to Staff Portal with `admin`/`admin123`

3. Upload the test files

4. Login to Student Portal with Moodle student credentials and register number

5. View and submit papers to Moodle

### API Testing with cURL

```bash
# Staff Login
curl -X POST http://localhost:8000/auth/staff/login \
  -F "username=admin" \
  -F "password=admin123"

# Upload File (use token from login)
curl -X POST http://localhost:8000/upload/single \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@611221104088_19AI405.pdf" \
  -F "exam_session=2024SPRING"

# Health Check
curl http://localhost:8000/health
```

## 📝 Workflow

1. **Staff uploads scanned papers** through the Staff Portal
2. **System extracts metadata** from filenames (register number, subject code)
3. **Papers are validated** and stored with unique transaction IDs
4. **Students login** with Moodle credentials and register number
5. **Students view** their assigned papers
6. **Students submit** papers directly to Moodle assignments
7. **System executes** 3-step Moodle submission:
   - Upload file to Moodle
   - Save submission draft
   - Submit for grading

## 🛡️ Security Considerations

- **Password Hashing**: bcrypt with 12 rounds
- **Token Encryption**: AES-256 (Fernet) for Moodle tokens
- **JWT Tokens**: Short-lived access tokens
- **File Validation**: Extension and size checks
- **Audit Logging**: All operations logged
- **CORS**: Configurable origin whitelist

## 🔄 Background Tasks (Optional)

For production deployment with Celery:

```bash
# Start Redis
redis-server

# Start Celery worker
celery -A app.tasks worker --loglevel=info
```

## 📈 Monitoring

- Health endpoint: `/health`
- Logs: `exam_middleware.log`
- Database audit table: `audit_logs`

## 🐛 Troubleshooting

### Database Connection Error
```
Ensure PostgreSQL is running and credentials in .env are correct
```

### Moodle Token Error
```
Verify MOODLE_ADMIN_TOKEN has required capabilities
Check Moodle external service configuration
```

### File Upload Failed
```
Check file size limits in Moodle
Verify assignment allows file submissions
```

## 📄 License

Not Licensed Yet.

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Commit changes
4. Push to branch
5. Create Pull Request
