from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Dish, DishSize, MenuCategory


class DishSizeInline(admin.TabularInline):
    model = DishSize
    extra = 1
    fields = ("size", "price")


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "display_order", "dish_count", "is_active")
    list_editable = ("display_order", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)

    @admin.display(description="Active Dishes")
    def dish_count(self, obj):
        return obj.dishes.filter(is_available=True).count()


@admin.register(Dish)
class DishAdmin(admin.ModelAdmin):
    list_display = (
        "image_thumb",
        "name",
        "category_badge",
        "base_price_formatted",
        "is_available",
        "spicy_badge",
        "veg_badge",
        "updated_at",
    )
    list_filter = ("category", "is_available", "is_spicy", "is_vegetarian")
    list_editable = ("is_available",)
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "description")
    inlines = [DishSizeInline]

    fieldsets = (
        ("🍽️ Dish Details", {
            "fields": (
                ("name", "slug"),
                ("category", "base_price", "old_price"),
                ("tag", "accent", "ribbon"),
                "description",
                "story",
                "image_url",
            )
        }),
        ("✨ Dietary, Spice & Nutrition", {
            "fields": (
                ("is_available", "is_spicy", "is_vegetarian"),
                ("heat_label", "time_label", "spice_level"),
                ("serves", "weight", "calories"),
                ("chef", "ingredients", "allergens"),
            )
        }),
    )

    @admin.display(description="Preview")
    def image_thumb(self, obj):
        if obj.image_url:
            return format_html(
                '<img src="{}" class="caddy-thumb" alt="{}" />',
                obj.image_url,
                obj.name,
            )
        return mark_safe('<span style="color: #adb5bd; font-size: 1.2rem;">🍽️</span>')

    @admin.display(description="Category")
    def category_badge(self, obj):
        if obj.category:
            return format_html(
                '<span style="background: #faf0e6; color: #d9480f; font-weight: 700; padding: 2px 8px; border-radius: 6px; font-size: 0.75rem;">{}</span>',
                obj.category.name,
            )
        return "—"

    @admin.display(description="Base Price")
    def base_price_formatted(self, obj):
        val = f"Rs {obj.base_price:,.0f}" if obj.base_price is not None else "—"
        return format_html(
            '<strong style="color: #e8590c;">{}</strong>',
            val,
        )


    @admin.display(description="Spiciness")
    def spicy_badge(self, obj):
        if obj.is_spicy:
            return mark_safe('<span title="Spicy">🌶️ Spicy</span>')
        return mark_safe('<span style="color: #8c786a;">Mild</span>')

    @admin.display(description="Diet")
    def veg_badge(self, obj):
        if obj.is_vegetarian:
            return mark_safe('<span style="color: #2b8a3e; font-weight: 700;">🌱 Veg</span>')
        return mark_safe('<span style="color: #c92a2a; font-weight: 600;">🥩 Non-Veg</span>')


@admin.register(DishSize)
class DishSizeAdmin(admin.ModelAdmin):
    list_display = ("dish", "size", "price_formatted")
    list_filter = ("size", "dish__category")
    search_fields = ("dish__name",)

    @admin.display(description="Price")
    def price_formatted(self, obj):
        return f"Rs {obj.price:,.0f}"
