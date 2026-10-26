"""Find map coordinates for each listing so every new resource or event gets a dot automatically.

Lookup order:
1. A `geocodes` cache table in resources.db (created automatically; existing tables are untouched).
2. OpenStreetMap's free Nominatim service for the street address, limited to the Rio Grande Valley.
   Each address is looked up once, then cached, so the service is only called for new listings.
3. The approximate center of the listing's city.
"""

import json
import sqlite3
import time
import urllib.parse
import urllib.request
from contextlib import closing

from database import DB_PATH

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "CommunityConnect-RGV/1.0 (community resource directory)"
# Only accept results inside the Rio Grande Valley / South Texas: west, north, east, south.
VIEWBOX = (-99.6, 27.3, -96.9, 25.7)
MAX_LOOKUPS_PER_RUN = 5  # Nominatim allows about one request per second; the rest finish on later page loads.

CITY_COORDS = {
    "mcallen": (26.2034, -98.2300), "edinburg": (26.3017, -98.1633), "brownsville": (25.9017, -97.4975),
    "harlingen": (26.1906, -97.6961), "mission": (26.2159, -98.3253), "pharr": (26.1948, -98.1836),
    "weslaco": (26.1595, -97.9908), "san juan": (26.1892, -98.1553), "alamo": (26.1834, -98.1231),
    "donna": (26.1704, -98.0519), "mercedes": (26.1498, -97.9136), "san benito": (26.1326, -97.6311),
    "rio grande city": (26.3798, -98.8203), "port isabel": (26.0734, -97.2086), "los fresnos": (26.0717, -97.4764),
    "raymondville": (26.4815, -97.7831), "hidalgo": (26.1003, -98.2631), "penitas": (26.2306, -98.4442),
    "south padre island": (26.1118, -97.1681), "la joya": (26.2470, -98.4814), "palmview": (26.2334, -98.3708),
    "edcouch": (26.2934, -97.9608), "elsa": (26.2934, -97.9930), "progreso": (26.0923, -97.9572),
    "lyford": (26.4123, -97.7900), "roma": (26.4053, -99.0159), "santa rosa": (26.2565, -97.8250),
    "la feria": (26.1592, -97.8236), "combes": (26.2465, -97.7230), "primera": (26.2209, -97.7520),
    "rancho viejo": (25.9898, -97.5550), "laguna vista": (26.1009, -97.2905), "port mansfield": (26.5543, -97.4244),
}


def _connect():
    connection = sqlite3.connect(DB_PATH)
    connection.execute("""CREATE TABLE IF NOT EXISTS geocodes (
        query TEXT PRIMARY KEY, lat REAL, lon REAL)""")
    return connection


def _nominatim(row):
    params = {
        "street": row["address"], "city": row["city"], "state": row["state"], "postalcode": row["zip"],
        "countrycodes": "us", "format": "json", "limit": "1",
        "viewbox": ",".join(str(v) for v in VIEWBOX), "bounded": "1",
    }
    request = urllib.request.Request(f"{NOMINATIM_URL}?{urllib.parse.urlencode(params)}",
                                     headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=6) as response:
        results = json.load(response)
    if results:
        return float(results[0]["lat"]), float(results[0]["lon"])
    return None


def locate_rows(rows):
    """Return {listing id: (lat, lon)} for every listing we can place on the map."""
    found = {}
    lookups = 0
    with closing(_connect()) as connection, connection:
        for row in rows:
            query = f'{row["address"]}, {row["city"]}, {row["state"]} {row["zip"]}'.strip().casefold()
            cached = connection.execute("SELECT lat, lon FROM geocodes WHERE query = ?", (query,)).fetchone()
            if cached is None and lookups < MAX_LOOKUPS_PER_RUN:
                lookups += 1
                try:
                    if lookups > 1:
                        time.sleep(1)  # Nominatim usage policy: at most one request per second.
                    coords = _nominatim(row)
                except (OSError, ValueError, KeyError):
                    coords = "retry"  # Network trouble: don't cache, try again on a later page load.
                    lookups = MAX_LOOKUPS_PER_RUN  # and skip the remaining lookups so the page stays fast.
                if coords != "retry":
                    cached = coords or (None, None)
                    connection.execute("INSERT OR REPLACE INTO geocodes (query, lat, lon) VALUES (?, ?, ?)",
                                       (query, *cached))
            if cached and cached[0] is not None:
                found[row["id"]] = (cached[0], cached[1])
            elif row["city"].strip().casefold() in CITY_COORDS:
                found[row["id"]] = CITY_COORDS[row["city"].strip().casefold()]
    return found
