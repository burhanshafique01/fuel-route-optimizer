import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from stations.geocoding import build_cache, city_key, normalize_name, read_price_list
from stations.models import FuelStation

CSV = """OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price
7,WOODSHED OF BIG CABIN,"I-44, EXIT 283 & US-69",Big Cabin,OK,307,3.00733333
20,PILOT TRAVEL CENTER #1243,"I-8, EXIT 119 & SR-85",Gila Bend,AZ,930,3.899
20,PILOT #1243,"I-8, EXIT 119 & SR-85",Gila Bend,AZ,930,3.799
99,CANADIAN STOP,HWY 1,Calgary,AB,1,1.50
101,NOWHERE STOP,US-1,Ghost Town,TX,2,3.10
"""

GAZETTEER = (
    "USPS\tGEOID\tANSICODE\tNAME\tLSAD\tFUNCSTAT\tALAND\tAWATER\tALAND_SQMI\tAWATER_SQMI"
    "\tINTPTLAT\tINTPTLONG\n"
    "OK\t1\t1\tBig Cabin town\t43\tA\t100\t0\t1\t0\t36.53\t-95.22\n"
    "AZ\t2\t2\tGila Bend town\t43\tA\t100\t0\t1\t0\t32.95\t-112.72\n"
    "ID\t3\t3\tBoise City city\t25\tA\t100\t0\t1\t0\t43.6\t-116.23\n"
)


class LoadStationsTests(TestCase):
    def test_load_dedupes_skips_canada_and_keeps_cheapest(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, cache_path = Path(tmp, "p.csv"), Path(tmp, "g.json")
            csv_path.write_text(CSV, encoding="utf-8")
            cache_path.write_text(json.dumps({
                "Big Cabin|OK": [36.53, -95.22], "Gila Bend|AZ": [32.95, -112.72],
                "Ghost Town|TX": None,
            }), encoding="utf-8")
            call_command("load_stations", csv=str(csv_path), cache=str(cache_path),
                         stdout=StringIO())

        self.assertEqual(FuelStation.objects.count(), 3)
        pilot = FuelStation.objects.get(opis_id=20)
        self.assertEqual(float(pilot.retail_price), 3.799)
        self.assertEqual(pilot.latitude, 32.95)
        self.assertIsNone(FuelStation.objects.get(opis_id=101).latitude)
        self.assertFalse(FuelStation.objects.filter(state="AB").exists())


class GeocodingTests(SimpleTestCase):
    def test_normalize_name(self):
        self.assertEqual(normalize_name("St. Louis"), normalize_name("Saint Louis"))
        self.assertEqual(normalize_name("De Forest"), normalize_name("DeForest"))
        self.assertEqual(normalize_name("Cañon City"), normalize_name("Canon City"))

    def test_build_cache_from_gazetteer(self):
        with tempfile.TemporaryDirectory() as tmp:
            gaz = Path(tmp, "gaz.txt")
            gaz.write_text(GAZETTEER, encoding="utf-8")
            csv_path = Path(tmp, "p.csv")
            csv_path.write_text(CSV, encoding="utf-8")
            pairs = sorted({(r.city, r.state) for r in read_price_list(csv_path)})
            cache = build_cache(pairs + [("Boise", "ID")], [gaz], {},
                                use_nominatim=False, log=lambda *_: None)
        self.assertEqual(cache[city_key("Big Cabin", "OK")], [36.53, -95.22])
        self.assertEqual(cache[city_key("Boise", "ID")], [43.6, -116.23])
        self.assertIsNone(cache[city_key("Ghost Town", "TX")])
        self.assertNotIn(city_key("Calgary", "AB"), cache)
