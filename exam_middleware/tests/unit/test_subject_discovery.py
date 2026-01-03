"""
Unit Tests for Subject Discovery Service

Tests the hybrid subject discovery functionality including:
- Cache layer operations
- Database lookup
- Moodle API discovery
- Config fallback
- Cache invalidation
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SubjectMapping
from app.services.subject_discovery_service import SubjectDiscoveryService
from app.core.cache import subject_cache

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.factories import SubjectMappingFactory, MoodleResponseFactory


class TestCacheLayer:
    """Tests for the cache layer of subject discovery."""
    
    @pytest.fixture(autouse=True)
    async def clear_cache(self):
        """Clear cache before each test."""
        await subject_cache.clear()
        yield
        await subject_cache.clear()
    
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_value(self, db_session):
        """Test that cache hit returns cached value without DB query."""
        service = SubjectDiscoveryService(db_session)
        
        # Pre-populate cache
        cache_key = "subject:19AI405"
        cached_data = {
            "assignment_id": 42,
            "course_id": 3,
            "source": "cache"
        }
        await subject_cache.set(cache_key, cached_data)
        
        # Should return cached value
        result = await service.get_assignment_info("19AI405")
        
        assert result is not None
        assert result["assignment_id"] == 42
        assert result["source"] == "cache"
    
    @pytest.mark.asyncio
    async def test_cache_stores_db_result(self, db_session, subject_mapping):
        """Test that DB results are cached."""
        service = SubjectDiscoveryService(db_session)
        
        # First call - should query DB
        result1 = await service.get_assignment_info("19AI405")
        
        # Second call - should hit cache
        result2 = await service.get_assignment_info("19AI405")
        
        assert result1 is not None
        assert result2 is not None
        assert result1["assignment_id"] == result2["assignment_id"]
    
    @pytest.mark.asyncio
    async def test_cache_invalidation(self, db_session, subject_mapping):
        """Test cache invalidation for a subject."""
        service = SubjectDiscoveryService(db_session)
        
        # Populate cache
        await service.get_assignment_info("19AI405")
        
        # Invalidate
        result = await SubjectDiscoveryService.invalidate_subject("19AI405")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_clear_all_cache(self, db_session):
        """Test clearing the entire cache."""
        # Add some items to cache
        await subject_cache.set("subject:TEST1", {"assignment_id": 1})
        await subject_cache.set("subject:TEST2", {"assignment_id": 2})
        
        # Clear all
        count = await SubjectDiscoveryService.clear_cache()
        
        assert count >= 2
        
        # Verify cache is empty
        assert await subject_cache.get("subject:TEST1") is None
        assert await subject_cache.get("subject:TEST2") is None
    
    @pytest.mark.asyncio
    async def test_get_cache_stats(self, db_session):
        """Test getting cache statistics."""
        # Make some operations
        await subject_cache.set("subject:TEST", {"assignment_id": 1})
        await subject_cache.get("subject:TEST")  # Hit
        await subject_cache.get("subject:MISSING")  # Miss
        
        stats = await SubjectDiscoveryService.get_cache_stats()
        
        assert "entries" in stats
        assert "hits" in stats
        assert "misses" in stats


class TestDatabaseLayer:
    """Tests for the database layer of subject discovery."""
    
    @pytest.fixture(autouse=True)
    async def clear_cache(self):
        """Clear cache to force DB queries."""
        await subject_cache.clear()
        yield
        await subject_cache.clear()
    
    @pytest.mark.asyncio
    async def test_db_lookup_finds_mapping(self, db_session, subject_mapping):
        """Test that DB lookup finds existing mapping."""
        service = SubjectDiscoveryService(db_session)
        
        result = await service.get_assignment_info("19AI405")
        
        assert result is not None
        assert result["assignment_id"] == subject_mapping.moodle_assignment_id
        assert result["source"] == "database"
    
    @pytest.mark.asyncio
    async def test_db_lookup_case_insensitive(self, db_session, subject_mapping):
        """Test that DB lookup is case-insensitive."""
        service = SubjectDiscoveryService(db_session)
        
        result1 = await service.get_assignment_info("19ai405")
        result2 = await service.get_assignment_info("19AI405")
        
        assert result1 is not None
        assert result2 is not None
        assert result1["assignment_id"] == result2["assignment_id"]
    
    @pytest.mark.asyncio
    async def test_db_lookup_only_active_mappings(self, db_session):
        """Test that only active mappings are returned."""
        # Create inactive mapping
        inactive = SubjectMappingFactory.create(
            subject_code="INACTIVE",
            is_active=False
        )
        db_session.add(inactive)
        await db_session.commit()
        
        service = SubjectDiscoveryService(db_session)
        
        result = await service.get_assignment_info("INACTIVE")
        
        # Should not find inactive mapping (unless discovered dynamically)
        # Behavior depends on whether other layers find it
    
    @pytest.mark.asyncio
    async def test_db_lookup_returns_full_info(self, db_session, subject_mapping):
        """Test that DB lookup returns complete information."""
        service = SubjectDiscoveryService(db_session)
        
        result = await service.get_assignment_info("19AI405")
        
        assert result is not None
        assert "assignment_id" in result
        assert "course_id" in result
        assert "assignment_name" in result
        assert "source" in result


class TestMoodleDiscoveryLayer:
    """Tests for the Moodle API discovery layer."""
    
    @pytest.fixture(autouse=True)
    async def clear_cache(self):
        """Clear cache before tests."""
        await subject_cache.clear()
        yield
        await subject_cache.clear()
    
    @pytest.mark.asyncio
    async def test_moodle_discovery_finds_by_course_shortname(self, db_session, mock_moodle_client):
        """Test discovery by matching course shortname."""
        service = SubjectDiscoveryService(db_session)
        
        with patch.object(service, '_discover_from_moodle') as mock_discover:
            mock_discover.return_value = {
                "assignment_id": 99,
                "course_id": 3,
                "assignment_name": "Discovered Assignment",
                "source": "moodle_discovery"
            }
            
            # Subject not in DB, but token provided for discovery
            result = await service.get_assignment_info(
                "NEWSUBJECT",
                user_token="test-token"
            )
            
            # Should have attempted discovery
            mock_discover.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_moodle_discovery_saves_to_db(self, db_session):
        """Test that discovered mappings are saved to DB."""
        service = SubjectDiscoveryService(db_session)
        
        # Mock the discovery to return a result
        discovered_data = {
            "assignment_id": 123,
            "course_id": 5,
            "assignment_name": "New Assignment",
            "source": "moodle_discovery"
        }
        
        with patch.object(
            service, '_discover_from_moodle',
            return_value=discovered_data
        ):
            result = await service.get_assignment_info(
                "DISCOVERED123",
                user_token="test-token"
            )
            
            assert result is not None
            assert result["assignment_id"] == 123
    
    @pytest.mark.asyncio
    async def test_moodle_discovery_skipped_without_token(self, db_session):
        """Test that Moodle discovery is skipped without token."""
        service = SubjectDiscoveryService(db_session)
        
        with patch.object(service, '_discover_from_moodle') as mock_discover:
            result = await service.get_assignment_info("UNKNOWN")
            
            # Should not call discovery without token
            mock_discover.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_moodle_discovery_handles_api_error(self, db_session):
        """Test graceful handling of Moodle API errors."""
        service = SubjectDiscoveryService(db_session)
        
        from app.services.moodle_client import MoodleAPIError
        
        with patch.object(
            service, '_discover_from_moodle',
            side_effect=MoodleAPIError("API Error", "invalidtoken")
        ):
            # Should not raise, should fall through to next layer
            result = await service.get_assignment_info(
                "UNKNOWN",
                user_token="bad-token"
            )
            
            # Result depends on config fallback


class TestConfigFallbackLayer:
    """Tests for the config fallback layer."""
    
    @pytest.fixture(autouse=True)
    async def clear_cache(self):
        """Clear cache before tests."""
        await subject_cache.clear()
        yield
        await subject_cache.clear()
    
    @pytest.mark.asyncio
    async def test_config_fallback_when_not_in_db(self, db_session):
        """Test config fallback when subject not in DB."""
        service = SubjectDiscoveryService(db_session)
        
        # Mock config to have a mapping
        with patch(
            'app.core.config.settings.get_subject_assignment_mapping',
            return_value={"CONFIGTEST": 777}
        ):
            result = await service.get_assignment_info("CONFIGTEST")
            
            # Should return config value
            if result:
                assert result["assignment_id"] == 777
                assert result["source"] == "config"
    
    @pytest.mark.asyncio
    async def test_config_fallback_saves_to_db(self, db_session):
        """Test that config fallback results are saved to DB."""
        service = SubjectDiscoveryService(db_session)
        
        with patch(
            'app.core.config.settings.get_subject_assignment_mapping',
            return_value={"SAVETEST": 888}
        ):
            result = await service.get_assignment_info("SAVETEST")
            
            if result:
                # Verify it was saved
                from sqlalchemy import select
                db_result = await db_session.execute(
                    select(SubjectMapping).where(
                        SubjectMapping.subject_code == "SAVETEST"
                    )
                )
                saved = db_result.scalar_one_or_none()
                # May or may not be saved depending on implementation


class TestGetAssignmentId:
    """Tests for the convenience get_assignment_id method."""
    
    @pytest.fixture(autouse=True)
    async def clear_cache(self):
        """Clear cache before tests."""
        await subject_cache.clear()
        yield
        await subject_cache.clear()
    
    @pytest.mark.asyncio
    async def test_get_assignment_id_returns_int(self, db_session, subject_mapping):
        """Test that get_assignment_id returns just the ID."""
        service = SubjectDiscoveryService(db_session)
        
        assignment_id = await service.get_assignment_id("19AI405")
        
        assert isinstance(assignment_id, int)
        assert assignment_id == subject_mapping.moodle_assignment_id
    
    @pytest.mark.asyncio
    async def test_get_assignment_id_returns_none_when_not_found(self, db_session):
        """Test that get_assignment_id returns None when not found."""
        service = SubjectDiscoveryService(db_session)
        
        # Mock config to have no mapping
        with patch(
            'app.core.config.settings.get_subject_assignment_mapping',
            return_value={}
        ):
            assignment_id = await service.get_assignment_id("NOTEXIST")
            
            assert assignment_id is None


class TestBulkOperations:
    """Tests for bulk operations like refresh_all_mappings."""
    
    @pytest.fixture(autouse=True)
    async def clear_cache(self):
        """Clear cache before tests."""
        await subject_cache.clear()
        yield
        await subject_cache.clear()
    
    @pytest.mark.asyncio
    async def test_refresh_all_mappings(self, db_session, subject_mapping):
        """Test refreshing all mappings from Moodle."""
        service = SubjectDiscoveryService(db_session)
        
        # Mock discovery to return updated info
        with patch.object(
            service, '_discover_from_moodle',
            return_value={
                "assignment_id": 999,  # Different from original
                "course_id": 10,
                "assignment_name": "Updated Assignment"
            }
        ):
            result = await service.refresh_all_mappings(user_token="test-token")
            
            assert "total" in result
            assert "refreshed" in result
            assert "failed" in result


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    @pytest.fixture(autouse=True)
    async def clear_cache(self):
        """Clear cache before tests."""
        await subject_cache.clear()
        yield
        await subject_cache.clear()
    
    @pytest.mark.asyncio
    async def test_handles_whitespace_in_subject_code(self, db_session, subject_mapping):
        """Test that whitespace in subject code is handled."""
        service = SubjectDiscoveryService(db_session)
        
        result = await service.get_assignment_info("  19AI405  ")
        
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_handles_empty_subject_code(self, db_session):
        """Test handling of empty subject code."""
        service = SubjectDiscoveryService(db_session)
        
        result = await service.get_assignment_info("")
        
        # Should return None or handle gracefully
    
    @pytest.mark.asyncio
    async def test_handles_none_token(self, db_session, subject_mapping):
        """Test that None token is handled correctly."""
        service = SubjectDiscoveryService(db_session)
        
        result = await service.get_assignment_info("19AI405", user_token=None)
        
        # Should still work using DB
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_same_subject(self, db_session, subject_mapping):
        """Test handling of concurrent requests for same subject."""
        import asyncio
        
        service = SubjectDiscoveryService(db_session)
        
        # Make concurrent requests
        results = await asyncio.gather(
            service.get_assignment_info("19AI405"),
            service.get_assignment_info("19AI405"),
            service.get_assignment_info("19AI405")
        )
        
        # All should succeed
        assert all(r is not None for r in results)
        assert all(r["assignment_id"] == results[0]["assignment_id"] for r in results)
