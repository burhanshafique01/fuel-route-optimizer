"""Glue: geocode -> route -> corridor search -> optimise -> response payload."""

from __future__ import annotations

import time

from django.conf import settings

from routes import clients
from routes.corridor import stations_near_route
from routes.exceptions import NoFeasibleFuelPlan
from routes.geo import encode_polyline
from routes.optimizer import Candidate, InfeasiblePlan, plan_fuel_stops
from stations.index import get_station_index


def build_fuel_plan(start_query: str, finish_query: str, max_detour_miles: float | None = None):
    conf = settings.FUEL_ROUTE
    detour = max_detour_miles or conf["DEFAULT_MAX_DETOUR_MILES"]
    range_miles, mpg = conf["VEHICLE_RANGE_MILES"], conf["VEHICLE_MPG"]
    started = time.perf_counter()

    start = clients.geocode(start_query)
    finish = clients.geocode(finish_query)
    route = clients.get_route(start, finish)

    index = get_station_index()
    corridor = stations_near_route(route.coordinates, index, detour, route.distance_miles)
    candidates = [
        Candidate(position=c.route_mile, price=float(index.price[c.index]), ref=c)
        for c in corridor
    ]
    try:
        plan = plan_fuel_stops(candidates, route.distance_miles, range_miles, mpg)
    except InfeasiblePlan as exc:
        raise NoFeasibleFuelPlan(
            f"{exc} Try a larger max_detour_miles (currently {detour:g})."
        ) from exc

    stops = []
    for n, purchase in enumerate(plan.purchases, start=1):
        cs = purchase.candidate.ref
        station = index.stations[cs.index]
        stops.append({
            "stop_number": n,
            "opis_id": station.opis_id,
            "name": station.name,
            "address": station.address,
            "city": station.city,
            "state": station.state,
            "lat": station.latitude,
            "lon": station.longitude,
            "price_per_gallon": round(float(station.retail_price), 4),
            "route_mile": round(cs.route_mile, 1),
            "distance_from_route_miles": round(cs.offset_miles, 1),
            "fuel_on_arrival_gallons": round(purchase.fuel_on_arrival_gallons, 2),
            "gallons_purchased": round(purchase.gallons, 2),
            "cost": round(purchase.cost, 2),
        })

    simplified = route.display_coordinates

    return {
        "start": start.as_dict(),
        "finish": finish.as_dict(),
        "summary": {
            "total_distance_miles": round(route.distance_miles, 1),
            "estimated_drive_time_hours": round(route.duration_hours, 1),
            "total_fuel_cost": round(plan.total_cost, 2),
            "total_gallons": round(plan.total_gallons, 2),
            "average_price_per_gallon": (
                round(plan.total_cost / plan.total_gallons, 4) if plan.total_gallons else None
            ),
            "number_of_stops": len(stops),
            "vehicle": {"max_range_miles": range_miles, "mpg": mpg,
                        "tank_gallons": range_miles / mpg},
            "max_detour_miles": detour,
            "stations_considered": len(candidates),
            "compute_time_ms": round((time.perf_counter() - started) * 1000, 1),
        },
        "fuel_stops": stops,
        "route": {
            "polyline": encode_polyline(simplified),
            "geojson": _feature_collection(simplified, start, finish, stops),
        },
    }


def _feature_collection(line, start, finish, stops) -> dict:
    def point(lat, lon, props):
        return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props}

    features = [
        {"type": "Feature",
         "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in line]},
         "properties": {"kind": "route"}},
        point(start.lat, start.lon, {"kind": "start", "label": start.label}),
        point(finish.lat, finish.lon, {"kind": "finish", "label": finish.label}),
    ]
    features += [
        point(s["lat"], s["lon"], {"kind": "fuel_stop", **{k: v for k, v in s.items()
                                                          if k not in ("lat", "lon")}})
        for s in stops
    ]
    return {"type": "FeatureCollection", "features": features}
