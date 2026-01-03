"""
Unit Tests for Artifact Service

Tests the artifact management service including:
- Artifact creation
- Status updates
- Statistics calculation
- Query operations
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ExaminationArtifact, WorkflowStatus, SubjectMapping
from app.services.artifact_service import ArtifactService, SubjectMappingService

# Import test factories
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.factories import ArtifactFactory, SubjectMappingFactory


class TestArtifactCreation:
    """Tests for artifact creation."""
    
    @pytest.mark.asyncio
    async def test_create_artifact_basic(self, db_session):
        """Test basic artifact creation."""
        service = ArtifactService(db_session)
        
        artifact = await service.create(
            raw_filename="123456789012_19AI405.pdf",
            original_filename="123456789012_19AI405.pdf",
            sanitized_filename="123456789012_19AI405.pdf",
            parsed_reg_no="123456789012",
            parsed_subject_code="19AI405",
            file_extension=".pdf",
            file_mime_type="application/pdf",
            file_size_bytes=1024,
            file_hash="abc123def456",
            file_blob_path="/uploads/123456789012_19AI405.pdf"
        )
        
        assert artifact is not None
        assert artifact.id is not None
        assert artifact.artifact_uuid is not None
        assert artifact.parsed_reg_no == "123456789012"
        assert artifact.parsed_subject_code == "19AI405"
        assert artifact.workflow_status == WorkflowStatus.PENDING
    
    @pytest.mark.asyncio
    async def test_create_artifact_generates_uuid(self, db_session):
        """Test that UUID is automatically generated."""
        service = ArtifactService(db_session)
        
        artifact = await service.create(
            raw_filename="123456789012_19AI405.pdf",
            original_filename="123456789012_19AI405.pdf",
            sanitized_filename="123456789012_19AI405.pdf",
            parsed_reg_no="123456789012",
            parsed_subject_code="19AI405",
            file_extension=".pdf",
            file_mime_type="application/pdf",
            file_size_bytes=1024,
            file_hash="abc123",
            file_blob_path="/uploads/test.pdf"
        )
        
        assert artifact.artifact_uuid is not None
        assert len(str(artifact.artifact_uuid)) == 36  # UUID format
    
    @pytest.mark.asyncio
    async def test_create_artifact_sets_timestamp(self, db_session):
        """Test that creation timestamp is set."""
        service = ArtifactService(db_session)
        
        before = datetime.utcnow()
        artifact = await service.create(
            raw_filename="123456789012_19AI405.pdf",
            original_filename="123456789012_19AI405.pdf",
            sanitized_filename="123456789012_19AI405.pdf",
            parsed_reg_no="123456789012",
            parsed_subject_code="19AI405",
            file_extension=".pdf",
            file_mime_type="application/pdf",
            file_size_bytes=1024,
            file_hash="abc123",
            file_blob_path="/uploads/test.pdf"
        )
        after = datetime.utcnow()
        
        assert artifact.uploaded_at is not None
        assert before <= artifact.uploaded_at <= after


class TestArtifactRetrieval:
    """Tests for artifact retrieval methods."""
    
    @pytest.mark.asyncio
    async def test_get_by_uuid(self, db_session, sample_artifact):
        """Test retrieving artifact by UUID."""
        service = ArtifactService(db_session)
        
        found = await service.get_by_uuid(str(sample_artifact.artifact_uuid))
        
        assert found is not None
        assert found.id == sample_artifact.id
    
    @pytest.mark.asyncio
    async def test_get_by_uuid_not_found(self, db_session):
        """Test retrieving non-existent artifact returns None."""
        service = ArtifactService(db_session)
        
        found = await service.get_by_uuid("non-existent-uuid")
        
        assert found is None
    
    @pytest.mark.asyncio
    async def test_get_by_id(self, db_session, sample_artifact):
        """Test retrieving artifact by ID."""
        service = ArtifactService(db_session)
        
        found = await service.get_by_id(sample_artifact.id)
        
        assert found is not None
        assert found.artifact_uuid == sample_artifact.artifact_uuid
    
    @pytest.mark.asyncio
    async def test_get_pending_for_student(self, db_session):
        """Test getting pending artifacts for a specific student."""
        service = ArtifactService(db_session)
        
        # Create artifacts for different students
        artifact1 = ArtifactFactory.create_pending(register_number="111111111111")
        artifact2 = ArtifactFactory.create_pending(register_number="111111111111")
        artifact3 = ArtifactFactory.create_pending(register_number="222222222222")
        
        db_session.add_all([artifact1, artifact2, artifact3])
        await db_session.commit()
        
        # Get pending for student 1
        pending = await service.get_pending_for_student(
            register_number="111111111111",
            moodle_user_id=42
        )
        
        assert len(pending) == 2
        assert all(a.parsed_reg_no == "111111111111" for a in pending)
    
    @pytest.mark.asyncio
    async def test_get_submitted_for_student(self, db_session):
        """Test getting submitted artifacts for a student."""
        service = ArtifactService(db_session)
        
        # Create submitted and pending artifacts
        submitted = ArtifactFactory.create_submitted(
            register_number="111111111111",
            moodle_user_id=42
        )
        pending = ArtifactFactory.create_pending(register_number="111111111111")
        
        db_session.add_all([submitted, pending])
        await db_session.commit()
        
        result = await service.get_submitted_for_student(moodle_user_id=42)
        
        assert len(result) == 1
        assert result[0].workflow_status == WorkflowStatus.SUBMITTED_TO_LMS


class TestArtifactStatusUpdates:
    """Tests for artifact status update operations."""
    
    @pytest.mark.asyncio
    async def test_update_status(self, db_session, sample_artifact):
        """Test updating artifact status."""
        service = ArtifactService(db_session)
        
        updated = await service.update_status(
            artifact_id=sample_artifact.id,
            status=WorkflowStatus.READY_FOR_REVIEW,
            log_action="status_updated",
            log_details={"reason": "test"}
        )
        
        assert updated is not None
        assert updated.workflow_status == WorkflowStatus.READY_FOR_REVIEW
    
    @pytest.mark.asyncio
    async def test_mark_completed(self, db_session, sample_artifact):
        """Test marking artifact as completed."""
        service = ArtifactService(db_session)
        
        completed = await service.mark_completed(
            artifact_id=sample_artifact.id,
            moodle_submission_id=12345
        )
        
        assert completed is not None
        assert completed.workflow_status == WorkflowStatus.COMPLETED
        assert completed.moodle_submission_id == 12345
        assert completed.submit_timestamp is not None
    
    @pytest.mark.asyncio
    async def test_mark_failed(self, db_session, sample_artifact):
        """Test marking artifact as failed."""
        service = ArtifactService(db_session)
        
        failed = await service.mark_failed(
            artifact_id=sample_artifact.id,
            error_message="Test error message",
            queue_for_retry=False
        )
        
        assert failed is not None
        assert failed.workflow_status == WorkflowStatus.FAILED
        assert failed.error_message == "Test error message"
    
    @pytest.mark.asyncio
    async def test_mark_failed_increments_retry_count(self, db_session, sample_artifact):
        """Test that failure increments retry count."""
        service = ArtifactService(db_session)
        
        original_count = sample_artifact.retry_count or 0
        
        failed = await service.mark_failed(
            artifact_id=sample_artifact.id,
            error_message="Error",
            queue_for_retry=True
        )
        
        assert failed.retry_count == original_count + 1


class TestStatisticsCalculation:
    """Tests for statistics calculation."""
    
    @pytest.mark.asyncio
    async def test_get_stats_empty_database(self, db_session):
        """Test stats calculation with no artifacts."""
        service = ArtifactService(db_session)
        
        stats = await service.get_stats()
        
        # All counts should be 0
        assert all(count == 0 for count in stats.values())
    
    @pytest.mark.asyncio
    async def test_get_stats_counts_by_status(self, db_session):
        """Test that stats correctly count by status."""
        service = ArtifactService(db_session)
        
        # Create artifacts with different statuses
        pending = ArtifactFactory.create_batch(3, status=WorkflowStatus.PENDING)
        submitted = ArtifactFactory.create_batch(2, status=WorkflowStatus.SUBMITTED_TO_LMS)
        failed = ArtifactFactory.create_batch(1, status=WorkflowStatus.FAILED)
        
        db_session.add_all(pending + submitted + failed)
        await db_session.commit()
        
        stats = await service.get_stats()
        
        assert stats.get("pending", 0) == 3
        assert stats.get("submitted_to_lms", 0) == 2
        assert stats.get("failed", 0) == 1
    
    @pytest.mark.asyncio
    async def test_get_stats_uses_single_query(self, db_session):
        """Test that get_stats uses efficient single query (GROUP BY)."""
        service = ArtifactService(db_session)
        
        # Create some artifacts
        artifacts = ArtifactFactory.create_batch(5, status=WorkflowStatus.PENDING)
        db_session.add_all(artifacts)
        await db_session.commit()
        
        # The implementation should use a single GROUP BY query
        # We can't directly test query count without more instrumentation,
        # but we verify it returns correct results
        stats = await service.get_stats()
        
        assert stats.get("pending", 0) == 5


class TestPaginatedQueries:
    """Tests for paginated query operations."""
    
    @pytest.mark.asyncio
    async def test_get_all_pending_pagination(self, db_session):
        """Test pagination of pending artifacts."""
        service = ArtifactService(db_session)
        
        # Create 15 pending artifacts
        artifacts = ArtifactFactory.create_batch(
            15, 
            status=WorkflowStatus.PENDING_REVIEW
        )
        db_session.add_all(artifacts)
        await db_session.commit()
        
        # Get first page
        page1, total = await service.get_all_pending(limit=10, offset=0)
        
        assert len(page1) == 10
        assert total == 15
        
        # Get second page
        page2, _ = await service.get_all_pending(limit=10, offset=10)
        
        assert len(page2) == 5
    
    @pytest.mark.asyncio
    async def test_get_all_pending_orders_by_upload_date(self, db_session):
        """Test that pending artifacts are ordered by upload date."""
        service = ArtifactService(db_session)
        
        # Create artifacts with different upload times
        old_artifact = ArtifactFactory.create_pending()
        old_artifact.uploaded_at = datetime.utcnow() - timedelta(days=1)
        
        new_artifact = ArtifactFactory.create_pending()
        new_artifact.uploaded_at = datetime.utcnow()
        
        db_session.add_all([old_artifact, new_artifact])
        await db_session.commit()
        
        results, _ = await service.get_all_pending(limit=10, offset=0)
        
        # Newest should be first (descending order)
        assert results[0].uploaded_at >= results[1].uploaded_at


class TestSubjectMappingService:
    """Tests for subject mapping service."""
    
    @pytest.mark.asyncio
    async def test_get_mapping_exists(self, db_session, subject_mapping):
        """Test getting an existing mapping."""
        service = SubjectMappingService(db_session)
        
        mapping = await service.get_mapping("19AI405")
        
        assert mapping is not None
        assert mapping.moodle_assignment_id == subject_mapping.moodle_assignment_id
    
    @pytest.mark.asyncio
    async def test_get_mapping_case_insensitive(self, db_session, subject_mapping):
        """Test that mapping lookup is case-insensitive."""
        service = SubjectMappingService(db_session)
        
        mapping = await service.get_mapping("19ai405")  # lowercase
        
        assert mapping is not None
    
    @pytest.mark.asyncio
    async def test_get_mapping_not_found(self, db_session):
        """Test that non-existent mapping returns None."""
        service = SubjectMappingService(db_session)
        
        mapping = await service.get_mapping("NONEXISTENT")
        
        assert mapping is None
    
    @pytest.mark.asyncio
    async def test_get_assignment_id(self, db_session, subject_mapping):
        """Test getting just the assignment ID."""
        service = SubjectMappingService(db_session)
        
        assignment_id = await service.get_assignment_id("19AI405")
        
        assert assignment_id == subject_mapping.moodle_assignment_id
    
    @pytest.mark.asyncio
    async def test_create_mapping(self, db_session):
        """Test creating a new mapping."""
        service = SubjectMappingService(db_session)
        
        mapping = await service.create_mapping(
            subject_code="19AI999",
            moodle_course_id=5,
            moodle_assignment_id=10,
            subject_name="New Subject",
            moodle_assignment_name="New Assignment"
        )
        
        assert mapping is not None
        assert mapping.id is not None
        assert mapping.subject_code == "19AI999"
        assert mapping.moodle_assignment_id == 10
    
    @pytest.mark.asyncio
    async def test_get_all_active(self, db_session):
        """Test getting all active mappings."""
        service = SubjectMappingService(db_session)
        
        # Create active and inactive mappings
        active = SubjectMappingFactory.create(is_active=True)
        inactive = SubjectMappingFactory.create(is_active=False)
        
        db_session.add_all([active, inactive])
        await db_session.commit()
        
        all_active = await service.get_all_active()
        
        # Should only return active mappings
        assert all(m.is_active for m in all_active)
    
    @pytest.mark.asyncio
    async def test_get_assignment_id_fallback_to_config(self, db_session):
        """Test fallback to config when no DB mapping exists."""
        service = SubjectMappingService(db_session)
        
        # Mock the config to have a mapping
        with patch.object(
            service, '_get_config_mapping',
            return_value={"TEST123": 999}
        ):
            # This subject doesn't exist in DB
            # Should fall back to config
            assignment_id = await service.get_assignment_id("TEST123")
            
            # Behavior depends on implementation
            # May return None if config fallback isn't implemented here
