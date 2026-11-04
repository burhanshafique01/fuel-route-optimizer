"""Load the OPIS price list into the database using the committed geocode cache.

Runs in about a second and makes no network calls. Duplicate rows for the same
OPIS truck stop are collapsed into one station that keeps the lowest price.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from stations.geocoding import city_key, load_cache, read_price_list
from stations.index import clear_station_index
from stations.models import FuelStation


class Command(BaseCommand):
    help = "Load fuel stations from the CSV price list and the city geocode cache."

    def add_arguments(self, parser):
        parser.add_argument("--csv", default=str(settings.FUEL_PRICES_CSV))
        parser.add_argument("--cache", default=str(settings.CITY_GEOCODES_JSON))

    def handle(self, *args, **opts):
        rows = read_price_list(Path(opts["csv"]))
        geocodes = load_cache(Path(opts["cache"]))

        by_id = {}
        for row in rows:
            current = by_id.get(row.opis_id)
            if current is None or row.price < current.price:
                by_id[row.opis_id] = row

        stations = []
        for row in by_id.values():
            coords = geocodes.get(city_key(row.city, row.state))
            stations.append(
                FuelStation(
                    opis_id=row.opis_id,
                    name=row.name,
                    address=row.address,
                    city=row.city.strip().title(),
                    state=row.state,
                    rack_id=row.rack_id,
                    retail_price=round(row.price, 6),
                    latitude=coords[0] if coords else None,
                    longitude=coords[1] if coords else None,
                )
            )

        with transaction.atomic():
            FuelStation.objects.all().delete()
            FuelStation.objects.bulk_create(stations, batch_size=1000)
        clear_station_index()

        located = sum(1 for s in stations if s.latitude is not None)
        self.stdout.write(self.style.SUCCESS(
            f"Loaded {len(stations)} stations from {len(rows)} US rows "
            f"({located} geocoded, {len(stations) - located} without coordinates)."
        ))
