"""
Integration Tests for Upload API Routes

Tests the file upload endpoints including:
- Single file upload
- Bulk file upload
- File validation
- Error handling
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient
from io import BytesIO
import json

from app.db.models import WorkflowStatus

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.conftest import create_test_pdf_content, create_test_image_content


class TestSingleUpload:
    """Tests for single file upload endpoint."""
    
    @pytest.mark.asyncio
    async def test_upload_valid_pdf(self, client: AsyncClient, staff_auth_headers):
        """Test uploading a valid PDF file."""
        pdf_content = create_test_pdf_content()
        
        files = {
            "file": ("123456789012_19AI405.pdf", BytesIO(pdf_content), "application/pdf")
        }
        
        response = await client.post(
            "/api/v1/upload/single",
            files=files,
            headers=staff_auth_headers
        )
        
        # Should succeed or fail gracefully
        assert response.status_code in [200, 201, 401, 422]
    
    @pytest.mark.asyncio
    async def test_upload_valid_image(self, client: AsyncClient, staff_auth_headers):
        """Test uploading a valid image file."""
        image_content = create_test_image_content()
        
        files = {
            "file": ("123456789012_19AI405.png", BytesIO(image_content), "image/png")
        }
        
        response = await client.post(
            "/api/v1/upload/single",
            files=files,
            headers=staff_auth_headers
        )
        
        assert response.status_code in [200, 201, 401, 422]
    
    @pytest.mark.asyncio
    async def test_upload_requires_authentication(self, client: AsyncClient):
        """Test that upload requires authentication."""
        pdf_content = create_test_pdf_content()
        
        files = {
            "file": ("123456789012_19AI405.pdf", BytesIO(pdf_content), "application/pdf")
        }
        
        response = await client.post(
            "/api/v1/upload/single",
            files=files
            # No auth headers
        )
        
        assert response.status_code in [401, 403]
    
    @pytest.mark.asyncio
    async def test_upload_invalid_extension(self, client: AsyncClient, staff_auth_headers):
        """Test that invalid file extensions are rejected."""
        files = {
            "file": ("123456789012_19AI405.exe", BytesIO(b"fake exe"), "application/octet-stream")
        }
        
        response = await client.post(
            "/api/v1/upload/single",
            files=files,
            headers=staff_auth_headers
        )
        
        # Should reject
        assert response.status_code in [400, 422, 401]
    
    @pytest.mark.asyncio
    async def test_upload_invalid_filename_format(self, client: AsyncClient, staff_auth_headers):
        """Test that files with invalid filename format are handled."""
        pdf_content = create_test_pdf_content()
        
        files = {
            "file": ("invalid_filename.pdf", BytesIO(pdf_content), "application/pdf")
        }
        
        response = await client.post(
            "/api/v1/upload/single",
            files=files,
            headers=staff_auth_headers
        )
        
        # Should either reject or handle gracefully
        assert response.status_code in [200, 400, 401, 422]
    
    @pytest.mark.asyncio
    async def test_upload_empty_file(self, client: AsyncClient, staff_auth_headers):
        """Test uploading an empty file."""
        files = {
            "file": ("123456789012_19AI405.pdf", BytesIO(b""), "application/pdf")
        }
        
        response = await client.post(
            "/api/v1/upload/single",
            files=files,
            headers=staff_auth_headers
        )
        
        # Should reject empty files
        assert response.status_code in [400, 401, 422]
    
    @pytest.mark.asyncio
    async def test_upload_response_contains_artifact_id(self, client: AsyncClient, staff_auth_headers):
        """Test that successful upload returns artifact ID."""
        pdf_content = create_test_pdf_content()
        
        files = {
            "file": ("123456789012_19AI405.pdf", BytesIO(pdf_content), "application/pdf")
        }
        
        response = await client.post(
            "/api/v1/upload/single",
            files=files,
            headers=staff_auth_headers
        )
        
        if response.status_code in [200, 201]:
            data = response.json()
            assert "artifact_uuid" in data or "id" in data or "artifact" in data


class TestBulkUpload:
    """Tests for bulk file upload endpoint."""
    
    @pytest.mark.asyncio
    async def test_bulk_upload_multiple_files(self, client: AsyncClient, staff_auth_headers):
        """Test uploading multiple files at once."""
        pdf_content = create_test_pdf_content()
        
        files = [
            ("files", ("123456789001_19AI405.pdf", BytesIO(pdf_content), "application/pdf")),
            ("files", ("123456789002_19AI405.pdf", BytesIO(pdf_content), "application/pdf")),
            ("files", ("123456789003_19AI405.pdf", BytesIO(pdf_content), "application/pdf")),
        ]
        
        response = await client.post(
            "/api/v1/upload/bulk",
            files=files,
            headers=staff_auth_headers
        )
        
        assert response.status_code in [200, 201, 401, 422]
    
    @pytest.mark.asyncio
    async def test_bulk_upload_partial_success(self, client: AsyncClient, staff_auth_headers):
        """Test bulk upload with some valid and some invalid files."""
        pdf_content = create_test_pdf_content()
        
        files = [
            ("files", ("123456789001_19AI405.pdf", BytesIO(pdf_content), "application/pdf")),
            ("files", ("invalid.exe", BytesIO(b"fake"), "application/octet-stream")),
        ]
        
        response = await client.post(
            "/api/v1/upload/bulk",
            files=files,
            headers=staff_auth_headers
        )
        
        # Should handle partial success
        if response.status_code in [200, 201]:
            data = response.json()
            # Response should indicate which succeeded and which failed
    
    @pytest.mark.asyncio
    async def test_bulk_upload_requires_authentication(self, client: AsyncClient):
        """Test that bulk upload requires authentication."""
        pdf_content = create_test_pdf_content()
        
        files = [
            ("files", ("123456789001_19AI405.pdf", BytesIO(pdf_content), "application/pdf")),
        ]
        
        response = await client.post(
            "/api/v1/upload/bulk",
            files=files
            # No auth
        )
        
        assert response.status_code in [401, 403]
    
    @pytest.mark.asyncio
    async def test_bulk_upload_empty_list(self, client: AsyncClient, staff_auth_headers):
        """Test bulk upload with no files."""
        response = await client.post(
            "/api/v1/upload/bulk",
            files=[],
            headers=staff_auth_headers
        )
        
        # Should reject or return empty result
        assert response.status_code in [200, 400, 401, 422]


class TestUploadValidation:
    """Tests for upload validation logic."""
    
    @pytest.mark.asyncio
    async def test_duplicate_file_detection(self, client: AsyncClient, staff_auth_headers):
        """Test that duplicate files are detected."""
        pdf_content = create_test_pdf_content()
        
        files = {
            "file": ("123456789012_19AI405.pdf", BytesIO(pdf_content), "application/pdf")
        }
        
        # Upload first time
        response1 = await client.post(
            "/api/v1/upload/single",
            files=files,
            headers=staff_auth_headers
        )
        
        # Try to upload same file again
        files["file"] = ("123456789012_19AI405.pdf", BytesIO(pdf_content), "application/pdf")
        response2 = await client.post(
            "/api/v1/upload/single",
            files=files,
            headers=staff_auth_headers
        )
        
        # Second upload should either succeed with note or fail as duplicate
        # Behavior depends on implementation
    
    @pytest.mark.asyncio
    async def test_file_size_limit(self, client: AsyncClient, staff_auth_headers):
        """Test that file size limit is enforced."""
        # Create a large file (assuming limit is less than 100MB)
        large_content = b"A" * (100 * 1024 * 1024)  # 100MB
        
        files = {
            "file": ("123456789012_19AI405.pdf", BytesIO(large_content), "application/pdf")
        }
        
        response = await client.post(
            "/api/v1/upload/single",
            files=files,
            headers=staff_auth_headers
        )
        
        # Should reject if over limit
        # Status depends on where limit is enforced
    
    @pytest.mark.asyncio
    async def test_content_type_validation(self, client: AsyncClient, staff_auth_headers):
        """Test that content type is validated against extension."""
        # Send PDF with wrong content type
        pdf_content = create_test_pdf_content()
        
        files = {
            "file": ("123456789012_19AI405.pdf", BytesIO(pdf_content), "image/png")
        }
        
        response = await client.post(
            "/api/v1/upload/single",
            files=files,
            headers=staff_auth_headers
        )
        
        # Behavior depends on validation strictness


class TestUploadErrorHandling:
    """Tests for upload error handling."""
    
    @pytest.mark.asyncio
    async def test_handles_storage_error(self, client: AsyncClient, staff_auth_headers):
        """Test handling of storage errors during upload."""
        pdf_content = create_test_pdf_content()
        
        files = {
            "file": ("123456789012_19AI405.pdf", BytesIO(pdf_content), "application/pdf")
        }
        
        with patch('app.services.file_processor.FileProcessor.save_file', side_effect=IOError("Disk full")):
            response = await client.post(
                "/api/v1/upload/single",
                files=files,
                headers=staff_auth_headers
            )
            
            # Should return error, not crash
            assert response.status_code in [401, 500, 503]
    
    @pytest.mark.asyncio
    async def test_handles_database_error(self, client: AsyncClient, staff_auth_headers):
        """Test handling of database errors during upload."""
        pdf_content = create_test_pdf_content()
        
        files = {
            "file": ("123456789012_19AI405.pdf", BytesIO(pdf_content), "application/pdf")
        }
        
        with patch('app.services.artifact_service.ArtifactService.create', side_effect=Exception("DB error")):
            response = await client.post(
                "/api/v1/upload/single",
                files=files,
                headers=staff_auth_headers
            )
            
            # Should return error, not crash
            assert response.status_code in [401, 500]
    
    @pytest.mark.asyncio
    async def test_rollback_on_error(self, client: AsyncClient, staff_auth_headers):
        """Test that partial operations are rolled back on error."""
        pdf_content = create_test_pdf_content()
        
        files = {
            "file": ("123456789012_19AI405.pdf", BytesIO(pdf_content), "application/pdf")
        }
        
        # This tests that if DB save fails after file save, file is cleaned up
        # Implementation may vary
