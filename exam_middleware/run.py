"""
Run script for Examination Middleware
Starts the FastAPI application with uvicorn
"""

import uvicorn
import os
import sys

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    """Run the FastAPI application."""
    print("=" * 60)
    print("  Examination Middleware - Starting Server")
    print("=" * 60)
    print()
    print("  Staff Portal:   http://localhost:8000/portal/staff")
    print("  Student Portal: http://localhost:8000/portal/student")
    print("  API Docs:       http://localhost:8000/docs")
    print("  Health Check:   http://localhost:8000/health")
    print()
    print("=" * 60)
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
