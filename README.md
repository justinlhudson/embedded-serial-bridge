# embedded-serial-bridge

Serial bridge with HDLC framing (CRC‑16/X25) and a minimal CLI.

- Package: `embedded_serial_bridge`
- CLI: `embedded-serial-bridge`

## Install

```bash
python3 -m pip install -e .
```

Requires: pyserial, click.

## Usage

The CLI auto-discovers serial ports by default. You can also specify options:

```bash
# Auto-discover and send ping
embedded-serial-bridge ping

# Specify port and send ping with text payload
embedded-serial-bridge ping -p /dev/ttyUSB0 -s "hello world"

# Send raw command with hex payload
embedded-serial-bridge raw -x "01 02 0A" -p COM3

# Custom settings
embedded-serial-bridge ping -p /dev/ttyUSB0 -b 9600 --fcs --payload-limit 128
```

**Options:**
- `-p, --port`: Serial port (auto-discovers if not specified)
- `-b, --baudrate`: Baud rate (default: 115200)
- `-t, --timeout`: Read timeout in seconds (default: 1.0)
- `--fcs/--no-fcs`: Enable FCS (CRC) validation (default: no-fcs)
- `--payload-limit`: Maximum payload size (default: 4096)
- `-s`: String payload
- `-x`: Hex payload
- `--encoding`: Text encoding (default: utf-8)

See [embassy-stm32-starter](https://github.com/justinlhudson/embassy-stm32-starter) for a compatible embedded implementation.

## API

```python
from embedded_serial_bridge import Comm, Command, Message
from embedded_serial_bridge.discovery import AutoDiscovery

# Auto-discover serial port
discovery = AutoDiscovery(baudrate=115200, timeout=1.0, fcs=False, payload_limit=4096)
port = discovery.discover()

# Use the communication interface
with Comm(port, baudrate=115200, timeout=1.0, fcs=False, payload_limit=4096) as comm:
    msg = Message(command=int(Command.Ping), id=0, fragments=1, fragment=0, length=0, payload=b"")
    comm.write(msg)
    response = comm.read(timeout=1.0, message=True)
```

## Examples

### Weather-Based Relay Control

The `apps/weather_relay.py` application demonstrates a practical use case: controlling a hardware relay based on weather conditions and sun position. It automatically turns on a relay when it's light outside and the sky is clear, and turns it off when it's dark or cloudy.

**Features:**
- Calculates sun position using astronomical data (latitude, longitude, elevation)
- Fetches real-time cloud cover from METAR weather stations
- Auto-discovers serial ports to communicate with embedded hardware
- Configurable via `weather_relay.toml` with sensible defaults

## License

MIT
