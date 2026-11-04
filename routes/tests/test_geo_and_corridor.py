import numpy as np
from django.test import SimpleTestCase

from routes.corridor import stations_near_route
from routes.geo import cumulative_miles, encode_polyline, haversine_miles, simplify
from stations.index import StationIndex


class GeoTests(SimpleTestCase):
    def test_haversine_new_york_to_los_angeles(self):
        miles = haversine_miles(40.7128, -74.0060, 34.0522, -118.2437)
        self.assertAlmostEqual(float(miles), 2445, delta=5)

    def test_encode_polyline_matches_reference_example(self):
        coords = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
        self.assertEqual(encode_polyline(coords), "_p~iF~ps|U_ulLnnqC_mqNvxq`@")

    def test_simplify_drops_collinear_points(self):
        lat = np.array([0.0, 0.0, 0.0, 1.0])
        lon = np.array([0.0, 1.0, 2.0, 2.0])
        self.assertEqual(list(simplify(lat, lon, 0.01)), [0, 2, 3])

    def test_cumulative_miles(self):
        cum = cumulative_miles(np.array([0.0, 1.0]), np.array([0.0, 0.0]))
        self.assertAlmostEqual(cum[-1], 69.09, delta=0.1)


def make_index(points, prices=None):
    prices = prices or [3.0] * len(points)
    return StationIndex(
        stations=tuple(range(len(points))),
        lat=np.array([p[0] for p in points], dtype=float),
        lon=np.array([p[1] for p in points], dtype=float),
        price=np.array(prices, dtype=float),
    )


class CorridorTests(SimpleTestCase):
    # A straight east-west route along latitude 40 from lon -100 to -95 (~265 mi).
    route = [(40.0, lon) for lon in np.linspace(-100, -95, 6)]

    def test_selects_stations_within_offset_and_orders_by_mile(self):
        index = make_index([
            (40.05, -97.5),  # ~3.5 mi north of the route, middle
            (40.0, -99.9),   # on the route, near the start
            (41.0, -97.5),   # ~69 mi away: excluded
            (40.0, -90.0),   # far past the end: excluded
        ])
        found = sorted(stations_near_route(self.route, index, 10), key=lambda c: c.route_mile)
        self.assertEqual([c.index for c in found], [1, 0])
        self.assertAlmostEqual(found[0].route_mile, 5.3, delta=0.6)
        self.assertAlmostEqual(found[1].route_mile, 132.5, delta=1)
        self.assertAlmostEqual(found[1].offset_miles, 3.45, delta=0.2)

    def test_route_mile_is_scaled_to_road_distance(self):
        index = make_index([(40.0, -97.5)])
        straight = stations_near_route(self.route, index, 5)[0].route_mile
        scaled = stations_near_route(self.route, index, 5, route_length_miles=530)[0].route_mile
        self.assertAlmostEqual(scaled, straight * 2, delta=1)

    def test_empty_inputs(self):
        self.assertEqual(stations_near_route(self.route, make_index([]), 10), [])
        self.assertEqual(stations_near_route([(40, -100)], make_index([(40, -100)]), 10), [])
