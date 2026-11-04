"""Small, dependency-free geometry helpers (numpy only)."""

from __future__ import annotations

import numpy as np

EARTH_RADIUS_MILES = 3958.7613
METERS_PER_MILE = 1609.344


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance in miles; accepts scalars or broadcastable arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def cumulative_miles(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Distance along a polyline from its first vertex to every vertex."""
    seg = haversine_miles(lat[:-1], lon[:-1], lat[1:], lon[1:])
    return np.concatenate(([0.0], np.cumsum(seg)))


def resample(lat: np.ndarray, lon: np.ndarray, cum: np.ndarray, step_miles: float):
    """Points every ``step_miles`` along the polyline (plus the final vertex)."""
    total = cum[-1]
    marks = np.append(np.arange(0.0, total, step_miles), total)
    return np.interp(marks, cum, lat), np.interp(marks, cum, lon), marks


def simplify(lat: np.ndarray, lon: np.ndarray, tolerance_deg: float) -> np.ndarray:
    """Ramer-Douglas-Peucker; returns the indices of the vertices to keep."""
    n = len(lat)
    if n < 3:
        return np.arange(n)
    pts = np.column_stack((lon, lat))
    keep = np.zeros(n, dtype=bool)
    keep[[0, -1]] = True
    stack = [(0, n - 1)]
    while stack:
        start, end = stack.pop()
        if end - start < 2:
            continue
        a, b = pts[start], pts[end]
        seg = pts[start + 1:end]
        ab = b - a
        norm = np.hypot(*ab)
        if norm == 0:
            dist = np.hypot(*(seg - a).T)
        else:
            dist = np.abs(ab[0] * (seg[:, 1] - a[1]) - ab[1] * (seg[:, 0] - a[0])) / norm
        i = int(np.argmax(dist))
        if dist[i] > tolerance_deg:
            mid = start + 1 + i
            keep[mid] = True
            stack.append((start, mid))
            stack.append((mid, end))
    return np.flatnonzero(keep)


def encode_polyline(coords, precision: int = 5) -> str:
    """Google encoded-polyline for a sequence of ``(lat, lon)`` pairs."""
    factor = 10 ** precision
    out = []
    prev_lat = prev_lon = 0
    for lat, lon in coords:
        ilat, ilon = round(lat * factor), round(lon * factor)
        for delta in (ilat - prev_lat, ilon - prev_lon):
            value = ~(delta << 1) if delta < 0 else delta << 1
            while value >= 0x20:
                out.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            out.append(chr(value + 63))
        prev_lat, prev_lon = ilat, ilon
    return "".join(out)
