"""Embedded Serial Bridge package.

Utilities and CLI to talk to USB-UART MCUs using pyserial with HDLC framing.
"""

__all__ = [
    "Comm",
    "Command",
    "Message",
    "discover_serial_port",
    "get_available_ports",
]

from .comm import Comm, Command, Message
from .discovery import discover_serial_port, get_available_ports

__version__ = "0.1.0"
