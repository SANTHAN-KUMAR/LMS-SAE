"""
Student API Routes
Handles student dashboard and submission
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, Header
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import logging
import os

from app.db.database import get_db
from app.db.models import StudentSession
from app.schemas import (
    StudentDashboardResponse,
    StudentPendingPaper,
    SubmissionRequest,
    SubmissionResponse,
    ArtifactResponse,
    WorkflowStatusEnum,
)
from app.services.artifact_service import ArtifactService, SubjectMappingService, AuditService
from app.services.submission_service import SubmissionService
from app.api.routes.auth import get_current_student_session, get_decrypted_token

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_session_from_header(
    x_session_id: str = Header(..., alias="X-Session-ID"),
    db: AsyncSession = Depends(get_db)
) -> StudentSession:
    """Get student session from header"""
    return await get_current_student_session(x_session_id, db)


@router.get("/dashboard", response_model=StudentDashboardResponse)
async def get_dashboard(
    request: Request,
    session: StudentSession = Depends(get_session_from_header),
    db: AsyncSession = Depends(get_db)
):
    """
    Get student dashboard
    
    Returns:
    - List of papers pending submission
    - List of already submitted papers
    - User information
    """
    artifact_service = ArtifactService(db)
    mapping_service = SubjectMappingService(db)
    
    # Extract register number from fullname (format: "Name 212222020029")
    import re
    register_number = session.moodle_username  # fallback
    if session.moodle_fullname:
        # Extract 12-digit number from fullname
        match = re.search(r'\b(\d{12})\b', session.moodle_fullname)
        if match:
            register_number = match.group(1)
    
    # Get pending papers for this student
    pending_artifacts = await artifact_service.get_pending_for_student(
        register_number=register_number,
        moodle_user_id=session.moodle_user_id
    )
    
    # Get submitted papers
    submitted_artifacts = await artifact_service.get_submitted_for_student(
        register_number=register_number
    )
    
    # Build pending papers list with subject info
    pending_papers = []
    for artifact in pending_artifacts:
        # Get subject mapping for additional info
        mapping = None
        if artifact.parsed_subject_code:
            mapping = await mapping_service.get_mapping(artifact.parsed_subject_code)
        
        # Check if we have a valid assignment mapping
        assignment_id = await mapping_service.get_assignment_id(artifact.parsed_subject_code) if artifact.parsed_subject_code else None
        
        pending_papers.append(StudentPendingPaper(
            artifact_uuid=str(artifact.artifact_uuid),
            subject_code=artifact.parsed_subject_code or "Unknown",
            subject_name=mapping.subject_name if mapping else None,
            assignment_name=mapping.moodle_assignment_name if mapping else None,
            filename=artifact.original_filename,
            uploaded_at=artifact.uploaded_at,
            can_submit=assignment_id is not None,
            message=None if assignment_id else "Assignment mapping not found. Contact admin."
        ))
    
    # Build submitted papers list
    submitted_papers = [
        ArtifactResponse(
            id=a.id,
            artifact_uuid=str(a.artifact_uuid),
            raw_filename=a.raw_filename,
            original_filename=a.original_filename,
            parsed_reg_no=a.parsed_reg_no,
            parsed_subject_code=a.parsed_subject_code,
            workflow_status=WorkflowStatusEnum(a.workflow_status.value),
            moodle_assignment_id=a.moodle_assignment_id,
            uploaded_at=a.uploaded_at,
            submit_timestamp=a.submit_timestamp
        )
        for a in submitted_artifacts
    ]
    
    return StudentDashboardResponse(
        moodle_user_id=session.moodle_user_id,
        moodle_username=session.moodle_username,
        full_name=session.moodle_fullname,
        pending_papers=pending_papers,
        submitted_papers=submitted_papers,
        total_pending=len(pending_papers),
        total_submitted=len(submitted_papers)
    )


@router.get("/paper/{artifact_uuid}")
async def get_paper_details(
    artifact_uuid: str,
    session: StudentSession = Depends(get_session_from_header),
    db: AsyncSession = Depends(get_db)
):
    """
    Get details of a specific paper
    
    Security: Only returns if the paper belongs to the logged-in student
    """
    artifact_service = ArtifactService(db)
    artifact = await artifact_service.get_by_uuid(artifact_uuid)
    
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paper not found"
        )
    
    # Security check
    if artifact.parsed_reg_no != session.moodle_username:
        logger.warning(
            f"Unauthorized access attempt: {session.moodle_username} tried to access "
            f"paper belonging to {artifact.parsed_reg_no}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own papers"
        )
    
    # Log the view
    audit_service = AuditService(db)
    await audit_service.log_action(
        action="paper_viewed",
        action_category="view",
        actor_type="student",
        actor_id=str(session.moodle_user_id),
        actor_username=session.moodle_username,
        artifact_id=artifact.id,
        description=f"Student viewed paper: {artifact.original_filename}"
    )
    await db.commit()
    
    return {
        "artifact_uuid": str(artifact.artifact_uuid),
        "filename": artifact.original_filename,
        "register_number": artifact.parsed_reg_no,
        "subject_code": artifact.parsed_subject_code,
        "status": artifact.workflow_status.value,
        "uploaded_at": artifact.uploaded_at.isoformat() if artifact.uploaded_at else None,
        "submitted_at": artifact.submit_timestamp.isoformat() if artifact.submit_timestamp else None,
        "file_size": artifact.file_size_bytes,
        "mime_type": artifact.mime_type
    }


@router.get("/paper/{artifact_uuid}/view")
async def view_paper_file(
    artifact_uuid: str,
    session: StudentSession = Depends(get_session_from_header),
    db: AsyncSession = Depends(get_db)
):
    """
    View/download the actual paper file
    
    Returns the file for display in the browser
    """
    artifact_service = ArtifactService(db)
    artifact = await artifact_service.get_by_uuid(artifact_uuid)
    
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paper not found"
        )
    
    # Security check
    if artifact.parsed_reg_no != session.moodle_username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own papers"
        )
    
    # Check if file exists
    if not os.path.exists(artifact.file_blob_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on server"
        )
    
    # Determine media type
    media_type = artifact.mime_type or "application/pdf"
    
    return FileResponse(
        path=artifact.file_blob_path,
        media_type=media_type,
        filename=artifact.original_filename
    )


@router.post("/submit/{artifact_uuid}", response_model=SubmissionResponse)
async def submit_paper_by_uuid(
    artifact_uuid: str,
    request: Request,
    session: StudentSession = Depends(get_session_from_header),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit a paper to Moodle by artifact UUID (simplified endpoint)
    """
    import re
    
    # Extract register number from fullname (format: "Name 212222020029")
    register_number = session.moodle_username  # fallback
    if session.moodle_fullname:
        match = re.search(r'\b(\d{12})\b', session.moodle_fullname)
        if match:
            register_number = match.group(1)
    
    # Get the decrypted Moodle token
    moodle_token = get_decrypted_token(session)
    
    # Create submission service
    submission_service = SubmissionService(db)
    
    # Execute submission
    success, message, result = await submission_service.submit_artifact(
        artifact_uuid=artifact_uuid,
        moodle_token=moodle_token,
        moodle_user_id=session.moodle_user_id,
        moodle_username=session.moodle_username,
        register_number=register_number,
        actor_ip=request.client.host if request.client else None,
        lock_submission=True
    )
    
    await db.commit()
    
    if not success:
        if result and result.get("queued"):
            return SubmissionResponse(
                success=False,
                message=message,
                artifact_uuid=artifact_uuid,
                workflow_status=WorkflowStatusEnum.QUEUED
            )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )
    
    # Get updated artifact for response
    artifact_service = ArtifactService(db)
    artifact = await artifact_service.get_by_uuid(artifact_uuid)
    
    return SubmissionResponse(
        success=True,
        message=message,
        artifact_uuid=artifact_uuid,
        workflow_status=WorkflowStatusEnum(artifact.workflow_status.value),
        moodle_submission_id=artifact.moodle_submission_id,
        submitted_at=artifact.submit_timestamp
    )


@router.post("/submit", response_model=SubmissionResponse)
async def submit_paper(
    submission: SubmissionRequest,
    request: Request,
    session: StudentSession = Depends(get_session_from_header),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit a paper to Moodle
    
    This is the main submission endpoint that:
    1. Validates the student owns the paper
    2. Uploads the file to Moodle draft area
    3. Links the file to the assignment
    4. Finalizes the submission
    
    The submission is atomic - if any step fails, the operation can be retried.
    """
    import re
    
    if not submission.confirm_submission:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must confirm the submission"
        )
    
    # Extract register number from fullname (format: "Name 212222020029")
    register_number = session.moodle_username  # fallback
    if session.moodle_fullname:
        match = re.search(r'\b(\d{12})\b', session.moodle_fullname)
        if match:
            register_number = match.group(1)
    
    # Get the decrypted Moodle token
    moodle_token = get_decrypted_token(session)
    
    # Create submission service
    submission_service = SubmissionService(db)
    
    # Execute submission
    success, message, result = await submission_service.submit_artifact(
        artifact_uuid=submission.artifact_uuid,
        moodle_token=moodle_token,
        moodle_user_id=session.moodle_user_id,
        moodle_username=session.moodle_username,
        register_number=register_number,
        actor_ip=request.client.host if request.client else None,
        lock_submission=True
    )
    
    await db.commit()
    
    if not success:
        # Check if it was queued
        if result and result.get("queued"):
            return SubmissionResponse(
                success=False,
                message=message,
                artifact_uuid=submission.artifact_uuid,
                workflow_status=WorkflowStatusEnum.QUEUED
            )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )
    
    # Get updated artifact for response
    artifact_service = ArtifactService(db)
    artifact = await artifact_service.get_by_uuid(submission.artifact_uuid)
    
    return SubmissionResponse(
        success=True,
        message=message,
        artifact_uuid=submission.artifact_uuid,
        workflow_status=WorkflowStatusEnum(artifact.workflow_status.value),
        moodle_submission_id=artifact.moodle_submission_id,
        submitted_at=artifact.submit_timestamp
    )


@router.get("/submission/{artifact_uuid}/status")
async def get_submission_status(
    artifact_uuid: str,
    session: StudentSession = Depends(get_session_from_header),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the status of a submission
    """
    artifact_service = ArtifactService(db)
    artifact = await artifact_service.get_by_uuid(artifact_uuid)
    
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paper not found"
        )
    
    # Security check
    if artifact.parsed_reg_no != session.moodle_username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own submissions"
        )
    
    return {
        "artifact_uuid": str(artifact.artifact_uuid),
        "status": artifact.workflow_status.value,
        "moodle_submission_id": artifact.moodle_submission_id,
        "submitted_at": artifact.submit_timestamp.isoformat() if artifact.submit_timestamp else None,
        "error_message": artifact.error_message,
        "retry_count": artifact.retry_count
    }


@router.get("/history")
async def get_submission_history(
    limit: int = Query(default=20, le=100),
    session: StudentSession = Depends(get_session_from_header),
    db: AsyncSession = Depends(get_db)
):
    """
    Get submission history for the student
    """
    artifact_service = ArtifactService(db)
    
    # Get all artifacts for this student
    pending = await artifact_service.get_pending_for_student(
        register_number=session.moodle_username,
        moodle_user_id=session.moodle_user_id
    )
    
    submitted = await artifact_service.get_submitted_for_student(
        register_number=session.moodle_username
    )
    
    history = []
    
    for a in pending + submitted:
        history.append({
            "artifact_uuid": str(a.artifact_uuid),
            "filename": a.original_filename,
            "subject_code": a.parsed_subject_code,
            "status": a.workflow_status.value,
            "uploaded_at": a.uploaded_at.isoformat() if a.uploaded_at else None,
            "submitted_at": a.submit_timestamp.isoformat() if a.submit_timestamp else None
        })
    
    # Sort by upload date, newest first
    history.sort(key=lambda x: x["uploaded_at"] or "", reverse=True)
    
    return {
        "total": len(history),
        "history": history[:limit]
    }
