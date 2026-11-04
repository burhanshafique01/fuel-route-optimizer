from django.conf import settings
from rest_framework import serializers


class FuelRouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(
        max_length=200, trim_whitespace=True,
        help_text='Start location in the USA: an address, a city ("Chicago, IL") or "lat,lon".',
    )
    finish = serializers.CharField(
        max_length=200, trim_whitespace=True,
        help_text="Finish location in the USA, same formats as start.",
    )
    max_detour_miles = serializers.FloatField(
        required=False,
        min_value=1.0,
        max_value=settings.FUEL_ROUTE["MAX_ALLOWED_DETOUR_MILES"],
        help_text="How far from the route a station may be (default 10 miles).",
    )

    def validate(self, attrs):
        if attrs["start"].lower() == attrs["finish"].lower():
            raise serializers.ValidationError("start and finish must be different locations.")
        return attrs
