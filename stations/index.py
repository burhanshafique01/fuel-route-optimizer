"""In-memory, vectorised view of all geocoded stations.

Loaded from the database once per process (a few thousand rows) so that each
route request can search the whole price list with numpy instead of SQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from stations.models import FuelStation


@dataclass(frozen=True)
class StationIndex:
    stations: tuple[FuelStation, ...]
    lat: np.ndarray
    lon: np.ndarray
    price: np.ndarray

    def __len__(self) -> int:
        return len(self.stations)


@lru_cache(maxsize=1)
def get_station_index() -> StationIndex:
    stations = tuple(
        FuelStation.objects.filter(latitude__isnull=False, longitude__isnull=False)
        .order_by("id")
    )
    return StationIndex(
        stations=stations,
        lat=np.array([s.latitude for s in stations], dtype=float),
        lon=np.array([s.longitude for s in stations], dtype=float),
        price=np.array([float(s.retail_price) for s in stations], dtype=float),
    )


def clear_station_index() -> None:
    get_station_index.cache_clear()
