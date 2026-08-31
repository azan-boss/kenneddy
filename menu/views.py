from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Dish, MenuCategory
from .serializers import DishSerializer, MenuCategorySerializer


class CategoryListView(APIView):
    """
    GET /api/menu/categories/
    Public endpoint: lists active categories with all available dishes and their size options.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        categories = MenuCategory.objects.filter(is_active=True).prefetch_related("dishes__sizes")
        serializer = MenuCategorySerializer(categories, many=True)
        return Response(serializer.data)


class DishListView(APIView):
    """
    GET /api/menu/dishes/?category=<category_slug>
    Public endpoint: lists available dishes, optionally filtered by category slug.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        qs = Dish.objects.filter(is_available=True).select_related("category").prefetch_related("sizes")
        category_slug = request.query_params.get("category")
        if category_slug:
            qs = qs.filter(category__slug=category_slug)
        serializer = DishSerializer(qs, many=True)
        return Response(serializer.data)


class DishDetailView(APIView):
    """
    GET /api/menu/dishes/{slug}/
    Public endpoint: retrieves detailed information and size variants for a single dish.
    """

    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            dish = Dish.objects.select_related("category").prefetch_related("sizes").get(slug=slug, is_available=True)
        except Dish.DoesNotExist:
            return Response({"detail": "Dish nahi mila."}, status=status.HTTP_404_NOT_FOUND)

        serializer = DishSerializer(dish)
        return Response(serializer.data)


class MenuBookView(APIView):
    """
    GET /api/menu/book/
    Public endpoint providing structured menu book data directly from Django DB.
    Ensures zero data mismatch between Django DB and the frontend Menu Book.
    Pizzas are prioritized first.
    """

    authentication_classes = []   # Skip JWT — public endpoint used by ElevenLabs
    permission_classes = [AllowAny]

    def get(self, request):
        # Fetch active categories ordered by display_order
        categories = MenuCategory.objects.filter(is_active=True).order_by("display_order", "name")
        
        # Fetch active dishes with category and size prefetching
        dishes = Dish.objects.filter(is_available=True).select_related("category").prefetch_related("sizes")
        
        # Sort dishes so Pizza category comes first
        dish_list = list(dishes)
        dish_list.sort(key=lambda d: 0 if d.category.slug == "pizza" else 1)
        
        dish_serializer = DishSerializer(dish_list, many=True)
        cat_serializer = MenuCategorySerializer(categories, many=True)

        return Response({
            "brand": {
                "title": "KENNEDY MOON GRILL",
                "tagline": "Takii · Caddy Kitchen",
                "subtitle": "Spicy Pizza Specialist & Charcoal Grills",
                "established": "Est. 2014",
                "chef": "Chef Kennedy & Caddy Kitchen",
            },
            "categories": cat_serializer.data,
            "dishes": dish_serializer.data,
        })

