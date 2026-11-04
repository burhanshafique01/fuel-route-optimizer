"""Find the stations that lie within a corridor around a route.

Two vectorised passes keep this fast for coast-to-coast routes and the full
station list:

1. A coarse pass against route points every ``COARSE_STEP`` miles discards
   everything that is clearly far away.
2. A fine pass against route points every ``FINE_STEP`` miles gives each
   surviving station its distance from the route and its position (mile
   marker) along it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from routes.geo import cumulative_miles, resample
from stations.index import StationIndex

COARSE_STEP = 20.0
FINE_STEP = 1.0
CHUNK = 512
MILES_PER_DEG_LAT = 69.05


@dataclass(frozen=True)
class CorridorStation:
    index: int  # position in StationIndex.stations
    route_mile: float
    offset_miles: float


def _nearest(route_lat, route_lon, st_lat, st_lon):
    """For each station: (min distance in miles, index of nearest route point).

    Uses a local equirectangular projection (scaled by the cosine of each
    route point's latitude), which is accurate to well under 1% at the
    corridor distances involved and much cheaper than haversine.
    """
    r_y = (route_lat * MILES_PER_DEG_LAT).astype(np.float32)
    r_x = (route_lon * MILES_PER_DEG_LAT).astype(np.float32)
    r_cos = np.cos(np.radians(route_lat)).astype(np.float32)
    s_y = (st_lat * MILES_PER_DEG_LAT).astype(np.float32)
    s_x = (st_lon * MILES_PER_DEG_LAT).astype(np.float32)
    best_d = np.empty(len(st_lat))
    best_i = np.empty(len(st_lat), dtype=int)
    for s in range(0, len(st_lat), CHUNK):
        dy = s_y[s:s + CHUNK, None] - r_y[None, :]
        dx = (s_x[s:s + CHUNK, None] - r_x[None, :]) * r_cos[None, :]
        d2 = dx * dx + dy * dy
        idx = np.argmin(d2, axis=1)
        best_i[s:s + CHUNK] = idx
        best_d[s:s + CHUNK] = np.sqrt(d2[np.arange(d2.shape[0]), idx])
    return best_d, best_i


def stations_near_route(
    route_coords: list[tuple[float, float]],
    index: StationIndex,
    max_offset_miles: float,
    route_length_miles: float | None = None,
) -> list[CorridorStation]:
    if len(index) == 0 or len(route_coords) < 2:
        return []
    coords = np.asarray(route_coords, dtype=float)
    lat, lon = coords[:, 0], coords[:, 1]
    cum = cumulative_miles(lat, lon)
    if cum[-1] == 0:
        return []
    # Rescale so mile markers agree with the routing engine's road distance.
    if route_length_miles:
        cum = cum * (route_length_miles / cum[-1])

    # Bounding-box prefilter (1 degree of latitude ~ 69 miles).
    pad_lat = max_offset_miles / 69.0 + 0.5
    pad_lon = pad_lat / max(np.cos(np.radians(np.abs(lat).max())), 0.2)
    in_box = np.flatnonzero(
        (index.lat >= lat.min() - pad_lat) & (index.lat <= lat.max() + pad_lat)
        & (index.lon >= lon.min() - pad_lon) & (index.lon <= lon.max() + pad_lon)
    )
    if in_box.size == 0:
        return []

    c_lat, c_lon, _ = resample(lat, lon, cum, COARSE_STEP)
    d, _ = _nearest(c_lat, c_lon, index.lat[in_box], index.lon[in_box])
    near = in_box[d <= max_offset_miles + COARSE_STEP / 2 + 1]
    if near.size == 0:
        return []

    f_lat, f_lon, f_mile = resample(lat, lon, cum, FINE_STEP)
    d, nearest = _nearest(f_lat, f_lon, index.lat[near], index.lon[near])
    keep = d <= max_offset_miles
    return [
        CorridorStation(index=int(i), route_mile=float(f_mile[k]), offset_miles=float(dd))
        for i, k, dd in zip(near[keep], nearest[keep], d[keep])
    ]
