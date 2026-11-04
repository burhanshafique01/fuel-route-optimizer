"""Cost-optimal refuelling along a fixed route (the "gas station problem").

The route is reduced to a line from mile 0 to mile ``total_miles``; every
candidate station sits at a position on that line with a price per gallon.

Model
-----
* The tank holds ``range_miles / mpg`` gallons.
* The truck leaves with an empty tank, so it fills up at the first station on
  the route; the few miles driven to reach that station are billed at that
  station's price. It arrives at the destination with an empty tank, which
  means the plan pays for exactly ``total_miles / mpg`` gallons.

Algorithm (greedy, provably optimal for this problem)
-----------------------------------------------------
Standing at station ``i``:

1. If a cheaper station is reachable on the fuel a full tank provides, buy
   just enough to reach the *first* such station and drive there.
2. Otherwise, if the destination is reachable, buy just enough to finish.
3. Otherwise fill the tank and drive to the cheapest station in range.

Fuel is therefore always bought at the cheapest price available for every
mile it covers. Runs in ``O(n * k)`` for ``n`` stations and ``k`` stations
per tank-range window, which is a few milliseconds for a coast-to-coast trip.
"""

from __future__ import annotations

from dataclasses import dataclass, field

EPS = 1e-9


@dataclass(frozen=True)
class Candidate:
    position: float  # miles from the start along the route
    price: float  # USD per gallon
    ref: object = None  # whatever the caller wants back (e.g. a FuelStation)


@dataclass(frozen=True)
class Purchase:
    candidate: Candidate
    gallons: float
    cost: float
    fuel_on_arrival_gallons: float


@dataclass
class FuelPlan:
    purchases: list[Purchase] = field(default_factory=list)

    @property
    def total_gallons(self) -> float:
        return sum(p.gallons for p in self.purchases)

    @property
    def total_cost(self) -> float:
        return sum(p.cost for p in self.purchases)


class InfeasiblePlan(Exception):
    def __init__(self, message: str, gap_start: float, gap_end: float):
        super().__init__(message)
        self.gap_start = gap_start
        self.gap_end = gap_end


def plan_fuel_stops(
    candidates: list[Candidate],
    total_miles: float,
    range_miles: float = 500.0,
    mpg: float = 10.0,
) -> FuelPlan:
    if total_miles <= 0:
        return FuelPlan()
    # Same position: only the cheapest is ever useful.
    stations = sorted(
        (c for c in candidates if -EPS <= c.position <= total_miles + EPS),
        key=lambda c: (c.position, c.price),
    )
    if not stations:
        raise InfeasiblePlan("No fuel stations found along the route.", 0.0, total_miles)

    first = stations[0]
    if first.position > range_miles + EPS:
        raise InfeasiblePlan(
            f"No fuel station within {range_miles:.0f} miles of the start.", 0.0, first.position
        )

    purchases: dict[int, list[float]] = {}  # station index -> [gallons, arrival fuel]
    # Miles driven to reach the first station are paid at its price.
    lead_in = max(first.position, 0.0)
    fuel = 0.0  # miles of fuel in the tank on arrival at the current station
    i = 0
    n = len(stations)
    while True:
        here = stations[i]
        reach = here.position + range_miles
        buy = 0.0

        cheaper = next(
            (j for j in range(i + 1, n)
             if stations[j].position <= reach + EPS and stations[j].price < here.price - EPS),
            None,
        )
        if cheaper is None and stations[i].position + range_miles >= total_miles - EPS:
            # Nothing cheaper before the destination: buy exactly what is needed.
            buy = max(0.0, total_miles - here.position - fuel)
            _record(purchases, i, buy, fuel)
            break

        if cheaper is not None:
            need = stations[cheaper].position - here.position
            buy = max(0.0, need - fuel)
            nxt = cheaper
        else:
            buy = range_miles - fuel
            in_range = [j for j in range(i + 1, n) if stations[j].position <= reach + EPS]
            if not in_range:
                gap_end = stations[i + 1].position if i + 1 < n else total_miles
                raise InfeasiblePlan(
                    f"No fuel station between mile {here.position:.0f} and mile "
                    f"{gap_end:.0f}, which is more than the {range_miles:.0f}-mile range.",
                    here.position,
                    gap_end,
                )
            nxt = min(in_range, key=lambda j: (stations[j].price, -stations[j].position))

        _record(purchases, i, buy, fuel)
        fuel = fuel + buy - (stations[nxt].position - here.position)
        i = nxt

    plan = FuelPlan()
    for idx in sorted(purchases):
        gallons_miles, arrival = purchases[idx]
        if idx == 0:
            gallons_miles += lead_in
        if gallons_miles <= EPS:
            continue
        gallons = gallons_miles / mpg
        cand = stations[idx]
        plan.purchases.append(
            Purchase(
                candidate=cand,
                gallons=gallons,
                cost=gallons * cand.price,
                fuel_on_arrival_gallons=max(arrival, 0.0) / mpg,
            )
        )
    return plan


def _record(purchases: dict, idx: int, miles: float, arrival_fuel: float) -> None:
    entry = purchases.setdefault(idx, [0.0, arrival_fuel])
    entry[0] += miles
