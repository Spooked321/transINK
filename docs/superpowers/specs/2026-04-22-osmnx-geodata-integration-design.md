# OSMnx Geodata Integration — Design Spec
**Date:** 2026-04-22
**Status:** Approved

---

## Problem

`renderer.py` currently uses three low-fidelity data sources for the base map:
- `geodata/sf.geojson` — SF coastline polygon (manually sourced, not future-proof)
- `BAY_POLYGON_LATLON` — hand-drawn 14-point Bay water polygon (~60% accurate)
- `PARKS` — three axis-aligned bounding boxes approximating Golden Gate Park, Presidio, McLaren Park

These produce a visually rough base map that doesn't scale well if the map is ever cropped or zoomed. OSMnx replaces all three with real OpenStreetMap geometry, fetched once and cached locally.

---

## Goals

- Replace the three low-fidelity data sources with OSMnx geometry
- Add a real street network layer (major roads only, for visual context)
- Cache all OSMnx data as GeoPackage files so Overpass API is only called once
- Keep BART KML rendering, Muni corridor rendering, and all visual styles unchanged
- Support future zoom/crop use cases with precise geometry

## Non-Goals

- Interactive zoom (the output is still a static 800×480 PNG)
- Replacing BART KML station/track data with OSMnx data
- Replacing hardcoded Muni route corridors (future work)
- Automatic cache invalidation (manual delete to refresh)

---

## New File Structure

```
geodata/
├── __init__.py              # new — makes geodata a Python package
├── loader.py                # new — OSMnx fetch + GeoPackage cache
├── cache/                   # new — written at runtime, gitignored
│   ├── boundary.gpkg        # SF land boundary polygon
│   ├── parks.gpkg           # leisure=park polygons
│   ├── water.gpkg           # natural=water polygons (within SF)
│   └── streets.gpkg         # primary/secondary/tertiary road edges
├── bart_stations_tracks.kml # unchanged
└── sf.geojson               # kept as reference, may remove later
```

---

## geodata/loader.py

### Interface

```python
def get_boundary() -> gpd.GeoDataFrame  # SF land polygon (1 row)
def get_parks()    -> gpd.GeoDataFrame  # park Polygon/MultiPolygon rows
def get_water()    -> gpd.GeoDataFrame  # water Polygon/MultiPolygon rows
def get_streets()  -> gpd.GeoDataFrame  # road LineString edge rows
```

### Behaviour

Each function:
1. Checks for `geodata/cache/<name>.gpkg`
2. If found: `gpd.read_file(path)` and return
3. If not found: fetch via OSMnx, save to `.gpkg`, return

### OSMnx Fetch Parameters

```python
PLACE = "San Francisco, California, USA"

# Boundary
ox.geocode_to_gdf(PLACE)

# Parks
ox.features_from_place(PLACE, tags={"leisure": "park"})
# filter to Polygon/MultiPolygon rows only

# Water bodies within SF (Stow Lake, Mountain Lake, etc.)
ox.features_from_place(PLACE, tags={"natural": "water"})
# filter to Polygon/MultiPolygon rows only

# Street network
STREET_FILTER = '["highway"~"primary|secondary|tertiary"]'
G = ox.graph_from_place(PLACE, custom_filter=STREET_FILTER)
gdf = ox.graph_to_gdfs(G, nodes=False)  # edges only
# save geometry column only
```

### Cache Format

GeoPackage (`.gpkg`) via `gdf.to_file(path, driver="GPKG")`. Only the `geometry` column is saved (all OSM attribute columns are dropped before saving).

### Cache Invalidation

Manual only — delete `geodata/cache/` to force a re-fetch on next startup.

### Error Handling

If Overpass API is unavailable and no cache exists: log error and return an empty GeoDataFrame. renderer.py must handle empty GeoDataFrames gracefully (skip the layer).

---

## renderer.py Changes

### New Imports

```python
from geodata.loader import get_boundary, get_parks, get_water, get_streets
from shapely.geometry import (
    Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection
)
```

### Module-Level Data Load

At module level (not inside `render()`), load all four datasets once:

```python
_osm_boundary = get_boundary()
_osm_parks    = get_parks()
_osm_water    = get_water()
_osm_streets  = get_streets()
```

First startup with empty cache: slow (Overpass fetch, ~30–120s). Subsequent startups: fast (GeoPackage load, <1s).

### New Helper: draw_geom()

```python
def draw_geom(
    draw: ImageDraw.ImageDraw,
    geom,               # any Shapely geometry
    width: int,
    height: int,
    fill=None,
    outline=None,
    line_width: int = 1,
) -> None
```

Handles recursively: `Polygon`, `MultiPolygon`, `LineString`, `MultiLineString`, `GeometryCollection`. Uses the existing `project(lat, lon, width, height)` for coordinate projection. Skips any geometry whose bounds don't intersect `SF_BOUNDS`.

### Updated render() Layer Order

| # | Layer | Source | Change |
|---|---|---|---|
| 1 | Full-canvas Bay fill `#D4E8F0` | Hardcoded | **Replaces** `BAY_POLYGON_LATLON` polygon draw |
| 2 | Hatch texture | Hardcoded | Unchanged |
| 3 | SF land boundary | `_osm_boundary` (GeoDataFrame) | **Replaces** `load_geojson_polygons(sf.geojson)` |
| 4 | Parks | `_osm_parks` (GeoDataFrame) | **Replaces** hardcoded `PARKS` rects |
| 5 | Streets | `_osm_streets` (GeoDataFrame) | **New** layer, faint `#C8BFA8`, width=1 |
| 6 | Water within SF | `_osm_water` (GeoDataFrame) | **New** layer (Stow Lake etc.), fill `#D4E8F0` |
| 7 | BART track | KML → `_BART_STATION_COORDS` | Unchanged |
| 8 | Muni routes | Hardcoded `MUNI_CORRIDORS` | Unchanged |
| 9 | BART stations | KML → `_BART_STATION_COORDS` | Unchanged |
| 10 | Vehicle dots | `vehicles` param | Unchanged |
| 11 | Legend + title | Hardcoded | Unchanged |

### Removed from renderer.py

- `BAY_POLYGON_LATLON` constant
- `PARKS` constant
- `load_geojson_polygons()` function (replaced by `draw_geom()` + loader)

### Visual Style (unchanged from CLAUDE.md)

| Element | Color |
|---|---|
| Bay / water fill | `#D4E8F0` |
| SF land | `#E8E2D4` fill, `#2A2A2A` 2px outline |
| Parks | `#C8D8B0` fill |
| Streets | `#C8BFA8`, width=1 (faint) |
| Inner water (Stow Lake etc.) | `#D4E8F0` fill |

---

## requirements.txt Additions

```
osmnx
shapely
```

(`geopandas`, `networkx`, `pyproj` are pulled in transitively.)

---

## .gitignore Addition

```
geodata/cache/
```

---

## Verification Steps

1. `pip install osmnx shapely` — confirm clean install
2. `python -c "from geodata.loader import get_boundary; print(get_boundary())"` — cold cache fetch, confirm geometry is SF land polygon
3. Run same command again — confirm cache hit (fast, no network)
4. `python -c "from mock_data import MOCK_VEHICLES; from renderer import render; render(MOCK_VEHICLES)"` — render with OSMnx layers
5. Inspect `output/map.png` — SF shape should match real geography, parks should show actual park boundaries, major streets visible as faint lines
6. Run `python server.py` — confirm server starts (cold cache prints fetch progress, warm cache starts instantly)
