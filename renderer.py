"""
Renders a retro-styled SF transit map as a Pillow image.
Saves result to output/map.png.

BART track geometry is loaded from the official BART KML (Track Centerline folder).
Muni route geometry is fetched from OSM via OSMnx and cached as a GeoPackage.
"""

import os
import xml.etree.ElementTree as ET
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from geodata.loader import get_boundary, get_parks, get_water, get_streets, get_muni_routes

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SF_BOUNDS = {
    "lat_min": 37.6880,
    "lat_max": 37.8324,
    "lon_min": -122.5880,   # expanded west to Ocean Beach (fixes horizontal scale)
    "lon_max": -122.2840,   # expanded east to Oakland waterfront
}

BART_COLORS = {
    "Yellow": "#FFD700",
    "Red":    "#E23026",
    "Blue":   "#00A4E4",
    "Green":  "#3F9142",
    "Orange": "#FF8000",
}

MUNI_COLORS = {
    "J": "#F97B0E",
    "K": "#659833",
    "L": "#C261B9",
    "M": "#E51F23",
    "N": "#2860AE",
    "T": "#CA9F2C",
    "F": "#8B4513",
}

# route_id from fetcher_bart.py → BART_COLORS key
BART_ROUTE_COLORS: dict[str, str] = {
    "YELLOW": "Yellow",
    "RED":    "Red",
    "BLUE":   "Blue",
    "GREEN":  "Green",
    "ORANGE": "Orange",
}

# ---------------------------------------------------------------------------
# KML loading
# ---------------------------------------------------------------------------

def _load_bart_station_coords() -> dict[str, tuple[float, float]]:
    """Load official BART station lat/lon from KML. Returns abbr → (lat, lon)."""
    kml_path = os.path.join(os.path.dirname(__file__), "geodata", "bart_stations_tracks.kml")

    name_to_abbr: dict[str, str] = {
        "Embarcadero":                          "EMBR",
        "Montgomery St":                         "MONT",
        "Powell St":                             "POWL",
        "Civic Center/UN Plaza":                 "CIVC",
        "16th St/Mission":                       "16TH",
        "24th St/Mission":                       "24TH",
        "Glen Park":                             "GLEN",
        "Balboa Park":                           "BALB",
        "Daly City":                             "DALY",
    }

    if not os.path.exists(kml_path):
        return _fallback_station_coords()

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
                abbr = name_to_abbr.get(pm_name)
                if abbr is None:
                    continue
                pt = pm.find(f".//{ns}Point")
                if pt is None:
                    continue
                coord_el = pt.find(f"{ns}coordinates")
                if coord_el is None or not coord_el.text:
                    continue
                lon_str, lat_str = coord_el.text.strip().split(",")[:2]
                coords[abbr] = (float(lat_str), float(lon_str))

        return coords if len(coords) >= 5 else _fallback_station_coords()
    except Exception:
        return _fallback_station_coords()


def _fallback_station_coords() -> dict[str, tuple[float, float]]:
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


# Load once at import time
_BART_STATION_COORDS = _load_bart_station_coords()
_BART_TRACKS         = _load_bart_tracks()

# OSMnx geodata — loaded once at import time (warm cache: <1s, cold cache: ~60s)
_osm_boundary = get_boundary()
_osm_parks    = get_parks()
_osm_water    = get_water()
_osm_streets  = get_streets()
_muni_routes  = get_muni_routes()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def project(lat: float, lon: float, width: int, height: int) -> tuple[int, int]:
    x = (lon - SF_BOUNDS["lon_min"]) / (SF_BOUNDS["lon_max"] - SF_BOUNDS["lon_min"]) * width
    y = (1 - (lat - SF_BOUNDS["lat_min"]) / (SF_BOUNDS["lat_max"] - SF_BOUNDS["lat_min"])) * height
    return int(x), int(y)


def in_bounds(lat: float, lon: float) -> bool:
    return (SF_BOUNDS["lat_min"] <= lat <= SF_BOUNDS["lat_max"] and
            SF_BOUNDS["lon_min"] <= lon <= SF_BOUNDS["lon_max"])


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]
    if not bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
        ] + candidates

    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_dashed_line(draw: ImageDraw.ImageDraw, pts: list[tuple[int, int]],
                     color: tuple, width: int, dash: list[int]) -> None:
    dash_on, dash_off = dash[0], dash[1]
    total_pattern = dash_on + dash_off
    dist_accum = 0.0

    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        seg_len = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        if seg_len == 0:
            continue
        dx, dy = (x1 - x0) / seg_len, (y1 - y0) / seg_len
        traveled = 0.0

        while traveled < seg_len:
            phase = dist_accum % total_pattern
            remaining_in_phase = (dash_on - phase) if phase < dash_on else (total_pattern - phase)
            remaining_in_seg = seg_len - traveled
            step = min(remaining_in_phase, remaining_in_seg)

            if phase < dash_on:
                sx = x0 + dx * traveled
                sy = y0 + dy * traveled
                ex = sx + dx * step
                ey = sy + dy * step
                draw.line([(int(sx), int(sy)), (int(ex), int(ey))], fill=color, width=width)

            traveled += step
            dist_accum += step


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
            draw.line(pts, fill=outline if outline is not None else fill, width=line_width)

    elif gtype == "MultiLineString":
        for part in geom.geoms:
            draw_geom(draw, part, width, height, fill=fill, outline=outline,
                      line_width=line_width)

    elif gtype == "GeometryCollection":
        for part in geom.geoms:
            draw_geom(draw, part, width, height, fill=fill, outline=outline,
                      line_width=line_width)
    # Points and other types are silently ignored

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render(vehicles: list[dict], width: int = 0, height: int = 0) -> None:
    img = Image.new("RGB", (width, height), "#D4E8F0")   # Bay water blue as base
    draw = ImageDraw.Draw(img, "RGBA")

    # 1. Background already filled above

    # 2. Diagonal hatch texture
    hatch_color = (180, 170, 150, 30)
    step = 8
    for offset in range(-height, width + height, step):
        draw.line([(offset, 0), (offset + height, height)], fill=hatch_color, width=1)

    # 3. SF land boundary (OSMnx)
    for geom in _osm_boundary.geometry:
        draw_geom(draw, geom, width, height, fill="#E8E2D4", outline="#2A2A2A")

    # 4. Parks (OSMnx)
    for geom in _osm_parks.geometry:
        draw_geom(draw, geom, width, height, fill="#C8D8B0")

    # 5. Streets (OSMnx — primary/secondary/tertiary, faint)
    street_color = hex_to_rgb("#C8BFA8")
    for geom in _osm_streets.geometry:
        draw_geom(draw, geom, width, height, outline=street_color, line_width=1)

    # 5b. Inland water bodies (OSMnx — Stow Lake, Mountain Lake, etc.)
    for geom in _osm_water.geometry:
        draw_geom(draw, geom, width, height, fill="#D4E8F0")

    # 6. BART route lines — real KML track geometry, stacked color bundle
    for geom in _BART_TRACKS:
        for hex_color in BART_COLORS.values():
            draw_geom(draw, geom, width, height, outline=hex_to_rgb(hex_color), line_width=7)
        draw_geom(draw, geom, width, height, outline=hex_to_rgb("#F5F0E4"), line_width=2)

    # 7. Muni route lines (OSM geometry, per-line color)
    for _, row in _muni_routes.iterrows():
        ref = row.get("ref", "")
        color = hex_to_rgb(MUNI_COLORS.get(ref, "#888888"))
        draw_geom(draw, row.geometry, width, height, outline=color, line_width=4)

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

    # 9. Vehicle dots
    for v in vehicles:
        lat, lon = v.get("lat"), v.get("lon")
        if lat is None or lon is None:
            continue
        if not in_bounds(lat, lon):
            continue

        x, y = project(lat, lon, width, height)
        agency = v.get("agency", "")
        route_id = v.get("route_id", "")

        if agency == "BA":
            color_name = BART_ROUTE_COLORS.get(route_id, "Yellow")
            dot_color = BART_COLORS[color_name]
            r, stroke_w = 5, 2
        else:
            dot_color = MUNI_COLORS.get(route_id, "#888888")
            r, stroke_w = 4, 2

        draw.ellipse(
            [(x - r, y - r), (x + r, y + r)],
            fill=dot_color,
            outline="#2A2A2A",
            width=stroke_w,
        )

    # 10. Legend box (bottom-right)
    _draw_legend(draw, width, height)

    # 11. Title + timestamp
    title_font = load_font(16, bold=True)
    ts_font = load_font(11)
    draw.text((10, 10), "SF TRANSIT LIVE", fill="#2A2A2A", font=title_font)
    ts = datetime.now().strftime("%H:%M · %b %d")
    draw.text((10, 30), ts, fill="#6A6055", font=ts_font)

    # Save
    out_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(out_dir, exist_ok=True)
    img.save(os.path.join(out_dir, "map.png"))


def _draw_legend(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    font = load_font(9)
    entries = [
        ("BART Yellow", BART_COLORS["Yellow"]),
        ("BART Red",    BART_COLORS["Red"]),
        ("BART Blue",   BART_COLORS["Blue"]),
        ("BART Green",  BART_COLORS["Green"]),
        ("BART Orange", BART_COLORS["Orange"]),
        ("Muni N",  MUNI_COLORS["N"]),
        ("Muni J",  MUNI_COLORS["J"]),
        ("Muni L",  MUNI_COLORS["L"]),
        ("Muni M",  MUNI_COLORS["M"]),
        ("Muni T",  MUNI_COLORS["T"]),
        ("Muni F",  MUNI_COLORS["F"]),
    ]

    row_h = 13
    box_w = 110
    box_h = len(entries) * row_h + 10
    margin = 8
    x0 = width - box_w - margin
    y0 = height - box_h - margin

    draw.rectangle([(x0, y0), (x0 + box_w, y0 + box_h)],
                   fill=(245, 240, 228, 210), outline="#2A2A2A", width=1)

    for i, (label, color) in enumerate(entries):
        y = y0 + 5 + i * row_h
        draw.rectangle([(x0 + 5, y + 2), (x0 + 18, y + 10)],
                       fill=color, outline="#2A2A2A", width=1)
        draw.text((x0 + 22, y), label, fill="#2A2A2A", font=font)
