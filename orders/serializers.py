from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.models import Address, Profile
from menu.models import Dish, DishSize
from .models import Order, OrderItem, OrderEvent


class OrderEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderEvent
        fields = ["id", "at", "label", "note", "actor"]


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            "id",
            "dish",
            "dish_size",
            "dish_name",
            "size",
            "unit_price",
            "qty",
            "line_total",
        ]
        read_only_fields = ["id", "dish_name", "size", "unit_price", "line_total"]


class OrderItemInputSerializer(serializers.Serializer):
    dish_id      = serializers.IntegerField(required=False)
    dish_slug    = serializers.CharField(required=False)
    dish_size_id = serializers.IntegerField(required=False)
    size         = serializers.CharField(required=False, default="Regular")
    qty          = serializers.IntegerField(min_value=1, default=1)


class OrderSerializer(serializers.ModelSerializer):
    """
    Handles Order creation with price integrity, delivery & cod fee calculation,
    and automatic OrderEvent timeline recording.
    """

    order_code  = serializers.CharField(read_only=True)
    username    = serializers.CharField(source="user.username", read_only=True)
    
    # Input options for address
    address_id  = serializers.IntegerField(write_only=True, required=False)
    address     = serializers.JSONField(required=False)

    # Input options for menu items
    items       = OrderItemInputSerializer(many=True, write_only=True, required=False)
    order_items = OrderItemSerializer(source="items", many=True, read_only=True)
    timeline    = OrderEventSerializer(many=True, read_only=True)

    # Optional single-item direct references
    dish_id      = serializers.IntegerField(write_only=True, required=False)
    dish_size_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = Order
        fields = [
            "id",
            "username",
            "order_code",
            "dish",
            "dish_size",
            "dish_id",
            "dish_size_id",
            "dish_name",
            "dish_image",
            "size",
            "qty",
            "subtotal",
            "delivery_fee",
            "cod_fee",
            "discount",
            "total",
            "payment",
            "payment_status",
            "payment_reference",
            "amount_paid",
            "paid_at",
            "verified_by",
            "priority",
            "internal_notes",
            "rating",
            "address_id",
            "address",
            "items",
            "order_items",
            "timeline",
            "rider",
            "rider_user",
            "status",
            "rider_lat",
            "rider_lng",
            "eta_minutes",
            "accepted_at",
            "delivered_at",
            "cancelled_at",
            "cancel_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "username",
            "order_code",
            "dish",
            "dish_size",
            "subtotal",
            "delivery_fee",
            "cod_fee",
            "discount",
            "total",
            "payment_status",
            "payment_reference",
            "amount_paid",
            "paid_at",
            "verified_by",
            "rider",
            "rider_user",
            "status",
            "rider_lat",
            "rider_lng",
            "eta_minutes",
            "accepted_at",
            "delivered_at",
            "cancelled_at",
            "cancel_reason",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "dish_name": {"required": False},
            "size":      {"required": False},
            "qty":       {"required": False, "default": 1},
        }

    # ── Address validation & resolution ───────────────────────────────────────
    def validate_address_dict(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("address must be a JSON object.")

        missing = [f for f in ("lat", "lng") if f not in value or value[f] is None]
        if missing:
            raise serializers.ValidationError(
                f"address is missing required field(s): {', '.join(missing)}. "
                "Geolocation coordinates (lat, lng) are mandatory."
            )

        lat = value["lat"]
        lng = value["lng"]
        try:
            lat = float(lat)
            lng = float(lng)
        except (TypeError, ValueError):
            raise serializers.ValidationError("address.lat and address.lng must be numbers.")

        if not (24.0 <= lat <= 37.5 and 60.0 <= lng <= 77.5):
            raise serializers.ValidationError(
                f"Coordinates ({lat}, {lng}) are outside the expected Pakistan bounding box."
            )

        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None

        # 1. Resolve Address
        address_id = attrs.get("address_id")
        raw_address = attrs.get("address")

        if address_id:
            try:
                saved_addr = Address.objects.get(pk=address_id, user=user)
                attrs["resolved_address"] = {
                    "label":  saved_addr.label,
                    "name":   saved_addr.name,
                    "phone":  saved_addr.phone,
                    "street": saved_addr.street,
                    "area":   saved_addr.area,
                    "city":   saved_addr.city,
                    "notes":  saved_addr.notes,
                    "lat":    saved_addr.lat,
                    "lng":    saved_addr.lng,
                }
            except Address.DoesNotExist:
                raise serializers.ValidationError({"address_id": "Saved address not found or not owned by user."})
        elif raw_address:
            self.validate_address_dict(raw_address)
            attrs["resolved_address"] = raw_address
        else:
            raise serializers.ValidationError("Either 'address_id' or inline 'address' with lat/lng is required.")

        return attrs

    # ── Order creation with server-computed price integrity ────────────────────
    def create(self, validated_data):
        user = self.context["request"].user
        address_data = validated_data.pop("resolved_address")
        validated_data.pop("address_id", None)
        validated_data.pop("address", None)

        items_input = validated_data.pop("items", None)
        dish_id = validated_data.pop("dish_id", None)
        dish_size_id = validated_data.pop("dish_size_id", None)

        # Ignore client financial fields — we compute everything server-side
        validated_data.pop("total", None)
        validated_data.pop("subtotal", None)
        validated_data.pop("delivery_fee", None)
        validated_data.pop("cod_fee", None)
        validated_data.pop("discount", None)

        line_items_to_create = []
        computed_subtotal = Decimal("0.00")
        total_qty = 0

        # Case A: Multi-item payload
        if items_input:
            for item in items_input:
                d = None
                ds = None

                if item.get("dish_id"):
                    d = Dish.objects.filter(pk=item["dish_id"]).first()
                elif item.get("dish_slug"):
                    d = Dish.objects.filter(slug=item["dish_slug"]).first()

                if item.get("dish_size_id"):
                    ds = DishSize.objects.filter(pk=item["dish_size_id"]).first()
                    if ds and not d:
                        d = ds.dish
                elif d and item.get("size"):
                    ds = DishSize.objects.filter(dish=d, size=item["size"]).first()

                qty = item.get("qty", 1)
                total_qty += qty

                if ds:
                    unit_price = ds.price
                    dish_name = d.name if d else ds.dish.name
                    size_name = ds.size
                elif d:
                    unit_price = d.base_price
                    dish_name = d.name
                    size_name = item.get("size", "Regular")
                else:
                    raise serializers.ValidationError(f"Dish could not be identified for item {item}.")

                line_total = unit_price * qty
                computed_subtotal += line_total

                line_items_to_create.append({
                    "dish": d,
                    "dish_size": ds,
                    "dish_name": dish_name,
                    "size": size_name,
                    "unit_price": unit_price,
                    "qty": qty,
                    "line_total": line_total,
                })

            first_dish = line_items_to_create[0]
            summary_name = first_dish["dish_name"]
            if len(line_items_to_create) > 1:
                summary_name += f" + {len(line_items_to_create) - 1} more"

            validated_data["dish"] = first_dish["dish"]
            validated_data["dish_size"] = first_dish["dish_size"]
            validated_data["dish_name"] = summary_name
            validated_data["dish_image"] = first_dish["dish"].image_url if first_dish["dish"] else ""
            validated_data["size"] = first_dish["size"]
            validated_data["qty"] = total_qty

        # Case B: Single item dish_id / dish_size_id references
        elif dish_size_id or dish_id:
            d = Dish.objects.filter(pk=dish_id).first() if dish_id else None
            ds = DishSize.objects.filter(pk=dish_size_id).first() if dish_size_id else None
            
            if ds and not d:
                d = ds.dish
            elif d and not ds:
                req_size = validated_data.get("size", "Regular")
                ds = DishSize.objects.filter(dish=d, size=req_size).first()

            qty = validated_data.get("qty", 1)
            unit_price = ds.price if ds else (d.base_price if d else Decimal("0.00"))
            computed_subtotal = unit_price * qty

            validated_data["dish"] = d
            validated_data["dish_size"] = ds
            validated_data["dish_name"] = validated_data.get("dish_name") or (d.name if d else "Custom Dish")
            validated_data["dish_image"] = validated_data.get("dish_image") or (d.image_url if d else "")
            validated_data["size"] = ds.size if ds else validated_data.get("size", "Regular")
            validated_data["qty"] = qty

            line_items_to_create.append({
                "dish": d,
                "dish_size": ds,
                "dish_name": validated_data["dish_name"],
                "size": validated_data["size"],
                "unit_price": unit_price,
                "qty": qty,
                "line_total": computed_subtotal,
            })

        # Case C: Fallback
        else:
            if not validated_data.get("dish_name"):
                validated_data["dish_name"] = "Food Order"

        payment_method = validated_data.get("payment", Order.PAYMENT_COD)
        delivery_fee = Decimal("0.00") if computed_subtotal >= Decimal("2000.00") else Decimal("120.00")
        cod_fee = Decimal("150.00") if payment_method == Order.PAYMENT_COD else Decimal("0.00")
        discount = Decimal("0.00")
        total = computed_subtotal + delivery_fee + cod_fee - discount

        validated_data["subtotal"] = computed_subtotal
        validated_data["delivery_fee"] = delivery_fee
        validated_data["cod_fee"] = cod_fee
        validated_data["discount"] = discount
        validated_data["total"] = total
        validated_data["address"] = address_data

        with transaction.atomic():
            order = Order.objects.create(user=user, **validated_data)

            # Create OrderItem records
            for item_data in line_items_to_create:
                OrderItem.objects.create(order=order, **item_data)

            # Record OrderEvent in timeline
            actor_name = getattr(user.profile, "full_name", "") or user.username
            OrderEvent.objects.create(
                order=order,
                label="Order placed",
                note=f"Payment: {order.get_payment_display()} · Total: Rs {order.total}",
                actor=f"Customer ({actor_name})",
                actor_user=user,
            )

            # Update Profile recipient name and phone if provided in address
            profile, _ = Profile.objects.get_or_create(user=user)
            updates = {}
            if address_data.get("name") and not profile.full_name:
                updates["full_name"] = address_data["name"]
            if address_data.get("phone") and not profile.phone:
                updates["phone"] = address_data["phone"]

            if updates:
                for k, v in updates.items():
                    setattr(profile, k, v)
                profile.save(update_fields=list(updates.keys()))

        return order


class StatusSerializer(serializers.Serializer):
    """
    Used for PATCH /api/orders/{id}/status/
    Enforces sequential forward transitions and logs OrderEvent.
    """

    status = serializers.ChoiceField(choices=Order.STATUS_CHOICES)
    note   = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_status(self, new_status):
        order = self.context["order"]
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None

        # Owner/admin may jump to any non-cancelled status (desk UX).
        # Kitchen/rider remain forward-only one step at a time.
        is_admin = False
        if user is not None:
            if getattr(user, "is_superuser", False):
                is_admin = True
            else:
                try:
                    from accounts.models import Role
                    is_admin = user.profile.role == Role.ADMIN
                except Exception:
                    is_admin = False

        if is_admin:
            if new_status == order.status:
                return new_status
            return new_status

        if order.status not in Order.STATUS_ORDER:
            raise serializers.ValidationError(
                f"Cannot advance from '{order.status}'."
            )
        if new_status not in Order.STATUS_ORDER:
            raise serializers.ValidationError(f"Invalid status '{new_status}'.")

        current_index = Order.STATUS_ORDER.index(order.status)
        new_index = Order.STATUS_ORDER.index(new_status)

        if new_index != current_index + 1:
            if new_index <= current_index:
                raise serializers.ValidationError(
                    f"Cannot go backward: '{order.status}' → '{new_status}'."
                )
            raise serializers.ValidationError(
                f"Cannot skip steps: '{order.status}' → '{new_status}'. "
                f"Next valid status is '{Order.STATUS_ORDER[current_index + 1]}'."
            )
        return new_status

    def save(self):
        order = self.context["order"]
        request = self.context.get("request")
        user = request.user if request else None

        new_status = self.validated_data["status"]
        note = self.validated_data.get("note", "")

        order.status = new_status
        if new_status == Order.STATUS_DELIVERED:
            order.delivered_at = timezone.now()
            if order.payment == Order.PAYMENT_COD and order.payment_status == Order.PAY_STATUS_PENDING:
                order.payment_status = Order.PAY_STATUS_VERIFIED
                order.amount_paid = order.total
                order.paid_at = timezone.now()
                order.verified_by = user

        order.save()

        # Record timeline event
        actor_name = "Owner"
        if user:
            role = getattr(user.profile, "role", "")
            if role == "kitchen":
                actor_name = "Kitchen Staff"
            elif role == "rider":
                actor_name = f"Rider ({getattr(user.profile, 'full_name', '') or user.username})"
            elif role == "admin" or user.is_staff:
                actor_name = "Owner"

        OrderEvent.objects.create(
            order=order,
            label=f"Status → {order.get_status_display()}",
            note=note,
            actor=actor_name,
            actor_user=user,
        )

        return order


class OrderRatingSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)

    def validate(self, attrs):
        order = self.context["order"]
        if order.status != Order.STATUS_DELIVERED:
            raise serializers.ValidationError("Only delivered orders can be rated.")
        if order.rating is not None:
            raise serializers.ValidationError("This order has already been rated.")
        return attrs


class OrderControlsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ["priority", "eta_minutes", "internal_notes", "discount"]

    def update(self, instance, validated_data):
        request = self.context.get("request")
        user = request.user if request else None

        for attr, val in validated_data.items():
            setattr(instance, attr, val)

        # Recompute total if discount changed
        if "discount" in validated_data:
            instance.total = instance.subtotal + instance.delivery_fee + instance.cod_fee - instance.discount

        instance.save()

        if "priority" in validated_data:
            OrderEvent.objects.create(
                order=instance,
                label=f"Priority → {instance.get_priority_display()}",
                actor="Owner",
                actor_user=user,
            )
        if "eta_minutes" in validated_data:
            OrderEvent.objects.create(
                order=instance,
                label=f"ETA → {instance.eta_minutes} min",
                actor="Owner",
                actor_user=user,
            )

        return instance

