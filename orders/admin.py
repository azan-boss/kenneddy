from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Order, OrderItem, OrderEvent


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("dish", "dish_name", "size", "unit_price_formatted", "qty", "line_total_formatted")
    fields = ("dish", "dish_name", "size", "unit_price_formatted", "qty", "line_total_formatted")

    @admin.display(description="Unit Price")
    def unit_price_formatted(self, obj):
        return f"Rs {obj.unit_price:,.0f}" if obj.unit_price else "—"

    @admin.display(description="Line Total")
    def line_total_formatted(self, obj):
        return f"Rs {obj.line_total:,.0f}" if obj.line_total else "—"


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 0
    readonly_fields = ("label", "note", "actor", "at")
    fields = ("label", "note", "actor", "at")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_code_badge",
        "customer_info",
        "dish_summary",
        "status_badge",
        "total_formatted",
        "payment_badge",
        "rider_display",
        "eta_display",
        "created_at_formatted",
    )
    list_filter = ("status", "payment", "payment_status", "created_at")
    search_fields = ("order_code", "user__username", "user__email", "dish_name", "rider__name", "payment_reference")
    readonly_fields = ("order_code", "created_at", "updated_at", "paid_at", "delivered_at")
    ordering = ("-created_at",)
    inlines = [OrderItemInline, OrderEventInline]

    fieldsets = (
        ("📦 Order Overview", {
            "fields": (
                ("order_code", "status"),
                ("created_at", "updated_at"),
            )
        }),
        ("👤 Customer & Dish Details", {
            "fields": (
                "user",
                ("dish_name", "size", "qty"),
                "dish_image",
                "address",
            )
        }),
        ("🛵 Caddy / Courier Dispatch", {
            "fields": (
                ("rider_user", "eta_minutes"),
                "rider",
                ("rider_lat", "rider_lng"),
            )
        }),
        ("💰 Payment & Financials", {
            "fields": (
                ("payment", "payment_status"),
                ("subtotal", "delivery_fee", "cod_fee", "discount", "total"),
                ("payment_reference", "amount_paid", "paid_at", "verified_by"),
            )
        }),
        ("⭐ Customer Feedback & Controls", {
            "fields": (
                "rating",
                ("priority", "internal_notes"),
            )
        }),
    )

    actions = [
        "mark_confirmed",
        "mark_kitchen",
        "mark_packed",
        "mark_onway",
        "mark_delivered",
        "verify_payments",
    ]

    @admin.display(description="Order Code")
    def order_code_badge(self, obj):
        return format_html(
            '<strong style="font-family: monospace; font-size: 0.9rem; color: #18110c; background: #faf0e6; padding: 3px 8px; border-radius: 6px; border: 1px solid #ffd8a8;">{}</strong>',
            obj.order_code,
        )

    @admin.display(description="Customer")
    def customer_info(self, obj):
        name = getattr(getattr(obj.user, "profile", None), "full_name", "") or obj.user.username
        phone = getattr(getattr(obj.user, "profile", None), "phone", "")
        phone_html = f'<br/><span style="font-size: 0.72rem; color: #8c786a;">📞 {phone}</span>' if phone else ""
        return format_html('<strong>{}</strong>{}', name, mark_safe(phone_html))

    @admin.display(description="Dish")
    def dish_summary(self, obj):
        items_count = obj.items.count()
        extra = f' <span style="font-size: 0.72rem; color: #8c786a;">(+{items_count-1} more)</span>' if items_count > 1 else ""
        return format_html('<span>{} (×{}){}</span>', obj.dish_name, obj.qty, mark_safe(extra))

    @admin.display(description="Status")
    def status_badge(self, obj):
        css_classes = {
            Order.STATUS_PENDING: "caddy-pill-pending",
            Order.STATUS_CONFIRMED: "caddy-pill-confirmed",
            Order.STATUS_KITCHEN: "caddy-pill-kitchen",
            Order.STATUS_PACKED: "caddy-pill-packed",
            Order.STATUS_ONWAY: "caddy-pill-onway",
            Order.STATUS_DELIVERED: "caddy-pill-delivered",
            Order.STATUS_CANCELLED: "caddy-pill-cancelled",
        }
        icons = {
            Order.STATUS_PENDING: "⏳",
            Order.STATUS_CONFIRMED: "✓",
            Order.STATUS_KITCHEN: "🍳",
            Order.STATUS_PACKED: "📦",
            Order.STATUS_ONWAY: "🛵",
            Order.STATUS_DELIVERED: "🎉",
            Order.STATUS_CANCELLED: "✕",
        }
        css = css_classes.get(obj.status, "caddy-pill-pending")
        icon = icons.get(obj.status, "•")
        return format_html(
            '<span class="caddy-pill {}">{} {}</span>',
            css,
            icon,
            obj.get_status_display(),
        )

    @admin.display(description="Total")
    def total_formatted(self, obj):
        val = f"Rs {obj.total:,.0f}" if obj.total is not None else "—"
        return format_html(
            '<strong style="color: #e8590c; font-size: 0.92rem;">{}</strong>',
            val,
        )


    @admin.display(description="Payment")
    def payment_badge(self, obj):
        icons = {
            Order.PAYMENT_COD: "💵 COD",
            Order.PAYMENT_JAZZCASH: "📱 JazzCash",
            Order.PAYMENT_EASYPAISA: "📱 EasyPaisa",
            Order.PAYMENT_CARD: "💳 Card",
        }
        label = icons.get(obj.payment, obj.payment.upper())
        status_tag = ""
        if obj.payment_status == Order.PAY_STATUS_VERIFIED:
            status_tag = ' <span style="color: #2b8a3e; font-weight: 800; font-size: 0.72rem;">✓ Paid</span>'
        elif obj.payment != Order.PAYMENT_COD:
            status_tag = ' <span style="color: #f59f00; font-weight: 800; font-size: 0.72rem;">⏳ Unverified</span>'
        return format_html('<span>{}{}</span>', label, mark_safe(status_tag))

    @admin.display(description="Assigned Caddy")
    def rider_display(self, obj):
        if obj.rider_user:
            return format_html('🛵 <strong>{}</strong>', obj.rider_user.username)
        if obj.rider and obj.rider.get("name"):
            return format_html('🛵 {}', obj.rider.get("name"))
        return mark_safe('<span style="color: #adb5bd; font-style: italic;">Unassigned</span>')

    @admin.display(description="ETA")
    def eta_display(self, obj):
        if obj.status == Order.STATUS_DELIVERED:
            return "—"
        return f"{obj.eta_minutes} min" if obj.eta_minutes else "—"

    @admin.display(description="Placed At")
    def created_at_formatted(self, obj):
        return obj.created_at.strftime("%b %d, %H:%M")

    # Custom Admin Actions for Live Kitchen & Dispatch
    @admin.action(description="🔵 Confirm Selected Orders")
    def mark_confirmed(self, request, queryset):
        for o in queryset:
            o.advance_to(Order.STATUS_CONFIRMED, actor_user=request.user)
        self.message_user(request, f"{queryset.count()} order(s) marked as Confirmed.")

    @admin.action(description="🍳 Send to Kitchen (Cooking)")
    def mark_kitchen(self, request, queryset):
        for o in queryset:
            o.advance_to(Order.STATUS_KITCHEN, actor_user=request.user)
        self.message_user(request, f"{queryset.count()} order(s) sent to Kitchen.")

    @admin.action(description="📦 Mark as Packed & Sealed")
    def mark_packed(self, request, queryset):
        for o in queryset:
            o.advance_to(Order.STATUS_PACKED, actor_user=request.user)
        self.message_user(request, f"{queryset.count()} order(s) marked as Packed.")

    @admin.action(description="🛵 Dispatch / Set On the Way")
    def mark_onway(self, request, queryset):
        for o in queryset:
            o.advance_to(Order.STATUS_ONWAY, actor_user=request.user)
        self.message_user(request, f"{queryset.count()} order(s) set On the Way.")

    @admin.action(description=" Mark as Delivered")
    def mark_delivered(self, request, queryset):
        for o in queryset:
            o.advance_to(Order.STATUS_DELIVERED, actor_user=request.user)
        self.message_user(request, f"{queryset.count()} order(s) marked as Delivered.")

    @admin.action(description="💳 Verify Payment for Selected Orders")
    def verify_payments(self, request, queryset):
        updated = queryset.update(
            payment_status=Order.PAY_STATUS_VERIFIED,
            verified_by=request.user,
        )
        self.message_user(request, f"Payment verified for {updated} order(s).")


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order_link", "dish_name", "size", "unit_price_display", "qty", "line_total_display")
    search_fields = ("order__order_code", "dish_name")
    list_filter = ("size",)

    @admin.display(description="Order")
    def order_link(self, obj):
        return obj.order.order_code

    @admin.display(description="Unit Price")
    def unit_price_display(self, obj):
        return f"Rs {obj.unit_price:,.0f}"

    @admin.display(description="Line Total")
    def line_total_display(self, obj):
        return f"Rs {obj.line_total:,.0f}"
