#!/usr/bin/env python3
import os
import time
import asyncio
import logging
import logging.handlers
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, BotCommand
from telegram.ext import ContextTypes
from datetime import datetime
from config import Config
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from contextlib import asynccontextmanager
from pathlib import Path
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
MEDIA_FILE_ID_CACHE = {}

async def safe_edit_message(message_or_query, text: str, reply_markup=None, parse_mode=None):
    """
    Safely edit a message, handling both text messages and media messages with captions.

    Args:
        message_or_query: Either a Message object or a CallbackQuery object
        text: The new text/caption content
        reply_markup: Optional InlineKeyboardMarkup
        parse_mode: Optional parse mode (e.g., 'Markdown')

    Returns:
        The edited message, or None if editing failed
    """
    try:
        # If it's a CallbackQuery, get the message from it
        if hasattr(message_or_query, 'message'):
            message = message_or_query.message
            is_callback = True
        else:
            message = message_or_query
            is_callback = False

        # Check if the message has media (photo, video, etc.)
        has_media = bool(
            getattr(message, 'photo', None) or
            getattr(message, 'video', None) or
            getattr(message, 'animation', None) or
            getattr(message, 'document', None) or
            getattr(message, 'audio', None)
        )

        if has_media:
            # Use edit_caption for media messages
            if is_callback:
                return await message_or_query.edit_message_caption(
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            else:
                return await message.edit_caption(
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
        else:
            # Use edit_text for text messages
            if is_callback:
                return await message_or_query.edit_message_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            else:
                return await message.edit_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
    except Exception as e:
        logger.warning(f"Failed to edit message: {e}")
        return None


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

# NOTE: Queue processor removed to reduce Redis API calls
# Downloads now process directly in handle_quality_selection

async def process_download(user_id: int, chat_id: int, url: str, quality: str, message_id: int = None, username: str = None, platform: str = None):
    """Execute the actual download for a user request"""

    try:
        if not application:
            logger.error("Application not initialized")
            return

        bot = application.bot
        logger.info(f"Starting ID-based download execution for user {user_id}")

        # Initial status update - always send a new text message for progress
        # This avoids issues with editing photo messages that have captions
        progress_message = await bot.send_message(
            chat_id=chat_id,
            text=f"🚀 Processing your download in {quality.upper()} quality..."
        )

        # Delete the old message with the photo/quality selection if possible
        if message_id:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Could not delete old message: {e}")

        async def progress_callback(progress_info):
            """Callback to update progress"""
            try:
                status = progress_info.get('status')

                if status == 'downloading':
                    percent = progress_info.get('_percent_str', 'N/A')
                    speed = progress_info.get('_speed_str', 'N/A')
                    eta = progress_info.get('_eta_str', 'N/A')

                    progress_text = f"📥 Downloading {quality.upper()}...\n"
                    progress_text += f"Progress: {percent}\n"
                    progress_text += f"Speed: {speed}\n"
                    progress_text += f"ETA: {eta}"

                    # Edit 'status' so we don't edit too often?
                    # yt-dlp calls frequently. app.py logic didn't seem to rate limit,
                    # maybe we should simple throttle here slightly but for now let's keep it simple
                    try:
                        await progress_message.edit_text(progress_text)
                    except:
                        pass # Ignore "message not modified" errors

                elif status == 'compressing':
                    target_mb = progress_info.get('target_mb', 45)
                    await progress_message.edit_text(f"🗜️ Compressing video to under {target_mb}MB...\nThis may take a moment.")

                elif status == 'finished':
                    await progress_message.edit_text("✅ Download completed! Processing...")

            except Exception as e:
                logger.error(f"Progress update error: {e}")

        # Perform the actual download
        # Note: We need to import video_downloader globally or access it if it's there
        # It seems accessed as 'video_downloader' in app.py generally

        result = await video_downloader.download_video(
            url,
            quality,
            progress_callback=progress_callback
        )

        if result['success']:
            file_path = result['file_path']

            # Check file size and compress if needed
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

            if file_size_mb > 49.0: # Telegram limit is 50MB
                await progress_message.edit_text(f"📏 File size ({file_size_mb:.1f}MB) exceeds limit. Compressing...")

                compress_result = await video_downloader.compress_video(
                    file_path,
                    target_size_mb=45.0,
                    progress_callback=progress_callback
                )

                if compress_result['success']:
                    file_path = compress_result['file_path']
                    logger.info(f"Compression successful: {compress_result.get('original_size_mb')} -> {compress_result.get('new_size_mb')} MB")
                else:
                    logger.warning(f"Compression failed: {compress_result.get('error')}")
                    # Try to send anyway if it failed? Or fail?
                    # If it's > 50MB sending will likely fail.

            # Send the video file
            await progress_message.edit_text("📤 Sending video...")

            try:
                with open(file_path, 'rb') as video_file:
                    await bot.send_video(
                        chat_id=chat_id,
                        video=video_file,
                        caption=f"🎥 Downloaded in {quality.upper()} quality",
                        supports_streaming=True,
                        read_timeout=120,
                        write_timeout=120,
                        connect_timeout=120,
                        pool_timeout=120
                    )

                # Statistics and Cleanup
                try:
                    stats_file_size = os.path.getsize(file_path)
                    user_stats_db.record_download(
                        user_id=user_id,
                        quality=quality,
                        file_size_bytes=stats_file_size,
                        url=url,
                        success=True,
                        username=username,
                        platform=platform
                    )
                except Exception as e:
                    logger.error(f"Stats error: {e}")

                os.remove(file_path)
                await progress_message.delete()
                logger.info(f"Successfully sent video to user {user_id}")

            except Exception as send_error:
                logger.error(f"Error sending video: {send_error}")
                await progress_message.edit_text(f"❌ Error sending video: {send_error}")
                if os.path.exists(file_path):
                    os.remove(file_path)

        else:
            error_msg = result.get('error', 'Unknown error')
            await progress_message.edit_text(f"❌ Download failed: {error_msg}")

    except Exception as e:
        logger.error(f"Error in process_download: {e}", exc_info=True)
        try:
             if progress_message:
                await progress_message.edit_text("❌ An unexpected error occurred during processing.")
        except:
            pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    global application, cleanup_task

    # Startup
    logger.info("Starting application lifespan...")
    polling_task = None

    try:
        # Initialize Telegram application
        application = setup_application()
        await application.initialize()
        logger.info("Telegram application initialized")

        # Start cleanup task
        cleanup_task = asyncio.create_task(cleanup_scheduler())
        logger.info("Started background cleanup task")

        # Set webhook if configured, otherwise start polling
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

                # Set bot menu commands
                commands = [
                    BotCommand("start", "Start the bot"),
                    BotCommand("help", "Get help and usage guide"),
                    BotCommand("settings", "Change video quality settings"),
                    BotCommand("stats", "View your download statistics"),
                    BotCommand("history", "View your download history"),
                    BotCommand("about", "About this bot")
                ]
                await application.bot.set_my_commands(commands)
                logger.info("Bot commands menu set")

                # Verify webhook was set
                webhook_info = await application.bot.get_webhook_info()
                logger.info(f"Webhook info: {webhook_info}")

            except Exception as e:
                logger.error(f"Failed to set webhook: {e}")
                raise
        else:
            # No webhook - start polling in background alongside web server
            logger.info("No webhook URL configured, starting polling mode alongside web server")
            await application.bot.delete_webhook(drop_pending_updates=True)

            # Set bot menu commands (polling mode)
            commands = [
                BotCommand("start", "Start the bot"),
                BotCommand("help", "Get help and usage guide"),
                BotCommand("settings", "Change video quality settings"),
                BotCommand("stats", "View your download statistics"),
                BotCommand("history", "View your download history"),
                BotCommand("about", "About this bot")
            ]
            await application.bot.set_my_commands(commands)
            logger.info("Bot commands menu set")

            await application.start()
            polling_task = asyncio.create_task(
                application.updater.start_polling(
                    drop_pending_updates=True,
                    allowed_updates=Update.ALL_TYPES
                )
            )
            logger.info("Polling started in background - Dashboard available at /dashboard")

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

        # Stop polling if it was running
        if polling_task:
            try:
                await application.updater.stop()
                await application.stop()
                logger.info("Polling stopped")
            except Exception as e:
                logger.error(f"Failed to stop polling: {e}")

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

from utils import (
    validate_twitter_url, validate_video_url, detect_platform, PLATFORM_PATTERNS,
    check_rate_limit, get_rate_limit_status, user_prefs, redis_cache,
    format_file_size, format_timestamp, get_quality_emoji
)
from video_downloader import VideoDownloader
from database import user_stats_db

video_downloader = VideoDownloader()

async def handle_quality_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quality selection callback"""
    try:
        query = update.callback_query
        await query.answer()
        logger.info(f"Processing callback from user {query.from_user.id}: {query.data}")

        data = query.data

        # Handle main menu navigation
        if data == 'menu_main':
            keyboard = [
                [
                    InlineKeyboardButton("📥 Download Video", callback_data="menu_download"),
                    InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings"),
                ],
                [
                    InlineKeyboardButton("📊 My Statistics", callback_data="menu_stats"),
                    InlineKeyboardButton("❓ Help", callback_data="menu_help"),
                ],
                [
                    InlineKeyboardButton("ℹ️ About", callback_data="menu_about"),
                ]
            ]
            await safe_edit_message(
                query,
                "👋 Welcome to Twitter/X Video Downloader!\n\n"
                "I can help you download videos from Twitter/X in various qualities.\n\n"
                "Choose an option below to get started:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        elif data == 'menu_download':
            await safe_edit_message(
                query,
                "📥 **How to Download Videos**\n\n"
                "1. Copy a Twitter/X video URL\n"
                "2. Send it to me\n"
                "3. Choose your preferred quality\n"
                "4. Wait for the download to complete\n\n"
                "Just paste any Twitter/X video link to get started!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="menu_main")]]),
                parse_mode='Markdown'
            )
            return

        elif data == 'menu_settings':
            user_id = query.from_user.id
            current_quality = user_prefs.get_preference(user_id, 'quality', 'hd')

            settings_text = (
                "⚙️ **Settings**\n\n"
                f"**Current Default Quality:** {current_quality.upper()}\n\n"
                "Choose your preferred default quality:"
            )

            keyboard = [
                [
                    InlineKeyboardButton(
                        f"{'✅ ' if current_quality == 'hd' else ''}HD (1080p)",
                        callback_data="quality_hd"
                    ),
                    InlineKeyboardButton(
                        f"{'✅ ' if current_quality == '720p' else ''}SD (720p)",
                        callback_data="quality_720p"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        f"{'✅ ' if current_quality == '480p' else ''}SD (480p)",
                        callback_data="quality_480p"
                    ),
                    InlineKeyboardButton(
                        f"{'✅ ' if current_quality == '360p' else ''}SD (360p)",
                        callback_data="quality_360p"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        f"{'✅ ' if current_quality == 'audio' else ''}Audio Only",
                        callback_data="quality_audio"
                    ),
                ],
                [
                    InlineKeyboardButton("« Back to Menu", callback_data="menu_main"),
                ]
            ]

            await safe_edit_message(
                query,
                settings_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return

        elif data == 'menu_stats':
            user_id = query.from_user.id
            stats = user_stats_db.get_user_stats(user_id)

            stats_text = "📊 **Your Download Statistics**\n\n"
            stats_text += f"📥 **Total Downloads:** {stats['total_downloads']}\n"

            if stats['total_downloads'] > 0:
                stats_text += f"\n**Quality Breakdown:**\n"
                for quality, count in stats['downloads_by_quality'].items():
                    if count > 0:
                        emoji = get_quality_emoji(quality)
                        percentage = (count / stats['total_downloads']) * 100
                        stats_text += f"{emoji} {quality.upper()}: {count} ({percentage:.1f}%)\n"

            total_size = stats['total_size_mb']
            if total_size >= 1024:
                size_str = f"{total_size / 1024:.2f} GB"
            else:
                size_str = f"{total_size:.2f} MB"
            stats_text += f"\n💾 **Total Data:** {size_str}\n"

            if stats['first_used']:
                stats_text += f"\n🗓️ **Member Since:** {format_timestamp(stats['first_used'])}\n"
            if stats['last_used']:
                stats_text += f"⏰ **Last Download:** {format_timestamp(stats['last_used'])}\n"

            if stats['download_history']:
                stats_text += f"\n**Recent Downloads:**\n"
                for i, download in enumerate(stats['download_history'][:5], 1):
                    emoji = get_quality_emoji(download['quality'])
                    stats_text += f"{i}. {emoji} {download['quality'].upper()} - {download['size_mb']} MB - {format_timestamp(download['timestamp'])}\n"

            rank = user_stats_db.get_user_rank(user_id)
            total_users = user_stats_db.get_total_users()
            stats_text += f"\n🏆 **Your Rank:** #{rank} out of {total_users} users\n"

            keyboard = [[InlineKeyboardButton("« Back to Menu", callback_data="menu_main")]]

            await safe_edit_message(
                query,
                stats_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return

        elif data == 'menu_help':
            help_text = (
                "❓ **Help & Usage Guide**\n\n"
                "**Single Video Download:**\n"
                "1. Send a Twitter/X video URL\n"
                "2. Choose your preferred quality\n"
                "3. Wait for the download to complete\n\n"
                "**📦 Batch Download (NEW!):**\n"
                "Send multiple URLs in one message!\n"
                "• All videos download in your default quality\n"
                "• Set quality first with /settings\n\n"
                "**Supported platforms:**\n"
                "• Twitter/X • Instagram Reels\n"
                "• TikTok • YouTube Shorts\n\n"
                "**Qualities:** HD • 720p • 480p • 360p • Audio\n\n"
                "**Commands:**\n"
                "/start - Main menu\n"
                "/stats - View your statistics\n"
                "/settings - Change preferences\n"
                "/history - Download history\n\n"
                "**Tips:**\n"
                "• ⭐ starred quality = your default\n"
                "• Auto-retry on failed downloads\n"
                f"• Rate limit: {Config.RATE_LIMIT_PER_HOUR}/hour"
            )

            keyboard = [[InlineKeyboardButton("« Back to Menu", callback_data="menu_main")]]

            await safe_edit_message(
                query,
                help_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return

        elif data == 'menu_about':
            global_stats = user_stats_db.get_global_stats()

            about_text = (
                "ℹ️ **About This Bot**\n\n"
                "🎬 Twitter/X Video Downloader Bot\n"
                "Version 1.0.0\n\n"
                "I help you download videos from Twitter/X in various qualities:\n"
                "• HD (1080p)\n"
                "• SD (720p/480p)\n"
                "• Audio Only (MP3)\n\n"
                f"**Global Statistics:**\n"
                f"👥 Total Users: {global_stats['total_users']}\n"
                f"📥 Total Downloads: {global_stats['total_downloads']}\n"
                f"💾 Total Data: {global_stats['total_size_mb'] / 1024:.2f} GB\n\n"
                "Made with ❤️ by @Fl3xxRichie\n"
                "Source: github.com/Fl3xxRichie/TWEET-VIDEO-DOWNLOADER"
            )

            keyboard = [[InlineKeyboardButton("« Back to Menu", callback_data="menu_main")]]

            await safe_edit_message(
                query,
                about_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return

        # Handle cancel download
        elif data == 'cancel_download':
            await query.message.delete()
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Download cancelled. Send another URL when you're ready!"
            )
            return

        # Handle quality preference setting

        if data.startswith('quality_'):
            # Set default quality preference
            quality = data.replace('quality_', '')
            user_prefs.set_preference(query.from_user.id, 'quality', quality)
            await safe_edit_message(query, f"✅ Default quality set to {quality.upper()}")
            logger.info(f"User {query.from_user.id} set default quality to {quality}")

        elif data.startswith('download_'):
            # Handle download with selected quality
            parts = data.split('_')
            if len(parts) < 3:
                await safe_edit_message(query, "❌ Error: Invalid callback data format.")
                return

            quality = parts[1]
            url_id = parts[2]
            url = redis_cache.get(url_id)

            if not url:
                await safe_edit_message(query, "❌ Error: Original URL not found or expired. Please send the link again.")
                logger.warning(f"URL not found in cache for ID: {url_id}")
                return

            logger.info(f"Starting download for user {query.from_user.id}: {url} in {quality} quality")

            # Save as last used quality
            user_prefs.set_preference(query.from_user.id, 'quality', quality)

            # Process download directly (no queue - reduces Redis API calls)
            # Run in background so we don't block the callback response
            asyncio.create_task(process_download(
                user_id=query.from_user.id,
                chat_id=query.message.chat_id,
                url=url,
                quality=quality,
                message_id=query.message.message_id,
                username=query.from_user.username,
                platform=detect_platform(url)
            ))

            # Clean up URL from cache
            redis_cache.delete(url_id)

    except Exception as e:
        logger.error(f"Error in handle_quality_selection: {e}", exc_info=True)
        try:
            if 'query' in locals():
                await safe_edit_message(query, f"❌ An error occurred: {str(e)}")
        except:
            pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    try:
        logger.info(f"Start command from user {update.effective_user.id}")

        # Create main menu keyboard
        keyboard = [
            [
                InlineKeyboardButton("📥 Download Video", callback_data="menu_download"),
                InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings"),
            ],
            [
                InlineKeyboardButton("📊 My Statistics", callback_data="menu_stats"),
                InlineKeyboardButton("❓ Help", callback_data="menu_help"),
            ],
            [
                InlineKeyboardButton("ℹ️ About", callback_data="menu_about"),
            ]
        ]

        welcome_text = (
            "👋 **Welcome to Video Downloader Bot!**\n\n"
            "📥 Download videos from:\n"
            "• Twitter/X\n"
            "• Instagram Reels\n"
            "• TikTok\n"
            "• YouTube\n\n"
            "Just send me a video URL to get started!"
        )

        # Check for custom start media
        if Config.START_MEDIA_URL:
            try:
                media_url = Config.START_MEDIA_URL
                is_local_file = os.path.exists(media_url)

                # Determine media type by extension
                lower_url = media_url.lower()
                is_video = any(lower_url.endswith(ext) for ext in ['.mp4', '.mov', '.avi'])
                is_gif = lower_url.endswith('.gif')

                if is_local_file:
                    # Check cache first
                    file_id = MEDIA_FILE_ID_CACHE.get(media_url)

                    if file_id:
                        # Send using cached file_id
                        if is_video:
                            await update.message.reply_video(
                                video=file_id,
                                caption=welcome_text,
                                reply_markup=InlineKeyboardMarkup(keyboard),
                                parse_mode='Markdown'
                            )
                        elif is_gif:
                            await update.message.reply_animation(
                                animation=file_id,
                                caption=welcome_text,
                                reply_markup=InlineKeyboardMarkup(keyboard),
                                parse_mode='Markdown'
                            )
                        else:
                            await update.message.reply_photo(
                                photo=file_id,
                                caption=welcome_text,
                                reply_markup=InlineKeyboardMarkup(keyboard),
                                parse_mode='Markdown'
                            )
                    else:
                        # Handle local file upload and cache file_id
                        sent_msg = None
                        with open(media_url, 'rb') as f:
                            if is_video:
                                sent_msg = await update.message.reply_video(
                                    video=f,
                                    caption=welcome_text,
                                    reply_markup=InlineKeyboardMarkup(keyboard),
                                    parse_mode='Markdown'
                                )
                                # Cache video file_id
                                if sent_msg.video:
                                    MEDIA_FILE_ID_CACHE[media_url] = sent_msg.video.file_id
                            elif is_gif:
                                sent_msg = await update.message.reply_animation(
                                    animation=f,
                                    caption=welcome_text,
                                    reply_markup=InlineKeyboardMarkup(keyboard),
                                    parse_mode='Markdown'
                                )
                                # Cache animation file_id
                                if sent_msg.animation:
                                    MEDIA_FILE_ID_CACHE[media_url] = sent_msg.animation.file_id
                            else:
                                sent_msg = await update.message.reply_photo(
                                    photo=f,
                                    caption=welcome_text,
                                    reply_markup=InlineKeyboardMarkup(keyboard),
                                    parse_mode='Markdown'
                                )
                                # Cache photo file_id (largest size)
                                if sent_msg.photo:
                                    MEDIA_FILE_ID_CACHE[media_url] = sent_msg.photo[-1].file_id

                        logger.info(f"Cached file_id for {media_url}")

                else:
                    # Handle URL (Telegram handles caching/downloading for URLs automatically mostly)
                    if is_video:
                        await update.message.reply_video(
                            video=media_url,
                            caption=welcome_text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='Markdown'
                        )
                    elif is_gif:
                        await update.message.reply_animation(
                            animation=media_url,
                            caption=welcome_text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='Markdown'
                        )
                    else:
                        await update.message.reply_photo(
                            photo=media_url,
                            caption=welcome_text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='Markdown'
                        )
            except Exception as e:
                logger.error(f"Failed to send start media: {e}")
                # Fallback to text
                await update.message.reply_text(
                    welcome_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
        else:
            await update.message.reply_text(
                welcome_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error in start command: {e}", exc_info=True)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message with usage instructions"""
    try:
        logger.info(f"Help command from user {update.effective_user.id}")
        await update.message.reply_text(
            "📌 **How to use this bot:**\n\n"
            "**Single Video:**\n"
            "1. Send a Twitter/X video URL\n"
            "2. Choose quality → Download!\n\n"
            "**📦 Batch Download:**\n"
            "Send multiple URLs in one message!\n"
            "Videos download in your default quality.\n\n"
            "**Supported platforms:**\n"
            "Twitter/X • Instagram • TikTok • YouTube Shorts\n\n"
            "**Qualities:** HD • 720p • 480p • 360p • Audio\n\n"
            "/settings - Set quality | /stats - Stats | /history - History",
            parse_mode='Markdown'
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
                InlineKeyboardButton("SD (360p)", callback_data="quality_360p"),
            ],
            [
                InlineKeyboardButton("Audio Only", callback_data="quality_audio"),
            ],
            [
                InlineKeyboardButton("« Back to Menu", callback_data="menu_main"),
            ]
        ]
        await update.message.reply_text(
            "Select your preferred video quality:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Error in quality command: {e}", exc_info=True)



async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display user statistics"""
    try:
        user_id = update.effective_user.id
        logger.info(f"Stats command from user {user_id}")

        # Get user statistics
        stats = user_stats_db.get_user_stats(user_id)

        # Format statistics message
        stats_text = "📊 **Your Download Statistics**\n\n"

        # Total downloads
        stats_text += f"📥 **Total Downloads:** {stats['total_downloads']}\n"

        # Downloads by quality
        if stats['total_downloads'] > 0:
            stats_text += f"\n**Quality Breakdown:**\n"
            for quality, count in stats['downloads_by_quality'].items():
                if count > 0:
                    emoji = get_quality_emoji(quality)
                    percentage = (count / stats['total_downloads']) * 100
                    stats_text += f"{emoji} {quality.upper()}: {count} ({percentage:.1f}%)\n"

        # Total data downloaded
        total_size = stats['total_size_mb']
        if total_size >= 1024:
            size_str = f"{total_size / 1024:.2f} GB"
        else:
            size_str = f"{total_size:.2f} MB"
        stats_text += f"\n💾 **Total Data:** {size_str}\n"

        # First and last used
        if stats['first_used']:
            stats_text += f"\n🗓️ **Member Since:** {format_timestamp(stats['first_used'])}\n"
        if stats['last_used']:
            stats_text += f"⏰ **Last Download:** {format_timestamp(stats['last_used'])}\n"

        # Download history
        if stats['download_history']:
            stats_text += f"\n**Recent Downloads:**\n"
            for i, download in enumerate(stats['download_history'][:5], 1):
                emoji = get_quality_emoji(download['quality'])
                stats_text += f"{i}. {emoji} {download['quality'].upper()} - {download['size_mb']} MB - {format_timestamp(download['timestamp'])}\n"

        # User rank
        rank = user_stats_db.get_user_rank(user_id)
        total_users = user_stats_db.get_total_users()
        stats_text += f"\n🏆 **Your Rank:** #{rank} out of {total_users} users\n"

        # Back button
        keyboard = [[InlineKeyboardButton("« Back to Menu", callback_data="menu_main")]]

        await update.message.reply_text(
            stats_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in stats command: {e}", exc_info=True)
        await update.message.reply_text("❌ Error retrieving statistics. Please try again.")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display settings panel"""
    try:
        user_id = update.effective_user.id
        logger.info(f"Settings command from user {user_id}")

        # Get current preferences
        current_quality = user_prefs.get_preference(user_id, 'quality', 'hd')

        settings_text = (
            "⚙️ **Settings**\n\n"
            f"**Current Default Quality:** {current_quality.upper()}\n\n"
            "Choose your preferred default quality:"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{'✅ ' if current_quality == 'hd' else ''}HD (1080p)",
                    callback_data="quality_hd"
                ),
                InlineKeyboardButton(
                    f"{'✅ ' if current_quality == '720p' else ''}SD (720p)",
                    callback_data="quality_720p"
                ),
            ],
            [
                InlineKeyboardButton(
                    f"{'✅ ' if current_quality == '480p' else ''}SD (480p)",
                    callback_data="quality_480p"
                ),
                InlineKeyboardButton(
                    f"{'✅ ' if current_quality == 'audio' else ''}Audio Only",
                    callback_data="quality_audio"
                ),
            ],
            [
                InlineKeyboardButton("« Back to Menu", callback_data="menu_main"),
            ]
        ]

        await update.message.reply_text(
            settings_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in settings command: {e}", exc_info=True)


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display bot information"""
    try:
        logger.info(f"About command from user {update.effective_user.id}")

        # Get global statistics
        global_stats = user_stats_db.get_global_stats()

        about_text = (
            "ℹ️ **About This Bot**\n\n"
            "🎬 Twitter/X Video Downloader Bot\n"
            "Version 1.0.0\n\n"
            "I help you download videos from Twitter/X in various qualities:\n"
            "• HD (1080p)\n"
            "• SD (720p/480p)\n"
            "• Audio Only (MP3)\n\n"
            f"**Global Statistics:**\n"
            f"👥 Total Users: {global_stats['total_users']}\n"
            f"📥 Total Downloads: {global_stats['total_downloads']}\n"
            f"💾 Total Data: {global_stats['total_size_mb'] / 1024:.2f} GB\n\n"
            "Made with ❤️ by @Fl3xxRichie\n"
            "Source: github.com/Fl3xxRichie/TWEET-VIDEO-DOWNLOADER"
        )

        keyboard = [[InlineKeyboardButton("« Back to Menu", callback_data="menu_main")]]

        await update.message.reply_text(
            about_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in about command: {e}", exc_info=True)


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display user's download history"""
    try:
        user_id = update.effective_user.id
        logger.info(f"History command from user {user_id}")

        # Get user statistics which includes download history
        stats = user_stats_db.get_user_stats(user_id)
        history = stats.get('download_history', [])

        if not history:
            await update.message.reply_text(
                "📜 **Download History**\n\n"
                "You haven't downloaded any videos yet!\n\n"
                "Send a Twitter/X video URL to get started.",
                parse_mode='Markdown'
            )
            return

        # Build history message
        history_text = "📜 **Your Download History**\n\n"

        for i, download in enumerate(history[:10], 1):
            emoji = get_quality_emoji(download['quality'])
            history_text += (
                f"{i}. {emoji} **{download['quality'].upper()}** - "
                f"{download['size_mb']} MB\n"
                f"   ⏰ {format_timestamp(download['timestamp'])}\n"
            )

        history_text += f"\n📊 Total downloads: {stats['total_downloads']}"

        keyboard = [[InlineKeyboardButton("« Back to Menu", callback_data="menu_main")]]

        await update.message.reply_text(
            history_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in history command: {e}", exc_info=True)
        await update.message.reply_text("❌ Error retrieving history. Please try again.")


async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display comprehensive admin statistics (admin only)"""
    try:
        user_id = update.effective_user.id
        logger.info(f"Admin stats command from user {user_id}")

        # Check if user is admin
        if not Config.ADMIN_USER_ID or user_id != Config.ADMIN_USER_ID:
            await update.message.reply_text("❌ This command is only available to administrators.")
            return

        # Get comprehensive statistics
        global_stats = user_stats_db.get_global_stats()
        daily_stats = user_stats_db.get_daily_stats(days=7)
        top_users = user_stats_db.get_top_users(limit=5)

        # Build admin stats message
        admin_text = "👑 **Admin Dashboard**\n\n"

        # Global Overview
        admin_text += "📊 **Global Statistics**\n"
        admin_text += f"👥 Total Users: {global_stats['total_users']}\n"
        admin_text += f"📥 Total Downloads: {global_stats['total_downloads']}\n"
        admin_text += f"💾 Total Data: {global_stats['total_size_mb'] / 1024:.2f} GB\n\n"

        # Quality Breakdown
        admin_text += "**Quality Distribution:**\n"
        total_dl = global_stats['total_downloads']
        if total_dl > 0:
            for quality, count in global_stats['downloads_by_quality'].items():
                percentage = (count / total_dl) * 100
                emoji = get_quality_emoji(quality)
                admin_text += f"{emoji} {quality.upper()}: {count} ({percentage:.1f}%)\n"
        admin_text += "\n"

        # Daily Statistics (Last 7 Days)
        admin_text += "📅 **Last 7 Days Activity**\n"
        sorted_dates = sorted(daily_stats.keys(), reverse=True)
        for date in sorted_dates[:7]:
            stats = daily_stats[date]
            admin_text += f"• {date}: {stats['downloads']} downloads, {stats['active_users']} users\n"
        admin_text += "\n"

        # Today's Stats
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        if today in daily_stats:
            today_stats = daily_stats[today]
            admin_text += "📈 **Today's Activity**\n"
            admin_text += f"Downloads: {today_stats['downloads']}\n"
            admin_text += f"Active Users: {today_stats['active_users']}\n"
            admin_text += f"Data: {today_stats['size_mb']:.2f} MB\n\n"

        # Top Users
        if top_users:
            admin_text += "🏆 **Top 5 Users**\n"
            for i, user in enumerate(top_users, 1):
                admin_text += f"{i}. User {user['user_id']}: {user['downloads']} downloads ({user['total_size_mb']} MB)\n"

        await update.message.reply_text(
            admin_text,
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error in admin stats command: {e}", exc_info=True)
        await update.message.reply_text("❌ Error retrieving admin statistics.")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message to all bot users (Admin only)

    Usage:
    - Text only: /broadcast Your message here
    - With image: Reply to an image with /broadcast Optional caption
    """
    try:
        user_id = update.effective_user.id
        logger.info(f"Broadcast command from user {user_id}")

        # Check if user is admin
        if not Config.ADMIN_USER_ID or user_id != Config.ADMIN_USER_ID:
            await update.message.reply_text("❌ This command is only available to administrators.")
            return

        # Check if this is a reply to a photo (image broadcast)
        reply_message = update.message.reply_to_message
        photo_file_id = None

        if reply_message and reply_message.photo:
            # Get the highest resolution photo
            photo_file_id = reply_message.photo[-1].file_id

        # Get message/caption to broadcast
        broadcast_message = ' '.join(context.args) if context.args else None

        # Validate input
        if not photo_file_id and not broadcast_message:
            await update.message.reply_text(
                "📢 **Broadcast Usage**\n\n"
                "**Text only:**\n"
                "`/broadcast Your message here`\n\n"
                "**With image:**\n"
                "Reply to an image with `/broadcast` (optional caption)\n\n"
                "**Examples:**\n"
                "`/broadcast 🎉 New feature available!`\n"
                "_Reply to photo_ + `/broadcast Check this out!`",
                parse_mode='Markdown'
            )
            return

        # Get all user IDs from database
        all_user_ids = user_stats_db._get_all_user_ids()

        if not all_user_ids:
            await update.message.reply_text("❌ No users found in database.")
            return

        # Determine broadcast type
        broadcast_type = "image" if photo_file_id else "text"

        # Send progress message
        progress_msg = await update.message.reply_text(
            f"📢 Broadcasting {broadcast_type} to {len(all_user_ids)} users...\n"
            f"This may take a moment."
        )

        success_count = 0
        fail_count = 0

        for uid in all_user_ids:
            try:
                if photo_file_id:
                    # Send image with optional caption
                    caption = f"📢 **Announcement**\n\n{broadcast_message}" if broadcast_message else "📢 **Announcement**"
                    await context.bot.send_photo(
                        chat_id=uid,
                        photo=photo_file_id,
                        caption=caption,
                        parse_mode='Markdown'
                    )
                else:
                    # Send text message
                    await context.bot.send_message(
                        chat_id=uid,
                        text=f"📢 **Announcement**\n\n{broadcast_message}",
                        parse_mode='Markdown'
                    )
                success_count += 1

                # Small delay to avoid hitting rate limits
                await asyncio.sleep(0.05)

            except Exception as e:
                logger.warning(f"Failed to send broadcast to user {uid}: {e}")
                fail_count += 1

        # Update progress message with results
        await progress_msg.edit_text(
            f"📢 **Broadcast Complete**\n\n"
            f"📝 Type: {broadcast_type.capitalize()}\n"
            f"✅ Sent: {success_count}\n"
            f"❌ Failed: {fail_count}\n"
            f"📊 Total: {len(all_user_ids)} users"
        )

        logger.info(f"Broadcast ({broadcast_type}) completed: {success_count} sent, {fail_count} failed")

    except Exception as e:
        logger.error(f"Error in broadcast command: {e}", exc_info=True)
        await update.message.reply_text("❌ Error sending broadcast.")


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming video URLs (supports batch - multiple URLs, multiple platforms)"""
    import re
    try:
        user_id = update.message.from_user.id
        message_text = update.message.text.strip()
        logger.info(f"Message received from user {user_id}: {message_text[:100]}...")

        # Extract all video URLs from supported platforms
        all_patterns = []
        for platform, patterns in PLATFORM_PATTERNS.items():
            all_patterns.extend(patterns)

        # Find all matching URLs
        urls = []
        for pattern in all_patterns:
            matches = re.findall(pattern, message_text)
            urls.extend(matches)
        urls = list(set(urls))  # Remove duplicates

        if not urls:
            await update.message.reply_text(
                "⚠️ Please send a valid video URL\n\n"
                "**Supported platforms:**\n"
                "• Twitter/X\n"
                "• Instagram Reels\n"
                "• TikTok\n"
                "• YouTube Shorts",
                parse_mode='Markdown'
            )
            return

        # Check rate limit status
        rate_status = get_rate_limit_status(user_id)

        if rate_status['remaining'] <= 0:
            await update.message.reply_text(
                f"⚠️ Rate limit exceeded. Please try again in an hour.\n"
                f"(Limit: {Config.RATE_LIMIT_PER_HOUR} downloads per hour)"
            )
            return

        # For batch downloads, check if we have enough remaining
        if len(urls) > rate_status['remaining']:
            await update.message.reply_text(
                f"⚠️ You have {rate_status['remaining']} downloads remaining this hour, "
                f"but you're trying to download {len(urls)} videos.\n"
                f"Please reduce the number of URLs or wait for your limit to reset."
            )
            return

        # Handle batch downloads (multiple URLs)
        if len(urls) > 1:
            await handle_batch_urls(update, context, urls, rate_status)
            return

        # Single URL processing
        url = urls[0]

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

        # Create buttons with accurate size estimates (now includes 360p)
        buttons = []
        for quality, label in [
            ('hd', 'HD (1080p)'),
            ('720p', 'SD (720p)'),
            ('480p', 'SD (480p)'),
            ('360p', 'SD (360p)'),
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

        # Arrange buttons in grid + cancel button
        keyboard = [
            buttons[:2],
            buttons[2:4],
            [buttons[4]],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_download")]
        ]

        # Format duration
        duration = video_info.get('duration', 0)
        if duration:
            minutes, seconds = divmod(int(duration), 60)
            duration_str = f"{minutes}:{seconds:02d}"
        else:
            duration_str = "Unknown"

        # Get updated rate status (after check_rate_limit consumed one)
        updated_rate_status = get_rate_limit_status(user_id)
        rate_warning = ""
        if updated_rate_status['remaining'] <= 3:
            rate_warning = f"\n⚠️ {updated_rate_status['remaining']} downloads remaining this hour"

        # Build caption with video info
        caption = (
            f"🎬 **{video_info.get('title', 'Video')}**\n\n"
            f"👤 {video_info.get('uploader', 'Unknown')}\n"
            f"⏱️ Duration: {duration_str}{rate_warning}\n\n"
            f"Select quality to download:"
        )

        # Delete processing message
        await processing_msg.delete()

        # Send thumbnail with quality buttons if available
        thumbnail_url = video_info.get('thumbnail')
        if thumbnail_url:
            try:
                await update.message.reply_photo(
                    photo=thumbnail_url,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.warning(f"Failed to send thumbnail: {e}, falling back to text")
                await update.message.reply_text(
                    caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
        else:
            await update.message.reply_text(
                caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )

        logger.info(f"Quality selection with thumbnail sent to user {user_id}")

    except Exception as e:
        logger.error(f"Error in handle_url: {e}", exc_info=True)
        try:
            await update.message.reply_text("❌ An error occurred while processing your request. Please try again.")
        except:
            pass


async def handle_batch_urls(update: Update, context: ContextTypes.DEFAULT_TYPE, urls: list, rate_status: dict):
    """Handle batch download of multiple URLs"""
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    # Get user's preferred quality
    preferred_quality = user_prefs.get_preference(user_id, 'quality', 'hd')

    await update.message.reply_text(
        f"📦 **Batch Download Started**\n\n"
        f"Processing {len(urls)} videos in {preferred_quality.upper()} quality...\n"
        f"(Downloads remaining: {rate_status['remaining']})\n\n"
        f"💡 Tip: Set your default quality with /settings",
        parse_mode='Markdown'
    )

    success_count = 0
    fail_count = 0

    for i, url in enumerate(urls, 1):
        # Check rate limit for each download
        if not check_rate_limit(user_id):
            await update.message.reply_text(
                f"⚠️ Rate limit reached after {success_count} downloads. "
                f"Remaining {len(urls) - i + 1} videos skipped."
            )
            break

        progress_msg = await update.message.reply_text(
            f"📥 Downloading video {i}/{len(urls)}..."
        )

        try:
            async def progress_callback(progress_info):
                try:
                    status = progress_info.get('status')
                    if status == 'downloading':
                        percent = progress_info.get('_percent_str', 'N/A')
                        await progress_msg.edit_text(
                            f"📥 Video {i}/{len(urls)}: {percent}"
                        )
                    elif status == 'retrying':
                        attempt = progress_info.get('attempt', 0)
                        max_retries = progress_info.get('max_retries', 3)
                        await progress_msg.edit_text(
                            f"🔄 Video {i}/{len(urls)}: Retry {attempt}/{max_retries}..."
                        )
                except:
                    pass

            result = await video_downloader.download_video(
                url, preferred_quality, progress_callback=progress_callback
            )

            if result['success']:
                file_path = result['file_path']
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

                # Compress if needed
                if file_size_mb > 49.0:
                    await progress_msg.edit_text(f"🗜️ Video {i}/{len(urls)}: Compressing...")
                    compress_result = await video_downloader.compress_video(file_path, target_size_mb=45.0)
                    if compress_result['success']:
                        file_path = compress_result['file_path']

                # Send video
                await progress_msg.edit_text(f"📤 Video {i}/{len(urls)}: Sending...")
                with open(file_path, 'rb') as video_file:
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=video_file,
                        caption=f"🎥 Video {i}/{len(urls)} - {preferred_quality.upper()}",
                        supports_streaming=True,
                        read_timeout=120,
                        write_timeout=120
                    )

                # Record stats
                user_stats_db.record_download(
                    user_id=user_id,
                    quality=preferred_quality,
                    file_size_bytes=os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                    url=url,
                    success=True,
                    username=username,
                    platform=detect_platform(url)
                )

                # Cleanup
                if os.path.exists(file_path):
                    os.remove(file_path)
                await progress_msg.delete()
                success_count += 1

            else:
                await progress_msg.edit_text(f"❌ Video {i}/{len(urls)}: Failed - {result.get('error', 'Unknown error')}")
                fail_count += 1

        except Exception as e:
            logger.error(f"Batch download error for URL {i}: {e}")
            await progress_msg.edit_text(f"❌ Video {i}/{len(urls)}: Error - {str(e)[:50]}")
            fail_count += 1

    # Summary message
    summary = f"📦 **Batch Download Complete**\n\n"
    summary += f"✅ Successful: {success_count}\n"
    if fail_count > 0:
        summary += f"❌ Failed: {fail_count}\n"

    await update.message.reply_text(summary, parse_mode='Markdown')


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
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("adminstats", admin_stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("history", history_command))

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

@app.post("/webhook")
@app.post("/")  # Also handle POST to root path for webhook (Google Cloud Run compatibility)
async def webhook(request: Request):
    """Handle incoming Telegram updates"""
    try:
        # Check token
        secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        # In a real app, verify this token matches what you set

        data = await request.json()
        update = Update.de_json(data, application.bot)

        # Feed update to application
        await application.process_update(update)

        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"Error in webhook: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, admin_id: int = None):
    """Serve the analytics dashboard"""
    # Optional: Check admin ID if provided
    if Config.ADMIN_USER_ID and admin_id:
        if admin_id != int(Config.ADMIN_USER_ID):
            raise HTTPException(status_code=403, detail="Unauthorized")

    try:
        template_path = Path("templates/dashboard.html")
        if not template_path.exists():
            return HTMLResponse("<h1>Dashboard template not found</h1>", status_code=404)

        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()

        return HTMLResponse(content=content)
    except Exception as e:
        logger.error(f"Error serving dashboard: {e}")
        return HTMLResponse("<h1>Internal Server Error</h1>", status_code=500)

@app.get("/api/stats/dashboard")
async def get_dashboard_stats():
    """Get statistics for the dashboard"""
    try:
        global_stats = user_stats_db.get_global_stats()
        daily_stats = user_stats_db.get_daily_stats(days=7)
        top_users = user_stats_db.get_top_users(limit=10)

        # Get today's stats specifically
        today_str = datetime.now().strftime('%Y-%m-%d')
        today_stats = daily_stats.get(today_str, {'downloads': 0, 'size_mb': 0})

        return JSONResponse({
            'global': global_stats,
            'daily': daily_stats,
            'today': today_stats,
            'top_users': top_users
        })
    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {e}")
        return JSONResponse({'error': str(e)}, status_code=500)

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, shutting down...")
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main():
    """Run the bot with uvicorn - polling or webhook mode determined by config"""
    mode = "webhook" if Config.WEBHOOK_URL else "polling"
    logger.info(f"Starting application in {mode} mode with web server on port {Config.PORT}")
    logger.info(f"Dashboard will be available at http://localhost:{Config.PORT}/dashboard")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=Config.PORT,
        log_level="info"
    )

if __name__ == "__main__":
    main()
