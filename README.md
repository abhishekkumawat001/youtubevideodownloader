# Course Material Downloader

Lightweight utilities for downloading YouTube videos/playlists with yt-dlp and analyzing downloaded files.

## Contents
 - youtube.py — full-featured CLI and interactive YouTube/playlist downloader (uses yt-dlp; supports manual quality, format listing, playlists, resume/archive).
 - analyze_videos.py — inspects local video files (via ffprobe/mediainfo) to report resolution and rough size heuristics.

## Requirements
- Python 3.9+
- Packages:
  - yt-dlp
  - tqdm
- Optional tools for analysis/merging:
  - FFmpeg (ffmpeg/ffprobe on PATH)
  - Mediainfo (optional fallback)

Install Python packages:

```powershell
pip install -r requirements.txt
```

Install FFmpeg on Windows:
- Winget: `winget install FFmpeg.FFmpeg`
- Chocolatey: `choco install ffmpeg`
- Or download from https://ffmpeg.org and add to PATH

## Quick start
Interactive mode:
```powershell
python .\youtube.py -i
```
Single video at 1080p to default Downloads/YouTube_Downloads:
```powershell
python .\youtube.py "<YOUTUBE_URL>" -q 1080p -f mp4 --skip-path-setup
```
Playlist download (confirm prompt, optional manual selection):
```powershell
python .\youtube.py "<PLAYLIST_URL>" -q best -m --skip-path-setup
```
Analyze a folder of videos:
```powershell
python .\analyze_videos.py -p .\deeplearning
```

List available formats (no download):
```powershell
python .\youtube.py "<YOUTUBE_URL>" --list-formats-only --skip-path-setup
# For a playlist URL, this shows formats for the first item only
```

## Notes
- youtube.py uses a robust default path on Windows (Downloads/YouTube_Downloads). You can override with -o.
- Without FFmpeg, yt-dlp may fetch separate video/audio at high resolutions or fall back to lower quality.
- For login-restricted or age-restricted content, consider passing cookies to yt-dlp (not wired here by default).

## Ideas for improvement
- Unify duplicate downloader scripts into one module; keep one CLI.
- Add download archive/resume flags and better logging.
- Add config file (JSON/ENV) and batch URL input support.
- Optional: write subtitles/thumbnails/metadata via yt-dlp postprocessors.
