#!/usr/bin/env python3
"""
YouTube Video Downloader Agent
Downloads YouTube videos, shorts, and playlists from provided URLs
"""

import sys
import re
import subprocess
import os
from pathlib import Path
import argparse
from typing import Dict, Any, List, Optional, Set
import yt_dlp
from tqdm import tqdm
import time
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

class YouTubeDownloader:
    def __init__(self):
        self.download_path = self.get_default_download_path()

    class QuietLogger:
        def debug(self, msg):
            pass
        def info(self, msg):
            pass
        def warning(self, msg):
            pass
        def error(self, msg):
            # Suppress noisy transient errors during format probing
            pass
        
    def get_default_download_path(self) -> Path:
        """Get the default download path for the OS"""
        if os.name == 'nt':  # Windows
            # Try to get Windows Downloads folder
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
    
    def setup_download_path(self) -> bool:
        """Ask user for download path or use default"""
        default_path = self.download_path
        print(f"Default download path: {default_path}")
        
        choice = input("Use default path? (Y/n): ").strip().lower()
        if choice in ['n', 'no']:
            custom_path = input("Enter custom download path: ").strip()
            if custom_path:
                try:
                    self.download_path = Path(custom_path)
                    self.download_path.mkdir(parents=True, exist_ok=True)
                    print(f"Download path set to: {self.download_path}")
                    return True
                except Exception as e:
                    print(f"Error creating custom path: {e}")
                    print("Using default path instead.")
        
        # Use default path
        try:
            self.download_path.mkdir(parents=True, exist_ok=True)
            print(f"Using download path: {self.download_path}")
            return True
        except Exception as e:
            print(f"Error creating download directory: {e}")
            return False
    
    def check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available"""
        import shutil
        
        # First try to find ffmpeg in PATH
        ffmpeg_path = shutil.which('ffmpeg')
        if ffmpeg_path:
            try:
                subprocess.run([ffmpeg_path, '-version'], capture_output=True, check=True)
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
        
        # Try common FFmpeg installation paths on Windows
        common_paths = [
            'ffmpeg.exe',
            'C:\\ffmpeg\\bin\\ffmpeg.exe',
            'C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe',
            'C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe',
        ]
        
        for path in common_paths:
            try:
                subprocess.run([path, '-version'], capture_output=True, check=True)
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        
        return False
    
    def is_valid_youtube_url(self, url: str) -> bool:
        """Check if the URL is a valid YouTube URL"""
        youtube_patterns = [
            r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+',
            r'https?://(?:www\.)?youtube\.com/shorts/[\w-]+',
            r'https?://youtu\.be/[\w-]+',
            r'https?://m\.youtube\.com/watch\?v=[\w-]+',
            r'https?://(?:www\.)?youtube\.com/playlist\?list=[\w-]+',
            r'https?://(?:www\.)?youtube\.com/watch\?.*[&?]list=[\w-]+',
        ]
        return any(re.search(pattern, url) for pattern in youtube_patterns)
    
    def is_playlist_url(self, url: str) -> bool:
        """Check if URL is a playlist"""
        # Also treat youtu.be URLs with list= as playlist links
        if 'list=' in url:
            return True
        playlist_patterns = [
            r'https?://(?:www\.)?youtube\.com/playlist\?list=[\w-]+',
            r'https?://(?:www\.)?youtube\.com/watch\?.*[&?]list=[\w-]+',
        ]
        return any(re.search(pattern, url) for pattern in playlist_patterns)

    def normalize_youtube_url(self, url: str) -> str:
        """Normalize YouTube URLs (e.g., youtu.be -> youtube.com/watch?v=...). Preserve other query params."""
        try:
            p = urlparse(url)
            # If already youtube.com watch/playlist, return as-is
            if p.netloc.endswith('youtube.com'):
                return url
            # Convert youtu.be/<id>?<qs> to youtube.com/watch?v=<id>&<qs>
            if p.netloc.endswith('youtu.be'):
                video_id = p.path.lstrip('/')
                qs = parse_qs(p.query)
                qs_flat = []
                for k, vals in qs.items():
                    for v in vals:
                        qs_flat.append((k, v))
                qs_flat.insert(0, ('v', video_id))  # v first
                new_qs = urlencode(qs_flat)
                new_url = urlunparse((
                    'https', 'www.youtube.com', '/watch', '', new_qs, ''
                ))
                return new_url
        except Exception:
            pass
        return url
    
    def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Get video information without downloading"""
        ydl_opts = {'quiet': True, 'no_warnings': True}
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print("Analyzing video...")
                info = ydl.extract_info(url, download=False)
                if info is None:
                    return None
                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                }
        except Exception as e:
            print(f"Error getting video info: {str(e)}")
            return None
    
    def get_playlist_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Get playlist information"""
        ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True}
        
        try:
            print("Analyzing playlist...")
            with tqdm(desc="Loading playlist", unit="items") as pbar:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    pbar.update(1)
                    
                if info and 'entries' in info:
                    entries = list(info['entries'])
                    return {
                        'title': info.get('title', 'Unknown Playlist'),
                        'uploader': info.get('uploader', 'Unknown'),
                        'entry_count': len(entries),
                        'entries': entries
                    }
        except Exception as e:
            print(f"Error getting playlist info: {str(e)}")
        
        return None
    
    def get_available_formats(self, url: str, silent: bool = False) -> List[Dict[str, Any]]:
        """Get available video formats with progress indication"""
        ydl_opts: Dict[str, Any] = {'quiet': True, 'no_warnings': True, 'extractor_retries': 1}
        if silent:
            ydl_opts['logger'] = self.QuietLogger()
            ydl_opts['noprogress'] = True
        
        try:
            print("Getting available formats...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info and 'formats' in info:
                    formats = []
                    seen_qualities = set()
                    
                    for fmt in tqdm(info['formats'], desc="Processing formats", unit="fmt"):
                        height = fmt.get('height')
                        if height and height not in seen_qualities:
                            formats.append({
                                'format_id': fmt.get('format_id'),
                                'height': height,
                                'ext': fmt.get('ext', 'unknown'),
                                'filesize': fmt.get('filesize', 0),
                                'vcodec': fmt.get('vcodec', 'none'),
                                'acodec': fmt.get('acodec', 'none')
                            })
                            seen_qualities.add(height)
                    
                    formats.sort(key=lambda x: x['height'], reverse=True)
                    return formats
        except Exception as e:
            print(f"Error getting formats: {str(e)}")
        
        return []

    def _extract_all_formats(self, url: str, silent: bool = False) -> Optional[Dict[str, Any]]:
        """Return full yt-dlp info dict for URL without downloading."""
        ydl_opts: Dict[str, Any] = {'quiet': True, 'no_warnings': True}
        if silent:
            ydl_opts['logger'] = self.QuietLogger()
            ydl_opts['noprogress'] = True
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.normalize_youtube_url(url), download=False)
                return info
        except Exception:
            # Retry once without a "t"/start parameter if present
            try:
                p = urlparse(url)
                qs = parse_qs(p.query)
                if 't' in qs or 'start' in qs:
                    qs.pop('t', None)
                    qs.pop('start', None)
                    new_qs = urlencode([(k, v2) for k, v in qs.items() for v2 in (v if isinstance(v, list) else [v])])
                    retry_url = urlunparse((p.scheme, p.netloc, p.path, p.params, new_qs, p.fragment))
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(self.normalize_youtube_url(retry_url), download=False)
                        return info
            except Exception:
                pass
            return None

    def select_format_manually(self, url: str, ffmpeg_available: bool) -> Optional[Dict[str, Any]]:
        """Show full format list and let the user pick exact format.
        Returns dict: { 'selector': str, 'audio_only': bool }
        """
        info = self._extract_all_formats(url)
        if not info or 'formats' not in info:
            print("Could not retrieve format list.")
            return None

        formats = info['formats']
        combined = []
        video_only = []
        audio_only = []

        for f in formats:
            v = f.get('vcodec')
            a = f.get('acodec')
            height = f.get('height')
            fps = f.get('fps')
            ext = f.get('ext')
            filesize = f.get('filesize') or f.get('filesize_approx')
            tbr = f.get('tbr')
            fmt_id = f.get('format_id')
            row = {
                'id': fmt_id,
                'height': height,
                'fps': fps,
                'ext': ext,
                'filesize': filesize,
                'tbr': tbr,
                'vcodec': v,
                'acodec': a,
            }
            if (v and v != 'none') and (a and a != 'none'):
                combined.append(row)
            elif (v and v != 'none') and (not a or a == 'none'):
                video_only.append(row)
            elif (not v or v == 'none') and (a and a != 'none'):
                audio_only.append(row)

        def sort_key(x):
            # sort by height desc, then tbr desc
            return (x.get('height') or 0, x.get('tbr') or 0)

        combined.sort(key=sort_key, reverse=True)
        video_only.sort(key=sort_key, reverse=True)
        audio_only.sort(key=lambda x: (x.get('tbr') or 0, x.get('filesize') or 0), reverse=True)

        print("\n0. Best available (auto)")
        idx_map: Dict[int, Dict[str, Any]] = {}
        idx = 1
        if combined:
            print("\nCombined formats (video+audio):")
            for f in combined:
                size_mb = (f['filesize'] or 0) / (1024*1024) if f.get('filesize') else 0
                size_str = f"{size_mb:.1f}MB" if size_mb > 0 else "?"
                h = f.get('height')
                fps = f.get('fps') or ''
                print(f"{idx}. id={f['id']} {h or '?'}p{'' if not fps else f'@{fps}fps'} {f['ext']} {size_str}")
                idx_map[idx] = {'kind': 'combined', 'id': f['id'], 'height': h}
                idx += 1
        if video_only:
            print("\nVideo-only formats (no audio):")
            for f in video_only:
                size_mb = (f['filesize'] or 0) / (1024*1024) if f.get('filesize') else 0
                size_str = f"{size_mb:.1f}MB" if size_mb > 0 else "?"
                h = f.get('height')
                fps = f.get('fps') or ''
                print(f"{idx}. id={f['id']} {h or '?'}p{'' if not fps else f'@{fps}fps'} {f['ext']} {size_str}")
                idx_map[idx] = {'kind': 'video', 'id': f['id'], 'height': h}
                idx += 1
        if audio_only:
            print("\nAudio-only formats:")
            for f in audio_only:
                size_mb = (f['filesize'] or 0) / (1024*1024) if f.get('filesize') else 0
                size_str = f"{size_mb:.1f}MB" if size_mb > 0 else "?"
                abr = f.get('tbr')
                abr_str = f"{abr}kbps" if abr else ''
                print(f"{idx}. id={f['id']} {f['ext']} {abr_str} {size_str}")
                idx_map[idx] = {'kind': 'audio', 'id': f['id'], 'height': None}
                idx += 1

        print(f"{idx}. Audio only (auto)")
        audio_auto_idx = idx

        while True:
            try:
                choice = input(f"\nSelect (0-{audio_auto_idx}): ").strip()
                n = int(choice)
            except ValueError:
                print("Enter a valid number.")
                continue

            if n == 0:
                return {'selector': 'best', 'audio_only': False}
            if n == audio_auto_idx:
                return {'selector': 'bestaudio/best', 'audio_only': True}
            sel = idx_map.get(n)
            if not sel:
                print("Invalid choice.")
                continue
            if sel['kind'] == 'combined':
                return {'selector': sel['id'], 'audio_only': False}
            if sel['kind'] == 'video':
                if ffmpeg_available:
                    return {'selector': f"{sel['id']}+bestaudio[ext=m4a]/{sel['id']}+bestaudio", 'audio_only': False}
                else:
                    print("Warning: Selected video-only format but FFmpeg not found; merging audio won't be possible.")
                    proceed = input("Proceed with video-only download? (y/N): ").strip().lower()
                    if proceed.startswith('y'):
                        return {'selector': sel['id'], 'audio_only': False}
                    else:
                        continue
            if sel['kind'] == 'audio':
                return {'selector': sel['id'], 'audio_only': True}

    def print_format_table(self, url: str) -> bool:
        """Print a full, readable format list for a video URL. Returns True on success."""
        info = self._extract_all_formats(url)
        if not info or 'formats' not in info:
            print("Could not retrieve format list.")
            return False

        print_title = info.get('title') or ''
        if print_title:
            print(f"\nTitle: {print_title}")

        formats = info['formats']
        combined: List[Dict[str, Any]] = []
        video_only: List[Dict[str, Any]] = []
        audio_only: List[Dict[str, Any]] = []

        for f in formats:
            v = f.get('vcodec')
            a = f.get('acodec')
            row = {
                'id': f.get('format_id'),
                'height': f.get('height'),
                'fps': f.get('fps'),
                'ext': f.get('ext'),
                'filesize': f.get('filesize') or f.get('filesize_approx'),
                'tbr': f.get('tbr'),
                'vcodec': v,
                'acodec': a,
            }
            if (v and v != 'none') and (a and a != 'none'):
                combined.append(row)
            elif (v and v != 'none') and (not a or a == 'none'):
                video_only.append(row)
            elif (not v or v == 'none') and (a and a != 'none'):
                audio_only.append(row)

        def sort_key(x):
            return (x.get('height') or 0, x.get('tbr') or 0)

        combined.sort(key=sort_key, reverse=True)
        video_only.sort(key=sort_key, reverse=True)
        audio_only.sort(key=lambda x: (x.get('tbr') or 0, x.get('filesize') or 0), reverse=True)

        def _size_str(val: Optional[int]) -> str:
            if not val:
                return '?'
            try:
                mb = float(val) / (1024 * 1024)
                return f"{mb:.1f}MB"
            except Exception:
                return '?'

        if combined:
            print("\nCombined (video+audio):")
            for f in combined:
                h = f.get('height')
                fps = f.get('fps') or ''
                print(f"  id={f['id']}  {h or '?'}p{'' if not fps else f'@{fps}fps'}  {f['ext']}  { _size_str(f.get('filesize')) }")
        if video_only:
            print("\nVideo-only (requires merge for audio):")
            for f in video_only:
                h = f.get('height')
                fps = f.get('fps') or ''
                print(f"  id={f['id']}  {h or '?'}p{'' if not fps else f'@{fps}fps'}  {f['ext']}  { _size_str(f.get('filesize')) }")
        if audio_only:
            print("\nAudio-only:")
            for f in audio_only:
                abr = f.get('tbr')
                abr_str = f"{abr}kbps" if abr else ''
                print(f"  id={f['id']}  {f['ext']}  {abr_str}  { _size_str(f.get('filesize')) }")

        return True

    def _get_archive_path(self, playlist_folder: Path, custom_archive: Optional[str]) -> Path:
        if custom_archive:
            return Path(custom_archive)
        return playlist_folder / '.download-archive.txt'

    def _read_archive_ids(self, archive_path: Path) -> Set[str]:
        ids: Set[str] = set()
        try:
            if archive_path.exists():
                for line in archive_path.read_text(encoding='utf-8', errors='ignore').splitlines():
                    parts = line.strip().split()
                    if parts:
                        ids.add(parts[-1])  # last token is typically the video id
        except Exception:
            pass
        return ids

    def get_playlist_sync_status(self, url: str, playlist_folder: Path, archive_path: Optional[Path]) -> Dict[str, Any]:
        info = self.get_playlist_info(url)
        if not info or not info.get('entries'):
            return {'total': 0, 'archive': 0, 'missing': 0}
        total = info['entry_count']
        archived = 0
        if archive_path:
            ids = self._read_archive_ids(archive_path)
            # entries may be dicts with 'id'
            for e in info['entries']:
                vid = e.get('id')
                if vid and vid in ids:
                    archived += 1
        missing = max(total - archived, 0)
        return {'total': total, 'archive': archived, 'missing': missing}

    def get_playlist_available_qualities(self, url: str, sample_size: int = 3) -> List[int]:
        """Sample the first N items of a playlist and return the union of available heights (descending)."""
        info = self.get_playlist_info(url)
        if not info or not info.get('entries'):
            return []

        heights: Set[int] = set()
        entries = list(info['entries'])[:sample_size]
        for entry in entries:
            vid_id = entry.get('id')
            vid_url = None
            if vid_id:
                vid_url = f"https://www.youtube.com/watch?v={vid_id}"
            elif entry.get('url'):
                # Some extractors return full URLs
                vid_url = entry['url']
            if not vid_url:
                continue
            try:
                fmts = self.get_available_formats(vid_url, silent=True)
                for f in fmts:
                    h = f.get('height')
                    if isinstance(h, int):
                        heights.add(h)
            except Exception:
                continue

        return sorted(heights, reverse=True)
    
    def select_quality_manually(self, url: str) -> Optional[str]:
        """Let user manually select video quality"""
        formats = self.get_available_formats(url)
        
        if not formats:
            print("No video formats found. Using default quality.")
            return 'best'
        
        print("\nAvailable video qualities:")
        print("0. Best available (auto)")
        
        for i, fmt in enumerate(formats, 1):
            size_mb = fmt['filesize'] / (1024 * 1024) if fmt['filesize'] else 0
            size_str = f"{size_mb:.1f}MB" if size_mb > 0 else "Unknown size"
            print(f"{i}. {fmt['height']}p ({fmt['ext']}) - {size_str}")
        
        print(f"{len(formats) + 1}. Audio only (MP3)")
        
        while True:
            try:
                choice = input(f"\nSelect quality (0-{len(formats) + 1}): ").strip()
                choice_num = int(choice)
                
                if choice_num == 0:
                    return 'best'
                elif choice_num == len(formats) + 1:
                    return 'audio_only'
                elif 1 <= choice_num <= len(formats):
                    selected_format = formats[choice_num - 1]
                    return f"{selected_format['height']}p"
                else:
                    print("Invalid choice. Please try again.")
            except ValueError:
                print("Please enter a valid number.")
            except KeyboardInterrupt:
                print("\nSelection cancelled.")
                return None

    def download_playlist(self, url: str, quality: str = 'best', audio_only: bool = False, 
                         output_format: str = 'mp4', manual_select: bool = False,
                         use_archive: bool = True, archive_file: Optional[str] = None,
                         append_id: bool = False, retries: int = 10, fragment_retries: int = 10) -> bool:
        """Download entire YouTube playlist"""
        
        if not self.is_playlist_url(url):
            print("Error: URL is not a valid playlist")
            return False
        
        # Get playlist info
        playlist_info = self.get_playlist_info(url)
        if not playlist_info:
            print("Error: Could not get playlist information")
            return False
        
        print(f"Playlist: {playlist_info['title']}")
        print(f"Uploader: {playlist_info['uploader']}")
        print(f"Videos: {playlist_info['entry_count']}")
        
        # Ask for confirmation
        proceed = input(f"\nDownload {playlist_info['entry_count']} videos? (y/N): ").lower().startswith('y')
        if not proceed:
            print("Playlist download cancelled.")
            return False
        
        # Manual quality selection for playlist
        selected_quality = quality
        selected_audio_only = audio_only
        
        if manual_select:
            print("\nFor playlist downloads, you can:")
            print("1. Use the same quality for all videos")
            print("2. Let yt-dlp choose the best available for each video")

            choice = input("Choose option (1/2): ").strip()
            if choice == '1':
                print("\nDetecting available qualities across the playlist (sampling a few videos)...")
                heights = self.get_playlist_available_qualities(url)
                if not heights:
                    print("Could not detect playlist qualities. Falling back to 'best'.")
                    selected_quality = 'best'
                else:
                    print("\nSelect quality to use for all videos:")
                    print("0. Best available")
                    for idx, h in enumerate(heights, start=1):
                        print(f"{idx}. {h}p")
                    audio_idx = len(heights) + 1
                    print(f"{audio_idx}. Audio only (MP3)")

                    while True:
                        quality_choice = input(f"Select (0-{audio_idx}): ").strip()
                        try:
                            qn = int(quality_choice)
                        except ValueError:
                            print("Enter a number from the list.")
                            continue

                        if qn == 0:
                            selected_quality = 'best'
                            break
                        elif qn == audio_idx:
                            selected_audio_only = True
                            selected_quality = 'best'
                            break
                        elif 1 <= qn <= len(heights):
                            selected_quality = f"{heights[qn-1]}p"
                            break
                        else:
                            print("Invalid choice. Try again.")
            else:
                selected_quality = 'best'  # Let yt-dlp choose best for each video
        
        # Create playlist folder
        playlist_folder = self.download_path / self.sanitize_filename(playlist_info['title'])
        playlist_folder.mkdir(exist_ok=True)

        # Archive/resume status
        archive_path = self._get_archive_path(playlist_folder, archive_file) if use_archive else None
        if archive_path:
            status = self.get_playlist_sync_status(url, playlist_folder, archive_path)
            if status['total']:
                print(f"Sync status: {status['archive']} downloaded, {status['missing']} remaining, total {status['total']}")
        
        # Optional pre-check: delete lower-than-requested files to allow re-download
        requested_height = self._parse_quality_height(selected_quality)
        if requested_height and not selected_audio_only:
            to_delete = []
            # Build a map of existing files that are below requested height
            for entry in playlist_info.get('entries', []):
                title = entry.get('title') or entry.get('id') or ''
                if not title:
                    continue
                files = self._find_existing_by_title(playlist_folder, self.sanitize_filename(title))
                if not files:
                    continue
                existing_height = self._best_local_height(files)
                if existing_height and existing_height < requested_height:
                    to_delete.extend(files)

            if to_delete:
                print(f"\nFound {len(to_delete)} existing file(s) below {requested_height}p.")
                preview = [p.name for p in to_delete[:5]]
                if preview:
                    print("Examples:", ", ".join(preview))
                if input("Delete and re-download higher quality? (y/N): ").lower().startswith('y'):
                    for p in to_delete:
                        try:
                            p.unlink(missing_ok=True)
                        except Exception as e:
                            print(f"Could not delete {p.name}: {e}")

        # Configure download options for playlist
        format_selector = self._get_format_selector(selected_quality, selected_audio_only, self.check_ffmpeg())
        print(f"Using format selector: {format_selector}")
        
        outtmpl = '%(playlist_index)s - %(title)s.%(ext)s'
        if append_id:
            outtmpl = '%(playlist_index)s - %(title)s [%(id)s].%(ext)s'

        ydl_opts = {
            'outtmpl': str(playlist_folder / outtmpl),
            'format': format_selector,
            'restrictfilenames': True,
            'ignoreerrors': True,  # Continue on errors
            'merge_output_format': output_format if not selected_audio_only else None,
            'extract_flat': False,  # Extract full info for each video
            'continuedl': True,
            'retries': retries,
            'fragment_retries': fragment_retries,
            'overwrites': False,
        }
        if archive_path:
            ydl_opts['download_archive'] = str(archive_path)
        
        if selected_audio_only:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        
        print(f"\nDownloading to: {playlist_folder}")
        print("Starting playlist download...\n")
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            print(f"\nPlaylist download completed!")
            print(f"Downloaded to: {playlist_folder}")
            return True
            
        except Exception as e:
            print(f"Playlist download error: {str(e)}")
            return False

    def verify_download_quality(self, file_path: str, expected_quality: str) -> None:
        """Verify the quality of downloaded video"""
        try:
            import json
            # Use yt-dlp to get info about the downloaded file
            result = subprocess.run([
                'yt-dlp', '--print', 'resolution,filesize', '--no-download', file_path
            ], capture_output=True, text=True)
            
            if result.returncode == 0 and result.stdout.strip():
                info = result.stdout.strip().split('\n')
                if info:
                    resolution = info[0] if len(info) > 0 else "Unknown"
                    print(f"✓ Downloaded resolution: {resolution}")
                    if expected_quality != 'best' and expected_quality != 'worst':
                        expected_height = int(expected_quality.replace('p', ''))
                        if 'x' in resolution:
                            actual_height = int(resolution.split('x')[1])
                            if actual_height < expected_height:
                                print(f"⚠ Warning: Expected {expected_quality} but got {actual_height}p")
                                print("This might happen if the video is not available in the requested quality")
        except Exception as e:
            print(f"Could not verify download quality: {str(e)}")

    def download_video(self, url: str, quality: str = 'best', audio_only: bool = False, 
                      output_format: str = 'mp4', manual_select: bool = False,
                      retries: int = 10, fragment_retries: int = 10) -> bool:
        """Download video from YouTube URL"""
        
        if not self.is_valid_youtube_url(url):
            print(f"Invalid YouTube URL: {url}")
            return False
        
        # Check if it's a playlist
        if self.is_playlist_url(url):
            return self.download_playlist(url, quality, audio_only, output_format, manual_select)
        
        # Get video info
        info = self.get_video_info(url)
        if info:
            print(f"Title: {info['title']}")
            print(f"Uploader: {info['uploader']}")
            if info['duration']:
                minutes, seconds = divmod(info['duration'], 60)
                print(f"Duration: {minutes}:{seconds:02d}")
        
        # Manual selection flow (quality or exact format) for single videos
        custom_selector: Optional[str] = None
        if manual_select and not self.is_playlist_url(url):
            ffmpeg_available = self.check_ffmpeg()
            print("\nSelection mode:")
            print("1. Choose by quality (height)")
            print("2. Choose exact file format (advanced)")
            mode = input("Select (1/2): ").strip()
            if mode == '2':
                picked = self.select_format_manually(url, ffmpeg_available)
                if not picked:
                    return False
                custom_selector = picked['selector']
                audio_only = bool(picked.get('audio_only'))
                # When exact selector chosen, keep quality as 'best' for downstream logs
                quality = 'best'
            else:
                selected_quality = self.select_quality_manually(url)
                if selected_quality is None:
                    return False
                elif selected_quality == 'audio_only':
                    audio_only = True
                    quality = 'best'
                else:
                    quality = selected_quality

        # Check for existing local file and offer upgrade/skip
        if info and not audio_only:
            requested_height = self._parse_quality_height(quality)
            existing_files = self._find_existing_by_title(self.download_path, self.sanitize_filename(info['title']))
            if existing_files:
                existing_height = self._best_local_height(existing_files)
                if requested_height and existing_height and existing_height >= requested_height:
                    print(f"Found existing '{info['title']}' at {existing_height}p which meets/exceeds requested {requested_height}p. Skipping.")
                    return True
                else:
                    # If requesting 'best', try to detect remote max
                    remote_max = None
                    if requested_height is None:
                        fmts = self.get_available_formats(url)
                        if fmts:
                            remote_max = max((f.get('height') or 0) for f in fmts)
                    disp_existing = f"{existing_height}p" if existing_height else "unknown quality"
                    disp_target = f"{requested_height}p" if requested_height else (f"best ({remote_max}p)" if remote_max else "best")
                    choice = input(f"Found existing file at {disp_existing}. Replace with {disp_target}? (y/N): ").strip().lower()
                    if choice.startswith('y'):
                        for p in existing_files:
                            try:
                                p.unlink(missing_ok=True)
                            except Exception as e:
                                print(f"Could not delete {p.name}: {e}")
                    else:
                        print("Keeping existing file; skipping download.")
                        return True
        
        # Check FFmpeg for high quality downloads
        ffmpeg_available = self.check_ffmpeg()
        if not ffmpeg_available:
            print("⚠ Warning: FFmpeg not found!")
            print("  - High-quality downloads may not work properly")
            print("  - Video and audio might be downloaded as separate files")
            print("  - Consider installing FFmpeg for better results")
            if quality in ['2160p', '4k', '1440p', '1080p']:
                print(f"  - Requested {quality} may fallback to lower quality without FFmpeg")
        else:
            print("✓ FFmpeg detected - high quality downloads available")

        # Configure download options
        format_selector = custom_selector or self._get_format_selector(quality, audio_only, ffmpeg_available)
        print(f"Using format selector: {format_selector}")
        print(f"Target quality: {quality}")
        if not audio_only and custom_selector is None:
            print("Checking available formats for this video...")
            # Show available formats for the specific quality
            available_formats = self.get_available_formats(url)
            if available_formats:
                requested_height_check: Optional[int] = None
                if quality.endswith('p') and quality != 'best' and quality != 'worst':
                    try:
                        requested_height_check = int(quality.replace('p', ''))
                    except Exception:
                        requested_height_check = None
                if requested_height_check:
                    available_at_quality = [f for f in available_formats if f['height'] == requested_height_check]
                    if available_at_quality:
                        print(f"✓ {quality} is available for this video")
                    else:
                        print(f"⚠ {quality} is NOT available for this video")
                        available_heights = [f['height'] for f in available_formats if f.get('height')]
                        print(f"Available qualities: {sorted(set(available_heights), reverse=True)}")
                        lower_qualities = [h for h in available_heights if h < requested_height_check]
                        if lower_qualities:
                            closest = max(lower_qualities)
                            print(f"Will likely download at {closest}p instead")
            else:
                print("Could not check available formats")

        ydl_opts = {
            'outtmpl': str(self.download_path / '%(title)s.%(ext)s'),
            'format': format_selector,
            'restrictfilenames': True,
            'merge_output_format': output_format if not audio_only else None,
            'continuedl': True,
            'retries': retries,
            'fragment_retries': fragment_retries,
            'overwrites': False,
        }

        if audio_only:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]

        print("Starting download...")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                print(f"Successfully downloaded: {info['title'] if info else 'Video'}")

                # Try to verify the quality of the downloaded file
                if not audio_only and quality != 'best' and quality != 'worst':
                    print("Verifying download quality...")
                    if info:
                        expected_filename = self.sanitize_filename(info['title']) + '.' + output_format
                        file_path = self.download_path / expected_filename
                        if file_path.exists():
                            self.verify_download_quality(str(file_path), quality)

                return True
        except Exception as e:
            print(f"Download failed: {str(e)}")
            return False

    def _parse_quality_height(self, quality: str) -> Optional[int]:
        """Parse a quality string like '1080p' to integer height; return None for best/worst/invalid."""
        if not quality:
            return None
        q = quality.lower()
        if q in ('best', 'worst'):
            return None
        m = re.match(r'^(\d{3,4})p$', q)
        return int(m.group(1)) if m else None

    def _get_local_height(self, file_path: Path) -> Optional[int]:
        """Return video height using ffprobe or mediainfo; None if unavailable/unknown."""
        try:
            # ffprobe
            result = subprocess.run(
                ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', str(file_path)],
                capture_output=True, text=True, check=True
            )
            import json as _json
            data = _json.loads(result.stdout)
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    return int(stream.get('height') or 0) or None
        except Exception:
            pass
        try:
            # mediainfo
            result = subprocess.run(
                ['mediainfo', '--Output=JSON', str(file_path)],
                capture_output=True, text=True, check=True
            )
            import json as _json
            data = _json.loads(result.stdout)
            tracks = data.get('media', {}).get('track', [])
            for track in tracks:
                if track.get('@type') == 'Video':
                    h = track.get('Height')
                    try:
                        return int(h) if h is not None else None
                    except Exception:
                        return None
        except Exception:
            pass
        return None

    def _best_local_height(self, files: List[Path]) -> Optional[int]:
        """Return the maximum height among given files."""
        heights = []
        for f in files:
            if f.suffix.lower() == '.part':
                continue
            h = self._get_local_height(f)
            if h:
                heights.append(h)
        return max(heights) if heights else None

    def _find_existing_by_title(self, folder: Path, sanitized_title: str) -> List[Path]:
        """Find files in folder whose names contain the sanitized title; filter known video extensions."""
        exts = ['.mp4', '.mkv', '.webm', '.mov', '.avi']
        matches: List[Path] = []
        try:
            for ext in exts:
                matches.extend(folder.glob(f"*{sanitized_title}*{ext}"))
        except Exception:
            pass
        # filter out temp/incomplete
        return [m for m in matches if not m.name.endswith('.part')]
    
    def _get_format_selector(self, quality: str, audio_only: bool, ffmpeg_available: bool = True) -> str:
        """Get format selector based on preferences. Supports 'best'/'worst' or '<height>p' (e.g., '1440p')."""
        if audio_only:
            return 'bestaudio/best'

        q = (quality or '').lower()
        if q in ('best', ''):
            return 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best' if ffmpeg_available else 'best[ext=mp4]/best'
        if q == 'worst':
            return 'worst[ext=mp4]/worst'

        # Parse dynamic height like '1080p'
        match = re.match(r'^(\d{3,4})p$', q)
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

        # Unknown format string, fall back to best
        return 'best[ext=mp4]/best'
    
    def download_multiple(self, urls: List[str], **kwargs) -> None:
        """Download multiple videos/playlists"""
        successful = failed = 0
        
        for i, url in enumerate(urls, 1):
            print(f"\n{'='*60}")
            print(f"Processing {i}/{len(urls)}")
            print(f"{'='*60}")
            
            if self.download_video(url.strip(), **kwargs):
                successful += 1
            else:
                failed += 1
        
        print(f"\nSummary: {successful} successful, {failed} failed")
    
    def sanitize_filename(self, filename: str) -> str:
        """Remove invalid characters from filename"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename[:200]  # Limit length
    
    def set_download_path(self, path: str) -> bool:
        """Set custom download path"""
        try:
            self.download_path = Path(path)
            self.download_path.mkdir(parents=True, exist_ok=True)
            print(f"Download path set to: {self.download_path}")
            return True
        except Exception as e:
            print(f"Error setting download path: {str(e)}")
            return False


def main():
    parser = argparse.ArgumentParser(description='YouTube Video & Playlist Downloader Agent')
    parser.add_argument('urls', nargs='*', help='YouTube video/playlist URLs')
    parser.add_argument('-q', '--quality',
                       default='best',
                       help='Video quality: best|worst|<height>p (e.g., 1440p)')
    parser.add_argument('-a', '--audio-only', action='store_true', help='Download audio only (MP3)')
    parser.add_argument('-f', '--format', choices=['mp4', 'webm', 'mkv'], 
                       default='mp4', help='Output format')
    parser.add_argument('-o', '--output', help='Output directory')
    parser.add_argument('-i', '--interactive', action='store_true', help='Interactive mode')
    parser.add_argument('-m', '--manual-select', action='store_true', 
                       help='Manually select quality for each video')
    parser.add_argument('--skip-path-setup', action='store_true', 
                       help='Skip download path setup (use default)')
    parser.add_argument('--no-archive', action='store_true', help='Disable download archive (may redownload)')
    parser.add_argument('--archive-file', help='Custom path to yt-dlp download archive file')
    parser.add_argument('--append-id', action='store_true', help='Append [id] to filenames to avoid collisions')
    parser.add_argument('--retries', type=int, default=10, help='Download retry count')
    parser.add_argument('--fragment-retries', type=int, default=10, help='Fragment retry count')
    parser.add_argument('--list-formats-only', action='store_true', help='Print available formats for the given URL(s) and exit')
    
    args = parser.parse_args()
    
    # Check for required dependencies
    try:
        import tqdm
    except ImportError:
        print("Error: tqdm is required for progress bars")
        print("Install with: pip install tqdm")
        sys.exit(1)
    
    downloader = YouTubeDownloader()
    
    # Setup download path unless skipped
    if not args.skip_path_setup:
        if not downloader.setup_download_path():
            sys.exit(1)
    else:
        downloader.download_path.mkdir(parents=True, exist_ok=True)
    
    if args.output:
        downloader.set_download_path(args.output)

    # List formats only and exit
    if args.list_formats_only:
        if not args.urls:
            print("Error: --list-formats-only requires at least one URL.")
            sys.exit(2)
        for url in args.urls:
            print(f"\n=== Formats for: {url} ===")
            if downloader.is_playlist_url(url):
                print("Note: URL is a playlist; showing formats for the first item only.")
                plist = downloader.get_playlist_info(url)
                if plist and plist.get('entries'):
                    entry = plist['entries'][0]
                    vid_url = None
                    vid_id = entry.get('id')
                    if vid_id:
                        vid_url = f"https://www.youtube.com/watch?v={vid_id}"
                    elif entry.get('url'):
                        vid_url = entry['url']
                    if vid_url:
                        downloader.print_format_table(vid_url)
                    else:
                        print("Could not resolve first video URL from playlist.")
                else:
                    print("Could not load playlist entries.")
            else:
                downloader.print_format_table(url)
        sys.exit(0)
    
    # Interactive mode
    if args.interactive or not args.urls:
        print("YouTube Video & Playlist Downloader")
        print("=" * 50)
        
        try:
            while True:
                print("\nOptions:")
                print("1. Download single video")
                print("2. Download playlist")
                print("3. Download multiple URLs") 
                print("4. Change settings")
                print("5. Change download path")
                print("6. Exit")
                
                choice = input("\nSelect (1-6): ").strip()
                
                if choice == '1':
                    url = input("Enter YouTube video URL: ").strip()
                    if url and downloader.is_valid_youtube_url(url):
                        manual = input("Manually select quality? (y/N): ").lower().startswith('y')
                        downloader.download_video(
                            url, 
                            quality=args.quality,
                            audio_only=args.audio_only,
                            output_format=args.format,
                            manual_select=manual
                        )
                    else:
                        print("Invalid or empty URL")
                
                elif choice == '2':
                    url = input("Enter YouTube playlist URL: ").strip()
                    if url and downloader.is_playlist_url(url):
                        manual = input("Manually select quality? (y/N): ").lower().startswith('y')
                        downloader.download_playlist(
                            url,
                            quality=args.quality,
                            audio_only=args.audio_only,
                            output_format=args.format,
                            manual_select=manual,
                            use_archive=not args.no_archive,
                            archive_file=args.archive_file,
                            append_id=args.append_id,
                            retries=args.retries,
                            fragment_retries=args.fragment_retries
                        )
                    else:
                        print("Invalid playlist URL")
                
                elif choice == '3':
                    print("Enter URLs (one per line, empty line to finish):")
                    urls = []
                    while True:
                        url = input().strip()
                        if not url:
                            break
                        if downloader.is_valid_youtube_url(url):
                            urls.append(url)
                        else:
                            print(f"Invalid URL skipped: {url}")
                    
                    if urls:
                        manual = input("Manually select quality for each? (y/N): ").lower().startswith('y')
                        downloader.download_multiple(
                            urls,
                            quality=args.quality,
                            audio_only=args.audio_only,
                            output_format=args.format,
                            manual_select=manual,
                            use_archive=not args.no_archive,
                            archive_file=args.archive_file,
                            append_id=args.append_id,
                            retries=args.retries,
                            fragment_retries=args.fragment_retries
                        )
                    else:
                        print("No valid URLs provided")
                
                elif choice == '4':
                    print("Current settings:")
                    print(f"   Quality: {args.quality}")
                    print(f"   Audio only: {args.audio_only}")
                    print(f"   Format: {args.format}")
                    print(f"   Output: {downloader.download_path}")
                    
                    new_quality = input(f"New quality ({args.quality}) [best|worst|<height>p]: ").strip()
                    if new_quality == '' or new_quality.lower() == 'best' or new_quality.lower() == 'worst' or re.match(r'^\d{3,4}p$', new_quality.lower()):
                        if new_quality:
                            args.quality = new_quality
                        else:
                            args.quality = 'best'
                        print(f"Quality updated to {args.quality}")
                    else:
                        print("Invalid quality string. Use best|worst|<height>p, e.g., 1080p")
                
                elif choice == '5':
                    downloader.setup_download_path()
                
                elif choice == '6':
                    print("Goodbye!")
                    break
                else:
                    print("Invalid choice")
        
        except KeyboardInterrupt:
            print("\n\nInterrupted. Goodbye!")
    
    # Command line mode
    else:
        downloader.download_multiple(
            args.urls,
            quality=args.quality,
            audio_only=args.audio_only,
            output_format=args.format,
            manual_select=args.manual_select,
            use_archive=not args.no_archive,
            archive_file=args.archive_file,
            append_id=args.append_id,
            retries=args.retries,
            fragment_retries=args.fragment_retries
        )


if __name__ == "__main__":
    main()