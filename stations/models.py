from django.db import models


class FuelStation(models.Model):
    """A truck stop from the OPIS price list, placed at its city's centroid."""

    opis_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=128)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=64)
    state = models.CharField(max_length=2, db_index=True)
    rack_id = models.PositiveIntegerField(null=True, blank=True)
    retail_price = models.DecimalField(max_digits=10, decimal_places=6)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["state", "city", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.city}, {self.state}) ${self.retail_price}"
