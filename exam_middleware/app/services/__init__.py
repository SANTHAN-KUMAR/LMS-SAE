"""
Services module initialization
"""

from app.services.moodle_client import MoodleClient, MoodleAPIError, moodle_client
from app.services.file_processor import FileProcessor, file_processor
from app.services.artifact_service import (
    ArtifactService,
    SubjectMappingService,
    AuditService,
)
from app.services.submission_service import SubmissionService

__all__ = [
    "MoodleClient",
    "MoodleAPIError",
    "moodle_client",
    "FileProcessor",
    "file_processor",
    "ArtifactService",
    "SubjectMappingService",
    "AuditService",
    "SubmissionService",
]
