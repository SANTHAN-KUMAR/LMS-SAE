"""
Dynamic Subject Discovery Service

Implements a hybrid approach for resolving subject codes to Moodle assignment IDs:
1. In-memory cache (fast, TTL-based)
2. Database lookup (persistent)
3. Dynamic Moodle API discovery (real-time)
4. Hardcoded config fallback (last resort)

This ensures maximum flexibility while maintaining performance and reliability.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import SubjectMapping
from app.services.moodle_client import MoodleClient, MoodleAPIError
from app.core.config import settings
from app.core.cache import subject_cache

logger = logging.getLogger(__name__)


class SubjectDiscoveryService:
    """
    Hybrid subject discovery with multiple fallback layers.
    
    Resolution Order:
    1. In-memory cache (sub-millisecond)
    2. Database lookup (fast)
    3. Dynamic Moodle API discovery (real-time search)
    4. Hardcoded config fallback (last resort)
    
    Successfully discovered mappings are automatically persisted to the database
    for future lookups, eliminating repeated API calls.
    """
    
    def __init__(self, db: AsyncSession):
        """
        Initialize the discovery service.
        
        Args:
            db: SQLAlchemy async session
        """
        self.db = db
    
    async def get_assignment_info(
        self,
        subject_code: str,
        user_token: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get complete assignment information for a subject code.
        
        Args:
            subject_code: Subject code to lookup (e.g., "19AI405")
            user_token: Optional Moodle token for dynamic discovery
            
        Returns:
            Dictionary with assignment_id, course_id, source, etc.
            None if not found in any layer.
        """
        subject_code = subject_code.upper().strip()
        cache_key = f"subject:{subject_code}"
        
        # Layer 1: Check in-memory cache
        cached = await subject_cache.get(cache_key)
        if cached:
            logger.debug(f"[Cache HIT] {subject_code} -> {cached.get('assignment_id')}")
            return cached
        
        # Layer 2: Check database
        db_mapping = await self._get_from_database(subject_code)
        if db_mapping:
            result = {
                "assignment_id": db_mapping.moodle_assignment_id,
                "course_id": db_mapping.moodle_course_id,
                "assignment_name": db_mapping.moodle_assignment_name,
                "subject_name": db_mapping.subject_name,
                "source": "database"
            }
            await subject_cache.set(cache_key, result)
            logger.debug(f"[Database HIT] {subject_code} -> {result.get('assignment_id')}")
            return result
        
        # Layer 3: Dynamic Moodle discovery (if token available)
        if user_token:
            discovered = await self._discover_from_moodle(subject_code, user_token)
            if discovered:
                # Persist to database for future lookups
                await self._save_discovered_mapping(
                    subject_code=subject_code,
                    course_id=discovered["course_id"],
                    assignment_id=discovered["assignment_id"],
                    assignment_name=discovered.get("assignment_name"),
                    source="moodle_discovery"
                )
                await subject_cache.set(cache_key, discovered)
                logger.info(f"[Moodle DISCOVERY] {subject_code} -> {discovered.get('assignment_id')}")
                return discovered
        
        # Layer 4: Fallback to config
        config_mapping = await self._get_from_config(subject_code)
        if config_mapping:
            # Save to DB for future (so we don't hit config every time)
            await self._save_discovered_mapping(
                subject_code=subject_code,
                course_id=config_mapping.get("course_id", 0),
                assignment_id=config_mapping["assignment_id"],
                assignment_name=None,
                source="config_fallback"
            )
            await subject_cache.set(cache_key, config_mapping)
            logger.info(f"[Config FALLBACK] {subject_code} -> {config_mapping.get('assignment_id')}")
            return config_mapping
        
        logger.warning(f"[NOT FOUND] No mapping found for subject code: {subject_code}")
        return None
    
    async def get_assignment_id(
        self,
        subject_code: str,
        user_token: Optional[str] = None
    ) -> Optional[int]:
        """
        Convenience method to get just the assignment ID.
        
        Args:
            subject_code: Subject code to lookup
            user_token: Optional Moodle token for dynamic discovery
            
        Returns:
            Assignment ID or None
        """
        info = await self.get_assignment_info(subject_code, user_token)
        return info.get("assignment_id") if info else None
    
    async def _get_from_database(self, subject_code: str) -> Optional[SubjectMapping]:
        """Query database for existing mapping."""
        result = await self.db.execute(
            select(SubjectMapping)
            .where(
                SubjectMapping.subject_code == subject_code,
                SubjectMapping.is_active == True
            )
        )
        return result.scalar_one_or_none()
    
    async def _discover_from_moodle(
        self,
        subject_code: str,
        token: str
    ) -> Optional[Dict[str, Any]]:
        """
        Dynamically discover assignment from Moodle API.
        
        Strategy:
        1. Get all courses the user is enrolled in
        2. For each course, check if course shortname/idnumber contains subject code
        3. Get assignments for matching courses
        4. Also check assignment names for subject code matches
        
        Args:
            subject_code: Subject code to find
            token: User's Moodle token
            
        Returns:
            Discovery result dict or None
        """
        client = MoodleClient(token=token)
        
        try:
            # Get user info and courses
            site_info = await client.get_site_info(token=token)
            user_id = site_info.get("userid")
            
            if not user_id:
                logger.warning("Could not get user ID from Moodle")
                return None
            
            # Get user's enrolled courses
            courses = await client.get_user_courses(user_id=user_id, token=token)
            
            if not courses:
                logger.debug(f"No courses found for user {user_id}")
                return None
            
            # First pass: Find courses matching the subject code
            matching_course_ids = []
            for course in courses:
                course_shortname = (course.get("shortname") or "").upper()
                course_idnumber = (course.get("idnumber") or "").upper()
                course_fullname = (course.get("fullname") or "").upper()
                
                if (subject_code in course_shortname or 
                    subject_code in course_idnumber or
                    subject_code in course_fullname):
                    matching_course_ids.append(course.get("id"))
                    logger.debug(f"Course match: {course.get('shortname')} (ID: {course.get('id')})")
            
            # If no direct course match, check all courses for assignment name matches
            if not matching_course_ids:
                matching_course_ids = [c.get("id") for c in courses if c.get("id")]
            
            if not matching_course_ids:
                return None
            
            # Get assignments for matching/all courses
            assignments_result = await client.get_assignments(
                course_ids=matching_course_ids,
                token=token
            )
            
            courses_with_assignments = assignments_result.get("courses", [])
            
            # Search for assignment matching subject code
            for course_data in courses_with_assignments:
                course_id = course_data.get("id")
                course_shortname = (course_data.get("shortname") or "").upper()
                course_idnumber = (course_data.get("idnumber") or "").upper()
                
                # Check if this course matches the subject code
                course_matches = (
                    subject_code in course_shortname or 
                    subject_code in course_idnumber
                )
                
                for assignment in course_data.get("assignments", []):
                    assignment_name = (assignment.get("name") or "").upper()
                    assignment_id = assignment.get("id")
                    
                    # Match if: course matches OR assignment name contains subject code
                    if course_matches or subject_code in assignment_name:
                        logger.info(
                            f"Discovered: {subject_code} -> "
                            f"Course {course_id}, Assignment {assignment_id} "
                            f"({assignment.get('name')})"
                        )
                        return {
                            "course_id": course_id,
                            "assignment_id": assignment_id,
                            "assignment_name": assignment.get("name"),
                            "source": "moodle_discovery"
                        }
            
            logger.debug(f"No matching assignment found in Moodle for {subject_code}")
            return None
            
        except MoodleAPIError as e:
            logger.warning(f"Moodle API error during discovery for {subject_code}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during Moodle discovery: {e}")
            return None
        finally:
            await client.close()
    
    async def _get_from_config(self, subject_code: str) -> Optional[Dict[str, Any]]:
        """Get from hardcoded config as last resort."""
        config_mapping = settings.get_subject_assignment_mapping()
        assignment_id = config_mapping.get(subject_code)
        
        if assignment_id:
            return {
                "assignment_id": assignment_id,
                "course_id": 0,  # Unknown from config
                "assignment_name": None,
                "source": "config"
            }
        return None
    
    async def _save_discovered_mapping(
        self,
        subject_code: str,
        course_id: int,
        assignment_id: int,
        assignment_name: Optional[str] = None,
        source: str = "discovery"
    ) -> SubjectMapping:
        """
        Persist discovered mapping to database.
        
        Args:
            subject_code: Subject code
            course_id: Moodle course ID
            assignment_id: Moodle assignment instance ID
            assignment_name: Optional assignment name
            source: Source of discovery for logging
            
        Returns:
            Created or updated SubjectMapping
        """
        existing = await self._get_from_database(subject_code)
        
        if existing:
            # Update existing mapping
            existing.moodle_course_id = course_id
            existing.moodle_assignment_id = assignment_id
            existing.moodle_assignment_name = assignment_name
            existing.last_verified_at = datetime.utcnow()
            logger.debug(f"Updated mapping for {subject_code} from {source}")
            await self.db.flush()
            return existing
        else:
            # Create new mapping
            new_mapping = SubjectMapping(
                subject_code=subject_code,
                moodle_course_id=course_id,
                moodle_assignment_id=assignment_id,
                moodle_assignment_name=assignment_name,
                is_active=True
            )
            self.db.add(new_mapping)
            await self.db.flush()
            logger.info(f"Created new mapping for {subject_code} from {source}")
            return new_mapping
    
    # ==========================================
    # Cache Management Methods
    # ==========================================
    
    @classmethod
    async def clear_cache(cls) -> int:
        """
        Clear all subject mappings from cache.
        
        Returns:
            Number of entries cleared
        """
        count = await subject_cache.clear()
        logger.info(f"Cleared {count} entries from subject cache")
        return count
    
    @classmethod
    async def invalidate_subject(cls, subject_code: str) -> bool:
        """
        Invalidate cache for a specific subject.
        
        Args:
            subject_code: Subject code to invalidate
            
        Returns:
            True if entry was found and deleted
        """
        subject_code = subject_code.upper().strip()
        cache_key = f"subject:{subject_code}"
        result = await subject_cache.delete(cache_key)
        if result:
            logger.info(f"Invalidated cache for {subject_code}")
        return result
    
    @classmethod
    async def get_cache_stats(cls) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache stats
        """
        return await subject_cache.stats()
    
    # ==========================================
    # Bulk Operations
    # ==========================================
    
    async def refresh_all_mappings(
        self,
        user_token: str
    ) -> Dict[str, Any]:
        """
        Refresh all mappings by re-discovering from Moodle.
        
        This is useful for syncing after Moodle course changes.
        
        Args:
            user_token: Moodle token with access to courses
            
        Returns:
            Summary of refresh results
        """
        # Get all active mappings
        result = await self.db.execute(
            select(SubjectMapping)
            .where(SubjectMapping.is_active == True)
        )
        mappings = list(result.scalars().all())
        
        results = {
            "total": len(mappings),
            "refreshed": 0,
            "unchanged": 0,
            "failed": 0,
            "details": []
        }
        
        for mapping in mappings:
            subject_code = mapping.subject_code
            old_assignment_id = mapping.moodle_assignment_id
            
            # Invalidate cache first
            await self.invalidate_subject(subject_code)
            
            # Try to discover
            discovered = await self._discover_from_moodle(subject_code, user_token)
            
            if discovered:
                new_assignment_id = discovered["assignment_id"]
                if new_assignment_id != old_assignment_id:
                    mapping.moodle_assignment_id = new_assignment_id
                    mapping.moodle_course_id = discovered["course_id"]
                    mapping.moodle_assignment_name = discovered.get("assignment_name")
                    mapping.last_verified_at = datetime.utcnow()
                    results["refreshed"] += 1
                    results["details"].append({
                        "subject_code": subject_code,
                        "status": "updated",
                        "old_id": old_assignment_id,
                        "new_id": new_assignment_id
                    })
                else:
                    mapping.last_verified_at = datetime.utcnow()
                    results["unchanged"] += 1
                    results["details"].append({
                        "subject_code": subject_code,
                        "status": "unchanged"
                    })
            else:
                results["failed"] += 1
                results["details"].append({
                    "subject_code": subject_code,
                    "status": "not_found"
                })
        
        await self.db.flush()
        logger.info(f"Mapping refresh complete: {results['refreshed']} updated, {results['unchanged']} unchanged, {results['failed']} failed")
        
        return results
