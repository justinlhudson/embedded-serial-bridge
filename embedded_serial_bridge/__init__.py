"""Embedded Serial Bridge package.

Utilities and CLI to talk to USB-UART MCUs using pyserial with HDLC framing.
"""

__all__ = [
    "Comm",
    "Command",
    "Message",
]

from .comm import Comm, Command, Message

__version__ = "0.1.0"

