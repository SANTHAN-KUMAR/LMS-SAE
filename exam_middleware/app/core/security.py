"""
Security utilities for JWT token management and password hashing
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
import bcrypt
from cryptography.fernet import Fernet
import base64
import hashlib
import secrets

from app.core.config import settings


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token
    
    Args:
        data: Payload data to encode
        expires_delta: Optional custom expiration time
        
    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "jti": secrets.token_hex(16)  # Unique token ID for potential revocation
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.algorithm
    )
    
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate a JWT access token
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded payload or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm]
        )
        return payload
    except JWTError:
        return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    try:
        password_bytes = plain_password.encode('utf-8')
        hash_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hash_bytes)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Generate password hash"""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def generate_token_key() -> str:
    """Generate a secure random token key"""
    return secrets.token_urlsafe(32)


class TokenEncryption:
    """
    AES-256 encryption for storing Moodle tokens securely
    Implements the security requirement from the design doc
    """
    
    def __init__(self, key: Optional[str] = None):
        """
        Initialize encryption with a key derived from secret_key
        """
        if key is None:
            key = settings.secret_key
        
        # Derive a 32-byte key for Fernet (AES-256)
        derived_key = hashlib.sha256(key.encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(derived_key))
    
    def encrypt(self, data: str) -> str:
        """
        Encrypt a string (e.g., Moodle token)
        
        Args:
            data: Plain text to encrypt
            
        Returns:
            Base64 encoded encrypted string
        """
        encrypted = self._fernet.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """
        Decrypt an encrypted string
        
        Args:
            encrypted_data: Base64 encoded encrypted string
            
        Returns:
            Decrypted plain text
        """
        decoded = base64.urlsafe_b64decode(encrypted_data.encode())
        decrypted = self._fernet.decrypt(decoded)
        return decrypted.decode()


# Global token encryption instance
token_encryption = TokenEncryption()


def compute_file_hash(file_content: bytes) -> str:
    """
    Compute SHA-256 hash of file content for integrity verification
    
    Args:
        file_content: Raw file bytes
        
    Returns:
        Hex digest of SHA-256 hash
    """
    return hashlib.sha256(file_content).hexdigest()


def generate_transaction_id(register_number: str, subject_code: str, exam_session: str = "") -> str:
    """
    Generate idempotent transaction ID for submission tracking
    This ensures the same submission attempt always generates the same ID
    
    Args:
        register_number: Student's register number
        subject_code: Subject code from the paper
        exam_session: Optional exam session identifier
        
    Returns:
        Unique transaction ID
    """
    # Create deterministic hash from components
    components = f"{register_number}:{subject_code}:{exam_session}"
    return hashlib.sha256(components.encode()).hexdigest()[:32]


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent directory traversal attacks
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename safe for storage
    """
    import os
    import re
    
    # Remove any path components
    filename = os.path.basename(filename)
    
    # Remove potentially dangerous characters
    filename = re.sub(r'[^\w\s\-\.]', '', filename)
    
    # Remove leading/trailing dots and spaces
    filename = filename.strip('. ')
    
    # Ensure it's not empty
    if not filename:
        filename = f"file_{secrets.token_hex(8)}"
    
    return filename
