import socket

from django.apps import AppConfig
from django.conf import settings


class RoutesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "routes"

    def ready(self):
        if settings.FUEL_ROUTE.get("FORCE_IPV4"):
            # On hosts with broken IPv6, every outbound call waits ~20 s for the
            # IPv6 connect to time out before falling back. All the services we
            # use are reachable over IPv4, so resolve IPv4 addresses only.
            import urllib3.util.connection

            urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET
