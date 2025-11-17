#!/usr/bin/env bash
set -euo pipefail

# prepare.sh — Prepare environment for PPGDataReceiverAPI
#
# This script performs the minimal, idempotent setup required before running
# `./start.sh`. It is written to be safe to re-run.
#
# What it does:
# - Verifies a usable Python interpreter (>= 3.8) is available
# - Creates a virtual environment (default: `.venv`) if missing
# - Installs packages from `requirements.txt` into the venv
# - Creates `logs/` and `data/` directories expected by `start.sh`
# - Copies `.env.example` to `.env` if present and `.env` is missing
# - Prints next steps to activate the venv and start the app
#
# Usage:
#   ./prepare.sh               # use default .venv in repository root
#   VENV_DIR=/path/to/venv ./prepare.sh
#   bash ./prepare.sh          # run from PowerShell using Bash


SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Preparing environment in $SCRIPT_DIR"

# Find a Python executable (prefer python3)
if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD=python
else
  echo "Error: Python is not installed or not in PATH. Install Python 3.8+." >&2
  exit 1
fi

# Check Python version >= 3.8
PY_MAJOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info[0])')
PY_MINOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info[1])')
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 8 ]; }; then
  echo "Error: Python 3.8+ is required. Found $PY_MAJOR.$PY_MINOR" >&2
  exit 1
fi

# Allow overriding venv location via env var or first argument
if [ -n "${1-}" ] && [ -z "${VENV_DIR-}" ]; then
  VENV_DIR="$1"
fi
VENV_DIR="${VENV_DIR:-$SCRIPT_DIR/.venv}"

echo "Using Python: $(command -v $PYTHON_CMD) ($( $PYTHON_CMD -V 2>&1))"
echo "Virtualenv path: $VENV_DIR"

# Create the virtual environment if it does not exist
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment at $VENV_DIR"
  "$PYTHON_CMD" -m venv "$VENV_DIR"
else
  echo "Virtual environment already exists. Skipping creation."
fi

# Resolve venv's python interpreter (posix and Windows paths)
if [ -x "$VENV_DIR/bin/python" ]; then
  VENV_PY="$VENV_DIR/bin/python"
elif [ -x "$VENV_DIR/Scripts/python.exe" ]; then
  VENV_PY="$VENV_DIR/Scripts/python.exe"
else
  # Fallback to system python (should not be ideal, but allow it)
  VENV_PY="$PYTHON_CMD"
fi

echo "Using venv python: $VENV_PY"

# Install/upgrade pip and install requirements if file exists
REQ_FILE="$SCRIPT_DIR/requirements.txt"
if [ -f "$REQ_FILE" ]; then
  echo "Installing dependencies from $REQ_FILE into venv (this may take a moment)"
  "$VENV_PY" -m pip install --upgrade pip setuptools wheel >/dev/null || true
  "$VENV_PY" -m pip install -r "$REQ_FILE"
else
  echo "No requirements.txt found at $REQ_FILE — skipping package installation."
fi

# Ensure directories expected by start.sh exist
mkdir -p "$SCRIPT_DIR/logs" "$SCRIPT_DIR/data"
echo "Ensured directories: $SCRIPT_DIR/logs  $SCRIPT_DIR/data"

# Copy .env.example to .env if present and .env missing
if [ -f "$SCRIPT_DIR/.env.example" ] && [ ! -f "$SCRIPT_DIR/.env" ]; then
  echo "Copying .env.example -> .env"
  cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
fi

echo
echo "Preparation complete. Next steps:"
echo
echo "- To activate the virtual environment (bash / Git Bash / WSL):"
echo "    source $VENV_DIR/bin/activate"
echo
echo "- To activate the virtual environment (PowerShell):"
echo "    .\\.venv\\Scripts\\Activate.ps1"
echo
echo "- Then start the app using:"
echo "    ./start.sh"

exit 0
