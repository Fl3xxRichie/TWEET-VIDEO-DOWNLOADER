# Admin Features Guide

## Overview

The bot now includes comprehensive admin statistics accessible only to the bot administrator.

## Setup

### 1. Get Your Telegram User ID

To enable admin features, you need your Telegram user ID:

1. Open Telegram
2. Search for `@userinfobot`
3. Start a chat and send `/start`
4. The bot will reply with your user ID (a number like `123456789`)

### 2. Configure Admin Access

Add your user ID to the `.env` file:

```bash
ADMIN_USER_ID=123456789
```

Replace `123456789` with your actual Telegram user ID.

### 3. Restart the Bot

After adding your user ID, restart the bot:

```bash
python app.py
```

## Admin Commands

### `/adminstats` - Admin Dashboard

Displays comprehensive statistics including:

**Global Statistics**
- Total users
- Total downloads
- Total data transferred

**Quality Distribution**
- Breakdown of downloads by quality (HD, SD, Audio)
- Percentage distribution

**Daily Activity (Last 7 Days)**
- Downloads per day
- Active users per day

**Today's Activity**
- Current day's downloads
- Active users today
- Data transferred today

**Top 5 Users**
- User rankings by download count
- Total data per user

### Example Output

```
👑 Admin Dashboard

📊 Global Statistics
👥 Total Users: 150
📥 Total Downloads: 1,234
💾 Total Data: 45.67 GB

Quality Distribution:
🎬 HD: 567 (45.9%)
📺 720P: 445 (36.1%)
📱 480P: 178 (14.4%)
🎵 AUDIO: 44 (3.6%)

📅 Last 7 Days Activity
• 2025-11-23: 89 downloads, 34 users
• 2025-11-22: 112 downloads, 42 users
• 2025-11-21: 95 downloads, 38 users
...

📈 Today's Activity
Downloads: 89
Active Users: 34
Data: 3.2 GB

🏆 Top 5 Users
1. User 123456: 45 downloads (1.2 GB)
2. User 789012: 38 downloads (980 MB)
...
```

## Security

- Only the user ID specified in `ADMIN_USER_ID` can access admin commands
- Other users will receive an "access denied" message
- Admin user ID is never exposed to regular users

## Troubleshooting

**"This command is only available to administrators"**
- Verify your user ID is correct in `.env`
- Restart the bot after changing `.env`
- Make sure you're using the correct Telegram account

**Admin command not working**
- Check that `ADMIN_USER_ID` is set in `.env`
- Verify the bot has been restarted
- Check logs for any errors

## Privacy Note

Admin statistics show:
- Aggregated data (total users, downloads, etc.)
- User IDs in top users list (not names or usernames)
- Daily activity trends

No personal information (names, usernames, messages) is stored or displayed.
