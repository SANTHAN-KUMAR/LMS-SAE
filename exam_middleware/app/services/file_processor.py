"""
File Processing Service
Handles filename parsing, validation, and file operations
"""

import os
import re
import uuid
import hashlib
import logging
from typing import Optional, Tuple, Dict, Any
from datetime import datetime
import aiofiles
import aiofiles.os

from app.core.config import settings
from app.core.security import sanitize_filename, compute_file_hash

logger = logging.getLogger(__name__)


class FileProcessor:
    """
    Service for processing uploaded examination files
    
    Implements the parsing strategy from Section 3.1 of the design document
    """
    
    # Regex patterns for filename parsing
    # Pattern: REGISTER_NUMBER_SUBJECT_CODE.pdf
    # Example: 212223240065_19AI405.pdf
    FILENAME_PATTERN = re.compile(
        r'^(\d{12})_([A-Z0-9]{2,10})\.(pdf|jpg|jpeg|png)$',
        re.IGNORECASE
    )
    
    # More flexible pattern for variations
    FLEXIBLE_PATTERN = re.compile(
        r'(\d{10,12})[_\-\s]?([A-Z]{2,3}[\d]{2,4}[A-Z]?\d*)',
        re.IGNORECASE
    )
    
    def __init__(self, upload_dir: Optional[str] = None):
        self.upload_dir = upload_dir or settings.upload_dir
        self._ensure_upload_dir()
    
    def _ensure_upload_dir(self):
        """Ensure upload directory exists"""
        os.makedirs(self.upload_dir, exist_ok=True)
        
        # Create subdirectories for organization
        for subdir in ['pending', 'processed', 'failed', 'temp']:
            os.makedirs(os.path.join(self.upload_dir, subdir), exist_ok=True)
    
    def parse_filename(self, filename: str) -> Tuple[Optional[str], Optional[str], bool]:
        """
        Parse filename to extract register number and subject code
        
        Implements the Regex Pattern Strategy from Section 3.1
        
        Args:
            filename: Original filename
            
        Returns:
            Tuple of (register_number, subject_code, is_valid)
        """
        # Sanitize first
        clean_filename = sanitize_filename(filename)
        
        # Try strict pattern first
        match = self.FILENAME_PATTERN.match(clean_filename)
        if match:
            register_no = match.group(1)
            subject_code = match.group(2).upper()
            logger.info(f"Parsed filename (strict): {register_no}, {subject_code}")
            return register_no, subject_code, True
        
        # Try flexible pattern
        match = self.FLEXIBLE_PATTERN.search(clean_filename)
        if match:
            register_no = match.group(1)
            # Pad to 12 digits if needed
            if len(register_no) < 12:
                register_no = register_no.zfill(12)
            subject_code = match.group(2).upper()
            logger.info(f"Parsed filename (flexible): {register_no}, {subject_code}")
            return register_no, subject_code, True
        
        logger.warning(f"Could not parse filename: {filename}")
        return None, None, False
    
    def validate_file(
        self,
        file_content: bytes,
        filename: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validate uploaded file
        
        Args:
            file_content: Raw file bytes
            filename: Original filename
            
        Returns:
            Tuple of (is_valid, message, metadata)
        """
        metadata = {
            "original_filename": filename,
            "size_bytes": len(file_content),
            "hash": compute_file_hash(file_content)
        }
        
        # Check file size
        if len(file_content) > settings.max_file_size_bytes:
            return False, f"File too large. Max size: {settings.max_file_size_mb}MB", metadata
        
        # Check extension
        ext = os.path.splitext(filename)[1].lower()
        if ext not in settings.allowed_extensions_list:
            return False, f"Invalid file type. Allowed: {settings.allowed_extensions}", metadata
        
        # Validate file magic bytes
        mime_type = self._detect_mime_type(file_content)
        if not mime_type:
            return False, "Could not determine file type", metadata
        
        metadata["mime_type"] = mime_type
        
        # Parse filename
        register_no, subject_code, is_parsed = self.parse_filename(filename)
        metadata["parsed_register_no"] = register_no
        metadata["parsed_subject_code"] = subject_code
        metadata["filename_valid"] = is_parsed
        
        if not is_parsed:
            return False, "Invalid filename format. Expected: REGISTER_SUBJECT.pdf", metadata
        
        return True, "File validated successfully", metadata
    
    def _detect_mime_type(self, content: bytes) -> Optional[str]:
        """Detect MIME type from file content magic bytes"""
        # PDF magic bytes
        if content[:4] == b'%PDF':
            return 'application/pdf'
        
        # JPEG magic bytes
        if content[:2] == b'\xff\xd8':
            return 'image/jpeg'
        
        # PNG magic bytes
        if content[:8] == b'\x89PNG\r\n\x1a\n':
            return 'image/png'
        
        return None
    
    async def save_file(
        self,
        file_content: bytes,
        original_filename: str,
        subfolder: str = "pending"
    ) -> Tuple[str, str]:
        """
        Save file to storage
        
        Args:
            file_content: Raw file bytes
            original_filename: Original filename
            subfolder: Subdirectory (pending, processed, etc.)
            
        Returns:
            Tuple of (file_path, file_hash)
        """
        # Generate unique filename
        file_hash = compute_file_hash(file_content)
        ext = os.path.splitext(original_filename)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        
        # Build path
        file_path = os.path.join(self.upload_dir, subfolder, unique_filename)
        
        # Ensure directory exists
        await aiofiles.os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Write file
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_content)
        
        logger.info(f"Saved file: {file_path} (hash: {file_hash[:16]}...)")
        
        return file_path, file_hash
    
    async def move_file(
        self,
        source_path: str,
        destination_subfolder: str
    ) -> str:
        """Move file to different subfolder"""
        filename = os.path.basename(source_path)
        dest_path = os.path.join(self.upload_dir, destination_subfolder, filename)
        
        await aiofiles.os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        await aiofiles.os.rename(source_path, dest_path)
        
        logger.info(f"Moved file: {source_path} -> {dest_path}")
        return dest_path
    
    async def delete_file(self, file_path: str) -> bool:
        """Delete a file"""
        try:
            if await aiofiles.os.path.exists(file_path):
                await aiofiles.os.remove(file_path)
                logger.info(f"Deleted file: {file_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")
            return False
    
    async def get_file_content(self, file_path: str) -> Optional[bytes]:
        """Read file content"""
        try:
            async with aiofiles.open(file_path, 'rb') as f:
                return await f.read()
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return None
    
    def generate_standardized_filename(
        self,
        register_number: str,
        subject_code: str,
        extension: str = ".pdf"
    ) -> str:
        """Generate standardized filename from metadata"""
        clean_reg = re.sub(r'[^\d]', '', register_number)[:12].zfill(12)
        clean_subject = re.sub(r'[^A-Z0-9]', '', subject_code.upper())[:10]
        return f"{clean_reg}_{clean_subject}{extension}"


# Global instance
file_processor = FileProcessor()
