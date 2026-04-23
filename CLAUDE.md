# SF Transit Live Map — Claude Code Instructions

## Project Overview

Build a server that polls the 511 SF Bay API for real-time BART and Muni vehicle positions, renders them onto a retro-styled map image, and serves that image over HTTP for a Raspberry Pi + e-ink display to fetch.

---

## Stack

- **Python 3.11+**
- **Pillow** — map image rendering
- **requests** — 511 API calls
- **Flask** — serves the latest map image over HTTP
- **schedule** — periodic refresh loop
- **python-dotenv** — environment variable management
- **protobuf + gtfs-realtime-bindings** — decoding GTFS-RT feeds

---

## Project Structure

```
sf-transit-map/
├── CLAUDE.md              # this file
├── .env                   # API token (never commit this)
├── .env.example           # template for .env
├── requirements.txt
├── server.py              # Flask app + schedule loop
├── fetcher.py             # 511 API polling, returns parsed vehicle positions
├── renderer.py            # Pillow map drawing
├── geodata/
│   └── sf.geojson         # SF peninsula + Bay coastline outline
└── output/
    └── map.png            # latest rendered image (written by renderer)
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

## 511 SF Bay API

**Base URL:** `https://api.511.org/transit`

**Operator IDs:**
- BART: `BA`
- Muni (SFMTA): `SF`

**Key endpoints:**

Vehicle positions (GTFS-RT protobuf):
```
GET https://api.511.org/transit/vehiclepositions?api_key={KEY}&agency={OPERATOR_ID}
```

Trip updates:
```
GET https://api.511.org/transit/tripupdates?api_key={KEY}&agency={OPERATOR_ID}
```

**Rate limit:** 60 requests per hour per key. At 5-minute refresh intervals fetching both BART and Muni, that's 24 requests/hour — well within limits.

**Response format:** GTFS-RT protobuf binary. Use `gtfs-realtime-bindings` to parse:

```python
from google.transit import gtfs_realtime_pb2

feed = gtfs_realtime_pb2.FeedMessage()
feed.ParseFromString(response.content)

for entity in feed.entity:
    if entity.HasField('vehicle'):
        v = entity.vehicle
        lat = v.position.latitude
        lon = v.position.longitude
        trip_id = v.trip.trip_id
        route_id = v.trip.route_id
        vehicle_id = v.vehicle.id
```

---

## fetcher.py

Responsibilities:
- Fetch GTFS-RT vehicle positions for both BART and Muni
- Parse protobuf response
- Return a list of vehicle dicts:

```python
{
    "agency": "BA",          # or "SF"
    "vehicle_id": "1234",
    "route_id": "01",        # BART line or Muni route
    "lat": 37.7749,
    "lon": -122.4194,
    "timestamp": 1713800000
}
```

- Handle errors gracefully — if a fetch fails, log the error and return the last successful data (don't crash the render loop)
- Log how many vehicles were returned per agency each refresh

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
| Street grid | Very faint lines `#C8BFA8`, 0.5px, low opacity |
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

Map `route_id` from the GTFS-RT feed to these colors. BART route IDs in the feed look like `"01"`, `"02"` etc — fetch the BART GTFS static feed or hardcode the mapping initially.

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

### Coordinate Projection

Convert lat/lon to pixel coordinates. SF bounding box:

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
```

### Map Layers (draw in this order)

1. Background fill
2. Bay water polygon
3. SF coastline/peninsula outline (load from `geodata/sf.geojson`)
4. Street grid (can be simplified/approximated lines initially)
5. Park areas (Golden Gate Park, Presidio at minimum)
6. BART route lines
7. Muni route lines (dashed)
8. BART station circles
9. Vehicle position dots (on top of everything)
10. Legend box (bottom right or top right)
11. Title text + timestamp

### GeoJSON

For the SF coastline, download `sf.geojson` from:
- https://github.com/codeforamerica/click_that_hood/blob/master/public/data/san-francisco.geojson

Or use OpenStreetMap data via the `osmnx` library if preferred. Render the polygon outline using Pillow's `ImageDraw.polygon()`.

---

## server.py

Responsibilities:
- On startup: run one immediate fetch + render
- Start a background thread running `schedule` to refresh every N minutes
- Flask route `GET /map.png` — serve `output/map.png`
- Flask route `GET /health` — return JSON `{"status": "ok", "last_updated": "<timestamp>", "vehicle_count": N}`
- Flask route `GET /` — simple HTML page showing the current map image (useful for browser preview during development)

```python
# Example Flask routes
@app.route('/map.png')
def serve_map():
    return send_file('output/map.png', mimetype='image/png')

@app.route('/health')
def health():
    return jsonify({"status": "ok", "last_updated": last_updated, "vehicle_count": vehicle_count})
```

Run Flask on `0.0.0.0:5000` so it's accessible from the Pi on the local network.

---

## Development Tips

### Test renderer without API calls

Create `mock_data.py` with a hardcoded list of vehicle dicts at known SF coordinates. Pass this to `renderer.py` directly to iterate on the visual without using API quota.

### Check your token works

```bash
curl "https://api.511.org/transit/vehiclepositions?api_key=YOUR_KEY&agency=BA" --output test.bin
# should return a non-empty binary file
```

### View the map during development

Open `http://localhost:5000` in a browser. It will show the current rendered map and auto-refresh every 30 seconds via a simple meta refresh tag.

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
- Authentication / API key protection on the Flask server (local network only for now)
- Historical data storage
- Multiple display size support

Keep it simple. Get a good-looking image rendering with live data first.
