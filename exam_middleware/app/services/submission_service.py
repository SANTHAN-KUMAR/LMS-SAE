"""
Submission Service
Orchestrates the complete submission workflow to Moodle
"""

import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ExaminationArtifact, WorkflowStatus
from app.services.moodle_client import MoodleClient, MoodleAPIError
from app.services.artifact_service import ArtifactService, SubjectMappingService, AuditService
from app.core.security import token_encryption
from app.core.config import settings

logger = logging.getLogger(__name__)


class SubmissionService:
    """
    Orchestrates the 3-step submission process to Moodle
    
    Implements the workflow from Section 4.3 of the design document:
    1. Upload to Draft Area (core_files_upload)
    2. Associate Draft with Assignment (mod_assign_save_submission)
    3. Lock the Submission (mod_assign_submit_for_grading)
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.artifact_service = ArtifactService(db)
        self.mapping_service = SubjectMappingService(db)
        self.audit_service = AuditService(db)
    
    async def submit_artifact(
        self,
        artifact_uuid: str,
        moodle_token: str,
        moodle_user_id: int,
        moodle_username: str,
        register_number: str,
        actor_ip: Optional[str] = None,
        lock_submission: bool = True
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Submit an artifact to Moodle
        
        This is the main entry point for the submission workflow.
        
        Args:
            artifact_uuid: UUID of the artifact to submit
            moodle_token: Student's Moodle web service token
            moodle_user_id: Student's Moodle user ID
            moodle_username: Student's Moodle username
            register_number: Student's register number (extracted from fullname)
            actor_ip: IP address of the student
            lock_submission: Whether to finalize/lock the submission
            
        Returns:
            Tuple of (success, message, result_data)
        """
        # Get artifact
        artifact = await self.artifact_service.get_by_uuid(artifact_uuid)
        if not artifact:
            return False, "Artifact not found", None
        
        # Security check: Verify the artifact belongs to this user (compare register numbers)
        if artifact.parsed_reg_no != register_number:
            logger.warning(
                f"Security violation: User {moodle_username} attempted to submit "
                f"artifact belonging to {artifact.parsed_reg_no}"
            )
            await self.audit_service.log_action(
                action="unauthorized_submission_attempt",
                action_category="security",
                actor_type="student",
                actor_id=str(moodle_user_id),
                actor_username=moodle_username,
                actor_ip=actor_ip,
                artifact_id=artifact.id,
                description=f"User attempted to submit artifact belonging to {artifact.parsed_reg_no}"
            )
            return False, "You can only submit your own papers", None
        
        # Check if already submitted
        if artifact.workflow_status in [WorkflowStatus.COMPLETED, WorkflowStatus.SUBMITTED_TO_LMS]:
            return False, "This paper has already been submitted", {
                "already_submitted": True,
                "submitted_at": artifact.submit_timestamp.isoformat() if artifact.submit_timestamp else None
            }
        
        # Get assignment ID
        assignment_id = await self._resolve_assignment_id(artifact)
        if not assignment_id:
            return False, f"No assignment mapping found for subject code: {artifact.parsed_subject_code}", None
        
        # Update artifact with Moodle info
        artifact.moodle_user_id = moodle_user_id
        artifact.moodle_username = moodle_username
        artifact.moodle_assignment_id = assignment_id
        
        # Log submission start
        await self.audit_service.log_action(
            action="submission_started",
            action_category="submit",
            actor_type="student",
            actor_id=str(moodle_user_id),
            actor_username=moodle_username,
            actor_ip=actor_ip,
            artifact_id=artifact.id,
            description=f"Starting submission for assignment {assignment_id}"
        )
        
        # Execute the 3-step submission process
        try:
            result = await self._execute_submission(
                artifact=artifact,
                assignment_id=assignment_id,
                moodle_token=moodle_token,
                lock_submission=lock_submission
            )
            
            # Log the complete result for debugging
            logger.info(f"Submission result: {result}")
            logger.info(f"Steps completed: {result.get('steps_completed', [])}")
            
            # Mark as completed (only after all verification and submit steps)
            await self.artifact_service.mark_submitted(
                artifact_id=artifact.id,
                moodle_submission_id=result.get("submission_id"),
                lms_transaction_id=result.get("transaction_id")
            )
            
            # Log success
            await self.audit_service.log_action(
                action="submission_completed",
                action_category="submit",
                actor_type="student",
                actor_id=str(moodle_user_id),
                actor_username=moodle_username,
                actor_ip=actor_ip,
                artifact_id=artifact.id,
                response_data=result,
                description="Submission completed successfully"
            )
            
            return True, "Submission completed successfully", result
            
        except MoodleAPIError as e:
            logger.error(f"Moodle API error during submission: {e}")
            
            # Check if this is a transient error that should be queued
            should_queue = self._should_queue_for_retry(e)
            
            await self.artifact_service.mark_failed(
                artifact_id=artifact.id,
                error_message=str(e),
                queue_for_retry=should_queue
            )
            
            await self.audit_service.log_action(
                action="submission_failed",
                action_category="error",
                actor_type="student",
                actor_id=str(moodle_user_id),
                actor_username=moodle_username,
                actor_ip=actor_ip,
                artifact_id=artifact.id,
                description=str(e),
                response_data={
                    "error": str(e),
                    "queued_for_retry": should_queue
                }
            )
            
            if should_queue:
                return False, "Submission queued - Moodle is temporarily unavailable", {
                    "queued": True,
                    "error": str(e)
                }
            
            return False, f"Submission failed: {e.message}", {"error": str(e)}
            
        except Exception as e:
            logger.error(f"Unexpected error during submission: {e}")
            
            await self.artifact_service.mark_failed(
                artifact_id=artifact.id,
                error_message=str(e),
                queue_for_retry=False
            )
            
            return False, f"Unexpected error: {str(e)}", None
    
    async def _resolve_assignment_id(self, artifact: ExaminationArtifact) -> Optional[int]:
        """Resolve the Moodle assignment ID for an artifact"""
        if artifact.moodle_assignment_id:
            return artifact.moodle_assignment_id
        
        if not artifact.parsed_subject_code:
            return None
        
        return await self.mapping_service.get_assignment_id(artifact.parsed_subject_code)
    
    async def _execute_submission(
        self,
        artifact: ExaminationArtifact,
        assignment_id: int,
        moodle_token: str,
        lock_submission: bool
    ) -> Dict[str, Any]:
        """
        Execute the 3-step submission process
        
        Step 1: Upload file to draft area
        Step 2: Link draft to assignment
        Step 3: Finalize submission (optional)
        """
        client = MoodleClient(token=moodle_token)
        result = {
            "assignment_id": assignment_id,
            "steps_completed": []
        }
        
        try:
            # Check if we have a previous draft that failed
            if artifact.moodle_draft_item_id and artifact.workflow_status == WorkflowStatus.UPLOADING:
                logger.info(f"Reusing existing draft item: {artifact.moodle_draft_item_id}")
                item_id = artifact.moodle_draft_item_id
                result["steps_completed"].append("upload_skipped_reuse")
            else:
                # Step 1: Upload to draft area
                logger.info(f"Step 1/3: Uploading file to draft area")
                artifact.workflow_status = WorkflowStatus.UPLOADING
                await self.db.flush()
                
                upload_result = await client.upload_file(
                    file_path=artifact.file_blob_path,
                    token=moodle_token,
                    filename=artifact.original_filename
                )
                
                item_id = upload_result["itemid"]
                artifact.moodle_draft_item_id = item_id
                await self.db.flush()
                
                result["item_id"] = item_id
                result["steps_completed"].append("upload")
            
            # Step 2: Verify assignment exists and is accessible BEFORE saving
            logger.info(f"Verifying assignment {assignment_id} exists and is accessible...")
            try:
                # Try to get submission status - this will fail if assignment doesn't exist
                verify_status = await client.get_submission_status(
                    assignment_id=assignment_id,
                    token=moodle_token
                )
                logger.info(f"Assignment {assignment_id} verified and accessible")
            except MoodleAPIError as verify_error:
                logger.error(
                    f"Assignment {assignment_id} verification failed: {verify_error.message}. "
                    f"This usually means the assignment ID is incorrect or the student doesn't have access."
                )
                raise MoodleAPIError(
                    f"Assignment {assignment_id} not found or not accessible: {verify_error.message}. "
                    f"Please verify the assignment ID in your subject mapping matches the Moodle assignment instance ID (not the course module ID).",
                    response_data={"assignment_id": assignment_id, "error": str(verify_error)}
                )
            
            # Step 2: Save submission
            logger.info(f"Step 2/3: Linking draft to assignment")
            artifact.workflow_status = WorkflowStatus.SUBMITTING
            await self.db.flush()
            
            save_result = await client.save_submission(
                assignment_id=assignment_id,
                item_id=item_id,
                token=moodle_token
            )
            
            result["save_result"] = save_result
            result["steps_completed"].append("save")
            
            # Verify the submission was actually saved by checking status
            logger.info(f"Verifying submission status after save...")
            status_result = await client.get_submission_status(
                assignment_id=assignment_id,
                token=moodle_token
            )
            
            # Log the full status for debugging
            logger.info(f"Full submission status response: {status_result}")
            
            # Check submission status details
            submission_status = "unknown"
            submission_files = []
            submission_id = None
            cansubmit = False
            if "lastattempt" in status_result:
                lastattempt = status_result["lastattempt"]
                submission = lastattempt.get("submission", {})
                submission_status = submission.get("status", "unknown")
                submission_id = submission.get("id")
                logger.info(f"Submission status: {submission_status}")
                logger.info(f"Submission ID: {submission_id}")
                logger.info(f"Submission timecreated: {submission.get('timecreated')}")
                logger.info(f"Submission timemodified: {submission.get('timemodified')}")
                
                # Check gradingstatus
                grading_status = lastattempt.get("gradingstatus", "unknown")
                logger.info(f"Grading status: {grading_status}")
                
                # Check submissionsenabled
                submissionsenabled = lastattempt.get("submissionsenabled", False)
                logger.info(f"Submissions enabled: {submissionsenabled}")
                
                # Check canedit
                canedit = lastattempt.get("canedit", False)
                logger.info(f"Can edit: {canedit}")
                
                # Check cansubmit (whether Moodle expects an explicit submit-for-grading action)
                cansubmit = lastattempt.get("cansubmit", False)
                logger.info(f"Can submit: {cansubmit}")
                
                plugins = submission.get("plugins", [])
                for plugin in plugins:
                    if plugin.get("type") == "file":
                        fileareas = plugin.get("fileareas", [])
                        for area in fileareas:
                            if area.get("area") == "submission_files":
                                submission_files = area.get("files", [])
                                break
            
            result["submission_status"] = submission_status
            if submission_id is not None:
                # Expose Moodle's internal submission id so we can persist it
                # Convert to string since database column is VARCHAR
                result["submission_id"] = str(submission_id)
            
            logger.info(f"Submission verification - Files found: {len(submission_files)}")
            if submission_files:
                logger.info(f"Verified files: {[f.get('filename') for f in submission_files]}")
                result["verified_files"] = [f.get("filename") for f in submission_files]
            else:
                # Treat this as a hard failure instead of silently continuing –
                # if Moodle doesn't report any files in the submission, the
                # teacher UI will also show “No submission”, so we should not
                # mark the artifact as successfully submitted.
                logger.error(
                    "No files found in submission after save. "
                    "Aborting submission and returning error to caller."
                )
                raise MoodleAPIError(
                    "Moodle did not attach any files to the submission. "
                    "Please retry or contact the administrator.",
                    response_data=status_result
                )
            
            # Step 3: Submit for grading (lock), but ONLY if Moodle reports that
            # this user can actually perform an explicit submit action.
            #
            # For many assignment configurations (submission drafts off), Moodle
            # treats file upload as the final submission and returns
            #   - submission.status = 'submitted'
            #   - cansubmit = False
            # In those cases calling mod_assign_submit_for_grading will return
            # 'couldnotsubmitforgrading', which we now treat as an error. To
            # avoid false failures, we simply skip the explicit submit call.
            if lock_submission and cansubmit:
                logger.info(f"Step 3/3: Finalizing submission")
                submit_result = await client.submit_for_grading(
                    assignment_id=assignment_id,
                    token=moodle_token
                )
                
                result["submit_result"] = submit_result
                result["steps_completed"].append("finalize")
            elif lock_submission and not cansubmit:
                logger.info(
                    "Skipping explicit submit_for_grading call because Moodle "
                    "reports cansubmit=False. Treating current 'submitted' "
                    "state as final."
                )
                result["submit_skipped"] = True
            
            result["success"] = True
            result["transaction_id"] = f"TXN_{artifact.artifact_uuid}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            
            return result
            
        finally:
            await client.close()
    
    def _should_queue_for_retry(self, error: MoodleAPIError) -> bool:
        """Determine if an error should trigger a retry queue"""
        # Queue for transient errors (Moodle maintenance, timeouts, etc.)
        if error.error:
            transient_errors = [
                "moodleoff",
                "maintenance",
                "timeout",
                "connection",
                "unavailable"
            ]
            return any(
                te in error.error.errorcode.lower() or te in error.error.message.lower()
                for te in transient_errors
            )
        
        return "timeout" in str(error).lower() or "connection" in str(error).lower()
    
    async def get_submission_status(
        self,
        artifact_uuid: str,
        moodle_token: str
    ) -> Dict[str, Any]:
        """Get the current submission status from Moodle"""
        artifact = await self.artifact_service.get_by_uuid(artifact_uuid)
        if not artifact:
            return {"error": "Artifact not found"}
        
        if not artifact.moodle_assignment_id:
            return {
                "artifact_status": artifact.workflow_status.value,
                "moodle_status": None
            }
        
        client = MoodleClient(token=moodle_token)
        try:
            status = await client.get_submission_status(
                assignment_id=artifact.moodle_assignment_id,
                token=moodle_token
            )
            
            return {
                "artifact_status": artifact.workflow_status.value,
                "moodle_status": status
            }
        finally:
            await client.close()
    
    async def retry_queued_submissions(self, admin_token: str) -> Dict[str, Any]:
        """
        Retry all queued submissions (for background worker)
        
        This implements the buffer pattern from Section 6.4
        """
        from app.db.models import SubmissionQueue
        from sqlalchemy import select
        
        result = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "details": []
        }
        
        # Get queued items
        query = await self.db.execute(
            select(SubmissionQueue)
            .where(SubmissionQueue.status == "QUEUED")
            .order_by(SubmissionQueue.priority, SubmissionQueue.queued_at)
            .limit(50)
        )
        
        queue_items = query.scalars().all()
        
        for item in queue_items:
            result["processed"] += 1
            
            artifact = await self.artifact_service.get_by_id(item.artifact_id)
            if not artifact:
                item.status = "FAILED"
                item.last_error = "Artifact not found"
                result["failed"] += 1
                continue
            
            # For queued items, we use the admin token
            # In production, you'd need to handle this differently
            try:
                client = MoodleClient(token=admin_token)
                
                submit_result = await self._execute_submission(
                    artifact=artifact,
                    assignment_id=artifact.moodle_assignment_id,
                    moodle_token=admin_token,
                    lock_submission=True
                )
                
                item.status = "COMPLETED"
                item.processed_at = datetime.utcnow()
                
                await self.artifact_service.mark_submitted(
                    artifact_id=artifact.id,
                    moodle_submission_id=submit_result.get("submission_id")
                )
                
                result["successful"] += 1
                result["details"].append({
                    "artifact_uuid": str(artifact.artifact_uuid),
                    "status": "success"
                })
                
            except Exception as e:
                item.retry_count += 1
                item.last_error = str(e)
                
                if item.retry_count >= item.max_retries:
                    item.status = "FAILED"
                    await self.artifact_service.mark_failed(
                        artifact_id=artifact.id,
                        error_message=f"Max retries exceeded: {e}",
                        queue_for_retry=False
                    )
                
                result["failed"] += 1
                result["details"].append({
                    "artifact_uuid": str(artifact.artifact_uuid),
                    "status": "failed",
                    "error": str(e)
                })
            
            finally:
                await client.close()
        
        await self.db.commit()
        return result
