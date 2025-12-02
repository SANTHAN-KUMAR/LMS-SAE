"""
Upload API Routes
Handles file uploads from staff
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import logging

from app.db.database import get_db
from app.db.models import StaffUser
from app.schemas import (
    FileUploadResponse,
    BulkUploadResponse,
    ErrorResponse,
)
from app.services.file_processor import file_processor
from app.services.artifact_service import ArtifactService, AuditService
from app.api.routes.auth import get_current_staff

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/single", response_model=FileUploadResponse)
async def upload_single_file(
    file: UploadFile = File(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff)
):
    """
    Upload a single examination paper
    
    The filename should follow the pattern: REGISTER_SUBJECT.pdf
    Example: 212223240065_19AI405.pdf
    
    Staff members upload scanned papers here. The system will:
    1. Validate the file format
    2. Parse the filename for register number and subject code
    3. Store the file and create a database record
    4. The paper will appear in the student's dashboard
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required"
        )
    
    # Read file content
    content = await file.read()
    
    # Validate file
    is_valid, message, metadata = file_processor.validate_file(content, file.filename)
    
    if not is_valid:
        logger.warning(f"File validation failed: {message}")
        return FileUploadResponse(
            success=False,
            message=message,
            errors=[message]
        )
    
    # Save file
    try:
        file_path, file_hash = await file_processor.save_file(
            file_content=content,
            original_filename=file.filename,
            subfolder="pending"
        )
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        return FileUploadResponse(
            success=False,
            message="Failed to save file",
            errors=[str(e)]
        )
    
    # Create artifact record
    artifact_service = ArtifactService(db)
    audit_service = AuditService(db)
    
    try:
        artifact = await artifact_service.create_artifact(
            raw_filename=file.filename,
            original_filename=metadata.get("original_filename", file.filename),
            file_blob_path=file_path,
            file_hash=file_hash,
            parsed_reg_no=metadata.get("parsed_register_no"),
            parsed_subject_code=metadata.get("parsed_subject_code"),
            file_size_bytes=metadata.get("size_bytes"),
            mime_type=metadata.get("mime_type"),
            uploaded_by_staff_id=current_staff.id
        )
        
        # Log the upload
        await audit_service.log_action(
            action="file_uploaded",
            action_category="upload",
            actor_type="staff",
            actor_id=str(current_staff.id),
            actor_username=current_staff.username,
            actor_ip=request.client.host if request and request.client else None,
            artifact_id=artifact.id,
            description=f"Uploaded file: {file.filename}",
            request_data={"filename": file.filename, "size": metadata.get("size_bytes")}
        )
        
        await db.commit()
        
        return FileUploadResponse(
            success=True,
            message="File uploaded successfully",
            artifact_uuid=str(artifact.artifact_uuid),
            parsed_register_number=artifact.parsed_reg_no,
            parsed_subject_code=artifact.parsed_subject_code,
            workflow_status=artifact.workflow_status.value
        )
        
    except Exception as e:
        logger.error(f"Failed to create artifact: {e}")
        await db.rollback()
        
        # Clean up the saved file
        await file_processor.delete_file(file_path)
        
        return FileUploadResponse(
            success=False,
            message="Failed to process file",
            errors=[str(e)]
        )


@router.post("/bulk", response_model=BulkUploadResponse)
async def upload_bulk_files(
    files: List[UploadFile] = File(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff)
):
    """
    Upload multiple examination papers at once
    
    Each file should follow the pattern: REGISTER_SUBJECT.pdf
    """
    results = []
    successful = 0
    failed = 0
    
    for file in files:
        if not file.filename:
            results.append(FileUploadResponse(
                success=False,
                message="Filename is required",
                errors=["Missing filename"]
            ))
            failed += 1
            continue
        
        # Read file content
        content = await file.read()
        
        # Validate file
        is_valid, message, metadata = file_processor.validate_file(content, file.filename)
        
        if not is_valid:
            results.append(FileUploadResponse(
                success=False,
                message=message,
                errors=[message]
            ))
            failed += 1
            continue
        
        # Save file
        try:
            file_path, file_hash = await file_processor.save_file(
                file_content=content,
                original_filename=file.filename,
                subfolder="pending"
            )
            
            # Create artifact
            artifact_service = ArtifactService(db)
            artifact = await artifact_service.create_artifact(
                raw_filename=file.filename,
                original_filename=metadata.get("original_filename", file.filename),
                file_blob_path=file_path,
                file_hash=file_hash,
                parsed_reg_no=metadata.get("parsed_register_no"),
                parsed_subject_code=metadata.get("parsed_subject_code"),
                file_size_bytes=metadata.get("size_bytes"),
                mime_type=metadata.get("mime_type"),
                uploaded_by_staff_id=current_staff.id
            )
            
            results.append(FileUploadResponse(
                success=True,
                message="File uploaded successfully",
                artifact_uuid=str(artifact.artifact_uuid),
                parsed_register_number=artifact.parsed_reg_no,
                parsed_subject_code=artifact.parsed_subject_code,
                workflow_status=artifact.workflow_status.value
            ))
            successful += 1
            
        except Exception as e:
            logger.error(f"Failed to process file {file.filename}: {e}")
            results.append(FileUploadResponse(
                success=False,
                message=f"Failed to process: {str(e)}",
                errors=[str(e)]
            ))
            failed += 1
    
    # Log bulk upload
    audit_service = AuditService(db)
    await audit_service.log_action(
        action="bulk_upload",
        action_category="upload",
        actor_type="staff",
        actor_id=str(current_staff.id),
        actor_username=current_staff.username,
        actor_ip=request.client.host if request and request.client else None,
        description=f"Bulk upload: {successful} successful, {failed} failed",
        request_data={"total": len(files), "successful": successful, "failed": failed}
    )
    
    await db.commit()
    
    return BulkUploadResponse(
        total_files=len(files),
        successful=successful,
        failed=failed,
        results=results
    )


@router.get("/pending")
async def get_pending_uploads(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff)
):
    """
    Get list of pending uploads (staff view)
    """
    artifact_service = ArtifactService(db)
    artifacts, total = await artifact_service.get_all_pending(limit=limit, offset=offset)
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "artifacts": [
            {
                "artifact_uuid": str(a.artifact_uuid),
                "filename": a.original_filename,
                "register_number": a.parsed_reg_no,
                "subject_code": a.parsed_subject_code,
                "status": a.workflow_status.value,
                "uploaded_at": a.uploaded_at.isoformat() if a.uploaded_at else None
            }
            for a in artifacts
        ]
    }


@router.get("/stats")
async def get_upload_stats(
    db: AsyncSession = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff)
):
    """
    Get upload statistics
    """
    artifact_service = ArtifactService(db)
    stats = await artifact_service.get_stats()
    
    return {
        "stats": stats,
        "total": sum(stats.values())
    }
