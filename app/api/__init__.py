"""
API module initialization
"""

from app.api.routes import (
    auth_router,
    upload_router,
    student_router,
    admin_router,
    health_router,
)

__all__ = [
    "auth_router",
    "upload_router",
    "student_router",
    "admin_router",
    "health_router",
]
