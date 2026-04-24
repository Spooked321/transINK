# Accurate Route Lines — Design Spec

**Date:** 2026-04-23
**Status:** Approved

## Problem

Route lines on the map are inaccurate:

- **BART** — the renderer connects the 9 SF station dots with straight line segments. The official BART KML at `geodata/bart_stations_tracks.kml` already contains real `LineString` track geometry (curved, accurate alignment) but it is never used for drawing.
- **Muni** — routes are 4–6 manually-typed waypoints per line (`MUNI_CORRIDORS` in `renderer.py`), rough approximations of the actual light rail corridors.

## Approach

### BART tracks

Parse the `LineString` elements from the existing `geodata/bart_stations_tracks.kml`. The KML has a single `BART Track Centerline` folder containing a `MultiGeometry` placemark — all BART lines share the same physical track through SF (they run the same Market Street tunnel), so there is no per-line geometry to separate. Filter the LineStrings to those that intersect the SF bounding box, build Shapely `LineString` objects, and draw the stacked color bundle (same visual as today — 5 BART colors drawn on the same path) but following the real curved track geometry instead of straight station-to-station segments.

No new downloads required — the data is already present.

### Muni routes

Add `get_muni_routes()` to `geodata/loader.py`. It queries OSM for tram/light rail route relations within the SF bounding polygon using `ox.features_from_place()` with `tags={"route": "tram"}`. OSM route relations carry a `ref` tag (`J`, `K`, `L`, `M`, `N`, `T`, `F`) which maps directly to `MUNI_COLORS`. Cache result to `geodata/cache/muni_routes.gpkg`, same pattern as parks/water/streets.

## Changes

### `geodata/loader.py`

Add one function:

```python
def get_muni_routes() -> gpd.GeoDataFrame:
    """OSM tram route relations in SF, cached to muni_routes.gpkg.
    Columns: geometry (MultiLineString or LineString), ref (route ID e.g. 'N')."""
```

Same `_load_or_fetch()` caching pattern as `get_parks()`, `get_water()`, `get_streets()`.

### `renderer.py`

**Add** a `_load_bart_tracks()` function (called once at module load time alongside the existing `_load_bart_station_coords()`):

```python
def _load_bart_tracks() -> list[LineString]:
    """Parse LineString elements from BART KML Track Centerline folder.
    Returns Shapely LineStrings that intersect the SF bounding box."""
```

Parse with `xml.etree.ElementTree`. Navigate to the `BART Track Centerline` folder → `MultiGeometry` → each `LineString` → `coordinates`. Build Shapely `LineString((lon, lat), ...)` objects. Keep only those whose bounding box overlaps SF bounds.

**Replace** the BART track drawing block (currently connects station dots in a loop, draws every color on the same path):

```python
# Before (lines ~301-314): connects SF_STATIONS_ORDERED station points
# After: draw stacked color bundle along real KML track geometry
for geom in _BART_TRACKS:
    for color_name, hex_color in BART_COLORS.items():
        draw_geom(draw, geom, width, height, outline=hex_to_rgb(hex_color), line_width=7)
    draw_geom(draw, geom, width, height, outline=hex_to_rgb("#F5F0E4"), line_width=2)
```

**Replace** the Muni route drawing block (currently iterates `MUNI_CORRIDORS`):

```python
# Before: iterate MUNI_CORRIDORS hardcoded waypoints, draw_dashed_line()
# After: iterate muni_routes GeoDataFrame rows, draw_geom() per row
for _, row in _muni_routes.iterrows():
    ref = row.get("ref", "")
    color = hex_to_rgb(MUNI_COLORS.get(ref, "#888888"))
    draw_geom(draw, row.geometry, width, height, outline=color, line_width=4)
```

Dashed rendering: `draw_dashed_line()` can still be used per-segment if desired; alternatively draw solid lines at reduced width (OSM geometry is dense enough that dashing is optional).

**Remove** `MUNI_CORRIDORS` constant and `SF_STATIONS_ORDERED` constant from `renderer.py` (replaced by loaded geodata).

**Module-level load** (alongside existing `_BART_STATION_COORDS`):

```python
_BART_TRACKS = _load_bart_tracks()
_muni_routes = loader.get_muni_routes()
```

## Critical Files

- [geodata/loader.py](geodata/loader.py) — add `get_muni_routes()`
- [renderer.py](renderer.py) — add `_load_bart_tracks()`, replace both route drawing blocks, remove hardcoded constants
- [geodata/bart_stations_tracks.kml](geodata/bart_stations_tracks.kml) — read-only, already present
- [geodata/cache/](geodata/cache/) — `muni_routes.gpkg` will be written here on first run

## Verification

1. Delete `geodata/cache/muni_routes.gpkg` if it exists (force fresh fetch)
2. Run `python renderer.py` (or `python server.py`) — should fetch Muni routes from OSM and cache them
3. Open `output/map.png` — BART lines should follow curved track geometry through SF, distinct per line
4. Open `output/map.png` — Muni J/K/L/M/N/T/F lines should follow actual street corridors (N-Judah along Judah St, L-Taraval along Taraval, etc.)
5. Confirm no regression: vehicle dots still render on top of route lines
6. Second run should load from cache (no OSM network call)
