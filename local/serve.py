#!/usr/bin/env python3
"""
Local SCE usage analyzer.

Serves app.html on 127.0.0.1 and proxies weather lookups, so the page can
fetch fresh daily highs for whatever dates your spreadsheet actually covers.

    python serve.py            start it and open a browser
    python serve.py --no-open  start it without opening a browser
    python serve.py --port N   pin a port

Nothing leaves this machine except anonymous weather lookups (a ZIP code and
a date range). Your usage spreadsheet is read in the browser and never sent
anywhere at all.
"""

import argparse
import datetime as dt
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "app.html")
CACHE = os.path.join(HERE, "weather-cache.json")
UA = {"User-Agent": "sce-usage-local/1.0"}

# Measured reanalysis trails real time by a few days; inside this window we
# use the forecast feed instead, and re-fetch it rather than trusting cache.
ARCHIVE_LAG = 5
FORECAST_AHEAD = 15  # the forecast feed rejects anything past today+15

# Fallback climate zones, used only if the ZIP geocoder is unreachable.
ZONES = {
    "900": (33.90, -118.40, "Coastal L.A. & South Bay"), "901": (33.90, -118.40, "Coastal L.A. & South Bay"),
    "902": (33.90, -118.40, "Coastal L.A. & South Bay"), "903": (33.90, -118.40, "Coastal L.A. & South Bay"),
    "904": (33.90, -118.40, "Coastal L.A. & South Bay"), "905": (33.90, -118.40, "Coastal L.A. & South Bay"),
    "906": (33.90, -118.40, "Coastal L.A. & South Bay"), "907": (33.90, -118.40, "Coastal L.A. & South Bay"),
    "908": (33.90, -118.40, "Coastal L.A. & South Bay"),
    "910": (34.15, -118.13, "San Gabriel Valley"), "911": (34.15, -118.13, "San Gabriel Valley"),
    "912": (34.15, -118.13, "San Gabriel Valley"), "918": (34.15, -118.13, "San Gabriel Valley"),
    "913": (34.19, -118.45, "San Fernando Valley"), "914": (34.19, -118.45, "San Fernando Valley"),
    "915": (34.19, -118.45, "San Fernando Valley"), "916": (34.19, -118.45, "San Fernando Valley"),
    "917": (34.05, -117.30, "Inland Empire"), "923": (34.05, -117.30, "Inland Empire"),
    "924": (34.05, -117.30, "Inland Empire"), "925": (34.05, -117.30, "Inland Empire"),
    "919": (32.72, -117.16, "San Diego"), "920": (32.72, -117.16, "San Diego"), "921": (32.72, -117.16, "San Diego"),
    "922": (33.83, -116.55, "Coachella Valley"),
    "926": (33.70, -117.83, "Orange County"), "927": (33.70, -117.83, "Orange County"),
    "928": (33.70, -117.83, "Orange County"),
    "930": (34.20, -119.18, "Ventura & Oxnard"),
    "931": (34.42, -119.70, "Santa Barbara"), "934": (34.42, -119.70, "Santa Barbara"),
    "932": (35.37, -119.02, "Bakersfield"), "933": (35.37, -119.02, "Bakersfield"),
    "935": (35.62, -117.67, "Mojave & Ridgecrest"),
    "936": (36.33, -119.29, "Tulare & Visalia"), "937": (36.33, -119.29, "Tulare & Visalia"),
    "938": (36.33, -119.29, "Tulare & Visalia"),
}

_lock = threading.Lock()


def load_cache():
    try:
        with open(CACHE, "r", encoding="utf-8") as f:
            c = json.load(f)
        c.setdefault("zips", {})
        c.setdefault("days", {})
        return c
    except Exception:
        return {"zips": {}, "days": {}}


def save_cache(c):
    try:
        tmp = CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(c, f)
        os.replace(tmp, CACHE)
    except Exception as e:
        print("  (could not write cache: %s)" % e)


def get_json(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def geocode(zipcode, cache):
    hit = cache["zips"].get(zipcode)
    if hit:
        return hit
    try:
        j = get_json("https://api.zippopotam.us/us/" + zipcode, timeout=15)
        pl = j["places"][0]
        out = {
            "lat": round(float(pl["latitude"]), 4),
            "lon": round(float(pl["longitude"]), 4),
            "name": "%s, %s" % (pl["place name"], pl["state abbreviation"]),
            "exact": True,
        }
    except Exception:
        z = ZONES.get(zipcode[:3])
        if not z:
            return None
        out = {"lat": z[0], "lon": z[1], "name": z[2] + " (approximate)", "exact": False}
    cache["zips"][zipcode] = out
    return out


def iso(d):
    return d.isoformat()


def fetch_range(lat, lon, start, end, endpoint):
    base = ("https://archive-api.open-meteo.com/v1/archive"
            if endpoint == "archive" else "https://api.open-meteo.com/v1/forecast")
    url = (base + "?latitude=%s&longitude=%s&start_date=%s&end_date=%s"
           "&daily=temperature_2m_max,temperature_2m_min&temperature_unit=fahrenheit"
           "&timezone=America%%2FLos_Angeles") % (lat, lon, iso(start), iso(end))
    try:
        d = get_json(url)["daily"]
    except urllib.error.HTTPError as e:
        # The forecast feed refuses a window that reaches too far ahead; pull
        # back to its limit rather than losing the whole request.
        if e.code == 400 and endpoint != "archive":
            capped = dt.date.today() + dt.timedelta(days=FORECAST_AHEAD)
            if end > capped >= start:
                return fetch_range(lat, lon, start, capped, endpoint)
        raise
    out = {}
    for t, hi, lo in zip(d["time"], d["temperature_2m_max"], d["temperature_2m_min"]):
        if hi is not None and lo is not None:
            out[t] = [int(round(hi)), int(round(lo))]
    return out


def weather(zipcode, start_s, end_s):
    with _lock:
        cache = load_cache()
        place = geocode(zipcode, cache)
        if not place:
            save_cache(cache)
            return {"ok": False, "error": "That ZIP code could not be located."}

        key = "%.4f,%.4f" % (place["lat"], place["lon"])
        days = cache["days"].setdefault(key, {})

        start = dt.date.fromisoformat(start_s)
        end = dt.date.fromisoformat(end_s)
        today = dt.date.today()
        end = min(end, today + dt.timedelta(days=FORECAST_AHEAD))
        if end < start:
            return {"ok": False, "error": "Empty date range."}

        settled = today - dt.timedelta(days=ARCHIVE_LAG)
        errors = []

        # Measured history: only fetch days we have never stored.
        arch_end = min(end, settled)
        if start <= arch_end:
            missing = [start + dt.timedelta(days=i)
                       for i in range((arch_end - start).days + 1)
                       if iso(start + dt.timedelta(days=i)) not in days]
            if missing:
                try:
                    got = fetch_range(place["lat"], place["lon"], min(missing), max(missing), "archive")
                    days.update(got)
                except Exception as e:
                    errors.append("history: %s" % e)

        # Recent and near-future days move, so always re-fetch that window.
        fc_start = max(start, settled)
        forecast_from = None
        if fc_start <= end:
            try:
                got = fetch_range(place["lat"], place["lon"], fc_start, end, "forecast")
                days.update(got)
                upcoming = [d for d in got if d > iso(today)]
                if upcoming:
                    forecast_from = min(upcoming)
            except Exception as e:
                errors.append("recent: %s" % e)

        save_cache(cache)

    n = (end - start).days + 1
    hi, lo, have = [], [], 0
    for i in range(n):
        d = iso(start + dt.timedelta(days=i))
        v = days.get(d)
        hi.append(v[0] if v else None)
        lo.append(v[1] if v else None)
        if v:
            have += 1

    if not have:
        return {"ok": False,
                "error": "No weather came back. " + ("; ".join(errors) if errors else "Check your internet connection.")}

    return {"ok": True, "name": place["name"], "exact": place["exact"],
            "lat": place["lat"], "lon": place["lon"],
            "start": iso(start), "hi": hi, "lo": lo,
            "covered": have, "days": n,
            "through": iso(end), "forecastFrom": forecast_from,
            "partial": "; ".join(errors) if errors else None}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if "/api/" in (self.path or ""):
            sys.stdout.write("  %s\n" % (fmt % args))

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)

        if u.path in ("/", "/index.html", "/app.html"):
            try:
                with open(APP, "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            except FileNotFoundError:
                return self._send(500, "app.html is missing from " + HERE, "text/plain; charset=utf-8")

        if u.path == "/api/ping":
            return self._send(200, json.dumps({"ok": True, "version": 1}), "application/json")

        if u.path == "/api/wx":
            z = (q.get("zip", [""])[0] or "").strip()
            s = (q.get("start", [""])[0] or "").strip()
            e = (q.get("end", [""])[0] or "").strip()
            if not (len(z) == 5 and z.isdigit()):
                return self._send(200, json.dumps({"ok": False, "error": "Need a five-digit ZIP."}), "application/json")
            try:
                dt.date.fromisoformat(s); dt.date.fromisoformat(e)
            except Exception:
                return self._send(200, json.dumps({"ok": False, "error": "Bad dates."}), "application/json")
            try:
                res = weather(z, s, e)
            except Exception as ex:
                res = {"ok": False, "error": "Weather lookup failed: %s" % ex}
            return self._send(200, json.dumps(res), "application/json")

        return self._send(404, "Not found", "text/plain; charset=utf-8")


def free_port(preferred):
    for p in [preferred] + list(range(preferred + 1, preferred + 40)):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(APP):
        print("app.html not found next to serve.py (looked in %s)" % HERE)
        return 1

    port = free_port(a.port)
    url = "http://127.0.0.1:%d/" % port
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)

    print("")
    print("  SCE usage analyzer")
    print("  " + url)
    print("")
    print("  Drag your Usage.xlsx onto the page. Weather is fetched for")
    print("  whatever dates the file covers and cached in weather-cache.json.")
    print("  Press Ctrl+C to stop.")
    print("")

    if not a.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
