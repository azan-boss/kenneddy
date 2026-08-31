from rest_framework import serializers

from .models import Favourite


class FavouriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Favourite
        fields = ["id", "dish_slug", "dish_name", "dish_image", "price", "kind", "created_at"]
        read_only_fields = ["id", "created_at"]


class FavouriteMergeItemSerializer(serializers.Serializer):
    """Validates a single item in the merge payload."""
    dish_slug  = serializers.SlugField(max_length=200)
    dish_name  = serializers.CharField(max_length=200)
    dish_image = serializers.URLField(allow_blank=True, default="")
    price      = serializers.DecimalField(max_digits=10, decimal_places=2)
    kind       = serializers.ChoiceField(choices=Favourite.KIND_CHOICES)


class FavouriteMergeSerializer(serializers.Serializer):
    """Accepts a list of favourites to bulk-merge from localStorage on login."""
    items = FavouriteMergeItemSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("items list cannot be empty.")
        return value
