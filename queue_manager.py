#!/usr/bin/env python3
"""
Queue Manager for handling download requests using Redis
"""
import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from config import Config

logger = logging.getLogger(__name__)

# Environment prefix to separate local and production data
ENV = os.getenv('ENVIRONMENT', 'development')


class DownloadQueue:
    """Redis-based download queue for managing concurrent downloads"""

    # Use environment-based key prefixes to avoid conflicts between local and production
    QUEUE_KEY = f"download_queue:{ENV}:pending"
    PROCESSING_KEY = f"download_queue:{ENV}:processing"
    MAX_CONCURRENT = 3  # Maximum concurrent downloads

    def __init__(self):
        self._redis = None
        self._connect_redis()
        self._processing_count = 0
        logger.info(f"Queue manager initialized with ENV={ENV}, keys: {self.QUEUE_KEY}, {self.PROCESSING_KEY}")

    def _connect_redis(self):
        """Connect to Redis"""
        try:
            import redis
            redis_url = Config.REDIS_URL

            if 'upstash.io' in redis_url:
                if not redis_url.startswith('rediss://'):
                    redis_url = redis_url.replace('redis://', 'rediss://')

                self._redis = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    ssl_cert_reqs=None,
                    socket_connect_timeout=10,
                    socket_timeout=10
                )
            else:
                self._redis = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=10,
                    socket_timeout=10
                )

            self._redis.ping()
            logger.info("Queue manager connected to Redis")

        except Exception as e:
            logger.error(f"Queue manager failed to connect to Redis: {e}")
            self._redis = None

    def add_to_queue(
        self,
        user_id: int,
        chat_id: int,
        url: str,
        quality: str,
        message_id: int
    ) -> Dict[str, Any]:
        """Add a download request to the queue"""
        request = {
            'user_id': user_id,
            'chat_id': chat_id,
            'url': url,
            'quality': quality,
            'message_id': message_id,
            'added_at': datetime.now().isoformat(),
            'status': 'pending'
        }

        if not self._redis:
            # No queue, process immediately
            return {'queued': False, 'position': 0, 'request': request}

        try:
            # Check if user already has a request in queue
            queue_length = self._redis.llen(self.QUEUE_KEY)

            # Add to queue
            self._redis.rpush(self.QUEUE_KEY, json.dumps(request))
            position = queue_length + 1

            logger.info(f"Added download to queue for user {user_id}, position: {position}")

            return {
                'queued': True,
                'position': position,
                'request': request
            }

        except Exception as e:
            logger.error(f"Error adding to queue: {e}")
            return {'queued': False, 'position': 0, 'request': request}

    def get_next(self) -> Optional[Dict[str, Any]]:
        """Get the next request from the queue"""
        if not self._redis:
            logger.debug("get_next: No Redis connection")
            return None

        request_json = None
        try:
            # Check if we can process more
            processing_count = self._redis.llen(self.PROCESSING_KEY)
            queue_count = self._redis.llen(self.QUEUE_KEY)

            logger.info(f"get_next: queue={queue_count}, processing={processing_count}, max={self.MAX_CONCURRENT}")

            if processing_count >= self.MAX_CONCURRENT:
                logger.info(f"get_next: Too many processing ({processing_count} >= {self.MAX_CONCURRENT})")
                return None

            if queue_count == 0:
                return None

            # Pop from pending, push to processing
            request_json = self._redis.lpop(self.QUEUE_KEY)
            if not request_json:
                return None

            logger.info(f"get_next: Popped item from queue: {request_json[:100]}...")

            request = json.loads(request_json)
            request['status'] = 'processing'
            request['started_at'] = datetime.now().isoformat()

            self._redis.rpush(self.PROCESSING_KEY, json.dumps(request))

            logger.info(f"get_next: Got request for user {request.get('user_id')}")

            return request

        except json.JSONDecodeError as e:
            logger.error(f"Error decoding queue item: {e}, raw data: {request_json}")
            # Don't re-add corrupt data, just log and continue
            return None
        except Exception as e:
            logger.error(f"Error getting next from queue: {e}", exc_info=True)
            # If we popped an item but failed to process it, try to put it back
            if request_json:
                try:
                    self._redis.lpush(self.QUEUE_KEY, request_json)
                    logger.info("Re-added item to queue after error")
                except Exception as re_add_error:
                    logger.error(f"Failed to re-add item to queue: {re_add_error}")
            return None

    def mark_complete(self, user_id: int) -> bool:
        """Mark a request as complete and remove from processing"""
        if not self._redis:
            return True

        try:
            # Find and remove the user's request from processing
            processing = self._redis.lrange(self.PROCESSING_KEY, 0, -1)
            for item in processing:
                request = json.loads(item)
                if request['user_id'] == user_id:
                    self._redis.lrem(self.PROCESSING_KEY, 1, item)
                    logger.info(f"Marked download complete for user {user_id}")
                    return True
            return False

        except Exception as e:
            logger.error(f"Error marking complete: {e}")
            return False

    def get_queue_position(self, user_id: int) -> int:
        """Get user's position in the queue (0 if not in queue)"""
        if not self._redis:
            return 0

        try:
            queue = self._redis.lrange(self.QUEUE_KEY, 0, -1)
            for i, item in enumerate(queue):
                request = json.loads(item)
                if request['user_id'] == user_id:
                    return i + 1
            return 0

        except Exception as e:
            logger.error(f"Error getting queue position: {e}")
            return 0

    def get_queue_length(self) -> int:
        """Get total number of pending requests"""
        if not self._redis:
            return 0

        try:
            return self._redis.llen(self.QUEUE_KEY)
        except Exception as e:
            logger.error(f"Error getting queue length: {e}")
            return 0

    def is_user_in_queue(self, user_id: int) -> bool:
        """Check if user already has a request in the queue"""
        if not self._redis:
            return False

        try:
            queue = self._redis.lrange(self.QUEUE_KEY, 0, -1)
            processing = self._redis.lrange(self.PROCESSING_KEY, 0, -1)

            for item in queue + processing:
                request = json.loads(item)
                if request['user_id'] == user_id:
                    return True
            return False

        except Exception as e:
            logger.error(f"Error checking user in queue: {e}")
            return False


# Global queue instance
download_queue = DownloadQueue()
