from urllib.parse import urlencode

from django.shortcuts import render
from django.urls import reverse
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from routes.planner import build_fuel_plan
from routes.serializers import FuelRouteRequestSerializer
from stations.index import get_station_index


class FuelRouteView(APIView):
    """Cheapest fuel plan for a truck driving between two US locations.

    `GET /api/route/?start=New York, NY&finish=Los Angeles, CA` or `POST` the
    same fields as JSON. Optional: `max_detour_miles` (1-50, default 10).
    """

    def get(self, request):
        return self._plan(request, request.query_params)

    def post(self, request):
        return self._plan(request, request.data)

    def _plan(self, request, data):
        serializer = FuelRouteRequestSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data
        result = build_fuel_plan(
            params["start"], params["finish"], params.get("max_detour_miles")
        )
        query = {"start": params["start"], "finish": params["finish"]}
        if params.get("max_detour_miles"):
            query["max_detour_miles"] = params["max_detour_miles"]
        result["map_url"] = request.build_absolute_uri(
            f"{reverse('route-map')}?{urlencode(query)}"
        )
        return Response(result)


class HealthView(APIView):
    def get(self, request):
        return Response({"status": "ok", "stations_loaded": len(get_station_index())})


def route_map(request):
    """HTML page with a Leaflet map of the route and the chosen fuel stops."""
    context = {
        "start": request.GET.get("start", ""),
        "finish": request.GET.get("finish", ""),
        "max_detour_miles": request.GET.get("max_detour_miles", ""),
        "plan": None,
        "error": None,
    }
    if context["start"] and context["finish"]:
        serializer = FuelRouteRequestSerializer(data=request.GET)
        try:
            serializer.is_valid(raise_exception=True)
            p = serializer.validated_data
            context["plan"] = build_fuel_plan(p["start"], p["finish"], p.get("max_detour_miles"))
        except ValidationError as exc:
            context["error"] = _flatten(exc.detail)
        except APIException as exc:
            context["error"] = str(exc.detail)
    status = 400 if context["error"] else 200
    return render(request, "routes/map.html", context, status=status)


def _flatten(detail) -> str:
    if isinstance(detail, dict):
        return "; ".join(f"{k}: {_flatten(v)}" for k, v in detail.items())
    if isinstance(detail, list):
        return " ".join(_flatten(v) for v in detail)
    return str(detail)
