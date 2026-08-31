from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import Favourite


@admin.register(Favourite)
class FavouriteAdmin(admin.ModelAdmin):
    list_display = ("user", "kind_badge", "dish_name", "dish_slug", "price_formatted", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("user__username", "dish_slug", "dish_name")
    ordering = ("-created_at",)

    @admin.display(description="Type")
    def kind_badge(self, obj):
        if obj.kind == Favourite.KIND_WISHLIST:
            return mark_safe('<span style="background: #fff4e6; color: #e8590c; font-weight: 800; padding: 2px 8px; border-radius: 999px; font-size: 0.72rem;">🛍️ Wishlist</span>')
        return mark_safe('<span style="background: #ffe3e3; color: #c92a2a; font-weight: 800; padding: 2px 8px; border-radius: 999px; font-size: 0.72rem;">❤️ Liked Recipe</span>')

    @admin.display(description="Price")
    def price_formatted(self, obj):
        if obj.price is not None:
            return f"Rs {obj.price:,.0f}"
        return "—"
