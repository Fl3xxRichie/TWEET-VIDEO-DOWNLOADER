import os
import re
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class Config:
    # Required settings
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is required")

    # Optional settings with defaults
    WEBHOOK_URL = os.getenv('WEBHOOK_URL', None)
    PORT = int(os.getenv('PORT', 8000))
    MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', 50))
    RATE_LIMIT_PER_HOUR = int(os.getenv('RATE_LIMIT_PER_HOUR', 5))

    # Referral Rewards Configuration
    REFERRAL_THRESHOLD_TIER_1 = 3    # Users with 3+ referrals
    REFERRAL_THRESHOLD_TIER_2 = 100  # Users with 100+ referrals
    DAILY_LIMIT_TIER_1 = 10          # Tier 1 Limit (10/hr ~ 100/day)
    DAILY_LIMIT_TIER_2 = 100         # Tier 2 Limit (100/hr ~ 1000/day)

    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    # Custom Start Screen Media
    START_MEDIA_URL = os.getenv('START_MEDIA_URL', None)

    # Donation Configuration (Optional - set your own addresses)
    DONATE_BTC = os.getenv('DONATE_BTC', None)
    DONATE_ETH = os.getenv('DONATE_ETH', None)
    DONATE_SOL = os.getenv('DONATE_SOL', None)
    DONATE_TRX = os.getenv('DONATE_TRX', None)
    DONATE_LTC = os.getenv('DONATE_LTC', None)
    DONATE_COFFEE_URL = os.getenv('DONATE_COFFEE_URL', None)
    DONATE_GITHUB_URL = os.getenv('DONATE_GITHUB_URL', None)

    # Admin configuration (optional)
    ADMIN_USER_ID = os.getenv('ADMIN_USER_ID', None)
    if ADMIN_USER_ID:
        try:
            ADMIN_USER_ID = int(str(ADMIN_USER_ID).strip())
        except ValueError:
            logger.warning(f"Invalid ADMIN_USER_ID: {ADMIN_USER_ID}, admin features disabled")
            ADMIN_USER_ID = None

    # Enhanced Redis URL parsing
    _redis_url = os.getenv('REDIS_URL')

    if not _redis_url:
        REDIS_URL = 'redis://localhost:6379'
        logger.warning("REDIS_URL not set, using default: redis://localhost:6379")
    elif ' ' in _redis_url:  # Handle command-style Redis URL
        # Extract host from command string
        match = re.search(r'-u\s+(\S+)', _redis_url)
        if match:
            REDIS_URL = match.group(1)
        else:
            REDIS_URL = 'redis://localhost:6379'
            logger.warning(f"Could not parse Redis URL from command: {_redis_url}, using default")
    elif 'upstash.io' in _redis_url:
        # Handle Upstash Redis URLs - ensure they use rediss:// for SSL
        if _redis_url.startswith('redis://') and not _redis_url.startswith('rediss://'):
            REDIS_URL = _redis_url.replace('redis://', 'rediss://', 1)
            logger.info("Converting Upstash Redis URL to use SSL (rediss://)")
        else:
            REDIS_URL = _redis_url
    elif not _redis_url.startswith(('redis://', 'rediss://', 'unix://')):
        # Assume it's a hostname or hostname:port
        if ':' not in _redis_url:
            REDIS_URL = f'redis://{_redis_url}:6379'
        else:
            REDIS_URL = f'redis://{_redis_url}'
    else:
        REDIS_URL = _redis_url

    # Validate critical settings
    @classmethod
    def validate(cls):
        """Validate configuration settings"""
        errors = []

        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN is required")

        if cls.BOT_TOKEN and not cls.BOT_TOKEN.startswith(('bot', 'Bot')):
            # Telegram bot tokens should start with a number followed by a colon
            if ':' not in cls.BOT_TOKEN:
                errors.append("BOT_TOKEN appears to be invalid (should contain ':')")

        if cls.PORT < 1 or cls.PORT > 65535:
            errors.append(f"PORT must be between 1 and 65535, got {cls.PORT}")

        if cls.MAX_FILE_SIZE_MB < 1 or cls.MAX_FILE_SIZE_MB > 2048:
            errors.append(f"MAX_FILE_SIZE_MB should be between 1 and 2048, got {cls.MAX_FILE_SIZE_MB}")

        if cls.RATE_LIMIT_PER_HOUR < 1:
            errors.append(f"RATE_LIMIT_PER_HOUR must be positive, got {cls.RATE_LIMIT_PER_HOUR}")

        if errors:
            raise ValueError(f"Configuration errors: {'; '.join(errors)}")

        logger.info(f"Configuration validated successfully:")
        logger.info(f"  - Bot Token: {'Set' if cls.BOT_TOKEN else 'Not set'}")
        logger.info(f"  - Webhook URL: {'Set' if cls.WEBHOOK_URL else 'Not set (polling mode)'}")
        logger.info(f"  - Port: {cls.PORT}")
        logger.info(f"  - Max file size: {cls.MAX_FILE_SIZE_MB}MB")
        logger.info(f"  - Rate limit: {cls.RATE_LIMIT_PER_HOUR}/hour")
        logger.info(f"  - Redis URL: {cls.REDIS_URL[:50]}{'...' if len(cls.REDIS_URL) > 50 else ''}")
        logger.info(f"  - Log level: {cls.LOG_LEVEL}")

# Validate configuration on import
try:
    Config.validate()
except Exception as e:
    logger.error(f"Configuration validation failed: {e}")
    raise
