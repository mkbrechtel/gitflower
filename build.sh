#!/bin/bash

set -e

# Add ./bin to PATH for this script
export PATH="./bin:$PATH"

# Check for --install-tailwind flag
if [[ "$1" == "--install-tailwind" ]]; then
    echo "Installing Tailwind CSS to bin/tailwindcss..."
    
    # Detect OS and architecture
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    ARCH=$(uname -m)
    
    # Map architecture names
    if [[ "$ARCH" == "x86_64" ]]; then
        ARCH="x64"
    elif [[ "$ARCH" == "aarch64" ]] || [[ "$ARCH" == "arm64" ]]; then
        ARCH="arm64"
    fi
    
    # Download directly to bin/
    mkdir -p bin
    curl -sLo bin/tailwindcss "https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-${OS}-${ARCH}"
    chmod +x bin/tailwindcss
    
    echo "✓ Installed to bin/tailwindcss"
    exit 0
fi

echo "Building GitFlower..."

# Track build errors
BUILD_ERROR=0

# Build Tailwind CSS
echo "→ Building Tailwind CSS..."
if command -v tailwindcss &> /dev/null; then
    tailwindcss -i ./web/static/css/input.css -o ./web/static/css/output.css --minify
else
    echo "  ⚠ Warning: tailwindcss not found, skipping CSS build"
    echo "  To install: ./build.sh --install-tailwind"
    BUILD_ERROR=1
fi

# Build Go binary
echo "→ Building Go binary..."
go build -o bin/gitflower main.go

if [[ $BUILD_ERROR -eq 0 ]]; then
    echo "✓ Build complete: bin/gitflower"
else
    echo "⚠ Build completed with warnings: bin/gitflower"
    echo "  CSS was not built. Run ./build.sh --install-tailwind to fix this."
fi

exit $BUILD_ERROR
