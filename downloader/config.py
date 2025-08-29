"""
Configuration management for YouTube Downloader
Supports JSON/YAML config files, environment variables, and download profiles
"""

import json
import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass, asdict, field
from enum import Enum


class DownloadProfile(Enum):
    """Predefined download profiles for different use cases"""
    MOBILE = "mobile"
    DESKTOP = "desktop"
    HIGH_QUALITY = "high_quality"  # 1440p+ for high-end displays
    ARCHIVE = "archive"
    AUDIO_ONLY = "audio_only"
    CUSTOM = "custom"


@dataclass
class DownloadConfig:
    """Configuration class for download settings"""
    
    # Basic settings
    output_dir: str = ""
    quality: str = "best"
    format: str = "mp4"
    audio_format: str = "m4a"
    
    # Features
    write_subtitles: bool = False
    write_thumbnail: bool = False
    write_metadata: bool = True
    write_description: bool = False
    
    # Archive and resume
    archive_file: Optional[str] = None
    enable_resume: bool = True
    
    # Queue and concurrency
    max_concurrent_downloads: int = 3
    download_timeout: int = 300
    
    # Retry and error handling
    max_retries: int = 3
    retry_delay: float = 1.0
    exponential_backoff: bool = True
    
    # Quality fallback chain - now includes 4K and 8K support
    quality_fallback_chain: list = field(default_factory=lambda: ["best", "2160p", "1440p", "1080p", "720p", "480p"])
    format_preference: list = field(default_factory=lambda: ["mp4", "webm", "mkv"])
    
    # Profile
    profile: str = DownloadProfile.DESKTOP.value
    
    # Advanced
    user_agent: Optional[str] = None
    proxy: Optional[str] = None
    cookies_file: Optional[str] = None
    
    def __post_init__(self):
        """Set default output directory if not provided"""
        if not self.output_dir:
            self.output_dir = str(self._get_default_download_path())
    
    def _get_default_download_path(self) -> Path:
        """Get default download path based on OS"""
        if os.name == 'nt':  # Windows
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                  r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as key:
                    downloads_path = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")[0]
                    return Path(downloads_path) / "YouTube_Downloads"
            except:
                return Path.home() / "Downloads" / "YouTube_Downloads"
        else:  # Linux/Mac
            return Path.home() / "Downloads" / "YouTube_Downloads"


class ConfigManager:
    """Manages configuration loading, saving, and profile management"""
    
    DEFAULT_CONFIG_FILE = "youtube_downloader_config.json"
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or self.DEFAULT_CONFIG_FILE
        self.config = DownloadConfig()
        self._load_config()
    
    def _load_config(self):
        """Load configuration from file and environment variables"""
        # Load from file
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    if self.config_file.endswith('.yaml') or self.config_file.endswith('.yml'):
                        data = yaml.safe_load(f)
                    else:
                        data = json.load(f)
                
                # Update config with loaded data
                for key, value in data.items():
                    if hasattr(self.config, key):
                        setattr(self.config, key, value)
                        
            except Exception as e:
                print(f"Warning: Could not load config file {self.config_file}: {e}")
        
        # Override with environment variables
        self._load_env_variables()
    
    def _load_env_variables(self):
        """Load configuration from environment variables"""
        env_mapping = {
            'YT_DL_OUTPUT_DIR': 'output_dir',
            'YT_DL_QUALITY': 'quality',
            'YT_DL_FORMAT': 'format',
            'YT_DL_WRITE_SUBS': 'write_subtitles',
            'YT_DL_WRITE_THUMBNAIL': 'write_thumbnail',
            'YT_DL_ARCHIVE_FILE': 'archive_file',
            'YT_DL_MAX_CONCURRENT': 'max_concurrent_downloads',
            'YT_DL_MAX_RETRIES': 'max_retries',
            'YT_DL_PROFILE': 'profile',
            'YT_DL_PROXY': 'proxy',
            'YT_DL_USER_AGENT': 'user_agent',
        }
        
        for env_var, config_attr in env_mapping.items():
            value = os.getenv(env_var)
            if value is not None:
                # Convert string values to appropriate types
                if config_attr in ['write_subtitles', 'write_thumbnail', 'write_metadata', 'enable_resume', 'exponential_backoff']:
                    value = value.lower() in ('true', '1', 'yes', 'on')
                elif config_attr in ['max_concurrent_downloads', 'max_retries', 'download_timeout']:
                    value = int(value)
                elif config_attr == 'retry_delay':
                    value = float(value)
                
                setattr(self.config, config_attr, value)
    
    def save_config(self, config_file: Optional[str] = None):
        """Save current configuration to file"""
        file_path = config_file or self.config_file
        
        try:
            config_dict = asdict(self.config)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                if file_path.endswith('.yaml') or file_path.endswith('.yml'):
                    yaml.dump(config_dict, f, default_flow_style=False, indent=2)
                else:
                    json.dump(config_dict, f, indent=2, ensure_ascii=False)
                    
            print(f"Configuration saved to {file_path}")
            
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def apply_profile(self, profile: Union[str, DownloadProfile]):
        """Apply a predefined download profile"""
        if isinstance(profile, str):
            try:
                profile = DownloadProfile(profile)
            except ValueError:
                print(f"Unknown profile: {profile}")
                return
        
        self.config.profile = profile.value
        
        # Apply profile-specific settings
        if profile == DownloadProfile.MOBILE:
            self.config.quality = "480p"
            self.config.format = "mp4"
            self.config.write_subtitles = False
            self.config.write_thumbnail = False
            self.config.quality_fallback_chain = ["480p", "360p", "worst"]
            
        elif profile == DownloadProfile.DESKTOP:
            self.config.quality = "best"  # Changed to best for highest available
            self.config.format = "mp4"
            self.config.write_subtitles = True
            self.config.write_thumbnail = True
            self.config.quality_fallback_chain = ["best", "2160p", "1440p", "1080p", "720p", "480p"]
            
        elif profile == DownloadProfile.HIGH_QUALITY:
            self.config.quality = "best"  # Always get the highest available
            self.config.format = "mp4"
            self.config.write_subtitles = True
            self.config.write_thumbnail = True
            self.config.write_metadata = True
            self.config.quality_fallback_chain = ["best", "4320p", "2880p", "2160p", "1440p"]  # 8K, 5K, 4K, 1440p
            
        elif profile == DownloadProfile.ARCHIVE:
            self.config.quality = "best"
            self.config.format = "mkv"
            self.config.write_subtitles = True
            self.config.write_thumbnail = True
            self.config.write_metadata = True
            self.config.write_description = True
            self.config.quality_fallback_chain = ["best"]
            
        elif profile == DownloadProfile.AUDIO_ONLY:
            self.config.quality = "bestaudio"
            self.config.format = "m4a"
            self.config.write_subtitles = False
            self.config.write_thumbnail = True
            self.config.quality_fallback_chain = ["bestaudio", "worst"]
    
    def get_yt_dlp_options(self) -> Dict[str, Any]:
        """Convert config to yt-dlp options dictionary"""
        options = {
            'outtmpl': os.path.join(self.config.output_dir, '%(title)s.%(ext)s'),
            'format': self._get_format_selector(),
            'writesubtitles': self.config.write_subtitles,
            'writethumbnail': self.config.write_thumbnail,
            'writeinfojson': self.config.write_metadata,
            'writedescription': self.config.write_description,
            'retries': self.config.max_retries,
            'socket_timeout': self.config.download_timeout,
        }
        
        if self.config.archive_file:
            options['download_archive'] = self.config.archive_file
        
        if self.config.user_agent:
            options['user_agent'] = self.config.user_agent
        
        if self.config.proxy:
            options['proxy'] = self.config.proxy
        
        if self.config.cookies_file and os.path.exists(self.config.cookies_file):
            options['cookiefile'] = self.config.cookies_file
        
        return options
    
    def _get_format_selector(self) -> str:
        """Generate yt-dlp format selector based on config - matches original youtube.py logic"""
        if self.config.profile == DownloadProfile.AUDIO_ONLY.value:
            return f"bestaudio[ext={self.config.audio_format}]/bestaudio/best"
        
        # Handle special cases
        quality = self.config.quality.lower()
        
        # Check if FFmpeg is available for merging
        ffmpeg_available = True  # Assume available, can be made configurable
        
        if quality in ('best', ''):
            if ffmpeg_available:
                return 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best'
            else:
                return 'best[ext=mp4]/best'
        
        if quality == 'worst':
            return 'worst[ext=mp4]/worst'
        
        # Parse dynamic height like '1080p', '1440p', '2160p' etc.
        import re
        match = re.match(r'^(\d{3,4})p$', quality)
        if match:
            height = int(match.group(1))
            if ffmpeg_available:
                # Prefer exact height, then <= height, with merge; fall back to best
                return (
                    f"bestvideo[height={height}][ext=mp4]+bestaudio[ext=m4a]/"
                    f"bestvideo[height={height}]+bestaudio/"
                    f"best[height={height}]/best[height<={height}]"
                )
            else:
                # Without FFmpeg, prefer pre-merged formats with both audio+video
                return (
                    f"best[height={height}][vcodec!=none][acodec!=none]/"
                    f"best[height<={height}][vcodec!=none][acodec!=none]/best"
                )
        
        # Build format selector with fallback chain for other cases
        format_parts = []
        for quality_option in self.config.quality_fallback_chain:
            for fmt in self.config.format_preference:
                if quality_option == "best":
                    format_parts.append(f"best[ext={fmt}]")
                elif quality_option == "worst":
                    format_parts.append(f"worst[ext={fmt}]")
                elif quality_option == "bestaudio":
                    format_parts.append(f"bestaudio[ext={self.config.audio_format}]")
                else:
                    # Parse height from quality like "2160p"
                    height_match = re.match(r'^(\d{3,4})p$', quality_option)
                    if height_match:
                        height = int(height_match.group(1))
                        if ffmpeg_available:
                            format_parts.append(f"bestvideo[height={height}][ext={fmt}]+bestaudio[ext=m4a]")
                            format_parts.append(f"best[height={height}][ext={fmt}]")
                        else:
                            format_parts.append(f"best[height={height}][ext={fmt}][vcodec!=none][acodec!=none]")
        
        # Add final fallbacks
        format_parts.extend(["best", "worst"])
        
        return "/".join(format_parts)
    
    def create_default_config_file(self):
        """Create a default configuration file with all available options"""
        self.save_config()
        print(f"Default configuration file created at {self.config_file}")
        print("You can edit this file to customize your download settings.")


# Convenience function to get a configured manager
def get_config_manager(config_file: Optional[str] = None, profile: Optional[str] = None) -> ConfigManager:
    """Get a configured ConfigManager instance"""
    manager = ConfigManager(config_file)
    
    if profile:
        manager.apply_profile(profile)
    
    return manager


if __name__ == "__main__":
    # Example usage and testing
    config_manager = ConfigManager()
    
    # Apply desktop profile
    config_manager.apply_profile(DownloadProfile.DESKTOP)
    
    # Save configuration
    config_manager.save_config("example_config.json")
    
    # Print yt-dlp options
    print("yt-dlp options:", config_manager.get_yt_dlp_options())
