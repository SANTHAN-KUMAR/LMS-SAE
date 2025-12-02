"""
Schemas module initialization
"""

from app.schemas.schemas import (
    # Auth
    StaffLoginRequest,
    StaffLoginResponse,
    StudentLoginRequest,
    StudentLoginResponse,
    TokenPayload,
    # File Upload
    FileUploadResponse,
    BulkUploadResponse,
    FileMetadata,
    # Artifacts
    ArtifactBase,
    ArtifactCreate,
    ArtifactResponse,
    ArtifactDetail,
    StudentPendingPaper,
    StudentDashboardResponse,
    # Submission
    SubmissionRequest,
    SubmissionResponse,
    SubmissionStatusResponse,
    # Subject Mapping
    SubjectMappingBase,
    SubjectMappingCreate,
    SubjectMappingResponse,
    # Audit
    AuditLogCreate,
    AuditLogResponse,
    # Moodle
    MoodleTokenResponse,
    MoodleSiteInfo,
    MoodleUploadResponse,
    MoodleAssignment,
    MoodleSubmissionStatus,
    # Errors
    ErrorResponse,
    ValidationErrorResponse,
    ValidationErrorDetail,
    # Health
    HealthCheckResponse,
    SystemStatsResponse,
    # Enums
    WorkflowStatusEnum,
)

__all__ = [
    "StaffLoginRequest",
    "StaffLoginResponse",
    "StudentLoginRequest",
    "StudentLoginResponse",
    "TokenPayload",
    "FileUploadResponse",
    "BulkUploadResponse",
    "FileMetadata",
    "ArtifactBase",
    "ArtifactCreate",
    "ArtifactResponse",
    "ArtifactDetail",
    "StudentPendingPaper",
    "StudentDashboardResponse",
    "SubmissionRequest",
    "SubmissionResponse",
    "SubmissionStatusResponse",
    "SubjectMappingBase",
    "SubjectMappingCreate",
    "SubjectMappingResponse",
    "AuditLogCreate",
    "AuditLogResponse",
    "MoodleTokenResponse",
    "MoodleSiteInfo",
    "MoodleUploadResponse",
    "MoodleAssignment",
    "MoodleSubmissionStatus",
    "ErrorResponse",
    "ValidationErrorResponse",
    "ValidationErrorDetail",
    "HealthCheckResponse",
    "SystemStatsResponse",
    "WorkflowStatusEnum",
]
