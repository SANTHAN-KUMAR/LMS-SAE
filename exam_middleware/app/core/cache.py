"""
Simple In-Memory Cache for Frequently Accessed Data

This module provides a thread-safe, TTL-based in-memory cache.
For production at scale, consider replacing with Redis.

Usage:
    from app.core.cache import cache, cached

    # Direct usage
    await cache.set("key", value, ttl=300)
    value = await cache.get("key")

    # Decorator usage
    @cached(ttl=300)
    async def expensive_operation(arg):
        ...
"""

from typing import Optional, Any, Callable, TypeVar, Dict
from datetime import datetime, timedelta
from functools import wraps
import asyncio
import hashlib
import json
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class SimpleCache:
    """
    Thread-safe in-memory cache with TTL support.
    
    Features:
    - TTL-based expiration
    - Async-safe operations with lock protection
    - Automatic cleanup of expired entries
    
    For production with multiple workers, use Redis instead.
    """
    
    def __init__(self, default_ttl: int = 300):
        """
        Initialize cache.
        
        Args:
            default_ttl: Default time-to-live in seconds (default: 5 minutes)
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._default_ttl = timedelta(seconds=default_ttl)
        self._lock = asyncio.Lock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0
        }
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value if exists and not expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        async with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if datetime.utcnow() < entry["expires_at"]:
                    self._stats["hits"] += 1
                    return entry["value"]
                else:
                    # Entry expired, remove it
                    del self._cache[key]
                    self._stats["misses"] += 1
            else:
                self._stats["misses"] += 1
        return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> None:
        """
        Set value with optional custom TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Optional TTL in seconds (uses default if not provided)
        """
        ttl_delta = timedelta(seconds=ttl) if ttl else self._default_ttl
        async with self._lock:
            self._cache[key] = {
                "value": value,
                "expires_at": datetime.utcnow() + ttl_delta,
                "created_at": datetime.utcnow()
            }
            self._stats["sets"] += 1
    
    async def delete(self, key: str) -> bool:
        """
        Delete a key.
        
        Args:
            key: Cache key to delete
            
        Returns:
            True if key existed and was deleted
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats["deletes"] += 1
                return True
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a pattern (prefix match).
        
        Args:
            pattern: Key prefix to match
            
        Returns:
            Number of keys deleted
        """
        async with self._lock:
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(pattern)]
            for key in keys_to_delete:
                del self._cache[key]
            self._stats["deletes"] += len(keys_to_delete)
            return len(keys_to_delete)
    
    async def clear(self) -> int:
        """
        Clear all entries.
        
        Returns:
            Number of entries cleared
        """
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count
    
    async def cleanup(self) -> int:
        """
        Remove expired entries.
        
        Returns:
            Number of entries removed
        """
        async with self._lock:
            now = datetime.utcnow()
            expired_keys = [
                k for k, v in self._cache.items() 
                if now >= v["expires_at"]
            ]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)
    
    async def stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache stats
        """
        async with self._lock:
            hit_rate = 0.0
            total_requests = self._stats["hits"] + self._stats["misses"]
            if total_requests > 0:
                hit_rate = self._stats["hits"] / total_requests
            
            return {
                "entries": len(self._cache),
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate": round(hit_rate, 4),
                "sets": self._stats["sets"],
                "deletes": self._stats["deletes"]
            }
    
    def cache_key(self, *args, **kwargs) -> str:
        """
        Generate cache key from arguments.
        
        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            MD5 hash of the arguments
        """
        # Handle non-serializable objects
        def _serialize(obj):
            if hasattr(obj, '__dict__'):
                return str(type(obj).__name__)
            return obj
        
        try:
            key_data = json.dumps(
                {"args": [_serialize(a) for a in args], "kwargs": {k: _serialize(v) for k, v in kwargs.items()}}, 
                sort_keys=True,
                default=str
            )
            return hashlib.md5(key_data.encode()).hexdigest()
        except (TypeError, ValueError):
            # Fallback for complex objects
            return hashlib.md5(str(args).encode() + str(kwargs).encode()).hexdigest()


# Global cache instance (5 minutes default TTL)
cache = SimpleCache(default_ttl=300)


def cached(ttl: int = 300, key_prefix: str = ""):
    """
    Decorator for caching async function results.
    
    Usage:
        @cached(ttl=300)
        async def expensive_db_query(user_id: int):
            ...
    
    Args:
        ttl: Time-to-live in seconds
        key_prefix: Optional prefix for cache keys
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Skip 'self' for cache key generation
            cache_args = args[1:] if args and hasattr(args[0], '__class__') else args
            
            # Generate cache key
            func_key = f"{key_prefix or func.__module__}.{func.__name__}"
            arg_key = cache.cache_key(*cache_args, **kwargs)
            key = f"{func_key}:{arg_key}"
            
            # Try to get from cache
            cached_value = await cache.get(key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {func.__name__}")
                return cached_value
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            
            # Only cache non-None results
            if result is not None:
                await cache.set(key, result, ttl)
            
            return result
        
        # Add cache invalidation method
        async def invalidate(*args, **kwargs):
            cache_args = args[1:] if args and hasattr(args[0], '__class__') else args
            func_key = f"{key_prefix or func.__module__}.{func.__name__}"
            arg_key = cache.cache_key(*cache_args, **kwargs)
            key = f"{func_key}:{arg_key}"
            return await cache.delete(key)
        
        wrapper.invalidate = invalidate
        wrapper.cache_key_prefix = f"{key_prefix or func.__module__}.{func.__name__}"
        
        return wrapper
    return decorator


# Subject mapping specific cache (longer TTL)
subject_cache = SimpleCache(default_ttl=1800)  # 30 minutes
