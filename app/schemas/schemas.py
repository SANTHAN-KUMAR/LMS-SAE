"""
Pydantic Schemas for API Request/Response Validation
"""

from pydantic import BaseModel, Field, EmailStr, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid
import re


# ============================================
# Enums
# ============================================

class WorkflowStatusEnum(str, Enum):
    PENDING = "PENDING"
    PENDING_REVIEW = "PENDING_REVIEW"
    VALIDATED = "VALIDATED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    LOCKED_BY_USER = "LOCKED_BY_USER"
    UPLOADING = "UPLOADING"
    SUBMITTING = "SUBMITTING"
    SUBMITTED_TO_LMS = "SUBMITTED_TO_LMS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    QUEUED = "QUEUED"


# ============================================
# Authentication Schemas
# ============================================

class StaffLoginRequest(BaseModel):
    """Staff login request"""
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=4)


class StaffLoginResponse(BaseModel):
    """Staff login response"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    staff_id: int
    username: str
    role: str


class StudentLoginRequest(BaseModel):
    """Student login using Moodle credentials"""
    username: str = Field(..., min_length=1, max_length=100, description="Moodle username")
    password: str = Field(..., min_length=1, description="Moodle password")
    register_number: str = Field(..., min_length=12, max_length=12, description="12-digit university register number")


class StudentLoginResponse(BaseModel):
    """Student login response"""
    success: bool
    session_id: str
    moodle_user_id: int
    moodle_username: str
    full_name: Optional[str]
    expires_at: datetime
    pending_submissions: int = 0


class TokenPayload(BaseModel):
    """JWT token payload"""
    sub: str
    exp: datetime
    type: str  # "staff" or "student"
    user_id: int
    username: str


# ============================================
# File Upload Schemas
# ============================================

class FileUploadResponse(BaseModel):
    """Response for file upload"""
    success: bool
    message: str
    artifact_uuid: Optional[str] = None
    parsed_register_number: Optional[str] = None
    parsed_subject_code: Optional[str] = None
    workflow_status: Optional[str] = None
    errors: Optional[List[str]] = None


class BulkUploadResponse(BaseModel):
    """Response for bulk file upload"""
    total_files: int
    successful: int
    failed: int
    results: List[FileUploadResponse]


class FileMetadata(BaseModel):
    """Extracted file metadata"""
    register_number: str
    subject_code: str
    
    @validator('register_number')
    def validate_register_number(cls, v):
        # Pattern for 12-digit register number
        if not re.match(r'^[0-9]{12}$', v):
            raise ValueError('Register number must be exactly 12 digits')
        return v
    
    @validator('subject_code')
    def validate_subject_code(cls, v):
        # Pattern for alphanumeric subject code
        if not re.match(r'^[A-Z0-9]{2,10}$', v.upper()):
            raise ValueError('Invalid subject code format')
        return v.upper()


# ============================================
# Examination Artifact Schemas
# ============================================

class ArtifactBase(BaseModel):
    """Base artifact schema"""
    raw_filename: str
    parsed_reg_no: Optional[str] = None
    parsed_subject_code: Optional[str] = None


class ArtifactCreate(ArtifactBase):
    """Schema for creating artifact"""
    file_blob_path: str
    file_hash: str
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None


class ArtifactResponse(BaseModel):
    """Artifact response for API"""
    id: int
    artifact_uuid: str
    raw_filename: str
    original_filename: str
    parsed_reg_no: Optional[str]
    parsed_subject_code: Optional[str]
    workflow_status: WorkflowStatusEnum
    moodle_assignment_id: Optional[int]
    uploaded_at: datetime
    submit_timestamp: Optional[datetime]
    
    class Config:
        from_attributes = True


class ArtifactDetail(ArtifactResponse):
    """Detailed artifact information"""
    file_size_bytes: Optional[int]
    mime_type: Optional[str]
    moodle_user_id: Optional[int]
    moodle_username: Optional[str]
    moodle_course_id: Optional[int]
    error_message: Optional[str]
    retry_count: int
    transaction_log: Optional[List[Dict[str, Any]]]
    
    class Config:
        from_attributes = True


class StudentPendingPaper(BaseModel):
    """Paper pending student review"""
    artifact_uuid: str
    subject_code: str
    subject_name: Optional[str]
    assignment_name: Optional[str]
    filename: str
    uploaded_at: datetime
    can_submit: bool
    message: Optional[str] = None


class StudentDashboardResponse(BaseModel):
    """Student dashboard data"""
    moodle_user_id: int
    moodle_username: str
    full_name: Optional[str]
    pending_papers: List[StudentPendingPaper]
    submitted_papers: List[ArtifactResponse]
    total_pending: int
    total_submitted: int


# ============================================
# Submission Schemas
# ============================================

class SubmissionRequest(BaseModel):
    """Request to submit a paper to Moodle"""
    artifact_uuid: str = Field(..., description="UUID of the artifact to submit")
    confirm_submission: bool = Field(True, description="Student confirms the paper is theirs")


class SubmissionResponse(BaseModel):
    """Response after submission attempt"""
    success: bool
    message: str
    artifact_uuid: str
    workflow_status: WorkflowStatusEnum
    moodle_submission_id: Optional[str] = None
    submitted_at: Optional[datetime] = None
    errors: Optional[List[str]] = None


class SubmissionStatusResponse(BaseModel):
    """Status of a submission"""
    artifact_uuid: str
    workflow_status: WorkflowStatusEnum
    moodle_submission_status: Optional[str]
    submitted_at: Optional[datetime]
    last_updated: datetime


# ============================================
# Subject Mapping Schemas
# ============================================

class SubjectMappingBase(BaseModel):
    """Base subject mapping schema"""
    subject_code: str
    subject_name: Optional[str] = None
    moodle_course_id: int
    moodle_assignment_id: int
    moodle_assignment_name: Optional[str] = None
    exam_session: Optional[str] = None


class SubjectMappingCreate(SubjectMappingBase):
    """Create subject mapping"""
    moodle_course_idnumber: Optional[str] = None


class SubjectMappingResponse(SubjectMappingBase):
    """Subject mapping response"""
    id: int
    is_active: bool
    created_at: datetime
    last_verified_at: Optional[datetime]
    
    class Config:
        from_attributes = True


# ============================================
# Audit Log Schemas
# ============================================

class AuditLogCreate(BaseModel):
    """Create audit log entry"""
    action: str
    action_category: str
    description: Optional[str] = None
    actor_type: str
    actor_id: Optional[str] = None
    actor_username: Optional[str] = None
    actor_ip: Optional[str] = None
    artifact_id: Optional[int] = None
    request_data: Optional[Dict[str, Any]] = None
    response_data: Optional[Dict[str, Any]] = None


class AuditLogResponse(BaseModel):
    """Audit log response"""
    id: int
    action: str
    action_category: str
    description: Optional[str]
    actor_type: str
    actor_username: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


# ============================================
# Moodle API Schemas
# ============================================

class MoodleTokenResponse(BaseModel):
    """Response from Moodle token endpoint"""
    token: str
    privatetoken: Optional[str] = None


class MoodleSiteInfo(BaseModel):
    """Response from core_webservice_get_site_info"""
    userid: int
    username: str
    fullname: str
    sitename: Optional[str] = None
    userpictureurl: Optional[str] = None


class MoodleUploadResponse(BaseModel):
    """Response from Moodle file upload"""
    itemid: int
    filename: str
    fileurl: Optional[str] = None


class MoodleAssignment(BaseModel):
    """Moodle assignment info"""
    id: int
    cmid: int
    name: str
    course: int
    duedate: Optional[int] = None
    allowsubmissionsfromdate: Optional[int] = None


class MoodleSubmissionStatus(BaseModel):
    """Moodle submission status"""
    assignment_id: int
    submission_id: Optional[int]
    status: str
    timemodified: Optional[int]


# ============================================
# Error Schemas
# ============================================

class ErrorResponse(BaseModel):
    """Standard error response"""
    success: bool = False
    error_code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ValidationErrorDetail(BaseModel):
    """Validation error detail"""
    field: str
    message: str
    value: Optional[Any] = None


class ValidationErrorResponse(BaseModel):
    """Validation error response"""
    success: bool = False
    error_code: str = "VALIDATION_ERROR"
    message: str = "Validation failed"
    errors: List[ValidationErrorDetail]


# ============================================
# Health Check Schemas
# ============================================

class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    database: str
    moodle_connection: str
    timestamp: datetime


class SystemStatsResponse(BaseModel):
    """System statistics"""
    total_artifacts: int
    pending_review: int
    submitted: int
    failed: int
    queued: int
    active_sessions: int
