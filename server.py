"""
Flask server: serves the latest rendered transit map image.
Runs a background scheduler to refresh vehicle positions and re-render.
"""

import logging
import os
import threading
import time
from datetime import datetime

import schedule
from dotenv import load_dotenv
from flask import Flask, jsonify, send_file

import fetcher_bart
import fetcher_muni
import renderer

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

MAP_PATH = os.path.join(os.path.dirname(__file__), "output", "map.png")
REFRESH_INTERVAL = int(os.environ.get("REFRESH_INTERVAL_MINUTES", 5))
IMAGE_WIDTH = int(os.environ.get("IMAGE_WIDTH", 800))
IMAGE_HEIGHT = int(os.environ.get("IMAGE_HEIGHT", 480))

# Shared state (written by scheduler thread, read by Flask threads)
_state_lock = threading.Lock()
_last_updated: str = "never"
_vehicle_count: int = 0


def refresh() -> None:
    global _last_updated, _vehicle_count
    logger.info("Refreshing vehicle positions…")
    try:
        vehicles = fetcher_bart.get_vehicles() + fetcher_muni.get_vehicles()
        renderer.render(vehicles, width=IMAGE_WIDTH, height=IMAGE_HEIGHT)
        with _state_lock:
            _last_updated = datetime.now().isoformat(timespec="seconds")
            _vehicle_count = len(vehicles)
        logger.info("Render complete — %d vehicles, saved to %s", len(vehicles), MAP_PATH)
    except Exception as exc:
        logger.error("Refresh failed: %s", exc)


def _scheduler_loop() -> None:
    schedule.every(REFRESH_INTERVAL).minutes.do(refresh)
    while True:
        schedule.run_pending()
        time.sleep(10)


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@app.route("/map.png")
def serve_map():
    return send_file(MAP_PATH, mimetype="image/png")


@app.route("/health")
def health():
    with _state_lock:
        return jsonify({
            "status": "ok",
            "last_updated": _last_updated,
            "vehicle_count": _vehicle_count,
        })


@app.route("/")
def index():
    with _state_lock:
        ts = _last_updated
        count = _vehicle_count
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="30">
  <title>SF Transit Live</title>
  <style>
    body {{ margin: 0; background: #1a1a1a; display: flex; flex-direction: column;
           align-items: center; justify-content: center; min-height: 100vh; font-family: monospace; }}
    img  {{ max-width: 100%; border: 2px solid #444; }}
    p    {{ color: #888; font-size: 12px; margin-top: 8px; }}
  </style>
</head>
<body>
  <img src="/map.png" alt="SF Transit Live Map">
  <p>Last updated: {ts} &nbsp;|&nbsp; Vehicles: {count} &nbsp;|&nbsp; Auto-refresh: 30s</p>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(os.path.join(os.path.dirname(__file__), "output"), exist_ok=True)

    # Initial render before accepting requests
    refresh()

    # Background scheduler thread
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()

    logger.info("Starting Flask on 0.0.0.0:5000 (refresh every %d min)", REFRESH_INTERVAL)
    app.run(host="0.0.0.0", port=5000, debug=False)
