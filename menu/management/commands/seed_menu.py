from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from menu.models import MenuCategory, Dish, DishSize, AccentChoice, RibbonChoice


class Command(BaseCommand):
    help = "Seeds menu categories, rich dishes, and dish sizes from menu.ts catalogue."

    def handle(self, *args, **options):
        self.stdout.write("Starting menu seeding from menu.ts catalogue...")

        SEED_DATA = [
            {
                "category": {
                    "name": "Pizza",
                    "slug": "pizza",
                    "display_order": 1,
                },
                "dishes": [
                    {
                        "slug": "spicy-white-pizza",
                        "name": "Spicy White Pizza",
                        "tag": "Signature",
                        "description": "Our legendary white sauce base loaded with fiery bird's eye chilies, buffalo mozzarella, roasted garlic slivers, and drizzled with hot honey on charcoal fired crust.",
                        "base_price": Decimal("1450.00"),
                        "old_price": Decimal("1750.00"),
                        "heat_label": "Hot",
                        "time_label": "18m",
                        "accent": AccentChoice.FLAME,
                        "ribbon": RibbonChoice.HOT,
                        "story": "Born in the original Narowal Moon Grill kitchen in 2014, our Spicy White Pizza flipped the script on traditional red pies. We simmer cream, roasted garlic, and crushed bird's eye chilies for four hours before ladling it onto hand-stretched 48-hour fermented dough. Baked over babool wood at 450°C, every blistered slice carries smoke, silk, and relentless fire.",
                        "ingredients": [
                            "Hand-stretched 48hr fermented dough",
                            "House slow-simmered garlic white cream",
                            "Fresh buffalo mozzarella from local dairy",
                            "Crushed Narowal bird's eye chilies",
                            "Kashmir wild hot honey drizzle",
                            "Crisp basil & toasted garlic slivers",
                        ],
                        "allergens": [
                            "Dairy (Mozzarella, Cream)",
                            "Gluten (Wheat Flour)",
                        ],
                        "serves": "2-3 persons",
                        "weight": "780g",
                        "calories": 1120,
                        "spice_level": 4,
                        "chef": "Chef Kennedy",
                        "image_url": "/images/pizza.png",
                        "is_spicy": True,
                        "sizes": [
                            ("Regular", Decimal("1450.00")),
                            ("Large",   Decimal("1800.00")),
                            ("Family",  Decimal("2150.00")),
                        ],
                    },
                ],
            },
            {
                "category": {
                    "name": "Charcoal Grills",
                    "slug": "grills",
                    "display_order": 2,
                },
                "dishes": [
                    {
                        "slug": "seekh-malai-boti",
                        "name": "Seekh & Malai Boti Platter",
                        "tag": "Charcoal",
                        "description": "Tender boneless chicken steeped in green cardamom, rich clotted malai, and white pepper, paired with melt-in-mouth beef seekh kebabs charred on open coals.",
                        "base_price": Decimal("1150.00"),
                        "old_price": Decimal("1400.00"),
                        "heat_label": "Medium",
                        "time_label": "22m",
                        "accent": AccentChoice.EMBER,
                        "ribbon": RibbonChoice.DEMAND,
                        "story": "The centerpiece of Moon Grill since day one. We marinate prime chicken thigh in 24-hour strained yogurt, churned malai, and hand-ground green chilies. Skewered on heavy iron rods and fanned over burning babool coals until golden and dripping with ghee.",
                        "ingredients": [
                            "Prime boneless chicken thigh",
                            "Fresh buffalo clotted malai",
                            "Minced beef with suet & marrow",
                            "Green cardamom & roasted cumin",
                            "Desi ghee baste",
                            "Charred onion & mint chutney",
                        ],
                        "allergens": [
                            "Dairy (Malai, Yogurt, Ghee)",
                        ],
                        "serves": "2 persons",
                        "weight": "650g",
                        "calories": 890,
                        "spice_level": 3,
                        "chef": "Ustad Nadeem",
                        "image_url": "/images/grills.png",
                        "is_spicy": True,
                        "sizes": [
                            ("Regular", Decimal("1150.00")),
                            ("Large",   Decimal("1500.00")),
                            ("Family",  Decimal("1850.00")),
                        ],
                    },
                ],
            },
            {
                "category": {
                    "name": "Karahi",
                    "slug": "karahi",
                    "display_order": 3,
                },
                "dishes": [
                    {
                        "slug": "chicken-karahi",
                        "name": "Shinwari Chicken Karahi",
                        "tag": "House Classic",
                        "description": "Desi murgh wok-tossed on high flame with ripe tomatoes, julienned ginger, green chilies, and black pepper in pure butter. Zero onion, pure flavor.",
                        "base_price": Decimal("1650.00"),
                        "old_price": Decimal("1950.00"),
                        "heat_label": "Extra Hot",
                        "time_label": "25m",
                        "accent": AccentChoice.CHAR,
                        "ribbon": RibbonChoice.HOT,
                        "story": "Prepared in traditional heavy cast-iron karahis over roaring gas burners. No onion paste, no heavy spices—just fresh tomatoes breaking down into a silky glaze with crushed ginger and spicy local chilies, finished with hand-churned butter.",
                        "ingredients": [
                            "Fresh farm chicken bone-in",
                            "Vine-ripened red tomatoes",
                            "Julienned fresh ginger",
                            "Coarse crushed black pepper",
                            "Hand-churned butter & desi ghee",
                            "Fresh coriander & slit green chilies",
                        ],
                        "allergens": [
                            "Dairy (Butter, Ghee)",
                        ],
                        "serves": "2-3 persons",
                        "weight": "900g",
                        "calories": 1340,
                        "spice_level": 5,
                        "chef": "Chef Kennedy",
                        "image_url": "/images/karahi.png",
                        "is_spicy": True,
                        "sizes": [
                            ("Regular", Decimal("1650.00")),
                            ("Large",   Decimal("2000.00")),
                            ("Family",  Decimal("2350.00")),
                        ],
                    },
                ],
            },
            {
                "category": {
                    "name": "Rice & Pulao",
                    "slug": "rice",
                    "display_order": 4,
                },
                "dishes": [
                    {
                        "slug": "kabuli-pulao",
                        "name": "Traditional Kabuli Pulao",
                        "tag": "Slow Cooked",
                        "description": "Long grain aged basmati rice steam-cooked in aromatic lamb broth, garnished with caramelized carrots, sweet black raisins, and toasted almond slivers.",
                        "base_price": Decimal("1350.00"),
                        "old_price": Decimal("1600.00"),
                        "heat_label": "Mild",
                        "time_label": "30m",
                        "accent": AccentChoice.GOLD,
                        "ribbon": RibbonChoice.SIGNATURE,
                        "story": "Slow cooked under sealed dough lids (dum) for six hours. The rice absorbs every drop of mutton stock, subtly sweet from sun-dried Afghan black raisins and julienned carrots cooked in brown sugar and cardamom butter.",
                        "ingredients": [
                            "Aged extra-long grain basmati rice",
                            "Slow-simmered lamb shank broth",
                            "Caramelized julienne carrots",
                            "Kandahar black raisins",
                            "Toasted almond & pistachio slivers",
                            "Cardamom & whole spice blend",
                        ],
                        "allergens": [
                            "Nuts (Almonds, Pistachios)",
                            "Dairy (Ghee)",
                        ],
                        "serves": "2-3 persons",
                        "weight": "850g",
                        "calories": 1260,
                        "spice_level": 1,
                        "chef": "Ustad Nadeem",
                        "image_url": "/images/rice.png",
                        "is_spicy": False,
                        "sizes": [
                            ("Regular", Decimal("1350.00")),
                            ("Large",   Decimal("1700.00")),
                            ("Family",  Decimal("2050.00")),
                        ],
                    },
                ],
            },
            {
                "category": {
                    "name": "Steaks",
                    "slug": "steaks",
                    "display_order": 5,
                },
                "dishes": [
                    {
                        "slug": "flame-grilled-steak",
                        "name": "Moon Grill Beef Tenderloin",
                        "tag": "Premium",
                        "description": "Thick cut aged beef tenderloin seared on scorching cast iron, basted with rosemary garlic butter, served with fiery peppercorn sauce and steak fries.",
                        "base_price": Decimal("2450.00"),
                        "old_price": Decimal("2900.00"),
                        "heat_label": "Medium",
                        "time_label": "20m",
                        "accent": AccentChoice.LEAF,
                        "ribbon": RibbonChoice.NEW,
                        "story": "Hand-selected 28-day dry-aged beef fillet from local organic farms. Seared at 500°F for a mahogany crust while keeping the center tender and juicy. Finished with a smoky black peppercorn reduction.",
                        "ingredients": [
                            "28-day aged prime beef tenderloin (350g)",
                            "Fresh rosemary & crushed garlic butter",
                            "Black peppercorn cream sauce",
                            "Hand-cut crispy steak fries",
                            "Charred herb cherry tomatoes",
                        ],
                        "allergens": [
                            "Dairy (Butter, Cream)",
                        ],
                        "serves": "1-2 persons",
                        "weight": "550g",
                        "calories": 980,
                        "spice_level": 2,
                        "chef": "Chef Kennedy",
                        "image_url": "/images/steak.png",
                        "is_spicy": False,
                        "sizes": [
                            ("Regular", Decimal("2450.00")),
                            ("Large",   Decimal("2800.00")),
                            ("Family",  Decimal("3150.00")),
                        ],
                    },
                ],
            },
        ]

        active_slugs = []

        with transaction.atomic():
            for group in SEED_DATA:
                cat_data = group["category"]
                category, _ = MenuCategory.objects.update_or_create(
                    slug=cat_data["slug"],
                    defaults={
                        "name": cat_data["name"],
                        "display_order": cat_data["display_order"],
                        "is_active": True,
                    },
                )

                for dish_data in group["dishes"]:
                    sizes_data = dish_data.pop("sizes")
                    slug = dish_data["slug"]
                    active_slugs.append(slug)

                    dish, _ = Dish.objects.update_or_create(
                        slug=slug,
                        defaults={
                            "category": category,
                            "is_available": True,
                            **dish_data,
                        },
                    )

                    for size_label, size_price in sizes_data:
                        DishSize.objects.update_or_create(
                            dish=dish,
                            size=size_label,
                            defaults={"price": size_price},
                        )

            # Soft-disable any obsolete dishes rather than hard deleting
            Dish.objects.exclude(slug__in=active_slugs).update(is_available=False)

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {len(active_slugs)} rich menu dishes!"))
