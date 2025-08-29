"""
Enhanced CLI interface for YouTube Downloader
Supports profiles, queue management, batch downloads, and all new features
"""

import argparse
import sys
import os
import time
import json
from pathlib import Path
from typing import List, Optional

from .core import DownloadManager, DownloadPriority
from .config import ConfigManager, DownloadProfile
from .utils import is_valid_youtube_url, is_playlist_url


def create_parser() -> argparse.ArgumentParser:
    """Create the command line argument parser"""
    parser = argparse.ArgumentParser(
        description="Enhanced YouTube Video Downloader with queue management and profiles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "https://youtube.com/watch?v=VIDEO_ID"
  %(prog)s --profile mobile "https://youtube.com/watch?v=VIDEO_ID"
  %(prog)s --batch-file urls.txt --priority high
  %(prog)s --quality 1080p --format mp4 "https://youtube.com/watch?v=VIDEO_ID"
  %(prog)s --config-file my_config.json "https://youtube.com/watch?v=VIDEO_ID"
  %(prog)s --list-profiles
  %(prog)s --create-config
        """
    )
    
    # URL arguments
    parser.add_argument(
        'urls', 
        nargs='*', 
        help='YouTube URLs to download'
    )
    
    # Configuration
    parser.add_argument(
        '--config-file', '-c',
        help='Configuration file to use (JSON/YAML)'
    )
    
    parser.add_argument(
        '--profile', '-p',
        choices=['mobile', 'desktop', 'high_quality', 'archive', 'audio_only'],
        help='Download profile to use'
    )
    
    parser.add_argument(
        '--create-config',
        action='store_true',
        help='Create a default configuration file'
    )
    
    parser.add_argument(
        '--list-profiles',
        action='store_true',
        help='List available download profiles'
    )
    
    # Input options
    parser.add_argument(
        '--batch-file', '-bf',
        help='File containing URLs to download (one per line)'
    )
    
    parser.add_argument(
        '--archive-file', '-a',
        help='Download archive file to track completed downloads'
    )
    
    # Quality and format
    parser.add_argument(
        '--quality', '-q',
        help='Video quality (e.g., best, worst, 1080p, 720p, 480p)'
    )
    
    parser.add_argument(
        '--format', '-f',
        help='Video format (e.g., mp4, webm, mkv)'
    )
    
    parser.add_argument(
        '--audio-only',
        action='store_true',
        help='Download audio only'
    )
    
    # Output options
    parser.add_argument(
        '--output-dir', '-o',
        help='Output directory for downloads'
    )
    
    parser.add_argument(
        '--write-subs',
        action='store_true',
        help='Download subtitles'
    )
    
    parser.add_argument(
        '--write-thumbnail',
        action='store_true',
        help='Download thumbnail'
    )
    
    parser.add_argument(
        '--write-metadata',
        action='store_true',
        help='Write metadata files'
    )
    
    # Queue and concurrency
    parser.add_argument(
        '--priority',
        choices=['low', 'normal', 'high', 'urgent'],
        default='normal',
        help='Download priority'
    )
    
    parser.add_argument(
        '--max-concurrent',
        type=int,
        help='Maximum concurrent downloads'
    )
    
    parser.add_argument(
        '--no-queue',
        action='store_true',
        help='Download immediately without queue'
    )
    
    # Error handling and retry
    parser.add_argument(
        '--max-retries',
        type=int,
        help='Maximum number of retries for failed downloads'
    )
    
    parser.add_argument(
        '--no-resume',
        action='store_true',
        help='Disable download resume functionality'
    )
    
    # Information and analysis
    parser.add_argument(
        '--info-only',
        action='store_true',
        help='Show video information without downloading'
    )
    
    parser.add_argument(
        '--list-formats',
        action='store_true',
        help='List available formats for the video'
    )
    
    parser.add_argument(
        '--show-progress',
        action='store_true',
        default=True,
        help='Show download progress (default: True)'
    )
    
    # Queue management
    parser.add_argument(
        '--queue-status',
        action='store_true',
        help='Show current queue status'
    )
    
    parser.add_argument(
        '--clear-queue',
        action='store_true',
        help='Clear completed downloads from queue'
    )
    
    # History and statistics
    parser.add_argument(
        '--history',
        action='store_true',
        help='Show download history'
    )
    
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show download statistics'
    )
    
    # Verbose output
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress output except errors'
    )
    
    return parser


def load_urls_from_file(file_path: str) -> List[str]:
    """Load URLs from a batch file"""
    urls = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if is_valid_youtube_url(line):
                        urls.append(line)
                    else:
                        print(f"Warning: Invalid URL skipped: {line}")
    except Exception as e:
        print(f"Error reading batch file {file_path}: {e}")
    
    return urls


def show_profiles():
    """Show available download profiles"""
    profiles = {
        'mobile': 'Optimized for mobile devices (480p, MP4, small size)',
        'desktop': 'Balanced quality for desktop viewing (best available, MP4, subtitles)',
        'high_quality': 'Maximum quality for high-end displays (8K/4K/1440p+ priority)',
        'archive': 'Best quality for archival purposes (best quality, MKV, all metadata)',
        'audio_only': 'Audio-only downloads (best audio quality)'
    }
    
    print("Available Download Profiles:")
    print("=" * 40)
    for profile, description in profiles.items():
        print(f"{profile:12} - {description}")


def show_video_info(manager: DownloadManager, url: str):
    """Show video information"""
    print(f"Getting information for: {url}")
    
    if is_playlist_url(url):
        info = manager.get_playlist_info(url)
        if info:
            print(f"Playlist: {info['title']}")
            print(f"Uploader: {info['uploader']}")
            print(f"Videos: {info['entry_count']}")
        else:
            print("Could not retrieve playlist information")
    else:
        info = manager.get_video_info(url)
        if info:
            print(f"Title: {info['title']}")
            print(f"Uploader: {info['uploader']}")
            print(f"Duration: {info.get('duration', 'Unknown')} seconds")
            print(f"Views: {info.get('view_count', 'Unknown')}")
            print(f"Upload Date: {info.get('upload_date', 'Unknown')}")
        else:
            print("Could not retrieve video information")


def show_formats(manager: DownloadManager, url: str):
    """Show available formats for a video"""
    print(f"Available formats for: {url}")
    formats = manager.get_available_formats(url)
    
    if formats:
        print(f"{'Format ID':<12} {'Extension':<10} {'Resolution':<12} {'Note'}")
        print("-" * 60)
        for fmt in formats:
            format_id = fmt.get('format_id', '')
            ext = fmt.get('ext', '')
            resolution = fmt.get('resolution', 'audio only')
            note = fmt.get('format_note', '')
            print(f"{format_id:<12} {ext:<10} {resolution:<12} {note}")
    else:
        print("No formats found or error retrieving formats")


def main():
    """Main CLI function"""
    parser = create_parser()
    args = parser.parse_args()
    
    # Handle special commands that don't require URLs
    if args.list_profiles:
        show_profiles()
        return
    
    if args.create_config:
        config_manager = ConfigManager()
        config_manager.create_default_config_file()
        return
    
    # Create config manager
    config_manager = ConfigManager(args.config_file)
    
    # Apply profile if specified
    if args.profile:
        config_manager.apply_profile(args.profile)
    
    # Apply command line overrides
    config = config_manager.config
    
    if args.output_dir:
        config.output_dir = args.output_dir
    if args.quality:
        config.quality = args.quality
    if args.format:
        config.format = args.format
    if args.archive_file:
        config.archive_file = args.archive_file
    if args.write_subs:
        config.write_subtitles = True
    if args.write_thumbnail:
        config.write_thumbnail = True
    if args.write_metadata:
        config.write_metadata = True
    if args.max_concurrent:
        config.max_concurrent_downloads = args.max_concurrent
    if args.max_retries:
        config.max_retries = args.max_retries
    if args.no_resume:
        config.enable_resume = False
    if args.audio_only:
        config_manager.apply_profile(DownloadProfile.AUDIO_ONLY)
    
    # Create download manager
    manager = DownloadManager(config_manager)
    
    # Handle queue management commands
    if args.queue_status:
        status = manager.get_queue_status()
        print("Queue Status:")
        print(f"  Queue size: {status['queue_size']}")
        print(f"  Active downloads: {status['active_downloads']}")
        print(f"  Completed: {status['completed_downloads']}")
        print(f"  Failed: {status['failed_downloads']}")
        return
    
    if args.clear_queue:
        manager.clear_completed()
        print("Cleared completed downloads from queue")
        return
    
    if args.history:
        entries = manager.download_history.get_recent_downloads(20)
        if entries:
            print("Recent Downloads:")
            print("-" * 80)
            for entry in entries:
                status = "✓" if entry.success else "✗"
                print(f"{status} {entry.title[:50]:<50} {entry.timestamp.strftime('%Y-%m-%d %H:%M')}")
        else:
            print("No download history found")
        return
    
    if args.stats:
        stats = manager.download_history.get_statistics()
        print("Download Statistics:")
        print(f"  Total downloads: {stats['total_downloads']}")
        print(f"  Success rate: {stats['success_rate']:.1f}%")
        print(f"  Total data downloaded: {stats['total_size_bytes'] / (1024*1024*1024):.2f} GB")
        return
    
    # Collect URLs
    urls = []
    
    # Add URLs from command line
    if args.urls:
        for url in args.urls:
            if is_valid_youtube_url(url):
                urls.append(url)
            else:
                print(f"Error: Invalid YouTube URL: {url}")
                sys.exit(1)
    
    # Add URLs from batch file
    if args.batch_file:
        batch_urls = load_urls_from_file(args.batch_file)
        urls.extend(batch_urls)
        print(f"Loaded {len(batch_urls)} URLs from batch file")
    
    if not urls:
        print("Error: No valid URLs provided")
        parser.print_help()
        sys.exit(1)
    
    # Handle info-only requests
    if args.info_only:
        for url in urls:
            show_video_info(manager, url)
            print()
        return
    
    if args.list_formats:
        for url in urls:
            show_formats(manager, url)
            print()
        return
    
    # Convert priority string to enum
    priority_map = {
        'low': DownloadPriority.LOW,
        'normal': DownloadPriority.NORMAL,
        'high': DownloadPriority.HIGH,
        'urgent': DownloadPriority.URGENT
    }
    priority = priority_map[args.priority]
    
    try:
        if args.no_queue:
            # Download immediately without queue
            for url in urls:
                print(f"Downloading: {url}")
                # Create a simple task and download
                from .core import DownloadTask
                task = DownloadTask(url=url, priority=priority)
                success = manager._download_single(task)
                if success:
                    print(f"✓ Download completed: {url}")
                else:
                    print(f"✗ Download failed: {url}")
        else:
            # Use queue system
            if not args.quiet:
                print(f"Adding {len(urls)} downloads to queue...")
            
            manager.start_queue_processing()
            
            # Add downloads to queue
            task_ids = []
            for url in urls:
                task_id = manager.add_download(url, priority)
                task_ids.append(task_id)
            
            if not args.quiet:
                print(f"Downloads queued. Task IDs: {', '.join(task_ids)}")
                print("Monitoring progress... (Press Ctrl+C to stop)")
            
            # Monitor progress
            try:
                while True:
                    status = manager.get_queue_status()
                    active = status['active_downloads']
                    completed = status['completed_downloads']
                    failed = status['failed_downloads']
                    
                    if active == 0 and status['queue_size'] == 0:
                        break
                    
                    if not args.quiet and args.show_progress:
                        print(f"\rActive: {active}, Completed: {completed}, Failed: {failed}", end='', flush=True)
                    
                    time.sleep(1)
                
                if not args.quiet:
                    print(f"\nAll downloads completed. Success: {completed}, Failed: {failed}")
                    
            except KeyboardInterrupt:
                print("\nDownload interrupted by user")
                
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    finally:
        manager.shutdown()


if __name__ == "__main__":
    main()
