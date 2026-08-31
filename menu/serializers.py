from rest_framework import serializers
from .models import MenuCategory, Dish, DishSize


class DishSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DishSize
        fields = ["id", "size", "price"]


class DishSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    sizes = DishSizeSerializer(many=True, read_only=True)

    class Meta:
        model = Dish
        fields = [
            "id",
            "category",
            "category_name",
            "category_slug",
            "name",
            "slug",
            "tag",
            "description",
            "image_url",
            "base_price",
            "old_price",
            "heat_label",
            "time_label",
            "accent",
            "ribbon",
            "story",
            "ingredients",
            "allergens",
            "serves",
            "weight",
            "calories",
            "spice_level",
            "chef",
            "is_available",
            "is_vegetarian",
            "is_spicy",
            "sizes",
            "created_at",
            "updated_at",
        ]





class MenuCategorySerializer(serializers.ModelSerializer):
    dishes = serializers.SerializerMethodField()

    class Meta:
        model = MenuCategory
        fields = ["id", "name", "slug", "display_order", "is_active", "dishes"]

    def get_dishes(self, obj):
        active_dishes = obj.dishes.filter(is_available=True)
        return DishSerializer(active_dishes, many=True).data



