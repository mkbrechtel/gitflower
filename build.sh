#!/bin/bash

set -e

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

# Build Tailwind CSS - check PATH first, then bin/
echo "→ Building Tailwind CSS..."
if command -v tailwindcss &> /dev/null; then
    tailwindcss -i ./iface/web/static/css/input.css -o ./iface/web/static/css/output.css --minify
elif [[ -x "bin/tailwindcss" ]]; then
    bin/tailwindcss -i ./iface/web/static/css/input.css -o ./iface/web/static/css/output.css --minify
else
    echo "  ⚠ Warning: tailwindcss not found, skipping CSS build"
    echo "  To install: ./build.sh --install-tailwind"
fi

# Build Go binary
echo "→ Building Go binary..."
go build -o bin/gitflower main.go

echo "✓ Build complete: bin/gitflower"