# 🎬 Twitter/X Video Downloader Telegram Bot

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-supported-blue.svg)](https://www.docker.com/)
[![Telegram](https://img.shields.io/badge/telegram-bot-blue.svg)](https://telegram.org/)

A powerful, scalable, and user-friendly Telegram bot for downloading high-quality videos from Twitter/X (formerly Twitter). Built with Python using modern frameworks like `python-telegram-bot`, `yt-dlp`, and `FastAPI` for optimal performance and reliability.

## 📋 Table of Contents

- [Features](#-features)
- [Demo](#-demo)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [Deployment](#-deployment)
- [Bot Commands](#-bot-commands)
- [API Endpoints](#-api-endpoints)
- [Project Structure](#-project-structure)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)
- [Support](#-support)

## 🌟 Features

### Core Functionality
- **🎥 High-Quality Downloads**: Support for multiple video qualities:
  - **HD (1080p)**: Crystal clear video quality
  - **SD (720p/480p)**: Balanced quality and file size
  - **Audio-only (MP3)**: Extract audio tracks
- **⚡ Lightning Fast**: Optimized download speeds with parallel processing
- **📱 User-Friendly Interface**: Intuitive commands and interactive buttons
- **📊 Real-Time Progress**: Live download progress with speed and ETA indicators

### Advanced Features
- **🛡️ Rate Limiting**: Configurable per-user download limits to prevent abuse
- **📏 File Size Control**: Automatic file size validation and compression
- **🗜️ Auto-Compression**: Automatically compresses videos over 45MB to fit Telegram limits
- **🖼️ Thumbnail Preview**: See video thumbnail, title, and duration before downloading
- **📜 Download History**: View your last 10 downloads with `/history`
- **📊 Download Queue**: Redis-based queue system for handling high traffic
- **🔄 Auto-Retry**: Intelligent retry mechanism for failed downloads
- **📝 Comprehensive Logging**: Detailed logs for monitoring and debugging
- **🔒 Redis Integration**: Utilizes Redis for rate limiting, user statistics, and preferences (required for persistent storage)
- **🌐 Multi-Format Support**: Various Twitter/X URL formats supported

### Deployment & Scaling
- **📉 Analytics Dashboard**: Web-based dashboard for visualizing bot usage, top users, and traffic trends
- **🚀 Dual Mode Operation**:
  - **Polling Mode**: Perfect for development and testing
  - **Webhook Mode**: Production-ready with FastAPI integration
- **🐳 Docker Support**: Containerized deployment for consistency
- **📈 Scalable Architecture**: Built to handle high traffic loads
- **💊 Health Monitoring**: Built-in health checks and status monitoring

## 🎯 Demo

### Basic Usage
```
User: https://twitter.com/username/status/1234567890
Bot: 🎬 Video detected! Choose your preferred quality:
     [🎥 HD (1080p)] [📺 SD (720p)] [🎵 Audio Only]

User: [Clicks HD]
Bot: ⬇️ Downloading... 45% (2.3 MB/s, ETA: 8s)
     ✅ Download complete! Here's your video.
```

## 📋 Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.8+** - [Download Python](https://www.python.org/downloads/)
- **Git** - [Install Git](https://git-scm.com/downloads)
- **Telegram Bot Token** - Create one via [BotFather](https://t.me/botfather)

### System Requirements
- **RAM**: Minimum 512MB, Recommended 1GB+
- **Storage**: At least 1GB free space for temporary files
- **Network**: Stable internet connection for video downloads

## 🚀 Installation

### Method 1: Standard Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/Fl3xxRichie/tweet-video-downloader.git
   cd tweet-video-downloader
   ```

2. **Create Virtual Environment** (Recommended)
   ```bash
   python -m venv venv

   # On Windows Bash
   source venv/Scripts/activate

   # On Windows
   venv\Scripts\activate

   # On macOS/Linux
   source venv/Scripts/activate
   ```

3. **Install Dependencies**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

### Method 2: Docker Installation

1. **Clone Repository**
   ```bash
   git clone https://github.com/Fl3xxRichie/tweet-video-downloader.git
   cd tweet-video-downloader
   ```

2. **Build Docker Image**
   ```bash
   docker build -t tweet-video-downloader .
   ```

## ⚙️ Configuration

### Environment Setup

1. **Create Configuration File**
   ```bash
   cp .env.example .env
   ```

2. **Edit Configuration**
   Open `.env` in your preferred text editor and configure:

   ```env
   # ===========================================
   # TELEGRAM BOT CONFIGURATION
   # ===========================================
   # Your bot token from @BotFather
   BOT_TOKEN=your_telegram_bot_token_here

   # ===========================================
   # DEPLOYMENT CONFIGURATION
   # ===========================================
   # Leave empty for polling mode (development)
   # Set for webhook mode (production)
   WEBHOOK_URL=https://your-app.herokuapp.com

   # Port for the web server (webhook mode only)
   PORT=8000

   # ===========================================
   # DOWNLOAD SETTINGS
   # ===========================================
   # Maximum file size for downloads (MB)
   MAX_FILE_SIZE_MB=50

   # Downloads per user per hour
   RATE_LIMIT_PER_HOUR=10

   # Default video quality (hd/sd/audio)
   DEFAULT_QUALITY=hd

   # ===========================================
   # SYSTEM CONFIGURATION
   # ===========================================
   # Logging level (DEBUG/INFO/WARNING/ERROR)
   LOG_LEVEL=INFO

   # Maximum concurrent downloads
   MAX_CONCURRENT_DOWNLOADS=5

   # Temporary file cleanup interval (hours)
   CLEANUP_INTERVAL_HOURS=1

   # ===========================================
   # REDIS CONFIGURATION (Required for persistent storage)
   # ===========================================
   # Redis connection URL - REQUIRED for stats to persist across deployments
   # For local development: redis://localhost:6379/0
   # For production: Use Upstash or similar managed Redis
   REDIS_URL=redis://localhost:6379/0
   ```

> ⚠️ **Important**: Redis is **required** for user statistics and preferences to persist across deployments. Without Redis, stats will reset every time your application restarts.

### Getting Your Bot Token

### Redis Setup

For local development, you can easily set up a Redis instance using Docker:

```bash
docker run --name some-redis -p 6379:6379 -d redis
```

This command starts a Redis container named `some-redis` and maps port `6379` to your host machine. You can then use `REDIS_URL=redis://localhost:6379/0` in your `.env` file.

For live deployments, consider using a managed Redis service like [Upstash](https://upstash.com/). Upstash provides a serverless Redis offering with a free tier, and you can obtain your `REDIS_URL` directly from their dashboard.

1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot` command
3. Follow the instructions to create your bot
4. Copy the provided token to your `.env` file

## 🎮 Usage

### Development Mode (Polling)

Perfect for local testing and development:

```bash
python app.py
```

The bot will start in polling mode and begin listening for updates.

### Production Mode (Webhook)

For production deployments with better performance:

1. Set your `WEBHOOK_URL` in `.env`
2. Deploy to your hosting platform
3. Run:
   ```bash
   python app.py
   ```

### Docker Usage

```bash
# Run with environment file
docker run --env-file .env -p 8000:8000 tweet-video-downloader

# Or with inline environment variables
docker run -e BOT_TOKEN=your_token -p 8000:8000 tweet-video-downloader
```

## 🚀 Deployment

### Heroku Deployment

1. **Install Heroku CLI**
   ```bash
   # Follow instructions at https://devcenter.heroku.com/articles/heroku-cli
   ```

2. **Create Heroku App**
   ```bash
   heroku create your-bot-name
   ```

3. **Set Environment Variables**
   ```bash
   heroku config:set BOT_TOKEN=your_bot_token
   heroku config:set WEBHOOK_URL=https://your-bot-name.herokuapp.com
   ```

4. **Deploy**
   ```bash
   git push heroku main
   ```

### Redis Deployment (Optional)

If you're deploying to a live server and require Redis for rate limiting or session management, you have a few options:

- **Managed Redis Service**:
  - **Upstash**: Recommended for serverless deployments. Sign up at [Upstash](https://upstash.com/) to get a free Redis instance and obtain your `REDIS_URL`.
  - Other cloud providers like AWS ElastiCache, Google Cloud Memorystore, or Azure Cache for Redis.

- **Self-Hosted Redis (Docker)**:
  If you have a server, you can deploy Redis using Docker:
  ```bash
  docker run -d --name my-redis -p 6379:6379 redis/redis-stack-server:latest
  ```
  Ensure your `REDIS_URL` in the `.env` file points to your Redis instance (e.g., `redis://your-server-ip:6379/0`)

### 📊 Analytics Dashboard

The bot includes a beautiful web-based dashboard to visualize usage statistics in real-time.

**Access**:
- **Local Development**: `http://localhost:8000/dashboard`
- **Production**: `https://your-deployment-url.com/dashboard`

**Dashboard Features**:
- 📈 **Real-time Stats**: Total users, downloads, and data usage
- 📊 **Weekly Activity Chart**: Visual download trends over the past 7 days
- 🥧 **Quality Distribution**: Breakdown of HD/SD/Audio downloads
- 🏆 **Top Users Leaderboard**: Most active users ranking
- 🔄 **Auto-refresh**: Data updates every 30 seconds

**Example URLs**:
```
# Render
https://your-app.onrender.com/dashboard

# Google Cloud Run
https://your-service-xyz.run.app/dashboard

# Railway
https://your-app.up.railway.app/dashboard
```

**Security** (Optional):
By default, the dashboard is read-only and public. To restrict access:
1. Set `ADMIN_USER_ID` in your `.env` file
2. Access with query parameter: `/dashboard?admin_id=YOUR_ID`

### Google Cloud Deployment

1. **Prerequisites**
   - Google Cloud account with billing enabled
   - `gcloud` CLI installed and configured
   - Redis instance (Upstash recommended for serverless)

2. **Deploy to Cloud Run**
   ```bash
   # Build and deploy
   gcloud run deploy tweet-bot \
     --source . \
     --region us-central1 \
     --allow-unauthenticated \
     --set-env-vars BOT_TOKEN=your_token,WEBHOOK_URL=https://your-service-url,REDIS_URL=your_redis_url
   ```

3. **Set Webhook URL** after deployment:
   ```bash
   # Get your Cloud Run URL and update WEBHOOK_URL env var
   gcloud run services update tweet-bot --set-env-vars WEBHOOK_URL=https://your-cloud-run-url
   ```

> ⚠️ **Note**: Google Cloud Run uses ephemeral containers. User statistics and preferences are stored in Redis to persist across deployments.

### Railway Deployment

1. Connect your GitHub repository to Railway
2. Set environment variables in Railway dashboard
3. Deploy automatically on push

### DigitalOcean/VPS Deployment

1. **Setup Server**
   ```bash
   # Update system
   sudo apt update && sudo apt upgrade -y

   # Install Python and Git
   sudo apt install python3 python3-pip git -y
   ```

2. **Clone and Setup**
   ```bash
   git clone https://github.com/Fl3xxRichie/tweet-video-downloader.git
   cd tweet-video-downloader
   pip3 install -r requirements.txt
   ```

3. **Create Service** (systemd)
   ```bash
   sudo nano /etc/systemd/system/tweet-bot.service
   ```

   Add:
   ```ini
   [Unit]
   Description=Tweet Video Downloader Bot
   After=network.target

   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/home/ubuntu/tweet-video-downloader
   ExecStart=/usr/bin/python3 app.py
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

4. **Start Service**
   ```bash
   sudo systemctl enable tweet-bot
   sudo systemctl start tweet-bot
   ```

### Keeping the Bot Alive on Free Tiers (e.g., Render)

Free hosting services like Render or Heroku often put applications to "sleep" after a period of inactivity to conserve resources. To prevent this and ensure your bot remains online 24/7, this project includes a keep-alive mechanism.

1.  **Health Check Endpoint**: The application exposes a `/health` endpoint that can be periodically pinged to signal that the bot is active.

2.  **Automated Pinging with GitHub Actions**: A pre-configured GitHub Actions workflow is included in `.github/workflows/health_check.yml`. This workflow automatically pings the `/health` endpoint every 10 minutes.

**How to Enable:**

To activate this feature, you only need to add your bot's public URL to your GitHub repository's secrets:

1.  Navigate to your repository on GitHub.
2.  Go to **Settings** > **Secrets and variables** > **Actions**.
3.  Click **New repository secret**.
4.  Create a secret with the following details:
    -   **Name**: `HEALTH_CHECK_URL`
    -   **Value**: `https://your-app-name.onrender.com/health` (replace with your actual Render/Heroku app URL).

Once the secret is added, the workflow will start running on its schedule, keeping your bot awake.

## 🤖 Bot Commands

| Command | Description | Usage |
|---------|-------------|-------|
| `/start` | Welcome message and basic instructions | `/start` |
| `/help` | Detailed help and feature overview | `/help` |
| `/quality` | Set your default video quality preference | `/quality` |
| `/stats` | View your download statistics | `/stats` |
| `/history` | View your last 10 downloads | `/history` |
| `/settings` | Configure personal bot settings | `/settings` |
| `/about` | Information about the bot and developer | `/about` |
| `/adminstats` | Admin dashboard (admin only) | `/adminstats` |

### Interactive Features

- **Thumbnail Preview**: See video info and thumbnail before downloading
- **Quality Selection**: Choose video quality via inline buttons
- **Cancel Option**: Cancel download before it starts
- **Progress Updates**: Real-time download progress bars
- **Auto-Compression**: Large files automatically compressed
- **Error Handling**: User-friendly error messages with solutions
- **Format Options**: Multiple download format choices

## 🌐 API Endpoints

The bot exposes several useful web endpoints (available in both polling and webhook modes):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/dashboard` | GET | Web-based analytics dashboard |
| `/api/stats/dashboard` | GET | Dashboard statistics JSON API |
| `/health` | GET | Bot health status and statistics |
| `/webhook` | POST | Telegram webhook endpoint |
| `/webhook-info` | GET | Current webhook configuration |

### Health Check Response
```json
{
  "status": "healthy",
  "uptime": "2 days, 5 hours",
  "downloads_today": 156,
  "active_users": 45,
  "memory_usage": "234 MB",
  "version": "1.0.0"
}
```

## 📁 Project Structure

```
tweet-video-downloader/
├── 📄 app.py                  # Main application entry point
├── 📄 video_downloader.py     # Core video download functionality
├── 📄 config.py               # Configuration management
├── 📄 utils.py                # Utility functions and helpers
├── 📄 database.py             # User statistics storage (Redis-backed)
├── 📄 rate_limiter.py         # Rate limiting implementation
├── 📄 redis_client.py         # Redis connection and utilities
├── 📄 logger.py               # Logging configuration
├── 📄 requirements.txt        # Python dependencies
├── 📄 Dockerfile              # Docker container configuration
├── 📄 docker-compose.yml      # Docker Compose setup
├── 📄 .env.example            # Environment variables template
├── 📄 .gitignore              # Git ignore rules
├── 📄 LICENSE                 # MIT License
├── 📄 README.md               # This comprehensive guide
├── 📁 tests/                  # Unit and integration tests
│   ├── test_downloader.py
│   ├── test_utils.py
│   └── test_bot.py
├── 📁 docs/                   # Additional documentation
│   ├── API.md
│   └── DEPLOYMENT.md
└── 📁 temp/                   # Temporary download directory
```

## 🐛 Troubleshooting

### Common Issues

#### Bot Not Responding
```bash
# Check if bot token is correct
python -c "import requests; print(requests.get('https://api.telegram.org/bot<YOUR_TOKEN>/getMe').json())"

# Verify webhook URL (if using webhook mode)
curl -X GET "https://api.telegram.org/bot<YOUR_TOKEN>/getWebhookInfo"
```

#### Download Failures
- **Check internet connection**
- **Verify Twitter URL format**
- **Ensure sufficient disk space**
- **Check rate limits**

#### Memory Issues
```bash
# Monitor memory usage
free -h

# Check Python process memory
ps aux | grep python
```

### Debug Mode

Enable debug logging in your `.env` file:
```env
LOG_LEVEL=DEBUG
```

### Getting Help

1. **Check Logs**: Review console output for error messages
2. **Test URLs**: Verify Twitter URLs work in browser
3. **Update Dependencies**: Run `pip install -r requirements.txt --upgrade`
4. **Restart Bot**: Sometimes a simple restart fixes issues

## 🧪 Testing

Run the test suite to ensure everything works correctly:

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html
```

## 📊 Monitoring & Analytics

### Built-in Metrics
- Download success/failure rates
- User activity statistics
- Performance metrics
- Error tracking

### External Monitoring
The bot supports integration with monitoring services:
- **Prometheus**: Metrics endpoint at `/metrics`
- **Grafana**: Dashboard templates available
- **Sentry**: Error tracking and performance monitoring

## 🤝 Contributing

We welcome contributions! Here's how you can help:

### Development Setup

1. **Fork the Repository**
   ```bash
   git fork https://github.com/Fl3xxRichie/tweet-video-downloader.git
   ```

2. **Create Feature Branch**
   ```bash
   git checkout -b feature/amazing-feature
   ```

3. **Install Development Dependencies**
   ```bash
   pip install -r requirements-dev.txt
   ```

4. **Make Changes and Test**
   ```bash
   pytest
   black . --check
   flake8
   ```

5. **Submit Pull Request**

### Contribution Guidelines

- **Code Quality**: Follow PEP 8 style guidelines
- **Testing**: Add tests for new features
- **Documentation**: Update README and docstrings
- **Commit Messages**: Use conventional commit format

### Areas for Contribution

- 🌍 **Internationalization**: Add multi-language support
- 🎨 **UI/UX**: Improve user interface and experience
- 📊 **Analytics**: Enhanced download statistics
- 🔧 **Features**: New download options and formats
- 🐛 **Bug Fixes**: Report and fix issues
- 📚 **Documentation**: Improve guides and examples

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2024 Fl3xxRichie

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 💬 Support

### Getting Help

- 📧 **Email**: [support@example.com](mailto:support@example.com)
- 💬 **Telegram**: [@Fl3xxRichie](https://t.me/Fl3xxRichie)
- 🐛 **Issues**: [GitHub Issues](https://github.com/Fl3xxRichie/tweet-video-downloader/issues)
- 💡 **Discussions**: [GitHub Discussions](https://github.com/Fl3xxRichie/tweet-video-downloader/discussions)

### Frequently Asked Questions

**Q: What Twitter URL formats are supported?**
A: All standard Twitter/X URLs including twitter.com, x.com, mobile versions, and various shortened formats.

**Q: Is there a file size limit?**
A: Yes, configurable via MAX_FILE_SIZE_MB in your .env file (default: 50MB).

**Q: Can I host this bot myself?**
A: Absolutely! The bot is designed for easy self-hosting on various platforms.

**Q: Is this bot free to use?**
A: Yes, the bot is completely free and open-source under MIT license.

---

<div align="center">

### 🌟 Star this repository if you found it helpful!

[![GitHub stars](https://img.shields.io/github/stars/Fl3xxRichie/tweet-video-downloader.svg?style=social&label=Star)](https://github.com/Fl3xxRichie/tweet-video-downloader)
[![GitHub forks](https://img.shields.io/github/forks/Fl3xxRichie/tweet-video-downloader.svg?style=social&label=Fork)](https://github.com/Fl3xxRichie/tweet-video-downloader/fork)

**Made with ❤️ by [Fl3xxRichie](https://github.com/Fl3xxRichie)**

</div>
