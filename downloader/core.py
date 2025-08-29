"""
Unified Download Manager for YouTube Downloader
Combines functionality from youtube.py and provides queue system, smart quality selection,
progress tracking, error handling, and state management
"""

import asyncio
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Union, Callable
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from queue import Queue, PriorityQueue
from dataclasses import dataclass
from enum import Enum

import yt_dlp
from .config import ConfigManager, DownloadProfile
from .error_handling import ErrorHandler, RetryStrategy, with_retry, DownloadError, ErrorCategory
from .progress import ProgressTracker, StateManager, DownloadHistory, DownloadState, DownloadProgress
from .utils import sanitize_filename, get_default_download_path, normalize_youtube_url, is_valid_youtube_url, is_playlist_url


class DownloadPriority(Enum):
    """Download priority levels"""
    LOW = 3
    NORMAL = 2
    HIGH = 1
    URGENT = 0


@dataclass
class DownloadTask:
    """Represents a download task in the queue"""
    url: str
    priority: DownloadPriority = DownloadPriority.NORMAL
    config_overrides: Optional[Dict[str, Any]] = None
    callback: Optional[Callable] = None
    task_id: Optional[str] = None
    
    def __post_init__(self):
        if self.task_id is None:
            self.task_id = f"task_{int(time.time() * 1000000)}"
    
    def __lt__(self, other):
        """For priority queue ordering"""
        return self.priority.value < other.priority.value


class DownloadManager:
    """Unified download manager with queue system and advanced features"""
    
    def __init__(self, config_manager: Optional[ConfigManager] = None):
        # Core components
        self.config_manager = config_manager or ConfigManager()
        self.progress_tracker = ProgressTracker()
        self.state_manager = StateManager()
        self.download_history = DownloadHistory()
        self.error_handler = ErrorHandler()
        
        # Queue system
        self.download_queue = PriorityQueue()
        self.active_downloads: Dict[str, DownloadTask] = {}
        self.completed_downloads: Dict[str, DownloadTask] = {}
        self.failed_downloads: Dict[str, DownloadTask] = {}
        
        # Thread management
        self.executor = ThreadPoolExecutor(
            max_workers=self.config_manager.config.max_concurrent_downloads
        )
        self.is_running = False
        self.queue_thread: Optional[threading.Thread] = None
        
        # Statistics
        self.stats = {
            'total_queued': 0,
            'total_completed': 0,
            'total_failed': 0,
            'bytes_downloaded': 0,
            'start_time': time.time()
        }
        
        # Setup callbacks
        self.progress_tracker.add_callback(self._on_progress_update)
    
    def start_queue_processing(self):
        """Start the download queue processing"""
        if self.is_running:
            return
        
        self.is_running = True
        self.queue_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.queue_thread.start()
        print("Download queue processing started")
    
    def stop_queue_processing(self):
        """Stop the download queue processing"""
        self.is_running = False
        if self.queue_thread:
            self.queue_thread.join(timeout=5)
        print("Download queue processing stopped")
    
    def add_download(self, 
                    url: str, 
                    priority: DownloadPriority = DownloadPriority.NORMAL,
                    config_overrides: Optional[Dict[str, Any]] = None,
                    callback: Optional[Callable] = None) -> str:
        """Add a download to the queue"""
        
        # Validate URL
        if not is_valid_youtube_url(url):
            raise ValueError(f"Invalid YouTube URL: {url}")
        
        # Normalize URL
        url = normalize_youtube_url(url)
        
        # Create task
        task = DownloadTask(
            url=url,
            priority=priority,
            config_overrides=config_overrides or {},
            callback=callback
        )
        
        # Add to queue
        self.download_queue.put(task)
        self.stats['total_queued'] += 1
        
        print(f"Added download to queue: {url} (Priority: {priority.name})")
        return task.task_id  # type: ignore
    
    def add_batch_downloads(self, 
                           urls: List[str], 
                           priority: DownloadPriority = DownloadPriority.NORMAL,
                           config_overrides: Optional[Dict[str, Any]] = None) -> List[str]:
        """Add multiple downloads to the queue"""
        task_ids = []
        for url in urls:
            try:
                task_id = self.add_download(url, priority, config_overrides)
                task_ids.append(task_id)
            except Exception as e:
                print(f"Error adding {url} to queue: {e}")
        return task_ids
    
    def _process_queue(self):
        """Process downloads from the queue"""
        while self.is_running:
            try:
                # Check if we can start more downloads
                if len(self.active_downloads) >= self.config_manager.config.max_concurrent_downloads:
                    time.sleep(0.1)
                    continue
                
                # Get next task
                try:
                    task = self.download_queue.get(timeout=1)
                except:
                    continue
                
                # Start download
                self.active_downloads[task.task_id] = task
                future = self.executor.submit(self._download_single, task)
                
                # Handle completion
                def on_complete(fut):
                    result = False
                    try:
                        result = fut.result()
                        if result:
                            self.completed_downloads[task.task_id] = task
                            self.stats['total_completed'] += 1
                        else:
                            self.failed_downloads[task.task_id] = task
                            self.stats['total_failed'] += 1
                    except Exception as e:
                        self.failed_downloads[task.task_id] = task
                        self.stats['total_failed'] += 1
                        print(f"Download failed: {e}")
                    finally:
                        self.active_downloads.pop(task.task_id, None)
                        if task.callback:
                            try:
                                task.callback(task, result)
                            except Exception as e:
                                print(f"Callback error: {e}")
                
                future.add_done_callback(on_complete)
                
            except Exception as e:
                print(f"Error in queue processing: {e}")
                time.sleep(1)
    
    def _download_single(self, task: DownloadTask) -> bool:
        """Download a single video"""
        try:
            # Check if we can resume
            if self.state_manager.can_resume_download(task.url):
                print(f"Resuming download: {task.url}")
                saved_progress = self.state_manager.get_download_state(task.url)
                if saved_progress:
                    self.progress_tracker.downloads[task.url] = saved_progress
            
            # Get video info
            video_info = self.get_video_info(task.url)
            if not video_info:
                return False
            
            # Start progress tracking
            progress = self.progress_tracker.start_download(
                task.url, 
                video_info.get('title', 'Unknown'),
                format=self.config_manager.config.format,
                quality=self.config_manager.config.quality
            )
            
            # Merge config overrides
            config = self.config_manager.config
            if task.config_overrides:
                for key, value in task.config_overrides.items():
                    setattr(config, key, value)
            
            # Setup yt-dlp options
            ydl_opts = self.config_manager.get_yt_dlp_options()
            ydl_opts.update({
                'progress_hooks': [lambda d: self._progress_hook(d, task.url)],
                'outtmpl': os.path.join(config.output_dir, '%(title)s.%(ext)s'),
            })
            
            # Add error handling and retry
            retry_strategy = RetryStrategy(
                max_retries=config.max_retries,
                base_delay=config.retry_delay,
                exponential_backoff=config.exponential_backoff
            )
            
            @with_retry(retry_strategy, self.error_handler)
            def download_with_retry():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([task.url])
            
            # Perform download
            download_with_retry()
            
            # Mark as completed
            self.progress_tracker.complete_download(task.url)
            self.download_history.add_entry(progress)
            self.state_manager.remove_download_state(task.url)
            
            return True
            
        except Exception as e:
            error = self.error_handler.handle_error(e, task.url)
            self.progress_tracker.fail_download(task.url, str(e))
            
            # Save state for potential resume
            if task.url in self.progress_tracker.downloads:
                self.state_manager.save_download_state(
                    task.url, 
                    self.progress_tracker.downloads[task.url]
                )
            
            return False
    
    def _progress_hook(self, d: Dict[str, Any], url: str):
        """Progress hook for yt-dlp"""
        if d['status'] == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            speed = d.get('speed', 0)
            
            self.progress_tracker.update_download(
                url, downloaded, total, speed=speed
            )
            
        elif d['status'] == 'finished':
            self.progress_tracker.complete_download(url)
    
    def _on_progress_update(self, url: str, progress: DownloadProgress):
        """Handle progress updates"""
        # Save state periodically
        if progress.state == DownloadState.DOWNLOADING:
            if time.time() - progress.last_update > 5:  # Save every 5 seconds
                self.state_manager.save_download_state(url, progress)
    
    def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Get video information without downloading"""
        ydl_opts = {
            'quiet': True, 
            'no_warnings': True,
            'extract_flat': False
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    return None
                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0),
                    'upload_date': info.get('upload_date', ''),
                    'description': info.get('description', ''),
                    'formats': info.get('formats', [])
                }
        except Exception as e:
            self.error_handler.handle_error(e, url)
            return None
    
    def get_playlist_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Get playlist information"""
        ydl_opts = {
            'quiet': True, 
            'no_warnings': True, 
            'extract_flat': True
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
            if info and 'entries' in info:
                entries = list(info['entries'])
                return {
                    'title': info.get('title', 'Unknown Playlist'),
                    'uploader': info.get('uploader', 'Unknown'),
                    'entry_count': len(entries),
                    'entries': entries
                }
        except Exception as e:
            self.error_handler.handle_error(e, url)
            return None
    
    def get_available_formats(self, url: str) -> List[Dict[str, Any]]:
        """Get available video formats"""
        ydl_opts = {
            'quiet': True, 
            'no_warnings': True, 
            'listformats': True
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get('formats', []) if info else []
        except Exception as e:
            self.error_handler.handle_error(e, url)
            return []
    
    def pause_download(self, task_id: str) -> bool:
        """Pause a download"""
        if task_id in self.active_downloads:
            task = self.active_downloads[task_id]
            self.progress_tracker.pause_download(task.url)
            return True
        return False
    
    def resume_download(self, task_id: str) -> bool:
        """Resume a paused download"""
        if task_id in self.active_downloads:
            task = self.active_downloads[task_id]
            self.progress_tracker.resume_download(task.url)
            return True
        return False
    
    def cancel_download(self, task_id: str) -> bool:
        """Cancel a download"""
        # Remove from queue if not started
        if task_id in self.active_downloads:
            # Note: Actual cancellation of yt-dlp is complex
            # For now, we just mark it for cancellation
            task = self.active_downloads[task_id]
            progress = self.progress_tracker.get_progress(task.url)
            if progress:
                progress.state = DownloadState.CANCELLED
            return True
        return False
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        return {
            'queue_size': self.download_queue.qsize(),
            'active_downloads': len(self.active_downloads),
            'completed_downloads': len(self.completed_downloads),
            'failed_downloads': len(self.failed_downloads),
            'statistics': self.stats.copy()
        }
    
    def get_download_progress(self, task_id: str) -> Optional[DownloadProgress]:
        """Get progress for a specific download"""
        if task_id in self.active_downloads:
            task = self.active_downloads[task_id]
            return self.progress_tracker.get_progress(task.url)
        return None
    
    def clear_completed(self):
        """Clear completed downloads from memory"""
        self.completed_downloads.clear()
        self.failed_downloads.clear()
    
    def shutdown(self):
        """Shutdown the download manager"""
        print("Shutting down download manager...")
        self.stop_queue_processing()
        self.executor.shutdown(wait=True)
        self.progress_tracker.cleanup()
        self.state_manager.save_state()
        print("Download manager shutdown complete")


# Legacy wrapper for backwards compatibility
class YouTubeDownloader(DownloadManager):
    """Backwards compatible wrapper"""
    
    def __init__(self):
        super().__init__()
        self.download_path = Path(self.config_manager.config.output_dir)
    
    def setup_download_path(self) -> bool:
        """Legacy method for setting up download path"""
        try:
            self.download_path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception:
            return False
    
    def check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available"""
        import shutil
        return shutil.which('ffmpeg') is not None
    
    def is_valid_youtube_url(self, url: str) -> bool:
        """Legacy method"""
        return is_valid_youtube_url(url)
    
    def is_playlist_url(self, url: str) -> bool:
        """Legacy method"""
        return is_playlist_url(url)
    
    def normalize_youtube_url(self, url: str) -> str:
        """Legacy method"""
        return normalize_youtube_url(url)


if __name__ == "__main__":
    # Example usage
    manager = DownloadManager()
    manager.start_queue_processing()
    
    # Add some downloads
    task_id = manager.add_download(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        priority=DownloadPriority.HIGH
    )
    
    # Monitor progress
    time.sleep(2)
    print(manager.get_queue_status())
    
    # Shutdown
    manager.shutdown()
