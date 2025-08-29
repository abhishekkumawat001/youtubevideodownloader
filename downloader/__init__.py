"""
Enhanced YouTube Video Downloader Package

A comprehensive YouTube video downloader with advanced features:
- Queue management and concurrent downloads
- Smart quality selection with fallback chains
- Progress tracking and download resume
- Configuration profiles and error handling
- Download history and statistics
"""

from .core import DownloadManager, YouTubeDownloader, DownloadPriority, DownloadTask
from .config import ConfigManager, DownloadProfile
from .error_handling import ErrorHandler, RetryStrategy, ErrorCategory
from .progress import ProgressTracker, StateManager, DownloadHistory, DownloadState
from .cli import main as cli_main

__version__ = "2.0.0"
__author__ = "YouTube Downloader Team"

# Backwards compatibility
from .core import YouTubeDownloader as YouTubeDownloaderLegacy

__all__ = [
    'DownloadManager',
    'YouTubeDownloader',
    'YouTubeDownloaderLegacy',
    'ConfigManager',
    'DownloadProfile',
    'DownloadPriority',
    'DownloadTask',
    'ErrorHandler',
    'RetryStrategy',
    'ErrorCategory',
    'ProgressTracker',
    'StateManager',
    'DownloadHistory',
    'DownloadState',
    'cli_main'
]
