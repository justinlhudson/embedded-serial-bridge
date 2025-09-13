from __future__ import annotations
import sys
import os
from typing import Optional
import click

# Handle relative imports when run as script vs module
try:
    from .comm import Comm, Command, Message
    from .discovery import discover_serial_port, get_available_ports
except ImportError:
    # Add parent directory to path for standalone execution
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    from embedded_serial_bridge.comm import Comm, Command, Message
    from embedded_serial_bridge.discovery import discover_serial_port, get_available_ports

try:  # Python 3.11+
    import tomllib as _toml
except Exception:  # pragma: no cover - fallback for <3.11
    try:
        import tomli as _toml  # type: ignore
    except Exception as e:  # pragma: no cover
        _toml = None  # will error when used


DEFAULT_CONFIG_PATH = "config.toml"


def _get_default_config_path() -> str:
    """Get the default config path relative to the script location."""
    # Get the directory containing this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Go up one level to the project root where config.toml is located
    project_root = os.path.dirname(script_dir)
    return os.path.join(project_root, "config.toml")


def _load_config(path: str) -> dict:
    if _toml is None:
        raise click.ClickException("TOML parser not available. Install 'tomli' for Python <3.11.")

    # If using default path, make it absolute from script location
    if path == DEFAULT_CONFIG_PATH:
        path = _get_default_config_path()

    try:
        with open(path, "rb") as f:
            return _toml.load(f)
    except FileNotFoundError:
        raise click.ClickException(f"Config file not found: {path}")
    except Exception as e:
        raise click.ClickException(f"Failed to parse config: {e}")


def _resolve_serial(cfg: dict, allow_missing_port: bool = False) -> tuple[str, int, float, bool, int, str]:
    serial_cfg = cfg.get("serial", {}) if isinstance(cfg, dict) else {}
    hdlc_cfg = cfg.get("hdlc", {}) if isinstance(cfg, dict) else {}
    fmt_cfg = cfg.get("format", {}) if isinstance(cfg, dict) else {}
    port = serial_cfg.get("port")
    if not port and not allow_missing_port:
        raise click.ClickException("Missing 'serial.port' in config")
    baudrate = int(serial_cfg.get("baudrate", 115200))
    timeout = float(serial_cfg.get("timeout", 0.2))
    # Always escape control; only read CRC and max payload from config
    crc_enabled = bool(hdlc_cfg.get("crc_enabled", False))
    max_payload = int(hdlc_cfg.get("max_payload", 128))
    if not (0 < max_payload <= 65535):
        raise click.ClickException("hdlc.max_payload must be in 1..65535 (fits u16 length)")
    encoding = str(fmt_cfg.get("encoding", "utf-8"))
    return port or "", baudrate, timeout, crc_enabled, max_payload, encoding


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
@click.option("--config", "config_path", type=click.Path(dir_okay=False), default=DEFAULT_CONFIG_PATH, show_default=True, help="Path to config.toml")
@click.option("-s", "string", help="String payload (mutually exclusive with --hex)")
@click.option("-x", "hexstr", help="Hex payload, e.g. '01 02 0a' or '01020a'")
@click.option("--discover", is_flag=True, help="Auto-discover serial port using ping before sending command")
def main(command: str, config_path: str, string: Optional[str], hexstr: Optional[str],
         discover: bool) -> None:
    """Send a command and payload using config.toml for serial settings.

    COMMAND can be symbolic (ping, ack, nak, raw) or numeric (0x03, 3).

    Examples:

      # Send ping command with empty payload
      embedded-serial-bridge ping

      # Send ping with text payload
      embedded-serial-bridge ping -s "hello world"

      # Send raw command with hex payload
      embedded-serial-bridge raw -x "01 02 03 04"

      # Auto-discover serial port and send ping
      embedded-serial-bridge ping --discover

      # Send command using custom config file
      embedded-serial-bridge ping --config my-config.toml -s "test"
    """

    cfg = _load_config(config_path)
    port, baudrate, timeout, crc_enabled, max_payload, encoding = _resolve_serial(cfg, allow_missing_port=discover)

    # Handle --discover
    if discover:
        click.echo("Auto-discovering serial port...")
        # Use absolute config path for discovery if using default
        discovery_config_path = config_path
        if config_path == DEFAULT_CONFIG_PATH:
            discovery_config_path = _get_default_config_path()

        discovered_port = discover_serial_port(config_path=discovery_config_path)
        if discovered_port:
            click.echo(f"Using discovered port: {discovered_port}")
            port = discovered_port
        else:
            raise click.ClickException("No responding serial port found. Check connections or try running discovery.py directly.")

    # Ensure we have a port at this point
    if not port:
        raise click.ClickException("No serial port specified. Use --discover or set serial.port in config.toml")

    cmd_val = _parse_command(command)
    payload = _build_payload(string, hexstr, encoding)

    # Defaults when options removed
    msg_id = 0
    fragments = 1
    fragment = 0

    with Comm(port, baudrate=baudrate, timeout=timeout, crc_enabled=crc_enabled, max_payload=max_payload) as c:
        try:
            # Use high-level Message API
            msg = Message(command=cmd_val, id=msg_id, fragments=fragments, fragment=fragment, length=len(payload), payload=payload)
            written = c.write_msg(msg)
            click.echo(f"Sent {written} bytes to {port}")

            # Try to read response/echo back
            click.echo("Waiting for response...")
            response = c.read_msg(timeout=3.0)  # Wait up to 3 seconds for response

            if response is not None:
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
