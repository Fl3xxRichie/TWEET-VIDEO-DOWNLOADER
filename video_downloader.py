import os
import yt_dlp
import time
import asyncio
import logging
import shutil
from typing import Dict, Optional, Callable
from config import Config

logger = logging.getLogger(__name__)

class VideoDownloader:
    def __init__(self):
        self.download_path = "downloads"
        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)

        # Check if ffmpeg is available
        self.ffmpeg_available = shutil.which('ffmpeg') is not None
        if not self.ffmpeg_available:
            logger.warning("ffmpeg not found! High quality downloads (1080p+) and format merging will be limited.")

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

                # Handle YouTube specific requirements when ffmpeg is missing
                # We need this in get_video_info too, otherwise extraction fails on some systems
                if 'youtube.com' in url or 'youtu.be' in url:
                     if not self.ffmpeg_available:
                        ydl_opts['extractor_args'] = {'youtube': {'player_client': ['android']}}

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await loop.run_in_executor(None, extract_info)

            if not info:
                return None

            # Extract size estimates for different qualities
            size_estimates = {}
            formats = info.get('formats', [])

            for fmt in formats:
                # Handle None values for height - some platforms don't provide this
                height = fmt.get('height')
                if height is None:
                    height = 0
                filesize = fmt.get('filesize') or fmt.get('filesize_approx') or 0

                if filesize and filesize > 0:
                    size_mb = filesize / (1024 * 1024)
                    size_str = f"{size_mb:.1f}MB"

                    if height >= 1080:
                        size_estimates['hd'] = size_str
                    elif height >= 720:
                        size_estimates['720p'] = size_str
                    elif height >= 480:
                        size_estimates['480p'] = size_str
                    elif height >= 360:
                        size_estimates['360p'] = size_str

            # Audio estimate (usually much smaller)
            if formats:
                audio_sizes = [f.get('filesize') or f.get('filesize_approx') or 0
                               for f in formats if f.get('acodec') != 'none']
                audio_sizes = [s for s in audio_sizes if s > 0]  # Filter out zeros
                if audio_sizes:
                    audio_size = min(audio_sizes)
                    size_estimates['audio'] = f"{audio_size / (1024 * 1024):.1f}MB"
                else:
                    size_estimates['audio'] = "~5MB"

            return {
                'title': info.get('title', 'Video'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail'),
                'uploader': info.get('uploader', 'Unknown'),
                'size_estimates': size_estimates
            }

        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return None

    async def download_video(self, url: str, quality: str, progress_callback: Optional[Callable] = None, max_retries: int = 3) -> Dict:
        """Download video with specified quality and automatic retry"""
        main_loop = asyncio.get_running_loop()
        timestamp = int(time.time())
        filename = f"video_{timestamp}"
        output_path = os.path.join(self.download_path, filename)

        logger.info(f"Starting download for URL: {url} with quality: {quality}")

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                if attempt > 1:
                    logger.info(f"Retry attempt {attempt}/{max_retries} for {url}")
                    if progress_callback:
                        await progress_callback({'status': 'retrying', 'attempt': attempt, 'max_retries': max_retries})

                # Quality format selection - platform-aware
                format_selector = self._get_format_selector(quality, url)

                # Progress hook
                def progress_hook(d):
                    if progress_callback:
                        try:
                            # Schedule the async callback to run on the main event loop
                            asyncio.run_coroutine_threadsafe(progress_callback(d), main_loop)
                        except Exception as e:
                            logger.error(f"Progress callback error: {e}")

                # yt-dlp options - avoid ffmpeg-dependent options
                ydl_opts = {
                    'outtmpl': f'{output_path}.%(ext)s',
                    'progress_hooks': [progress_hook],
                    'no_warnings': True,
                    'extractaudio': quality == 'audio',
                    'audioformat': 'mp3' if quality == 'audio' else None,
                    # Skip post-processing that requires ffmpeg
                    'postprocessors': [],
                }

                # Handle YouTube specific requirements when ffmpeg is missing
                is_youtube = 'youtube.com' in url or 'youtu.be' in url
                if is_youtube and not self.ffmpeg_available:
                     # Use Android client to expose legacy formats (18, 22) that are direct downloads
                    ydl_opts['extractor_args'] = {'youtube': {'player_client': ['android']}}

                # Only set format if format_selector is not None (YouTube uses auto-select)
                if format_selector:
                    ydl_opts['format'] = format_selector

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
                    last_error = 'Download completed but file not found'
                    continue  # Retry

            except asyncio.TimeoutError:
                logger.error(f"Download timed out for URL: {url} (attempt {attempt})")
                last_error = 'Download timed out after 5 minutes'
                # Clean up partial files before retry
                self._cleanup_partial_files(timestamp)
                continue  # Retry

            except Exception as e:
                error_msg = str(e)
                logger.error(f"Download error for {url} (attempt {attempt}): {error_msg}", exc_info=True)
                last_error = error_msg
                # Clean up partial files before retry
                self._cleanup_partial_files(timestamp)
                continue  # Retry

        # All retries exhausted
        logger.error(f"All {max_retries} download attempts failed for {url}")
        return {
            'success': False,
            'error': f"Download failed after {max_retries} attempts: {last_error}"
        }

    def _cleanup_partial_files(self, timestamp: int):
        """Clean up partial download files"""
        try:
            for file in os.listdir(self.download_path):
                if file.startswith(f"video_{timestamp}"):
                    os.remove(os.path.join(self.download_path, file))
        except Exception as cleanup_error:
            logger.error(f"Error during cleanup for {timestamp}: {cleanup_error}")


    def _get_format_selector(self, quality: str, url: str = "") -> str:
        """Get yt-dlp format selector based on quality choice and platform.
        Uses pre-merged formats to avoid requiring ffmpeg for stream merging.
        Platform-aware to handle YouTube Shorts' limited format options.
        """
        # Check if this is a YouTube URL (including Shorts)
        is_youtube = 'youtube.com' in url or 'youtu.be' in url

        if is_youtube:
            # If ffmpeg is NOT available, we MUST fallback to single-file formats
            if not self.ffmpeg_available:
                # Prioritize format 22 (720p) and 18 (360p) which are often available as direct downloads on Android client
                # Standard 'best' might pick a video-only stream
                compat_formats = '22/18/best[ext=mp4]/best'
                if quality == 'audio':
                    return 'bestaudio/best'
                return compat_formats

            # YouTube Shorts work best with no format specified - let yt-dlp auto-select
            # This avoids "format not available" errors
            # Return None to indicate no format should be specified
            return None
        else:
            # For TikTok, Instagram, Twitter - use height-based selection
            format_selectors = {
                'hd': 'best[height<=1080][ext=mp4]/best[height<=1080]/best[ext=mp4]/best',
                '720p': 'best[height<=720][ext=mp4]/best[height<=720]/best[ext=mp4]/best',
                '480p': 'best[height<=480][ext=mp4]/best[height<=480]/best[ext=mp4]/best',
                '360p': 'best[height<=360][ext=mp4]/best[height<=360]/best[ext=mp4]/best',
                'audio': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best'
            }
            return format_selectors.get(quality, format_selectors.get('720p', 'best'))

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

    async def compress_video(
        self,
        file_path: str,
        target_size_mb: float = 45.0,
        progress_callback: Optional[Callable] = None
    ) -> Dict:
        """
        Compress video to target size using ffmpeg.
        Returns dict with success status and compressed file path.
        """
        import subprocess
        import shutil

        try:
            # Check if ffmpeg is available
            if not shutil.which('ffmpeg'):
                logger.warning("ffmpeg not found, skipping compression")
                return {'success': False, 'error': 'ffmpeg not available', 'file_path': file_path}

            # Get current file size
            current_size_mb = os.path.getsize(file_path) / (1024 * 1024)

            if current_size_mb <= target_size_mb:
                logger.info(f"File already under {target_size_mb}MB, no compression needed")
                return {'success': True, 'compressed': False, 'file_path': file_path}

            # Calculate target bitrate
            # Get video duration using ffprobe
            duration_cmd = [
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', file_path
            ]

            loop = asyncio.get_event_loop()

            def get_duration():
                result = subprocess.run(duration_cmd, capture_output=True, text=True)
                return float(result.stdout.strip()) if result.stdout.strip() else 0

            duration = await loop.run_in_executor(None, get_duration)

            if duration <= 0:
                logger.warning("Could not determine video duration")
                return {'success': False, 'error': 'Could not determine duration', 'file_path': file_path}

            # Calculate target bitrate (in kbps)
            # Target size in kilobits, minus 10% for audio
            target_total_bitrate = (target_size_mb * 8 * 1024 * 0.9) / duration
            video_bitrate = int(target_total_bitrate * 0.9)  # 90% for video
            audio_bitrate = 128  # 128 kbps for audio

            # Generate compressed filename
            base, ext = os.path.splitext(file_path)
            compressed_path = f"{base}_compressed{ext}"

            # Compress with ffmpeg
            compress_cmd = [
                'ffmpeg', '-i', file_path,
                '-c:v', 'libx264', '-preset', 'fast',
                '-b:v', f'{video_bitrate}k',
                '-c:a', 'aac', '-b:a', f'{audio_bitrate}k',
                '-y',  # Overwrite output
                compressed_path
            ]

            logger.info(f"Compressing video from {current_size_mb:.1f}MB to ~{target_size_mb}MB")

            if progress_callback:
                await progress_callback({'status': 'compressing', 'target_mb': target_size_mb})

            def run_compression():
                subprocess.run(compress_cmd, capture_output=True)

            await loop.run_in_executor(None, run_compression)

            if os.path.exists(compressed_path):
                new_size_mb = os.path.getsize(compressed_path) / (1024 * 1024)
                logger.info(f"Compression complete: {current_size_mb:.1f}MB -> {new_size_mb:.1f}MB")

                # Remove original, keep compressed
                os.remove(file_path)

                return {
                    'success': True,
                    'compressed': True,
                    'file_path': compressed_path,
                    'original_size_mb': round(current_size_mb, 2),
                    'new_size_mb': round(new_size_mb, 2)
                }
            else:
                logger.error("Compression failed, compressed file not found")
                return {'success': False, 'error': 'Compression failed', 'file_path': file_path}

        except Exception as e:
            logger.error(f"Compression error: {e}")
            return {'success': False, 'error': str(e), 'file_path': file_path}
