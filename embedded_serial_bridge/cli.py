from __future__ import annotations
import sys
import os
from typing import Optional
import click

# Handle relative imports when run as script vs module
try:
    from .comm import Comm, Command, Message
    from .auto_discovery import AutoDiscovery
except ImportError:
    # Add parent directory to path for standalone execution
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    from embedded_serial_bridge.comm import Comm, Command, Message
    from embedded_serial_bridge.auto_discovery import AutoDiscovery


def _parse_command(value: str) -> int:
    # Accept symbolic (ack/nak/ping/raw), hex (0x..), or decimal
    name = value.strip().lower()
    alias = {"ack": Command.Ack, "nak": Command.Nak, "ping": Command.Ping, "raw": Command.Raw}
    if name in alias:
        return int(alias[name])
    try:
        # int(x, 0) accepts 0x.., 0o.., 0b.., or decimal
        v = int(value, 0)
    except ValueError:
        raise click.ClickException(f"Invalid command: {value}")
    if not (0 <= v <= 0xFFFF):
        raise click.ClickException("Command out of range (u16)")
    return v


def _build_payload(string: Optional[str], hexstr: Optional[str], encoding: str) -> bytes:
    sources = [s is not None for s in (string, hexstr)]
    if sum(sources) > 1:
        raise click.ClickException("Use only one of --string or --hex")
    if string is not None:
        try:
            return string.encode(encoding)
        except LookupError:
            return string.encode("utf-8")
    if hexstr is not None:
        try:
            return bytes.fromhex(hexstr)
        except ValueError as e:
            raise click.ClickException(f"Invalid hex string: {e}")
    # Default to empty payload instead of reading from stdin
    return b""


@click.command()
@click.argument("command")
@click.option("-p", "--port", help="Serial port (e.g., /dev/ttyUSB0, COM3). If not specified, will auto-discover.")
@click.option("-b", "--baudrate", type=int, default=115200, show_default=True, help="Baud rate")
@click.option("-t", "--timeout", type=float, default=1.0, show_default=True, help="Read timeout in seconds")
@click.option("--fcs/--no-fcs", default=False, show_default=True, help="Enable FCS (CRC) validation")
@click.option("--payload-limit", type=int, default=4096, show_default=True, help="Maximum payload size")
@click.option("-s", "string", help="String payload (mutually exclusive with --hex)")
@click.option("-x", "hex", help="Hex payload, e.g. '01 02 0a' or '01020a'")
@click.option("--encoding", default="utf-8", show_default=True, help="Text encoding for string payloads")
def main(command: str, port: Optional[str], baudrate: int, timeout: float,
         fcs: bool, payload_limit: int, string: Optional[str], hex: Optional[str],
         encoding: str) -> None:
    """Send a command and payload over serial.

    COMMAND can be symbolic (ping, ack, nak, raw) or numeric (0x03, 3).

    Examples:

      # Auto-discover port and send ping
      embedded-serial-bridge ping

      # Send ping with text payload to specific port
      embedded-serial-bridge ping -p /dev/ttyUSB0 -s "hello world"

      # Send raw command with hex payload
      embedded-serial-bridge raw -x "01 02 03 04" -p COM3

      # Use custom settings
      embedded-serial-bridge ping -p /dev/ttyUSB0 -b 9600 --fcs --payload-limit 128
    """

    # Auto-discover port if not specified
    if not port:
        click.echo("Auto-discovering serial port...")
        discovery = AutoDiscovery(baudrate=baudrate, timeout=timeout, fcs=fcs, payload_limit=payload_limit)
        discovered_port = discovery.discover()
        if discovered_port:
            click.echo(f"Using discovered port: {discovered_port}")
            port = discovered_port
        else:
            raise click.ClickException("No responding serial port found. Specify port with -p/--port option.")

    cmd_val = _parse_command(command)
    payload = _build_payload(string, hex, encoding)

    # Message defaults
    msg_id = 0
    fragments = 1
    fragment = 0

    with Comm(port, baudrate=baudrate, timeout=timeout, fcs=fcs, payload_limit=payload_limit) as c:
        try:
            # Use high-level Message API
            msg = Message(command=cmd_val, id=msg_id, fragments=fragments, fragment=fragment, length=len(payload), payload=payload)
            written = c.write(msg)
            click.echo(f"Sent {written} bytes to {port}")

            # Try to read response/echo back
            click.echo("Waiting for response...")
            response = c.read(timeout=3.0, message=True)  # Wait up to 3 seconds for response

            if response is not None and not isinstance(response, bytes):
                click.echo(f"Received response:")
                click.echo(f"  Command: 0x{response.command:04x} ({response.command})")
                click.echo(f"  ID: {response.id}")
                click.echo(f"  Fragments: {response.fragments}")
                click.echo(f"  Fragment: {response.fragment}")
                click.echo(f"  Length: {response.length}")

                if response.payload:
                    # Try to decode as string first, fall back to hex
                    try:
                        payload_str = response.payload.decode('utf-8')
                        click.echo(f"  Payload (string): '{payload_str}'")
                    except UnicodeDecodeError:
                        payload_hex = response.payload.hex()
                        click.echo(f"  Payload (hex): {payload_hex}")
                else:
                    click.echo(f"  Payload: (empty)")
            else:
                click.echo("No response received within timeout")

        except Exception as e:
            raise click.ClickException(str(e))


if __name__ == "__main__":
    main()
