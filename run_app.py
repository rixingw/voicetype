#!/usr/bin/env python3
"""Launcher for VoiceType menu bar app."""

import sys

# Check Python version
if sys.version_info < (3, 10) or sys.version_info >= (3, 14):
    print(f"❌ Error: VoiceType requires Python >=3.10, <3.14")
    print(f"   Current version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    print(f"\n   Please install a compatible Python version:")
    print(f"   - Python 3.10, 3.11, 3.12, or 3.13")
    print(f"   - Using pyenv: pyenv install 3.13")
    print(f"   - Using Homebrew: brew install python@3.13")
    sys.exit(1)

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from voicetype_app import main

if __name__ == "__main__":
    main()

