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
    echo "   Note: Python 3.14 is not yet supported due to numba dependency limitations."
    echo ""
    echo "🔧 Attempting to install Python 3.13..."
    
    # Try Homebrew first (more common on macOS, doesn't require pyenv setup)
    if command -v brew &> /dev/null; then
        echo "   Using Homebrew to install Python 3.13..."
        echo "   Note: This installs Python system-wide but does NOT change your default Python"
        if brew install python@3.13 2>/dev/null; then
            # Wait a moment for installation to complete
            sleep 2
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
        else
            echo "   ⚠️  Homebrew installation failed or already installed"
        fi
    fi
    
    # Try pyenv if Homebrew didn't work (only sets local version, not global)
    if [ -z "$PYTHON_CMD" ] && command -v pyenv &> /dev/null; then
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
    
    # If still no Python, provide manual instructions
    if [ -z "$PYTHON_CMD" ]; then
        echo ""
        echo "❌ Could not automatically install Python."
        echo "   Please install Python 3.10-3.13 manually:"
        echo ""
        if [[ "$OSTYPE" == "darwin"* ]]; then
            echo "   Option 1: Using Homebrew (recommended for macOS)"
            echo "     brew install python@3.13"
            echo "     Then run this script again"
            echo ""
            echo "   Option 2: Install pyenv first, then use it"
            echo "     brew install pyenv"
            echo "     pyenv install 3.13.2"
            echo "     pyenv local 3.13.2"
            echo "     Then run this script again"
            echo ""
        else
            echo "   Option 1: Using your system package manager"
            echo "     # Ubuntu/Debian"
            echo "     sudo apt-get update"
            echo "     sudo apt-get install python3.13 python3.13-venv"
            echo ""
            echo "     # Fedora"
            echo "     sudo dnf install python3.13"
            echo ""
            echo "   Option 2: Install pyenv first, then use it"
            echo "     curl https://pyenv.run | bash"
            echo "     pyenv install 3.13.2"
            echo "     pyenv local 3.13.2"
            echo ""
        fi
        echo "   Option 3: Download from python.org"
        echo "     https://www.python.org/downloads/"
        echo "     Install Python 3.13, then run this script again"
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

# Check for build tools (needed for numba)
echo ""
echo "🔧 Checking for build tools..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS - check for Xcode Command Line Tools
    if ! xcode-select -p &> /dev/null; then
        echo "⚠️  Xcode Command Line Tools not found."
        echo "   Installing Xcode Command Line Tools (this may take a while)..."
        xcode-select --install 2>/dev/null || echo "   Please install manually: xcode-select --install"
        echo "   After installation completes, run this script again."
        exit 1
    else
        echo "✅ Xcode Command Line Tools found"
    fi
fi

# Install build dependencies first
echo ""
echo "📦 Installing build dependencies..."
python -m pip install --upgrade wheel setuptools --quiet

# Install dependencies
echo ""
echo "📥 Installing dependencies..."
# Try to install with pre-built wheels first, fall back to building if needed
pip install -r requirements.txt || {
    echo ""
    echo "⚠️  Installation failed. Trying with build isolation disabled..."
    pip install --no-build-isolation -r requirements.txt || {
        echo ""
        echo "❌ Installation failed. Common solutions:"
        echo ""
        if [[ "$OSTYPE" == "darwin"* ]]; then
            echo "   1. Ensure Xcode Command Line Tools are installed:"
            echo "      xcode-select --install"
            echo ""
            echo "   2. Try installing numba separately first:"
            echo "      pip install numba"
            echo "      pip install -r requirements.txt"
        else
            echo "   1. Install build essentials:"
            echo "      - Ubuntu/Debian: sudo apt-get install build-essential"
            echo "      - Fedora: sudo dnf install gcc gcc-c++"
            echo ""
            echo "   2. Try installing numba separately first:"
            echo "      pip install numba"
            echo "      pip install -r requirements.txt"
        fi
        exit 1
    }
}

echo ""
echo "✅ Setup complete!"
echo ""
echo "You can now run the app with:"
echo "  ./run.sh"
echo ""
echo "Or directly:"
echo "  source venv/bin/activate"
echo "  python run_app.py"

