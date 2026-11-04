from unittest import mock

import requests
from django.core.cache import cache
from django.test import SimpleTestCase

from routes import clients
from routes.exceptions import LocationNotFound, RouteNotFound, UpstreamServiceError


def fake_response(payload, status=200):
    resp = mock.Mock(status_code=status)
    resp.json.return_value = payload
    return resp


NOMINATIM_CHICAGO = [{"lat": "41.8755616", "lon": "-87.6244212",
                      "display_name": "Chicago, Cook County, Illinois, United States"}]


class GeocodeTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_raw_coordinates_skip_the_network(self):
        with mock.patch("routes.clients.requests.get") as get:
            loc = clients.geocode(" 40.71, -74.0 ")
        get.assert_not_called()
        self.assertEqual((loc.lat, loc.lon), (40.71, -74.0))

    def test_coordinates_outside_the_usa_are_rejected(self):
        with self.assertRaises(LocationNotFound):
            clients.geocode("51.5, -0.12")  # London

    def test_result_is_cached(self):
        with mock.patch("routes.clients.requests.get",
                        return_value=fake_response(NOMINATIM_CHICAGO)) as get:
            first = clients.geocode("Chicago, IL")
            second = clients.geocode("chicago,   il")
        self.assertEqual(get.call_count, 1)
        self.assertEqual(first.label, "Chicago, Cook County, Illinois")
        self.assertEqual((second.lat, second.lon), (41.875562, -87.624421))

    def test_not_found(self):
        with mock.patch("routes.clients.requests.get", return_value=fake_response([])):
            with self.assertRaises(LocationNotFound):
                clients.geocode("Nowhereville, ZZ")

    def test_falls_back_to_photon_when_nominatim_is_down(self):
        photon = {"features": [{
            "geometry": {"coordinates": [-87.62, 41.88]},
            "properties": {"countrycode": "US", "name": "Chicago", "state": "Illinois"},
        }]}
        with mock.patch("routes.clients.requests.get",
                        side_effect=[requests.Timeout(), fake_response(photon)]):
            loc = clients.geocode("Chicago")
        self.assertEqual(loc.label, "Chicago, Illinois")

    def test_both_geocoders_down_is_an_upstream_error(self):
        with mock.patch("routes.clients.requests.get", side_effect=requests.ConnectionError()):
            with self.assertRaises(UpstreamServiceError):
                clients.geocode("Chicago")


class RouteTests(SimpleTestCase):
    start = clients.Location("a", "A", 40.0, -100.0)
    finish = clients.Location("b", "B", 41.0, -101.0)

    def setUp(self):
        cache.clear()

    def test_parses_osrm_and_caches(self):
        payload = {"code": "Ok", "routes": [{
            "distance": 160934.4, "duration": 7200,
            "geometry": {"coordinates": [[-100.0, 40.0], [-101.0, 41.0]]},
        }]}
        with mock.patch("routes.clients.requests.get", return_value=fake_response(payload)) as get:
            route = clients.get_route(self.start, self.finish)
            clients.get_route(self.start, self.finish)
        self.assertEqual(get.call_count, 1)
        self.assertAlmostEqual(route.distance_miles, 100)
        self.assertAlmostEqual(route.duration_hours, 2)
        self.assertEqual(route.coordinates[0], (40.0, -100.0))
        self.assertEqual(route.display_coordinates, [(40.0, -100.0), (41.0, -101.0)])

    def test_no_route(self):
        with mock.patch("routes.clients.requests.get",
                        return_value=fake_response({"code": "NoRoute", "routes": []}, 400)):
            with self.assertRaises(RouteNotFound):
                clients.get_route(self.start, self.finish)

    def test_server_error(self):
        with mock.patch("routes.clients.requests.get", return_value=fake_response({}, 503)):
            with self.assertRaises(UpstreamServiceError):
                clients.get_route(self.start, self.finish)
