"""
weather_relay.py - Weather-Based Relay Control Application

This module provides the WeatherChecker and BoardController classes for controlling hardware
via a serial bridge based on weather and time conditions. The main loop periodically checks
weather conditions and controls a board relay accordingly.

Classes:
    WeatherChecker: Computes sun position and fetches cloud state.
    BoardController: Sends raw pin commands to a board using the serial bridge protocol.

Example:
    Run this script directly to start the main control loop.
"""

#!/usr/bin/env python3
import datetime
from pathlib import Path
from suntime import Sun  # type: ignore
import ephem  # type: ignore
from metar import Metar

from embedded_serial_bridge import Comm
from embedded_serial_bridge.auto_discovery import AutoDiscovery


def _load_module_toml_config(module_file: str) -> dict:
    """Load TOML file with the same base name as `module_file` (e.g., `weather_relay.toml`)."""
    toml_path = Path(module_file).with_suffix(".toml")
    if not toml_path.exists():
        return {}
    try:
        import tomllib  # Python 3.11+
        with toml_path.open("rb") as f:
            return tomllib.load(f)
    except (ImportError, ModuleNotFoundError):
        try:
            import toml  # fallback to third-party package
            return toml.load(toml_path)
        except Exception:
            return {}
    except Exception:
        return {}


class WeatherChecker:
    """
    Weather and sun position checker.

    Args:
        latitude: Location latitude in degrees
        longitude: Location longitude in degrees
        elevation: Location elevation in meters
        station: METAR station code for cloud data (e.g., 'KJFK')
    """

    def __init__(
        self,
        latitude: float,
        longitude: float,
        elevation: float = 0.0,
        station: str = "KJFK"
    ):
        self.latitude = latitude
        self.longitude = longitude
        self.elevation = elevation
        self.station = station.strip("'")

        self.process()

    @property
    def is_light(self):
        """Return True if sun is above the calculated angle threshold."""
        self.sun_ephem.compute(self.observer)
        sun_angle = self.sun_ephem.alt / ephem.degree
        return sun_angle >= self.sun_angle_offset

    @property
    def is_dark(self):
        """Return True if sun is below the calculated angle threshold."""
        return not self.is_light

    @property
    def is_cloudy(self):
        """Return the last fetched cloud state (True/False). Call process() to refresh."""
        return self._cloudy

    def _sun_out(self):
        """Calculate sun angle offset based on current month."""
        # Use the observer's longitude to estimate the local timezone offset from UTC
        # This is a rough estimate: 15 degrees longitude per hour offset
        utc_offset_hours = int(round(self.longitude / 15.0))

        # Get the current UTC time and apply the offset to get local month
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        local_time = now_utc + datetime.timedelta(hours=utc_offset_hours)
        month = local_time.month

        peak = 2.5
        if month in range(6, 13):
            result = month
        elif month in range(1, 6):
            result = (12 - month)
        else:
            result = month
        result = result ** (1 + (peak / 10))
        return result

    def _fetch_cloudy(self):
        """Fetch and return True if current METAR report indicates cloudy (BKN or OVC), else False."""
        try:
            import urllib.request
            import ssl
            import certifi

            url = f'https://tgftp.nws.noaa.gov/data/observations/metar/stations/{self.station}.TXT'
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            with urllib.request.urlopen(url, context=ssl_context) as response:
                metar_text = response.read().decode('utf-8').split('\n')[1]
            obs = Metar.Metar(metar_text)

            # Check for broken (BKN) or overcast (OVC) clouds
            for sky in obs.sky:
                if sky[0] in ['BKN', 'OVC']:
                    return True
            return False
        except Exception:
            return False

    def process(self):
        """
        This is called to refresh state.
        """
        self.utc = datetime.datetime.now(datetime.timezone.utc)
        self.sun = Sun(self.latitude, self.longitude)

        self.observer = ephem.Observer()
        self.observer.lat = str(self.latitude)
        self.observer.lon = str(self.longitude)
        self.observer.elevation = self.elevation
        self.observer.compute_pressure()

        # Initialize sun_ephem and compute sun angle at current UTC time
        self.sun_ephem = ephem.Sun()
        self.observer.date = self.utc  # Set observer date to current UTC
        self.sun_ephem.compute(self.observer)
        self.sun_angle = self.sun_ephem.alt / ephem.degree
        self.sun_angle_offset = self._sun_out()

        # Fetch and set cloud state
        self._cloudy = self._fetch_cloudy()


class BoardController:
    """
    Controls board pins via the serial bridge using the raw protocol.
    Sends two bytes: first is the pin number, second is 0x01 (on) or 0x00 (off).
    Automatically discovers the serial port if not specified.

    Args:
        port: Serial port path (default: None, auto-discover)
        baudrate: Baud rate for communication (default: 115200)
        timeout: Communication timeout in seconds (default: 0.1)
    """

    def __init__(self, port=None, baudrate=115200, timeout=0.1):
        if port is None:
            discovery = AutoDiscovery(baudrate=baudrate, timeout=timeout)
            port = discovery.run()
            if port is None:
                raise RuntimeError("No serial port found by discovery.")

        self.comm = Comm(port=port, baudrate=baudrate, timeout=timeout)

    def send_raw(self, data: bytes) -> None:
        """
        Send a raw command to the board with the given data bytes.

        Args:
            data (bytes): Raw data to send (user is responsible for format)
        """
        from embedded_serial_bridge.comm import Message, Command

        if not isinstance(data, bytes):
            raise ValueError("data must be of type bytes")

        # Use the Raw command type for raw data
        msg = Message.make(command=Command.Raw, payload=data)
        self.comm.write(msg)

    def close(self):
        """Close the serial connection."""
        self.comm.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def main():
    """
    Main function demonstrating weather-based relay control.
    """
    # Load configuration from TOML file if available
    config = _load_module_toml_config(__file__)
    weather_config = config.get("weather", {})  # subset

    # Fallback to example default values (New York City) if not provided in config
    latitude = weather_config.get("latitude", 40.7128)
    longitude = weather_config.get("longitude", -74.0060)
    elevation = weather_config.get("elevation", 10.0)
    station = weather_config.get("station", "KJFK")

    weather = WeatherChecker(
        latitude=latitude,
        longitude=longitude,
        elevation=elevation,
        station=station
    )

    print(f"Is it light? {weather.is_light}")
    print(f"Is it dark? {weather.is_dark}")
    print(f"Is it cloudy? {weather.is_cloudy}")

    with BoardController() as board:
        if weather.is_light and not weather.is_cloudy:
            print("Turning on (light and clear)...")
            board.send_raw(data=bytes([0xD8, 0x01]))  # on
        else:
            print("Turning off (dark or cloudy)...")
            board.send_raw(data=bytes([0xD8, 0x00]))  # off


if __name__ == "__main__":
    main()
