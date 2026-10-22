"""
live_data.py

Fetches live/current climate data for MENA country capitals using Open-Meteo,
a free public weather API that requires no API key. This is the one data
feed in AquaNexus that is genuinely live rather than a static curated value.

Electricity prices are NOT fetched live here: no free public API exists for
electricity tariffs by country. Those remain a curated, sourced table in
country_profiles.yaml, refreshed manually as better data is found (see
data/sources.csv for provenance of every figure).

If the live climate API call fails (no network, API down), calling code
should fall back to the static ambient_temperature_normal_c value in
country_profiles.yaml and clearly indicate the fallback occurred.
"""

import requests
from dataclasses import dataclass
from typing import Optional

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Capital city coordinates for each MENA country profile. Used only to
# anchor the live climate lookup, not as a claim that the whole country
# shares the capital's exact climate.
COUNTRY_CAPITALS = {
    "UAE": {"city": "Abu Dhabi", "lat": 24.4539, "lon": 54.3773},
    "Saudi_Arabia": {"city": "Riyadh", "lat": 24.7136, "lon": 46.6753},
    "Qatar": {"city": "Doha", "lat": 25.2854, "lon": 51.5310},
    "Jordan": {"city": "Amman", "lat": 31.9454, "lon": 35.9284},
    "Morocco": {"city": "Rabat", "lat": 34.0209, "lon": -6.8416},
    "Algeria": {"city": "Algiers", "lat": 36.7538, "lon": 3.0588},
    "Tunisia": {"city": "Tunis", "lat": 36.8065, "lon": 10.1815},
}


@dataclass
class LiveClimateResult:
    temperature_c: float
    relative_humidity_pct: Optional[float]
    city: str
    fetched_live: bool
    source: str


def fetch_live_climate(country_key: str, timeout_seconds: float = 5.0) -> Optional[LiveClimateResult]:
    """
    Fetch current temperature and relative humidity for a MENA country's
    capital city via Open-Meteo. Returns None if the country is not in
    COUNTRY_CAPITALS or if the API call fails for any reason (network
    error, timeout, unexpected response shape) -- callers must handle the
    None case by falling back to a static value, never by crashing.
    """
    if country_key not in COUNTRY_CAPITALS:
        return None

    loc = COUNTRY_CAPITALS[country_key]
    params = {
        "latitude": loc["lat"],
        "longitude": loc["lon"],
        "current": "temperature_2m,relative_humidity_2m",
        "timezone": "auto",
    }

    try:
        response = requests.get(OPEN_METEO_URL, params=params, timeout=timeout_seconds)
        response.raise_for_status()
        data = response.json()
        current = data["current"]
        return LiveClimateResult(
            temperature_c=float(current["temperature_2m"]),
            relative_humidity_pct=float(current.get("relative_humidity_2m")) if current.get("relative_humidity_2m") is not None else None,
            city=loc["city"],
            fetched_live=True,
            source="Open-Meteo (api.open-meteo.com), live current-weather endpoint",
        )
    except (requests.RequestException, KeyError, ValueError, TypeError):
        return None
