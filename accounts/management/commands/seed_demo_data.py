"""
management command: seed_demo_data

Creates realistic demo data for the Kennedy Moon Grill admin panel:
  - 5 customers
  - 4 riders (one unverified/fleet-pending, one account-pending)
  - 2 kitchen staff
  - 30-40 orders across 14 days with full OrderEvent timelines

Fully idempotent – safe to run multiple times (skips existing records).

Usage:
    python manage.py seed_demo_data
    python manage.py seed_demo_data --clear  # wipe then re-seed
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Profile, Address, Role
from menu.models import Dish, MenuCategory
from orders.models import Order, OrderItem, OrderEvent


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _rand_phone():
    prefix = random.choice(["0300", "0311", "0321", "0333", "0345", "0301"])
    return f"{prefix}{random.randint(1000000, 9999999)}"


def _rand_coords_lahore():
    """Random coordinates inside Lahore rough bounding box."""
    lat = round(random.uniform(31.42, 31.65), 6)
    lng = round(random.uniform(74.22, 74.45), 6)
    return lat, lng


def _make_user(username, email, password, full_name, role, is_active=True):
    """Get-or-create a user + profile. Returns (user, created)."""
    user, created = User.objects.get_or_create(
        username=username,
        defaults={"email": email, "is_active": is_active},
    )
    if created:
        user.set_password(password)
        user.save()
        Profile.objects.update_or_create(
            user=user,
            defaults={"role": role, "full_name": full_name, "phone": _rand_phone()},
        )
    return user, created


def _make_address(user, label="Home"):
    if user.addresses.exists():
        return user.addresses.first()
    lat, lng = _rand_coords_lahore()
    areas = ["Gulberg", "DHA Phase 5", "Johar Town", "Model Town", "Bahria Town",
             "Garden Town", "Cantt", "Faisal Town", "Wapda Town", "EME Society"]
    streets = ["Main Boulevard", "Park Avenue", "Street 12", "Block C Street",
                "Hussain Chowk Road", "Ravi Road", "Mall Road"]
    return Address.objects.create(
        user=user,
        label=label,
        name=user.profile.full_name or user.username,
        phone=user.profile.phone or _rand_phone(),
        street=f"{random.randint(5, 120)} {random.choice(streets)}",
        area=random.choice(areas),
        city="Lahore",
        lat=lat,
        lng=lng,
        is_default=True,
    )


# ─── OrderEvent labels matching the established format ────────────────────────

EVENT_PLACED     = "Order placed"
EVENT_CONFIRMED  = "Status → Confirmed"
EVENT_KITCHEN    = "Status → In Kitchen"
EVENT_PACKED     = "Status → Packed"
EVENT_RIDER_ACC  = "Rider accepted the order"
EVENT_ONWAY      = "Status → On the Way"
EVENT_DELIVERED  = "Marked delivered"
EVENT_CANCELLED  = "Order cancelled"
EVENT_VERIFIED   = "Payment verified"
EVENT_RATED      = "Customer rated the order"


def _add_event(order, label, at, actor="System", actor_user=None, note=""):
    OrderEvent.objects.get_or_create(
        order=order,
        label=label,
        defaults={"at": at, "actor": actor, "actor_user": actor_user, "note": note},
    )


def _build_timeline(order, status, placed_at, rider_user=None, actor_admin=None):
    """
    Add OrderEvent rows for all statuses up to the given target status.
    Uses the exact label strings established in the OrderEvent design.
    """
    t = placed_at
    _add_event(order, EVENT_PLACED, t, actor="Customer", actor_user=order.user)
    t += timedelta(minutes=random.randint(2, 6))

    if status in ("confirmed", "kitchen", "packed", "onway", "delivered", "cancelled"):
        _add_event(order, EVENT_CONFIRMED, t, actor="Admin", actor_user=actor_admin)
        t += timedelta(minutes=random.randint(3, 8))

    if status in ("kitchen", "packed", "onway", "delivered"):
        _add_event(order, EVENT_KITCHEN, t, actor="Kitchen", actor_user=actor_admin)
        t += timedelta(minutes=random.randint(12, 25))

    if status in ("packed", "onway", "delivered"):
        _add_event(order, EVENT_PACKED, t, actor="Kitchen", actor_user=actor_admin)
        t += timedelta(minutes=random.randint(2, 5))

    if status in ("onway", "delivered"):
        if rider_user:
            _add_event(order, EVENT_RIDER_ACC, t, actor=rider_user.profile.full_name or rider_user.username, actor_user=rider_user)
        t += timedelta(minutes=random.randint(1, 4))
        _add_event(order, EVENT_ONWAY, t, actor="Rider", actor_user=rider_user)
        t += timedelta(minutes=random.randint(18, 40))

    if status == "delivered":
        _add_event(order, EVENT_DELIVERED, t, actor="Rider", actor_user=rider_user)
        t += timedelta(minutes=random.randint(5, 30))
        if random.random() > 0.4:
            _add_event(order, EVENT_VERIFIED, t, actor="Admin", actor_user=actor_admin,
                       note="Payment confirmed via screenshot")
        if random.random() > 0.5:
            _add_event(order, EVENT_RATED, t, actor="Customer", actor_user=order.user,
                       note=f"{order.rating}★ rating")

    if status == "cancelled":
        _add_event(order, EVENT_CANCELLED, t, actor="Admin", actor_user=actor_admin,
                   note=order.cancel_reason or "Cancelled by admin")


# ─── Dish fixtures (fallback if none exist) ───────────────────────────────────

DISH_FIXTURES = [
    {"name": "Smash Burger Classic",   "slug": "smash-burger-classic",   "base_price": 890,  "category": "Burgers"},
    {"name": "Double Stack Inferno",   "slug": "double-stack-inferno",   "base_price": 1190, "category": "Burgers"},
    {"name": "Crispy Chicken Crunch",  "slug": "crispy-chicken-crunch",  "base_price": 950,  "category": "Burgers"},
    {"name": "Volcano Fries",          "slug": "volcano-fries",          "base_price": 390,  "category": "Sides"},
    {"name": "Loaded Cheese Fries",    "slug": "loaded-cheese-fries",    "base_price": 490,  "category": "Sides"},
    {"name": "Mango Lassi",            "slug": "mango-lassi",            "base_price": 250,  "category": "Drinks"},
    {"name": "Mint Lemonade",          "slug": "mint-lemonade",          "base_price": 220,  "category": "Drinks"},
    {"name": "Chocolate Shake",        "slug": "chocolate-shake",        "base_price": 320,  "category": "Drinks"},
    {"name": "Chicken Tikka Wrap",     "slug": "chicken-tikka-wrap",     "base_price": 750,  "category": "Wraps"},
    {"name": "Seekh Kabab Platter",    "slug": "seekh-kabab-platter",    "base_price": 1350, "category": "Mains"},
]


def _ensure_dishes():
    """Create fallback dishes if the menu is empty."""
    if Dish.objects.exists():
        return list(Dish.objects.all())
    dishes = []
    for d in DISH_FIXTURES:
        cat, _ = MenuCategory.objects.get_or_create(
            slug=d["category"].lower(),
            defaults={"name": d["category"], "display_order": 0},
        )
        dish, _ = Dish.objects.get_or_create(
            slug=d["slug"],
            defaults={
                "category": cat,
                "name": d["name"],
                "base_price": Decimal(d["base_price"]),
                "description": f"House special — {d['name']}",
                "heat_label": random.choice(["Mild", "Medium", "Hot", "Extra Hot"]),
                "time_label": f"{random.randint(15, 35)}m",
            },
        )
        dishes.append(dish)
    return dishes


# ─── Order factories ──────────────────────────────────────────────────────────

PAYMENT_METHODS = [
    Order.PAYMENT_COD, Order.PAYMENT_JAZZCASH,
    Order.PAYMENT_EASYPAISA, Order.PAYMENT_CARD,
]
SIZES = [Order.SIZE_REGULAR, Order.SIZE_LARGE, Order.SIZE_FAMILY]
PRIORITIES = [Order.PRIORITY_NORMAL, Order.PRIORITY_NORMAL, Order.PRIORITY_RUSH, Order.PRIORITY_VIP]


def _make_order(customer, dish, rider_user, admin_user, days_ago, status=None):
    """Create one order (idempotent by customer + dish_name + approximate day)."""
    placed_at = timezone.now() - timedelta(days=days_ago, hours=random.randint(0, 20))
    payment = random.choice(PAYMENT_METHODS)
    size = random.choice(SIZES)
    qty = random.randint(1, 3)

    size_price_mult = {"Regular": Decimal("1.0"), "Large": Decimal("1.3"), "Family": Decimal("1.7")}
    unit = dish.base_price * size_price_mult.get(size, Decimal("1.0"))
    subtotal = unit * qty
    delivery_fee = Decimal("150")
    cod_fee = Decimal("30") if payment == Order.PAYMENT_COD else Decimal("0")
    total = subtotal + delivery_fee + cod_fee

    if status is None:
        status = random.choices(
            [Order.STATUS_DELIVERED, Order.STATUS_ONWAY, Order.STATUS_KITCHEN,
             Order.STATUS_PACKED, Order.STATUS_CONFIRMED, Order.STATUS_CANCELLED],
            weights=[55, 10, 10, 10, 10, 5],
        )[0]

    pay_status = Order.PAY_STATUS_VERIFIED if status == Order.STATUS_DELIVERED and payment != Order.PAYMENT_COD else Order.PAY_STATUS_PENDING
    rating = random.randint(3, 5) if status == Order.STATUS_DELIVERED and random.random() > 0.4 else None

    addr = _make_address(customer)
    lat, lng = _rand_coords_lahore()
    rider_blob = None
    if rider_user and status in ("onway", "delivered"):
        rider_blob = {
            "name": rider_user.profile.full_name or rider_user.username,
            "phone": rider_user.profile.phone or "0300-0000000",
        }

    order = Order.objects.create(
        user=customer,
        dish_name=dish.name,
        dish_image=getattr(dish, "image_url", "") or "",
        size=size,
        qty=qty,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        cod_fee=cod_fee,
        total=total,
        payment=payment,
        payment_status=pay_status,
        payment_reference=f"REF{random.randint(100000, 999999)}" if payment != Order.PAYMENT_COD else None,
        amount_paid=total if pay_status == Order.PAY_STATUS_VERIFIED else Decimal("0"),
        address={
            "label": addr.label,
            "name": addr.name,
            "phone": addr.phone,
            "street": addr.street,
            "area": addr.area,
            "city": addr.city,
            "notes": "",
            "lat": addr.lat,
            "lng": addr.lng,
        },
        rider=rider_blob,
        rider_user=rider_user if status in ("onway", "delivered") else None,
        status=status,
        priority=random.choice(PRIORITIES),
        rider_lat=lat if status in ("onway", "delivered") else None,
        rider_lng=lng if status in ("onway", "delivered") else None,
        eta_minutes=random.randint(20, 50),
        rating=rating,
        cancel_reason="Customer changed mind" if status == Order.STATUS_CANCELLED else "",
    )

    # Backdate the created_at
    Order.objects.filter(pk=order.pk).update(created_at=placed_at, updated_at=placed_at)

    # Build OrderEvent timeline
    _build_timeline(order, status, placed_at, rider_user=rider_user, actor_admin=admin_user)

    # Add OrderItem
    OrderItem.objects.create(
        order=order,
        dish_name=dish.name,
        size=size,
        unit_price=unit,
        qty=qty,
        line_total=unit * qty,
    )

    return order


# ─── Command ──────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Seed realistic demo data for Kennedy Moon Grill admin panel"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear all demo seed users and their orders before re-seeding",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self._clear()

        self.stdout.write(self.style.WARNING("[...] Seeding demo data..."))

        # ── Admin user (superuser) ─────────────────────────────────────────────
        admin_user, created = User.objects.get_or_create(
            username="kennedy_admin",
            defaults={"email": "admin@kennedymoongrill.com", "is_staff": True, "is_superuser": True, "is_active": True},
        )
        if created:
            admin_user.set_password("Admin@1234")
            admin_user.save()
            Profile.objects.update_or_create(
                user=admin_user,
                defaults={"role": Role.ADMIN, "full_name": "Kennedy Admin", "phone": "0300-1111111"},
            )
            self.stdout.write(f"  [+] Admin: kennedy_admin / Admin@1234")
        else:
            self.stdout.write(f"  - Admin kennedy_admin already exists")

        # ── Kitchen staff ──────────────────────────────────────────────────────
        kitchen_data = [
            ("chef_bilal", "bilal@kmg.pk", "Chef Bilal Hussain"),
            ("chef_sara",  "sara@kmg.pk",  "Sara Khan"),
        ]
        kitchen_users = []
        for uname, email, full_name in kitchen_data:
            u, created = _make_user(uname, email, "Staff@1234", full_name, Role.KITCHEN, is_active=True)
            kitchen_users.append(u)
            state = "[+] Created" if created else "- Exists"
            self.stdout.write(f"  {state} kitchen: {uname}")

        # ── Riders ────────────────────────────────────────────────────────────
        # 2 active verified, 1 active unverified (fleet-pending), 1 account-pending
        riders_data = [
            ("rider_ahmed",  "ahmed@kmg.pk",  "Ahmed Raza",     True,  True),   # active + verified
            ("rider_zara",   "zara@kmg.pk",   "Zara Malik",     True,  True),   # active + verified
            ("rider_usman",  "usman@kmg.pk",  "Usman Tariq",    True,  False),  # active, fleet-unverified
            ("rider_hamza",  "hamza@kmg.pk",  "Hamza Sheikh",   False, False),  # account-pending (is_active=False)
        ]
        active_riders = []
        for uname, email, full_name, is_active, verified in riders_data:
            u, created = _make_user(uname, email, "Rider@1234", full_name, Role.RIDER, is_active=is_active)
            # RiderProfile handled separately after model is added
            if is_active:
                active_riders.append(u)
            state = "[+] Created" if created else "- Exists"
            tag = "active+verified" if is_active and verified else ("active+fleet-pending" if is_active else "account-pending")
            self.stdout.write(f"  {state} rider: {uname} [{tag}]")

        # ── Customers ─────────────────────────────────────────────────────────
        customers_data = [
            ("customer_ali",     "ali@gmail.com",     "Ali Hassan"),
            ("customer_fatima",  "fatima@gmail.com",  "Fatima Noor"),
            ("customer_omar",    "omar@gmail.com",    "Omar Khalid"),
            ("customer_ayesha",  "ayesha@gmail.com",  "Ayesha Butt"),
            ("customer_danish",  "danish@gmail.com",  "Danish Mehmood"),
        ]
        customers = []
        for uname, email, full_name in customers_data:
            u, created = _make_user(uname, email, "Customer@1234", full_name, Role.CUSTOMER, is_active=True)
            _make_address(u)
            customers.append(u)
            state = "[+] Created" if created else "- Exists"
            self.stdout.write(f"  {state} customer: {uname}")

        # ── Dishes ────────────────────────────────────────────────────────────
        dishes = _ensure_dishes()
        self.stdout.write(f"  - Using {len(dishes)} menu dishes")

        # ── Orders ────────────────────────────────────────────────────────────
        self.stdout.write(self.style.WARNING("  [.]  Generating orders..."))
        order_count = 0
        now = timezone.now()

        # Spread 35 orders across 14 days
        order_specs = []
        for day in range(0, 14):
            # 2-4 orders per day
            n = random.randint(2, 4)
            for _ in range(n):
                customer = random.choice(customers)
                dish = random.choice(dishes)
                rider = random.choice(active_riders) if active_riders else None
                order_specs.append((customer, dish, rider, day))

        for customer, dish, rider, days_ago in order_specs:
            _make_order(customer, dish, rider, admin_user, days_ago)
            order_count += 1

        # Ensure we have a few live orders (recent, not delivered)
        for status in [Order.STATUS_CONFIRMED, Order.STATUS_KITCHEN, Order.STATUS_ONWAY]:
            customer = random.choice(customers)
            dish = random.choice(dishes)
            rider = random.choice(active_riders) if active_riders else None
            _make_order(customer, dish, rider, admin_user, days_ago=0, status=status)
            order_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n[OK]  Seed complete!\n"
            f"   Admin:    kennedy_admin / Admin@1234\n"
            f"   Kitchen:  chef_bilal, chef_sara / Staff@1234\n"
            f"   Riders:   rider_ahmed, rider_zara (verified) | rider_usman (fleet-pending) | rider_hamza (account-pending)\n"
            f"   Customers: customer_ali, _fatima, _omar, _ayesha, _danish / Customer@1234\n"
            f"   Orders:   {order_count} orders across 14 days\n"
        ))

    def _clear(self):
        seed_usernames = [
            "kennedy_admin", "chef_bilal", "chef_sara",
            "rider_ahmed", "rider_zara", "rider_usman", "rider_hamza",
            "customer_ali", "customer_fatima", "customer_omar", "customer_ayesha", "customer_danish",
        ]
        deleted_orders = 0
        for uname in seed_usernames:
            try:
                u = User.objects.get(username=uname)
                deleted_orders += u.orders.count()
                u.delete()
            except User.DoesNotExist:
                pass
        self.stdout.write(self.style.WARNING(f"[DEL]  Cleared seed users and {deleted_orders} orders."))

