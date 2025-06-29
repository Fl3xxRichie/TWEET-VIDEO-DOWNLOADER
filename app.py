#!/usr/bin/env python3
import os
import time
import logging
import logging.handlers
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from datetime import datetime
from config import Config
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

# Setup logging
logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# File handler (rotating)
file_handler = logging.handlers.RotatingFileHandler(
    'app.log', maxBytes=10000000, backupCount=5
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

async def cleanup_scheduler():
    """Periodically clean up old files."""
    while True:
        try:
            video_downloader.cleanup_old_files(max_age_minutes=15)
        except Exception as e:
            logger.error(f"Error during scheduled cleanup: {e}")
        await asyncio.sleep(600)  # Sleep for 10 minutes

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handle startup and shutdown events.
    """
    # Startup
    cleanup_task = asyncio.create_task(cleanup_scheduler())
    logger.info("Started background cleanup task.")

    if Config.WEBHOOK_URL:
        try:
            await application.initialize()
            await application.bot.set_webhook(
                url=Config.WEBHOOK_URL,
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
            logger.info(f"Webhook set to {Config.WEBHOOK_URL}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")

    yield

    # Shutdown
    cleanup_task.cancel()
    logger.info("Stopped background cleanup task.")

    if Config.WEBHOOK_URL:
        try:
            await application.bot.delete_webhook()
            await application.shutdown()
            logger.info("Webhook deleted and application shut down")
        except Exception as e:
            logger.error(f"Failed to delete webhook: {e}")

app = FastAPI(lifespan=lifespan)

# Custom exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error"}
    )

# Logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(
        f"Request: {request.method} {request.url} "
        f"Status: {response.status_code} "
        f"Time: {process_time:.2f}s"
    )
    return response

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from utils import validate_twitter_url, check_rate_limit, user_prefs
from video_downloader import VideoDownloader

video_downloader = VideoDownloader()

from utils import validate_twitter_url, check_rate_limit, user_prefs, redis_cache
from video_downloader import VideoDownloader

video_downloader = VideoDownloader()

async def handle_quality_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quality selection callback"""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith('quality_'):
        # Set default quality preference
        quality = data.replace('quality_', '')
        user_prefs.set_preference(query.from_user.id, 'quality', quality)
        await query.edit_message_text(f"✅ Default quality set to {quality.upper()}")

    elif data.startswith('download_'):
        # Handle download with selected quality
        parts = data.split('_')
        quality = parts[1]
        url_id = parts[2]
        url = redis_cache.get(url_id) # Retrieve URL from Redis

        if not url:
            await query.edit_message_text("❌ Error: Original URL not found or expired. Please send the link again.")
            return

        # Save as last used quality
        user_prefs.set_preference(query.from_user.id, 'quality', quality)

        try:
            # Update message to show download starting
            await query.edit_message_text(f"⏳ Starting download in {quality.upper()} quality...")

            # Start the download with progress callback
            progress_message = await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="📥 Preparing download..."
            )

            async def progress_callback(progress_info):
                """Callback to update progress"""
                try:
                    if progress_info.get('status') == 'downloading':
                        percent = progress_info.get('_percent_str', 'N/A')
                        speed = progress_info.get('_speed_str', 'N/A')
                        eta = progress_info.get('_eta_str', 'N/A')

                        progress_text = f"📥 Downloading {quality.upper()}...\n"
                        progress_text += f"Progress: {percent}\n"
                        progress_text += f"Speed: {speed}\n"
                        progress_text += f"ETA: {eta}"

                        await progress_message.edit_text(progress_text)

                    elif progress_info.get('status') == 'finished':
                        await progress_message.edit_text("✅ Download completed! Preparing to send...")

                except Exception as e:
                    logger.error(f"Progress update error: {e}")

            # Perform the actual download
            result = await video_downloader.download_video(
                url,
                quality,
                progress_callback=progress_callback
            )

            if result['success']:
                # Send the video file
                await progress_message.edit_text("📤 Sending video...")

                with open(result['file_path'], 'rb') as video_file:
                    await context.bot.send_video(
                        chat_id=query.message.chat_id,
                        video=video_file,
                        caption=f"🎥 Downloaded in {quality.upper()} quality",
                        supports_streaming=True
                    )

                # Clean up
                try:
                    os.remove(result['file_path'])
                    await progress_message.delete()
                    logger.info(f"Successfully sent video to user {query.from_user.id}")
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")

            else:
                await progress_message.edit_text(f"❌ Download failed: {result.get('error', 'Unknown error')}")

        except Exception as e:
            logger.error(f"Download error: {e}")
            await query.edit_message_text(f"❌ Download failed: {str(e)}")

        finally:
            # Clean up URL from cache
            redis_cache.delete(url_id) # Delete URL from Redis

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        "Hi! I can download videos from Twitter/X. Just send me a URL.\n\n"
        "Available commands:\n"
        "/help - Show usage guide\n"
        "/quality - Set preferred video quality"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message with usage instructions"""
    await update.message.reply_text(
        "📌 How to use this bot:\n\n"
        "1. Send me a Twitter/X video URL\n"
        "2. Choose your preferred quality\n"
        "3. Wait for the download to complete\n\n"
        "Supported formats:\n"
        "- Single video tweets\n"
        "- HD (1080p), SD (720p/480p)\n"
        "- Audio only (MP3)\n\n"
        "Use /quality to set your default preference"
    )

async def quality_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Let user set preferred video quality"""
    keyboard = [
        [
            InlineKeyboardButton("HD (1080p)", callback_data="quality_hd"),
            InlineKeyboardButton("SD (720p)", callback_data="quality_720p"),
        ],
        [
            InlineKeyboardButton("SD (480p)", callback_data="quality_480p"),
            InlineKeyboardButton("Audio Only", callback_data="quality_audio"),
        ]
    ]
    await update.message.reply_text(
        "Select your preferred video quality:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming Twitter URLs"""
    user_id = update.message.from_user.id
    url = update.message.text

    if not validate_twitter_url(url):
        await update.message.reply_text("⚠️ Please send a valid Twitter/X URL")
        return

    if not check_rate_limit(user_id):
        await update.message.reply_text(
            f"⚠️ Rate limit exceeded. Please try again in an hour.\n"
            f"(Limit: {Config.RATE_LIMIT_PER_HOUR} downloads per hour)"
        )
        return

    # Get video info for size estimates
    video_info = await video_downloader.get_video_info(url)
    if not video_info:
        await update.message.reply_text("⚠️ Could not fetch video information")
        return

    # Get user's preferred quality if set
    preferred_quality = user_prefs.get_preference(user_id, 'quality')

    # Generate a unique ID for the URL to use in callbacks
    url_id = str(hash(url))  # Simple hash for unique ID
    redis_cache.set(url_id, url, ex=300) # Store the URL in Redis with a 5-minute expiration

    # Create buttons with accurate size estimates
    buttons = []
    for quality, label in [
        ('hd', 'HD (1080p)'),
        ('720p', 'SD (720p)'),
        ('480p', 'SD (480p)'),
        ('audio', 'Audio Only')
    ]:
        size_estimate = video_info['size_estimates'].get(quality, '~?')
        button_text = f"{label} ({size_estimate})"
        if quality == preferred_quality:
            button_text = f"⭐ {button_text} ⭐"
        buttons.append(
            InlineKeyboardButton(
                button_text,
                callback_data=f"download_{quality}_{url_id}"
            )
        )

    # Arrange buttons in 2x2 grid
    keyboard = [
        buttons[:2],
        buttons[2:]
    ]

    await update.message.reply_text(
        "Choose video quality (estimated sizes):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def setup_application() -> Application:
    """Configure and return Telegram application"""
    application = Application.builder().token(Config.BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quality", quality_command))

    # Message handler for URLs
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_url
    ))

    # Callback handler for quality selection
    application.add_handler(CallbackQueryHandler(handle_quality_selection))
    return application

@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint"""
    status = {
        "status": "ok",
        "bot": "running",
        "database": "ok",
        "last_checked": datetime.now().isoformat(),
        "version": "1.0.0"
    }

    # Add memory usage info
    try:
        import psutil
        process = psutil.Process()
        status.update({
            "memory_usage": f"{process.memory_info().rss / 1024 / 1024:.2f}MB",
            "cpu_usage": f"{process.cpu_percent()}%"
        })
    except ImportError:
        status["system_metrics"] = "unavailable"

    return status

application = setup_application()


@app.post("/")
async def handle_telegram_update(request: Request):
    """Handle incoming Telegram updates"""
    try:
        update_data = await request.json()
        update = Update.de_json(update_data, application.bot)
        await application.process_update(update)
        return JSONResponse(status_code=200, content={"status": "ok"})
    except Exception as e:
        logger.error(f"Error processing update: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error"})

def main():
    """Run the bot with webhook or polling"""
    if Config.WEBHOOK_URL:
        # In production, Uvicorn is started by the Docker command
        logger.info("Application will be started by Uvicorn in production.")
        pass
    else:
        # Polling mode for local development
        logger.info("WEBHOOK_URL not set, starting in polling mode.")
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )

if __name__ == "__main__":
    if Config.WEBHOOK_URL:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=Config.PORT
        )
    else:
        main()
