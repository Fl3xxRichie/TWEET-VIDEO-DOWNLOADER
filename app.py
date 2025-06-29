#!/usr/bin/env python3
import os
import time
import asyncio
import logging
import logging.handlers
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from datetime import datetime
from config import Config
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import signal
import sys

# Setup logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

# File handler (rotating)
try:
    file_handler = logging.handlers.RotatingFileHandler(
        'app.log', maxBytes=10000000, backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    ))
    logger.addHandler(file_handler)
except Exception as e:
    logger.warning(f"Could not setup file logging: {e}")

# Global application instance
application = None
cleanup_task = None

async def cleanup_scheduler():
    """Periodically clean up old files."""
    while True:
        try:
            await asyncio.sleep(600)  # Sleep for 10 minutes
            video_downloader.cleanup_old_files(max_age_minutes=15)
            logger.info("Scheduled cleanup completed")
        except asyncio.CancelledError:
            logger.info("Cleanup scheduler cancelled")
            break
        except Exception as e:
            logger.error(f"Error during scheduled cleanup: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    global application, cleanup_task

    # Startup
    logger.info("Starting application lifespan...")

    try:
        # Initialize Telegram application
        application = setup_application()
        await application.initialize()
        logger.info("Telegram application initialized")

        # Start cleanup task
        cleanup_task = asyncio.create_task(cleanup_scheduler())
        logger.info("Started background cleanup task")

        # Set webhook if configured
        if Config.WEBHOOK_URL:
            try:
                # Delete any existing webhook first
                await application.bot.delete_webhook(drop_pending_updates=True)
                await asyncio.sleep(1)  # Small delay

                # Set new webhook
                await application.bot.set_webhook(
                    url=Config.WEBHOOK_URL,
                    allowed_updates=Update.ALL_TYPES,
                    drop_pending_updates=True
                )
                logger.info(f"Webhook set to {Config.WEBHOOK_URL}")

                # Verify webhook was set
                webhook_info = await application.bot.get_webhook_info()
                logger.info(f"Webhook info: {webhook_info}")

            except Exception as e:
                logger.error(f"Failed to set webhook: {e}")
                raise
        else:
            logger.info("No webhook URL configured, running in polling mode")

    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise

    yield

    # Shutdown
    logger.info("Starting application shutdown...")

    try:
        # Cancel cleanup task
        if cleanup_task:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped background cleanup task")

        # Clean up webhook and application
        if application and Config.WEBHOOK_URL:
            try:
                await application.bot.delete_webhook()
                logger.info("Webhook deleted")
            except Exception as e:
                logger.error(f"Failed to delete webhook: {e}")

        if application:
            try:
                await application.shutdown()
                logger.info("Application shut down")
            except Exception as e:
                logger.error(f"Failed to shutdown application: {e}")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

app = FastAPI(lifespan=lifespan)

# Enhanced exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception for {request.method} {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error", "error": str(exc)}
    )

# Enhanced logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    # Log request
    body = None
    if request.method == "POST":
        try:
            body = await request.body()
            logger.info(f"Incoming {request.method} {request.url} - Body size: {len(body)} bytes")
        except Exception as e:
            logger.error(f"Failed to read request body: {e}")

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

from utils import validate_twitter_url, check_rate_limit, user_prefs, redis_cache
from video_downloader import VideoDownloader

video_downloader = VideoDownloader()

async def handle_quality_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quality selection callback"""
    try:
        query = update.callback_query
        await query.answer()
        logger.info(f"Processing callback from user {query.from_user.id}: {query.data}")

        data = query.data

        if data.startswith('quality_'):
            # Set default quality preference
            quality = data.replace('quality_', '')
            user_prefs.set_preference(query.from_user.id, 'quality', quality)
            await query.edit_message_text(f"✅ Default quality set to {quality.upper()}")
            logger.info(f"User {query.from_user.id} set default quality to {quality}")

        elif data.startswith('download_'):
            # Handle download with selected quality
            parts = data.split('_')
            if len(parts) < 3:
                await query.edit_message_text("❌ Error: Invalid callback data format.")
                return

            quality = parts[1]
            url_id = parts[2]
            url = redis_cache.get(url_id)

            if not url:
                await query.edit_message_text("❌ Error: Original URL not found or expired. Please send the link again.")
                logger.warning(f"URL not found in cache for ID: {url_id}")
                return

            logger.info(f"Starting download for user {query.from_user.id}: {url} in {quality} quality")

            # Save as last used quality
            user_prefs.set_preference(query.from_user.id, 'quality', quality)

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
                error_msg = result.get('error', 'Unknown error')
                await progress_message.edit_text(f"❌ Download failed: {error_msg}")
                logger.error(f"Download failed for user {query.from_user.id}: {error_msg}")

            # Clean up URL from cache
            redis_cache.delete(url_id)

    except Exception as e:
        logger.error(f"Error in handle_quality_selection: {e}", exc_info=True)
        try:
            if 'query' in locals():
                await query.edit_message_text(f"❌ An error occurred: {str(e)}")
        except:
            pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    try:
        logger.info(f"Start command from user {update.effective_user.id}")
        await update.message.reply_text(
            "Hi! I can download videos from Twitter/X. Just send me a URL.\n\n"
            "Available commands:\n"
            "/help - Show usage guide\n"
            "/quality - Set preferred video quality"
        )
    except Exception as e:
        logger.error(f"Error in start command: {e}", exc_info=True)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message with usage instructions"""
    try:
        logger.info(f"Help command from user {update.effective_user.id}")
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
    except Exception as e:
        logger.error(f"Error in help command: {e}", exc_info=True)

async def quality_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Let user set preferred video quality"""
    try:
        logger.info(f"Quality command from user {update.effective_user.id}")
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
    except Exception as e:
        logger.error(f"Error in quality command: {e}", exc_info=True)

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming Twitter URLs"""
    try:
        user_id = update.message.from_user.id
        url = update.message.text.strip()
        logger.info(f"URL received from user {user_id}: {url}")

        if not validate_twitter_url(url):
            await update.message.reply_text("⚠️ Please send a valid Twitter/X URL")
            return

        if not check_rate_limit(user_id):
            await update.message.reply_text(
                f"⚠️ Rate limit exceeded. Please try again in an hour.\n"
                f"(Limit: {Config.RATE_LIMIT_PER_HOUR} downloads per hour)"
            )
            return

        # Send a processing message first
        processing_msg = await update.message.reply_text("🔍 Processing URL...")

        # Get video info for size estimates
        video_info = await video_downloader.get_video_info(url)
        if not video_info:
            await processing_msg.edit_text("⚠️ Could not fetch video information. Please check the URL and try again.")
            return

        # Get user's preferred quality if set
        preferred_quality = user_prefs.get_preference(user_id, 'quality')

        # Generate a unique ID for the URL to use in callbacks
        url_id = str(abs(hash(url + str(time.time()))))  # More unique hash
        redis_cache.set(url_id, url, ex=300)  # Store for 5 minutes

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

        await processing_msg.edit_text(
            "Choose video quality (estimated sizes):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        logger.info(f"Quality selection buttons sent to user {user_id}")

    except Exception as e:
        logger.error(f"Error in handle_url: {e}", exc_info=True)
        try:
            await update.message.reply_text("❌ An error occurred while processing your request. Please try again.")
        except:
            pass

def setup_application() -> Application:
    """Configure and return Telegram application"""
    logger.info("Setting up Telegram application...")

    application = Application.builder().token(Config.BOT_TOKEN).build()

    # Add error handler
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log the error and send a telegram message to notify the developer."""
        logger.error("Exception while handling an update:", exc_info=context.error)

        # Try to send error message to user if possible
        if update and hasattr(update, 'effective_chat'):
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ An unexpected error occurred. Please try again."
                )
            except:
                pass

    application.add_error_handler(error_handler)

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

    logger.info("Telegram application setup completed")
    return application

@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint"""
    status = {
        "status": "ok",
        "bot": "running" if application else "not_initialized",
        "webhook": "configured" if Config.WEBHOOK_URL else "not_configured",
        "redis": "connected" if redis_cache._redis_client else "disconnected",
        "last_checked": datetime.now().isoformat(),
        "version": "1.0.0"
    }

    # Test bot connection
    if application:
        try:
            bot_info = await application.bot.get_me()
            status["bot_username"] = bot_info.username
            status["bot_id"] = bot_info.id
        except Exception as e:
            status["bot_error"] = str(e)
            status["status"] = "degraded"

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

@app.get("/webhook-info")
async def webhook_info():
    """Get current webhook information"""
    if not application:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    try:
        webhook_info = await application.bot.get_webhook_info()
        return {
            "webhook_url": webhook_info.url,
            "pending_update_count": webhook_info.pending_update_count,
            "last_error_date": webhook_info.last_error_date,
            "last_error_message": webhook_info.last_error_message,
            "max_connections": webhook_info.max_connections,
            "allowed_updates": webhook_info.allowed_updates
        }
    except Exception as e:
        logger.error(f"Error getting webhook info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/")
async def handle_telegram_update(request: Request):
    """Handle incoming Telegram updates"""
    if not application:
        logger.error("Application not initialized, cannot process update")
        raise HTTPException(status_code=503, detail="Bot not initialized")

    try:
        # Log incoming update
        update_data = await request.json()
        logger.info(f"Received update: {update_data.get('update_id', 'unknown')}")

        # Process update
        update = Update.de_json(update_data, application.bot)
        if update:
            await application.process_update(update)
            logger.info(f"Successfully processed update {update.update_id}")
        else:
            logger.warning("Failed to parse update from JSON")

        return JSONResponse(status_code=200, content={"status": "ok"})

    except Exception as e:
        logger.error(f"Error processing update: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, shutting down...")
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main():
    """Run the bot with webhook or polling"""
    if Config.WEBHOOK_URL:
        logger.info("Application will be started by Uvicorn in webhook mode.")
    else:
        logger.info("WEBHOOK_URL not set, starting in polling mode.")
        global application
        application = setup_application()
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )

if __name__ == "__main__":
    if Config.WEBHOOK_URL:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=Config.PORT,
            log_level="info"
        )
    else:
        main()
