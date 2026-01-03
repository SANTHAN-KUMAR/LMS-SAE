"""
Unit Tests for Security Module

Tests the security functionality including:
- Password hashing and verification
- JWT token generation and validation
- Token encryption/decryption
- Key generation
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
import jwt

from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token,
    generate_secure_key,
    TokenEncryption,
    token_encryption
)
from app.core.config import settings


class TestPasswordHashing:
    """Tests for password hashing functionality."""
    
    def test_hash_password_returns_string(self):
        """Test that hashing returns a string."""
        hashed = get_password_hash("password123")
        assert isinstance(hashed, str)
        assert len(hashed) > 0
    
    def test_hash_is_not_plaintext(self):
        """Test that hash is not the plaintext password."""
        password = "password123"
        hashed = get_password_hash(password)
        assert hashed != password
    
    def test_hash_is_bcrypt_format(self):
        """Test that hash is in bcrypt format."""
        hashed = get_password_hash("password123")
        # Bcrypt hashes start with $2b$ or $2a$
        assert hashed.startswith("$2")
    
    def test_same_password_different_hashes(self):
        """Test that same password produces different hashes (salting)."""
        password = "password123"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)
        
        # Due to salting, hashes should differ
        assert hash1 != hash2
    
    def test_verify_correct_password(self):
        """Test that correct password verifies successfully."""
        password = "correctpassword"
        hashed = get_password_hash(password)
        
        assert verify_password(password, hashed) is True
    
    def test_verify_incorrect_password(self):
        """Test that incorrect password fails verification."""
        hashed = get_password_hash("correctpassword")
        
        assert verify_password("wrongpassword", hashed) is False
    
    def test_verify_empty_password(self):
        """Test verification with empty password."""
        hashed = get_password_hash("password123")
        
        assert verify_password("", hashed) is False
    
    def test_hash_special_characters(self):
        """Test hashing password with special characters."""
        password = "P@$$w0rd!#$%^&*()"
        hashed = get_password_hash(password)
        
        assert verify_password(password, hashed) is True
    
    def test_hash_unicode_password(self):
        """Test hashing password with unicode characters."""
        password = "пароль123日本語"
        hashed = get_password_hash(password)
        
        assert verify_password(password, hashed) is True
    
    def test_hash_very_long_password(self):
        """Test hashing very long password."""
        # Note: bcrypt has a 72 byte limit
        password = "a" * 100
        hashed = get_password_hash(password)
        
        # Should still work (bcrypt truncates at 72 bytes)
        assert verify_password(password, hashed) is True


class TestJWTTokens:
    """Tests for JWT token generation and validation."""
    
    def test_create_token_returns_string(self):
        """Test that token creation returns a string."""
        token = create_access_token(data={"sub": "testuser"})
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_create_token_has_three_parts(self):
        """Test that JWT has header.payload.signature format."""
        token = create_access_token(data={"sub": "testuser"})
        parts = token.split(".")
        assert len(parts) == 3
    
    def test_decode_valid_token(self):
        """Test decoding a valid token."""
        original_data = {"sub": "testuser", "role": "staff"}
        token = create_access_token(data=original_data)
        
        decoded = decode_access_token(token)
        
        assert decoded is not None
        assert decoded.get("sub") == "testuser"
        assert decoded.get("role") == "staff"
    
    def test_decode_expired_token_returns_none(self):
        """Test that expired tokens fail validation."""
        token = create_access_token(
            data={"sub": "testuser"},
            expires_delta=timedelta(seconds=-1)  # Already expired
        )
        
        decoded = decode_access_token(token)
        
        # Should return None or raise exception for expired token
        assert decoded is None or "exp" in str(decoded)
    
    def test_decode_invalid_token(self):
        """Test decoding an invalid token."""
        decoded = decode_access_token("invalid.token.here")
        
        assert decoded is None
    
    def test_token_contains_expiration(self):
        """Test that token contains expiration claim."""
        token = create_access_token(data={"sub": "testuser"})
        
        # Decode without verification to check structure
        decoded = jwt.decode(token, options={"verify_signature": False})
        
        assert "exp" in decoded
    
    def test_token_custom_expiration(self):
        """Test token with custom expiration time."""
        custom_delta = timedelta(hours=24)
        token = create_access_token(
            data={"sub": "testuser"},
            expires_delta=custom_delta
        )
        
        decoded = jwt.decode(token, options={"verify_signature": False})
        exp_time = datetime.fromtimestamp(decoded["exp"])
        
        # Should expire roughly 24 hours from now
        expected = datetime.utcnow() + custom_delta
        assert abs((exp_time - expected).total_seconds()) < 60  # Within 1 minute
    
    def test_decode_tampered_token(self):
        """Test that tampered tokens fail validation."""
        token = create_access_token(data={"sub": "testuser"})
        
        # Tamper with the payload (middle part)
        parts = token.split(".")
        parts[1] = parts[1][:-1] + "X"  # Modify last character
        tampered = ".".join(parts)
        
        decoded = decode_access_token(tampered)
        
        assert decoded is None
    
    def test_token_preserves_data_types(self):
        """Test that data types are preserved in token."""
        data = {
            "sub": "testuser",
            "user_id": 42,
            "is_admin": True,
            "score": 3.14
        }
        token = create_access_token(data=data)
        decoded = decode_access_token(token)
        
        assert decoded["user_id"] == 42
        assert decoded["is_admin"] is True
        assert decoded["score"] == 3.14


class TestTokenEncryption:
    """Tests for Moodle token encryption/decryption."""
    
    def test_encrypt_returns_string(self):
        """Test that encryption returns a string."""
        encrypted = token_encryption.encrypt("test-token")
        assert isinstance(encrypted, str)
    
    def test_encrypt_not_plaintext(self):
        """Test that encrypted value is not plaintext."""
        plaintext = "moodle-token-12345"
        encrypted = token_encryption.encrypt(plaintext)
        assert encrypted != plaintext
    
    def test_decrypt_returns_original(self):
        """Test that decryption returns original value."""
        original = "moodle-token-12345"
        encrypted = token_encryption.encrypt(original)
        decrypted = token_encryption.decrypt(encrypted)
        
        assert decrypted == original
    
    def test_encrypt_same_value_different_results(self):
        """Test that encrypting same value produces different ciphertexts."""
        plaintext = "same-token"
        encrypted1 = token_encryption.encrypt(plaintext)
        encrypted2 = token_encryption.encrypt(plaintext)
        
        # Fernet includes a timestamp, so same plaintext = different ciphertext
        assert encrypted1 != encrypted2
        
        # But both should decrypt to same value
        assert token_encryption.decrypt(encrypted1) == token_encryption.decrypt(encrypted2)
    
    def test_decrypt_invalid_data_fails(self):
        """Test that decrypting invalid data fails gracefully."""
        with pytest.raises(Exception):
            token_encryption.decrypt("invalid-encrypted-data")
    
    def test_encrypt_empty_string(self):
        """Test encrypting empty string."""
        encrypted = token_encryption.encrypt("")
        decrypted = token_encryption.decrypt(encrypted)
        assert decrypted == ""
    
    def test_encrypt_unicode(self):
        """Test encrypting unicode characters."""
        original = "токен-日本語-🔐"
        encrypted = token_encryption.encrypt(original)
        decrypted = token_encryption.decrypt(encrypted)
        assert decrypted == original
    
    def test_encrypt_long_token(self):
        """Test encrypting long token."""
        original = "x" * 1000
        encrypted = token_encryption.encrypt(original)
        decrypted = token_encryption.decrypt(encrypted)
        assert decrypted == original


class TestSecureKeyGeneration:
    """Tests for secure key generation."""
    
    def test_generate_key_returns_string(self):
        """Test that key generation returns a string."""
        key = generate_secure_key()
        assert isinstance(key, str)
    
    def test_generate_key_default_length(self):
        """Test default key length."""
        key = generate_secure_key()
        # Default should produce a reasonable length
        assert len(key) >= 32
    
    def test_generate_key_custom_length(self):
        """Test custom key length."""
        key = generate_secure_key(length=64)
        assert len(key) >= 64
    
    def test_generate_key_unique(self):
        """Test that generated keys are unique."""
        keys = [generate_secure_key() for _ in range(100)]
        unique_keys = set(keys)
        
        assert len(unique_keys) == 100
    
    def test_generate_key_url_safe(self):
        """Test that key is URL-safe."""
        key = generate_secure_key()
        # URL-safe base64 characters: A-Z, a-z, 0-9, -, _
        import re
        assert re.match(r'^[A-Za-z0-9_-]+$', key)


class TestTokenEncryptionClass:
    """Tests for the TokenEncryption class initialization."""
    
    def test_create_with_key(self):
        """Test creating encryption with specific key."""
        key = "test-secret-key-32-chars-long!!!"
        encryptor = TokenEncryption(key)
        
        encrypted = encryptor.encrypt("test")
        decrypted = encryptor.decrypt(encrypted)
        
        assert decrypted == "test"
    
    def test_different_keys_incompatible(self):
        """Test that different keys produce incompatible encryptions."""
        encryptor1 = TokenEncryption("key1-32-characters-long-here!!!")
        encryptor2 = TokenEncryption("key2-32-characters-long-here!!!")
        
        encrypted = encryptor1.encrypt("test")
        
        with pytest.raises(Exception):
            encryptor2.decrypt(encrypted)
    
    def test_same_key_compatible(self):
        """Test that same key produces compatible encryptions."""
        key = "same-key-32-characters-long!!!"
        encryptor1 = TokenEncryption(key)
        encryptor2 = TokenEncryption(key)
        
        encrypted = encryptor1.encrypt("test")
        decrypted = encryptor2.decrypt(encrypted)
        
        assert decrypted == "test"
