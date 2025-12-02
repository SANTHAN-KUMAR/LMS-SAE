"""
Authentication API Routes
Handles staff and student authentication
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
import logging
import secrets

from app.db.database import get_db
from app.db.models import StaffUser, StudentSession
from app.schemas import (
    StaffLoginRequest,
    StaffLoginResponse,
    StudentLoginRequest,
    StudentLoginResponse,
    ErrorResponse,
)
from app.core.security import (
    create_access_token,
    decode_access_token,
    verify_password,
    get_password_hash,
    token_encryption,
)
from app.core.config import settings
from app.services.moodle_client import MoodleClient, MoodleAPIError
from app.services.artifact_service import ArtifactService

logger = logging.getLogger(__name__)

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/staff/login")


# ============================================
# Staff Authentication
# ============================================

@router.post("/staff/login", response_model=StaffLoginResponse)
async def staff_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Staff login endpoint
    
    Returns JWT token for accessing staff-only endpoints
    """
    # Find staff user
    result = await db.execute(
        select(StaffUser).where(StaffUser.username == form_data.username)
    )
    staff = result.scalar_one_or_none()
    
    if not staff or not verify_password(form_data.password, staff.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not staff.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled"
        )
    
    # Update last login
    staff.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    
    # Create access token
    access_token = create_access_token(
        data={
            "sub": str(staff.id),
            "username": staff.username,
            "type": "staff",
            "role": staff.role
        }
    )
    
    return StaffLoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        staff_id=staff.id,
        username=staff.username,
        role=staff.role
    )


async def get_current_staff(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> StaffUser:
    """
    Dependency to get current authenticated staff user
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    
    if payload.get("type") != "staff":
        raise credentials_exception
    
    staff_id = payload.get("sub")
    if staff_id is None:
        raise credentials_exception
    
    result = await db.execute(
        select(StaffUser).where(StaffUser.id == int(staff_id))
    )
    staff = result.scalar_one_or_none()
    
    if staff is None:
        raise credentials_exception
    
    if not staff.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled"
        )
    
    return staff


@router.post("/staff/register", response_model=dict)
async def register_staff(
    username: str,
    password: str,
    email: str,
    full_name: str = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new staff user (admin only in production)
    """
    # Check if username exists
    result = await db.execute(
        select(StaffUser).where(StaffUser.username == username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    # Create staff user
    staff = StaffUser(
        username=username,
        email=email,
        hashed_password=get_password_hash(password),
        full_name=full_name,
        role="staff",
        is_active=True
    )
    
    db.add(staff)
    await db.commit()
    await db.refresh(staff)
    
    return {"message": "Staff user created", "staff_id": staff.id}


# ============================================
# Student Authentication (via Moodle)
# ============================================

@router.post("/student/login", response_model=StudentLoginResponse)
async def student_login(
    credentials: StudentLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Student login using Moodle credentials
    
    This endpoint:
    1. Authenticates with Moodle to get a web service token
    2. Gets user information from Moodle
    3. Creates a local session
    4. Returns session information and pending papers
    """
    client = MoodleClient()
    
    try:
        # Step 1: Get Moodle token
        logger.info(f"Authenticating student: {credentials.username}")
        
        token_response = await client.get_token(
            username=credentials.username,
            password=credentials.password
        )
        
        moodle_token = token_response["token"]
        
        # Step 2: Get user info
        site_info = await client.get_site_info(token=moodle_token)
        
        moodle_user_id = site_info["userid"]
        moodle_username = site_info["username"]
        moodle_fullname = site_info.get("fullname", "")
        
        # Step 3: Create session
        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
        
        # Encrypt the token for storage
        encrypted_token = token_encryption.encrypt(moodle_token)
        
        # Store session
        session = StudentSession(
            session_id=session_id,
            moodle_user_id=moodle_user_id,
            moodle_username=moodle_username,
            moodle_fullname=moodle_fullname,
            encrypted_token=encrypted_token,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent", "")[:500],
            expires_at=expires_at
        )
        
        db.add(session)
        await db.commit()
        
        # Step 4: Get pending papers count
        artifact_service = ArtifactService(db)
        pending_papers = await artifact_service.get_pending_for_student(
            register_number=credentials.register_number,
            moodle_user_id=moodle_user_id
        )
        
        logger.info(f"Student {moodle_username} (reg: {credentials.register_number}) logged in. Pending papers: {len(pending_papers)}")
        
        return StudentLoginResponse(
            success=True,
            session_id=session_id,
            moodle_user_id=moodle_user_id,
            moodle_username=moodle_username,
            full_name=moodle_fullname,
            expires_at=expires_at,
            pending_submissions=len(pending_papers)
        )
        
    except MoodleAPIError as e:
        logger.warning(f"Moodle authentication failed for {credentials.username}: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.message}"
        )
    except Exception as e:
        logger.error(f"Unexpected error during student login: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )
    finally:
        await client.close()


async def get_current_student_session(
    session_id: str,
    db: AsyncSession = Depends(get_db)
) -> StudentSession:
    """
    Get and validate student session
    """
    result = await db.execute(
        select(StudentSession).where(StudentSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session"
        )
    
    if session.expires_at < datetime.now(timezone.utc):
        # Clean up expired session
        await db.delete(session)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired"
        )
    
    # Update last activity
    session.last_activity_at = datetime.now(timezone.utc)
    await db.commit()
    
    return session


def get_decrypted_token(session: StudentSession) -> str:
    """
    Decrypt the Moodle token from session
    """
    return token_encryption.decrypt(session.encrypted_token)


@router.post("/student/logout")
async def student_logout(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Logout student and invalidate session
    """
    result = await db.execute(
        select(StudentSession).where(StudentSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if session:
        await db.delete(session)
        await db.commit()
    
    return {"message": "Logged out successfully"}


@router.get("/student/session/{session_id}")
async def get_session_info(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get current session information
    """
    session = await get_current_student_session(session_id, db)
    
    return {
        "session_id": session.session_id,
        "moodle_user_id": session.moodle_user_id,
        "moodle_username": session.moodle_username,
        "full_name": session.moodle_fullname,
        "expires_at": session.expires_at.isoformat(),
        "is_valid": True
    }
