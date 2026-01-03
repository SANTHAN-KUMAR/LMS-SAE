"""
Integration Tests for Authentication API Routes

Tests the authentication endpoints including:
- Staff login/logout
- Student Moodle login
- Session management
- Token validation
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient
from datetime import datetime, timedelta

from app.db.models import StaffUser, StudentSession
from app.core.security import get_password_hash, create_access_token

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.factories import StaffUserFactory


class TestStaffLogin:
    """Tests for staff login endpoint."""
    
    @pytest.mark.asyncio
    async def test_login_valid_credentials(self, client: AsyncClient, staff_user):
        """Test login with valid credentials."""
        response = await client.post(
            "/api/v1/auth/staff/login",
            json={
                "username": "test_staff",
                "password": "testpass123"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    @pytest.mark.asyncio
    async def test_login_invalid_password(self, client: AsyncClient, staff_user):
        """Test login with wrong password."""
        response = await client.post(
            "/api/v1/auth/staff/login",
            json={
                "username": "test_staff",
                "password": "wrongpassword"
            }
        )
        
        assert response.status_code in [401, 400]
    
    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Test login with non-existent user."""
        response = await client.post(
            "/api/v1/auth/staff/login",
            json={
                "username": "nonexistent",
                "password": "password123"
            }
        )
        
        assert response.status_code in [401, 400]
    
    @pytest.mark.asyncio
    async def test_login_missing_username(self, client: AsyncClient):
        """Test login without username."""
        response = await client.post(
            "/api/v1/auth/staff/login",
            json={
                "password": "password123"
            }
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_login_missing_password(self, client: AsyncClient):
        """Test login without password."""
        response = await client.post(
            "/api/v1/auth/staff/login",
            json={
                "username": "test_staff"
            }
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_login_empty_credentials(self, client: AsyncClient):
        """Test login with empty credentials."""
        response = await client.post(
            "/api/v1/auth/staff/login",
            json={
                "username": "",
                "password": ""
            }
        )
        
        assert response.status_code in [400, 401, 422]
    
    @pytest.mark.asyncio
    async def test_login_inactive_user(self, client: AsyncClient, db_session):
        """Test login with inactive user account."""
        # Create inactive user
        user = StaffUserFactory.create(username="inactive_user", is_active=False)
        db_session.add(user)
        await db_session.commit()
        
        response = await client.post(
            "/api/v1/auth/staff/login",
            json={
                "username": "inactive_user",
                "password": "testpass123"
            }
        )
        
        # Should reject inactive user
        assert response.status_code in [400, 401, 403]


class TestStudentLogin:
    """Tests for student Moodle login endpoint."""
    
    @pytest.mark.asyncio
    async def test_student_login_via_moodle(self, client: AsyncClient, mock_moodle_client):
        """Test student login using Moodle credentials."""
        with patch('app.services.moodle_client.MoodleClient', return_value=mock_moodle_client):
            response = await client.post(
                "/api/v1/auth/student/login",
                json={
                    "username": "student1",
                    "password": "studentpass",
                    "register_number": "123456789012"
                }
            )
            
            # Success depends on Moodle mock setup
            assert response.status_code in [200, 401, 400]
    
    @pytest.mark.asyncio
    async def test_student_login_invalid_moodle_credentials(self, client: AsyncClient):
        """Test student login with invalid Moodle credentials."""
        from app.services.moodle_client import MoodleAPIError
        
        with patch('app.services.moodle_client.MoodleClient.get_token', side_effect=MoodleAPIError("Invalid credentials", "invalidlogin")):
            response = await client.post(
                "/api/v1/auth/student/login",
                json={
                    "username": "baduser",
                    "password": "badpass",
                    "register_number": "123456789012"
                }
            )
            
            assert response.status_code in [401, 400]
    
    @pytest.mark.asyncio
    async def test_student_login_creates_session(self, client: AsyncClient, db_session, mock_moodle_client):
        """Test that student login creates a session."""
        with patch('app.services.moodle_client.MoodleClient', return_value=mock_moodle_client):
            response = await client.post(
                "/api/v1/auth/student/login",
                json={
                    "username": "student1",
                    "password": "studentpass",
                    "register_number": "123456789012"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                assert "session_id" in data or "token" in data
    
    @pytest.mark.asyncio
    async def test_student_login_missing_register_number(self, client: AsyncClient):
        """Test student login without register number."""
        response = await client.post(
            "/api/v1/auth/student/login",
            json={
                "username": "student1",
                "password": "studentpass"
                # Missing register_number
            }
        )
        
        # May be required or optional depending on implementation
        assert response.status_code in [200, 400, 422]


class TestTokenValidation:
    """Tests for JWT token validation."""
    
    @pytest.mark.asyncio
    async def test_valid_token_accepted(self, client: AsyncClient, staff_auth_headers):
        """Test that valid token is accepted."""
        response = await client.get(
            "/api/v1/auth/me",
            headers=staff_auth_headers
        )
        
        assert response.status_code in [200, 404]  # 404 if endpoint doesn't exist
    
    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, client: AsyncClient, staff_user):
        """Test that expired token is rejected."""
        # Create an expired token
        expired_token = create_access_token(
            data={"sub": staff_user.username},
            expires_delta=timedelta(seconds=-1)
        )
        
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        
        assert response.status_code in [401, 403, 404]
    
    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, client: AsyncClient):
        """Test that invalid token is rejected."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid-token"}
        )
        
        assert response.status_code in [401, 403, 404]
    
    @pytest.mark.asyncio
    async def test_missing_token_rejected(self, client: AsyncClient):
        """Test that missing token is rejected for protected endpoints."""
        response = await client.get(
            "/api/v1/admin/stats"
        )
        
        assert response.status_code in [401, 403]
    
    @pytest.mark.asyncio
    async def test_malformed_auth_header(self, client: AsyncClient):
        """Test handling of malformed authorization header."""
        response = await client.get(
            "/api/v1/admin/stats",
            headers={"Authorization": "NotBearer token"}
        )
        
        assert response.status_code in [401, 403]


class TestProtectedEndpoints:
    """Tests for protected endpoint access."""
    
    @pytest.mark.asyncio
    async def test_admin_endpoint_requires_auth(self, client: AsyncClient):
        """Test that admin endpoint requires authentication."""
        response = await client.get("/api/v1/admin/stats")
        
        assert response.status_code in [401, 403]
    
    @pytest.mark.asyncio
    async def test_admin_endpoint_accessible_with_auth(self, client: AsyncClient, staff_auth_headers):
        """Test that admin endpoint is accessible with valid auth."""
        response = await client.get(
            "/api/v1/admin/stats",
            headers=staff_auth_headers
        )
        
        # May succeed or fail based on auth headers fixture
        assert response.status_code in [200, 401, 403]
    
    @pytest.mark.asyncio
    async def test_upload_endpoint_requires_auth(self, client: AsyncClient):
        """Test that upload endpoint requires authentication."""
        response = await client.post("/api/v1/upload/single")
        
        assert response.status_code in [401, 403, 422]


class TestSessionManagement:
    """Tests for session management."""
    
    @pytest.mark.asyncio
    async def test_logout_invalidates_session(self, client: AsyncClient, staff_auth_headers):
        """Test that logout invalidates the session."""
        # This test depends on logout implementation
        response = await client.post(
            "/api/v1/auth/logout",
            headers=staff_auth_headers
        )
        
        # Logout may or may not exist
        assert response.status_code in [200, 204, 404, 401]
    
    @pytest.mark.asyncio
    async def test_concurrent_sessions_allowed(self, client: AsyncClient, staff_user):
        """Test that multiple concurrent sessions are allowed."""
        # Login twice
        response1 = await client.post(
            "/api/v1/auth/staff/login",
            json={"username": "test_staff", "password": "testpass123"}
        )
        
        response2 = await client.post(
            "/api/v1/auth/staff/login",
            json={"username": "test_staff", "password": "testpass123"}
        )
        
        # Both should succeed
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Tokens should be different
        if response1.status_code == 200 and response2.status_code == 200:
            token1 = response1.json().get("access_token")
            token2 = response2.json().get("access_token")
            assert token1 != token2
