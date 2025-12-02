"""
Artifact Service
Business logic for managing examination artifacts
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_
from sqlalchemy.orm import selectinload

from app.db.models import (
    ExaminationArtifact,
    SubjectMapping,
    AuditLog,
    SubmissionQueue,
    WorkflowStatus
)
from app.schemas import (
    ArtifactCreate,
    ArtifactResponse,
    StudentPendingPaper,
    StudentDashboardResponse,
)
from app.core.security import generate_transaction_id
from app.core.config import settings

logger = logging.getLogger(__name__)


class ArtifactService:
    """
    Service for managing examination artifacts
    Implements the business logic from the design document
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_artifact(
        self,
        raw_filename: str,
        original_filename: str,
        file_blob_path: str,
        file_hash: str,
        parsed_reg_no: Optional[str] = None,
        parsed_subject_code: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        mime_type: Optional[str] = None,
        uploaded_by_staff_id: Optional[int] = None
    ) -> ExaminationArtifact:
        """
        Create a new examination artifact
        
        Args:
            raw_filename: Original uploaded filename
            original_filename: Sanitized filename
            file_blob_path: Path to stored file
            file_hash: SHA-256 hash of file content
            parsed_reg_no: Extracted register number
            parsed_subject_code: Extracted subject code
            file_size_bytes: File size
            mime_type: MIME type
            uploaded_by_staff_id: Staff user who uploaded
            
        Returns:
            Created ExaminationArtifact
        """
        # Generate transaction ID for idempotency
        transaction_id = None
        if parsed_reg_no and parsed_subject_code:
            transaction_id = generate_transaction_id(
                parsed_reg_no,
                parsed_subject_code,
                datetime.utcnow().strftime("%Y%m")
            )
            
            # Check for existing artifact with same transaction ID
            existing = await self.get_by_transaction_id(transaction_id)
            if existing:
                logger.warning(f"Duplicate artifact detected: {transaction_id}")
                # Return existing instead of creating duplicate
                return existing
        
        artifact = ExaminationArtifact(
            raw_filename=raw_filename,
            original_filename=original_filename,
            file_blob_path=file_blob_path,
            file_hash=file_hash,
            parsed_reg_no=parsed_reg_no,
            parsed_subject_code=parsed_subject_code,
            file_size_bytes=file_size_bytes,
            mime_type=mime_type,
            uploaded_by_staff_id=uploaded_by_staff_id,
            transaction_id=transaction_id,
            workflow_status=WorkflowStatus.PENDING if parsed_reg_no else WorkflowStatus.FAILED
        )
        
        # Add initial log entry
        artifact.add_log_entry("created", {
            "filename": raw_filename,
            "parsed_reg_no": parsed_reg_no,
            "parsed_subject_code": parsed_subject_code
        })
        
        self.db.add(artifact)
        await self.db.flush()
        await self.db.refresh(artifact)
        
        logger.info(f"Created artifact: {artifact.artifact_uuid}")
        return artifact
    
    async def get_by_uuid(self, artifact_uuid: str) -> Optional[ExaminationArtifact]:
        """Get artifact by UUID"""
        result = await self.db.execute(
            select(ExaminationArtifact)
            .where(ExaminationArtifact.artifact_uuid == artifact_uuid)
        )
        return result.scalar_one_or_none()
    
    async def get_by_transaction_id(self, transaction_id: str) -> Optional[ExaminationArtifact]:
        """Get artifact by transaction ID (for idempotency)"""
        result = await self.db.execute(
            select(ExaminationArtifact)
            .where(ExaminationArtifact.transaction_id == transaction_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_id(self, artifact_id: int) -> Optional[ExaminationArtifact]:
        """Get artifact by ID"""
        result = await self.db.execute(
            select(ExaminationArtifact)
            .where(ExaminationArtifact.id == artifact_id)
        )
        return result.scalar_one_or_none()
    
    async def get_pending_for_student(
        self,
        register_number: str,
        moodle_user_id: int
    ) -> List[ExaminationArtifact]:
        """
        Get pending artifacts for a specific student
        
        Security: Only returns artifacts matching the student's register number or Moodle username
        Note: register_number can be either the 12-digit register or the Moodle username
        """
        from sqlalchemy import or_
        result = await self.db.execute(
            select(ExaminationArtifact)
            .where(
                and_(
                    or_(
                        ExaminationArtifact.parsed_reg_no == register_number,
                        ExaminationArtifact.moodle_username == register_number
                    ),
                    ExaminationArtifact.workflow_status.in_([
                        WorkflowStatus.PENDING,
                        WorkflowStatus.PENDING_REVIEW,
                        WorkflowStatus.VALIDATED,
                        WorkflowStatus.READY_FOR_REVIEW
                    ])
                )
            )
            .order_by(ExaminationArtifact.uploaded_at.desc())
        )
        return list(result.scalars().all())
    
    async def get_submitted_for_student(
        self,
        register_number: str
    ) -> List[ExaminationArtifact]:
        """Get submitted artifacts for a student"""
        result = await self.db.execute(
            select(ExaminationArtifact)
            .where(
                and_(
                    ExaminationArtifact.parsed_reg_no == register_number,
                    ExaminationArtifact.workflow_status.in_([
                        WorkflowStatus.SUBMITTED_TO_LMS,
                        WorkflowStatus.COMPLETED
                    ])
                )
            )
            .order_by(ExaminationArtifact.submit_timestamp.desc())
        )
        return list(result.scalars().all())
    
    async def update_status(
        self,
        artifact_id: int,
        status: WorkflowStatus,
        log_action: Optional[str] = None,
        log_details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> Optional[ExaminationArtifact]:
        """Update artifact workflow status"""
        artifact = await self.get_by_id(artifact_id)
        if not artifact:
            return None
        
        old_status = artifact.workflow_status
        artifact.workflow_status = status
        
        if error_message:
            artifact.error_message = error_message
        
        if log_action:
            artifact.add_log_entry(log_action, {
                "old_status": old_status.value if old_status else None,
                "new_status": status.value,
                **(log_details or {})
            })
        
        await self.db.flush()
        await self.db.refresh(artifact)
        
        logger.info(f"Updated artifact {artifact_id} status: {old_status} -> {status}")
        return artifact
    
    async def resolve_moodle_mapping(
        self,
        artifact_id: int,
        moodle_user_id: int,
        moodle_username: str,
        moodle_assignment_id: int,
        moodle_course_id: Optional[int] = None
    ) -> Optional[ExaminationArtifact]:
        """
        Resolve Moodle mapping for an artifact
        
        This is called after student authentication to link
        the artifact to their Moodle user and the correct assignment
        """
        artifact = await self.get_by_id(artifact_id)
        if not artifact:
            return None
        
        artifact.moodle_user_id = moodle_user_id
        artifact.moodle_username = moodle_username
        artifact.moodle_assignment_id = moodle_assignment_id
        artifact.moodle_course_id = moodle_course_id
        artifact.validated_at = datetime.utcnow()
        
        if artifact.workflow_status == WorkflowStatus.PENDING:
            artifact.workflow_status = WorkflowStatus.READY_FOR_REVIEW
        
        artifact.add_log_entry("moodle_resolved", {
            "moodle_user_id": moodle_user_id,
            "moodle_assignment_id": moodle_assignment_id
        })
        
        await self.db.flush()
        await self.db.refresh(artifact)
        
        return artifact
    
    async def mark_submitting(
        self,
        artifact_id: int,
        moodle_draft_item_id: int
    ) -> Optional[ExaminationArtifact]:
        """Mark artifact as currently being submitted (for retry logic)"""
        artifact = await self.get_by_id(artifact_id)
        if not artifact:
            return None
        
        artifact.workflow_status = WorkflowStatus.UPLOADING
        artifact.moodle_draft_item_id = moodle_draft_item_id
        
        artifact.add_log_entry("upload_started", {
            "draft_item_id": moodle_draft_item_id
        })
        
        await self.db.flush()
        await self.db.refresh(artifact)
        return artifact
    
    async def mark_submitted(
        self,
        artifact_id: int,
        moodle_submission_id: Optional[str] = None,
        lms_transaction_id: Optional[str] = None
    ) -> Optional[ExaminationArtifact]:
        """Mark artifact as successfully submitted to Moodle"""
        artifact = await self.get_by_id(artifact_id)
        if not artifact:
            return None
        
        artifact.workflow_status = WorkflowStatus.COMPLETED
        artifact.submit_timestamp = datetime.utcnow()
        artifact.completed_at = datetime.utcnow()
        # Ensure moodle_submission_id is a string (database column is VARCHAR)
        artifact.moodle_submission_id = str(moodle_submission_id) if moodle_submission_id is not None else None
        artifact.lms_transaction_id = lms_transaction_id
        
        artifact.add_log_entry("submission_completed", {
            "moodle_submission_id": moodle_submission_id,
            "lms_transaction_id": lms_transaction_id
        })
        
        await self.db.flush()
        await self.db.refresh(artifact)
        
        logger.info(f"Artifact {artifact_id} marked as submitted")
        return artifact
    
    async def mark_failed(
        self,
        artifact_id: int,
        error_message: str,
        queue_for_retry: bool = False
    ) -> Optional[ExaminationArtifact]:
        """Mark artifact as failed"""
        artifact = await self.get_by_id(artifact_id)
        if not artifact:
            return None
        
        artifact.workflow_status = WorkflowStatus.QUEUED if queue_for_retry else WorkflowStatus.FAILED
        artifact.error_message = error_message
        artifact.retry_count = (artifact.retry_count or 0) + 1
        
        artifact.add_log_entry("submission_failed", {
            "error": error_message,
            "retry_count": artifact.retry_count,
            "queued": queue_for_retry
        })
        
        # Add to retry queue if needed
        if queue_for_retry:
            queue_item = SubmissionQueue(
                artifact_id=artifact_id,
                status="QUEUED",
                last_error=error_message
            )
            self.db.add(queue_item)
        
        await self.db.flush()
        await self.db.refresh(artifact)
        
        return artifact
    
    async def get_all_pending(
        self,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[ExaminationArtifact], int]:
        """Get all pending artifacts (for admin view)"""
        # Get count
        count_result = await self.db.execute(
            select(ExaminationArtifact)
            .where(
                ExaminationArtifact.workflow_status.in_([
                    WorkflowStatus.PENDING,
                    WorkflowStatus.PENDING_REVIEW
                ])
            )
        )
        total = len(count_result.scalars().all())
        
        # Get paginated results
        result = await self.db.execute(
            select(ExaminationArtifact)
            .where(
                ExaminationArtifact.workflow_status.in_([
                    WorkflowStatus.PENDING,
                    WorkflowStatus.PENDING_REVIEW
                ])
            )
            .order_by(ExaminationArtifact.uploaded_at.desc())
            .limit(limit)
            .offset(offset)
        )
        
        return list(result.scalars().all()), total
    
    async def get_stats(self) -> Dict[str, int]:
        """Get artifact statistics"""
        stats = {}
        
        for status in WorkflowStatus:
            result = await self.db.execute(
                select(ExaminationArtifact)
                .where(ExaminationArtifact.workflow_status == status)
            )
            stats[status.value.lower()] = len(result.scalars().all())
        
        return stats


class SubjectMappingService:
    """Service for managing subject to assignment mappings"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_mapping(self, subject_code: str) -> Optional[SubjectMapping]:
        """Get mapping for a subject code"""
        result = await self.db.execute(
            select(SubjectMapping)
            .where(
                and_(
                    SubjectMapping.subject_code == subject_code.upper(),
                    SubjectMapping.is_active == True
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def get_assignment_id(self, subject_code: str) -> Optional[int]:
        """Get assignment ID for a subject code"""
        # First check database
        mapping = await self.get_mapping(subject_code)
        if mapping:
            return mapping.moodle_assignment_id
        
        # Fall back to config
        config_mapping = settings.get_subject_assignment_mapping()
        return config_mapping.get(subject_code.upper())
    
    async def create_mapping(
        self,
        subject_code: str,
        moodle_course_id: int,
        moodle_assignment_id: int,
        subject_name: Optional[str] = None,
        moodle_assignment_name: Optional[str] = None,
        exam_session: Optional[str] = None
    ) -> SubjectMapping:
        """Create a new subject mapping"""
        mapping = SubjectMapping(
            subject_code=subject_code.upper(),
            subject_name=subject_name,
            moodle_course_id=moodle_course_id,
            moodle_assignment_id=moodle_assignment_id,
            moodle_assignment_name=moodle_assignment_name,
            exam_session=exam_session,
            is_active=True
        )
        
        self.db.add(mapping)
        await self.db.flush()
        await self.db.refresh(mapping)
        
        return mapping
    
    async def get_all_active(self) -> List[SubjectMapping]:
        """Get all active mappings"""
        result = await self.db.execute(
            select(SubjectMapping)
            .where(SubjectMapping.is_active == True)
            .order_by(SubjectMapping.subject_code)
        )
        return list(result.scalars().all())
    
    async def sync_from_config(self) -> int:
        """Sync mappings from configuration"""
        config_mapping = settings.get_subject_assignment_mapping()
        created = 0
        
        for subject_code, assignment_id in config_mapping.items():
            existing = await self.get_mapping(subject_code)
            if not existing:
                await self.create_mapping(
                    subject_code=subject_code,
                    moodle_course_id=0,  # Will be resolved later
                    moodle_assignment_id=assignment_id
                )
                created += 1
        
        return created


class AuditService:
    """Service for audit logging"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def log_action(
        self,
        action: str,
        action_category: str,
        actor_type: str,
        actor_id: Optional[str] = None,
        actor_username: Optional[str] = None,
        actor_ip: Optional[str] = None,
        artifact_id: Optional[int] = None,
        description: Optional[str] = None,
        request_data: Optional[Dict[str, Any]] = None,
        response_data: Optional[Dict[str, Any]] = None,
        moodle_api_function: Optional[str] = None,
        moodle_response_code: Optional[int] = None
    ) -> AuditLog:
        """Create an audit log entry"""
        log = AuditLog(
            action=action,
            action_category=action_category,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_username=actor_username,
            actor_ip=actor_ip,
            artifact_id=artifact_id,
            description=description,
            request_data=request_data,
            response_data=response_data,
            moodle_api_function=moodle_api_function,
            moodle_response_code=moodle_response_code
        )
        
        self.db.add(log)
        await self.db.flush()
        
        return log
    
    async def get_for_artifact(self, artifact_id: int) -> List[AuditLog]:
        """Get all audit logs for an artifact"""
        result = await self.db.execute(
            select(AuditLog)
            .where(AuditLog.artifact_id == artifact_id)
            .order_by(AuditLog.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def get_recent(self, limit: int = 100) -> List[AuditLog]:
        """Get recent audit logs"""
        result = await self.db.execute(
            select(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
