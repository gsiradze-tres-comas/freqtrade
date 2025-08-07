#!/bin/bash

echo "Installing TA-Lib for macOS..."

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo "Homebrew is not installed. Please install Homebrew first."
    echo "Visit https://brew.sh for installation instructions."
    exit 1
fi

# Install TA-Lib using Homebrew
echo "Installing TA-Lib via Homebrew..."
brew install ta-lib

# For Intel Macs, also try to install using the pre-built wheel
echo "Installing Python TA-Lib package..."
arch=$(uname -m)
if [ "$arch" = "x86_64" ]; then
    # Try to use the pre-built wheel from the build_helpers directory
    if [ -f "build_helpers/ta_lib-0.5.5-cp311-cp311-macosx_10_9_x86_64.whl" ]; then
        echo "Found pre-built wheel, installing..."
        pip install build_helpers/ta_lib-0.5.5-cp311-cp311-macosx_10_9_x86_64.whl
    else
        # If homebrew installation succeeded, try pip install
        pip install ta-lib
    fi
else
    # For Apple Silicon
    pip install ta-lib
fi

echo "TA-Lib installation complete!"