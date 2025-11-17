#!/bin/bash
# VoiceType Menu Bar App Launcher
# This script runs the VoiceType menu bar app with default settings

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Please create one first:"
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Check Python version before running
PYTHON_VERSION=$(python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]) || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 14 ]); then
    echo "❌ Error: VoiceType requires Python >=3.10, <3.14"
    echo "   Current version: $PYTHON_VERSION"
    echo ""
    echo "   Please install a compatible Python version:"
    echo "   - Python 3.10, 3.11, 3.12, or 3.13"
    echo "   - Using pyenv: pyenv install 3.13"
    echo "   - Using Homebrew: brew install python@3.13"
    exit 1
fi

# Run the app
python run_app.py

