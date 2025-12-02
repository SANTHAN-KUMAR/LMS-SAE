"""
Moodle API Client
Complete implementation following the Moodle Web Services API specification
Implements the 3-step submission process from the design document
"""

import httpx
import logging
import base64
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass
from datetime import datetime
import aiofiles
import os

from app.core.config import settings
from app.core.security import token_encryption

logger = logging.getLogger(__name__)


@dataclass
class MoodleError:
    """Structured Moodle error response"""
    exception: str
    errorcode: str
    message: str
    debuginfo: Optional[str] = None


class MoodleAPIError(Exception):
    """Custom exception for Moodle API errors"""
    def __init__(self, message: str, error: Optional[MoodleError] = None, response_data: Any = None):
        self.message = message
        self.error = error
        self.response_data = response_data
        super().__init__(self.message)


class MoodleClient:
    """
    Async Moodle API Client
    
    Implements all required Moodle Web Service functions for the exam middleware:
    - login/token.php - Authentication
    - core_webservice_get_site_info - User identity
    - core_files_upload - Draft area upload
    - mod_assign_save_submission - Link file to assignment
    - mod_assign_submit_for_grading - Finalize submission
    - mod_assign_get_assignments - Get assignments for mapping
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 30.0
    ):
        self.base_url = (base_url or settings.moodle_base_url).rstrip('/')
        self.token = token
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": "ExamMiddleware/1.0",
                    "Accept": "application/json",
                }
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    def _check_error_response(self, data: Any, function_name: str) -> None:
        """
        Check if response contains Moodle error
        Implements error handling from Section 6.1
        """
        if isinstance(data, dict):
            if "exception" in data:
                error = MoodleError(
                    exception=data.get("exception", ""),
                    errorcode=data.get("errorcode", ""),
                    message=data.get("message", "Unknown error"),
                    debuginfo=data.get("debuginfo")
                )
                logger.error(
                    f"Moodle API error in {function_name}: "
                    f"{error.errorcode} - {error.message} "
                    f"(debug: {error.debuginfo})"
                )
                raise MoodleAPIError(
                    f"Moodle API error: {error.message}",
                    error=error,
                    response_data=data
                )
    
    # =========================================
    # Authentication
    # =========================================
    
    async def get_token(
        self,
        username: str,
        password: str,
        service: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Authenticate user and get web service token
        
        Endpoint: /login/token.php
        
        Args:
            username: Moodle username (register number)
            password: Moodle password
            service: Service name (default: moodle_mobile_app)
            
        Returns:
            Dict with 'token' and optionally 'privatetoken'
            
        Raises:
            MoodleAPIError: If authentication fails
        """
        client = await self._get_client()
        
        url = f"{self.base_url}/login/token.php"
        data = {
            "username": username,
            "password": password,
            "service": service or settings.moodle_service
        }
        
        logger.info(f"Authenticating user: {username}")
        
        try:
            response = await client.post(url, data=data)
            response.raise_for_status()
            result = response.json()
            
            # Check for error in response
            if "error" in result:
                raise MoodleAPIError(
                    f"Authentication failed: {result.get('error')}",
                    response_data=result
                )
            
            if "token" not in result:
                raise MoodleAPIError(
                    "No token in response",
                    response_data=result
                )
            
            logger.info(f"Successfully authenticated user: {username}")
            return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during authentication: {e}")
            raise MoodleAPIError(f"HTTP error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise
    
    # =========================================
    # User Information
    # =========================================
    
    async def get_site_info(self, token: Optional[str] = None) -> Dict[str, Any]:
        """
        Get site and user information from token
        
        Function: core_webservice_get_site_info
        
        Args:
            token: Web service token (uses self.token if not provided)
            
        Returns:
            Dict containing userid, username, fullname, etc.
        """
        client = await self._get_client()
        ws_token = token or self.token
        
        if not ws_token:
            raise MoodleAPIError("No token provided")
        
        url = f"{self.base_url}/webservice/rest/server.php"
        params = {
            "wstoken": ws_token,
            "wsfunction": "core_webservice_get_site_info",
            "moodlewsrestformat": "json"
        }
        
        try:
            response = await client.post(url, data=params)
            response.raise_for_status()
            result = response.json()
            
            self._check_error_response(result, "core_webservice_get_site_info")
            
            logger.info(f"Got site info for user: {result.get('username')}")
            return result
            
        except httpx.HTTPStatusError as e:
            raise MoodleAPIError(f"HTTP error: {e.response.status_code}")
    
    # =========================================
    # Course and Assignment Discovery
    # =========================================
    
    async def get_courses_by_field(
        self,
        field: str,
        value: str,
        token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get courses by a specific field
        
        Function: core_course_get_courses_by_field
        
        Args:
            field: Field to search by (e.g., 'idnumber')
            value: Value to search for (e.g., '19AI405')
            token: Web service token
            
        Returns:
            List of matching courses
        """
        client = await self._get_client()
        ws_token = token or self.token
        
        url = f"{self.base_url}/webservice/rest/server.php"
        params = {
            "wstoken": ws_token,
            "wsfunction": "core_course_get_courses_by_field",
            "moodlewsrestformat": "json",
            "field": field,
            "value": value
        }
        
        try:
            response = await client.post(url, data=params)
            response.raise_for_status()
            result = response.json()
            
            self._check_error_response(result, "core_course_get_courses_by_field")
            
            courses = result.get("courses", [])
            logger.info(f"Found {len(courses)} courses for {field}={value}")
            return courses
            
        except httpx.HTTPStatusError as e:
            raise MoodleAPIError(f"HTTP error: {e.response.status_code}")
    
    async def get_courses(
        self,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get all courses the user has access to
        
        Function: core_course_get_courses
        
        Args:
            token: Web service token
            
        Returns:
            Dict with courses list
        """
        client = await self._get_client()
        ws_token = token or self.token
        
        url = f"{self.base_url}/webservice/rest/server.php"
        params = {
            "wstoken": ws_token,
            "wsfunction": "core_course_get_courses",
            "moodlewsrestformat": "json",
        }
        
        try:
            response = await client.post(url, data=params)
            response.raise_for_status()
            result = response.json()
            
            self._check_error_response(result, "core_course_get_courses")
            
            # Result is array of courses
            return {"courses": result if isinstance(result, list) else []}
            
        except httpx.HTTPStatusError as e:
            raise MoodleAPIError(f"HTTP error: {e.response.status_code}")
    
    async def get_assignments(
        self,
        course_ids: List[int],
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get assignments for specified courses
        
        Function: mod_assign_get_assignments
        
        Args:
            course_ids: List of course IDs
            token: Web service token
            
        Returns:
            Dict with courses and their assignments
        """
        client = await self._get_client()
        ws_token = token or self.token
        
        url = f"{self.base_url}/webservice/rest/server.php"
        params = {
            "wstoken": ws_token,
            "wsfunction": "mod_assign_get_assignments",
            "moodlewsrestformat": "json",
        }
        
        # Add course IDs
        for i, course_id in enumerate(course_ids):
            params[f"courseids[{i}]"] = str(course_id)
        
        try:
            response = await client.post(url, data=params)
            response.raise_for_status()
            result = response.json()
            
            self._check_error_response(result, "mod_assign_get_assignments")
            
            return result
            
        except httpx.HTTPStatusError as e:
            raise MoodleAPIError(f"HTTP error: {e.response.status_code}")
    
    # =========================================
    # File Upload (Step 1 of Submission)
    # =========================================
    
    async def upload_file(
        self,
        file_path: str,
        token: Optional[str] = None,
        filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Upload file to Moodle draft area
        
        Endpoint: /webservice/upload.php
        
        This is Step 1 of the submission process.
        Returns an itemid which is used in save_submission.
        
        Args:
            file_path: Path to the file to upload
            token: Web service token
            filename: Optional override for filename
            
        Returns:
            Dict with 'itemid' for the uploaded file
        """
        client = await self._get_client()
        ws_token = token or self.token
        
        if not ws_token:
            raise MoodleAPIError("No token provided for file upload")
        
        if not os.path.exists(file_path):
            raise MoodleAPIError(f"File not found: {file_path}")
        
        upload_filename = filename or os.path.basename(file_path)
        
        # Determine MIME type
        ext = os.path.splitext(file_path)[1].lower()
        mime_types = {
            '.pdf': 'application/pdf',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
        }
        mime_type = mime_types.get(ext, 'application/octet-stream')
        
        url = f"{self.base_url}/webservice/upload.php"
        
        try:
            # Read file content
            async with aiofiles.open(file_path, 'rb') as f:
                file_content = await f.read()
            
            # Prepare multipart form data
            files = {
                'file_1': (upload_filename, file_content, mime_type)
            }
            data = {
                'token': ws_token
            }
            
            logger.info(f"Uploading file: {upload_filename} ({len(file_content)} bytes)")
            
            response = await client.post(url, files=files, data=data)
            response.raise_for_status()
            result = response.json()
            
            # Check for error
            if isinstance(result, dict) and "error" in result:
                raise MoodleAPIError(
                    f"Upload error: {result.get('error')}",
                    response_data=result
                )
            
            # Response should be a list with file info
            # Log the raw upload response
            logger.info(f"Upload response: {result}")
            
            if isinstance(result, list) and len(result) > 0:
                item_id = result[0].get('itemid')
                if item_id:
                    logger.info(f"File uploaded successfully. Item ID: {item_id}")
                    return {
                        "itemid": item_id,
                        "filename": result[0].get('filename', upload_filename),
                        "fileurl": result[0].get('url')
                    }
            
            raise MoodleAPIError(
                "Unexpected upload response format",
                response_data=result
            )
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during upload: {e}")
            raise MoodleAPIError(f"HTTP error: {e.response.status_code}")
    
    # =========================================
    # Save Submission (Step 2 of Submission)
    # =========================================
    
    async def save_submission(
        self,
        assignment_id: int,
        item_id: int,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Save/link the uploaded file to an assignment submission
        
        Function: mod_assign_save_submission
        
        This is Step 2 of the submission process.
        Links the draft file (item_id) to the assignment.
        
        CRITICAL: plugindata structure must match assignment configuration
        
        Args:
            assignment_id: Moodle assignment ID
            item_id: Draft item ID from upload_file
            token: Web service token
            
        Returns:
            Empty list on success, or warnings dict
        """
        client = await self._get_client()
        ws_token = token or self.token
        
        url = f"{self.base_url}/webservice/rest/server.php"
        
        # IMPORTANT: This exact structure is required by Moodle
        # plugindata[files_filemanager] links the draft to file submission
        params = {
            "wstoken": ws_token,
            "wsfunction": "mod_assign_save_submission",
            "moodlewsrestformat": "json",
            "assignmentid": str(assignment_id),
            "plugindata[files_filemanager]": str(item_id)
        }
        
        logger.info(f"Saving submission for assignment {assignment_id} with item {item_id}")
        
        try:
            response = await client.post(url, data=params)
            response.raise_for_status()
            result = response.json()
            
            self._check_error_response(result, "mod_assign_save_submission")
            
            # Log the raw response for debugging
            logger.info(f"mod_assign_save_submission response: {result}")
            
            # Success is indicated by empty array or null
            if result is None or (isinstance(result, list) and len(result) == 0):
                logger.info(f"Submission saved successfully for assignment {assignment_id}")
                return {"success": True, "warnings": []}
            
            # Check for warnings
            if isinstance(result, dict) and "warnings" in result:
                warnings = result.get("warnings", [])
                if warnings:
                    logger.warning(f"Submission saved with warnings: {warnings}")
                return {"success": True, "warnings": warnings}
            
            logger.info(f"Unexpected save_submission response format: {result}")
            return {"success": True, "data": result}
            
        except httpx.HTTPStatusError as e:
            raise MoodleAPIError(f"HTTP error: {e.response.status_code}")
    
    # =========================================
    # Submit for Grading (Step 3 of Submission)
    # =========================================
    
    async def submit_for_grading(
        self,
        assignment_id: int,
        accept_statement: bool = True,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Finalize submission - locks it from further editing
        
        Function: mod_assign_submit_for_grading
        
        This is Step 3 (final) of the submission process.
        After this, the student cannot edit their submission.
        
        Args:
            assignment_id: Moodle assignment ID
            accept_statement: Accept submission statement (default True)
            token: Web service token
            
        Returns:
            Empty list on success
        """
        client = await self._get_client()
        ws_token = token or self.token
        
        url = f"{self.base_url}/webservice/rest/server.php"
        params = {
            "wstoken": ws_token,
            "wsfunction": "mod_assign_submit_for_grading",
            "moodlewsrestformat": "json",
            "assignmentid": str(assignment_id),
            "acceptsubmissionstatement": "1" if accept_statement else "0"
        }
        
        logger.info(f"Submitting for grading: assignment {assignment_id}")
        
        try:
            response = await client.post(url, data=params)
            response.raise_for_status()
            result = response.json()
            
            self._check_error_response(result, "mod_assign_submit_for_grading")
            
            # Log the raw response for debugging
            logger.info(f"mod_assign_submit_for_grading response: {result}")
            logger.debug(f"Response type: {type(result)}, is list: {isinstance(result, list)}")
            if isinstance(result, list):
                logger.debug(f"List length: {len(result)}")
                for idx, item in enumerate(result):
                    logger.debug(f"Item {idx}: type={type(item)}, value={item}")
                    if isinstance(item, dict):
                        logger.debug(f"Item {idx} keys: {item.keys()}")
            
            # Check for warnings - Moodle returns warnings array if submission failed
            if isinstance(result, list) and len(result) > 0:
                # Check if any item has a warningcode
                for warning in result:
                    if isinstance(warning, dict) and 'warningcode' in warning:
                        warning_code = warning.get('warningcode', '')
                        error_msg = warning.get('message', 'Unknown error')

                        # NOTE:
                        # Previously we treated "couldnotsubmitforgrading" as a soft-warning and
                        # still marked the submission as successful under the assumption that
                        # some assignments auto-submit files (no draft mode).
                        #
                        # In practice (as seen in your environment) this can mean *nothing has
                        # actually been submitted for grading* and the teacher UI continues to
                        # show "No submission".  To avoid false positives on the portal, we now
                        # ALWAYS treat this as a hard error and bubble it up.
                        if warning_code == 'couldnotsubmitforgrading':
                            logger.error(
                                f"Moodle returned 'couldnotsubmitforgrading' for assignment {assignment_id}: "
                                f"{error_msg}. Treating as hard failure."
                            )
                            raise MoodleAPIError(
                                f"Submission failed (Moodle could not submit for grading): {error_msg}",
                                response_data=result
                            )

                        logger.error(f"Moodle warning during submit_for_grading: {warning}")
                        raise MoodleAPIError(
                            f"Submission failed: {error_msg}",
                            response_data=result
                        )
            
            logger.info(f"Successfully submitted for grading: assignment {assignment_id}")
            return {"success": True, "data": result}
            
        except httpx.HTTPStatusError as e:
            raise MoodleAPIError(f"HTTP error: {e.response.status_code}")
    
    # =========================================
    # Get Submission Status
    # =========================================
    
    async def get_submissions(
        self,
        assignment_ids: List[int],
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get submissions for assignments
        
        Function: mod_assign_get_submissions
        
        Args:
            assignment_ids: List of assignment IDs
            token: Web service token
            
        Returns:
            Submissions data
        """
        client = await self._get_client()
        ws_token = token or self.token
        
        url = f"{self.base_url}/webservice/rest/server.php"
        params = {
            "wstoken": ws_token,
            "wsfunction": "mod_assign_get_submissions",
            "moodlewsrestformat": "json",
        }
        
        for i, aid in enumerate(assignment_ids):
            params[f"assignmentids[{i}]"] = str(aid)
        
        try:
            response = await client.post(url, data=params)
            response.raise_for_status()
            result = response.json()
            
            self._check_error_response(result, "mod_assign_get_submissions")
            return result
            
        except httpx.HTTPStatusError as e:
            raise MoodleAPIError(f"HTTP error: {e.response.status_code}")
    
    async def get_submission_status(
        self,
        assignment_id: int,
        user_id: Optional[int] = None,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get detailed submission status for an assignment
        
        Function: mod_assign_get_submission_status
        
        Args:
            assignment_id: Assignment ID
            user_id: Optional user ID (defaults to current user)
            token: Web service token
            
        Returns:
            Detailed submission status
        """
        client = await self._get_client()
        ws_token = token or self.token
        
        url = f"{self.base_url}/webservice/rest/server.php"
        params = {
            "wstoken": ws_token,
            "wsfunction": "mod_assign_get_submission_status",
            "moodlewsrestformat": "json",
            "assignid": str(assignment_id),
        }
        
        if user_id:
            params["userid"] = str(user_id)
        
        try:
            response = await client.post(url, data=params)
            response.raise_for_status()
            result = response.json()
            
            self._check_error_response(result, "mod_assign_get_submission_status")
            return result
            
        except httpx.HTTPStatusError as e:
            raise MoodleAPIError(f"HTTP error: {e.response.status_code}")
    
    # =========================================
    # Complete Submission Workflow
    # =========================================
    
    async def submit_assignment_complete(
        self,
        assignment_id: int,
        file_path: str,
        token: Optional[str] = None,
        filename: Optional[str] = None,
        lock_submission: bool = True
    ) -> Dict[str, Any]:
        """
        Complete 3-step submission workflow
        
        1. Upload file to draft area
        2. Save submission (link file to assignment)
        3. Submit for grading (lock submission)
        
        Args:
            assignment_id: Target assignment ID
            file_path: Path to file to submit
            token: Web service token
            filename: Optional override for filename
            lock_submission: Whether to lock submission after saving
            
        Returns:
            Dict with submission details and step results
        """
        ws_token = token or self.token
        result = {
            "success": False,
            "assignment_id": assignment_id,
            "steps": {},
            "errors": []
        }
        
        try:
            # Step 1: Upload file
            logger.info("Step 1/3: Uploading file to draft area...")
            upload_result = await self.upload_file(
                file_path=file_path,
                token=ws_token,
                filename=filename
            )
            result["steps"]["upload"] = {
                "success": True,
                "item_id": upload_result["itemid"]
            }
            item_id = upload_result["itemid"]
            
            # Step 2: Save submission
            logger.info("Step 2/3: Linking file to assignment...")
            save_result = await self.save_submission(
                assignment_id=assignment_id,
                item_id=item_id,
                token=ws_token
            )
            result["steps"]["save"] = {
                "success": True,
                "data": save_result
            }
            
            # Step 3: Submit for grading (if requested)
            if lock_submission:
                logger.info("Step 3/3: Finalizing submission...")
                submit_result = await self.submit_for_grading(
                    assignment_id=assignment_id,
                    token=ws_token
                )
                result["steps"]["submit"] = {
                    "success": True,
                    "data": submit_result
                }
            else:
                result["steps"]["submit"] = {
                    "skipped": True,
                    "reason": "lock_submission=False"
                }
            
            result["success"] = True
            result["item_id"] = item_id
            logger.info(f"Complete submission successful for assignment {assignment_id}")
            
        except MoodleAPIError as e:
            result["errors"].append(str(e))
            logger.error(f"Submission failed: {e}")
            raise
        except Exception as e:
            result["errors"].append(str(e))
            logger.error(f"Unexpected error during submission: {e}")
            raise MoodleAPIError(f"Submission failed: {e}")
        
        return result
    
    # =========================================
    # Health Check
    # =========================================
    
    async def check_connection(self) -> Tuple[bool, str]:
        """
        Check if Moodle is accessible
        
        Returns:
            Tuple of (is_connected, message)
        """
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/login/index.php",
                timeout=10.0
            )
            if response.status_code == 200:
                return True, "Moodle is accessible"
            else:
                return False, f"Unexpected status: {response.status_code}"
        except Exception as e:
            return False, f"Connection error: {e}"


# Create a default client instance
moodle_client = MoodleClient()
