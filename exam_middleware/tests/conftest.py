"""
Pytest Configuration and Shared Fixtures

This module provides shared fixtures for all tests including:
- Test database setup (SQLite in-memory for speed)
- FastAPI test client
- Mock services
- Test data factories
"""

import pytest
import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import tempfile
import os

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment before importing app
os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests-only"
os.environ["MOODLE_BASE_URL"] = "http://moodle.test"
os.environ["MOODLE_ADMIN_TOKEN"] = "test-admin-token"

from app.db.database import Base, get_db
from app.db.models import (
    ExaminationArtifact, 
    SubjectMapping, 
    StaffUser, 
    StudentSession,
    AuditLog,
    WorkflowStatus
)
from app.main import app
from app.core.security import get_password_hash


# ============================================
# Event Loop Configuration
# ============================================

@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for session scope."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================
# Database Fixtures
# ============================================

@pytest.fixture(scope="function")
async def test_engine():
    """Create a test database engine (SQLite in-memory)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,  # Share connection across all tests
        connect_args={"check_same_thread": False}
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a database session for testing."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture(scope="function")
async def client(test_engine, db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with overridden database."""
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


# ============================================
# Model Fixtures
# ============================================

@pytest.fixture
async def staff_user(db_session: AsyncSession) -> StaffUser:
    """Create a test staff user."""
    user = StaffUser(
        username="test_staff",
        hashed_password=get_password_hash("testpass123"),
        email="test@example.com",
        role="staff",
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> StaffUser:
    """Create a test admin user."""
    user = StaffUser(
        username="test_admin",
        hashed_password=get_password_hash("adminpass123"),
        email="admin@example.com",
        role="admin",
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def subject_mapping(db_session: AsyncSession) -> SubjectMapping:
    """Create a test subject mapping."""
    mapping = SubjectMapping(
        subject_code="19AI405",
        subject_name="Machine Learning",
        moodle_course_id=3,
        moodle_assignment_id=1,
        moodle_assignment_name="ML Assignment",
        exam_session="2024-DEC",
        is_active=True
    )
    db_session.add(mapping)
    await db_session.commit()
    await db_session.refresh(mapping)
    return mapping


@pytest.fixture
async def sample_artifact(db_session: AsyncSession) -> ExaminationArtifact:
    """Create a sample examination artifact."""
    artifact = ExaminationArtifact(
        raw_filename="123456789012_19AI405.pdf",
        original_filename="123456789012_19AI405.pdf",
        sanitized_filename="123456789012_19AI405.pdf",
        parsed_reg_no="123456789012",
        parsed_subject_code="19AI405",
        file_extension=".pdf",
        file_mime_type="application/pdf",
        file_size_bytes=1024,
        file_hash="abc123def456",
        file_blob_path="/uploads/test/123456789012_19AI405.pdf",
        workflow_status=WorkflowStatus.PENDING_REVIEW,
        transaction_log=[]
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)
    return artifact


@pytest.fixture
async def submitted_artifact(db_session: AsyncSession) -> ExaminationArtifact:
    """Create a submitted artifact."""
    artifact = ExaminationArtifact(
        raw_filename="987654321098_19AI411.pdf",
        original_filename="987654321098_19AI411.pdf",
        sanitized_filename="987654321098_19AI411.pdf",
        parsed_reg_no="987654321098",
        parsed_subject_code="19AI411",
        file_extension=".pdf",
        file_mime_type="application/pdf",
        file_size_bytes=2048,
        file_hash="xyz789uvw012",
        file_blob_path="/uploads/test/987654321098_19AI411.pdf",
        workflow_status=WorkflowStatus.SUBMITTED_TO_LMS,
        moodle_user_id=42,
        moodle_assignment_id=2,
        submit_timestamp=datetime.utcnow() - timedelta(hours=1),
        transaction_log=[]
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)
    return artifact


# ============================================
# Mock Fixtures
# ============================================

@pytest.fixture
def mock_moodle_client():
    """Create a mock Moodle client."""
    mock = AsyncMock()
    mock.get_token.return_value = {"token": "mock-token-12345"}
    mock.get_site_info.return_value = {
        "userid": 42,
        "fullname": "Test Student",
        "username": "student1"
    }
    mock.get_user_courses.return_value = [
        {"id": 3, "shortname": "19AI405", "fullname": "Machine Learning"}
    ]
    mock.get_assignments.return_value = {
        "courses": [
            {
                "id": 3,
                "shortname": "19AI405",
                "assignments": [
                    {"id": 1, "name": "ML Assignment", "cmid": 4}
                ]
            }
        ]
    }
    mock.upload_file.return_value = {
        "itemid": 12345,
        "filename": "test.pdf"
    }
    mock.save_submission.return_value = {
        "warnings": []
    }
    mock.submit_for_grading.return_value = {"status": True}
    mock.close.return_value = None
    return mock


@pytest.fixture
def mock_file():
    """Create a mock file for upload testing."""
    from io import BytesIO
    content = b"%PDF-1.4\n%Test PDF content\n"
    return BytesIO(content)


# ============================================
# Temporary File Fixtures
# ============================================

@pytest.fixture
def temp_upload_dir():
    """Create a temporary upload directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


# ============================================
# Authentication Fixtures
# ============================================

@pytest.fixture
async def staff_auth_headers(client: AsyncClient, staff_user: StaffUser) -> dict:
    """Get authentication headers for staff user."""
    response = await client.post(
        "/api/v1/auth/staff/login",
        json={
            "username": "test_staff",
            "password": "testpass123"
        }
    )
    if response.status_code == 200:
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    return {}


# ============================================
# Utility Functions
# ============================================

def create_test_pdf_content() -> bytes:
    """Create minimal valid PDF content for testing."""
    return b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer << /Size 4 /Root 1 0 R >>
startxref
190
%%EOF
"""


def create_test_image_content() -> bytes:
    """Create minimal valid PNG content for testing."""
    # Minimal 1x1 transparent PNG
    return bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
        0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,  # IDAT chunk
        0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
        0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
        0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,  # IEND chunk
        0x42, 0x60, 0x82
    ])
