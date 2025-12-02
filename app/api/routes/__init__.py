"""
API Routes initialization
"""

from app.api.routes.auth import router as auth_router
from app.api.routes.upload import router as upload_router
from app.api.routes.student import router as student_router
from app.api.routes.admin import router as admin_router
from app.api.routes.health import router as health_router

__all__ = [
    "auth_router",
    "upload_router",
    "student_router",
    "admin_router",
    "health_router",
]
