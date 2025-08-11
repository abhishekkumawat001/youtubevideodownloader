#!/usr/bin/env python3
"""
Analyze existing downloaded videos to check their actual quality
"""

import os
import subprocess
import json
from pathlib import Path
import argparse


def analyze_video_quality(video_path: Path) -> str:
    """Analyze video resolution using ffprobe or mediainfo if available."""
    try:
        # Try ffprobe first (bundled with FFmpeg)
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', str(video_path)],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    width = stream.get('width', 0)
                    height = stream.get('height', 0)
                    return f"{width}x{height} ({height}p)"
        except Exception:
            pass

        # Fallback: mediainfo if available
        try:
            result = subprocess.run(
                ['mediainfo', '--Output=JSON', str(video_path)],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)
            tracks = data.get('media', {}).get('track', [])
            for track in tracks:
                if track.get('@type') == 'Video':
                    width = track.get('Width')
                    height = track.get('Height')
                    if width and height:
                        return f"{width}x{height} ({height}p)"
        except Exception:
            pass

        return "Unknown (analysis tools not available)"

    except Exception as e:
        return f"Error: {e}"


def analyze_folder(folder_path: str) -> None:
    """Analyze all videos in a folder."""
    folder = Path(folder_path)
    if not folder.exists():
        print(f"Folder not found: {folder}")
        return

    print(f"Analyzing videos in: {folder}")
    print("=" * 60)

    video_extensions = ['.mp4', '.mkv', '.webm', '.avi', '.mov']
    video_files = []
    for ext in video_extensions:
        video_files.extend(folder.glob(f'*{ext}'))

    if not video_files:
        print("No video files found")
        return

    total_size = 0
    for video_file in sorted(video_files):
        if video_file.name.endswith('.part'):
            print(f"⚠ INCOMPLETE: {video_file.name}")
            continue

        file_size = video_file.stat().st_size
        size_mb = file_size / (1024 * 1024)
        total_size += file_size

        quality = analyze_video_quality(video_file)

        # Heuristic note based on size
        expected_size_note = ""
        if size_mb < 20:
            expected_size_note = " (⚠ Very small - likely low quality)"
        elif size_mb < 50:
            expected_size_note = " (⚠ Small - possibly 480p or lower)"
        elif size_mb < 100:
            expected_size_note = " (~ Moderate - possibly 720p)"
        elif size_mb > 200:
            expected_size_note = " (✓ Large - likely 1080p+)"

        print(f"{video_file.name}")
        print(f"   Quality: {quality}")
        print(f"   Size: {size_mb:.1f} MB{expected_size_note}")
        print()

    total_mb = total_size / (1024 * 1024)
    print(f"Total folder size: {total_mb:.1f} MB ({len(video_files)} videos)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze local video files for resolution and size")
    parser.add_argument(
        '-p', '--path',
        default=str(Path(__file__).parent / 'deeplearning'),
        help="Folder path to analyze (default: ./deeplearning)",
    )
    args = parser.parse_args()

    analyze_folder(args.path)

    print("\n" + "=" * 60)
    print("Note: This analysis is based on file sizes and available tools.")
    print("Small file sizes often indicate lower quality downloads.")
    print("For accurate analysis, install ffprobe (comes with FFmpeg).")
