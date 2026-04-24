# Accurate Route Lines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded BART/Muni route line approximations with real geodata — BART from the official KML already on disk, Muni from OSM via OSMnx.

**Architecture:** `geodata/loader.py` gains `get_muni_routes()` (OSMnx + GeoPackage cache, preserving the `ref` column for per-route coloring). `renderer.py` gains `_load_bart_tracks()` (parses the existing KML for Track Centerline LineStrings). Both results are loaded at module level and drawn with the existing `draw_geom()` helper, replacing the station-connecting BART polyline and hardcoded `MUNI_CORRIDORS` waypoints.

**Tech Stack:** Python 3.11, Shapely, GeoPandas, OSMnx, Pillow, xml.etree.ElementTree (stdlib)

---

## File Map

| File | Change |
|---|---|
| `geodata/loader.py` | Add `get_muni_routes()` with its own cache logic (preserves `ref` column) |
| `renderer.py` | Add `_load_bart_tracks(kml_path=None)`, update imports + module-level loads, replace BART + Muni drawing blocks, remove `SF_STATIONS_ORDERED` and `MUNI_CORRIDORS` constants |
| `tests/test_loader.py` | Add `TestGetMuniRoutes` class |
| `tests/test_renderer.py` | Add `TestLoadBartTracks` class |

---

## Task 1: `get_muni_routes()` in `geodata/loader.py`

**Files:**
- Modify: `tests/test_loader.py`
- Modify: `geodata/loader.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_loader.py` (after the `TestErrorHandling` class):

```python
# ---------------------------------------------------------------------------
# get_muni_routes
# ---------------------------------------------------------------------------

class TestGetMuniRoutes:
    def _muni_gdf(self):
        return gpd.GeoDataFrame(
            {
                "geometry": [
                    LineString([(-122.42, 37.77), (-122.40, 37.79)]),
                    LineString([(-122.46, 37.76), (-122.44, 37.75)]),
                ],
                "ref": ["N", "J"],
            },
            crs="EPSG:4326",
        )

    def test_cold_cache_filters_to_known_routes(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))

        mock_gdf = gpd.GeoDataFrame(
            {
                "geometry": [
                    LineString([(-122.42, 37.77), (-122.40, 37.79)]),
                    LineString([(-122.46, 37.76), (-122.44, 37.75)]),
                ],
                "ref": ["N", "X"],   # X is not a Muni line
            },
            crs="EPSG:4326",
        )
        with patch.object(loader.ox, "features_from_place", return_value=mock_gdf):
            result = loader.get_muni_routes()

        assert (tmp_path / "muni_routes.gpkg").exists(), "cache file should be written"
        assert "N" in result["ref"].values
        assert "X" not in result["ref"].values

    def test_warm_cache_skips_osmnx(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))
        self._muni_gdf().to_file(tmp_path / "muni_routes.gpkg", driver="GPKG")

        with patch.object(loader.ox, "features_from_place") as mock_fn:
            result = loader.get_muni_routes()

        mock_fn.assert_not_called()
        assert len(result) == 2
        assert "ref" in result.columns

    def test_returns_empty_on_error(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))

        with patch.object(loader.ox, "features_from_place", side_effect=Exception("network error")):
            result = loader.get_muni_routes()

        assert isinstance(result, gpd.GeoDataFrame)
        assert len(result) == 0
        assert "ref" in result.columns
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/sagan/Documents/Repos/transINK
python -m pytest tests/test_loader.py::TestGetMuniRoutes -v
```

Expected: `AttributeError: module 'geodata.loader' has no attribute 'get_muni_routes'`

- [ ] **Step 3: Implement `get_muni_routes()` in `geodata/loader.py`**

Append after `get_streets()`:

```python
def get_muni_routes() -> gpd.GeoDataFrame:
    """OSM tram route relations in SF, cached to muni_routes.gpkg.

    Columns: geometry (LineString/MultiLineString), ref (Muni route letter).
    Uses its own cache logic (not _load_or_fetch) to preserve the ref column.
    """
    path = _cache_path("muni_routes")
    known_routes = {"J", "K", "L", "M", "N", "T", "F"}
    try:
        if os.path.exists(path):
            logger.debug("Loading muni_routes from cache: %s", path)
            return gpd.read_file(path)
        logger.info("Fetching Muni routes from OSMnx (Overpass API)...")
        os.makedirs(CACHE_DIR, exist_ok=True)
        gdf = ox.features_from_place(PLACE, tags={"route": "tram"})
        if "ref" in gdf.columns:
            gdf = gdf[gdf["ref"].isin(known_routes)].copy()
        else:
            gdf = gdf.copy()
            gdf["ref"] = ""
        out = gdf[["geometry", "ref"]]
        out.to_file(path, driver="GPKG")
        logger.info("Cached muni_routes to %s (%d rows)", path, len(out))
        return out
    except Exception as exc:
        logger.error("Failed to fetch muni_routes: %s — returning empty GeoDataFrame", exc)
        return gpd.GeoDataFrame({"geometry": [], "ref": []}, crs="EPSG:4326")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_loader.py::TestGetMuniRoutes -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
python -m pytest tests/test_loader.py -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add geodata/loader.py tests/test_loader.py
git commit -m "feat: add get_muni_routes() to loader with OSM route data and GeoPackage cache"
```

---

## Task 2: `_load_bart_tracks()` in `renderer.py`

**Files:**
- Modify: `tests/test_renderer.py`
- Modify: `renderer.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_renderer.py` (after `TestDrawGeomMulti`):

```python
# ---------------------------------------------------------------------------
# _load_bart_tracks
# ---------------------------------------------------------------------------

_KML_IN_BOUNDS = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Folder>
  <name>BART Track Centerline</name>
  <Placemark>
    <name>1</name>
    <MultiGeometry>
      <LineString>
        <coordinates>-122.397,37.793,0 -122.402,37.785,0 -122.408,37.779,0</coordinates>
      </LineString>
    </MultiGeometry>
  </Placemark>
</Folder>
</Document>
</kml>"""

_KML_OUT_OF_BOUNDS = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Folder>
  <name>BART Track Centerline</name>
  <Placemark>
    <name>1</name>
    <MultiGeometry>
      <LineString>
        <coordinates>-121.500,37.000,0 -121.600,37.100,0</coordinates>
      </LineString>
    </MultiGeometry>
  </Placemark>
</Folder>
</Document>
</kml>"""


class TestLoadBartTracks:
    def test_missing_kml_returns_empty_list(self, tmp_path):
        result = renderer._load_bart_tracks(str(tmp_path / "nonexistent.kml"))
        assert result == []

    def test_returns_shapely_linestrings_within_sf(self, tmp_path):
        kml_file = tmp_path / "test.kml"
        kml_file.write_text(_KML_IN_BOUNDS)
        result = renderer._load_bart_tracks(str(kml_file))
        assert len(result) == 1
        assert result[0].geom_type == "LineString"

    def test_filters_out_of_bounds_segments(self, tmp_path):
        kml_file = tmp_path / "test.kml"
        kml_file.write_text(_KML_OUT_OF_BOUNDS)
        result = renderer._load_bart_tracks(str(kml_file))
        assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_renderer.py::TestLoadBartTracks -v
```

Expected: `AttributeError: module 'renderer' has no attribute '_load_bart_tracks'`

- [ ] **Step 3: Implement `_load_bart_tracks()` in `renderer.py`**

Add the function immediately after `_fallback_station_coords()` (before the module-level load line):

```python
def _load_bart_tracks(kml_path: str | None = None) -> list:
    """Parse LineString elements from BART KML Track Centerline folder.

    Returns Shapely LineStrings that intersect the SF bounding box.
    Accepts an optional kml_path for testing; defaults to the geodata KML.
    """
    from shapely.geometry import LineString as _LS, box as _box
    if kml_path is None:
        kml_path = os.path.join(os.path.dirname(__file__), "geodata", "bart_stations_tracks.kml")
    if not os.path.exists(kml_path):
        return []
    sf_box = _box(
        SF_BOUNDS["lon_min"], SF_BOUNDS["lat_min"],
        SF_BOUNDS["lon_max"], SF_BOUNDS["lat_max"],
    )
    try:
        tree = ET.parse(kml_path)
        root = tree.getroot()
        ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
        tracks = []
        for folder in root.iter(f"{ns}Folder"):
            if "Track Centerline" not in (folder.findtext(f"{ns}name") or ""):
                continue
            for ls_el in folder.iter(f"{ns}LineString"):
                coord_el = ls_el.find(f"{ns}coordinates")
                if coord_el is None or not coord_el.text:
                    continue
                coords = []
                for triplet in coord_el.text.strip().split():
                    parts = triplet.split(",")
                    if len(parts) >= 2:
                        coords.append((float(parts[0]), float(parts[1])))
                if len(coords) >= 2:
                    geom = _LS(coords)
                    if geom.intersects(sf_box):
                        tracks.append(geom)
        return tracks
    except Exception:
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_renderer.py::TestLoadBartTracks -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Run the full renderer test suite**

```bash
python -m pytest tests/test_renderer.py -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add renderer.py tests/test_renderer.py
git commit -m "feat: add _load_bart_tracks() — parse KML track centerline geometry for SF"
```

---

## Task 3: Wire up new geodata in `renderer.py`

**Files:**
- Modify: `renderer.py`

- [ ] **Step 1: Update the import line and add module-level loads**

In `renderer.py`, change line 16:
```python
# Before
from geodata.loader import get_boundary, get_parks, get_water, get_streets

# After
from geodata.loader import get_boundary, get_parks, get_water, get_streets, get_muni_routes
```

Change the module-level load block (lines 136–143) from:
```python
# Load once at import time
_BART_STATION_COORDS = _load_bart_station_coords()

# OSMnx geodata — loaded once at import time (warm cache: <1s, cold cache: ~60s)
_osm_boundary = get_boundary()
_osm_parks    = get_parks()
_osm_water    = get_water()
_osm_streets  = get_streets()
```

To:
```python
# Load once at import time
_BART_STATION_COORDS = _load_bart_station_coords()
_BART_TRACKS         = _load_bart_tracks()

# OSMnx geodata — loaded once at import time (warm cache: <1s, cold cache: ~60s)
_osm_boundary = get_boundary()
_osm_parks    = get_parks()
_osm_water    = get_water()
_osm_streets  = get_streets()
_muni_routes  = get_muni_routes()
```

- [ ] **Step 2: Remove the two hardcoded constants**

Remove `SF_STATIONS_ORDERED` (line 57):
```python
# DELETE this line:
SF_STATIONS_ORDERED = ["DALY", "BALB", "GLEN", "24TH", "16TH", "CIVC", "POWL", "MONT", "EMBR"]
```

Remove `MUNI_CORRIDORS` (lines 59–68):
```python
# DELETE this entire block:
# Muni light rail route corridors (approximated)
MUNI_CORRIDORS: dict[str, list[tuple[float, float]]] = {
    "N": [(37.7796, -122.3948), ...],
    ...
}
```

- [ ] **Step 3: Replace the BART track drawing block**

In `render()`, replace lines 301–314 (the block that reads `SF_STATIONS_ORDERED` and calls `draw.line(bart_track_pts, ...)`):

```python
# Before:
# 6. BART route lines — one polyline connecting SF stations south→north
# All lines share the SF tunnel; draw a single bold line for each color
# so the map shows all BART routes without overplotting
bart_track_pts = []
for abbr in SF_STATIONS_ORDERED:
    coords = _BART_STATION_COORDS.get(abbr)
    if coords:
        bart_track_pts.append(project(coords[0], coords[1], width, height))

if len(bart_track_pts) >= 2:
    for color_name, hex_color in BART_COLORS.items():
        draw.line(bart_track_pts, fill=hex_color, width=7)
    # Draw again with cream center to give a multi-line "bundle" feel
    draw.line(bart_track_pts, fill="#F5F0E4", width=2)
```

```python
# After:
# 6. BART route lines — real KML track geometry, stacked color bundle
for geom in _BART_TRACKS:
    for hex_color in BART_COLORS.values():
        draw_geom(draw, geom, width, height, outline=hex_to_rgb(hex_color), line_width=7)
    draw_geom(draw, geom, width, height, outline=hex_to_rgb("#F5F0E4"), line_width=2)
```

- [ ] **Step 4: Replace the Muni route drawing block**

In `render()`, replace lines 316–320 (the block that reads `MUNI_CORRIDORS`):

```python
# Before:
# 7. Muni route lines (dashed)
for route_id, corridor in MUNI_CORRIDORS.items():
    pts = [project(lat, lon, width, height) for lat, lon in corridor]
    color_hex = MUNI_COLORS.get(route_id, "#888888")
    draw_dashed_line(draw, pts, hex_to_rgb(color_hex), 4, [12, 3])
```

```python
# After:
# 7. Muni route lines (OSM geometry, per-line color)
for _, row in _muni_routes.iterrows():
    ref = row.get("ref", "")
    color = hex_to_rgb(MUNI_COLORS.get(ref, "#888888"))
    draw_geom(draw, row.geometry, width, height, outline=color, line_width=4)
```

- [ ] **Step 5: Update the station circle loop to not reference `SF_STATIONS_ORDERED`**

In `render()`, replace the station circle block (previously iterates `SF_STATIONS_ORDERED`):

```python
# Before:
# 8. BART station circles (SF only, from KML coords)
station_r = 6
for abbr in SF_STATIONS_ORDERED:
    coords = _BART_STATION_COORDS.get(abbr)
    if not coords:
        continue
    lat, lon = coords
    if not in_bounds(lat, lon):
        continue
    x, y = project(lat, lon, width, height)
    draw.ellipse(
        [(x - station_r, y - station_r), (x + station_r, y + station_r)],
        fill="#F5F0E4",
        outline="#2A2A2A",
        width=2,
    )
```

```python
# After:
# 8. BART station circles (SF only, from KML coords)
station_r = 6
for abbr, coords in _BART_STATION_COORDS.items():
    lat, lon = coords
    if not in_bounds(lat, lon):
        continue
    x, y = project(lat, lon, width, height)
    draw.ellipse(
        [(x - station_r, y - station_r), (x + station_r, y + station_r)],
        fill="#F5F0E4",
        outline="#2A2A2A",
        width=2,
    )
```

- [ ] **Step 6: Update the module docstring**

Replace the docstring at the top of `renderer.py`:

```python
# Before:
"""
Renders a retro-styled SF transit map as a Pillow image.
Saves result to output/map.png.

BART track lines are drawn as polylines connecting SF stations in order
(the tunnel follows a nearly straight path through downtown SF).
Station coordinates are loaded from the official BART KML.
"""
```

```python
# After:
"""
Renders a retro-styled SF transit map as a Pillow image.
Saves result to output/map.png.

BART track geometry is loaded from the official BART KML (Track Centerline folder).
Muni route geometry is fetched from OSM via OSMnx and cached as a GeoPackage.
"""
```

- [ ] **Step 7: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests PASS. (Any `NameError` for `SF_STATIONS_ORDERED` or `MUNI_CORRIDORS` means a reference was missed.)

- [ ] **Step 8: Commit**

```bash
git add renderer.py
git commit -m "feat: replace hardcoded route lines with KML track geometry (BART) and OSM routes (Muni)"
```

---

## Task 4: End-to-end smoke test

**Files:** none changed — verification only

- [ ] **Step 1: Remove stale Muni routes cache if present**

```bash
rm -f /home/sagan/Documents/Repos/transINK/geodata/cache/muni_routes.gpkg
```

- [ ] **Step 2: Run renderer with mock data**

```bash
cd /home/sagan/Documents/Repos/transINK
python - <<'EOF'
from mock_data import MOCK_VEHICLES
import renderer
renderer.render(MOCK_VEHICLES)
print("Rendered OK → output/map.png")
EOF
```

Expected output: logs showing OSMnx fetch for Muni routes, then `Rendered OK → output/map.png`. No tracebacks.

- [ ] **Step 3: Open the output and inspect**

```bash
xdg-open output/map.png
```

Verify:
- BART lines follow curved track geometry through SF (not straight station-to-station segments)
- Muni J/K/L/M/N/T/F lines appear in their correct colors along actual street corridors
- BART station circles still present at correct locations
- Vehicle dots still rendered on top of route lines
- Legend still present bottom-right

- [ ] **Step 4: Second run should use cache**

```bash
python - <<'EOF'
from mock_data import MOCK_VEHICLES
import importlib, renderer
importlib.reload(renderer)
renderer.render(MOCK_VEHICLES)
print("Second run OK")
EOF
```

Expected: no Overpass API network calls in the logs — both runs after the first should load from `.gpkg` cache files.

- [ ] **Step 5: Final commit if any cleanup needed**

```bash
git add -p   # stage only if there were fixup changes
git commit -m "fix: <describe any fixup>" 
```
