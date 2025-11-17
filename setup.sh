#!/bin/bash
# VoiceType Setup Script
# This script ensures the correct Python version is installed and sets up the environment

set -e  # Exit on error

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Required Python version
REQUIRED_MIN_MAJOR=3
REQUIRED_MIN_MINOR=10
REQUIRED_MAX_MINOR=13

echo "🔍 Checking Python version..."

# Function to check if a Python version is compatible
check_python_version() {
    local python_cmd=$1
    if command -v "$python_cmd" &> /dev/null; then
        local version=$($python_cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        if [ -n "$version" ]; then
            local major=$(echo $version | cut -d. -f1)
            local minor=$(echo $version | cut -d. -f2)
            
            if [ "$major" -eq "$REQUIRED_MIN_MAJOR" ] && [ "$minor" -ge "$REQUIRED_MIN_MINOR" ] && [ "$minor" -le "$REQUIRED_MAX_MINOR" ]; then
                echo "$python_cmd"
                return 0
            fi
        fi
    fi
    return 1
}

# Try to find compatible Python version
PYTHON_CMD=""
for cmd in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if check_python_version "$cmd"; then
        PYTHON_CMD="$cmd"
        PYTHON_VERSION=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
        echo "✅ Found compatible Python: $PYTHON_VERSION ($PYTHON_CMD)"
        break
    fi
done

# If no compatible Python found, try to install it
if [ -z "$PYTHON_CMD" ]; then
    echo "❌ No compatible Python version found (>=3.10, <3.14)"
    echo ""
    echo "🔧 Attempting to install Python 3.13..."
    
    # Try pyenv first (only sets local version, not global)
    if command -v pyenv &> /dev/null; then
        echo "   Using pyenv to install Python 3.13 (local to this directory only)..."
        pyenv install 3.13.2 --skip-existing 2>/dev/null || pyenv install 3.13.2
        pyenv local 3.13.2  # Sets .python-version file (local only, doesn't change global)
        PYTHON_CMD="python3.13"
        if check_python_version "$PYTHON_CMD"; then
            PYTHON_VERSION=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
            echo "✅ Installed Python $PYTHON_VERSION using pyenv (local to this directory)"
            echo "   Note: This does NOT change your global Python version"
        else
            PYTHON_CMD=""
        fi
    fi
    
    # Try Homebrew if pyenv didn't work (installs system-wide but doesn't change default)
    if [ -z "$PYTHON_CMD" ] && command -v brew &> /dev/null; then
        echo "   Using Homebrew to install Python 3.13..."
        echo "   Note: This installs Python system-wide but does NOT change your default Python"
        brew install python@3.13 2>/dev/null || echo "   Note: Homebrew installation may require manual setup"
        # Try to find the newly installed Python
        for cmd in python3.13 /opt/homebrew/bin/python3.13 /usr/local/bin/python3.13; do
            if check_python_version "$cmd"; then
                PYTHON_CMD="$cmd"
                PYTHON_VERSION=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
                echo "✅ Found Python $PYTHON_VERSION after Homebrew install"
                echo "   Note: Your default 'python3' command remains unchanged"
                break
            fi
        done
    fi
    
    # If still no Python, provide manual instructions
    if [ -z "$PYTHON_CMD" ]; then
        echo ""
        echo "❌ Could not automatically install Python."
        echo "   Please install Python 3.10-3.13 manually:"
        echo ""
        echo "   Option 1: Using pyenv"
        echo "     brew install pyenv"
        echo "     pyenv install 3.13.2"
        echo "     pyenv local 3.13.2"
        echo ""
        echo "   Option 2: Using Homebrew"
        echo "     brew install python@3.13"
        echo ""
        echo "   Option 3: Download from python.org"
        echo "     https://www.python.org/downloads/"
        echo ""
        exit 1
    fi
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo ""
    echo "📦 Creating virtual environment with Python $PYTHON_VERSION..."
    $PYTHON_CMD -m venv venv
    echo "✅ Virtual environment created"
else
    echo ""
    echo "📦 Virtual environment already exists"
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Verify the venv Python version
VENV_PYTHON_VERSION=$(python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
echo "   Using Python $VENV_PYTHON_VERSION in virtual environment"

# Upgrade pip
echo ""
echo "⬆️  Upgrading pip..."
python -m pip install --upgrade pip --quiet

# Install dependencies
echo ""
echo "📥 Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "You can now run the app with:"
echo "  ./run.sh"
echo ""
echo "Or directly:"
echo "  source venv/bin/activate"
echo "  python run_app.py"

