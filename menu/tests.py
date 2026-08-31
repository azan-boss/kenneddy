from decimal import Decimal
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase
from menu.models import MenuCategory, Dish, DishSize


class MenuCatalogTests(APITestCase):

    def setUp(self):
        call_command("seed_menu")

    def test_seed_menu_creates_5_rich_dishes(self):
        self.assertEqual(MenuCategory.objects.filter(is_active=True).count(), 5)
        self.assertEqual(Dish.objects.filter(is_available=True).count(), 5)

        pizza = Dish.objects.get(slug="spicy-white-pizza")
        self.assertEqual(pizza.name, "Spicy White Pizza")
        self.assertEqual(pizza.tag, "Signature")
        self.assertEqual(pizza.spice_level, 4)
        self.assertEqual(pizza.heat_label, "Hot")
        self.assertEqual(pizza.time_label, "18m")
        self.assertEqual(pizza.accent, "flame")
        self.assertEqual(pizza.ribbon, "hot")
        self.assertEqual(pizza.calories, 1120)
        self.assertIn("48hr fermented dough", pizza.ingredients[0])
        self.assertEqual(pizza.sizes.count(), 3)

    def test_get_categories_endpoint(self):
        res = self.client.get("/api/menu/categories/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 5)
        
        # Check first category has nested dishes with sizes
        first_cat = res.data[0]
        self.assertIn("dishes", first_cat)
        self.assertTrue(len(first_cat["dishes"]) >= 1)
        first_dish = first_cat["dishes"][0]
        self.assertIn("sizes", first_dish)
        self.assertEqual(len(first_dish["sizes"]), 3)

    def test_get_single_dish_by_slug(self):
        res = self.client.get("/api/menu/dishes/spicy-white-pizza/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["slug"], "spicy-white-pizza")
        self.assertEqual(res.data["name"], "Spicy White Pizza")
        self.assertEqual(res.data["chef"], "Chef Kennedy")
        self.assertEqual(res.data["spice_level"], 4)
        self.assertIn("story", res.data)
        self.assertIn("allergens", res.data)
        self.assertEqual(len(res.data["sizes"]), 3)
