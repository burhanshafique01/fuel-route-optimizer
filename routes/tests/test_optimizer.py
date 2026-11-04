import random

from django.test import SimpleTestCase

from routes.optimizer import Candidate, InfeasiblePlan, plan_fuel_stops


def brute_force_cost(stations, total, range_miles, mpg):
    """Exact DP over integer fuel levels (miles), used to check the greedy."""
    stations = sorted(stations, key=lambda c: (c.position, c.price))
    nodes = [(c.position, c.price / mpg) for c in stations] + [(total, None)]
    inf = float("inf")
    first_pos, first_price = nodes[0]
    best = [inf] * (range_miles + 1)
    best[0] = first_pos * first_price  # lead-in billed at the first station
    for (pos, price), (nxt, _) in zip(nodes, nodes[1:]):
        dist = int(nxt - pos)
        # Fill from `fuel` up to `target`: cost + (target - fuel) * price. A running
        # minimum of (cost - fuel * price) makes each step O(range).
        after = [inf] * (range_miles + 1)
        running = inf
        for target in range(range_miles + 1):
            running = min(running, best[target] - target * price)
            if target >= dist and running < inf:
                after[target - dist] = running + target * price
        best = after
    return min(best)


class GreedyOptimizerTests(SimpleTestCase):
    def test_short_trip_buys_only_what_it_needs(self):
        plan = plan_fuel_stops([Candidate(0, 3.0)], total_miles=200)
        self.assertEqual(len(plan.purchases), 1)
        self.assertAlmostEqual(plan.total_gallons, 20)
        self.assertAlmostEqual(plan.total_cost, 60)

    def test_buys_just_enough_to_reach_a_cheaper_station(self):
        stations = [Candidate(0, 4.0), Candidate(100, 3.0), Candidate(300, 5.0)]
        plan = plan_fuel_stops(stations, total_miles=550)
        bought = [(p.candidate.position, round(p.gallons, 6)) for p in plan.purchases]
        # 10 gal to reach the cheap station, then fill the tank (50 gal) there,
        # which covers miles 100-550 except nothing more is needed.
        self.assertEqual(bought, [(0, 10.0), (100, 45.0)])
        self.assertAlmostEqual(plan.total_cost, 10 * 4 + 45 * 3)

    def test_fills_up_when_current_station_is_cheapest_in_range(self):
        stations = [Candidate(0, 2.5), Candidate(450, 4.0), Candidate(700, 3.5)]
        plan = plan_fuel_stops(stations, total_miles=900)
        first = plan.purchases[0]
        self.assertAlmostEqual(first.gallons, 50)  # full tank at the cheapest price
        self.assertAlmostEqual(plan.total_gallons, 90)

    def test_lead_in_miles_are_billed_at_the_first_station(self):
        plan = plan_fuel_stops([Candidate(5, 3.0)], total_miles=105)
        self.assertAlmostEqual(plan.total_gallons, 10.5)
        self.assertAlmostEqual(plan.total_cost, 31.5)

    def test_gap_longer_than_range_is_infeasible(self):
        with self.assertRaises(InfeasiblePlan) as ctx:
            plan_fuel_stops([Candidate(0, 3.0), Candidate(600, 3.0)], total_miles=800)
        self.assertEqual(ctx.exception.gap_start, 0)
        self.assertEqual(ctx.exception.gap_end, 600)

    def test_no_stations_is_infeasible(self):
        with self.assertRaises(InfeasiblePlan):
            plan_fuel_stops([], total_miles=50)

    def test_ignores_stations_past_the_destination(self):
        plan = plan_fuel_stops([Candidate(0, 4.0), Candidate(150, 1.0)], total_miles=100)
        self.assertEqual(len(plan.purchases), 1)
        self.assertAlmostEqual(plan.total_cost, 40)

    def test_matches_exact_dynamic_programme_on_random_routes(self):
        rng = random.Random(42)
        for _ in range(300):
            total = rng.randint(50, 2000)
            positions = sorted({0, *(rng.randint(0, total) for _ in range(rng.randint(3, 25)))})
            stations = [Candidate(p, round(rng.uniform(2.7, 4.5), 3)) for p in positions]
            range_miles = rng.choice([100, 250, 500])
            try:
                plan = plan_fuel_stops(stations, total, range_miles, mpg=10)
            except InfeasiblePlan:
                self.assertEqual(brute_force_cost(stations, total, range_miles, 10), float("inf"))
                continue
            expected = brute_force_cost(stations, total, range_miles, 10)
            self.assertAlmostEqual(plan.total_cost, expected, places=6)
            self.assertAlmostEqual(plan.total_gallons, total / 10, places=6)
            for purchase in plan.purchases:
                self.assertLessEqual(purchase.gallons, range_miles / 10 + 1e-6)
