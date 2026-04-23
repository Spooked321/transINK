"""
Mock vehicle data for testing renderer without burning API quota.
Covers representative BART and Muni positions across SF.
"""

import time

MOCK_VEHICLES = [
    # BART - Yellow line (Antioch) — positions in SF tunnel
    {"agency": "BA", "vehicle_id": "ba01", "route_id": "YELLOW", "lat": 37.7794, "lon": -122.4139, "timestamp": int(time.time())},
    {"agency": "BA", "vehicle_id": "ba02", "route_id": "YELLOW", "lat": 37.7651, "lon": -122.4197, "timestamp": int(time.time())},

    # BART - Red line (Richmond)
    {"agency": "BA", "vehicle_id": "ba03", "route_id": "RED", "lat": 37.7849, "lon": -122.4070, "timestamp": int(time.time())},
    {"agency": "BA", "vehicle_id": "ba04", "route_id": "RED", "lat": 37.7522, "lon": -122.4185, "timestamp": int(time.time())},

    # BART - Blue line (Dublin/Pleasanton)
    {"agency": "BA", "vehicle_id": "ba05", "route_id": "BLUE", "lat": 37.7214, "lon": -122.4476, "timestamp": int(time.time())},
    {"agency": "BA", "vehicle_id": "ba06", "route_id": "BLUE", "lat": 37.7331, "lon": -122.4338, "timestamp": int(time.time())},

    # BART - Green line (Berryessa)
    {"agency": "BA", "vehicle_id": "ba07", "route_id": "GREEN", "lat": 37.7894, "lon": -122.4012, "timestamp": int(time.time())},

    # BART - Orange line (Warm Springs/Millbrae)
    {"agency": "BA", "vehicle_id": "ba08", "route_id": "ORANGE", "lat": 37.7929, "lon": -122.3969, "timestamp": int(time.time())},

    # Muni - N Judah
    {"agency": "SF", "vehicle_id": "sf01", "route_id": "N", "lat": 37.7714, "lon": -122.4463, "timestamp": int(time.time())},
    {"agency": "SF", "vehicle_id": "sf02", "route_id": "N", "lat": 37.7640, "lon": -122.4591, "timestamp": int(time.time())},
    {"agency": "SF", "vehicle_id": "sf03", "route_id": "N", "lat": 37.7796, "lon": -122.3948, "timestamp": int(time.time())},

    # Muni - J Church
    {"agency": "SF", "vehicle_id": "sf04", "route_id": "J", "lat": 37.7647, "lon": -122.4283, "timestamp": int(time.time())},
    {"agency": "SF", "vehicle_id": "sf05", "route_id": "J", "lat": 37.7521, "lon": -122.4239, "timestamp": int(time.time())},

    # Muni - L Taraval
    {"agency": "SF", "vehicle_id": "sf06", "route_id": "L", "lat": 37.7440, "lon": -122.4762, "timestamp": int(time.time())},
    {"agency": "SF", "vehicle_id": "sf07", "route_id": "L", "lat": 37.7394, "lon": -122.5024, "timestamp": int(time.time())},

    # Muni - M Ocean View
    {"agency": "SF", "vehicle_id": "sf08", "route_id": "M", "lat": 37.7283, "lon": -122.4523, "timestamp": int(time.time())},

    # Muni - K Ingleside
    {"agency": "SF", "vehicle_id": "sf09", "route_id": "K", "lat": 37.7258, "lon": -122.4520, "timestamp": int(time.time())},

    # Muni - T Third Street
    {"agency": "SF", "vehicle_id": "sf10", "route_id": "T", "lat": 37.7580, "lon": -122.3879, "timestamp": int(time.time())},
    {"agency": "SF", "vehicle_id": "sf11", "route_id": "T", "lat": 37.7143, "lon": -122.4012, "timestamp": int(time.time())},

    # Muni - F Market & Wharves
    {"agency": "SF", "vehicle_id": "sf12", "route_id": "F", "lat": 37.8080, "lon": -122.4156, "timestamp": int(time.time())},
    {"agency": "SF", "vehicle_id": "sf13", "route_id": "F", "lat": 37.7959, "lon": -122.3937, "timestamp": int(time.time())},
]
