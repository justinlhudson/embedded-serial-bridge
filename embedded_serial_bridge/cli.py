from __future__ import annotations

import sys
from typing import Optional

import click

from .comm import Comm, Command, Message

try:  # Python 3.11+
    import tomllib as _toml
except Exception:  # pragma: no cover - fallback for <3.11
    try:
        import tomli as _toml  # type: ignore
    except Exception as e:  # pragma: no cover
        _toml = None  # will error when used


DEFAULT_CONFIG_PATH = "config.toml"


def _load_config(path: str) -> dict:
    if _toml is None:
        raise click.ClickException("TOML parser not available. Install 'tomli' for Python <3.11.")
    try:
        with open(path, "rb") as f:
            return _toml.load(f)
    except FileNotFoundError:
        raise click.ClickException(f"Config file not found: {path}")
    except Exception as e:
        raise click.ClickException(f"Failed to parse config: {e}")


def _resolve_serial(cfg: dict) -> tuple[str, int, float, bool, int, str]:
    serial_cfg = cfg.get("serial", {}) if isinstance(cfg, dict) else {}
    hdlc_cfg = cfg.get("hdlc", {}) if isinstance(cfg, dict) else {}
    fmt_cfg = cfg.get("format", {}) if isinstance(cfg, dict) else {}
    port = serial_cfg.get("port")
    if not port:
        raise click.ClickException("Missing 'serial.port' in config")
    baudrate = int(serial_cfg.get("baudrate", 115200))
    timeout = float(serial_cfg.get("timeout", 0.2))
    # Always escape control; only read CRC and max payload from config
    crc_enabled = bool(hdlc_cfg.get("crc_enabled", False))
    max_payload = int(hdlc_cfg.get("max_payload", 128))
    if not (0 < max_payload <= 65535):
        raise click.ClickException("hdlc.max_payload must be in 1..65535 (fits u16 length)")
    encoding = str(fmt_cfg.get("encoding", "utf-8"))
    return port, baudrate, timeout, crc_enabled, max_payload, encoding


def _parse_command(value: str) -> int:
    # Accept symbolic (ack/nak/ping), hex (0x..), or decimal
    name = value.strip().lower()
    alias = {"ack": Command.Ack, "nak": Command.Nak, "ping": Command.Ping}
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
    # Fallback to stdin
    return sys.stdin.buffer.read()


@click.command()
@click.argument("command")
@click.option("--config", "config_path", type=click.Path(dir_okay=False), default=DEFAULT_CONFIG_PATH, show_default=True, help="Path to config.toml")
@click.option("-s", "string", help="String payload (mutually exclusive with --hex)")
@click.option("-x", "hexstr", help="Hex payload, e.g. '01 02 0a' or '01020a'")
def main(command: str, config_path: str, string: Optional[str], hexstr: Optional[str]) -> None:
    """Send a command and payload using config.toml for serial settings."""
    cfg = _load_config(config_path)
    port, baudrate, timeout, crc_enabled, max_payload, encoding = _resolve_serial(cfg)

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
            c.write_msg(msg)
        except Exception as e:
            raise click.ClickException(str(e))

