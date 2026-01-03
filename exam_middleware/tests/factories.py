"""
Test Data Factories

Factory classes for creating test data with sensible defaults.
Uses a builder pattern for flexible test data creation.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from app.db.models import (
    ExaminationArtifact,
    SubjectMapping,
    StaffUser,
    StudentSession,
    AuditLog,
    WorkflowStatus,
    SubmissionQueue
)
from app.core.security import get_password_hash


class ArtifactFactory:
    """Factory for creating ExaminationArtifact test instances."""
    
    _counter = 0
    
    @classmethod
    def create(
        cls,
        register_number: Optional[str] = None,
        subject_code: str = "19AI405",
        status: WorkflowStatus = WorkflowStatus.PENDING_REVIEW,
        moodle_user_id: Optional[int] = None,
        moodle_assignment_id: Optional[int] = None,
        file_size: int = 1024,
        **kwargs
    ) -> ExaminationArtifact:
        """
        Create an artifact with sensible defaults.
        
        Args:
            register_number: Student register number (auto-generated if None)
            subject_code: Subject code for the paper
            status: Workflow status
            moodle_user_id: Moodle user ID if resolved
            moodle_assignment_id: Moodle assignment ID if resolved
            file_size: File size in bytes
            **kwargs: Additional fields to override
            
        Returns:
            ExaminationArtifact instance (not saved to DB)
        """
        cls._counter += 1
        
        if register_number is None:
            register_number = f"12345678{cls._counter:04d}"
        
        filename = f"{register_number}_{subject_code}.pdf"
        
        defaults = {
            "raw_filename": filename,
            "original_filename": filename,
            "sanitized_filename": filename,
            "parsed_reg_no": register_number,
            "parsed_subject_code": subject_code.upper(),
            "file_extension": ".pdf",
            "file_mime_type": "application/pdf",
            "file_size_bytes": file_size,
            "file_hash": f"sha256_{uuid.uuid4().hex[:32]}",
            "file_blob_path": f"/uploads/test/{filename}",
            "workflow_status": status,
            "moodle_user_id": moodle_user_id,
            "moodle_assignment_id": moodle_assignment_id,
            "transaction_log": [],
        }
        
        defaults.update(kwargs)
        return ExaminationArtifact(**defaults)
    
    @classmethod
    def create_pending(cls, **kwargs) -> ExaminationArtifact:
        """Create a pending artifact."""
        return cls.create(status=WorkflowStatus.PENDING_REVIEW, **kwargs)
    
    @classmethod
    def create_submitted(cls, **kwargs) -> ExaminationArtifact:
        """Create a submitted artifact."""
        return cls.create(
            status=WorkflowStatus.SUBMITTED_TO_LMS,
            moodle_user_id=kwargs.pop("moodle_user_id", 42),
            moodle_assignment_id=kwargs.pop("moodle_assignment_id", 1),
            submit_timestamp=datetime.utcnow() - timedelta(hours=1),
            **kwargs
        )
    
    @classmethod
    def create_failed(cls, error_message: str = "Test error", **kwargs) -> ExaminationArtifact:
        """Create a failed artifact."""
        return cls.create(
            status=WorkflowStatus.FAILED,
            error_message=error_message,
            **kwargs
        )
    
    @classmethod
    def create_batch(
        cls,
        count: int,
        status: WorkflowStatus = WorkflowStatus.PENDING_REVIEW,
        **kwargs
    ) -> List[ExaminationArtifact]:
        """Create multiple artifacts."""
        return [cls.create(status=status, **kwargs) for _ in range(count)]


class StaffUserFactory:
    """Factory for creating StaffUser test instances."""
    
    _counter = 0
    
    @classmethod
    def create(
        cls,
        username: Optional[str] = None,
        password: str = "testpass123",
        role: str = "staff",
        is_active: bool = True,
        **kwargs
    ) -> StaffUser:
        """
        Create a staff user with sensible defaults.
        
        Args:
            username: Username (auto-generated if None)
            password: Plain text password (will be hashed)
            role: User role (staff/admin)
            is_active: Whether user is active
            **kwargs: Additional fields
            
        Returns:
            StaffUser instance (not saved to DB)
        """
        cls._counter += 1
        
        if username is None:
            username = f"testuser_{cls._counter}"
        
        defaults = {
            "username": username,
            "hashed_password": get_password_hash(password),
            "email": f"{username}@test.com",
            "role": role,
            "is_active": is_active,
        }
        
        defaults.update(kwargs)
        return StaffUser(**defaults)
    
    @classmethod
    def create_admin(cls, **kwargs) -> StaffUser:
        """Create an admin user."""
        return cls.create(role="admin", **kwargs)


class SubjectMappingFactory:
    """Factory for creating SubjectMapping test instances."""
    
    _counter = 0
    
    @classmethod
    def create(
        cls,
        subject_code: Optional[str] = None,
        course_id: int = 3,
        assignment_id: int = 1,
        is_active: bool = True,
        **kwargs
    ) -> SubjectMapping:
        """
        Create a subject mapping with sensible defaults.
        
        Args:
            subject_code: Subject code (auto-generated if None)
            course_id: Moodle course ID
            assignment_id: Moodle assignment ID
            is_active: Whether mapping is active
            **kwargs: Additional fields
            
        Returns:
            SubjectMapping instance (not saved to DB)
        """
        cls._counter += 1
        
        if subject_code is None:
            subject_code = f"19AI{400 + cls._counter}"
        
        defaults = {
            "subject_code": subject_code.upper(),
            "subject_name": f"Test Subject {cls._counter}",
            "moodle_course_id": course_id,
            "moodle_assignment_id": assignment_id,
            "moodle_assignment_name": f"Assignment {cls._counter}",
            "exam_session": "2024-DEC",
            "is_active": is_active,
        }
        
        defaults.update(kwargs)
        return SubjectMapping(**defaults)


class StudentSessionFactory:
    """Factory for creating StudentSession test instances."""
    
    @classmethod
    def create(
        cls,
        moodle_user_id: int = 42,
        moodle_username: str = "student1",
        register_number: str = "123456789012",
        token: str = "encrypted-token",
        expires_in_hours: int = 8,
        **kwargs
    ) -> StudentSession:
        """
        Create a student session with sensible defaults.
        
        Args:
            moodle_user_id: Moodle user ID
            moodle_username: Moodle username
            register_number: Student register number
            token: Encrypted Moodle token
            expires_in_hours: Session duration
            **kwargs: Additional fields
            
        Returns:
            StudentSession instance (not saved to DB)
        """
        defaults = {
            "session_id": str(uuid.uuid4()),
            "moodle_user_id": moodle_user_id,
            "moodle_username": moodle_username,
            "moodle_fullname": "Test Student",
            "register_number": register_number,
            "encrypted_moodle_token": token,
            "expires_at": datetime.utcnow() + timedelta(hours=expires_in_hours),
        }
        
        defaults.update(kwargs)
        return StudentSession(**defaults)


class AuditLogFactory:
    """Factory for creating AuditLog test instances."""
    
    @classmethod
    def create(
        cls,
        action: str = "test_action",
        action_category: str = "test",
        artifact_id: Optional[int] = None,
        actor_type: str = "system",
        **kwargs
    ) -> AuditLog:
        """
        Create an audit log entry with sensible defaults.
        
        Args:
            action: Action name
            action_category: Action category
            artifact_id: Related artifact ID
            actor_type: Type of actor
            **kwargs: Additional fields
            
        Returns:
            AuditLog instance (not saved to DB)
        """
        defaults = {
            "action": action,
            "action_category": action_category,
            "artifact_id": artifact_id,
            "actor_type": actor_type,
            "actor_username": kwargs.pop("actor_username", "system"),
            "description": f"Test {action} action",
            "details": {},
        }
        
        defaults.update(kwargs)
        return AuditLog(**defaults)


# ============================================
# Mock Response Factories
# ============================================

class MoodleResponseFactory:
    """Factory for creating Moodle API mock responses."""
    
    @staticmethod
    def token_response(token: str = "test-token-12345") -> dict:
        """Create a token response."""
        return {"token": token}
    
    @staticmethod
    def site_info(
        user_id: int = 42,
        fullname: str = "Test Student",
        username: str = "student1"
    ) -> dict:
        """Create a site info response."""
        return {
            "userid": user_id,
            "username": username,
            "fullname": fullname,
            "sitename": "Test Moodle",
            "userpictureurl": ""
        }
    
    @staticmethod
    def courses(courses: Optional[List[dict]] = None) -> List[dict]:
        """Create a courses response."""
        if courses is None:
            courses = [
                {"id": 3, "shortname": "19AI405", "fullname": "Machine Learning"},
                {"id": 4, "shortname": "19AI411", "fullname": "Deep Learning"}
            ]
        return courses
    
    @staticmethod
    def assignments(course_id: int = 3, assignment_id: int = 1) -> dict:
        """Create an assignments response."""
        return {
            "courses": [
                {
                    "id": course_id,
                    "shortname": "19AI405",
                    "assignments": [
                        {
                            "id": assignment_id,
                            "name": "Test Assignment",
                            "cmid": 4,
                            "duedate": int((datetime.utcnow() + timedelta(days=7)).timestamp())
                        }
                    ]
                }
            ]
        }
    
    @staticmethod
    def upload_response(item_id: int = 12345, filename: str = "test.pdf") -> dict:
        """Create a file upload response."""
        return {
            "itemid": item_id,
            "filename": filename,
            "filepath": "/",
            "filesize": 1024
        }
    
    @staticmethod
    def submission_status(status: str = "submitted") -> dict:
        """Create a submission status response."""
        return {
            "lastattempt": {
                "submission": {
                    "status": status,
                    "timemodified": int(datetime.utcnow().timestamp())
                }
            }
        }
    
    @staticmethod
    def error_response(error_code: str = "invalidtoken", message: str = "Invalid token") -> dict:
        """Create an error response."""
        return {
            "error": message,
            "errorcode": error_code
        }
