"""Geocode every (city, state) in the price list once and cache the result.

This is a one-off, offline step. ``data/city_geocodes.json`` is committed, so
a fresh checkout never needs to run it; re-run it only when the price list
gains new cities. Cities already in the cache are skipped.

Download the two Census Gazetteer files first (public domain), e.g.
https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/
``2024_Gaz_place_national.zip`` and ``2024_Gaz_cousubs_national.zip``.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from stations.geocoding import build_cache, load_cache, read_price_list, save_cache


class Command(BaseCommand):
    help = "Geocode price-list cities (Census Gazetteer + Nominatim) into data/."

    def add_arguments(self, parser):
        parser.add_argument("gazetteer", nargs="+",
                            help="Census Gazetteer .txt files, most preferred first.")
        parser.add_argument("--csv", default=str(settings.FUEL_PRICES_CSV))
        parser.add_argument("--cache", default=str(settings.CITY_GEOCODES_JSON))
        parser.add_argument("--no-nominatim", action="store_true",
                            help="Do not query Nominatim for unmatched cities.")
        parser.add_argument("--retry-missing", action="store_true",
                            help="Retry cities cached as not found.")

    def handle(self, *args, **opts):
        rows = read_price_list(Path(opts["csv"]))
        cache_path = Path(opts["cache"])
        cache = load_cache(cache_path)
        if opts["retry_missing"]:
            cache = {k: v for k, v in cache.items() if v}
        pairs = sorted({(r.city.title(), r.state) for r in rows})
        cache = build_cache(
            pairs,
            [Path(p) for p in opts["gazetteer"]],
            cache,
            use_nominatim=not opts["no_nominatim"],
            log=self.stdout.write,
        )
        save_cache(cache_path, cache)
        missing = sum(1 for v in cache.values() if v is None)
        self.stdout.write(self.style.SUCCESS(
            f"Cached {len(cache)} cities ({missing} not found) in {cache_path}"))
