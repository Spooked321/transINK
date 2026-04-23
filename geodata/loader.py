"""
Fetches and caches OpenStreetMap geodata for San Francisco via OSMnx.

Each public function checks for a GeoPackage cache file. On a cold cache
(first run), it fetches from the Overpass API and writes the cache. On a
warm cache, it reads the .gpkg directly. Delete geodata/cache/ to force
a re-fetch.
"""

import logging
import os

import geopandas as gpd
import osmnx as ox

logger = logging.getLogger(__name__)

PLACE = "San Francisco, California, USA"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")

STREET_FILTER = '["highway"~"primary|secondary|tertiary"]'


def _cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, f"{name}.gpkg")


def _load_or_fetch(name: str, fetch_fn) -> gpd.GeoDataFrame:
    """Generic cache-or-fetch pattern. Returns empty GeoDataFrame on error."""
    path = _cache_path(name)
    try:
        if os.path.exists(path):
            logger.debug("Loading %s from cache: %s", name, path)
            return gpd.read_file(path)
        logger.info("Fetching %s from OSMnx (Overpass API)...", name)
        os.makedirs(CACHE_DIR, exist_ok=True)
        gdf = fetch_fn()
        gdf[["geometry"]].to_file(path, driver="GPKG")
        logger.info("Cached %s to %s (%d rows)", name, path, len(gdf))
        return gdf[["geometry"]]
    except Exception as exc:
        logger.error("Failed to fetch %s: %s — returning empty GeoDataFrame", name, exc)
        return gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")


def get_boundary() -> gpd.GeoDataFrame:
    """Return the SF administrative boundary as a single-row GeoDataFrame."""
    return _load_or_fetch("boundary", lambda: ox.geocode_to_gdf(PLACE))


def get_parks() -> gpd.GeoDataFrame:
    """Return SF park polygons (leisure=park, Polygon/MultiPolygon only)."""
    def fetch():
        gdf = ox.features_from_place(PLACE, tags={"leisure": "park"})
        return gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    return _load_or_fetch("parks", fetch)


def get_water() -> gpd.GeoDataFrame:
    """Return SF inland water polygons (natural=water, Polygon/MultiPolygon only)."""
    def fetch():
        gdf = ox.features_from_place(PLACE, tags={"natural": "water"})
        return gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    return _load_or_fetch("water", fetch)


def get_streets() -> gpd.GeoDataFrame:
    """Return SF primary/secondary/tertiary road edge geometries."""
    def fetch():
        G = ox.graph_from_place(PLACE, custom_filter=STREET_FILTER)
        return ox.graph_to_gdfs(G, nodes=False)
    return _load_or_fetch("streets", fetch)
