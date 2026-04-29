# embedded-serial-bridge

Serial bridge with HDLC framing (CRC‑16/X25) and a minimal CLI.

- Package: `embedded_serial_bridge`
- CLI: `embedded-serial-bridge`

## Setup

Run the setup script to create a virtual environment, install dependencies, and configure serial port permissions:

```bash
./setup
```

This will:
- Create a `.venv` virtual environment
- Install all dependencies
- Add your user to the `dialout` group
- Install a udev rule so STLink devices are always accessible without `sudo`

## Running

```bash
./run --help
```

The `run` script activates the venv and proxies all arguments to the CLI.

## Manual Install

```bash
python3 -m pip install -e .
```

Requires: pyserial, click.

## Usage

The CLI auto-discovers serial ports by default. You can also specify options:

```bash
# Auto-discover and send ping
embedded-serial-bridge ping

# Request firmware version from MCU
embedded-serial-bridge version

# Specify port and send ping with text payload
embedded-serial-bridge ping -p /dev/ttyUSB0 -s "hello world"

# Send raw command with hex payload
embedded-serial-bridge raw -x "01 02 0A" -p COM3

# Custom settings
embedded-serial-bridge ping -p /dev/ttyUSB0 -b 9600 --fcs --payload-limit 128
```

**Commands:**
- `ping` — send ping (0x03), expects echo
- `version` — request firmware version (0x05)
- `ack` — send acknowledge (0x01)
- `nak` — send negative acknowledge (0x02)
- `raw` — send raw data (0x04)
- Numeric commands also accepted: `0x03`, `3`, etc.

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
from embedded_serial_bridge.auto_discovery import AutoDiscovery

# Auto-discover serial port
discovery = AutoDiscovery(baudrate=115200, timeout=1.0)
port = discovery.run()

# Use the communication interface
with Comm(port, baudrate=115200, timeout=1.0, fcs=True, payload_limit=128) as comm:
    # Simple way: use Message.make() with command and payload
    msg = Message.make(command=Command.Ping, payload=b"hello")
    comm.write(msg)
    response = comm.read(timeout=1.0, message=True)
    
    # Advanced: full control over all message fields
    msg = Message(command=int(Command.Raw), id=0, fragments=1, fragment=0, length=5, payload=b"hello")
    comm.write(msg)
```

## Examples

### Version Check

The `apps/version_check.py` application pings the board until it responds, then requests the firmware version string. Use it as a quick liveness check to confirm the board is connected and running compatible firmware.

```bash
# Auto-discover port
python apps/version_check.py

# Explicit port
python apps/version_check.py --port /dev/ttyUSB0

# More retries and longer timeout
python apps/version_check.py --retries 10 --timeout 3.0
```

### Weather-Based Relay Control

The `apps/weather_relay.py` application demonstrates a practical use case: controlling a hardware relay based on weather conditions and sun position. It automatically turns on a relay when it's light outside and the sky is clear, and turns it off when it's dark or cloudy.

**Features:**
- Calculates sun position using astronomical data (latitude, longitude, elevation)
- Fetches real-time cloud cover from METAR weather stations
- Auto-discovers serial ports to communicate with embedded hardware
- Configurable via `weather_relay.toml` with sensible defaults

## License

MIT
