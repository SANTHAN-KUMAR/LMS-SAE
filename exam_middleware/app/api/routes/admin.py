"""
Admin API Routes
Administrative functions for system management
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import logging

from app.db.database import get_db
from app.db.models import StaffUser, SubjectMapping, ExaminationArtifact
from app.schemas import (
    SubjectMappingCreate,
    SubjectMappingResponse,
    AuditLogResponse,
    SystemStatsResponse,
)
from app.services.artifact_service import ArtifactService, SubjectMappingService, AuditService
from app.services.submission_service import SubmissionService
from app.services.moodle_client import MoodleClient, MoodleAPIError
from app.api.routes.auth import get_current_staff
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================
# Subject Mapping Management
# ============================================

@router.get("/mappings", response_model=list[SubjectMappingResponse])
async def list_subject_mappings(
    db: AsyncSession = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff)
):
    """
    List all subject to assignment mappings
    """
    mapping_service = SubjectMappingService(db)
    mappings = await mapping_service.get_all_active()
    
    return [
        SubjectMappingResponse(
            id=m.id,
            subject_code=m.subject_code,
            subject_name=m.subject_name,
            moodle_course_id=m.moodle_course_id,
            moodle_assignment_id=m.moodle_assignment_id,
            moodle_assignment_name=m.moodle_assignment_name,
            exam_session=m.exam_session,
            is_active=m.is_active,
            created_at=m.created_at,
            last_verified_at=m.last_verified_at
        )
        for m in mappings
    ]


@router.post("/mappings", response_model=SubjectMappingResponse)
async def create_subject_mapping(
    mapping: SubjectMappingCreate,
    db: AsyncSession = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff)
):
    """
    Create a new subject to assignment mapping
    """
    mapping_service = SubjectMappingService(db)
    
    # Check if mapping already exists
    existing = await mapping_service.get_mapping(mapping.subject_code)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mapping for {mapping.subject_code} already exists"
        )
    
    new_mapping = await mapping_service.create_mapping(
        subject_code=mapping.subject_code,
        moodle_course_id=mapping.moodle_course_id,
        moodle_assignment_id=mapping.moodle_assignment_id,
        subject_name=mapping.subject_name,
        moodle_assignment_name=mapping.moodle_assignment_name,
        exam_session=mapping.exam_session
    )
    
    await db.commit()
    
    return SubjectMappingResponse(
        id=new_mapping.id,
        subject_code=new_mapping.subject_code,
        subject_name=new_mapping.subject_name,
        moodle_course_id=new_mapping.moodle_course_id,
        moodle_assignment_id=new_mapping.moodle_assignment_id,
        moodle_assignment_name=new_mapping.moodle_assignment_name,
        exam_session=new_mapping.exam_session,
        is_active=new_mapping.is_active,
        created_at=new_mapping.created_at,
        last_verified_at=new_mapping.last_verified_at
    )


@router.post("/mappings/sync")
async def sync_mappings_from_config(
    db: AsyncSession = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff)
):
    """
    Sync subject mappings from configuration
    """
    mapping_service = SubjectMappingService(db)
    created = await mapping_service.sync_from_config()
    await db.commit()
    
    return {
        "message": f"Synced {created} new mappings from configuration",
        "created": created
    }


@router.post("/mappings/discover")
async def discover_assignments_from_moodle(
    db: AsyncSession = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff)
):
    """
    Discover assignments from Moodle using admin token
    
    This uses the configured admin token to fetch course and assignment information
    """
    if not settings.moodle_admin_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin token not configured"
        )
    
    client = MoodleClient(token=settings.moodle_admin_token)
    
    try:
        # Get site info to verify token works
        site_info = await client.get_site_info()
        
        # This is a simplified example - in production you would:
        # 1. Get all courses the admin can see
        # 2. For each course, get assignments
        # 3. Create or update mappings
        
        return {
            "message": "Discovery successful",
            "site": site_info.get("sitename"),
            "user": site_info.get("fullname"),
            "note": "Use the Moodle admin panel to find course and assignment IDs"
        }
        
    except MoodleAPIError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Moodle API error: {e.message}"
        )
    finally:
        await client.close()


@router.delete("/mappings/{mapping_id}")
async def delete_subject_mapping(
    mapping_id: int,
    db: AsyncSession = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff)
):
    """
    Delete (deactivate) a subject mapping
    """
    result = await db.execute(
        select(SubjectMapping).where(SubjectMapping.id == mapping_id)
    )
    mapping = result.scalar_one_or_none()
    
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mapping not found"
        )
    
    mapping.is_active = False
    await db.commit()
    
    return {"message": f"Mapping {mapping.subject_code} deactivated"}


# ============================================
# System Statistics
# ============================================

@router.get("/stats", response_model=SystemStatsResponse)
async def get_system_stats(
    db: AsyncSession = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff)
):
    """
    Get system-wide statistics
    """
    artifact_service = ArtifactService(db)
    stats = await artifact_service.get_stats()
    
    # Count active sessions
    from app.db.models import StudentSession
    from datetime import datetime
    
    result = await db.execute(
        select(StudentSession).where(StudentSession.expires_at > datetime.utcnow())
    )
    active_sessions = len(result.scalars().all())
    
    return SystemStatsResponse(
        total_artifacts=sum(stats.values()),
        pending_review=stats.get("pending", 0) + stats.get("pending_review", 0),
        submitted=stats.get("completed", 0) + stats.get("submitted_to_lms", 0),
        failed=stats.get("failed", 0),
        queued=stats.get("queued", 0),
        active_sessions=active_sessions
    )


# ============================================
# Audit Logs
# ============================================

@router.get("/audit-logs", response_model=list[AuditLogResponse])
async def get_audit_logs(
    limit: int = Query(default=100, le=500),
    artifact_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff)
):
    """
    Get audit logs
    """
    audit_service = AuditService(db)
    
    if artifact_id:
        logs = await audit_service.get_for_artifact(artifact_id)
    else:
        logs = await audit_service.get_recent(limit=limit)
    
    return [
        AuditLogResponse(
            id=log.id,
            action=log.action,
            action_category=log.action_category,
            description=log.description,
            actor_type=log.actor_type,
            actor_username=log.actor_username,
            created_at=log.created_at
        )
        for log in logs
    ]


# ============================================
# Queue Management
# ============================================

@router.post("/queue/retry")
async def retry_queued_submissions(
    db: AsyncSession = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff)
):
    """
    Manually trigger retry of queued submissions
    """
    if not settings.moodle_admin_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin token not configured for queue processing"
        )
    
    submission_service = SubmissionService(db)
    result = await submission_service.retry_queued_submissions(settings.moodle_admin_token)
    
    return result


@router.get("/queue/status")
async def get_queue_status(
    db: AsyncSession = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff)
):
    """
    Get status of the submission queue
    """
    from app.db.models import SubmissionQueue
    
    result = await db.execute(select(SubmissionQueue))
    queue_items = result.scalars().all()
    
    status_counts = {}
    for item in queue_items:
        status_counts[item.status] = status_counts.get(item.status, 0) + 1
    
    return {
        "total_items": len(queue_items),
        "by_status": status_counts,
        "items": [
            {
                "id": item.id,
                "artifact_id": item.artifact_id,
                "status": item.status,
                "retry_count": item.retry_count,
                "queued_at": item.queued_at.isoformat() if item.queued_at else None,
                "last_error": item.last_error
            }
            for item in queue_items[:50]
        ]
    }


# ============================================
# Artifact Management
# ============================================

@router.get("/artifacts/{artifact_uuid}")
async def get_artifact_details(
    artifact_uuid: str,
    db: AsyncSession = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff)
):
    """
    Get detailed artifact information (admin view)
    """
    artifact_service = ArtifactService(db)
    artifact = await artifact_service.get_by_uuid(artifact_uuid)
    
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found"
        )
    
    return {
        "id": artifact.id,
        "artifact_uuid": str(artifact.artifact_uuid),
        "raw_filename": artifact.raw_filename,
        "original_filename": artifact.original_filename,
        "parsed_reg_no": artifact.parsed_reg_no,
        "parsed_subject_code": artifact.parsed_subject_code,
        "file_hash": artifact.file_hash,
        "file_size_bytes": artifact.file_size_bytes,
        "workflow_status": artifact.workflow_status.value,
        "moodle_user_id": artifact.moodle_user_id,
        "moodle_assignment_id": artifact.moodle_assignment_id,
        "moodle_draft_item_id": artifact.moodle_draft_item_id,
        "moodle_submission_id": artifact.moodle_submission_id,
        "transaction_id": artifact.transaction_id,
        "uploaded_at": artifact.uploaded_at.isoformat() if artifact.uploaded_at else None,
        "submit_timestamp": artifact.submit_timestamp.isoformat() if artifact.submit_timestamp else None,
        "error_message": artifact.error_message,
        "retry_count": artifact.retry_count,
        "transaction_log": artifact.transaction_log
    }


@router.post("/artifacts/{artifact_uuid}/reset")
async def reset_artifact_status(
    artifact_uuid: str,
    db: AsyncSession = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff)
):
    """
    Reset artifact status to pending (for retry)
    """
    artifact_service = ArtifactService(db)
    artifact = await artifact_service.get_by_uuid(artifact_uuid)
    
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found"
        )
    
    from app.db.models import WorkflowStatus
    
    artifact = await artifact_service.update_status(
        artifact_id=artifact.id,
        status=WorkflowStatus.PENDING_REVIEW,
        log_action="admin_reset",
        log_details={"reset_by": current_staff.username}
    )
    
    # Clear error state
    artifact.error_message = None
    artifact.moodle_draft_item_id = None
    
    await db.commit()
    
    return {"message": "Artifact status reset to pending"}
