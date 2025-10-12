#!/usr/bin/env python3
import os.path
import datetime
from pathlib import Path
from suntime import Sun  # type: ignore
import ephem  # type: ignore
from metar import Metar
import tomllib as toml


class WeatherChecker:
    def __init__(self):
        self.config_file_path = os.path.join(Path(__file__).parent, "crypto.toml")

        self.coordinates = self._load_configuration()

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
        peak = 3
        if month in range(6, 13):
            result = month
        elif month in range(1, 6):
            result = (12 - month)
        else:
            result = month
        result = result ** (1 + (peak / 10))
        return result

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
        """Check if the current METAR report indicates cloudy conditions (BKN or OVC)."""
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
        except Exception as ex:
            return False

# Example usage in main()
def main():
    weather = WeatherChecker()
    print(f"Is it light? {weather.is_light}")
    print(f"Is it dark? {weather.is_dark}")
    print(f"Is it cloudy? {weather.is_cloudy}")

if __name__ == "__main__":
    main()
