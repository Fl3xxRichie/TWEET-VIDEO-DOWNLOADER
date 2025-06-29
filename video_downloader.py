import os
import yt_dlp
import time
import asyncio
import logging
from typing import Dict, Optional, Callable
from config import Config

logger = logging.getLogger(__name__)

class VideoDownloader:
    def __init__(self):
        self.download_path = "downloads"
        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)

    async def get_video_info(self, url: str) -> Optional[Dict]:
        """Get video information including size estimates"""
        try:
            loop = asyncio.get_event_loop()

            def extract_info():
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'skip_download': True,
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await loop.run_in_executor(None, extract_info)

            if not info:
                return None

            # Extract size estimates for different qualities
            size_estimates = {}
            formats = info.get('formats', [])

            for fmt in formats:
                height = fmt.get('height', 0)
                filesize = fmt.get('filesize') or fmt.get('filesize_approx', 0)

                if filesize:
                    size_mb = filesize / (1024 * 1024)
                    size_str = f"{size_mb:.1f}MB"

                    if height >= 1080:
                        size_estimates['hd'] = size_str
                    elif height >= 720:
                        size_estimates['720p'] = size_str
                    elif height >= 480:
                        size_estimates['480p'] = size_str

            # Audio estimate (usually much smaller)
            if formats:
                audio_size = min([f.get('filesize', 0) or 0 for f in formats if f.get('acodec') != 'none'])
                if audio_size:
                    size_estimates['audio'] = f"{audio_size / (1024 * 1024):.1f}MB"
                else:
                    size_estimates['audio'] = "~5MB"

            return {
                'title': info.get('title', 'Video'),
                'duration': info.get('duration', 0),
                'size_estimates': size_estimates
            }

        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return None

    async def download_video(self, url: str, quality: str, progress_callback: Optional[Callable] = None) -> Dict:
        """Download video with specified quality"""
        main_loop = asyncio.get_running_loop()
        timestamp = int(time.time())
        filename = f"video_{timestamp}"
        output_path = os.path.join(self.download_path, filename)

        logger.info(f"Starting download for URL: {url} with quality: {quality}")

        try:
            # Quality format selection
            format_selector = self._get_format_selector(quality)

            # Progress hook
            def progress_hook(d):
                if progress_callback:
                    try:
                        # Schedule the async callback to run on the main event loop
                        asyncio.run_coroutine_threadsafe(progress_callback(d), main_loop)
                    except Exception as e:
                        logger.error(f"Progress callback error: {e}")

            # yt-dlp options
            ydl_opts = {
                'format': format_selector,
                'outtmpl': f'{output_path}.%(ext)s',
                'progress_hooks': [progress_hook],
                'no_warnings': True,
                'extractaudio': quality == 'audio',
                'audioformat': 'mp3' if quality == 'audio' else None,
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
            }
            logger.debug(f"yt-dlp options: {ydl_opts}")

            # Check file size limit before download
            if Config.MAX_FILE_SIZE_MB:
                ydl_opts['max_filesize'] = Config.MAX_FILE_SIZE_MB * 1024 * 1024

            def download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

            # Run download with a 5-minute timeout
            await asyncio.wait_for(
                main_loop.run_in_executor(None, download),
                timeout=300.0
            )

            # Find the downloaded file
            downloaded_file = None
            for file in os.listdir(self.download_path):
                if file.startswith(f"video_{timestamp}"):
                    downloaded_file = os.path.join(self.download_path, file)
                    break

            if downloaded_file and os.path.exists(downloaded_file):
                file_size = os.path.getsize(downloaded_file) / (1024 * 1024)  # MB
                logger.info(f"Successfully downloaded: {downloaded_file} ({file_size:.2f}MB)")

                return {
                    'success': True,
                    'file_path': downloaded_file,
                    'file_size': f"{file_size:.2f}MB"
                }
            else:
                logger.error(f"Download completed but file not found for timestamp: {timestamp}")
                return {
                    'success': False,
                    'error': 'Download completed but file not found'
                }

        except asyncio.TimeoutError:
            logger.error(f"Download timed out for URL: {url}")
            return {'success': False, 'error': 'Download timed out after 5 minutes'}

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Download error for {url}: {error_msg}", exc_info=True)

            # Clean up any partial files
            try:
                for file in os.listdir(self.download_path):
                    if file.startswith(f"video_{timestamp}"):
                        os.remove(os.path.join(self.download_path, file))
            except Exception as cleanup_error:
                logger.error(f"Error during cleanup for {timestamp}: {cleanup_error}")

            return {
                'success': False,
                'error': "An unexpected error occurred during download."
            }

    def _get_format_selector(self, quality: str) -> str:
        """Get yt-dlp format selector based on quality choice"""
        format_selectors = {
            'hd': 'best[height<=1080][ext=mp4]/best[height<=1080]/best[ext=mp4]/best',
            '720p': 'best[height<=720][ext=mp4]/best[height<=720]/best[ext=mp4]/best',
            '480p': 'best[height<=480][ext=mp4]/best[height<=480]/best[ext=mp4]/best',
            'audio': 'bestaudio[ext=m4a]/bestaudio/best'
        }

        return format_selectors.get(quality, format_selectors['720p'])

    def cleanup_old_files(self, max_age_minutes: int = 10):
        """Clean up old downloaded files"""
        try:
            current_time = time.time()

            for filename in os.listdir(self.download_path):
                file_path = os.path.join(self.download_path, filename)
                file_age = current_time - os.path.getctime(file_path)

                if file_age > (max_age_minutes * 60):
                    os.remove(file_path)
                    logger.info(f"Cleaned up old file: {filename}")

        except Exception as e:
            logger.error(f"Cleanup error: {e}")
