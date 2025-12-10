#!/usr/bin/env python3
import os
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import redis
from config import Config

logger = logging.getLogger(__name__)

# Environment prefix to separate local and production data
ENV = os.getenv('ENVIRONMENT', 'development')


class RedisStatsDB:
    """Redis-based connection for stats storage"""

    def __init__(self):
        self._redis_client = None
        self._connect_redis()

    def _connect_redis(self):
        """Establishes connection to Redis."""
        try:
            logger.info(f"Connecting to Redis for stats storage...")
            redis_url = Config.REDIS_URL

            # Handle Upstash Redis URLs which often need SSL
            if 'upstash.io' in redis_url:
                if not redis_url.startswith('rediss://'):
                    redis_url = redis_url.replace('redis://', 'rediss://')

                self._redis_client = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    ssl_cert_reqs=None,
                    socket_connect_timeout=10,
                    socket_timeout=10,
                    retry_on_timeout=True
                )
            else:
                self._redis_client = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=10,
                    socket_timeout=10
                )

            # Test the connection
            self._redis_client.ping()
            logger.info("Successfully connected to Redis for stats storage.")

        except redis.exceptions.ConnectionError as e:
            logger.error(f"Could not connect to Redis for stats: {e}")
            self._redis_client = None
        except Exception as e:
            logger.error(f"Unexpected Redis connection error: {e}")
            self._redis_client = None

    @property
    def client(self):
        return self._redis_client

    @property
    def connected(self):
        return self._redis_client is not None


# Global Redis connection for stats
_redis_stats_db = RedisStatsDB()


class UserStatsDB:
    """Handles storage and retrieval of user statistics using Redis"""

    # Use environment-prefixed keys to separate local and production
    STATS_KEY_PREFIX = f"user_stats:{ENV}:"

    def __init__(self):
        self._redis = _redis_stats_db.client
        self._memory_fallback: Dict[int, Dict[str, Any]] = {}

        if not self._redis:
            logger.warning("Redis not available, using in-memory fallback for stats (NOT PERSISTENT)")
        else:
            logger.info(f"User stats DB initialized with ENV={ENV}, prefix={self.STATS_KEY_PREFIX}")

    def _get_key(self, user_id: int) -> str:
        """Generate Redis key for user stats"""
        return f"{self.STATS_KEY_PREFIX}{user_id}"

    def _get_user_stats_from_redis(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Load user stats from Redis"""
        if not self._redis:
            return self._memory_fallback.get(user_id)

        try:
            data = self._redis.get(self._get_key(user_id))
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Error loading stats for user {user_id}: {e}")
            return self._memory_fallback.get(user_id)

    def _save_user_stats_to_redis(self, user_id: int, stats: Dict[str, Any]) -> bool:
        """Save user stats to Redis"""
        if not self._redis:
            self._memory_fallback[user_id] = stats
            return True

        try:
            self._redis.set(self._get_key(user_id), json.dumps(stats))
            return True
        except Exception as e:
            logger.error(f"Error saving stats for user {user_id}: {e}")
            self._memory_fallback[user_id] = stats
            return False

    def _init_user(self, user_id: int) -> Dict[str, Any]:
        """Initialize statistics for a new user or return existing"""
        stats = self._get_user_stats_from_redis(user_id)
        if stats is None:
            stats = {
                'total_downloads': 0,
                'downloads_by_quality': {
                    'hd': 0,
                    '720p': 0,
                    '480p': 0,
                    'audio': 0
                },
                'first_used': datetime.now().isoformat(),
                'last_used': datetime.now().isoformat(),
                'total_size_mb': 0.0,
                'download_history': [],
                'daily_stats': {}
            }
            self._save_user_stats_to_redis(user_id, stats)
        return stats

    def _get_today_key(self) -> str:
        """Get today's date as a key (YYYY-MM-DD)"""
        return datetime.now().strftime('%Y-%m-%d')

    def record_download(
        self,
        user_id: int,
        quality: str,
        file_size_bytes: int = 0,
        url: str = "",
        success: bool = True
    ) -> None:
        """Record a download event for a user"""
        stats = self._init_user(user_id)

        if success:
            # Update counters
            stats['total_downloads'] += 1

            # Update quality-specific counter
            if quality in stats['downloads_by_quality']:
                stats['downloads_by_quality'][quality] += 1
            else:
                stats['downloads_by_quality'][quality] = 1

            # Update total size
            size_mb = file_size_bytes / (1024 * 1024)
            stats['total_size_mb'] += size_mb

            # Update last used timestamp
            stats['last_used'] = datetime.now().isoformat()

            # Track daily statistics
            today = self._get_today_key()
            if 'daily_stats' not in stats:
                stats['daily_stats'] = {}

            if today not in stats['daily_stats']:
                stats['daily_stats'][today] = {
                    'downloads': 0,
                    'size_mb': 0.0,
                    'qualities': {}
                }

            stats['daily_stats'][today]['downloads'] += 1
            stats['daily_stats'][today]['size_mb'] += size_mb

            if quality not in stats['daily_stats'][today]['qualities']:
                stats['daily_stats'][today]['qualities'][quality] = 0
            stats['daily_stats'][today]['qualities'][quality] += 1

            # Add to download history (keep last 10)
            history_entry = {
                'timestamp': datetime.now().isoformat(),
                'quality': quality,
                'size_mb': round(size_mb, 2),
                'url': url[:50] + '...' if len(url) > 50 else url
            }

            stats['download_history'].insert(0, history_entry)
            stats['download_history'] = stats['download_history'][:10]

            logger.info(f"Recorded download for user {user_id}: {quality}, {size_mb:.2f}MB")

        self._save_user_stats_to_redis(user_id, stats)

    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Get statistics for a specific user"""
        return self._init_user(user_id).copy()

    def _get_all_user_ids(self) -> List[int]:
        """Get all user IDs that have stats stored"""
        if not self._redis:
            return list(self._memory_fallback.keys())

        try:
            user_ids = []
            cursor = 0
            pattern = f"{self.STATS_KEY_PREFIX}*"

            while True:
                cursor, keys = self._redis.scan(cursor=cursor, match=pattern, count=100)
                for key in keys:
                    # Extract user ID from key
                    user_id_str = key.replace(self.STATS_KEY_PREFIX, "")
                    try:
                        user_ids.append(int(user_id_str))
                    except ValueError:
                        continue

                if cursor == 0:
                    break

            return user_ids
        except Exception as e:
            logger.error(f"Error getting all user IDs: {e}")
            return list(self._memory_fallback.keys())

    def _get_all_stats(self) -> Dict[int, Dict[str, Any]]:
        """Get all user stats (used internally)"""
        all_stats = {}
        for user_id in self._get_all_user_ids():
            stats = self._get_user_stats_from_redis(user_id)
            if stats:
                all_stats[user_id] = stats
        return all_stats

    def get_daily_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get daily download statistics for the last N days (admin function)"""
        daily_data = {}
        today = datetime.now()

        for i in range(days):
            date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
            daily_data[date] = {
                'downloads': 0,
                'active_users': 0,
                'size_mb': 0.0,
                'qualities': {'hd': 0, '720p': 0, '480p': 0, 'audio': 0}
            }

        # Aggregate data from all users
        all_stats = self._get_all_stats()
        for user_id, user_stats in all_stats.items():
            if 'daily_stats' in user_stats:
                for date, stats in user_stats['daily_stats'].items():
                    if date in daily_data:
                        daily_data[date]['downloads'] += stats.get('downloads', 0)
                        daily_data[date]['active_users'] += 1
                        daily_data[date]['size_mb'] += stats.get('size_mb', 0.0)

                        for quality, count in stats.get('qualities', {}).items():
                            if quality in daily_data[date]['qualities']:
                                daily_data[date]['qualities'][quality] += count

        return daily_data

    def get_all_stats(self) -> Dict[int, Dict[str, Any]]:
        """Get statistics for all users (admin function)"""
        return self._get_all_stats()

    def get_total_users(self) -> int:
        """Get total number of users who have used the bot"""
        return len(self._get_all_user_ids())

    def get_global_stats(self) -> Dict[str, Any]:
        """Get global statistics across all users"""
        all_stats = self._get_all_stats()

        total_downloads = sum(user['total_downloads'] for user in all_stats.values())
        total_size_mb = sum(user['total_size_mb'] for user in all_stats.values())

        # Aggregate downloads by quality
        quality_totals = {
            'hd': 0,
            '720p': 0,
            '480p': 0,
            'audio': 0
        }

        for user in all_stats.values():
            for quality, count in user['downloads_by_quality'].items():
                if quality in quality_totals:
                    quality_totals[quality] += count

        return {
            'total_users': len(all_stats),
            'total_downloads': total_downloads,
            'total_size_mb': round(total_size_mb, 2),
            'downloads_by_quality': quality_totals
        }

    def delete_user_data(self, user_id: int) -> bool:
        """Delete all data for a specific user (GDPR compliance)"""
        if not self._redis:
            if user_id in self._memory_fallback:
                del self._memory_fallback[user_id]
                logger.info(f"Deleted all data for user {user_id} (memory)")
                return True
            return False

        try:
            result = self._redis.delete(self._get_key(user_id))
            if result:
                logger.info(f"Deleted all data for user {user_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting user data: {e}")
            return False

    def get_user_rank(self, user_id: int) -> int:
        """Get user's rank by total downloads"""
        user_stats = self._init_user(user_id)
        user_downloads = user_stats['total_downloads']

        # Count how many users have more downloads
        rank = 1
        for uid in self._get_all_user_ids():
            if uid != user_id:
                other_stats = self._get_user_stats_from_redis(uid)
                if other_stats and other_stats['total_downloads'] > user_downloads:
                    rank += 1

        return rank

    def get_top_users(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top users by download count"""
        all_stats = self._get_all_stats()

        sorted_users = sorted(
            all_stats.items(),
            key=lambda x: x[1]['total_downloads'],
            reverse=True
        )

        return [
            {
                'user_id': user_id,
                'downloads': stats['total_downloads'],
                'total_size_mb': round(stats['total_size_mb'], 2)
            }
            for user_id, stats in sorted_users[:limit]
        ]


# Initialize global stats database
user_stats_db = UserStatsDB()
