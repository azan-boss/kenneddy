from django.db import models


class MenuCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Menu Category"
        verbose_name_plural = "Menu Categories"

    def __str__(self):
        return self.name


class AccentChoice(models.TextChoices):
    FLAME = "flame", "Flame"
    EMBER = "ember", "Ember"
    GOLD  = "gold", "Gold"
    CHAR  = "char", "Char"
    LEAF  = "leaf", "Leaf"


class RibbonChoice(models.TextChoices):
    HOT       = "hot", "Hot"
    NEW       = "new", "New"
    DEMAND    = "demand", "In Demand"
    SIGNATURE = "signature", "Signature"


class Dish(models.Model):
    category = models.ForeignKey(MenuCategory, on_delete=models.CASCADE, related_name="dishes")
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    tag = models.CharField(max_length=50, blank=True, default="")
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Default/Regular size price in PKR")
    old_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    heat_label = models.CharField(max_length=30, blank=True, default="Medium")
    time_label = models.CharField(max_length=30, blank=True, default="20m")
    accent = models.CharField(max_length=20, choices=AccentChoice.choices, default=AccentChoice.FLAME)
    ribbon = models.CharField(max_length=20, choices=RibbonChoice.choices, null=True, blank=True)
    story = models.TextField(blank=True, default="")
    ingredients = models.JSONField(default=list, blank=True)
    allergens = models.JSONField(default=list, blank=True)
    serves = models.CharField(max_length=50, blank=True, default="2 people")
    weight = models.CharField(max_length=50, blank=True, default="")
    calories = models.PositiveIntegerField(default=0)
    spice_level = models.PositiveSmallIntegerField(default=3)
    chef = models.CharField(max_length=100, blank=True, default="Chef Kennedy")
    is_available = models.BooleanField(default=True)
    is_vegetarian = models.BooleanField(default=False)
    is_spicy = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Dish"
        verbose_name_plural = "Dishes"

    def __str__(self):
        return f"{self.name} ({self.category.name})"



class DishSize(models.Model):
    SIZE_REGULAR = "Regular"
    SIZE_LARGE   = "Large"
    SIZE_FAMILY  = "Family"

    SIZE_CHOICES = [
        (SIZE_REGULAR, "Regular"),
        (SIZE_LARGE,   "Large"),
        (SIZE_FAMILY,  "Family"),
    ]

    dish = models.ForeignKey(Dish, on_delete=models.CASCADE, related_name="sizes")
    size = models.CharField(max_length=20, choices=SIZE_CHOICES)
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price in PKR for this size")

    class Meta:
        unique_together = ("dish", "size")
        ordering = ["price"]
        verbose_name = "Dish Size"
        verbose_name_plural = "Dish Sizes"

    def __str__(self):
        return f"{self.dish.name} - {self.size} (PKR {self.price})"
