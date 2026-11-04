"""Build ``data/us_places.json``: an offline "City, ST" -> coordinates lookup.

The API resolves plain city inputs ("Chicago, IL", "Austin, Texas") from this
file without any network call, so public geocoders are only needed for street
addresses and landmarks. The file is committed; re-run this only to refresh it
from a newer Census Gazetteer (same files as ``geocode_cities``).
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from stations.geocoding import build_place_index


class Command(BaseCommand):
    help = "Build the offline US place index from Census Gazetteer files."

    def add_arguments(self, parser):
        parser.add_argument("gazetteer", nargs="+",
                            help="Census Gazetteer .txt files, most preferred first.")
        parser.add_argument("--out", default=str(settings.US_PLACES_JSON))

    def handle(self, *args, **opts):
        index = build_place_index([Path(p) for p in opts["gazetteer"]])
        out = Path(opts["out"])
        out.write_text(json.dumps(index, separators=(",", ":"), sort_keys=True),
                       encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Wrote {len(index)} places to {out}"))
