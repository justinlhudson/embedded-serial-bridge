# embedded-serial-bridge

Serial bridge with HDLC framing (CRC‑16/X25) and a minimal CLI.

- Package: `embedded_serial_bridge`
- CLI: `embedded-serial-bridge`
- Config: `config.toml` (project root by default)

## Install

```bash
python3 -m pip install -e .
```

Requires: pyserial, click, tomli (for Python < 3.11).

## Config

Example `config.toml`:

```toml
[serial]
port = "/dev/ttyUSB0"
baudrate = 115200
timeout = 0.2

[hdlc]
crc_enabled = false
max_payload = 65535

[format]
encoding = "utf-8"
```

## Usage

- **Auto-detects serial port** with `--discover` (sends Ping to likely ports).
- CLI examples:

```bash
embedded-serial-bridge ping
embedded-serial-bridge ping -s "hello"
embedded-serial-bridge raw -x "01 02 0A"
embedded-serial-bridge ping --discover
```

See [embassy-stm32-starter](https://github.com/justinlhudson/embassy-stm32-starter) for a compatible embedded implementation.

## API

```python
from embedded_serial_bridge import Comm, Command, Message, discover
```

## License

MIT
