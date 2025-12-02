"""
SQLAlchemy Database Models for Examination Middleware
Following the schema from the architectural blueprint
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional, Dict, Any

from sqlalchemy import (
    Column, String, Integer, BigInteger, DateTime, Text, 
    Boolean, Enum, ForeignKey, Index, UniqueConstraint, JSON
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class WorkflowStatus(str, PyEnum):
    """Workflow status enum for examination artifacts"""
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
    QUEUED = "QUEUED"  # For Moodle maintenance mode


class ExaminationArtifact(Base):
    """
    Main table for tracking scanned examination papers
    Following the schema from Section 5.1 of the design document
    """
    __tablename__ = "examination_artifacts"
    
    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)
    artifact_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    
    # Original File Information
    raw_filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    
    # Extracted Metadata (parsed from filename or ML extraction)
    parsed_reg_no = Column(String(20), index=True, nullable=True)
    parsed_subject_code = Column(String(20), index=True, nullable=True)
    
    # File Storage
    file_blob_path = Column(String(512), nullable=False)
    file_hash = Column(String(64), nullable=False)  # SHA-256
    file_size_bytes = Column(BigInteger, nullable=True)
    mime_type = Column(String(100), nullable=True)
    
    # Moodle Resolution (populated during validation)
    moodle_user_id = Column(BigInteger, nullable=True)
    moodle_username = Column(String(100), nullable=True)
    moodle_course_id = Column(Integer, nullable=True)
    moodle_assignment_id = Column(Integer, nullable=True)
    
    # Workflow State
    workflow_status = Column(
        Enum(WorkflowStatus),
        default=WorkflowStatus.PENDING,
        nullable=False
    )
    
    # Moodle Submission Tracking
    moodle_draft_item_id = Column(BigInteger, nullable=True)  # For retry logic
    moodle_submission_id = Column(String(100), nullable=True)
    lms_transaction_id = Column(String(100), nullable=True)
    
    # Transaction ID for idempotency
    transaction_id = Column(String(64), unique=True, nullable=True)
    
    # Timestamps
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    validated_at = Column(DateTime(timezone=True), nullable=True)
    submit_timestamp = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Audit
    uploaded_by_staff_id = Column(Integer, ForeignKey("staff_users.id"), nullable=True)
    submitted_by_user_id = Column(BigInteger, nullable=True)  # Moodle user ID
    
    # Transaction/Error Log
    transaction_log = Column(JSONB, nullable=True, default=list)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    
    # Relationships
    audit_logs = relationship("AuditLog", back_populates="artifact")
    
    # Indexes for performance
    __table_args__ = (
        Index('ix_artifacts_reg_subject', 'parsed_reg_no', 'parsed_subject_code'),
        Index('ix_artifacts_status', 'workflow_status'),
        UniqueConstraint('parsed_reg_no', 'parsed_subject_code', name='uq_paper_submission'),
    )
    
    def add_log_entry(self, action: str, details: Dict[str, Any]) -> None:
        """Add an entry to the transaction log"""
        if self.transaction_log is None:
            self.transaction_log = []
        
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "details": details
        }
        self.transaction_log.append(entry)


class SubjectMapping(Base):
    """
    Mapping table for Subject Code to Moodle Course/Assignment IDs
    Implements the catalog service pattern from Section 4.2.2
    """
    __tablename__ = "subject_mappings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Subject Information
    subject_code = Column(String(20), unique=True, nullable=False, index=True)
    subject_name = Column(String(255), nullable=True)
    
    # Moodle Mapping
    moodle_course_id = Column(Integer, nullable=False)
    moodle_course_idnumber = Column(String(50), nullable=True)  # Moodle's idnumber field
    moodle_assignment_id = Column(Integer, nullable=False)
    moodle_assignment_name = Column(String(255), nullable=True)
    
    # Exam Session
    exam_session = Column(String(50), nullable=True)  # e.g., "CIA-II 2025-2026"
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Cache invalidation
    last_verified_at = Column(DateTime(timezone=True), nullable=True)


class StaffUser(Base):
    """
    Staff users who can upload scanned papers
    Implements separation of concerns - staff only uploads, never accesses Moodle
    """
    __tablename__ = "staff_users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    
    # Role and permissions
    role = Column(String(50), default="staff")  # staff, admin, supervisor
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    uploaded_artifacts = relationship("ExaminationArtifact", backref="uploaded_by")


class StudentSession(Base):
    """
    Track student sessions for Moodle token management
    Tokens are encrypted and stored temporarily
    """
    __tablename__ = "student_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    
    # Moodle User Info (from core_webservice_get_site_info)
    moodle_user_id = Column(BigInteger, nullable=False)
    moodle_username = Column(String(100), nullable=False)
    moodle_fullname = Column(String(255), nullable=True)
    
    # Encrypted Token Storage
    encrypted_token = Column(Text, nullable=False)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Session Tracking
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(String(500), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_activity_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    # Index for cleanup
    __table_args__ = (
        Index('ix_session_expires', 'expires_at'),
    )


class AuditLog(Base):
    """
    Comprehensive audit trail for all actions
    Implements the Chain of Custody requirement from Section 7.3
    """
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Action Details
    action = Column(String(100), nullable=False, index=True)
    action_category = Column(String(50), nullable=False)  # upload, view, submit, error
    description = Column(Text, nullable=True)
    
    # Actor Information
    actor_type = Column(String(20), nullable=False)  # staff, student, system
    actor_id = Column(String(100), nullable=True)
    actor_username = Column(String(100), nullable=True)
    actor_ip = Column(String(45), nullable=True)
    
    # Target
    artifact_id = Column(Integer, ForeignKey("examination_artifacts.id"), nullable=True)
    target_type = Column(String(50), nullable=True)
    target_id = Column(String(100), nullable=True)
    
    # Additional Data
    request_data = Column(JSONB, nullable=True)
    response_data = Column(JSONB, nullable=True)
    error_details = Column(JSONB, nullable=True)
    
    # Moodle API Tracking
    moodle_api_function = Column(String(100), nullable=True)
    moodle_response_code = Column(Integer, nullable=True)
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationships
    artifact = relationship("ExaminationArtifact", back_populates="audit_logs")
    
    # Indexes
    __table_args__ = (
        Index('ix_audit_actor', 'actor_type', 'actor_id'),
        Index('ix_audit_artifact_action', 'artifact_id', 'action'),
    )


class SubmissionQueue(Base):
    """
    Queue for handling submissions during Moodle maintenance or failures
    Implements the buffer pattern from Section 6.4
    """
    __tablename__ = "submission_queue"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Reference to artifact
    artifact_id = Column(Integer, ForeignKey("examination_artifacts.id"), nullable=False)
    
    # Queue State
    status = Column(String(20), default="QUEUED")  # QUEUED, PROCESSING, COMPLETED, FAILED
    priority = Column(Integer, default=5)  # 1 = highest
    
    # Retry Logic
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=5)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    queued_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Error tracking
    last_error = Column(Text, nullable=True)
    
    # Index for processing
    __table_args__ = (
        Index('ix_queue_status_retry', 'status', 'next_retry_at'),
    )


class SystemConfig(Base):
    """
    Runtime configuration storage
    """
    __tablename__ = "system_config"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)
    value_type = Column(String(20), default="string")  # string, int, bool, json
    description = Column(Text, nullable=True)
    
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
