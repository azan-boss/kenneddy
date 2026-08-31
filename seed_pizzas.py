import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from menu.models import MenuCategory, Dish, DishSize

cat, _ = MenuCategory.objects.get_or_create(slug='pizza', defaults={'name': 'Spicy Pizza Specialist', 'display_order': 1})
cat.name = 'Spicy Pizza Specialist'
cat.display_order = 1
cat.save()

pizzas = [
    {
        'name': 'Kennedy Inferno Pizza',
        'slug': 'kennedy-inferno-pizza',
        'tag': 'Signature Hot',
        'desc': '48-hour cold fermented stone-baked dough loaded with spicy pepperoni, charred jalapenos, red crushed peppers, and garlic cream drizzle.',
        'image_url': 'https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?w=800',
        'base_price': 1850,
        'old_price': 2150,
        'heat_label': 'Extra Fiery',
        'time_label': '18m',
        'spice_level': 5,
        'story': 'Cold fermented for 48 hours and baked on 450°C stone deck with Chef Kennedy & Caddy secret chili drizzle.',
        'ingredients': ['Cold-fermented dough', 'Garlic cream', 'Charred jalapeno', 'Beef pepperoni', 'Crushed red chili', 'Smoked mozzarella'],
        'allergens': ['Gluten', 'Dairy'],
        'sizes': [('Regular (10")', 1450), ('Large (13")', 1850), ('Family (16")', 2450)]
    },
    {
        'name': 'Spicy White Garlic Pizza',
        'slug': 'spicy-white-garlic-pizza',
        'tag': 'House Classic',
        'desc': 'Decadent roasted garlic white sauce, flame-broiled chicken boti, fresh basil leaves, and crushed chili flakes on stone-baked crust.',
        'image_url': 'https://images.unsplash.com/photo-1513104890138-7c749659a591?w=800',
        'base_price': 1650,
        'old_price': 1950,
        'heat_label': 'Medium Spicy',
        'time_label': '20m',
        'spice_level': 4,
        'story': 'Roasted garlic cream sauce replaces tomato sauce for a velvety smoke and heat finish from Caddy Kitchen.',
        'ingredients': ['Roasted garlic sauce', 'Flame-broiled chicken', 'Fresh basil', 'Chili flakes', 'Mozzarella and cheddar blend'],
        'allergens': ['Gluten', 'Dairy'],
        'sizes': [('Regular (10")', 1350), ('Large (13")', 1650), ('Family (16")', 2200)]
    },
    {
        'name': 'Smoked Chicken Fajita Pizza',
        'slug': 'smoked-chicken-fajita-pizza',
        'tag': 'Customer Favorite',
        'desc': 'Charcoal-grilled fajita chicken, bell peppers, sweet red onions, melted gouda, and oregano sprinkle.',
        'image_url': 'https://images.unsplash.com/photo-1593560708920-61dd98c46a4e?w=800',
        'base_price': 1750,
        'old_price': 2000,
        'heat_label': 'Hot',
        'time_label': '18m',
        'spice_level': 4,
        'story': 'Marinated in Mexican fajita spices and seared over charcoal before topping our stone deck crust.',
        'ingredients': ['Fajita chicken strips', 'Bell peppers', 'Red onion', 'Smoked gouda', 'Oregano', 'Kennedy tomato glaze'],
        'allergens': ['Gluten', 'Dairy'],
        'sizes': [('Regular (10")', 1400), ('Large (13")', 1750), ('Family (16")', 2350)]
    },
    {
        'name': 'BBQ Cheese Stacker Pizza',
        'slug': 'bbq-cheese-stacker-pizza',
        'tag': 'Cheesy Delight',
        'desc': 'Double cheese-stuffed crust layered with hickory BBQ smoked chicken, charred corn, and cilantro.',
        'image_url': 'https://images.unsplash.com/photo-1550547660-d9450f859349?w=800',
        'base_price': 1950,
        'old_price': 2250,
        'heat_label': 'Medium',
        'time_label': '22m',
        'spice_level': 3,
        'story': 'Stuffed around the edge with sharp cheddar and mozzarella, glazed with smokey hickory BBQ sauce.',
        'ingredients': ['Cheese-stuffed crust', 'Hickory BBQ sauce', 'Smoked chicken', 'Charred corn', 'Cilantro'],
        'allergens': ['Gluten', 'Dairy'],
        'sizes': [('Regular (10")', 1550), ('Large (13")', 1950), ('Family (16")', 2600)]
    },
    {
        'name': 'Devils Pepperoni Blast Pizza',
        'slug': 'devils-pepperoni-blast-pizza',
        'tag': 'Fiery Pepperoni',
        'desc': 'Crispy beef pepperoni cups, habanero chili oil drizzle, double mozzarella, and hot honey glaze.',
        'image_url': 'https://images.unsplash.com/photo-1628840042765-356cda07504e?w=800',
        'base_price': 1890,
        'old_price': 2190,
        'heat_label': 'Fiery Hot',
        'time_label': '18m',
        'spice_level': 5,
        'story': 'Loaded with pepperoni cups that crisp up into little oil wells, drizzled with hot chili honey from Caddy Oven.',
        'ingredients': ['Beef pepperoni cups', 'Habanero oil', 'Hot honey glaze', 'Double mozzarella', 'Cold fermented crust'],
        'allergens': ['Gluten', 'Dairy'],
        'sizes': [('Regular (10")', 1490), ('Large (13")', 1890), ('Family (16")', 2490)]
    },
    {
        'name': 'Malai Boti Crown Crust Pizza',
        'slug': 'malai-boti-crown-crust-pizza',
        'tag': 'Crown Special',
        'desc': 'Malai boti stuffed crown pockets, charcoal chicken tikka, green chili cream sauce, and fresh coriander.',
        'image_url': 'https://images.unsplash.com/photo-1574071318508-1cdbab80d002?w=800',
        'base_price': 1990,
        'old_price': 2290,
        'heat_label': 'Rich and Spicy',
        'time_label': '24m',
        'spice_level': 4,
        'story': 'Our crown crust has 8 pockets filled with creamy malai boti, surrounding a center of spicy charcoal chicken.',
        'ingredients': ['Malai boti crown pockets', 'Charcoal chicken tikka', 'Green chili cream', 'Smoked mozzarella', 'Coriander'],
        'allergens': ['Gluten', 'Dairy'],
        'sizes': [('Regular (10")', 1590), ('Large (13")', 1990), ('Family (16")', 2690)]
    },
    {
        'name': 'Charcoal Afghani Pizza',
        'slug': 'charcoal-afghani-pizza',
        'tag': 'Smoky Taste',
        'desc': 'Mild smoky Afghani boti, garlic sauce, roasted capsicum, oregano, and cheddar melt.',
        'image_url': 'https://images.unsplash.com/photo-1541745537411-b8046dc6d66c?w=800',
        'base_price': 1690,
        'old_price': 1990,
        'heat_label': 'Mild Smoky',
        'time_label': '20m',
        'spice_level': 2,
        'story': 'Mildly spiced, marinated with yogurt and white pepper, seared over coal for an authentic Afghan aroma.',
        'ingredients': ['Afghani boti', 'Yogurt garlic glaze', 'Roasted capsicum', 'Cheddar and mozzarella'],
        'allergens': ['Gluten', 'Dairy'],
        'sizes': [('Regular (10")', 1390), ('Large (13")', 1690), ('Family (16")', 2290)]
    },
    {
        'name': 'Veggie Volcano Pizza',
        'slug': 'veggie-volcano-pizza',
        'tag': 'Zesty Veggie',
        'desc': 'Black olives, jalapenos, mushrooms, sweet corn, vine tomatoes, and spicy tomato sauce.',
        'image_url': 'https://images.unsplash.com/photo-1571407970349-bc81e7e96d47?w=800',
        'base_price': 1490,
        'old_price': 1790,
        'heat_label': 'Zesty Veggie',
        'time_label': '18m',
        'spice_level': 3,
        'story': 'A vibrant garden of fresh vegetables baked over spicy herb tomato sauce in Caddy Stone Deck.',
        'ingredients': ['Black olives', 'Jalapenos', 'Mushrooms', 'Sweet corn', 'Vine tomatoes', 'Spicy herb sauce'],
        'allergens': ['Gluten', 'Dairy'],
        'sizes': [('Regular (10")', 1190), ('Large (13")', 1490), ('Family (16")', 2090)]
    }
]

created_count = 0
for p in pizzas:
    d, created = Dish.objects.update_or_create(
        slug=p['slug'],
        defaults={
            'category': cat,
            'name': p['name'],
            'tag': p['tag'],
            'description': p['desc'],
            'image_url': p['image_url'],
            'base_price': p['base_price'],
            'old_price': p['old_price'],
            'heat_label': p['heat_label'],
            'time_label': p['time_label'],
            'spice_level': p['spice_level'],
            'story': p['story'],
            'ingredients': p['ingredients'],
            'allergens': p['allergens'],
            'chef': 'Chef Kennedy & Caddy Kitchen',
            'is_available': True,
            'is_spicy': p['spice_level'] >= 3,
        }
    )
    d.sizes.all().delete()
    for size_name, size_price in p['sizes']:
        DishSize.objects.create(dish=d, size=size_name, price=size_price)
    created_count += 1

print('Successfully seeded', created_count, 'authentic pizza recipes into Django DB!')
