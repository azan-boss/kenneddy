from django.contrib.auth.models import User
from django.db import models


class Favourite(models.Model):
    KIND_WISHLIST = "wishlist"
    KIND_LIKE     = "like"

    KIND_CHOICES = [
        (KIND_WISHLIST, "Wishlist"),
        (KIND_LIKE,     "Like"),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favourites")
    dish_slug  = models.SlugField(max_length=200)
    dish_name  = models.CharField(max_length=200)
    dish_image = models.URLField(blank=True)
    price      = models.DecimalField(max_digits=10, decimal_places=2)
    kind       = models.CharField(max_length=20, choices=KIND_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "dish_slug", "kind")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} — {self.kind}: {self.dish_slug}"
