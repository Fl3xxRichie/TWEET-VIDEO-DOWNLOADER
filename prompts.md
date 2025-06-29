# AI Prompt: Build Twitter Video Downloader Bot for Koyeb Deployment

## Project Overview
Create a complete Twitter video downloader bot using Python that can be deployed on Koyeb. The bot should accept Twitter URLs via Telegram and return downloaded videos to users.

## Technical Requirements

### Core Stack
- **Language:** Python 3.9+
- **Video Extraction:** yt-dlp library
- **Bot Framework:** python-telegram-bot (latest version)
- **Web Framework:** FastAPI (for webhooks)
- **Deployment:** Koyeb-ready configuration
- **Storage:** Temporary local storage with auto-cleanup
- **Rate Limiting:** Built-in user rate limiting

### Project Structure
```
twitter-video-bot/
├── app.py                 # Main bot application
├── config.py             # Configuration management
├── video_downloader.py   # Video download logic
├── utils.py              # Helper functions
├── requirements.txt      # Dependencies
├── Dockerfile           # Koyeb deployment
├── .env.example         # Environment variables template
├── README.md            # Documentation
└── .gitignore           # Git ignore file
```

## Feature Requirements

### Core Features
1. **URL Validation:** Detect and validate Twitter/X URLs
2. **Video Download:** Extract and download videos using yt-dlp
3. **Quality Selection:** Let users choose video quality (HD 1080p, SD 720p, SD 480p, Audio Only)
4. **Interactive UI:** Inline keyboard buttons for quality selection
5. **File Management:** Temporary storage with automatic cleanup
6. **User Interface:** Clean Telegram bot with command support
7. **Error Handling:** Comprehensive error messages and logging
8. **Rate Limiting:** Prevent abuse (e.g., 5 downloads per user per hour)
9. **User Preferences:** Remember user's preferred quality setting

### Bot Commands
- `/start` - Welcome message and instructions
- `/help` - Usage guide and supported formats
- `/quality` - Set preferred video quality (HD/SD/Audio)
- `/stats` - Show bot usage statistics (admin only)
- Direct URL sending - Main functionality with quality options

### Video Quality System
1. **Quality Options:**
   - **HD (1080p)** - Best quality, larger file size
   - **SD (720p)** - Good quality, moderate file size
   - **SD (480p)** - Lower quality, smaller file size
   - **Audio Only** - Extract audio track only (MP3)

2. **User Experience:**
   - When user sends Twitter URL, show inline keyboard with quality options
   - Remember user's preferred quality for future downloads
   - Show estimated file size for each quality option
   - Allow quality override with `/quality` command

3. **Technical Implementation:**
   - Use yt-dlp format selection: `best[height<=1080]`, `best[height<=720]`, etc.
   - Implement quality-based file size estimation
   - Store user preferences in memory (or simple JSON file)
   - Add quality indicators in download progress messages

## Technical Specifications

### Dependencies (requirements.txt)
```
python-telegram-bot>=20.0
yt-dlp>=2023.12.30
fastapi>=0.104.0
uvicorn>=0.24.0
python-multipart>=0.0.6
python-dotenv>=1.0.0
aiofiles>=23.2.1
```

### Environment Variables
```
BOT_TOKEN=your_telegram_bot_token
WEBHOOK_URL=your_koyeb_app_url
PORT=8000
MAX_FILE_SIZE_MB=50
RATE_LIMIT_PER_HOUR=5
LOG_LEVEL=INFO
```

### Koyeb Deployment Config
- **Runtime:** Python 3.9+
- **Port:** 8000 (configurable via environment)
- **Build Command:** `pip install -r requirements.txt`
- **Run Command:** `python app.py`
- **Health Check:** `/health` endpoint
- **Auto-scaling:** Based on CPU/memory usage

## Implementation Guidelines

### Code Structure
1. **Modular Design:** Separate concerns into different files
2. **Async/Await:** Use async programming for better performance
3. **Error Handling:** Try-catch blocks with specific error messages
4. **Logging:** Comprehensive logging for debugging
5. **Clean Code:** Follow PEP 8 style guidelines

### Security & Best Practices
1. **Input Validation:** Sanitize all user inputs
2. **File Cleanup:** Auto-delete temporary files after 10 minutes
3. **Rate Limiting:** Implement user-based rate limiting
4. **Error Messages:** User-friendly error messages without exposing internals
5. **Environment Variables:** Never hardcode sensitive data

### Performance Optimization
1. **Async Operations:** Non-blocking file operations
2. **Memory Management:** Stream large files instead of loading into memory
3. **Timeout Handling:** Set reasonable timeouts for downloads
4. **Concurrent Downloads:** Handle multiple users simultaneously

## Detailed Implementation Steps

### Step 1: Project Setup
- Create virtual environment
- Install dependencies
- Set up project structure
- Configure environment variables

### Step 2: Core Bot Logic
- Initialize Telegram bot with webhook support
- Create message handlers for URLs and commands
- Implement URL validation and parsing
- Add user rate limiting system

### Step 3: Video Download System
- Configure yt-dlp with quality-specific format selection
- Implement download function with quality parameters
- Create inline keyboard for quality selection
- Add file size estimation and validation
- Implement user preference storage system
- Create temporary file management system

### Step 4: FastAPI Integration
- Set up webhook endpoint for Telegram
- Add health check endpoint
- Implement proper error handling middleware
- Configure CORS if needed

### Step 5: Deployment Preparation
- Create Dockerfile for Koyeb
- Set up environment variable configuration
- Add logging configuration
- Test local deployment

### Step 6: Koyeb Deployment
- Configure Koyeb service
- Set up environment variables
- Deploy and test webhook functionality
- Monitor logs and performance

## Error Handling Requirements

### User-Facing Errors
- Invalid URL format
- Video not found or private
- File too large
- Rate limit exceeded
- Download failed

### Technical Errors
- Network timeouts
- Storage issues
- API rate limits
- Server errors

## Testing Requirements
- Unit tests for core functions
- Integration tests for bot commands
- Mock testing for external APIs
- Error scenario testing

## Documentation Requirements
- Clear README with setup instructions
- Environment variable documentation
- API endpoint documentation
- Troubleshooting guide

## Success Criteria
- Bot responds to Twitter URLs within 30 seconds
- Handles at least 10 concurrent users
- 99% uptime on Koyeb
- Clear error messages for all failure cases
- Proper cleanup of temporary files
- Rate limiting works correctly

## Additional Considerations
- **Quality Selection UI:** Implement elegant inline keyboards for quality choice
- **Smart Defaults:** Auto-select best quality that fits file size limits
- **Progress Indicators:** Show download progress with quality information
- Add support for Twitter Spaces audio (future enhancement)
- Add usage analytics with quality preference tracking
- Consider adding support for Twitter threads with videos

Please implement this bot following these specifications, ensuring it's production-ready for Koyeb deployment with proper error handling, logging, and user experience.
