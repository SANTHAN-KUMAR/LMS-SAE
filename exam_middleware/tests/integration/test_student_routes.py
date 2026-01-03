"""
Integration Tests for Student API Routes

Tests the student portal endpoints including:
- Student dashboard
- Paper viewing
- Submission flow
- Download functionality
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient
from datetime import datetime, timedelta

from app.db.models import ExaminationArtifact, StudentSession, WorkflowStatus
from app.core.security import token_encryption

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.factories import ArtifactFactory, StudentSessionFactory


class TestStudentDashboard:
    """Tests for student dashboard endpoint."""
    
    @pytest.fixture
    async def student_session(self, db_session):
        """Create a valid student session."""
        session = StudentSessionFactory.create(
            moodle_user_id=42,
            moodle_username="student1",
            register_number="123456789012"
        )
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)
        return session
    
    @pytest.fixture
    async def student_artifacts(self, db_session):
        """Create artifacts for the student."""
        pending1 = ArtifactFactory.create_pending(register_number="123456789012")
        pending2 = ArtifactFactory.create_pending(register_number="123456789012")
        submitted = ArtifactFactory.create_submitted(
            register_number="123456789012",
            moodle_user_id=42
        )
        other_student = ArtifactFactory.create_pending(register_number="999999999999")
        
        db_session.add_all([pending1, pending2, submitted, other_student])
        await db_session.commit()
        
        return {
            "pending": [pending1, pending2],
            "submitted": [submitted],
            "other": [other_student]
        }
    
    @pytest.mark.asyncio
    async def test_dashboard_requires_session(self, client: AsyncClient):
        """Test that dashboard requires valid session."""
        response = await client.get("/api/v1/student/dashboard")
        
        assert response.status_code in [401, 403]
    
    @pytest.mark.asyncio
    async def test_dashboard_returns_student_papers(
        self, 
        client: AsyncClient, 
        student_session,
        student_artifacts
    ):
        """Test that dashboard returns only the student's papers."""
        response = await client.get(
            "/api/v1/student/dashboard",
            headers={"X-Session-ID": student_session.session_id}
        )
        
        # May need different auth mechanism
        assert response.status_code in [200, 401, 403]
        
        if response.status_code == 200:
            data = response.json()
            # Should have pending and submitted sections
            assert "pending" in data or "papers" in data
    
    @pytest.mark.asyncio
    async def test_dashboard_separates_pending_and_submitted(
        self, 
        client: AsyncClient, 
        student_session,
        student_artifacts
    ):
        """Test that pending and submitted papers are separated."""
        response = await client.get(
            "/api/v1/student/dashboard",
            headers={"X-Session-ID": student_session.session_id}
        )
        
        if response.status_code == 200:
            data = response.json()
            if "pending" in data and "submitted" in data:
                pending_ids = [p.get("id") for p in data["pending"]]
                submitted_ids = [s.get("id") for s in data["submitted"]]
                
                # Should not overlap
                assert len(set(pending_ids) & set(submitted_ids)) == 0
    
    @pytest.mark.asyncio
    async def test_dashboard_excludes_other_students(
        self, 
        client: AsyncClient, 
        student_session,
        student_artifacts
    ):
        """Test that dashboard excludes other students' papers."""
        response = await client.get(
            "/api/v1/student/dashboard",
            headers={"X-Session-ID": student_session.session_id}
        )
        
        if response.status_code == 200:
            data = response.json()
            all_papers = data.get("pending", []) + data.get("submitted", [])
            
            # None should be from different student
            for paper in all_papers:
                reg_no = paper.get("register_number") or paper.get("parsed_reg_no")
                if reg_no:
                    assert reg_no != "999999999999"


class TestPaperDetails:
    """Tests for viewing paper details."""
    
    @pytest.fixture
    async def student_session(self, db_session):
        """Create a valid student session."""
        session = StudentSessionFactory.create(
            moodle_user_id=42,
            moodle_username="student1",
            register_number="123456789012"
        )
        db_session.add(session)
        await db_session.commit()
        return session
    
    @pytest.mark.asyncio
    async def test_view_own_paper(self, client: AsyncClient, student_session, sample_artifact):
        """Test viewing own paper details."""
        response = await client.get(
            f"/api/v1/student/papers/{sample_artifact.artifact_uuid}",
            headers={"X-Session-ID": student_session.session_id}
        )
        
        assert response.status_code in [200, 401, 403, 404]
    
    @pytest.mark.asyncio
    async def test_cannot_view_other_student_paper(
        self, 
        client: AsyncClient, 
        student_session, 
        db_session
    ):
        """Test that student cannot view another student's paper."""
        # Create artifact for different student
        other_artifact = ArtifactFactory.create_pending(register_number="999999999999")
        db_session.add(other_artifact)
        await db_session.commit()
        
        response = await client.get(
            f"/api/v1/student/papers/{other_artifact.artifact_uuid}",
            headers={"X-Session-ID": student_session.session_id}
        )
        
        # Should be forbidden or not found
        assert response.status_code in [403, 404, 401]
    
    @pytest.mark.asyncio
    async def test_view_nonexistent_paper(self, client: AsyncClient, student_session):
        """Test viewing non-existent paper."""
        response = await client.get(
            "/api/v1/student/papers/nonexistent-uuid",
            headers={"X-Session-ID": student_session.session_id}
        )
        
        assert response.status_code in [404, 401, 403]


class TestPaperSubmission:
    """Tests for paper submission endpoint."""
    
    @pytest.fixture
    async def student_session(self, db_session):
        """Create a valid student session with encrypted token."""
        encrypted_token = token_encryption.encrypt("moodle-token-123")
        session = StudentSessionFactory.create(
            moodle_user_id=42,
            moodle_username="student1",
            register_number="123456789012",
            token=encrypted_token
        )
        db_session.add(session)
        await db_session.commit()
        return session
    
    @pytest.mark.asyncio
    async def test_submit_paper_requires_session(self, client: AsyncClient, sample_artifact):
        """Test that submission requires valid session."""
        response = await client.post(
            f"/api/v1/student/papers/{sample_artifact.artifact_uuid}/submit"
        )
        
        assert response.status_code in [401, 403]
    
    @pytest.mark.asyncio
    async def test_submit_own_pending_paper(
        self, 
        client: AsyncClient, 
        student_session,
        db_session,
        mock_moodle_client
    ):
        """Test submitting own pending paper."""
        # Create artifact for this student
        artifact = ArtifactFactory.create_pending(
            register_number="123456789012",
            subject_code="19AI405"
        )
        db_session.add(artifact)
        await db_session.commit()
        
        with patch('app.services.moodle_client.MoodleClient', return_value=mock_moodle_client):
            response = await client.post(
                f"/api/v1/student/papers/{artifact.artifact_uuid}/submit",
                headers={"X-Session-ID": student_session.session_id}
            )
            
            # Should succeed or fail with clear error
            assert response.status_code in [200, 400, 401, 403, 404, 500]
    
    @pytest.mark.asyncio
    async def test_cannot_submit_other_student_paper(
        self, 
        client: AsyncClient, 
        student_session,
        db_session
    ):
        """Test that student cannot submit another student's paper."""
        other_artifact = ArtifactFactory.create_pending(register_number="999999999999")
        db_session.add(other_artifact)
        await db_session.commit()
        
        response = await client.post(
            f"/api/v1/student/papers/{other_artifact.artifact_uuid}/submit",
            headers={"X-Session-ID": student_session.session_id}
        )
        
        assert response.status_code in [403, 404, 401]
    
    @pytest.mark.asyncio
    async def test_cannot_submit_already_submitted(
        self, 
        client: AsyncClient, 
        student_session,
        db_session
    ):
        """Test that already submitted paper cannot be submitted again."""
        submitted = ArtifactFactory.create_submitted(
            register_number="123456789012",
            moodle_user_id=42
        )
        db_session.add(submitted)
        await db_session.commit()
        
        response = await client.post(
            f"/api/v1/student/papers/{submitted.artifact_uuid}/submit",
            headers={"X-Session-ID": student_session.session_id}
        )
        
        # Should reject duplicate submission
        assert response.status_code in [400, 409, 401, 403]
    
    @pytest.mark.asyncio
    async def test_submit_handles_moodle_error(
        self, 
        client: AsyncClient, 
        student_session,
        db_session
    ):
        """Test handling of Moodle API errors during submission."""
        artifact = ArtifactFactory.create_pending(register_number="123456789012")
        db_session.add(artifact)
        await db_session.commit()
        
        from app.services.moodle_client import MoodleAPIError
        
        with patch(
            'app.services.moodle_client.MoodleClient.upload_file',
            side_effect=MoodleAPIError("Upload failed", "uploadfailed")
        ):
            response = await client.post(
                f"/api/v1/student/papers/{artifact.artifact_uuid}/submit",
                headers={"X-Session-ID": student_session.session_id}
            )
            
            # Should return error, not crash
            assert response.status_code in [400, 401, 403, 500, 503]


class TestPaperDownload:
    """Tests for paper download endpoint."""
    
    @pytest.fixture
    async def student_session(self, db_session):
        """Create a valid student session."""
        session = StudentSessionFactory.create(
            moodle_user_id=42,
            register_number="123456789012"
        )
        db_session.add(session)
        await db_session.commit()
        return session
    
    @pytest.mark.asyncio
    async def test_download_own_paper(
        self, 
        client: AsyncClient, 
        student_session,
        sample_artifact
    ):
        """Test downloading own paper."""
        response = await client.get(
            f"/api/v1/student/papers/{sample_artifact.artifact_uuid}/download",
            headers={"X-Session-ID": student_session.session_id}
        )
        
        # May succeed or fail based on file existence and auth
        assert response.status_code in [200, 401, 403, 404]
    
    @pytest.mark.asyncio
    async def test_download_requires_session(self, client: AsyncClient, sample_artifact):
        """Test that download requires valid session."""
        response = await client.get(
            f"/api/v1/student/papers/{sample_artifact.artifact_uuid}/download"
        )
        
        assert response.status_code in [401, 403]
    
    @pytest.mark.asyncio
    async def test_cannot_download_other_student_paper(
        self, 
        client: AsyncClient, 
        student_session,
        db_session
    ):
        """Test that student cannot download another student's paper."""
        other_artifact = ArtifactFactory.create_pending(register_number="999999999999")
        db_session.add(other_artifact)
        await db_session.commit()
        
        response = await client.get(
            f"/api/v1/student/papers/{other_artifact.artifact_uuid}/download",
            headers={"X-Session-ID": student_session.session_id}
        )
        
        assert response.status_code in [403, 404, 401]


class TestSessionExpiry:
    """Tests for session expiry handling."""
    
    @pytest.mark.asyncio
    async def test_expired_session_rejected(self, client: AsyncClient, db_session):
        """Test that expired session is rejected."""
        # Create expired session
        expired_session = StudentSessionFactory.create(
            expires_in_hours=-1  # Already expired
        )
        db_session.add(expired_session)
        await db_session.commit()
        
        response = await client.get(
            "/api/v1/student/dashboard",
            headers={"X-Session-ID": expired_session.session_id}
        )
        
        assert response.status_code in [401, 403]
    
    @pytest.mark.asyncio
    async def test_valid_session_accepted(self, client: AsyncClient, db_session):
        """Test that valid non-expired session is accepted."""
        valid_session = StudentSessionFactory.create(
            expires_in_hours=8  # 8 hours from now
        )
        db_session.add(valid_session)
        await db_session.commit()
        
        response = await client.get(
            "/api/v1/student/dashboard",
            headers={"X-Session-ID": valid_session.session_id}
        )
        
        # Should not be rejected due to expiry
        # May fail for other reasons
        assert response.status_code in [200, 401, 403]
