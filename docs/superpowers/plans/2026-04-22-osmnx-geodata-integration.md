# OSMnx Geodata Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace renderer.py's three low-fidelity hardcoded data sources (Bay polygon, park rects, GeoJSON coastline) with real OpenStreetMap geometry fetched via OSMnx and cached as GeoPackage files, adding a street network layer in the process.

**Architecture:** A new `geodata/loader.py` module handles all OSMnx fetching and GeoPackage caching; `renderer.py` imports from it at module level so data is loaded once per process. A new `draw_geom()` helper in `renderer.py` projects Shapely geometries through the existing `project()` function onto the Pillow canvas.

**Tech Stack:** osmnx, shapely, geopandas (transitive), Pillow (existing), pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `geodata/__init__.py` | Create | Makes `geodata` a Python package |
| `geodata/loader.py` | Create | OSMnx fetch + GeoPackage cache for boundary, parks, water, streets |
| `geodata/cache/` | Created at runtime | `.gpkg` cache files, gitignored |
| `tests/__init__.py` | Create | Makes `tests` a Python package |
| `tests/test_loader.py` | Create | Unit tests for loader cache hit/miss + polygon filtering |
| `tests/test_renderer.py` | Create | Unit tests for `draw_geom()` |
| `renderer.py` | Modify | Add `draw_geom()`, swap OSMnx layers in `render()`, remove old constants/helpers |
| `requirements.txt` | Modify | Add `osmnx`, `shapely` |
| `.gitignore` | Modify | Add `geodata/cache/` |

---

## Task 1: Verify OSMnx Installs and Can Fetch SF Data

**Files:** none (verification only)

- [ ] **Step 1: Install osmnx and shapely into the venv**

```bash
.venv/bin/pip install osmnx shapely
```

Expected: Clean install. osmnx pulls in geopandas, networkx, pyproj transitively.

- [ ] **Step 2: Verify SF boundary fetch works**

```bash
.venv/bin/python -c "
import osmnx as ox
gdf = ox.geocode_to_gdf('San Francisco, California, USA')
print('CRS:', gdf.crs)
print('Rows:', len(gdf))
print('Bounds:', gdf.total_bounds)
"
```

Expected output (approximate):
```
CRS: EPSG:4326
Rows: 1
Bounds: [-122.517... 37.707... -122.357... 37.833...]
```

- [ ] **Step 3: Verify parks fetch works**

```bash
.venv/bin/python -c "
import osmnx as ox
gdf = ox.features_from_place('San Francisco, California, USA', tags={'leisure': 'park'})
polys = gdf[gdf.geometry.geom_type.isin(['Polygon', 'MultiPolygon'])]
print('Park polygons:', len(polys))
print('Sample names:', list(polys.get('name', polys.index)[:3]))
"
```

Expected: `Park polygons: 50+` (Golden Gate Park, Dolores Park, etc.)

- [ ] **Step 4: Verify street graph fetch works**

```bash
.venv/bin/python -c "
import osmnx as ox
G = ox.graph_from_place(
    'San Francisco, California, USA',
    custom_filter='[\"highway\"~\"primary|secondary|tertiary\"]'
)
edges = ox.graph_to_gdfs(G, nodes=False)
print('Street edges:', len(edges))
print('Geometry type:', edges.geometry.iloc[0].geom_type)
"
```

Expected: `Street edges: 500+`, geometry type `LineString`

---

## Task 2: Add Dependencies and Gitignore Entry

**Files:**
- Modify: `requirements.txt`
- Modify: `.gitignore`

- [ ] **Step 1: Add osmnx and shapely to requirements.txt**

Open `requirements.txt`. Add two lines after the existing deps:
```
osmnx
shapely
```

Final file:
```
Flask
Pillow
requests
schedule
python-dotenv
protobuf
gtfs-realtime-bindings
pykml
osmnx
shapely
```

- [ ] **Step 2: Add cache directory to .gitignore**

Add to `.gitignore`:
```
geodata/cache/
```

- [ ] **Step 3: Commit**

```bash
git add requirements.txt .gitignore
git commit -m "feat: add osmnx and shapely dependencies"
```

---

## Task 3: Create geodata Package and Failing Loader Tests

**Files:**
- Create: `geodata/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_loader.py`

- [ ] **Step 1: Create geodata/__init__.py**

Create `geodata/__init__.py` as an empty file (makes the directory a Python package).

```python
```
(empty file)

- [ ] **Step 2: Create tests/__init__.py**

Create `tests/__init__.py` as an empty file.

```python
```
(empty file)

- [ ] **Step 3: Write failing tests for loader.py**

Create `tests/test_loader.py`:

```python
"""Tests for geodata/loader.py — cache hit/miss behaviour and geometry filtering."""
import os
import sys

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, box
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _boundary_gdf():
    return gpd.GeoDataFrame(
        {"geometry": [box(-122.52, 37.70, -122.35, 37.83)]},
        crs="EPSG:4326",
    )


def _mixed_gdf():
    """GeoDataFrame with polygon + non-polygon rows (points should be filtered)."""
    return gpd.GeoDataFrame(
        {"geometry": [
            box(-122.51, 37.77, -122.45, 37.76),   # Polygon — keep
            box(-122.46, 37.75, -122.44, 37.74),   # Polygon — keep
            Point(-122.4, 37.8),                    # Point — filter out
        ]},
        crs="EPSG:4326",
    )


def _edges_gdf():
    return gpd.GeoDataFrame(
        {"geometry": [
            LineString([(-122.42, 37.77), (-122.41, 37.78)]),
            LineString([(-122.43, 37.76), (-122.42, 37.77)]),
        ]},
        crs="EPSG:4326",
    )


# ---------------------------------------------------------------------------
# get_boundary
# ---------------------------------------------------------------------------

class TestGetBoundary:
    def test_cold_cache_calls_osmnx_and_saves_gpkg(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))

        with patch.object(loader.ox, "geocode_to_gdf", return_value=_boundary_gdf()) as mock_fn:
            result = loader.get_boundary()

        mock_fn.assert_called_once_with("San Francisco, California, USA")
        assert (tmp_path / "boundary.gpkg").exists(), "cache file should be written"
        assert len(result) >= 1
        assert "geometry" in result.columns

    def test_warm_cache_skips_osmnx(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))
        _boundary_gdf()[["geometry"]].to_file(tmp_path / "boundary.gpkg", driver="GPKG")

        with patch.object(loader.ox, "geocode_to_gdf") as mock_fn:
            result = loader.get_boundary()

        mock_fn.assert_not_called()
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# get_parks
# ---------------------------------------------------------------------------

class TestGetParks:
    def test_cold_cache_filters_to_polygons_only(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))

        with patch.object(loader.ox, "features_from_place", return_value=_mixed_gdf()):
            result = loader.get_parks()

        # Must contain only Polygon/MultiPolygon rows
        assert len(result) == 2
        assert all(
            t in ("Polygon", "MultiPolygon")
            for t in result.geometry.geom_type
        )

    def test_warm_cache_skips_osmnx(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))
        _boundary_gdf()[["geometry"]].to_file(tmp_path / "parks.gpkg", driver="GPKG")

        with patch.object(loader.ox, "features_from_place") as mock_fn:
            loader.get_parks()

        mock_fn.assert_not_called()


# ---------------------------------------------------------------------------
# get_water
# ---------------------------------------------------------------------------

class TestGetWater:
    def test_cold_cache_filters_to_polygons_only(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))

        with patch.object(loader.ox, "features_from_place", return_value=_mixed_gdf()):
            result = loader.get_water()

        assert all(
            t in ("Polygon", "MultiPolygon")
            for t in result.geometry.geom_type
        )

    def test_warm_cache_skips_osmnx(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))
        _boundary_gdf()[["geometry"]].to_file(tmp_path / "water.gpkg", driver="GPKG")

        with patch.object(loader.ox, "features_from_place") as mock_fn:
            loader.get_water()

        mock_fn.assert_not_called()


# ---------------------------------------------------------------------------
# get_streets
# ---------------------------------------------------------------------------

class TestGetStreets:
    def test_cold_cache_returns_linestrings(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))

        fake_graph = MagicMock()
        with patch.object(loader.ox, "graph_from_place", return_value=fake_graph):
            with patch.object(loader.ox, "graph_to_gdfs", return_value=_edges_gdf()):
                result = loader.get_streets()

        assert (tmp_path / "streets.gpkg").exists()
        assert len(result) == 2
        assert "geometry" in result.columns

    def test_warm_cache_skips_osmnx(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))
        _edges_gdf()[["geometry"]].to_file(tmp_path / "streets.gpkg", driver="GPKG")

        with patch.object(loader.ox, "graph_from_place") as mock_fn:
            loader.get_streets()

        mock_fn.assert_not_called()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_get_boundary_returns_empty_on_network_error(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))

        with patch.object(loader.ox, "geocode_to_gdf", side_effect=Exception("network error")):
            result = loader.get_boundary()

        assert isinstance(result, gpd.GeoDataFrame)
        assert len(result) == 0
```

- [ ] **Step 4: Run tests — expect ImportError (loader.py doesn't exist yet)**

```bash
.venv/bin/pytest tests/test_loader.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'geodata.loader'` or similar. This confirms the tests are wired correctly.

---

## Task 4: Implement geodata/loader.py

**Files:**
- Create: `geodata/loader.py`

- [ ] **Step 1: Create geodata/loader.py**

```python
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
    if os.path.exists(path):
        logger.debug("Loading %s from cache: %s", name, path)
        return gpd.read_file(path)
    try:
        logger.info("Fetching %s from OSMnx (Overpass API)...", name)
        gdf = fetch_fn()
        os.makedirs(CACHE_DIR, exist_ok=True)
        gdf[["geometry"]].to_file(path, driver="GPKG")
        logger.info("Cached %s to %s (%d rows)", name, path, len(gdf))
        return gdf
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
```

- [ ] **Step 2: Run the loader tests — all should pass**

```bash
.venv/bin/pytest tests/test_loader.py -v
```

Expected:
```
tests/test_loader.py::TestGetBoundary::test_cold_cache_calls_osmnx_and_saves_gpkg PASSED
tests/test_loader.py::TestGetBoundary::test_warm_cache_skips_osmnx PASSED
tests/test_loader.py::TestGetParks::test_cold_cache_filters_to_polygons_only PASSED
tests/test_loader.py::TestGetParks::test_warm_cache_skips_osmnx PASSED
tests/test_loader.py::TestGetWater::test_cold_cache_filters_to_polygons_only PASSED
tests/test_loader.py::TestGetWater::test_warm_cache_skips_osmnx PASSED
tests/test_loader.py::TestGetStreets::test_cold_cache_returns_linestrings PASSED
tests/test_loader.py::TestGetStreets::test_warm_cache_skips_osmnx PASSED
tests/test_loader.py::TestErrorHandling::test_get_boundary_returns_empty_on_network_error PASSED
```

- [ ] **Step 3: Do a real cold-cache fetch to populate geodata/cache/**

```bash
.venv/bin/python -c "
from geodata.loader import get_boundary, get_parks, get_water, get_streets
import logging
logging.basicConfig(level=logging.INFO)
print('Fetching boundary...')
b = get_boundary(); print(f'  boundary: {len(b)} rows')
print('Fetching parks...')
p = get_parks(); print(f'  parks: {len(p)} rows')
print('Fetching water...')
w = get_water(); print(f'  water: {len(w)} rows')
print('Fetching streets...')
s = get_streets(); print(f'  streets: {len(s)} rows')
print('Done. Cache populated.')
"
```

Expected (takes 30–120s on first run):
```
boundary: 1 rows
parks: 50+ rows
water: 10+ rows
streets: 500+ rows
```

- [ ] **Step 4: Verify cache files were written**

```bash
ls -lh geodata/cache/
```

Expected:
```
boundary.gpkg   ~10KB
parks.gpkg      ~100KB
water.gpkg      ~50KB
streets.gpkg    ~500KB
```

- [ ] **Step 5: Commit**

```bash
git add geodata/__init__.py geodata/loader.py tests/__init__.py tests/test_loader.py
git commit -m "feat: add geodata/loader.py with OSMnx fetch and GeoPackage cache"
```

---

## Task 5: Write Failing Tests for draw_geom()

**Files:**
- Create: `tests/test_renderer.py`

- [ ] **Step 1: Write failing tests for draw_geom()**

Create `tests/test_renderer.py`:

```python
"""Tests for renderer.py helper functions."""
import os
import sys

import pytest
from PIL import Image, ImageDraw
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPolygon,
    Point,
    Polygon,
    box,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import renderer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_canvas(w=100, h=100):
    img = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(img)
    return img, draw


def _sf_box(d=0.005):
    """Return a small Polygon centred in SF_BOUNDS (lon, lat order)."""
    lat_mid = (renderer.SF_BOUNDS["lat_min"] + renderer.SF_BOUNDS["lat_max"]) / 2
    lon_mid = (renderer.SF_BOUNDS["lon_min"] + renderer.SF_BOUNDS["lon_max"]) / 2
    return box(lon_mid - d, lat_mid - d, lon_mid + d, lat_mid + d)


def _sf_line():
    """Return a LineString crossing the centre of SF_BOUNDS (lon, lat order)."""
    lat_mid = (renderer.SF_BOUNDS["lat_min"] + renderer.SF_BOUNDS["lat_max"]) / 2
    lon_mid = (renderer.SF_BOUNDS["lon_min"] + renderer.SF_BOUNDS["lon_max"]) / 2
    return LineString([
        (lon_mid - 0.01, lat_mid),
        (lon_mid + 0.01, lat_mid),
    ])


def _any_red(img):
    return any(p[0] > 200 and p[1] < 50 and p[2] < 50 for p in img.getdata())


def _any_blue(img):
    return any(p[2] > 200 and p[0] < 50 for p in img.getdata())


# ---------------------------------------------------------------------------
# draw_geom — Polygon
# ---------------------------------------------------------------------------

class TestDrawGeomPolygon:
    def test_fills_polygon_with_color(self):
        img, draw = _make_canvas()
        renderer.draw_geom(draw, _sf_box(), 100, 100, fill="red")
        assert _any_red(img), "expected red pixels inside polygon"

    def test_draws_outline(self):
        img, draw = _make_canvas()
        renderer.draw_geom(draw, _sf_box(), 100, 100, fill="white", outline=(0, 0, 200))
        assert _any_blue(img), "expected blue outline pixels"

    def test_none_geom_does_not_raise(self):
        _, draw = _make_canvas()
        renderer.draw_geom(draw, None, 100, 100, fill="red")  # should not raise

    def test_empty_geom_does_not_raise(self):
        _, draw = _make_canvas()
        renderer.draw_geom(draw, Polygon(), 100, 100, fill="red")  # should not raise


# ---------------------------------------------------------------------------
# draw_geom — LineString
# ---------------------------------------------------------------------------

class TestDrawGeomLineString:
    def test_draws_line(self):
        img, draw = _make_canvas()
        renderer.draw_geom(draw, _sf_line(), 100, 100, outline=(255, 0, 0), line_width=2)
        assert _any_red(img), "expected red pixels along line"

    def test_single_point_line_does_not_raise(self):
        _, draw = _make_canvas()
        lat_mid = (renderer.SF_BOUNDS["lat_min"] + renderer.SF_BOUNDS["lat_max"]) / 2
        lon_mid = (renderer.SF_BOUNDS["lon_min"] + renderer.SF_BOUNDS["lon_max"]) / 2
        line = LineString([(lon_mid, lat_mid)])
        renderer.draw_geom(draw, line, 100, 100, outline="red")


# ---------------------------------------------------------------------------
# draw_geom — Multi* types
# ---------------------------------------------------------------------------

class TestDrawGeomMulti:
    def test_multipolygon_fills_both_parts(self):
        img, draw = _make_canvas()
        mp = MultiPolygon([_sf_box(0.002), _sf_box(0.001)])
        renderer.draw_geom(draw, mp, 100, 100, fill="red")
        assert _any_red(img)

    def test_multilinestring_draws_all_segments(self):
        img, draw = _make_canvas()
        mls = MultiLineString([_sf_line(), _sf_line()])
        renderer.draw_geom(draw, mls, 100, 100, outline=(255, 0, 0), line_width=2)
        assert _any_red(img)

    def test_geometry_collection_handles_mixed_types(self):
        _, draw = _make_canvas()
        gc = GeometryCollection([_sf_box(), _sf_line(), Point(0, 0)])
        renderer.draw_geom(draw, gc, 100, 100, fill="red", outline="blue")
```

- [ ] **Step 2: Run tests — expect NameError or AttributeError (draw_geom doesn't exist yet)**

```bash
.venv/bin/pytest tests/test_renderer.py -v 2>&1 | head -20
```

Expected: `AttributeError: module 'renderer' has no attribute 'draw_geom'`

---

## Task 6: Implement draw_geom() in renderer.py

**Files:**
- Modify: `renderer.py` (add `draw_geom`, add `shapely` import)

- [ ] **Step 1: Add shapely import at top of renderer.py**

In `renderer.py`, after the existing imports, add:

```python
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPolygon,
    Polygon,
)
```

- [ ] **Step 2: Add draw_geom() function to renderer.py**

Add this function after the `draw_dashed_line()` function (around line 276), before the `# Render` section:

```python
def draw_geom(
    draw: ImageDraw.ImageDraw,
    geom,
    width: int,
    height: int,
    fill=None,
    outline=None,
    line_width: int = 1,
) -> None:
    """Project a Shapely geometry onto the Pillow canvas via project().

    Handles Polygon, MultiPolygon, LineString, MultiLineString, and
    GeometryCollection recursively. Silently ignores None and empty geometries.

    OSMnx geometries use (lon, lat) coordinate order (GIS standard x, y).
    project() expects (lat, lon), so coordinates are swapped on projection.
    """
    if geom is None or geom.is_empty:
        return

    gtype = geom.geom_type

    if gtype == "Polygon":
        pts = [project(lat, lon, width, height) for lon, lat in geom.exterior.coords]
        if len(pts) >= 3:
            draw.polygon(pts, fill=fill, outline=outline)

    elif gtype == "MultiPolygon":
        for part in geom.geoms:
            draw_geom(draw, part, width, height, fill=fill, outline=outline,
                      line_width=line_width)

    elif gtype == "LineString":
        pts = [project(lat, lon, width, height) for lon, lat in geom.coords]
        if len(pts) >= 2:
            draw.line(pts, fill=outline or fill, width=line_width)

    elif gtype == "MultiLineString":
        for part in geom.geoms:
            draw_geom(draw, part, width, height, fill=fill, outline=outline,
                      line_width=line_width)

    elif gtype == "GeometryCollection":
        for part in geom.geoms:
            draw_geom(draw, part, width, height, fill=fill, outline=outline,
                      line_width=line_width)
    # Points and other types are silently ignored
```

- [ ] **Step 3: Run renderer tests — all should pass**

```bash
.venv/bin/pytest tests/test_renderer.py -v
```

Expected: all 10 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add renderer.py tests/test_renderer.py
git commit -m "feat: add draw_geom() helper to renderer for Shapely geometry projection"
```

---

## Task 7: Swap OSMnx Layers into render()

**Files:**
- Modify: `renderer.py`

This task replaces the three low-fidelity layers and adds streets + inner water. It also removes `BAY_POLYGON_LATLON`, `PARKS`, and `load_geojson_polygons`.

- [ ] **Step 1: Add OSMnx loader imports and module-level data loads**

At the top of `renderer.py`, add after the existing imports:

```python
from geodata.loader import get_boundary, get_parks, get_water, get_streets
```

After the `_BART_STATION_COORDS = _load_bart_station_coords()` line near the bottom of the constants section, add:

```python
# OSMnx geodata — loaded once at import time (warm cache: <1s, cold cache: ~60s)
_osm_boundary = get_boundary()
_osm_parks    = get_parks()
_osm_water    = get_water()
_osm_streets  = get_streets()
```

- [ ] **Step 2: Remove the three old data constants**

Delete these three blocks from renderer.py:

1. `PARKS = [...]` (lines ~59–69, the three park bounding-box lists)
2. `BAY_POLYGON_LATLON = [...]` (lines ~72–93, the hand-drawn bay polygon)
3. `load_geojson_polygons()` function (lines ~218–243)

- [ ] **Step 3: Rewrite render() layers 1–6 to use OSMnx data**

Replace the current layers 3–5 in `render()` with the new OSMnx-powered version. The full updated section (replacing from `# 3. Bay water` through `# 5. Park areas`) becomes:

```python
    # 3. SF land boundary (OSMnx) — drawn over the blue canvas
    for geom in _osm_boundary.geometry:
        draw_geom(draw, geom, width, height, fill="#E8E2D4", outline="#2A2A2A")

    # 4. Parks (OSMnx)
    for geom in _osm_parks.geometry:
        draw_geom(draw, geom, width, height, fill="#C8D8B0")

    # 5. Streets (OSMnx — primary/secondary/tertiary, very faint)
    street_color = hex_to_rgb("#C8BFA8")
    for geom in _osm_streets.geometry:
        draw_geom(draw, geom, width, height, outline=street_color, line_width=1)

    # 5b. Inland water bodies (OSMnx — Stow Lake, Mountain Lake, etc.)
    for geom in _osm_water.geometry:
        draw_geom(draw, geom, width, height, fill="#D4E8F0")
```

Also update layer 1 (background) from the current bay polygon draw to a full-canvas water fill. Replace:

```python
    # 3. Bay water
    bay_pts = [project(lat, lon, width, height) for lat, lon in BAY_POLYGON_LATLON]
    draw.polygon(bay_pts, fill="#D4E8F0")
```

with a full-canvas blue fill (done by changing the initial `Image.new` background colour):

```python
    img = Image.new("RGB", (width, height), "#D4E8F0")   # Bay water blue as base
```

So the full canvas starts blue, then the SF land polygon draws cream on top. This replaces the bay polygon entirely.

- [ ] **Step 4: Update the hatch texture draw call**

After changing `Image.new` to blue, the hatch still draws in rgba mode — no change needed. Confirm the `ImageDraw.Draw(img, "RGBA")` call is unchanged directly after `Image.new`.

- [ ] **Step 5: Run all tests to confirm nothing broke**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests pass (loader tests + renderer unit tests).

- [ ] **Step 6: Smoke test — render with mock data**

```bash
.venv/bin/python -c "
from mock_data import MOCK_VEHICLES
from renderer import render
render(MOCK_VEHICLES)
import os
print('OK — size:', os.path.getsize('output/map.png'), 'bytes')
"
```

Expected: no errors, `output/map.png` written.

- [ ] **Step 7: Inspect output/map.png**

Open or view `output/map.png`. Verify:
- Bay area is blue
- SF land fills cream over the blue
- Golden Gate Park and other parks show as muted green shapes (not bounding boxes)
- Faint street grid visible on the land
- Stow Lake (inside GGP) appears as a small blue polygon
- BART tunnel polyline and station dots still visible
- Muni dashed routes still visible
- Legend and title unchanged

- [ ] **Step 8: Commit**

```bash
git add renderer.py
git commit -m "feat: replace hardcoded base map layers with OSMnx geodata"
```

---

## Task 8: Final Cleanup and Push

**Files:**
- Modify: `.gitignore` (verify `geodata/cache/` is listed)

- [ ] **Step 1: Confirm cache directory is gitignored**

```bash
git status
```

Expected: `geodata/cache/` does NOT appear in untracked files.

If it does appear, confirm `.gitignore` contains `geodata/cache/`.

- [ ] **Step 2: Run full test suite one final time**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Push to GitHub**

```bash
git push origin main
```

---

## Self-Review Notes

- All spec requirements covered: boundary ✓, parks ✓, water ✓, streets ✓, caching ✓, BART KML kept ✓, visual style unchanged ✓
- `draw_geom` coordinate swap documented inline (OSMnx is lon/lat, `project()` takes lat/lon)
- Error handling: `_load_or_fetch` returns empty GeoDataFrame on network error; `render()` loops over empty GeoDataFrame gracefully (zero iterations)
- `geodata/cache/` gitignored in Task 2 before cache is populated in Task 4
- Module-level OSMnx loads mean cold-cache startup is slow — this is expected and documented
