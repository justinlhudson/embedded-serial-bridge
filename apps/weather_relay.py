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
import ephem  # type: ignore
from metar import Metar
from embedded_serial_bridge import Comm
from embedded_serial_bridge.auto_discovery import AutoDiscovery
import logging

_logger = logging.getLogger(__name__)
# Ensure module logger emits debug messages. If no logging configuration exists yet,
# configure the root logger to show DEBUG messages with a simple format so output
# is visible when running this script directly.
_logger.setLevel(logging.DEBUG)
if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

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
        try:  # type: ignore
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
        angle: Sun angle threshold in degrees (default: -6 for civil twilight)
        station: METAR station code for cloud data (e.g., 'KJFK')
        visibility: Minimum visibility in statute miles (default: 6.0)
    """

    def __init__(
        self,
        latitude: float,
        longitude: float,
        elevation: float = 0.0,
        angle: float = -6,  # civil twilight
        station: str = "KJFK",
        visibility: float = 6.0,  # statute miles
    ):
        self.sun_ephem = ephem.Sun()  # where is that silly sun
        self.observer = ephem.Observer()  # lat. long. fun
        self.sun_angle = 0 # horizon
        self._cloudy = True  # assume worst case
        self._visible = False  # assume worst case
        self.angle = angle
        self.latitude = latitude
        self.longitude = longitude
        self.elevation = elevation
        self.station = station.strip("'")
        self.visibility = visibility

        self.refresh()

    @property
    def is_light(self):
        """Return True if sun is above the calculated angle threshold."""
        self.sun_ephem.compute(self.observer)
        sun_angle = self.sun_ephem.alt / ephem.degree
        return sun_angle >= self.angle

    @property
    def is_dark(self):
        """Return True if sun is below the calculated angle threshold."""
        return not self.is_light

    @property
    def is_cloudy(self):
        """Return the last fetched cloud state (True/False). Call process() to refresh."""
        return self._cloudy

    @property
    def is_visible(self):
        """Return True if visibility is greater than threshold. Call refresh() to update."""
        return self._visible

    def _fetch_metar(self):
        """Fetch METAR report and update cloudy and visibility state."""
        try:
            import urllib.request
            import ssl
            import certifi

            url = f'https://tgftp.nws.noaa.gov/data/observations/metar/stations/{self.station}.TXT'
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            with urllib.request.urlopen(url, context=ssl_context) as response:
                metar_text = response.read().decode('utf-8').split('\n')[1]
            obs = Metar.Metar(metar_text)
            _logger.debug(obs)

            self._visible = False
            visibility_sm = 0
            for unit in hasattr(obs.vis, 'legal_units') and obs.vis.legal_units:
                try:
                    vis_value = obs.vis.value(unit)
                    if vis_value is not None:
                        # Convert to statute miles
                        unit_upper = unit.upper()
                        if unit_upper in ['SM', 'MI']:
                            visibility_sm = vis_value
                        elif unit_upper == 'M':
                            visibility_sm = vis_value / 1609.344  # meters to miles
                        elif unit_upper == 'KM':
                            visibility_sm = vis_value * 0.621371  # km to miles
                        elif unit_upper == 'FT':
                            visibility_sm = vis_value / 5280.0  # feet to miles
                        elif unit_upper == 'IN':
                            visibility_sm = vis_value / 63360.0  # inches to miles
                        else:
                            continue  # Unknown unit, try next
                        _logger.debug(f"Visibility: {vis_value} {unit} = {visibility_sm:.2f} SM (threshold: {self.visibility} SM)")
                        break
                except (ValueError, TypeError):
                    continue

            if visibility_sm is not None:
                self._visible = visibility_sm > self.visibility

            # Check for broken (BKN) or overcast (OVC) clouds
            self._cloudy = False
            for sky in obs.sky:
                if sky[0] in ['BKN', 'OVC']:
                    self._cloudy = True
                    break
        except Exception as ex:
            # Log the station and the exception message; include traceback for debugging.
            _logger.warning(
                "Failed to fetch or parse METAR data for station %s: %s",
                self.station,
                ex,
                exc_info=True,
            )
            # assume worst case on error
            self._visible = False
            self._cloudy = True

    def refresh(self):
        """
        This is called to refresh state.
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        self.observer.lat = str(self.latitude)
        self.observer.lon = str(self.longitude)
        self.observer.elevation = self.elevation
        self.observer.compute_pressure()

        self.observer.date = now  # UTC
        self.sun_ephem.compute(self.observer)
        self.sun_angle = self.sun_ephem.alt / ephem.degree

        # fetch weather station information
        self._fetch_metar()


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
    elevation = weather_config.get("elevation", 10.0)  # meters
    angle = weather_config.get("angle", -6)  # civil twilight
    station = weather_config.get("station", "KJFK")
    visibility = weather_config.get("visibility", 6.0)  # statute miles

    weather = WeatherChecker(
        latitude=latitude,
        longitude=longitude,
        elevation=elevation,
        angle=angle,
        station=station,
        visibility=visibility
    )

    print(f"Is it light? {weather.is_light}")
    print(f"Is it dark? {weather.is_dark}")
    print(f"Is it cloudy? {weather.is_cloudy}")
    print(f"Is visibility good? {weather.is_visible}")

    # Use context manager for BoardController and catch discovery failure at creation time.
    try:
        with BoardController() as board:
            if weather.is_light and not weather.is_cloudy and weather.is_visible:
                print("Turning on (light and clear)...")
                board.send_raw(data=bytes([0xD8, 0x01]))  # on
            else:
                print("Turning off (dark or cloudy)...")
                board.send_raw(data=bytes([0xD8, 0x00]))  # off
    except RuntimeError as e:
        _logger.error("BoardController unavailable: %s - skipping board operations.", e)
        _logger.info("No serial board available; completed checks without hardware control.")


if __name__ == "__main__":
    main()
