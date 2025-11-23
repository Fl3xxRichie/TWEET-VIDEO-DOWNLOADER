#!/usr/bin/env python3
"""
Script to add all enhancements to app.py:
1. Statistics tracking in download handler
2. Enhanced callback handler with menu navigation
3. New command handlers (stats, settings, about, adminstats)
4. Updated start command with buttons
5. Register new handlers
"""

import re

# Read the current app.py
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add statistics tracking after successful download (around line 271-277)
old_cleanup = """                # Clean up
                try:
                    os.remove(result['file_path'])
                    await progress_message.delete()
                    logger.info(f"Successfully sent video to user {query.from_user.id}")
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")"""

new_cleanup = """                # Clean up
                try:
                    # Record successful download in statistics
                    file_size = os.path.getsize(result['file_path'])
                    user_stats_db.record_download(
                        user_id=query.from_user.id,
                        quality=quality,
                        file_size_bytes=file_size,
                        url=url,
                        success=True
                    )

                    os.remove(result['file_path'])
                    await progress_message.delete()
                    logger.info(f"Successfully sent video to user {query.from_user.id}")
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")"""

content = content.replace(old_cleanup, new_cleanup)

# 2. Enhance callback handler to support menu navigation (insert after line 199)
menu_navigation_code = '''
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
            await query.edit_message_text(
                "👋 Welcome to Twitter/X Video Downloader!\\n\\n"
                "I can help you download videos from Twitter/X in various qualities.\\n\\n"
                "Choose an option below to get started:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        elif data == 'menu_download':
            await query.edit_message_text(
                "📥 **How to Download Videos**\\n\\n"
                "1. Copy a Twitter/X video URL\\n"
                "2. Send it to me\\n"
                "3. Choose your preferred quality\\n"
                "4. Wait for the download to complete\\n\\n"
                "Just paste any Twitter/X video link to get started!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="menu_main")]]),
                parse_mode='Markdown'
            )
            return

        elif data == 'menu_settings':
            user_id = query.from_user.id
            current_quality = user_prefs.get_preference(user_id, 'quality', 'hd')

            settings_text = (
                "⚙️ **Settings**\\n\\n"
                f"**Current Default Quality:** {current_quality.upper()}\\n\\n"
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

            await query.edit_message_text(
                settings_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return

        elif data == 'menu_stats':
            user_id = query.from_user.id
            stats = user_stats_db.get_user_stats(user_id)

            stats_text = "📊 **Your Download Statistics**\\n\\n"
            stats_text += f"📥 **Total Downloads:** {stats['total_downloads']}\\n"

            if stats['total_downloads'] > 0:
                stats_text += f"\\n**Quality Breakdown:**\\n"
                for quality, count in stats['downloads_by_quality'].items():
                    if count > 0:
                        emoji = get_quality_emoji(quality)
                        percentage = (count / stats['total_downloads']) * 100
                        stats_text += f"{emoji} {quality.upper()}: {count} ({percentage:.1f}%)\\n"

            total_size = stats['total_size_mb']
            if total_size >= 1024:
                size_str = f"{total_size / 1024:.2f} GB"
            else:
                size_str = f"{total_size:.2f} MB"
            stats_text += f"\\n💾 **Total Data:** {size_str}\\n"

            if stats['first_used']:
                stats_text += f"\\n🗓️ **Member Since:** {format_timestamp(stats['first_used'])}\\n"
            if stats['last_used']:
                stats_text += f"⏰ **Last Download:** {format_timestamp(stats['last_used'])}\\n"

            if stats['download_history']:
                stats_text += f"\\n**Recent Downloads:**\\n"
                for i, download in enumerate(stats['download_history'][:5], 1):
                    emoji = get_quality_emoji(download['quality'])
                    stats_text += f"{i}. {emoji} {download['quality'].upper()} - {download['size_mb']} MB - {format_timestamp(download['timestamp'])}\\n"

            rank = user_stats_db.get_user_rank(user_id)
            total_users = user_stats_db.get_total_users()
            stats_text += f"\\n🏆 **Your Rank:** #{rank} out of {total_users} users\\n"

            keyboard = [[InlineKeyboardButton("« Back to Menu", callback_data="menu_main")]]

            await query.edit_message_text(
                stats_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return

        elif data == 'menu_help':
            help_text = (
                "❓ **Help & Usage Guide**\\n\\n"
                "**How to use this bot:**\\n\\n"
                "1. Send me a Twitter/X video URL\\n"
                "2. Choose your preferred quality\\n"
                "3. Wait for the download to complete\\n\\n"
                "**Supported formats:**\\n"
                "• Single video tweets\\n"
                "• HD (1080p), SD (720p/480p)\\n"
                "• Audio only (MP3)\\n\\n"
                "**Commands:**\\n"
                "/start - Main menu\\n"
                "/stats - View your statistics\\n"
                "/settings - Change preferences\\n"
                "/help - Show this help message\\n"
                "/about - About this bot\\n\\n"
                "**Tips:**\\n"
                "• Set your default quality in Settings\\n"
                "• Check your stats to see download history\\n"
                f"• Rate limit: {Config.RATE_LIMIT_PER_HOUR} downloads per hour"
            )

            keyboard = [[InlineKeyboardButton("« Back to Menu", callback_data="menu_main")]]

            await query.edit_message_text(
                help_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return

        elif data == 'menu_about':
            global_stats = user_stats_db.get_global_stats()

            about_text = (
                "ℹ️ **About This Bot**\\n\\n"
                "🎬 Twitter/X Video Downloader Bot\\n"
                "Version 1.0.0\\n\\n"
                "I help you download videos from Twitter/X in various qualities:\\n"
                "• HD (1080p)\\n"
                "• SD (720p/480p)\\n"
                "• Audio Only (MP3)\\n\\n"
                f"**Global Statistics:**\\n"
                f"👥 Total Users: {global_stats['total_users']}\\n"
                f"📥 Total Downloads: {global_stats['total_downloads']}\\n"
                f"💾 Total Data: {global_stats['total_size_mb'] / 1024:.2f} GB\\n\\n"
                "Made with ❤️ by @Fl3xxRichie\\n"
                "Source: github.com/Fl3xxRichie/TWEET-VIDEO-DOWNLOADER"
            )

            keyboard = [[InlineKeyboardButton("« Back to Menu", callback_data="menu_main")]]

            await query.edit_message_text(
                about_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return

        # Handle quality preference setting
'''

# Insert menu navigation after "data = query.data"
content = content.replace(
    "        data = query.data\n\n        if data.startswith('quality_'):",
    f"        data = query.data\n{menu_navigation_code}\n        if data.startswith('quality_'):"
)

# 3. Update start command with buttons
old_start = '''async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    try:
        logger.info(f"Start command from user {update.effective_user.id}")
        await update.message.reply_text(
            "Hi! I can download videos from Twitter/X. Just send me a URL.\\n\\n"
            "Available commands:\\n"
            "/help - Show usage guide\\n"
            "/quality - Set preferred video quality"
        )
    except Exception as e:
        logger.error(f"Error in start command: {e}", exc_info=True)'''

new_start = '''async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            "👋 Welcome to Twitter/X Video Downloader!\\n\\n"
            "I can help you download videos from Twitter/X in various qualities.\\n\\n"
            "Choose an option below to get started:"
        )

        await update.message.reply_text(
            welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Error in start command: {e}", exc_info=True)'''

content = content.replace(old_start, new_start)

# 4. Add back button to quality command
old_quality = '''async def quality_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        logger.error(f"Error in quality command: {e}", exc_info=True)'''

new_quality = '''async def quality_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        logger.error(f"Error in quality command: {e}", exc_info=True)'''

content = content.replace(old_quality, new_quality)

# 5. Add new command handlers before handle_url function
new_commands = '''

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display user statistics"""
    try:
        user_id = update.effective_user.id
        logger.info(f"Stats command from user {user_id}")

        # Get user statistics
        stats = user_stats_db.get_user_stats(user_id)

        # Format statistics message
        stats_text = "📊 **Your Download Statistics**\\n\\n"

        # Total downloads
        stats_text += f"📥 **Total Downloads:** {stats['total_downloads']}\\n"

        # Downloads by quality
        if stats['total_downloads'] > 0:
            stats_text += f"\\n**Quality Breakdown:**\\n"
            for quality, count in stats['downloads_by_quality'].items():
                if count > 0:
                    emoji = get_quality_emoji(quality)
                    percentage = (count / stats['total_downloads']) * 100
                    stats_text += f"{emoji} {quality.upper()}: {count} ({percentage:.1f}%)\\n"

        # Total data downloaded
        total_size = stats['total_size_mb']
        if total_size >= 1024:
            size_str = f"{total_size / 1024:.2f} GB"
        else:
            size_str = f"{total_size:.2f} MB"
        stats_text += f"\\n💾 **Total Data:** {size_str}\\n"

        # First and last used
        if stats['first_used']:
            stats_text += f"\\n🗓️ **Member Since:** {format_timestamp(stats['first_used'])}\\n"
        if stats['last_used']:
            stats_text += f"⏰ **Last Download:** {format_timestamp(stats['last_used'])}\\n"

        # Download history
        if stats['download_history']:
            stats_text += f"\\n**Recent Downloads:**\\n"
            for i, download in enumerate(stats['download_history'][:5], 1):
                emoji = get_quality_emoji(download['quality'])
                stats_text += f"{i}. {emoji} {download['quality'].upper()} - {download['size_mb']} MB - {format_timestamp(download['timestamp'])}\\n"

        # User rank
        rank = user_stats_db.get_user_rank(user_id)
        total_users = user_stats_db.get_total_users()
        stats_text += f"\\n🏆 **Your Rank:** #{rank} out of {total_users} users\\n"

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
            "⚙️ **Settings**\\n\\n"
            f"**Current Default Quality:** {current_quality.upper()}\\n\\n"
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
            "ℹ️ **About This Bot**\\n\\n"
            "🎬 Twitter/X Video Downloader Bot\\n"
            "Version 1.0.0\\n\\n"
            "I help you download videos from Twitter/X in various qualities:\\n"
            "• HD (1080p)\\n"
            "• SD (720p/480p)\\n"
            "• Audio Only (MP3)\\n\\n"
            f"**Global Statistics:**\\n"
            f"👥 Total Users: {global_stats['total_users']}\\n"
            f"📥 Total Downloads: {global_stats['total_downloads']}\\n"
            f"💾 Total Data: {global_stats['total_size_mb'] / 1024:.2f} GB\\n\\n"
            "Made with ❤️ by @Fl3xxRichie\\n"
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
        admin_text = "👑 **Admin Dashboard**\\n\\n"

        # Global Overview
        admin_text += "📊 **Global Statistics**\\n"
        admin_text += f"👥 Total Users: {global_stats['total_users']}\\n"
        admin_text += f"📥 Total Downloads: {global_stats['total_downloads']}\\n"
        admin_text += f"💾 Total Data: {global_stats['total_size_mb'] / 1024:.2f} GB\\n\\n"

        # Quality Breakdown
        admin_text += "**Quality Distribution:**\\n"
        total_dl = global_stats['total_downloads']
        if total_dl > 0:
            for quality, count in global_stats['downloads_by_quality'].items():
                percentage = (count / total_dl) * 100
                emoji = get_quality_emoji(quality)
                admin_text += f"{emoji} {quality.upper()}: {count} ({percentage:.1f}%)\\n"
        admin_text += "\\n"

        # Daily Statistics (Last 7 Days)
        admin_text += "📅 **Last 7 Days Activity**\\n"
        sorted_dates = sorted(daily_stats.keys(), reverse=True)
        for date in sorted_dates[:7]:
            stats = daily_stats[date]
            admin_text += f"• {date}: {stats['downloads']} downloads, {stats['active_users']} users\\n"
        admin_text += "\\n"

        # Today's Stats
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        if today in daily_stats:
            today_stats = daily_stats[today]
            admin_text += "📈 **Today's Activity**\\n"
            admin_text += f"Downloads: {today_stats['downloads']}\\n"
            admin_text += f"Active Users: {today_stats['active_users']}\\n"
            admin_text += f"Data: {today_stats['size_mb']:.2f} MB\\n\\n"

        # Top Users
        if top_users:
            admin_text += "🏆 **Top 5 Users**\\n"
            for i, user in enumerate(top_users, 1):
                admin_text += f"{i}. User {user['user_id']}: {user['downloads']} downloads ({user['total_size_mb']} MB)\\n"

        await update.message.reply_text(
            admin_text,
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error in admin stats command: {e}", exc_info=True)
        await update.message.reply_text("❌ Error retrieving admin statistics.")

'''

# Insert new commands before handle_url
content = content.replace(
    "async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):",
    new_commands + "\nasync def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):"
)

# 6. Register new handlers
old_handlers = '''    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quality", quality_command))'''

new_handlers = '''    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quality", quality_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("adminstats", admin_stats_command))'''

content = content.replace(old_handlers, new_handlers)

# Write the updated content
with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Successfully applied all enhancements to app.py!")
print("Changes applied:")
print("  1. Added statistics tracking to download handler")
print("  2. Enhanced callback handler with menu navigation")
print("  3. Updated start command with button interface")
print("  4. Added back button to quality command")
print("  5. Added stats_command, settings_command, about_command, admin_stats_command")
print("  6. Registered all new command handlers")
