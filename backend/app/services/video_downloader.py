"""Video download service using yt-dlp"""
import yt_dlp
import copy
import os
import re
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import logging

logger = logging.getLogger(__name__)


def parse_subtitle_to_text(path: Path) -> str:
    """
    Parse SRT or VTT subtitle file to plain text (strip timestamps and sequence numbers).
    Returns joined text lines.
    """
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.warning("Failed to read subtitle file %s: %s", path, e)
        return ""
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip sequence number (digits only)
        if line.isdigit():
            continue
        # Skip SRT/VTT timestamp line (e.g. 00:00:00,000 --> 00:00:02,000 or 00:00:00.000 --> 00:00:02.000)
        if re.match(r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}", line):
            continue
        # Skip WEBVTT header
        if line.upper().startswith("WEBVTT"):
            continue
        # Skip VTT note/cue identifier (e.g. NOTE or 1)
        if line.upper().startswith("NOTE ") or (len(line) <= 4 and line.isalnum()):
            if line.upper().startswith("NOTE "):
                continue
            if re.match(r"^\d+$", line):
                continue
        lines.append(line)
    return " ".join(lines).strip()


class VideoDownloadError(Exception):
    """Structured download error so callers can decide retry/pause behavior."""

    def __init__(self, message: str, *, blocked: bool = False, retryable: bool = False):
        super().__init__(message)
        self.blocked = blocked
        self.retryable = retryable


def _looks_like_blocked_error(message: str) -> bool:
    """Detect errors that indicate YouTube is blocking downloads (login/bot check)."""
    if not message:
        return False
    msg = message.lower()
    needles = [
        "sign in to confirm you're not a bot",
        "sign in to confirm you’re not a bot",
        "confirm you’re not a bot",
        "confirm you're not a bot",
        "use --cookies-from-browser or --cookies",
        "captcha",
        "verify that you are not a robot",
        "this helps protect our community",
        "cookies are no longer valid",
    ]
    return any(n in msg for n in needles)


def _looks_retryable(message: str) -> bool:
    """Heuristic for transient errors worth retrying."""
    if not message:
        return False
    msg = message.lower()
    needles = [
        "timed out",
        "timeout",
        "temporarily unavailable",
        "connection reset",
        "connection aborted",
        "connection refused",
        "network is unreachable",
        "tls",
        "ssl",
        "proxy",
        "http error 429",
        "http error 500",
        "http error 502",
        "http error 503",
        "http error 504",
        "unable to download",
        "failed to establish a new connection",
    ]
    return any(n in msg for n in needles)


def _looks_like_format_unavailable(message: str) -> bool:
    """Detect yt-dlp errors caused by overly strict format selection."""
    if not message:
        return False
    msg = message.lower()
    return "requested format is not available" in msg


def _looks_like_subtitle_only_error(message: str) -> bool:
    """Detect errors that are only about subtitle download (e.g. 429 on subtitle URL)."""
    if not message:
        return False
    msg = message.lower()
    if "subtitle" not in msg:
        return False
    return "unable to download" in msg or "429" in msg or "too many requests" in msg


def looks_like_membership_only_error(message: str) -> bool:
    """Detect errors indicating the video is member-only / requires channel membership."""
    if not message:
        return False
    msg = message.lower()
    return (
        "member" in msg
        and (
            "members-only" in msg
            or "member-only" in msg
            or "join this channel" in msg
            or "join the channel" in msg
        )
    )


class VideoDownloader:
    """Download YouTube videos using yt-dlp"""
    
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def download(self, url: str, progress_callback=None) -> Dict[str, Any]:
        """
        Download video from URL
        
        Args:
            url: YouTube video URL
            progress_callback: Optional callback function for progress updates
            
        Returns:
            Dict with video info including file path
        """
        preferred_format = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        fallback_format = 'bestvideo+bestaudio/best'

        # Extractor args: keep conservative defaults.
        youtube_extractor_args: Dict[str, Any] = {'player_client': ['android', 'ios', 'web']}

        remote_components_env = os.getenv("YTDLP_REMOTE_COMPONENTS", "").strip()
        remote_components: Optional[List[str]] = None
        if remote_components_env:
            # Allow comma-separated values, e.g. "ejs:github" or "ejs:github,ejs:npm"
            remote_components = [c.strip() for c in remote_components_env.split(",") if c.strip()]

        ydl_opts = {
            'format': preferred_format,
            'outtmpl': str(self.storage_dir / '%(id)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            # Only download the video/audio; do not attempt subtitles in the queue path.
            # This keeps the flow simpler and avoids extra subtitle HTTP requests.
            'javascript_runtime': os.getenv("YTDLP_JAVASCRIPT_RUNTIME", "deno"),
            # Add options to bypass YouTube restrictions
            'extractor_args': {
                'youtube': {
                    **youtube_extractor_args,
                }
            },
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'referer': 'https://www.youtube.com/',
            # Retry options (we default to NO automatic retries; manual retry only)
            'retries': max(0, int(os.getenv("YTDLP_RETRIES", "0"))),
            'fragment_retries': max(0, int(os.getenv("YTDLP_FRAGMENT_RETRIES", "0"))),
            'ignoreerrors': False,
            # Additional headers
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
        }

        if remote_components:
            # Enable downloading EJS remote components (challenge solver scripts)
            ydl_opts['remote_components'] = remote_components
        
        if progress_callback:
            def hook(d):
                if d.get('status') != 'downloading':
                    return
                # Subtitle downloads often have total_bytes=None; avoid int/NoneType
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                if total is None or total <= 0:
                    return
                downloaded = d.get('downloaded_bytes')
                if downloaded is not None:
                    percent = (downloaded / total) * 100
                    progress_callback(percent)
            ydl_opts['progress_hooks'] = [hook]

        # Reject live streams: they would run forever (HLS segment loop) and flood logs.
        try:
            pre_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'extractor_args': {'youtube': {**youtube_extractor_args}},
            }
            if remote_components:
                pre_opts['remote_components'] = remote_components
            with yt_dlp.YoutubeDL(pre_opts) as ydl:
                pre_info = ydl.extract_info(url, download=False)
            if pre_info and pre_info.get('live_status') == 'is_live':
                raise VideoDownloadError(
                    "Live stream detected; download skipped. Add the video after the stream has ended.",
                    blocked=False,
                    retryable=False,
                )
        except VideoDownloadError:
            raise
        except Exception as e:
            # If pre-check fails (e.g. network), continue and let the main download fail or succeed
            logger.debug("Pre-check for live stream skipped: %s", e)

        # Extra retry wrapper (covers extractor failures that yt-dlp internal retries may not).
        # Default to 1 attempt: do not auto retry failed downloads.
        max_attempts = max(1, int(os.getenv("YTDLP_DOWNLOAD_MAX_ATTEMPTS", "1")))
        base_backoff = float(os.getenv("YTDLP_DOWNLOAD_RETRY_BACKOFF_SECONDS", "2.0"))

        last_err: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                # Use a deep copy so nested dicts (e.g. extractor_args) don't retain state on retry
                opts = copy.deepcopy(ydl_opts)
                if attempt > 1:
                    opts['format'] = fallback_format
                    opts['merge_output_format'] = 'mkv'

                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)

                # Find the downloaded file
                video_id = info.get('id', '')
                ext = info.get('ext', 'mp4')
                video_file = self.storage_dir / f"{video_id}.{ext}"

                if not video_file.exists():
                    # Try to find any file with the video ID
                    for file in self.storage_dir.glob(f"{video_id}.*"):
                        video_file = file
                        break

                # Extract upload date
                upload_date = None
                if 'upload_date' in info:
                    # yt-dlp returns upload_date as YYYYMMDD string
                    upload_date_str = info.get('upload_date')
                    if upload_date_str:
                        try:
                            from datetime import datetime
                            upload_date = datetime.strptime(upload_date_str, '%Y%m%d')
                        except (ValueError, TypeError):
                            logger.warning(f"Could not parse upload_date: {upload_date_str}")
                elif 'release_date' in info:
                    # Fallback to release_date
                    release_date_str = info.get('release_date')
                    if release_date_str:
                        try:
                            from datetime import datetime
                            upload_date = datetime.strptime(release_date_str, '%Y%m%d')
                        except (ValueError, TypeError):
                            logger.warning(f"Could not parse release_date: {release_date_str}")

                result: Dict[str, Any] = {
                    'id': video_id,
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'file_path': str(video_file),
                    'thumbnail': info.get('thumbnail'),
                    'description': info.get('description', ''),
                    'upload_date': upload_date,
                    # Common metadata (may be None depending on extractor)
                    'channel_id': info.get('channel_id'),
                    'channel': info.get('channel') or info.get('uploader'),
                    'uploader_id': info.get('uploader_id'),
                    'uploader': info.get('uploader'),
                    'view_count': info.get('view_count') or 0,
                    'like_count': info.get('like_count') or 0,
                }
                return result
            except Exception as e:
                last_err = e
                msg = str(e)

                if _looks_like_blocked_error(msg):
                    logger.error(f"Download blocked by YouTube auth/bot-check: {msg}")
                    raise VideoDownloadError(msg, blocked=True, retryable=False)

                # If our mp4/m4a preference is too strict, switch to fallback format.
                if attempt == 1 and _looks_like_format_unavailable(msg):
                    logger.warning(
                        f"Requested format unavailable for {url}. "
                        f"Retrying with fallback format selection (attempt 2/{max_attempts})."
                    )
                    if max_attempts >= 2:
                        continue

                retryable = _looks_retryable(msg)
                if attempt < max_attempts and retryable:
                    sleep_s = base_backoff * (2 ** (attempt - 1))
                    logger.warning(
                        f"Download attempt {attempt}/{max_attempts} failed (retryable): {msg}. "
                        f"Retrying in {sleep_s:.1f}s..."
                    )
                    time.sleep(sleep_s)
                    continue

                logger.error(f"Error downloading video (attempt {attempt}/{max_attempts}): {msg}")
                raise VideoDownloadError(f"Failed to download video: {msg}", blocked=False, retryable=retryable)

        raise VideoDownloadError(f"Failed to download video: {last_err}", blocked=False, retryable=False)
