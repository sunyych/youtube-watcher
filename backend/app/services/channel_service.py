"""YouTube channel resolution and latest-videos listing via yt-dlp."""
import logging
from typing import List, Optional, Tuple

import yt_dlp

logger = logging.getLogger(__name__)


def resolve_channel(channel_url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve a channel URL to (channel_id, channel_title).
    Supports /channel/UC..., /@handle, /c/custom.
    Uses the channel's /videos tab to avoid the homepage featuring members-only content.
    Returns (None, None) on failure.
    """
    if not channel_url or not channel_url.strip():
        return None, None
    url = channel_url.strip()
    if "/videos" not in url and "/streams" not in url and "/shorts" not in url:
        base = url.rstrip("/")
        url = f"{base}/videos"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "socket_timeout": 60,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            return None, None
        channel_id = info.get("channel_id") or info.get("id")
        channel_title = info.get("channel") or info.get("uploader") or info.get("title")
        if channel_id:
            return channel_id, (channel_title or None)
        return None, None
    except Exception as e:
        logger.warning("Failed to resolve channel %s: %s", url, e)
        return None, None


def fetch_latest_video_urls(
    channel_url: str,
    max_items: int = 20,
) -> List[str]:
    """
    Fetch up to max_items latest video URLs from a channel (no download).
    Returns list of watch URLs (https://www.youtube.com/watch?v=...).
    """
    if not channel_url or not channel_url.strip():
        return []
    url = channel_url.strip()
    # Ensure we hit the channel's videos tab for consistent playlist behavior
    if "/videos" not in url and "/streams" not in url and "/shorts" not in url:
        base = url.rstrip("/")
        url = f"{base}/videos"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "playlistend": max_items,
        "socket_timeout": 60,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            return []
        entries = info.get("entries") or []
        urls: List[str] = []
        seen_ids = set()
        for entry in entries:
            if not entry:
                continue
            vid = entry.get("id")
            if vid and vid not in seen_ids:
                seen_ids.add(vid)
                urls.append(f"https://www.youtube.com/watch?v={vid}")
        return urls
    except Exception as e:
        logger.warning("Failed to fetch channel videos %s: %s", url, e)
        return []
