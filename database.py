#!/usr/bin/env python3
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from threading import Lock

logger = logging.getLogger(__name__)


class UserStatsDB:
    """Handles storage and retrieval of user statistics"""

    def __init__(self, db_file: str = 'user_stats.json'):
        self._db_file = Path(db_file)
        self._stats: Dict[int, Dict[str, Any]] = {}
        self._lock = Lock()
        self._load_stats()

    def _load_stats(self) -> None:
        """Load statistics from JSON file"""
        if not self._db_file.exists():
            logger.info(f"Stats database file not found, creating new one: {self._db_file}")
            self._stats = {}
            self._save_stats()
            return

        try:
            with open(self._db_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Convert string keys to int for user IDs
                self._stats = {int(k): v for k, v in data.items()}
            logger.info(f"Loaded statistics for {len(self._stats)} users")
        except Exception as e:
            logger.error(f"Failed to load statistics: {e}")
            self._stats = {}

    def _save_stats(self) -> None:
        """Save statistics to JSON file"""
        try:
            with self._lock:
                # Convert int keys to strings for JSON serialization
                data = {str(k): v for k, v in self._stats.items()}
                with open(self._db_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save statistics: {e}")

    def _init_user(self, user_id: int) -> None:
        """Initialize statistics for a new user"""
        if user_id not in self._stats:
            self._stats[user_id] = {
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
                'daily_stats': {}  # Track downloads per day
            }

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
        self._init_user(user_id)

        if success:
            # Update counters
            self._stats[user_id]['total_downloads'] += 1

            # Update quality-specific counter
            if quality in self._stats[user_id]['downloads_by_quality']:
                self._stats[user_id]['downloads_by_quality'][quality] += 1
            else:
                self._stats[user_id]['downloads_by_quality'][quality] = 1

            # Update total size
            size_mb = file_size_bytes / (1024 * 1024)
            self._stats[user_id]['total_size_mb'] += size_mb

            # Update last used timestamp
            self._stats[user_id]['last_used'] = datetime.now().isoformat()

            # Track daily statistics
            today = self._get_today_key()
            if 'daily_stats' not in self._stats[user_id]:
                self._stats[user_id]['daily_stats'] = {}

            if today not in self._stats[user_id]['daily_stats']:
                self._stats[user_id]['daily_stats'][today] = {
                    'downloads': 0,
                    'size_mb': 0.0,
                    'qualities': {}
                }

            self._stats[user_id]['daily_stats'][today]['downloads'] += 1
            self._stats[user_id]['daily_stats'][today]['size_mb'] += size_mb

            if quality not in self._stats[user_id]['daily_stats'][today]['qualities']:
                self._stats[user_id]['daily_stats'][today]['qualities'][quality] = 0
            self._stats[user_id]['daily_stats'][today]['qualities'][quality] += 1

            # Add to download history (keep last 10)
            history_entry = {
                'timestamp': datetime.now().isoformat(),
                'quality': quality,
                'size_mb': round(size_mb, 2),
                'url': url[:50] + '...' if len(url) > 50 else url
            }

            self._stats[user_id]['download_history'].insert(0, history_entry)
            self._stats[user_id]['download_history'] = self._stats[user_id]['download_history'][:10]

            logger.info(f"Recorded download for user {user_id}: {quality}, {size_mb:.2f}MB")

        self._save_stats()

    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Get statistics for a specific user"""
        self._init_user(user_id)
        return self._stats[user_id].copy()

    def get_daily_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get daily download statistics for the last N days (admin function)"""
        from datetime import timedelta

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
        for user_id, user_stats in self._stats.items():
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
        return self._stats.copy()

    def get_total_users(self) -> int:
        """Get total number of users who have used the bot"""
        return len(self._stats)

    def get_global_stats(self) -> Dict[str, Any]:
        """Get global statistics across all users"""
        total_downloads = sum(user['total_downloads'] for user in self._stats.values())
        total_size_mb = sum(user['total_size_mb'] for user in self._stats.values())

        # Aggregate downloads by quality
        quality_totals = {
            'hd': 0,
            '720p': 0,
            '480p': 0,
            'audio': 0
        }

        for user in self._stats.values():
            for quality, count in user['downloads_by_quality'].items():
                if quality in quality_totals:
                    quality_totals[quality] += count

        return {
            'total_users': len(self._stats),
            'total_downloads': total_downloads,
            'total_size_mb': round(total_size_mb, 2),
            'downloads_by_quality': quality_totals
        }

    def delete_user_data(self, user_id: int) -> bool:
        """Delete all data for a specific user (GDPR compliance)"""
        if user_id in self._stats:
            del self._stats[user_id]
            self._save_stats()
            logger.info(f"Deleted all data for user {user_id}")
            return True
        return False

    def get_user_rank(self, user_id: int) -> int:
        """Get user's rank by total downloads"""
        self._init_user(user_id)
        user_downloads = self._stats[user_id]['total_downloads']

        # Count how many users have more downloads
        rank = 1
        for uid, stats in self._stats.items():
            if uid != user_id and stats['total_downloads'] > user_downloads:
                rank += 1

        return rank

    def get_top_users(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top users by download count"""
        sorted_users = sorted(
            self._stats.items(),
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
