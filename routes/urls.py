from django.urls import path

from routes import views

urlpatterns = [
    path("route/", views.FuelRouteView.as_view(), name="fuel-route"),
    path("route/map/", views.route_map, name="route-map"),
    path("health/", views.HealthView.as_view(), name="health"),
]
