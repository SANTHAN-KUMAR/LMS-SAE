"""
SQLAlchemy Database Configuration and Session Management
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import AsyncAdaptedQueuePool
from typing import AsyncGenerator
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# Create async engine with proper connection pooling
# Note: Previously used NullPool which created a new connection for every request
# causing performance issues and potential connection exhaustion under load
engine = create_async_engine(
    settings.database_url_computed,
    echo=settings.debug,
    
    # Use proper connection pooling for production
    poolclass=AsyncAdaptedQueuePool,
    pool_size=10,           # Base number of connections to maintain
    max_overflow=20,        # Additional connections allowed under high load
    pool_timeout=30,        # Seconds to wait for connection before error
    pool_recycle=1800,      # Recycle connections after 30 minutes (prevents stale)
    pool_pre_ping=True,     # Validate connections before use (handles disconnects)
    
    future=True,
)

# Async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for models
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides database session
    
    Yields:
        AsyncSession: Database session
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database - create all tables
    """
    async with engine.begin() as conn:
        # Import all models to ensure they're registered
        from app.db import models  # noqa
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")


async def close_db() -> None:
    """
    Close database connections
    """
    await engine.dispose()
    logger.info("Database connections closed")
