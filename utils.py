import os
import time
import re
import json
import redis
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from config import Config
from pathlib import Path
import threading
from collections import defaultdict

logger = logging.getLogger(__name__)

class RedisCache:
    """Handles caching data in Redis."""
    def __init__(self):
        self._redis_client = None
        self._connect_redis()

    def _connect_redis(self):
        """Establishes connection to Redis."""
        try:
            logger.info(f"Connecting to Redis...")

            # Parse Redis URL to handle Upstash format
            redis_url = Config.REDIS_URL

            # Handle Upstash Redis URLs which often need SSL
            if 'upstash.io' in redis_url:
                # For Upstash, we need to use SSL
                if not redis_url.startswith('rediss://'):
                    redis_url = redis_url.replace('redis://', 'rediss://')

                self._redis_client = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    ssl_cert_reqs=None,  # Don't verify SSL certificates
                    socket_connect_timeout=10,
                    socket_timeout=10,
                    retry_on_timeout=True
                )
            else:
                # For local or other Redis instances
                self._redis_client = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=10,
                    socket_timeout=10
                )

            # Test the connection
            self._redis_client.ping()
            logger.info("Successfully connected to Redis.")

        except redis.exceptions.ConnectionError as e:
            logger.error(f"Could not connect to Redis: {e}")
            logger.info("Running without Redis - using in-memory fallback")
            self._redis_client = None
        except Exception as e:
            logger.error(f"Unexpected Redis connection error: {e}")
            self._redis_client = None

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """Set a key-value pair in Redis."""
        if not self._redis_client:
            logger.debug("Redis client not connected. Using in-memory storage.")
            # Fallback to in-memory storage
            return self._memory_set(key, value, ex)

        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            self._redis_client.set(key, value, ex=ex)
            return True
        except Exception as e:
            logger.error(f"Error setting key '{key}' in Redis: {e}")
            return self._memory_set(key, value, ex)

    def get(self, key: str) -> Optional[Any]:
        """Get a value from Redis."""
        if not self._redis_client:
            logger.debug("Redis client not connected. Using in-memory storage.")
            return self._memory_get(key)

        try:
            value = self._redis_client.get(key)
            if value is None:
                return None

            # Try to parse as JSON, fallback to string
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        except Exception as e:
            logger.error(f"Error getting key '{key}' from Redis: {e}")
            return self._memory_get(key)

    def delete(self, key: str) -> bool:
        """Delete a key from Redis."""
        if not self._redis_client:
            logger.debug("Redis client not connected. Using in-memory storage.")
            return self._memory_delete(key)

        try:
            self._redis_client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error deleting key '{key}' from Redis: {e}")
            return self._memory_delete(key)

    # Fallback in-memory storage
    _memory_store = {}
    _memory_expiry = {}

    def _memory_set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """Fallback in-memory set operation."""
        self._memory_store[key] = value
        if ex:
            self._memory_expiry[key] = time.time() + ex
        return True

    def _memory_get(self, key: str) -> Optional[Any]:
        """Fallback in-memory get operation."""
        # Check if expired
        if key in self._memory_expiry:
            if time.time() > self._memory_expiry[key]:
                self._memory_delete(key)
                return None

        return self._memory_store.get(key)

    def _memory_delete(self, key: str) -> bool:
        """Fallback in-memory delete operation."""
        self._memory_store.pop(key, None)
        self._memory_expiry.pop(key, None)
        return True

# Initialize Redis cache
redis_cache = RedisCache()

# Track temporary files
_temp_files: Dict[str, Dict[str, Any]] = defaultdict(dict)

def cleanup_file(filepath: str, delay: int = 600) -> None:
    """Schedule file for deletion after delay seconds"""
    def _cleanup():
        try:
            if os.path.exists(filepath):
                time.sleep(delay)
                os.remove(filepath)
                logger.info(f"Cleaned up temporary file: {filepath}")
                if filepath in _temp_files:
                    del _temp_files[filepath]
        except Exception as e:
            logger.error(f"Failed to cleanup file {filepath}: {e}")

    # Track the file and start cleanup thread
    _temp_files[filepath] = {
        'path': filepath,
        'created': datetime.now(),
        'size': os.path.getsize(filepath) if os.path.exists(filepath) else 0
    }
    threading.Thread(target=_cleanup, daemon=True).start()

def cleanup_all_temp_files() -> None:
    """Force cleanup of all tracked temporary files"""
    for filepath in list(_temp_files.keys()):
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                logger.info(f"Cleaned up temporary file: {filepath}")
            except Exception as e:
                logger.error(f"Failed to cleanup file {filepath}: {e}")
        if filepath in _temp_files:
            del _temp_files[filepath]

def validate_twitter_url(url: str) -> bool:
    """Validate if URL is a valid Twitter/X URL"""
    patterns = [
        r'https?://(?:www\.)?(?:twitter|x)\.com/.+/status/\d+',
        r'https?://(?:www\.)?(?:twitter|x)\.com/\w+/status/\d+',
        r'https?://(?:www\.)?(?:twitter|x)\.com/i/status/\d+'
    ]
    return any(re.match(pattern, url) for pattern in patterns)

def parse_tweet_id(url: str) -> Optional[str]:
    """Extract tweet ID from Twitter/X URL"""
    match = re.search(r'/status/(\d+)', url)
    return match.group(1) if match else None

def check_rate_limit(user_id: int) -> bool:
    """Check if user has exceeded rate limit using Redis or in-memory fallback"""
    now = datetime.now()
    key = f"rate_limit:{user_id}"
    user_data = redis_cache.get(key)

    if user_data and isinstance(user_data, dict):
        try:
            window_start = datetime.fromisoformat(user_data['window_start'])
            count = user_data['count']
        except (KeyError, ValueError):
            # Handle corrupted data
            window_start = now
            count = 0
    else:
        window_start = now
        count = 0

    # Reset if window expired
    if now - window_start > timedelta(hours=1):
        window_start = now
        count = 0

    # Check limit
    if count >= Config.RATE_LIMIT_PER_HOUR:
        logger.info(f"Rate limit exceeded for user {user_id}: {count}/{Config.RATE_LIMIT_PER_HOUR}")
        return False

    # Update count and save
    count += 1
    redis_cache.set(key, {
        'count': count,
        'window_start': window_start.isoformat()
    }, ex=3600)  # Expire after 1 hour

    logger.debug(f"Rate limit check for user {user_id}: {count}/{Config.RATE_LIMIT_PER_HOUR}")
    return True

class UserPreferences:
    """Handles storage and retrieval of user preferences using Redis"""

    PREFS_KEY_PREFIX = "user_prefs:"

    def __init__(self):
        # Memory fallback for when Redis is unavailable
        self._memory_prefs: Dict[int, Dict[str, Any]] = {}

    def _get_key(self, user_id: int) -> str:
        """Generate Redis key for user preferences"""
        return f"{self.PREFS_KEY_PREFIX}{user_id}"

    def _load_user_prefs(self, user_id: int) -> Dict[str, Any]:
        """Load preferences for a user from Redis"""
        prefs = redis_cache.get(self._get_key(user_id))
        if prefs and isinstance(prefs, dict):
            return prefs
        return self._memory_prefs.get(user_id, {})

    def _save_user_prefs(self, user_id: int, prefs: Dict[str, Any]) -> None:
        """Save preferences for a user to Redis"""
        redis_cache.set(self._get_key(user_id), prefs)
        self._memory_prefs[user_id] = prefs

    def get_preference(self, user_id: int, key: str, default: Any = None) -> Any:
        """Get a user preference"""
        prefs = self._load_user_prefs(user_id)
        return prefs.get(key, default)

    def set_preference(self, user_id: int, key: str, value: Any) -> None:
        """Set a user preference"""
        prefs = self._load_user_prefs(user_id)
        prefs[key] = value
        self._save_user_prefs(user_id, prefs)
        logger.debug(f"Set preference for user {user_id}: {key}={value}")

    def get_all_preferences(self, user_id: int) -> Dict[str, Any]:
        """Get all preferences for a user"""
        return self._load_user_prefs(user_id).copy()

    def delete_user_data(self, user_id: int) -> bool:
        """Delete all user data (GDPR compliance)"""
        try:
            redis_cache.delete(self._get_key(user_id))
            if user_id in self._memory_prefs:
                del self._memory_prefs[user_id]
            logger.info(f"Deleted preferences for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting user preferences: {e}")
            return False

# Initialize preferences storage
user_prefs = UserPreferences()


def format_file_size(size_bytes: int) -> str:
    """Convert bytes to human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def format_duration(seconds: int) -> str:
    """Convert seconds to human-readable duration"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}d {hours}h"


def get_quality_emoji(quality: str) -> str:
    """Get emoji for quality level"""
    quality_emojis = {
        'hd': '🎬',      # HD quality
        '720p': '📺',    # SD 720p
        '480p': '📱',    # SD 480p
        'audio': '🎵'    # Audio only
    }
    return quality_emojis.get(quality.lower(), '📥')


def format_timestamp(iso_timestamp: str) -> str:
    """Format ISO timestamp to readable format"""
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        now = datetime.now()
        diff = now - dt

        if diff.days == 0:
            if diff.seconds < 60:
                return "Just now"
            elif diff.seconds < 3600:
                minutes = diff.seconds // 60
                return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            else:
                hours = diff.seconds // 3600
                return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif diff.days == 1:
            return "Yesterday"
        elif diff.days < 7:
            return f"{diff.days} days ago"
        else:
            return dt.strftime("%b %d, %Y")
    except Exception as e:
        logger.error(f"Error formatting timestamp: {e}")
        return "Unknown"
