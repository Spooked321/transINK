"""
Fetches real-time Muni vehicle positions from the 511 SF Bay GTFS-RT API.
"""

import logging
import os
import time

import requests
from dotenv import load_dotenv
from google.transit import gtfs_realtime_pb2

load_dotenv()

logger = logging.getLogger(__name__)

API_BASE = "https://api.511.org/transit"

SF_BOUNDS = {
    "lat_min": 37.6880,
    "lat_max": 37.8324,
    "lon_min": -122.5170,
    "lon_max": -122.3549,
}

_cache: list[dict] = []


def _in_bounds(lat: float, lon: float) -> bool:
    return (SF_BOUNDS["lat_min"] <= lat <= SF_BOUNDS["lat_max"] and
            SF_BOUNDS["lon_min"] <= lon <= SF_BOUNDS["lon_max"])


def get_vehicles() -> list[dict]:
    """Fetch and parse Muni vehicle positions from 511 GTFS-RT.

    Returns positions filtered to SF bounding box. Falls back to cached
    data on error so the render loop never crashes.
    """
    global _cache

    api_key = os.environ["TRANSIT_API_KEY"]
    url = f"{API_BASE}/vehiclepositions?api_key={api_key}&agency=SF"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()

        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)

        vehicles = []
        for entity in feed.entity:
            if not entity.HasField("vehicle"):
                continue
            v = entity.vehicle
            lat = v.position.latitude
            lon = v.position.longitude
            if not _in_bounds(lat, lon):
                continue
            vehicles.append({
                "agency": "SF",
                "vehicle_id": v.vehicle.id,
                "route_id": v.trip.route_id,
                "lat": lat,
                "lon": lon,
                "timestamp": v.timestamp if v.timestamp else int(time.time()),
            })

        logger.info("Muni: %d vehicles in SF bounds", len(vehicles))
        _cache = vehicles
        return vehicles

    except Exception as exc:
        logger.error("Muni fetch failed: %s — using cached data (%d vehicles)", exc, len(_cache))
        return _cache
