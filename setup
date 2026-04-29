#!/usr/bin/env bash
# setup - One-time environment setup for embedded-serial-bridge
#
# Creates a Python virtual environment, installs all dependencies,
# and configures serial port permissions so the STLink board is
# accessible without sudo on every plug-in.
#
# Usage:
#   ./setup
#
# Environment variables:
#   PYTHON  - Python interpreter to use (default: python3)
set -euo pipefail

VENV_DIR=".venv"
PYTHON="${PYTHON:-python3}"

echo "Using Python: $($PYTHON --version)"

# --- Virtual environment ---

# Create venv if it doesn't already exist; reuse if it does
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR..."
    "$PYTHON" -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists at $VENV_DIR, skipping creation."
fi

# Activate so pip installs go into the venv
source "$VENV_DIR/bin/activate"

echo "Upgrading pip..."
pip install --upgrade pip

# Install package in editable mode with dev extras (pytest etc.)
echo "Installing embedded-serial-bridge with dev dependencies..."
pip install -e ".[dev]"


# --- Serial port permissions ---

# Add current user to the dialout group so /dev/tty* devices are accessible
# without sudo. Takes effect after next login.
if ! groups "$USER" | grep -qw dialout; then
    echo "Adding $USER to dialout group..."
    sudo usermod -aG dialout "$USER"
    echo "  NOTE: Log out and back in for group change to take effect."
else
    echo "User $USER already in dialout group."
fi

# Install a udev rule that sets MODE=0666 on the STLink VCP whenever it is
# plugged in (VID 0483 / PID 374B = STM32 STLink). This prevents the port
# reverting to root-only permissions on reconnect.
UDEV_RULE='SUBSYSTEM=="tty", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="374b", MODE="0666"'
UDEV_FILE="/etc/udev/rules.d/99-stlink.rules"

if [ ! -f "$UDEV_FILE" ] || ! grep -qF "$UDEV_RULE" "$UDEV_FILE"; then
    echo "Installing udev rule for STLink at $UDEV_FILE..."
    echo "$UDEV_RULE" | sudo tee "$UDEV_FILE" > /dev/null
    sudo udevadm control --reload-rules   # reload rules without reboot
    sudo udevadm trigger                  # apply to already-connected devices
    echo "  udev rule installed."
else
    echo "udev rule already present at $UDEV_FILE."
fi

echo ""
echo "Setup complete. Activate the environment with:"
echo "  source $VENV_DIR/bin/activate"
echo ""
echo "Then run the application with:"
echo "  embedded-serial-bridge --help"
