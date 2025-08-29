# downloader/utils.py
# Utility functions for YouTube downloader (ffmpeg checks, filename sanitize, URL normalize, etc.)

import os
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

def sanitize_filename(filename: str) -> str:
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename[:200]

def get_default_download_path() -> Path:
    if os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as key:
                downloads_path = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")[0]
                return Path(downloads_path) / "YouTube_Downloads"
        except:
            return Path.home() / "Downloads" / "YouTube_Downloads"
    else:
        return Path.home() / "Downloads" / "YouTube_Downloads"

def normalize_youtube_url(url: str) -> str:
    try:
        p = urlparse(url)
        if p.netloc.endswith('youtube.com'):
            return url
        if p.netloc.endswith('youtu.be'):
            video_id = p.path.lstrip('/')
            qs = parse_qs(p.query)
            qs_flat = []
            for k, vals in qs.items():
                for v in vals:
                    qs_flat.append((k, v))
            qs_flat.insert(0, ('v', video_id))
            new_qs = urlencode(qs_flat)
            new_url = urlunparse(('https', 'www.youtube.com', '/watch', '', new_qs, ''))
            return new_url
    except Exception:
        pass
    return url

def is_valid_youtube_url(url: str) -> bool:
    youtube_patterns = [
        r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+',
        r'https?://(?:www\.)?youtube\.com/shorts/[\w-]+',
        r'https?://youtu\.be/[\w-]+',
        r'https?://m\.youtube\.com/watch\?v=[\w-]+',
        r'https?://(?:www\.)?youtube\.com/playlist\?list=[\w-]+',
        r'https?://(?:www\.)?youtube\.com/watch\?.*[&?]list=[\w-]+',
    ]
    return any(re.search(pattern, url) for pattern in youtube_patterns)

def is_playlist_url(url: str) -> bool:
    if 'list=' in url:
        return True
    playlist_patterns = [
        r'https?://(?:www\.)?youtube\.com/playlist\?list=[\w-]+',
        r'https?://(?:www\.)?youtube\.com/watch\?.*[&?]list=[\w-]+',
    ]
    return any(re.search(pattern, url) for pattern in playlist_patterns)
