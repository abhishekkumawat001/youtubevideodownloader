# downloader/cli.py
# CLI entry point (argparse, main, calls core)

import argparse
import sys
from .core import YouTubeDownloader
from .utils import is_valid_youtube_url, is_playlist_url

def main():
    # ...argparse and main logic from youtube.py...
    pass

if __name__ == "__main__":
    main()
