import os
import re
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    WEBHOOK_URL = os.getenv('WEBHOOK_URL', None)
    PORT = int(os.getenv('PORT', 8000))
    MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', 50))
    RATE_LIMIT_PER_HOUR = int(os.getenv('RATE_LIMIT_PER_HOUR', 5))
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    _redis_url = os.getenv('REDIS_URL')
    if not _redis_url:
        REDIS_URL = 'redis://localhost:6379'
    elif ' ' in _redis_url:  # Handle command-style Redis URL
        # Extract host from command string
        match = re.search(r'-u\s+(\S+)', _redis_url)
        REDIS_URL = match.group(1) if match else 'redis://localhost:6379'
    elif not _redis_url.startswith(('redis://', 'rediss://', 'unix://')):
        REDIS_URL = f'redis://{_redis_url}'
    else:
        REDIS_URL = _redis_url
