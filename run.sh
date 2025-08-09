#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Set the config path relative to script directory
export GITFLOWER_CONFIG="${SCRIPT_DIR}/test/config.yaml"

# Run the application with go run
go run main.go "$@"