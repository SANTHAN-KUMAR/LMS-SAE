import os
import tempfile
import pytest
from fastapi.testclient import TestClient

# Ensure environment variables for non-destructive test runs
os.environ.setdefault("ENV", "test")
os.environ.setdefault("DEBUG", "false")

# Use temporary directories for uploads/storage to avoid touching real data
tmp_base = tempfile.mkdtemp(prefix="lms_sae_tests_")
os.environ.setdefault("UPLOAD_DIR", os.path.join(tmp_base, "uploads"))

# Create client fixture
@pytest.fixture(scope="session")
def client():
    # Import after env is set so config picks up values
    from app.main import app
    return TestClient(app)
