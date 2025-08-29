# downloader/core.py
# Core YouTube download logic (class YouTubeDownloader, all main methods)

from pathlib import Path
from typing import Dict, Any, List, Optional, Set
import yt_dlp
from tqdm import tqdm
import subprocess
import os
from .utils import sanitize_filename, get_default_download_path, normalize_youtube_url, is_valid_youtube_url, is_playlist_url

class YouTubeDownloader:
    # ...existing code from youtube.py, but use utils for helpers...
    pass
