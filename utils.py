import os
import time
from typing import Optional, Dict, Any
import logging
from datetime import datetime, timedelta
from config import Config

# Rate limiting storage
_rate_limits: Dict[int, Dict[str, int]] = {}

logger = logging.getLogger(__name__)

import threading
from collections import defaultdict

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

import re

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
    """Check if user has exceeded rate limit"""
    now = datetime.now()
    user_data = _rate_limits.get(user_id, {'count': 0, 'window_start': now})

    # Reset if window expired
    if now - user_data['window_start'] > timedelta(hours=1):
        user_data = {'count': 0, 'window_start': now}

    # Check limit
    if user_data['count'] >= Config.RATE_LIMIT_PER_HOUR:
        return False

    # Update count
    user_data['count'] += 1
    _rate_limits[user_id] = user_data
    return True

import json
from pathlib import Path

class UserPreferences:
    """Handles storage and retrieval of user preferences"""
    def __init__(self):
        self._prefs_file = Path('user_prefs.json')
        self._prefs: Dict[int, Dict[str, Any]] = self._load_prefs()

    def _load_prefs(self) -> Dict[int, Dict[str, Any]]:
        """Load preferences from JSON file"""
        if not self._prefs_file.exists():
            return {}
        try:
            with open(self._prefs_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load preferences: {e}")
            return {}

    def _save_prefs(self) -> None:
        """Save preferences to JSON file"""
        try:
            with open(self._prefs_file, 'w') as f:
                json.dump(self._prefs, f)
        except Exception as e:
            logger.error(f"Failed to save preferences: {e}")

    def get_preference(self, user_id: int, key: str, default: Any = None) -> Any:
        """Get a user preference"""
        return self._prefs.get(user_id, {}).get(key, default)

    def set_preference(self, user_id: int, key: str, value: Any) -> None:
        """Set a user preference"""
        if user_id not in self._prefs:
            self._prefs[user_id] = {}
        self._prefs[user_id][key] = value
        self._save_prefs()

# Initialize preferences storage
user_prefs = UserPreferences()
