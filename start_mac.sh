#!/usr/bin/env bash
# macOS & Linux Universal Launcher for Yards & Parts Platform
cd "$(dirname "$0")"

echo "==================================================="
echo "Starting Yards & Parts Platform (macOS / Linux)"
echo "==================================================="

# Check for Python 3
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "Error: Python 3 is not installed or not in PATH."
    exit 1
fi

$PYTHON_CMD run.py
