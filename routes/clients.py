"""Thin, cached clients for the two free external services.

* Nominatim (OpenStreetMap), with Photon (komoot) as a fallback, turns a
  free-text place into coordinates.
* OSRM (public demo server) returns the driving route with full geometry.

A request makes at most three external calls (geocode start, geocode finish,
route) and zero when the results are already cached.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import numpy as np
import requests
from django.conf import settings
from django.core.cache import cache

from routes.exceptions import LocationNotFound, RouteNotFound, UpstreamServiceError
from routes.geo import METERS_PER_MILE, simplify

CACHE_VERSION = "v2"
# ~55 m: keeps returned geometry small while staying faithful to the roads.
DISPLAY_TOLERANCE_DEG = 0.0005
COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")

# Generous bounds around the 50 states, used for raw "lat,lon" input.
US_LAT_RANGE = (18.0, 72.0)
US_LON_RANGE = (-180.0, -65.0)


@dataclass(frozen=True)
class Location:
    query: str
    label: str
    lat: float
    lon: float

    def as_dict(self) -> dict:
        return {"query": self.query, "label": self.label, "lat": self.lat, "lon": self.lon}


@dataclass(frozen=True)
class Route:
    distance_miles: float
    duration_hours: float
    coordinates: list[tuple[float, float]]  # full geometry, (lat, lon)
    display_coordinates: list[tuple[float, float]]  # simplified for responses/maps


def _conf(key):
    return settings.FUEL_ROUTE[key]


def _http_get(url: str, params: dict | None = None, timeout: float | None = None):
    try:
        resp = requests.get(
            url,
            params=params,
            headers={"User-Agent": _conf("USER_AGENT")},
            timeout=timeout or _conf("HTTP_TIMEOUT_SECONDS"),
        )
    except requests.RequestException as exc:
        raise UpstreamServiceError(f"Upstream request failed: {exc.__class__.__name__}") from exc
    if resp.status_code >= 500 or resp.status_code == 429:
        raise UpstreamServiceError(f"Upstream service returned HTTP {resp.status_code}.")
    try:
        return resp.json()
    except ValueError as exc:
        raise UpstreamServiceError("Upstream service returned invalid JSON.") from exc


def _in_us_bounds(lat: float, lon: float) -> bool:
    return US_LAT_RANGE[0] <= lat <= US_LAT_RANGE[1] and US_LON_RANGE[0] <= lon <= US_LON_RANGE[1]


def _label(props: dict) -> str:
    parts = [props.get("name"), props.get("city"), props.get("state")]
    seen, out = set(), []
    for part in parts:
        if part and part not in seen:
            seen.add(part)
            out.append(part)
    return ", ".join(out)


def geocode(query: str) -> Location:
    """Resolve free text (or a ``"lat,lon"`` pair) to a location in the USA."""
    text = " ".join(query.split())
    match = COORD_RE.match(text)
    if match:
        lat, lon = float(match.group(1)), float(match.group(2))
        if not _in_us_bounds(lat, lon):
            raise LocationNotFound(f"Coordinates {lat},{lon} are outside the USA.")
        return Location(query=query, label=f"{lat:.5f}, {lon:.5f}", lat=lat, lon=lon)

    key = f"geocode:{CACHE_VERSION}:" + hashlib.sha1(text.lower().encode()).hexdigest()
    cached = cache.get(key)
    if cached:
        return Location(query=query, **cached)

    errors = []
    for provider in (_nominatim, _photon):
        try:
            found = provider(text)
        except UpstreamServiceError as exc:
            errors.append(str(exc.detail))
            continue
        if found:
            cache.set(key, found)
            return Location(query=query, **found)
        if not errors:
            break  # A healthy provider found nothing; no need to ask another.
    if errors and len(errors) == 2:
        raise UpstreamServiceError("Geocoding services are unavailable: " + " | ".join(errors))
    raise LocationNotFound(f"Could not find '{text}' in the USA.")


def _nominatim(text: str) -> dict | None:
    data = _http_get(
        _conf("NOMINATIM_URL"),
        {"q": text, "format": "jsonv2", "countrycodes": "us", "limit": 5, "addressdetails": 0},
        timeout=_conf("GEOCODER_TIMEOUT_SECONDS"),
    )
    for item in data if isinstance(data, list) else []:
        lat, lon = float(item["lat"]), float(item["lon"])
        if _in_us_bounds(lat, lon):
            label = ", ".join(item.get("display_name", text).split(", ")[:3])
            return {"label": label, "lat": round(lat, 6), "lon": round(lon, 6)}
    return None


def _photon(text: str) -> dict | None:
    data = _http_get(
        _conf("PHOTON_URL"), {"q": text, "limit": 10, "lang": "en"},
        timeout=_conf("GEOCODER_TIMEOUT_SECONDS"),
    )
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        if props.get("countrycode") != "US":
            continue
        lon, lat = feature["geometry"]["coordinates"]
        if _in_us_bounds(lat, lon):
            return {"label": _label(props) or text, "lat": round(lat, 6), "lon": round(lon, 6)}
    return None


def get_route(start: Location, finish: Location) -> Route:
    """Driving route from OSRM in a single call, cached by rounded coordinates."""
    coords = f"{start.lon:.5f},{start.lat:.5f};{finish.lon:.5f},{finish.lat:.5f}"
    key = f"route:{CACHE_VERSION}:{coords}"
    cached = cache.get(key)
    if cached:
        return Route(**cached)

    data = _http_get(
        f"{_conf('OSRM_URL').rstrip('/')}/route/v1/driving/{coords}",
        {"overview": "full", "geometries": "geojson", "alternatives": "false", "steps": "false"},
    )
    code = data.get("code")
    if code in {"NoRoute", "NoSegment"}:
        raise RouteNotFound()
    if code != "Ok" or not data.get("routes"):
        raise UpstreamServiceError(f"Routing service error: {data.get('message') or code}")

    best = data["routes"][0]
    lonlat = np.asarray(best["geometry"]["coordinates"], dtype=float)
    keep = simplify(lonlat[:, 1], lonlat[:, 0], DISPLAY_TOLERANCE_DEG)
    route = {
        "distance_miles": best["distance"] / METERS_PER_MILE,
        "duration_hours": best["duration"] / 3600,
        "coordinates": [(lat, lon) for lon, lat in lonlat.tolist()],
        "display_coordinates": [tuple(pt) for pt in np.round(lonlat[keep][:, ::-1], 5).tolist()],
    }
    cache.set(key, route)
    return Route(**route)
