"""Offline city-level geocoding for the fuel price list.

The price list only has a highway/exit description, a city and a state, so
each station is placed at its city's centroid. Every distinct ``(city, state)``
pair is resolved once and cached in ``data/city_geocodes.json``, which is
committed to the repository; API requests never geocode stations.

Sources, in order of preference:

1. US Census Bureau Gazetteer, places (cities, towns, villages, CDPs).
2. US Census Bureau Gazetteer, county subdivisions (New England towns,
   townships), for names that are not a Census place.
3. OpenStreetMap Nominatim (1 request/second) for whatever is still missing.
"""

from __future__ import annotations

import csv
import json
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "fuel-route-optimizer/1.0 (assessment project)"

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}

# Legal/statistical area suffixes the Gazetteer appends to names.
_LSAD = re.compile(
    r"^(?P<name>.*?)\s+(city and borough|consolidated government|metropolitan government|"
    r"unified government|urban county|city|town|township|village|borough|CDP|municipality|"
    r"plantation|charter township|gore|grant|location|purchase|CCD|UT)"
    r"(\s*\(balance\))?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class StationRow:
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    rack_id: int | None
    price: float


def city_key(city: str, state: str) -> str:
    return f"{city.strip().title()}|{state.strip().upper()}"


def normalize_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " and ")
    s = re.sub(r"\bsaint\b|\bst\.", "st", s)
    s = re.sub(r"\bsainte\b|\bste\.", "ste", s)
    s = re.sub(r"\bfort\b|\bft\.", "ft", s)
    s = re.sub(r"\bmount\b|\bmt\.", "mt", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = " ".join(s.split())
    return s.replace(" ", "")  # "De Forest" == "DeForest"


def read_price_list(path: Path) -> list[StationRow]:
    """Parse the OPIS CSV, keeping only rows located in a US state."""
    rows: list[StationRow] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for raw in csv.DictReader(fh):
            state = raw["State"].strip().upper()
            if state not in US_STATES:
                continue  # Canadian provinces are out of scope (USA-only API).
            rack = raw.get("Rack ID", "").strip()
            rows.append(
                StationRow(
                    opis_id=int(raw["OPIS Truckstop ID"]),
                    name=" ".join(raw["Truckstop Name"].split()),
                    address=" ".join(raw["Address"].split()),
                    city=" ".join(raw["City"].split()),
                    state=state,
                    rack_id=int(rack) if rack.isdigit() else None,
                    price=float(raw["Retail Price"]),
                )
            )
    return rows


def load_cache(path: Path) -> dict[str, list[float] | None]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_cache(path: Path, cache: dict[str, list[float] | None]) -> None:
    lines = [f'"{k}": {json.dumps(v)}' for k, v in sorted(cache.items())]
    path.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")


def load_gazetteer(path: Path) -> dict[tuple[str, str], tuple[float, float]]:
    """Map ``(normalized name, state)`` to the internal point of the largest match."""
    best: dict[tuple[str, str], tuple[float, float, float, int]] = {}
    with open(path, encoding="utf-8") as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = [h.strip() for h in next(reader)]
        col = {h: i for i, h in enumerate(header)}
        for raw in reader:
            row = [v.strip() for v in raw]
            state, full = row[col["USPS"]], row[col["NAME"]]
            match = _LSAD.match(full)
            base = match.group("name") if match else full
            # "Athens-Clarke County" / "Nashville-Davidson" also answer to "Athens".
            aliases = [(base, 0), (full, 0), (re.split(r"[-/]", base)[0], 1)]
            if base.lower().endswith(" city"):  # "Boise City" is listed for Boise
                aliases.append((base[:-5], 1))
            lat, lon = float(row[col["INTPTLAT"]]), float(row[col["INTPTLONG"]])
            land = float(row[col["ALAND"]])
            for alias, rank in aliases:
                key = (normalize_name(alias), state)
                current = best.get(key)
                # Prefer exact names over aliases, then the largest land area.
                if current is None or (rank, -land) < (current[3], -current[2]):
                    best[key] = (lat, lon, land, rank)
    return {k: (v[0], v[1]) for k, v in best.items()}


def nominatim_city(city: str, state: str, session: requests.Session | None = None):
    """Return ``[lat, lon]`` from Nominatim, or ``None``. Callers must throttle."""
    http = session or requests.Session()
    resp = http.get(
        NOMINATIM_URL,
        params={"city": city, "state": US_STATES[state], "country": "USA",
                "format": "jsonv2", "limit": 1},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        return None
    return [round(float(results[0]["lat"]), 5), round(float(results[0]["lon"]), 5)]


def build_cache(
    pairs: list[tuple[str, str]],
    gazetteers: list[Path],
    cache: dict[str, list[float] | None],
    use_nominatim: bool = True,
    log=print,
) -> dict[str, list[float] | None]:
    tables = [load_gazetteer(p) for p in gazetteers]
    missing = []
    for city, state in pairs:
        key = city_key(city, state)
        if cache.get(key):
            continue
        norm = normalize_name(city)
        hit = next((t[(norm, state)] for t in tables if (norm, state) in t), None)
        if hit:
            cache[key] = [round(hit[0], 5), round(hit[1], 5)]
        else:
            missing.append((city, state))
    log(f"Gazetteer matched {len(pairs) - len(missing)}/{len(pairs)} cities; "
        f"{len(missing)} left")

    if use_nominatim and missing:
        session = requests.Session()
        for n, (city, state) in enumerate(missing, 1):
            try:
                cache[city_key(city, state)] = nominatim_city(city, state, session)
            except requests.RequestException as exc:
                log(f"  Nominatim failed for {city}, {state}: {exc}")
                cache[city_key(city, state)] = None
            if n % 25 == 0:
                log(f"  Nominatim {n}/{len(missing)}")
            time.sleep(1.1)  # Nominatim usage policy: max 1 request per second.
    else:
        for city, state in missing:
            cache.setdefault(city_key(city, state), None)
    return cache
