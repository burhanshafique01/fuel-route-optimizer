from rest_framework import status
from rest_framework.exceptions import APIException


class LocationNotFound(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "location_not_found"
    default_detail = "Could not find that location in the USA."


class RouteNotFound(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "route_not_found"
    default_detail = "No drivable route exists between these locations."


class NoFeasibleFuelPlan(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "no_feasible_fuel_plan"
    default_detail = "The route has a gap between fuel stations longer than the vehicle range."


class UpstreamServiceError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_code = "upstream_error"
    default_detail = "The routing or geocoding service is unavailable. Please retry."
