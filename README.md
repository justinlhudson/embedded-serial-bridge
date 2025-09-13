# embedded-serial-bridge

Embedded serial bridge with HDLC framing (CRC‑16/X25) and a minimal CLI.

- Package: `embedded_serial_bridge`
- CLI: `embedded-serial-bridge`
- Config file: `config.toml` (looked up at the project root by default)

## Install

Editable install from this repo:

```bash
python3 -m pip install -e .
```

Requirements are installed automatically: pyserial, click, and tomli for Python < 3.11.

## Config (config.toml)

Place `config.toml` in the project root (same folder as this README):

```toml
[serial]
# Optional if you use --discover on the CLI
port = "/dev/ttyUSB0"   # or "/dev/tty.usbserial-XXXX", "COM3"
baudrate = 115200
timeout = 0.2             # seconds

[hdlc]
# TX always appends CRC. This flag controls RX validation only.
crc_enabled = false       # validate CRC on receive
max_payload = 65535       # u16 payload length limit (1..65535)

[format]
encoding = "utf-8"        # used for CLI --string payloads
```

Notes
- Control characters (< 0x20) are always escaped (plus FLAG 0x7E and ESC 0x7D).
- CRC‑16 is always added on transmit. Receive validation is off by default (enable via `hdlc.crc_enabled`).
- Message length is u16, so `max_payload` can be up to 65535.

## Public API

from embedded_serial_bridge import Comm, Command, Message, discover

- Comm
  - Comm(port: str, baudrate: int = 115200, timeout: float = 0.1, *, crc_enabled: bool = False, max_payload: int = 4096, **serial_kwargs)
  - write(data: bytes | Message) -> int
    - Frames the payload using HDLC and writes to the serial port.
    - Enforces `max_payload`.
  - read(timeout: float | None = None, *, message: bool = True) -> Message | bytes | None
    - When `message=True` (default), parses and returns a Message; returns None on timeout or parse failure.
    - When `message=False`, returns raw payload bytes.

- Command (enum.IntEnum)

| Command | Value (hex) |
|---------|-------------|
| Ack     | 0x01        |
| Nak     | 0x02        |
| Ping    | 0x03        |
| Raw     | 0x04        |

- Message

| Field     | Type | Notes                   |
|-----------|------|-------------------------|
| command   | u16  |                         |
| id        | u8   | Not used (TBD for user) |
| fragments | u16  | Not used (TBD for user) |
| fragment  | u16  | Not used (TBD for user) |
| length    | u16  |                         |
| payload   | bytes|                         |

- discover(config_path: str = "config.toml") -> str | None

> **IMPORTANT:** **Probes likely ports on the host using a Ping and returns the first responding port**.

  - Uses serial/HDLC settings from the given config.

## CLI usage

```bash
# Send Ping (symbolic) with empty payload using config.toml
embedded-serial-bridge ping

# Send Ping with a UTF‑8 string payload
embedded-serial-bridge ping -s "hello world"

# Send Raw command with a hex payload (spaces optional)
embedded-serial-bridge raw -x "01 02 0A 0B"

# Use numeric command (hex or decimal)
embedded-serial-bridge 0x03 -x "DE AD BE EF"

# Auto‑discover the serial port using Ping, then send a command
embedded-serial-bridge ping --discover

# Use a custom config file (absolute or relative path)
embedded-serial-bridge ping --config ./my-config.toml
```

Arguments and options
- command: one of `ack`, `nak`, `ping`, `raw`, or a u16 number (e.g., `3`, `0x03`).
- --config PATH: path to a TOML config. If omitted, the tool looks for `config.toml` at the project root.
- -s/--string TEXT: payload as a string (encoded using `[format].encoding`).
- -x/--hex HEX: payload as hexadecimal bytes, e.g., `"01 02 0a"` or `"01020a"`.
- --discover: probe ports to find a responding device; uses the config for baudrate/timeout.

Behavior
- If both `--string` and `--hex` are omitted, an empty payload is sent.
- The CLI prints a summary of any response if one is received within the timeout.

## License

This project is licensed under the MIT License. See the LICENSE file for details.
