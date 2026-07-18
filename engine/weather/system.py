"""Weather simulation — climate, seasons, weather events."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from engine.core.clock import Season
from engine.utils.rng import RNG
from engine.world.map import WorldMap


class WeatherType(Enum):
    CLEAR = "clear"
    CLOUDY = "cloudy"
    OVERCAST = "overcast"
    FOG = "fog"
    DRIZZLE = "drizzle"
    RAIN = "rain"
    HEAVY_RAIN = "heavy_rain"
    THUNDERSTORM = "thunderstorm"
    SNOW = "snow"
    BLIZZARD = "blizzard"
    HAIL = "hail"
    HEATWAVE = "heatwave"
    DROUGHT = "drought"
    SANDSTORM = "sandstorm"
    AURORA = "aurora"


class ClimateType(Enum):
    TROPICAL = "tropical"
    ARID = "arid"
    TEMPERATE = "temperate"
    CONTINENTAL = "continental"
    POLAR = "polar"
    ALPINE = "alpine"


@dataclass
class Climate:
    """A climate definition."""

    climate_type: ClimateType
    base_temperature: float       # Celsius annual mean
    temperature_variance: float   # seasonal swing
    base_humidity: float = 0.5
    precipitation_frequency: float = 0.3
    extreme_weather_chance: float = 0.05

    def seasonal_temperature(self, season: Season) -> float:
        if self.climate_type == ClimateType.TROPICAL:
            return self.base_temperature + self.temperature_variance * 0.3 * math.sin(season.value)
        if self.climate_type == ClimateType.ARID:
            offset = [-5, 5, -3, -10][season.value]
            return self.base_temperature + offset
        if self.climate_type == ClimateType.TEMPERATE:
            offset = [-8, 8, 3, -10][season.value]
            return self.base_temperature + offset
        if self.climate_type == ClimateType.CONTINENTAL:
            offset = [-20, 15, 5, -25][season.value]
            return self.base_temperature + offset
        if self.climate_type == ClimateType.POLAR:
            offset = [-15, 5, -5, -25][season.value]
            return self.base_temperature + offset
        if self.climate_type == ClimateType.ALPINE:
            offset = [-10, 6, 2, -15][season.value]
            return self.base_temperature + offset
        return self.base_temperature


@dataclass
class Weather:
    """Current weather state."""

    type: WeatherType = WeatherType.CLEAR
    temperature: float = 15.0
    humidity: float = 0.5
    wind_speed: float = 5.0       # km/h
    wind_direction: float = 0.0   # degrees
    visibility: float = 1.0       # 0..1
    pressure: float = 1013.0      # hPa
    duration: float = 3600.0      # seconds remaining

    def description(self) -> str:
        return (
            f"{self.type.value.replace('_', ' ').title()}, "
            f"{self.temperature:.0f}°C, wind {self.wind_speed:.0f} km/h, "
            f"humidity {self.humidity * 100:.0f}%"
        )


class WeatherSystem:
    """Simulates weather over the world map."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self.climate: Climate = Climate(ClimateType.TEMPERATE, 12.0, 8.0)
        self.current: Weather = Weather()
        self.history: list[WeatherType] = []
        self._transition_timer: float = 0.0

    def set_climate(self, climate: Climate) -> None:
        self.climate = climate

    def update(self, dt: float, season: Season) -> Weather:
        self._transition_timer += dt
        self.current.duration -= dt
        if self.current.duration <= 0:
            self._transition(season)
        # Slow temperature drift
        target_temp = self.climate.seasonal_temperature(season)
        if self.current.type in (WeatherType.HEATWAVE,):
            target_temp += 8.0
        elif self.current.type in (WeatherType.BLIZZARD, WeatherType.SNOW,
                                   WeatherType.HAIL):
            target_temp -= 5.0
        self.current.temperature += (target_temp - self.current.temperature) * 0.01 * dt
        # Wind shifts slowly
        self.current.wind_direction += self.rng.uniform(-5, 5) * dt
        self.current.wind_direction %= 360
        return self.current

    def _transition(self, season: Season) -> None:
        old_type = self.current.type
        # Weighted choice of next weather based on season & climate
        weights = self._seasonal_weights(season)
        types = list(weights.keys())
        ws = list(weights.values())
        new_type = self.rng.weighted_choice(types, ws)
        self.current.type = new_type
        self.current.duration = self.rng.uniform(1800, 14400)  # 30 min to 4 hours
        # Adjust other properties
        if new_type in (WeatherType.RAIN, WeatherType.HEAVY_RAIN,
                        WeatherType.THUNDERSTORM):
            self.current.humidity = self.rng.uniform(0.7, 1.0)
            self.current.visibility = 0.5 if new_type == WeatherType.HEAVY_RAIN else 0.7
            self.current.wind_speed = self.rng.uniform(15, 40)
        elif new_type == WeatherType.THUNDERSTORM:
            self.current.wind_speed = self.rng.uniform(30, 70)
            self.current.visibility = 0.3
        elif new_type == WeatherType.FOG:
            self.current.humidity = self.rng.uniform(0.9, 1.0)
            self.current.visibility = self.rng.uniform(0.1, 0.4)
            self.current.wind_speed = self.rng.uniform(0, 5)
        elif new_type in (WeatherType.SNOW, WeatherType.BLIZZARD):
            self.current.humidity = self.rng.uniform(0.6, 0.9)
            self.current.visibility = 0.4 if new_type == WeatherType.SNOW else 0.1
            self.current.wind_speed = self.rng.uniform(10, 25) if new_type == WeatherType.SNOW else self.rng.uniform(40, 80)
        elif new_type == WeatherType.SANDSTORM:
            self.current.visibility = 0.2
            self.current.wind_speed = self.rng.uniform(40, 90)
        elif new_type == WeatherType.CLEAR:
            self.current.visibility = 1.0
            self.current.wind_speed = self.rng.uniform(0, 15)
            self.current.humidity = self.rng.uniform(0.3, 0.6)
        elif new_type == WeatherType.HEATWAVE:
            self.current.humidity = self.rng.uniform(0.1, 0.3)
            self.current.visibility = 0.9
            self.current.wind_speed = self.rng.uniform(0, 5)
        else:
            self.current.visibility = 0.8
            self.current.wind_speed = self.rng.uniform(5, 20)
            self.current.humidity = self.rng.uniform(0.5, 0.8)

        self.history.append(new_type)
        if len(self.history) > 100:
            self.history = self.history[-100:]

    def _seasonal_weights(self, season: Season) -> dict[WeatherType, float]:
        c = self.climate.climate_type
        if c == ClimateType.TROPICAL:
            return {
                WeatherType.CLEAR: 4.0, WeatherType.CLOUDY: 2.0,
                WeatherType.RAIN: 3.0, WeatherType.HEAVY_RAIN: 1.5,
                WeatherType.THUNDERSTORM: 1.0,
                WeatherType.HEATWAVE: 0.5 if season == Season.SUMMER else 0.0,
                WeatherType.OVERCAST: 1.0,
            }
        if c == ClimateType.ARID:
            return {
                WeatherType.CLEAR: 6.0, WeatherType.CLOUDY: 1.0,
                WeatherType.HEATWAVE: 2.0 if season == Season.SUMMER else 0.5,
                WeatherType.DROUGHT: 1.5,
                WeatherType.SANDSTORM: 1.0,
                WeatherType.RAIN: 0.2,
            }
        if c == ClimateType.POLAR:
            return {
                WeatherType.CLEAR: 2.0, WeatherType.CLOUDY: 1.5,
                WeatherType.OVERCAST: 1.0, WeatherType.SNOW: 3.0,
                WeatherType.BLIZZARD: 2.0 if season in (Season.WINTER, Season.AUTUMN) else 0.5,
                WeatherType.FOG: 1.0,
                WeatherType.AURORA: 0.5 if season == Season.WINTER else 0.0,
            }
        # Temperate / continental / alpine
        if season == Season.SPRING:
            return {
                WeatherType.CLEAR: 3.0, WeatherType.CLOUDY: 2.5,
                WeatherType.RAIN: 2.0, WeatherType.DRIZZLE: 1.5,
                WeatherType.FOG: 1.0, WeatherType.OVERCAST: 1.5,
                WeatherType.THUNDERSTORM: 0.5,
            }
        if season == Season.SUMMER:
            return {
                WeatherType.CLEAR: 4.0, WeatherType.CLOUDY: 2.0,
                WeatherType.RAIN: 1.5, WeatherType.THUNDERSTORM: 1.5,
                WeatherType.HEATWAVE: 1.0, WeatherType.OVERCAST: 1.0,
                WeatherType.HAIL: 0.3,
            }
        if season == Season.AUTUMN:
            return {
                WeatherType.CLEAR: 2.0, WeatherType.CLOUDY: 3.0,
                WeatherType.OVERCAST: 2.5, WeatherType.RAIN: 2.5,
                WeatherType.HEAVY_RAIN: 1.0, WeatherType.FOG: 2.0,
                WeatherType.WIND: 0 if False else 1.0,
            }
        # Winter
        return {
            WeatherType.CLEAR: 2.0, WeatherType.CLOUDY: 2.0,
            WeatherType.OVERCAST: 2.0, WeatherType.SNOW: 3.0,
            WeatherType.BLIZZARD: 1.0, WeatherType.FOG: 1.5,
        }
