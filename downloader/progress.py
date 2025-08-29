"""
Comprehensive progress and state management for YouTube Downloader
Handles real-time progress tracking, download state persistence, and download history
"""

import json
import os
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
import pickle

from tqdm import tqdm


class DownloadState(Enum):
    """Download states"""
    PENDING = "pending"
    STARTING = "starting"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadProgress:
    """Progress information for a download"""
    url: str
    title: str = ""
    state: DownloadState = DownloadState.PENDING
    
    # Size information
    total_bytes: int = 0
    downloaded_bytes: int = 0
    
    # Speed and timing
    speed: float = 0.0  # bytes per second
    eta: float = 0.0    # estimated time remaining in seconds
    elapsed_time: float = 0.0
    
    # Progress percentage
    progress_percent: float = 0.0
    
    # File information
    filename: str = ""
    output_path: str = ""
    format: str = ""
    quality: str = ""
    
    # Timestamps
    start_time: float = 0.0
    end_time: float = 0.0
    last_update: float = 0.0
    
    # Error information
    error_message: str = ""
    retry_count: int = 0
    
    # Resume information
    resume_data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.start_time == 0.0:
            self.start_time = time.time()
        self.last_update = time.time()
    
    def update_progress(self, downloaded: int, total: Optional[int] = None, speed: Optional[float] = None):
        """Update progress information"""
        self.downloaded_bytes = downloaded
        if total is not None:
            self.total_bytes = total
        
        if self.total_bytes > 0:
            self.progress_percent = (self.downloaded_bytes / self.total_bytes) * 100
        
        current_time = time.time()
        self.elapsed_time = current_time - self.start_time
        
        if speed is not None:
            self.speed = speed
        elif self.elapsed_time > 0:
            self.speed = self.downloaded_bytes / self.elapsed_time
        
        # Calculate ETA
        if self.speed > 0 and self.total_bytes > 0:
            remaining_bytes = self.total_bytes - self.downloaded_bytes
            self.eta = remaining_bytes / self.speed
        
        self.last_update = current_time
    
    def mark_completed(self):
        """Mark download as completed"""
        self.state = DownloadState.COMPLETED
        self.end_time = time.time()
        self.progress_percent = 100.0
        
    def mark_failed(self, error_message: str):
        """Mark download as failed"""
        self.state = DownloadState.FAILED
        self.error_message = error_message
        self.end_time = time.time()
    
    def get_human_readable_size(self, bytes_value: int) -> str:
        """Convert bytes to human readable format"""
        if bytes_value == 0:
            return "0 B"
        
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        unit_index = 0
        size = float(bytes_value)
        
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        
        return f"{size:.1f} {units[unit_index]}"
    
    def get_human_readable_speed(self) -> str:
        """Get human readable download speed"""
        return f"{self.get_human_readable_size(int(self.speed))}/s"
    
    def get_human_readable_eta(self) -> str:
        """Get human readable ETA"""
        if self.eta <= 0:
            return "Unknown"
        
        if self.eta < 60:
            return f"{int(self.eta)}s"
        elif self.eta < 3600:
            minutes = int(self.eta // 60)
            seconds = int(self.eta % 60)
            return f"{minutes}m {seconds}s"
        else:
            hours = int(self.eta // 3600)
            minutes = int((self.eta % 3600) // 60)
            return f"{hours}h {minutes}m"


@dataclass
class DownloadHistoryEntry:
    """Entry in download history"""
    url: str
    title: str
    filename: str
    output_path: str
    file_size: int
    format: str
    quality: str
    download_time: float
    timestamp: datetime
    success: bool
    error_message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DownloadHistoryEntry':
        """Create from dictionary"""
        data = data.copy()
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class ProgressTracker:
    """Tracks progress for multiple downloads with real-time updates"""
    
    def __init__(self):
        self.downloads: Dict[str, DownloadProgress] = {}
        self.progress_bars: Dict[str, tqdm] = {}
        self.callbacks: List[Callable[[str, DownloadProgress], None]] = []
        self._lock = threading.Lock()
    
    def start_download(self, url: str, title: str = "", **kwargs) -> DownloadProgress:
        """Start tracking a new download"""
        with self._lock:
            progress = DownloadProgress(url=url, title=title, **kwargs)
            progress.state = DownloadState.STARTING
            self.downloads[url] = progress
            
            # Create progress bar
            desc = title[:50] + "..." if len(title) > 50 else title
            self.progress_bars[url] = tqdm(
                total=100,
                desc=desc,
                unit="%",
                bar_format="{l_bar}{bar}| {n:.1f}% [{elapsed}<{remaining}, {rate_fmt}]"
            )
            
            self._notify_callbacks(url, progress)
            return progress
    
    def update_download(self, url: str, downloaded: int, total: Optional[int] = None, **kwargs):
        """Update download progress"""
        with self._lock:
            if url not in self.downloads:
                return
            
            progress = self.downloads[url]
            progress.update_progress(downloaded, total, **kwargs)
            progress.state = DownloadState.DOWNLOADING
            
            # Update progress bar
            if url in self.progress_bars:
                pbar = self.progress_bars[url]
                pbar.n = progress.progress_percent
                pbar.set_postfix({
                    'size': progress.get_human_readable_size(progress.downloaded_bytes),
                    'speed': progress.get_human_readable_speed(),
                    'eta': progress.get_human_readable_eta()
                })
                pbar.refresh()
            
            self._notify_callbacks(url, progress)
    
    def complete_download(self, url: str):
        """Mark download as completed"""
        with self._lock:
            if url not in self.downloads:
                return
            
            progress = self.downloads[url]
            progress.mark_completed()
            
            # Complete progress bar
            if url in self.progress_bars:
                pbar = self.progress_bars[url]
                pbar.n = 100
                pbar.set_postfix({'status': 'Complete'})
                pbar.close()
                del self.progress_bars[url]
            
            self._notify_callbacks(url, progress)
    
    def fail_download(self, url: str, error_message: str):
        """Mark download as failed"""
        with self._lock:
            if url not in self.downloads:
                return
            
            progress = self.downloads[url]
            progress.mark_failed(error_message)
            
            # Close progress bar
            if url in self.progress_bars:
                pbar = self.progress_bars[url]
                pbar.set_postfix({'status': 'Failed'})
                pbar.close()
                del self.progress_bars[url]
            
            self._notify_callbacks(url, progress)
    
    def pause_download(self, url: str):
        """Pause a download"""
        with self._lock:
            if url in self.downloads:
                self.downloads[url].state = DownloadState.PAUSED
                if url in self.progress_bars:
                    self.progress_bars[url].set_postfix({'status': 'Paused'})
    
    def resume_download(self, url: str):
        """Resume a paused download"""
        with self._lock:
            if url in self.downloads:
                self.downloads[url].state = DownloadState.DOWNLOADING
                if url in self.progress_bars:
                    self.progress_bars[url].set_postfix({'status': 'Resuming'})
    
    def get_progress(self, url: str) -> Optional[DownloadProgress]:
        """Get progress for a specific download"""
        return self.downloads.get(url)
    
    def get_all_progress(self) -> Dict[str, DownloadProgress]:
        """Get progress for all downloads"""
        return self.downloads.copy()
    
    def add_callback(self, callback: Callable[[str, DownloadProgress], None]):
        """Add a progress callback function"""
        self.callbacks.append(callback)
    
    def _notify_callbacks(self, url: str, progress: DownloadProgress):
        """Notify all registered callbacks"""
        for callback in self.callbacks:
            try:
                callback(url, progress)
            except Exception as e:
                print(f"Error in progress callback: {e}")
    
    def cleanup(self):
        """Clean up progress bars"""
        with self._lock:
            for pbar in self.progress_bars.values():
                pbar.close()
            self.progress_bars.clear()


class StateManager:
    """Manages download state persistence for resume functionality"""
    
    def __init__(self, state_file: str = "download_state.pkl"):
        self.state_file = Path(state_file)
        self.state_data: Dict[str, Any] = {}
        self._load_state()
    
    def _load_state(self):
        """Load state from file"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'rb') as f:
                    self.state_data = pickle.load(f)
            except Exception as e:
                print(f"Warning: Could not load state file: {e}")
                self.state_data = {}
    
    def save_state(self):
        """Save state to file"""
        try:
            with open(self.state_file, 'wb') as f:
                pickle.dump(self.state_data, f)
        except Exception as e:
            print(f"Warning: Could not save state file: {e}")
    
    def save_download_state(self, url: str, progress: DownloadProgress):
        """Save state for a specific download"""
        self.state_data[url] = {
            'progress': asdict(progress),
            'timestamp': time.time()
        }
        self.save_state()
    
    def get_download_state(self, url: str) -> Optional[DownloadProgress]:
        """Get saved state for a download"""
        if url in self.state_data:
            try:
                progress_data = self.state_data[url]['progress']
                return DownloadProgress(**progress_data)
            except Exception as e:
                print(f"Error loading state for {url}: {e}")
        return None
    
    def remove_download_state(self, url: str):
        """Remove saved state for a download"""
        if url in self.state_data:
            del self.state_data[url]
            self.save_state()
    
    def can_resume_download(self, url: str) -> bool:
        """Check if a download can be resumed"""
        state = self.get_download_state(url)
        if state:
            return state.state in [DownloadState.PAUSED, DownloadState.DOWNLOADING]
        return False


class DownloadHistory:
    """Manages download history with search and filtering capabilities"""
    
    def __init__(self, history_file: str = "download_history.json"):
        self.history_file = Path(history_file)
        self.entries: List[DownloadHistoryEntry] = []
        self._load_history()
    
    def _load_history(self):
        """Load history from file"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.entries = [DownloadHistoryEntry.from_dict(entry) for entry in data]
            except Exception as e:
                print(f"Warning: Could not load history file: {e}")
                self.entries = []
    
    def save_history(self):
        """Save history to file"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                data = [entry.to_dict() for entry in self.entries]
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Could not save history file: {e}")
    
    def add_entry(self, progress: DownloadProgress):
        """Add a completed download to history"""
        entry = DownloadHistoryEntry(
            url=progress.url,
            title=progress.title,
            filename=progress.filename,
            output_path=progress.output_path,
            file_size=progress.total_bytes,
            format=progress.format,
            quality=progress.quality,
            download_time=progress.elapsed_time,
            timestamp=datetime.fromtimestamp(progress.end_time),
            success=(progress.state == DownloadState.COMPLETED),
            error_message=progress.error_message
        )
        
        self.entries.append(entry)
        self.save_history()
    
    def get_recent_downloads(self, limit: int = 10) -> List[DownloadHistoryEntry]:
        """Get recent downloads"""
        return sorted(self.entries, key=lambda x: x.timestamp, reverse=True)[:limit]
    
    def search_downloads(self, query: str) -> List[DownloadHistoryEntry]:
        """Search downloads by title or URL"""
        query = query.lower()
        return [
            entry for entry in self.entries
            if query in entry.title.lower() or query in entry.url.lower()
        ]
    
    def get_failed_downloads(self) -> List[DownloadHistoryEntry]:
        """Get failed downloads"""
        return [entry for entry in self.entries if not entry.success]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get download statistics"""
        if not self.entries:
            return {"total_downloads": 0}
        
        total_downloads = len(self.entries)
        successful_downloads = len([e for e in self.entries if e.success])
        total_size = sum(e.file_size for e in self.entries if e.success)
        total_time = sum(e.download_time for e in self.entries if e.success)
        
        return {
            "total_downloads": total_downloads,
            "successful_downloads": successful_downloads,
            "failed_downloads": total_downloads - successful_downloads,
            "success_rate": (successful_downloads / total_downloads) * 100 if total_downloads > 0 else 0,
            "total_size_bytes": total_size,
            "total_download_time": total_time,
            "average_speed": total_size / total_time if total_time > 0 else 0
        }


# Example usage and testing
if __name__ == "__main__":
    # Test progress tracking
    tracker = ProgressTracker()
    
    # Start a mock download
    url = "https://youtube.com/watch?v=test"
    progress = tracker.start_download(url, "Test Video")
    
    # Simulate progress updates
    for i in range(0, 101, 10):
        time.sleep(0.1)
        tracker.update_download(url, i * 1024, 100 * 1024, speed=1024)
    
    tracker.complete_download(url)
    tracker.cleanup()
    
    print("Progress tracking test completed!")
