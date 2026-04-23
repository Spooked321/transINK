"""
Fetches BART train positions by interpolating along track segments using
the BART Legacy ETD API. No API key required for the demo key.

Position interpolation approach:
- ETD API returns minutes until each train departs each SF station
- We identify which segment each train is on (prev_station → station)
- We interpolate along the straight line between those station coords
- Positions outside the SF bounding box are filtered out
"""

import logging
import os
import time
import xml.etree.ElementTree as ET

import requests

logger = logging.getLogger(__name__)

BART_ETD_URL = (
    "http://api.bart.gov/api/etd.aspx"
    "?cmd=etd&orig=ALL&key=MW9S-E7SL-26DU-VV8V&json=y"
)

SF_BOUNDS = {
    "lat_min": 37.6880,
    "lat_max": 37.8324,
    "lon_min": -122.5170,
    "lon_max": -122.3549,
}

# SF BART stations ordered south → north through the tunnel
SF_STATIONS_ORDERED = ["DALY", "BALB", "GLEN", "24TH", "16TH", "CIVC", "POWL", "MONT", "EMBR"]
SF_STATION_INDEX = {s: i for i, s in enumerate(SF_STATIONS_ORDERED)}

# Approximate inter-station travel times in minutes (northbound order)
SEGMENT_TIMES: dict[tuple[str, str], int] = {
    ("DALY", "BALB"): 4,
    ("BALB", "GLEN"): 2,
    ("GLEN", "24TH"): 3,
    ("24TH", "16TH"): 2,
    ("16TH", "CIVC"): 2,
    ("CIVC", "POWL"): 1,
    ("POWL", "MONT"): 1,
    ("MONT", "EMBR"): 1,
}

# Destination abbreviation → BART line color name
DEST_TO_COLOR: dict[str, str] = {
    "ANTC": "YELLOW", "PITT": "YELLOW", "PCTR": "YELLOW",
    "RICH": "RED",
    "DUBL": "BLUE",   "CAST": "BLUE",
    "BERY": "GREEN",  "WARM": "GREEN",
    "MLBR": "ORANGE", "SFIA": "ORANGE",
}

# Official KML station coordinates (lat, lon), loaded once at startup
STATION_COORDS: dict[str, tuple[float, float]] = {}

_cache: list[dict] = []


# ---------------------------------------------------------------------------
# KML loading
# ---------------------------------------------------------------------------

def _load_station_coords() -> dict[str, tuple[float, float]]:
    """Parse BART station coords from the official KML file.

    Returns a dict of abbr → (lat, lon). Falls back to hardcoded SF
    station coords if the KML is unavailable.
    """
    kml_path = os.path.join(os.path.dirname(__file__), "geodata", "bart_stations_tracks.kml")
    if not os.path.exists(kml_path):
        logger.warning("KML not found at %s — using fallback station coords", kml_path)
        return _fallback_coords()

    # KML station name → BART 4-letter abbreviation
    name_to_abbr: dict[str, str] = {
        "Embarcadero":             "EMBR",
        "Montgomery St":           "MONT",
        "Powell St":               "POWL",
        "Civic Center/UN Plaza":   "CIVC",
        "16th St/Mission":         "16TH",
        "24th St/Mission":         "24TH",
        "Glen Park":               "GLEN",
        "Balboa Park":             "BALB",
        "Daly City":               "DALY",
        "Colma":                   "COLM",
        "South San Francisco":     "SSAN",
        "San Bruno":               "SBRN",
        "Millbrae":                "MLBR",
        "San Francisco International Airport": "SFIA",
    }

    try:
        tree = ET.parse(kml_path)
        root = tree.getroot()
        ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""

        coords: dict[str, tuple[float, float]] = {}
        for folder in root.iter(f"{ns}Folder"):
            folder_name = folder.findtext(f"{ns}name") or ""
            if "BART Station" not in folder_name or "Entrance" in folder_name:
                continue
            for pm in folder.iter(f"{ns}Placemark"):
                pm_name = pm.findtext(f"{ns}name") or ""
                pt = pm.find(f".//{ns}Point")
                if pt is None:
                    continue
                coord_text = pt.find(f"{ns}coordinates")
                if coord_text is None or not coord_text.text:
                    continue
                lon_str, lat_str = coord_text.text.strip().split(",")[:2]
                abbr = name_to_abbr.get(pm_name)
                if abbr:
                    coords[abbr] = (float(lat_str), float(lon_str))

        logger.info("Loaded %d SF BART station coords from KML", len(coords))
        return coords

    except Exception as exc:
        logger.error("KML parse error: %s — using fallback coords", exc)
        return _fallback_coords()


def _fallback_coords() -> dict[str, tuple[float, float]]:
    return {
        "EMBR": (37.7929, -122.3969),
        "MONT": (37.7894, -122.4012),
        "POWL": (37.7849, -122.4070),
        "CIVC": (37.7794, -122.4139),
        "16TH": (37.7651, -122.4197),
        "24TH": (37.7522, -122.4185),
        "GLEN": (37.7331, -122.4338),
        "BALB": (37.7214, -122.4476),
        "DALY": (37.7063, -122.4689),
    }


# Load station coords once at import time
STATION_COORDS = _load_station_coords()


# ---------------------------------------------------------------------------
# Interpolation helpers
# ---------------------------------------------------------------------------

def _in_bounds(lat: float, lon: float) -> bool:
    return (SF_BOUNDS["lat_min"] <= lat <= SF_BOUNDS["lat_max"] and
            SF_BOUNDS["lon_min"] <= lon <= SF_BOUNDS["lon_max"])


def _get_prev_station(station: str, direction: str) -> str | None:
    """Return the station a train came from given its current station and direction."""
    idx = SF_STATION_INDEX.get(station)
    if idx is None:
        return None
    if direction == "North":
        return SF_STATIONS_ORDERED[idx - 1] if idx > 0 else None
    else:
        return SF_STATIONS_ORDERED[idx + 1] if idx < len(SF_STATIONS_ORDERED) - 1 else None


def _get_segment_time(prev: str, curr: str) -> int | None:
    return SEGMENT_TIMES.get((prev, curr)) or SEGMENT_TIMES.get((curr, prev))


def _interpolate(prev: str, curr: str, fraction: float) -> tuple[float, float]:
    """Interpolate lat/lon between two stations. fraction=0 → prev, 1 → curr."""
    lat_p, lon_p = STATION_COORDS[prev]
    lat_c, lon_c = STATION_COORDS[curr]
    return lat_p + fraction * (lat_c - lat_p), lon_p + fraction * (lon_c - lon_p)


# ---------------------------------------------------------------------------
# Main fetch
# ---------------------------------------------------------------------------

def get_vehicles() -> list[dict]:
    """Fetch BART ETD data and return interpolated SF-area vehicle positions.

    Falls back to cached positions on error.
    """
    global _cache

    try:
        resp = requests.get(BART_ETD_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        stations = data.get("root", {}).get("station", [])
        vehicles: list[dict] = []
        seen: set[str] = set()  # deduplicate by (station, dest, estimate_index)
        now = int(time.time())

        for station_data in stations:
            abbr = station_data.get("abbr", "")
            if abbr not in SF_STATION_INDEX:
                continue

            for etd_entry in station_data.get("etd", []):
                dest_abbr = etd_entry.get("abbreviation", "")
                color = DEST_TO_COLOR.get(dest_abbr)
                if color is None:
                    continue

                for i, estimate in enumerate(etd_entry.get("estimate", [])):
                    min_str = estimate.get("minutes", "")
                    if min_str == "Leaving":
                        etd_min = 0.0
                    elif min_str.lstrip("-").isdigit():
                        etd_min = float(min_str)
                    else:
                        continue  # unknown format

                    # Skip stale data
                    ts = estimate.get("epochTime")
                    if ts and (now - int(ts)) > 120:
                        continue

                    direction = estimate.get("direction", "North")
                    prev = _get_prev_station(abbr, direction)
                    if prev is None:
                        continue

                    seg_time = _get_segment_time(prev, abbr)
                    if seg_time is None:
                        continue

                    fraction = max(0.0, min(1.0, (seg_time - etd_min) / seg_time))
                    lat, lon = _interpolate(prev, abbr, fraction)

                    if not _in_bounds(lat, lon):
                        continue

                    vid = f"bart_{abbr}_{dest_abbr}_{i}"
                    if vid in seen:
                        continue
                    seen.add(vid)

                    vehicles.append({
                        "agency": "BA",
                        "vehicle_id": vid,
                        "route_id": color,
                        "lat": lat,
                        "lon": lon,
                        "timestamp": now,
                    })

        logger.info("BART: %d interpolated vehicles in SF bounds", len(vehicles))
        _cache = vehicles
        return vehicles

    except Exception as exc:
        logger.error("BART fetch failed: %s — using cached data (%d vehicles)", exc, len(_cache))
        return _cache
