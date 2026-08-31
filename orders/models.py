import random
import string

from django.contrib.auth.models import User
from django.db import models


def _generate_order_code():
    """Generate a unique MG-XXXXXX style order code."""
    digits = "".join(random.choices(string.digits, k=6))
    return f"MG-{digits}"
    


class Order(models.Model):
    # ── Status choices — forward-only transitions enforced in the serializer ──
    STATUS_PENDING    = "pending"
    STATUS_CONFIRMED  = "confirmed"
    STATUS_KITCHEN    = "kitchen"
    STATUS_PACKED     = "packed"
    STATUS_ONWAY      = "onway"
    STATUS_DELIVERED  = "delivered"
    STATUS_CANCELLED  = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING,   "Awaiting Review"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_KITCHEN,   "In Kitchen"),
        (STATUS_PACKED,    "Packed"),
        (STATUS_ONWAY,     "On the Way"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    STATUS_ORDER = [
        STATUS_PENDING,
        STATUS_CONFIRMED,
        STATUS_KITCHEN,
        STATUS_PACKED,
        STATUS_ONWAY,
        STATUS_DELIVERED,
    ]

    # ── Payment choices ────────────────────────────────────────────────────────
    PAYMENT_JAZZCASH  = "jazzcash"
    PAYMENT_EASYPAISA = "easypaisa"
    PAYMENT_CARD      = "card"
    PAYMENT_COD       = "cod"

    PAYMENT_CHOICES = [
        (PAYMENT_JAZZCASH,  "JazzCash"),
        (PAYMENT_EASYPAISA, "Easypaisa"),
        (PAYMENT_CARD,      "Card"),
        (PAYMENT_COD,       "Cash on Delivery"),
    ]

    # ── Payment status choices ─────────────────────────────────────────────────
    PAY_STATUS_PENDING  = "pending"
    PAY_STATUS_VERIFIED = "verified"
    PAY_STATUS_FAILED   = "failed"
    PAY_STATUS_REFUNDED = "refunded"

    PAY_STATUS_CHOICES = [
        (PAY_STATUS_PENDING,  "Unverified"),
        (PAY_STATUS_VERIFIED, "Verified"),
        (PAY_STATUS_FAILED,   "Failed"),
        (PAY_STATUS_REFUNDED, "Refunded"),
    ]

    # ── Priority choices ───────────────────────────────────────────────────────
    PRIORITY_NORMAL = "normal"
    PRIORITY_RUSH   = "rush"
    PRIORITY_VIP    = "vip"

    PRIORITY_CHOICES = [
        (PRIORITY_NORMAL, "Normal"),
        (PRIORITY_RUSH,   "Rush"),
        (PRIORITY_VIP,    "VIP"),
    ]

    # ── Size choices ───────────────────────────────────────────────────────────
    SIZE_REGULAR = "Regular"
    SIZE_LARGE   = "Large"
    SIZE_FAMILY  = "Family"

    SIZE_CHOICES = [
        (SIZE_REGULAR, "Regular"),
        (SIZE_LARGE,   "Large"),
        (SIZE_FAMILY,  "Family"),
    ]

    # ── Fields ─────────────────────────────────────────────────────────────────
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders")
    order_code = models.CharField(max_length=20, unique=True, blank=True)

    # Primary / summary dish FK (nullable for multi-item or legacy orders)
    dish       = models.ForeignKey("menu.Dish", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    dish_size  = models.ForeignKey("menu.DishSize", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")

    dish_name  = models.CharField(max_length=200)
    dish_image = models.URLField(blank=True)
    size       = models.CharField(max_length=20, choices=SIZE_CHOICES, default=SIZE_REGULAR)
    qty        = models.PositiveIntegerField(default=1)

    # Financial / Price breakdown
    subtotal     = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    cod_fee      = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount     = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total        = models.DecimalField(max_digits=10, decimal_places=2)

    # Payment details
    payment           = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default=PAYMENT_COD)
    payment_status    = models.CharField(max_length=20, choices=PAY_STATUS_CHOICES, default=PAY_STATUS_PENDING)
    payment_reference = models.CharField(max_length=100, blank=True, null=True)
    amount_paid       = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    paid_at           = models.DateTimeField(null=True, blank=True)
    verified_by       = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_payments",
    )

    # address jsonb snapshot: {label, name, phone, street, area, city, notes, lat, lng}
    address    = models.JSONField()

    # rider display blob — set by kitchen/admin
    rider      = models.JSONField(null=True, blank=True)

    # FK to the actual rider's User account
    rider_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deliveries",
    )

    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CONFIRMED)
    priority       = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL)
    rider_lat      = models.FloatField(null=True, blank=True)
    rider_lng      = models.FloatField(null=True, blank=True)
    eta_minutes    = models.PositiveIntegerField(default=30)
    internal_notes = models.TextField(blank=True, default="")
    rating         = models.PositiveSmallIntegerField(null=True, blank=True)

    accepted_at    = models.DateTimeField(null=True, blank=True)
    delivered_at   = models.DateTimeField(null=True, blank=True)
    cancelled_at   = models.DateTimeField(null=True, blank=True)
    cancel_reason  = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.order_code:
            code = _generate_order_code()
            while Order.objects.filter(order_code=code).exists():
                code = _generate_order_code()
            self.order_code = code
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_code} — {self.user.username}"


class OrderItem(models.Model):
    order      = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    dish       = models.ForeignKey("menu.Dish", on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items")
    dish_size  = models.ForeignKey("menu.DishSize", on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items")
    dish_name  = models.CharField(max_length=200)
    size       = models.CharField(max_length=20, default="Regular")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    qty        = models.PositiveIntegerField(default=1)
    line_total = models.DecimalField(max_digits=10, decimal_places=2)

    def save(self, *args, **kwargs):
        self.line_total = self.unit_price * self.qty
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order.order_code} - {self.dish_name} ({self.size}) x{self.qty}"


class OrderEvent(models.Model):
    order      = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="timeline")
    at         = models.DateTimeField(auto_now_add=True)
    label      = models.CharField(max_length=200)
    note       = models.TextField(blank=True, default="")
    actor      = models.CharField(max_length=120)
    actor_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-at"]

    def __str__(self):
        return f"{self.order.order_code} - {self.label} at {self.at}"

