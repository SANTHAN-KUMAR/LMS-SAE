"""
Examination Middleware - Main FastAPI Application

This is the main entry point for the FastAPI application that bridges
scanned examination papers with Moodle LMS for student submissions.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.db.database import engine, Base
from app.api.routes import (
    auth_router,
    upload_router,
    student_router,
    admin_router,
    health_router,
)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("exam_middleware.log"),
    ],
)
# Set specific loggers to INFO to reduce SQLAlchemy noise
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events handler.
    Manages startup and shutdown events.
    """
    # Startup
    logger.info("Starting Examination Middleware...")
    
    # Create database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")
    
    # Ensure upload and storage directories exist
    upload_path = Path(settings.upload_dir)
    upload_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Upload directory: {upload_path.absolute()}")
    
    storage_path = Path("./storage")
    storage_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Storage directory: {storage_path.absolute()}")
    
    # Create templates directory
    templates_path = Path("app/templates")
    templates_path.mkdir(parents=True, exist_ok=True)
    
    # Create static directory
    static_path = Path("app/static")
    static_path.mkdir(parents=True, exist_ok=True)
    
    logger.info("Examination Middleware started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Examination Middleware...")
    await engine.dispose()
    logger.info("Database connections closed")


# Create FastAPI application
app = FastAPI(
    title="Examination Middleware",
    description="""
    ## Examination Paper Submission Middleware
    
    This API provides a secure bridge between scanned examination papers 
    and the Moodle LMS, enabling students to submit their answer sheets.
    
    ### Features:
    - **Staff Upload Portal**: Bulk upload of scanned answer sheets
    - **Student Portal**: View and submit assigned papers to Moodle
    - **Moodle Integration**: Direct submission to assignment modules
    - **Security**: JWT authentication, encrypted token storage
    - **Audit Trail**: Complete logging of all operations
    
    ### Workflow:
    1. Staff uploads scanned papers with standardized filenames
    2. System extracts student register number and subject code
    3. Students authenticate via Moodle credentials
    4. Students view their assigned papers and submit to Moodle
    5. System handles the complete submission workflow
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add GZip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "An internal server error occurred",
            "detail": str(exc) if settings.debug else None,
        },
    )


# Mount static files
try:
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
except Exception:
    logger.warning("Static files directory not found, skipping mount")

# Include API routers
app.include_router(
    health_router,
    prefix="/health",
    tags=["Health"],
)

app.include_router(
    auth_router,
    prefix="/auth",
    tags=["Authentication"],
)

app.include_router(
    upload_router,
    prefix="/upload",
    tags=["Upload"],
)

app.include_router(
    student_router,
    prefix="/student",
    tags=["Student"],
)

app.include_router(
    admin_router,
    prefix="/admin",
    tags=["Administration"],
)


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint - API information.
    """
    return {
        "name": "Examination Middleware API",
        "version": "1.0.0",
        "description": "Examination Paper Submission Middleware for Moodle LMS",
        "documentation": "/docs",
        "health_check": "/health",
        "endpoints": {
            "staff_login": "/auth/staff/login",
            "student_login": "/auth/student/login",
            "upload": "/upload/single",
            "bulk_upload": "/upload/bulk",
            "student_dashboard": "/student/dashboard",
            "submit": "/student/submit/{artifact_id}",
            "admin": "/admin/mappings",
        },
    }


# Templates setup
templates = Jinja2Templates(directory="app/templates")


@app.get("/portal/staff", tags=["Portal"], include_in_schema=False)
async def staff_portal(request: Request):
    """Staff upload portal page."""
    return templates.TemplateResponse(
        "staff_upload.html",
        {"request": request, "title": "Staff Upload Portal"},
    )


@app.get("/portal/student", tags=["Portal"], include_in_schema=False)
async def student_portal(request: Request):
    """Student submission portal page."""
    return templates.TemplateResponse(
        "student_portal.html",
        {"request": request, "title": "Student Submission Portal"},
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
