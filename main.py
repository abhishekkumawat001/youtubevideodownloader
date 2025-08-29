#!/usr/bin/env python3
"""
YouTube Video Downloader - Main Entry Point
Enhanced version with queue management, profiles, and advanced features
"""

import sys
import os

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from downloader.cli import main

if __name__ == "__main__":
    main()
