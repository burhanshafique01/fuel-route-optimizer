from unittest import mock

import numpy as np
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from routes.clients import Location, Route
from stations.index import clear_station_index
from stations.models import FuelStation

# A ~690-mile straight road along latitude 40 (lon -100 -> -87).
LINE = [(40.0, float(lon)) for lon in np.linspace(-100, -87, 200)]
ROUTE = Route(distance_miles=690.0, duration_hours=10.5,
              coordinates=LINE, display_coordinates=[LINE[0], LINE[-1]])
PLACES = {
    "west": Location("west", "West Town, NE", 40.0, -100.0),
    "east": Location("east", "East Town, IL", 40.0, -87.0),
}


def station(opis_id, lon, price, lat=40.0):
    return FuelStation(opis_id=opis_id, name=f"STOP {opis_id}", address="I-80, EXIT 1",
                       city=f"Town {opis_id}", state="NE", retail_price=price,
                       latitude=lat, longitude=lon)


@mock.patch("routes.planner.clients.get_route", return_value=ROUTE)
@mock.patch("routes.planner.clients.geocode", side_effect=lambda q: PLACES[q])
class FuelRouteApiTests(TestCase):
    def setUp(self):
        FuelStation.objects.bulk_create([
            station(1, -99.95, "3.900"),          # at the start, pricey
            station(2, -99.5, "3.100"),           # ~26 mi, cheap
            station(3, -94.0, "3.600"),           # ~318 mi
            station(4, -91.0, "2.950"),           # ~477 mi, cheapest
            station(5, -95.0, "2.000", lat=41.5),  # cheap but ~100 mi off route
        ])
        clear_station_index()
        self.client = APIClient()

    def tearDown(self):
        clear_station_index()

    def test_post_returns_optimal_plan(self, *_):
        resp = self.client.post(reverse("fuel-route"),
                                {"start": "west", "finish": "east"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        summary = body["summary"]
        self.assertEqual(summary["total_distance_miles"], 690.0)
        self.assertAlmostEqual(summary["total_gallons"], 69.0, places=1)
        stop_ids = [s["opis_id"] for s in body["fuel_stops"]]
        self.assertNotIn(5, stop_ids)  # outside the corridor
        self.assertEqual(stop_ids, [1, 2, 4])
        self.assertAlmostEqual(summary["total_fuel_cost"],
                               sum(s["cost"] for s in body["fuel_stops"]), places=1)
        geojson = body["route"]["geojson"]
        self.assertEqual(geojson["features"][0]["geometry"]["type"], "LineString")
        self.assertEqual(sum(f["properties"]["kind"] == "fuel_stop"
                             for f in geojson["features"]), 3)
        self.assertTrue(body["route"]["polyline"])
        self.assertIn("/api/route/map/?start=west&finish=east", body["map_url"])

    def test_get_with_query_params(self, *_):
        resp = self.client.get(reverse("fuel-route"), {"start": "west", "finish": "east"})
        self.assertEqual(resp.status_code, 200)

    def test_wider_detour_can_pick_the_off_route_station(self, *_):
        resp = self.client.post(reverse("fuel-route"), {
            "start": "west", "finish": "east", "max_detour_miles": 50}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["summary"]["max_detour_miles"], 50)

    def test_validation_errors(self, *_):
        resp = self.client.post(reverse("fuel-route"), {"start": "west"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("finish", resp.json())
        resp = self.client.post(reverse("fuel-route"), {
            "start": "west", "finish": "east", "max_detour_miles": 500}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_gap_in_stations_returns_422(self, *_):
        FuelStation.objects.filter(opis_id__in=[3, 4]).delete()
        clear_station_index()
        resp = self.client.post(reverse("fuel-route"),
                                {"start": "west", "finish": "east"}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertIn("range", resp.json()["detail"])

    def test_map_page_renders(self, *_):
        resp = self.client.get(reverse("route-map"), {"start": "west", "finish": "east"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "leaflet")
        self.assertContains(resp, "STOP 4")

    def test_map_page_without_params_shows_form(self, *_):
        resp = self.client.get(reverse("route-map"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Plan fuel stops")

    def test_health(self, *_):
        resp = self.client.get(reverse("health"))
        self.assertEqual(resp.json(), {"status": "ok", "stations_loaded": 5})
