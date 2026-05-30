#!/usr/bin/env bash
# run - Activate venv and run the embedded-serial-bridge CLI
#
# Wraps the CLI so you don't need to manually activate the virtual
# environment. All arguments are forwarded directly to the CLI.
#
# Usage:
#   ./run --help
#   ./run ping
#   ./run version -p /dev/ttyUSB0
#   ./run raw -x "01 02 03" -p /dev/ttyUSB0
#
# Run ./setup first if the virtual environment does not exist yet.
set -euo pipefail

VENV_DIR=".venv"

# Ensure the venv exists before trying to activate it
if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment not found. Run ./setup first."
    exit 1
fi

# Activate the venv for this shell session
source "$VENV_DIR/bin/activate"

# Replace this process with the CLI, forwarding all arguments.
# Using exec means the CLI process inherits the same PID and signals
# are handled correctly (e.g. Ctrl-C goes straight to the CLI).
exec embedded-serial-bridge "$@"
