"""
crypto.py - Weather and Board Control Application

This module provides the WeatherChecker and BoardController classes for controlling hardware
via a serial bridge based on weather and time conditions. Configuration is loaded from a local
crypto.toml file. The main loop periodically checks weather conditions and controls a board pin
accordingly, with the interval configurable via the TOML file.

Classes:
    WeatherChecker: Loads weather configuration, computes sun position, and fetches cloud state.
    BoardController: Sends raw pin commands to a board using the serial bridge protocol.

Example:
    Run this script directly to start the main control loop.
    Configuration is read from crypto.toml in the same directory.
"""

#!/usr/bin/env python3
import os.path
import datetime
import time
from pathlib import Path
from suntime import Sun  # type: ignore
import ephem  # type: ignore
from metar import Metar
import tomllib as toml

from embedded_serial_bridge import Comm
from embedded_serial_bridge.auto_discovery import discover


class WeatherChecker:
    def __init__(self):
        self.config_file_path = os.path.join(Path(__file__).parent, "crypto.toml")
        self.coordinates = self._load_configuration()

        self.process()

    @property
    def is_light(self):
        self.sun_ephem.compute(self.observer)
        sun_angle = self.sun_ephem.alt / ephem.degree
        return sun_angle >= self.sun_angle_offset

    @property
    def is_dark(self):
        return not self.is_light

    @property
    def is_cloudy(self):
        """Return the last fetched cloud state (True/False). Call process() to refresh."""
        return self._cloudy

    # --- Private methods ---
    def _load_configuration(self):
        with open(self.config_file_path, "rb") as f:
            config = toml.load(f)
        weather = config.get("weather", {})
        # Remove all default values for privacy
        lat = weather.get("latitude")
        lon = weather.get("longitude")
        elev = weather.get("elevation")
        station = weather.get("station", None)
        self.station = station.strip("'")
        self.interval_seconds = int(weather.get("interval_seconds", 3600))

        return lat, lon, elev

    def _sun_out(self):
        # Use the observer's longitude to estimate the local timezone offset from UTC
        # This is a rough estimate: 15 degrees longitude per hour offset

        longitude = float(self.coordinates[1])
        utc_offset_hours = int(round(longitude / 15.0))

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
        Perform all the setup and calculations for sun, observer, and sun angles.
        This is called during __init__, but can also be called to refresh state.
        Also fetches and sets the current cloud state as self.cloudy.
        """
        self.utc = datetime.datetime.now(datetime.timezone.utc)
        self.sun = Sun(self.coordinates[0], self.coordinates[1])

        self.observer = ephem.Observer()
        self.observer.lat = str(self.coordinates[0])
        self.observer.lon = str(self.coordinates[1])
        self.observer.elevation = self.coordinates[2]
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
    Automatically discovers the serial port using the internal discover() function.
    """
    def __init__(self, port=None, baudrate=115200, timeout=0.1):
        if port is None:
            port = discover()
            if port is None:
                raise RuntimeError("No serial port found by discovery.")

        self.comm = Comm(port=port, baudrate=baudrate, timeout=timeout)

    def send_raw(self, data: bytes) -> None:
        """
        Send a raw command to the board with the given data bytes using the Message data type.
        Args:
            data (bytes): Raw data to send (user is responsible for format)
        """
        from embedded_serial_bridge.comm import Message, Command
        if not isinstance(data, bytes):
            raise ValueError("data must be of type bytes")
        # Use the Raw command type for raw data
        msg = Message.make(command=Command.Raw, payload=data)
        self.comm.write(msg)
        # Optionally, wait for a response or add retries here

    def close(self):
        self.comm.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def main():
    weather = WeatherChecker()
    print(f"Is it light? {weather.is_light}")
    print(f"Is it dark? {weather.is_dark}")
    print(f"Is it cloudy? {weather.is_cloudy}")

    test = True
    with BoardController() as board:
        if weather.is_light and not weather.is_cloudy and test:
            print("on...")
            board.send_raw(data=bytes([0xD8, 0x01]))  # on
        else:
            print("off...")
            board.send_raw(data=bytes([0xD8, 0x00]))  # off

if __name__ == "__main__":
    main()
