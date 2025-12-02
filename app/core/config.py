"""
Examination Middleware - Configuration Module
Pydantic Settings for type-safe configuration management
"""

from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
import json


class Settings(BaseSettings):
    """Application Settings with validation"""
    
    # Application
    app_name: str = Field(default="Exam Submission Middleware")
    app_version: str = Field(default="1.0.0")
    debug: bool = Field(default=False)
    secret_key: str = Field(default="change-this-secret-key")
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=60)
    
    # Server
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000)
    reload: bool = Field(default=True)
    
    # PostgreSQL
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_user: str = Field(default="postgres")
    postgres_password: str = Field(default="")
    postgres_db: str = Field(default="exam_middleware")
    database_url: Optional[str] = None
    
    # Redis
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_password: str = Field(default="")
    redis_db: int = Field(default=0)
    redis_url: Optional[str] = None
    
    # Moodle
    moodle_base_url: str = Field(default="https://1844fdb23815.ngrok-free.app")
    moodle_ws_endpoint: str = Field(default="/webservice/rest/server.php")
    moodle_upload_endpoint: str = Field(default="/webservice/upload.php")
    moodle_token_endpoint: str = Field(default="/login/token.php")
    moodle_service: str = Field(default="moodle_mobile_app")
    moodle_admin_token: Optional[str] = None
    
    # File Storage
    upload_dir: str = Field(default="./uploads")
    max_file_size_mb: int = Field(default=50)
    allowed_extensions: str = Field(default=".pdf,.jpg,.jpeg,.png")
    
    # ML Service
    ml_service_url: str = Field(default="http://localhost:8501")
    ml_service_enabled: bool = Field(default=False)
    
    # Subject Mapping (Default values from your setup)
    subject_19ai405_assignment_id: int = Field(default=4)
    subject_19ai411_assignment_id: int = Field(default=6)
    subject_ml_assignment_id: int = Field(default=2)
    
    # Logging
    log_level: str = Field(default="INFO")
    log_file: str = Field(default="./logs/app.log")
    
    # CORS
    cors_origins: str = Field(default='["http://localhost:8000"]')
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    @property
    def database_url_computed(self) -> str:
        """Compute database URL if not provided"""
        if self.database_url:
            return self.database_url
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def database_url_sync(self) -> str:
        """Synchronous database URL for migrations"""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def redis_url_computed(self) -> str:
        """Compute Redis URL if not provided"""
        if self.redis_url:
            return self.redis_url
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    @property
    def moodle_webservice_url(self) -> str:
        """Full Moodle webservice URL"""
        return f"{self.moodle_base_url}{self.moodle_ws_endpoint}"
    
    @property
    def moodle_upload_url(self) -> str:
        """Full Moodle upload URL"""
        return f"{self.moodle_base_url}{self.moodle_upload_endpoint}"
    
    @property
    def moodle_token_url(self) -> str:
        """Full Moodle token URL"""
        return f"{self.moodle_base_url}{self.moodle_token_endpoint}"
    
    @property
    def allowed_extensions_list(self) -> List[str]:
        """Parse allowed extensions as list"""
        return [ext.strip() for ext in self.allowed_extensions.split(",")]
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins as list"""
        try:
            return json.loads(self.cors_origins)
        except json.JSONDecodeError:
            return ["http://localhost:8000"]
    
    @property
    def max_file_size_bytes(self) -> int:
        """Max file size in bytes"""
        return self.max_file_size_mb * 1024 * 1024
    
    def get_subject_assignment_mapping(self) -> dict:
        """Return subject code to assignment ID mapping"""
        return {
            "19AI405": self.subject_19ai405_assignment_id,
            "19AI411": self.subject_19ai411_assignment_id,
            "ML": self.subject_ml_assignment_id,
            "MACHINELEARNING": self.subject_ml_assignment_id,
        }


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Global settings instance
settings = get_settings()
