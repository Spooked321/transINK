# transINK — Claude Code Instructions

## Project Overview

Build a server that polls the BART Legacy API and 511 SF Bay API for real-time vehicle positions,
renders them onto a retro-styled map image of San Francisco, and serves that image over HTTP for
a Raspberry Pi + e-ink display to fetch.

**Scope: San Francisco only.** The map covers the SF peninsula. BART trains outside SF (East Bay,
South Bay, peninsula to SFO) are fetched but only rendered if their position falls within the SF
bounding box. Don't try to render the full BART system.

---

## Stack

- **Python 3.11+**
- **Pillow** — map image rendering
- **requests** — API calls
- **Flask** — serves the latest map image over HTTP
- **schedule** — periodic refresh loop
- **python-dotenv** — environment variable management
- **protobuf + gtfs-realtime-bindings** — decoding Muni GTFS-RT feed
- **pykml** — parsing BART's official KML geodata files

---

## Project Structure

```
transINK/
├── CLAUDE.md                        # this file
├── .env                             # API token (never commit this)
├── .env.example                     # template for .env
├── requirements.txt
├── server.py                        # Flask app + schedule loop
├── fetcher_bart.py                  # BART Legacy API polling + position interpolation
├── fetcher_muni.py                  # 511 GTFS-RT polling for Muni
├── renderer.py                      # Pillow map drawing
├── geodata/
│   ├── bart_stations_tracks.kml     # official BART station + track geometry (download once)
│   └── sf.geojson                   # SF peninsula + Bay coastline outline
└── output/
    └── map.png                      # latest rendered image (written by renderer)
```

---

## Environment Variables

`.env.example`:
```
TRANSIT_API_KEY=your_511_token_here
REFRESH_INTERVAL_MINUTES=5
IMAGE_WIDTH=800
IMAGE_HEIGHT=480
```

---

## BART Legacy API (for vehicle positions)

BART does not publish a GTFS-RT vehicle positions feed. Instead, use the BART Legacy API's ETD
(estimated time of departure) endpoint to infer train positions by interpolating between stations.
This is the same approach used by whereisbart.com.

**No API key required** for the Legacy API.

**ETD endpoint:**
```
GET http://api.bart.gov/api/etd.aspx?cmd=etd&orig=ALL&key=MW9S-E7SL-26DU-VV8V&json=y
```

The public demo key `MW9S-E7SL-26DU-VV8V` works for development. Register for your own key at
https://api.bart.gov/docs/overview/index.aspx for production.

**How position interpolation works:**
1. Fetch ETD data for all stations — returns minutes until each train departs each station
2. For each train, identify its current segment: the station it just left and its next station
3. Calculate how far along that segment the train is based on elapsed time vs total travel time
4. Use the KML track geometry to find the actual lat/lon at that point along the line
5. Only plot the train if that lat/lon falls within the SF bounding box

**BART Geospatial Data (official KML):**

Download once and save to `geodata/bart_stations_tracks.kml`:
```
https://www.bart.gov/sites/default/files/2025-12/BART-Stations-tracks-entrances-121025.kmz_.zip
```
The `.kmz` is a zip file — extract it to get the `.kml` inside. This contains:
- Exact lat/lon for every station (Point placemarks)
- Precise track geometry for all lines (LineString placemarks)

Parse with `pykml` or Python's `xml.etree.ElementTree`. Extract station Points and track
LineStrings, build a station lookup dict and a list of track coordinate sequences.

---

## Muni — 511 SF Bay API (for vehicle positions)

**Base URL:** `https://api.511.org/transit`

**Operator ID:** `SF`

**Vehicle positions (GTFS-RT protobuf):**
```
GET https://api.511.org/transit/vehiclepositions?api_key={KEY}&agency=SF
```

**Rate limit:** 60 requests per hour. At 5-minute refresh intervals, that's 12 requests/hour.

**Response format:** GTFS-RT protobuf binary. Parse with `gtfs-realtime-bindings`:

```python
from google.transit import gtfs_realtime_pb2

feed = gtfs_realtime_pb2.FeedMessage()
feed.ParseFromString(response.content)

for entity in feed.entity:
    if entity.HasField('vehicle'):
        v = entity.vehicle
        lat = v.position.latitude
        lon = v.position.longitude
        route_id = v.trip.route_id
        vehicle_id = v.vehicle.id
```

---

## fetcher_bart.py

Responsibilities:
- Call the BART ETD API for all stations
- Interpolate estimated train positions along track segments using the KML geometry
- Filter out any positions outside the SF bounding box before returning
- Cache the KML track geometry at startup — don't reload it on every refresh
- Return a list of vehicle dicts:

```python
{
    "agency": "BA",
    "vehicle_id": "train_POWL_antioch_1",   # synthesized from route + station + index
    "route_id": "YELLOW",
    "lat": 37.7749,
    "lon": -122.4194,
    "timestamp": 1713800000
}
```

- Handle errors gracefully — log and return last known positions on failure

## fetcher_muni.py

Responsibilities:
- Fetch GTFS-RT vehicle positions from 511 for agency `SF`
- Parse protobuf and return vehicle dicts in the same format as above
- Filter out any positions outside the SF bounding box before returning
- Handle errors gracefully — log and return last known positions on failure
- Log how many vehicles were returned each refresh

---

## Known BART API Quirks

These are known limitations of the BART ETD API. Handle them gracefully — don't crash or error,
just skip or degrade silently.

**Missing last leg:** BART does not provide ETA data for the final approach into a terminal station.
Trains on their last segment will have no ETD data and cannot be interpolated. Simply don't render
a dot for these trains — this is expected behaviour, not a bug.

**SF-only scope handles most messiness automatically:** The Antioch/SFO-Millbrae destination
confusion and the East Bay/South Bay data oddities all occur outside SF. By filtering to the SF
bounding box, most of these edge cases are silently ignored. The only BART stations to render are:

```python
SF_BART_STATIONS = [
    "EMBR",  # Embarcadero
    "MONT",  # Montgomery St
    "POWL",  # Powell St
    "CIVC",  # Civic Center/UN Plaza
    "16TH",  # 16th St Mission
    "24TH",  # 24th St Mission
    "GLEN",  # Glen Park
    "BALB",  # Balboa Park
    "DALY",  # Daly City (just outside SF but terminus for some lines)
]
```

**Stale positions:** If a vehicle's last timestamp is more than 2 minutes old, skip it rather than
rendering a potentially misleading position.

---

## renderer.py

Responsibilities:
- Draw the map as a Pillow `Image` object at target resolution (default 800x480)
- Save to `output/map.png`

### Visual Style (retro transit map — match this carefully)

| Element | Style |
|---|---|
| Background | Cream `#F5F0E4` |
| Paper texture | Fine diagonal hatching at low opacity |
| SF coastline/outline | Black stroke `#2A2A2A`, 2px, filled with slightly darker cream `#E8E2D4` |
| Bay water | Muted blue `#D4E8F0` |
| Park areas | Muted green `#C8D8B0` |
| BART lines | Bold, 7px stroke, official colors (see below) |
| Muni lines | Medium, 4px stroke, official colors, dashed `[12, 3]` |
| BART stations | Open circle, cream fill, black stroke 1.5px, radius 6px |
| Vehicle dots (BART) | Filled circle, line color, black stroke 1.5px, radius 5px |
| Vehicle dots (Muni) | Filled circle, line color, black stroke 1.2px, radius 4px |
| Typography | Bold condensed sans — use a bundled font or fall back to a system condensed font |

### BART Line Colors (official)

```python
BART_COLORS = {
    "Yellow":  "#FFD700",   # Antioch
    "Red":     "#E23026",   # Richmond
    "Blue":    "#00A4E4",   # Dublin/Pleasanton
    "Green":   "#3F9142",   # Berryessa/North Concord
    "Orange":  "#FF8000",   # Warm Springs/Richmond
}
```

### Muni Line Colors (official)

```python
MUNI_COLORS = {
    "J": "#F97B0E",   # Church — orange
    "K": "#659833",   # Ingleside — green
    "L": "#C261B9",   # Taraval — purple
    "M": "#E51F23",   # Ocean View — red
    "N": "#2860AE",   # Judah — blue
    "T": "#CA9F2C",   # Third Street — gold
    "F": "#8B4513",   # Market & Wharves — brown
}
```

### SF Bounding Box

```python
SF_BOUNDS = {
    "lat_min": 37.6880,
    "lat_max": 37.8324,
    "lon_min": -122.5170,
    "lon_max": -122.3549,
}

def project(lat, lon, width, height):
    x = (lon - SF_BOUNDS["lon_min"]) / (SF_BOUNDS["lon_max"] - SF_BOUNDS["lon_min"]) * width
    y = (1 - (lat - SF_BOUNDS["lat_min"]) / (SF_BOUNDS["lat_max"] - SF_BOUNDS["lat_min"])) * height
    return int(x), int(y)

def in_bounds(lat, lon):
    return (SF_BOUNDS["lat_min"] <= lat <= SF_BOUNDS["lat_max"] and
            SF_BOUNDS["lon_min"] <= lon <= SF_BOUNDS["lon_max"])
```

---

### Map Layers (draw in this order)

1. Background fill
2. Bay water polygon
3. SF coastline/peninsula outline (from `geodata/sf.geojson`)
4. Park areas (Golden Gate Park, Presidio at minimum)
5. BART route lines — drawn from official KML track LineStrings, clipped to SF bounds
6. Muni route lines — dashed, drawn from 511 GTFS static shapes or approximated
7. BART station circles — drawn from official KML station Points (SF stations only)
8. Vehicle position dots (on top of everything, SF bounds filtered)
9. Legend box
10. Title text + timestamp

### Geodata Sources

**BART tracks and stations — use the official KML:**

Download `geodata/bart_stations_tracks.kml` from BART (see BART Geospatial Data section above).
Unzip the `.kmz` — it's just a zipped `.kml`. Parse with `pykml` or `xml.etree.ElementTree`:
- `<Placemark>` with `<Point>` = station location
- `<Placemark>` with `<LineString>` = track segment

Draw track LineStrings directly using `project()` on each coordinate pair. Clip to SF bounds.

**SF coastline — GeoJSON:**

Download `sf.geojson` from:
`https://github.com/codeforamerica/click_that_hood/blob/master/public/data/san-francisco.geojson`

Render outline using Pillow's `ImageDraw.polygon()`.

**Muni route lines:**

Approximate the main light rail corridors manually for the initial version. Muni GTFS static
shapes are available via 511 if more precision is needed later.

---

## server.py

Responsibilities:
- On startup: run one immediate fetch + render
- Start a background thread running `schedule` to refresh every N minutes
- Flask route `GET /map.png` — serve `output/map.png`
- Flask route `GET /health` — return JSON `{"status": "ok", "last_updated": "<timestamp>", "vehicle_count": N}`
- Flask route `GET /` — simple HTML page showing the map, auto-refreshes every 30 seconds

Run Flask on `0.0.0.0:5000` so it's accessible from the Pi on the local network.

---

## Development Tips

### Test renderer without API calls

Create `mock_data.py` with hardcoded vehicle dicts at known SF coordinates — a few on each BART
line through downtown and a few Muni routes. Pass directly to `renderer.py` to iterate on visuals
without burning API quota.

### Verify KML parsing before anything else

Write a quick script that loads `bart_stations_tracks.kml`, extracts all station Points and track
LineStrings, and prints the coordinates. Confirm you're getting Bay Area lat/lon (~37.x, ~-122.x).

### Check the BART Legacy API (no key needed)

```bash
curl "http://api.bart.gov/api/etd.aspx?cmd=etd&orig=ALL&key=MW9S-E7SL-26DU-VV8V&json=y" \
  | python3 -m json.tool | head -60
```

### Check your 511 token works

```bash
curl "https://api.511.org/transit/vehiclepositions?api_key=YOUR_KEY&agency=SF" --output test.bin
# should return a non-empty binary file
```

---

## Pi Integration (for later)

The Pi will run a simple Python script that:
1. Fetches `http://<your-local-ip>:5000/map.png` every N minutes
2. Dithers the image to match the e-ink display's color palette (Pillow `quantize()`)
3. Pushes it to the Waveshare display using the vendor Python library

This is a separate repo/script — don't build it here yet.

---

## What NOT to build yet

- Pi-side display code
- Auth / API key protection on the Flask server (local network only for now)
- Historical data storage
- Multiple display size support
- Full BART system map beyond SF bounds

Keep it simple. Get a good-looking image rendering with live data first.
