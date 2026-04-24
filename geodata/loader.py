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
    """Return SF land polygon from OSM coastline ways + admin fallback for the north strip.

    Builds the SF peninsula land polygon by finding the coastline way chain that
    traces the full peninsula (both Bay and Pacific coasts, from south tip to south
    tip) and closing it into a polygon.  That gives accurate Bay-side boundaries
    (fixing the natural=bay polygon gap near Mission Bay).

    The coastline path only reaches ~lat 37.81 at the northern waterfront, so the
    strip above that (Presidio / Golden Gate approach) is supplemented by the
    admin-minus-bay approach, which is accurate there.

    Falls back to admin-minus-bay for the whole polygon if coastline data fails.
    """
    def _bay_polygon():
        from shapely.ops import unary_union
        # OSMnx 2.x bbox format: (left, bottom, right, top)
        bay_gdf = ox.features_from_bbox(
            bbox=(-122.555, 37.440, -122.030, 37.990), tags={"natural": "bay"}
        )
        polys = bay_gdf[bay_gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].geometry.tolist()
        return unary_union(polys) if polys else None

    def fetch():
        from shapely.ops import linemerge, unary_union
        from shapely.geometry import Polygon, box as sbox

        admin_poly = ox.geocode_to_gdf(PLACE).geometry.iloc[0]

        try:
            # Get coastline ways in a wide SF bbox
            coast_gdf = ox.features_from_bbox(
                bbox=(-122.55, 37.60, -122.32, 37.90),
                tags={"natural": "coastline"},
            )
            lines = coast_gdf[coast_gdf.geometry.geom_type == "LineString"].geometry.tolist()
            merged = linemerge(lines)
            pieces = merged.geoms if hasattr(merged, "geoms") else [merged]

            # The SF peninsula piece has both endpoints south of lat 37.65
            sf_piece = next(
                (g for g in pieces
                 if len(list(g.coords)) > 1000
                 and list(g.coords)[0][1] < 37.65
                 and list(g.coords)[-1][1] < 37.65),
                None,
            )
            if sf_piece is None:
                raise ValueError("SF peninsula coastline piece not found")

            coords = list(sf_piece.coords)
            coast_land = Polygon(coords + [coords[0]])
            if not coast_land.is_valid:
                from shapely import make_valid
                coast_land = make_valid(coast_land)

            # Clip to the visible SF map area (admin polygon clips incorrectly at
            # the southern Hunters Point / India Basin boundary, so use a bbox instead)
            vis_box = sbox(-122.56, 37.65, -122.32, 37.90)
            coast_land = coast_land.intersection(vis_box)

            # Supplement the northern strip (lat 37.81+) with admin-minus-bay for
            # the eastern/bay side only. Clip west to ~-122.47 (≈ Pacific coast at
            # those latitudes) so we don't paint Pacific Ocean as land.
            north_strip = sbox(-122.47, 37.806, -122.32, 37.90)
            bay = _bay_polygon()
            if bay is not None:
                north_land = admin_poly.difference(bay).intersection(north_strip)
                coast_land = unary_union([coast_land, north_land])

            if coast_land.is_empty:
                raise ValueError("Empty coastline land polygon")

            return gpd.GeoDataFrame(geometry=[coast_land], crs="EPSG:4326")

        except Exception as exc:
            logger.warning("Coastline polygon failed: %s — falling back to admin-minus-bay", exc)

        # Fallback: admin polygon minus Bay polygon
        try:
            bay = _bay_polygon()
            if bay is not None:
                land = admin_poly.difference(bay)
                return gpd.GeoDataFrame(geometry=[land], crs="EPSG:4326")
        except Exception as exc2:
            logger.warning("Bay subtraction also failed: %s — using raw admin boundary", exc2)

        return ox.geocode_to_gdf(PLACE)

    return _load_or_fetch("boundary", fetch)


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


def get_muni_routes() -> gpd.GeoDataFrame:
    """OSM tram/light-rail ways in SF, cached to muni_routes.gpkg.

    Columns: geometry (LineString), ref (Muni route letter extracted from name,
    e.g. 'N' from 'Muni N'; empty string for shared/unnamed tracks).
    Uses its own cache logic (not _load_or_fetch) to preserve the ref column.
    """
    import re

    def _ref_from_name(name) -> str:
        if not name or (hasattr(name, "__class__") and name != name):  # NaN check
            return ""
        m = re.match(r"Muni\s+([A-Z])\b", str(name))
        return m.group(1) if m else ""

    path = _cache_path("muni_routes")
    try:
        if os.path.exists(path):
            logger.debug("Loading muni_routes from cache: %s", path)
            return gpd.read_file(path)
        logger.info("Fetching Muni routes from OSMnx (Overpass API)...")
        os.makedirs(CACHE_DIR, exist_ok=True)
        gdf = ox.features_from_place(PLACE, tags={"railway": ["tram", "light_rail"]})
        gdf = gdf.copy()
        name_col = gdf["name"] if "name" in gdf.columns else None
        ref_col = gdf["ref"] if "ref" in gdf.columns else None
        if ref_col is not None:
            gdf["ref"] = ref_col.fillna("").astype(str)
        elif name_col is not None:
            gdf["ref"] = name_col.apply(_ref_from_name)
        else:
            gdf["ref"] = ""
        out = gdf[["geometry", "ref"]]
        out.to_file(path, driver="GPKG")
        logger.info("Cached muni_routes to %s (%d rows)", path, len(out))
        return out
    except Exception as exc:
        logger.error("Failed to fetch muni_routes: %s — returning empty GeoDataFrame", exc)
        return gpd.GeoDataFrame({"geometry": [], "ref": []}, crs="EPSG:4326")
