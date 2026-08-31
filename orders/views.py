from decimal import Decimal
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from .models import Order
from .permissions import CanAdvanceStatus, IsAdminRole, IsAssignedRider, CanAssignRider, CanViewAllOrders
from .serializers import OrderSerializer, StatusSerializer


# ── helpers ────────────────────────────────────────────────────────────────────

def _fetch_order_or_404(pk):
    """Return Order or None — callers decide 404 vs 403 messaging."""
    try:
        return Order.objects.select_related("rider_user__profile").get(pk=pk)
    except Order.DoesNotExist:
        return None


def _broadcast_order_update(order):
    """Push rider location + status to the Channels group for this order."""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"order_{order.id}",
        {
            "type":       "order.update",      # maps to consumer method order_update
            "status":     order.status,
            "rider_lat":  order.rider_lat,
            "rider_lng":  order.rider_lng,
            "eta_minutes": order.eta_minutes,
        },
    )


# ── Order list / create ────────────────────────────────────────────────────────

class OrderListCreateView(APIView):
    """
    GET  /api/orders/?limit=30  — authenticated user's own orders only.
    POST /api/orders/           — create an order; also upserts the user's Profile.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit  = min(int(request.query_params.get("limit", 30)), 100)
        orders = Order.objects.filter(user=request.user)[:limit]
        return Response(OrderSerializer(orders, many=True).data)

    def post(self, request):
        serializer = OrderSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            order = serializer.save()
            return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VoiceOrderCreateView(APIView):
    """
    POST /api/orders/voice-order/
    Public endpoint for ElevenLabs Conversational AI Voice Assistant to place customer orders.
    Secured via X-Kennedy-Secret header set as an ElevenLabs Environment Variable.
    """

    authentication_classes = []   # Skip JWT — ElevenLabs uses our own Bearer secret
    permission_classes = [AllowAny]
    WEBHOOK_SECRET = "kennedy-secret-2024"  # Must match ElevenLabs Bearer token value

    def post(self, request):
        # Verify ElevenLabs is the caller via Bearer token
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip()
        if token != self.WEBHOOK_SECRET:
            return Response(
                {"detail": "Unauthorized — invalid secret."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        data = request.data
        customer_name = data.get("customer_name") or data.get("name") or "Voice Customer"
        customer_phone = data.get("customer_phone") or data.get("phone_number") or data.get("phone") or "0000000000"
        delivery_address = data.get("delivery_address") or data.get("address") or data.get("delivery_area") or "Narowal"
        payment_method = data.get("payment_method") or data.get("payment") or Order.PAYMENT_COD
        user_id = data.get("user_id")
        ordered_items = data.get("ordered_items", [])

        if not customer_phone or customer_phone == "0000000000" or not delivery_address:
            return Response(
                {"detail": "customer_phone and delivery_address are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── Link to real user if user_id was passed, otherwise guest user ─────
        user = None
        if user_id:
            try:
                user = User.objects.filter(id=int(user_id)).first()
            except (ValueError, TypeError):
                pass

        if not user:
            # Get or create guest user
            clean_phone = "".join(filter(str.isdigit, customer_phone)) or "000000"
            username = f"voice_{clean_phone}"
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={"first_name": customer_name, "email": f"{username}@kennedy.local"}
            )

        # Update profile details (only fields that exist on Profile model)
        profile = getattr(user, "profile", None)
        if profile:
            if not profile.full_name or profile.full_name == "Voice Customer":
                profile.full_name = customer_name
            if not profile.phone or profile.phone == "0000000000":
                profile.phone = customer_phone
            profile.save()

        # Parse items & compute financial totals
        total_amount = Decimal("0.00")
        item_objects = []

        # Case 1: Top-level dish_name passed directly by ElevenLabs
        if data.get("dish_name"):
            d_name = data.get("dish_name")
            d_size = data.get("size") or data.get("portion_size") or "Large"
            d_price_raw = data.get("price") or data.get("total_price") or 1450
            try:
                d_price = Decimal(str(d_price_raw))
                if d_price > 500 and "total_price" in data and not data.get("price"):
                    # total_price included delivery fee (150)
                    if d_price > 150:
                        d_price = d_price - Decimal("150.00")
            except Exception:
                d_price = Decimal("1450.00")
            
            d_qty = int(data.get("qty") or data.get("quantity") or 1)
            item_objects.append({
                "dish_name": d_name,
                "size": str(d_size),
                "price": d_price,
                "qty": d_qty,
            })
            total_amount += d_price * d_qty

        # Case 2: ordered_items passed as string or list
        import json as _json
        if isinstance(ordered_items, str) and ordered_items.strip():
            try:
                ordered_items = _json.loads(ordered_items)
            except (_json.JSONDecodeError, ValueError):
                ordered_items = []

        if isinstance(ordered_items, list) and len(ordered_items) > 0:
            for item in ordered_items:
                dish_name = item.get("dish_name", "Spicy Pizza")
                size = item.get("portion_size") or item.get("size") or "Large"
                price = Decimal(str(item.get("price", 1500)))
                qty = int(item.get("qty", 1))
                line_total = price * qty
                total_amount += line_total
                item_objects.append({
                    "dish_name": dish_name,
                    "size": str(size),
                    "price": price,
                    "qty": qty,
                })

        if total_amount == 0:
            total_amount = Decimal("1450.00")  # Default fallback

        delivery_fee = Decimal("150.00")
        grand_total = total_amount + delivery_fee

        first_item = item_objects[0] if item_objects else {"dish_name": "Kennedy Pizza Special", "size": "Regular"}

        # Create Order
        order = Order.objects.create(
            user=user,
            dish_name=first_item["dish_name"],
            size=first_item["size"][:20],
            qty=first_item.get("qty", 1),
            subtotal=total_amount,
            delivery_fee=delivery_fee,
            total=grand_total,
            payment=payment_method,
            status=Order.STATUS_PENDING,
            address={
                "name": customer_name,
                "phone": customer_phone,
                "area": delivery_address,
                "street": delivery_address,
                "notes": "Placed via ElevenLabs AI Voice Assistant",
            },
        )

        # Save order items
        from .models import OrderItem, OrderEvent
        for item in item_objects:
            OrderItem.objects.create(
                order=order,
                dish_name=item["dish_name"],
                size=item["size"][:20],
                unit_price=item["price"],
                qty=item["qty"],
                line_total=item["price"] * item["qty"],
            )

        OrderEvent.objects.create(
            order=order,
            label="Order created via Voice AI",
            note=f"Placed by AI Voice Agent for {customer_name}",
            actor="ElevenLabs AI",
        )

        # Broadcast live order to Admin Panel over Channels
        try:
            _broadcast_order_update(order)
        except Exception:
            pass

        return Response({
            "status": "success",
            "order_code": order.order_code,
            "total": float(order.total),
            "message": f"Shukriya {customer_name}! Aapka order {order.order_code} (PKR {order.total}) confirm ho chuka hai.",
        }, status=status.HTTP_201_CREATED)



class VoiceOrderStatusView(APIView):
    """
    GET /api/orders/voice-status/?phone=03001234567
    GET /api/orders/voice-status/?order_code=MG-123456
    Public endpoint for ElevenLabs AI to check order status by phone or order code.
    """

    authentication_classes = []   # Skip JWT — ElevenLabs uses our own Bearer secret
    permission_classes = [AllowAny]
    WEBHOOK_SECRET = "kennedy-secret-2024"

    def get(self, request):
        # Verify ElevenLabs caller
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip()
        if token != self.WEBHOOK_SECRET:
            return Response({"detail": "Unauthorized."}, status=status.HTTP_401_UNAUTHORIZED)

        phone = request.query_params.get("phone", "").strip()
        order_code = request.query_params.get("order_code", "").strip()

        order = None
        if order_code:
            order = Order.objects.filter(order_code__iexact=order_code).first()
        elif phone:
            clean_phone = "".join(filter(str.isdigit, phone)) or ""
            username = f"voice_{clean_phone}"
            order = (
                Order.objects.filter(order_code__iexact=phone).first()
                or Order.objects.filter(user__username=username).order_by("-created_at").first()
                or Order.objects.filter(user__profile__phone__icontains=clean_phone).order_by("-created_at").first()
                or Order.objects.filter(address__phone__icontains=clean_phone).order_by("-created_at").first()
            )

        if not order:
            return Response({
                "found": False,
                "message": "Koi order nahi mila. Kripya sahi phone number ya order code dijiye.",
            })

        STATUS_LABELS = {
            Order.STATUS_PENDING:   "Pending — abhi confirm nahi hua",
            Order.STATUS_CONFIRMED: "Confirmed — kitchen mein ja raha hai",
            Order.STATUS_KITCHEN:   "Kitchen mein taiyar ho raha hai",
            Order.STATUS_PACKED:    "Pack ho gaya — rider pick karne wala hai",
            Order.STATUS_ONWAY:     "Rider raaste mein hai",
            Order.STATUS_DELIVERED: "Deliver ho gaya",
            Order.STATUS_CANCELLED: "Cancel ho gaya",
        }
        label = STATUS_LABELS.get(order.status, order.status)

        rider_name = None
        rider_phone = None
        if order.rider and isinstance(order.rider, dict):
            rider_name = order.rider.get("name")
            rider_phone = order.rider.get("phone")
        elif order.rider_user:
            r_prof = getattr(order.rider_user, "profile", None)
            rider_name = (r_prof.full_name if r_prof and r_prof.full_name else order.rider_user.get_full_name()) or order.rider_user.username
            rider_phone = r_prof.phone if r_prof else ""

        status_msg = f"Aapka order {order.order_code} ka status hai: {label}. Total: PKR {order.total}."
        if rider_name and order.status in [Order.STATUS_PACKED, Order.STATUS_ONWAY]:
            status_msg += f" Rider {rider_name} (Phone: {rider_phone or 'Active'}) aapka order deliver kar raha hai."

        return Response({
            "found": True,
            "order_code": order.order_code,
            "status": order.status,
            "status_label": label,
            "total": float(order.total),
            "rider_name": rider_name or "Assign nahi hua abhi",
            "rider_phone": rider_phone or "",
            "message": status_msg,
        })


# ── Status transitions ─────────────────────────────────────────────────────────

class OrderStatusView(APIView):
    """
    PATCH /api/orders/{id}/status/

    Role matrix (forward-only still enforced by StatusSerializer):
      customer  → 403
      kitchen   → confirmed→kitchen, kitchen→packed only
      rider     → packed→onway, onway→delivered, only on assigned order
      admin     → any valid forward transition

    Special: status="cancelled" is handled separately (not forward-only).
    """

    permission_classes = [IsAuthenticated, CanAdvanceStatus]

    def patch(self, request, pk):
        order = _fetch_order_or_404(pk)
        if order is None:
            return Response({"detail": "Order nahi mila."}, status=status.HTTP_404_NOT_FOUND)

        request.order = order

        if not CanAdvanceStatus().has_permission(request, self):
            return Response(
                {"detail": CanAdvanceStatus.message},
                status=status.HTTP_403_FORBIDDEN,
            )

        if order.status == Order.STATUS_DELIVERED:
            return Response(
                {"detail": "Order already delivered — no further transitions."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Special rider accept handling
        requested_status = request.data.get("status")

        # Handle cancellation separately (not in the forward-only STATUS_ORDER chain)
        if requested_status == Order.STATUS_CANCELLED:
            note = request.data.get("note", "")
            order.status = Order.STATUS_CANCELLED
            order.cancelled_at = timezone.now()
            order.cancel_reason = note
            order.save(update_fields=["status", "cancelled_at", "cancel_reason", "updated_at"])
            from .models import OrderEvent
            OrderEvent.objects.create(
                order=order,
                label="Order cancelled",
                note=note,
                actor="Owner",
                actor_user=request.user,
            )
            try:
                _broadcast_order_update(order)
            except Exception:
                pass
            return Response({
                "order_code": order.order_code,
                "status": order.status,
                "updated_at": order.updated_at,
            })

        user_role = getattr(getattr(request.user, "profile", None), "role", "")
        if user_role == Role.RIDER and requested_status == Order.STATUS_ONWAY:
            order.rider_user = request.user
            if not order.rider:
                rp = getattr(request.user, "profile", None)
                order.rider = {
                    "name": rp.full_name or request.user.username if rp else request.user.username,
                    "phone": rp.phone if rp else "",
                    "bike": "",
                }

            # If still in confirmed/kitchen/packed, mark as accepted (no status change)
            if order.status in (Order.STATUS_CONFIRMED, Order.STATUS_KITCHEN, Order.STATUS_PACKED):
                from .models import OrderEvent
                order.accepted_at = timezone.now()
                order.save(update_fields=["rider_user", "rider", "accepted_at", "updated_at"])
                OrderEvent.objects.create(
                    order=order,
                    label="Rider accepted order",
                    note=order.rider.get("name", ""),
                    actor=f"Rider ({order.rider.get('name', '')})",
                    actor_user=request.user,
                )
                try:
                    _broadcast_order_update(order)
                except Exception:
                    pass
                return Response({
                    "order_code": order.order_code,
                    "status": order.status,
                    "accepted_at": order.accepted_at.isoformat() if order.accepted_at else None,
                    "updated_at": order.updated_at,
                })

        serializer = StatusSerializer(
            data=request.data,
            context={"order": order, "request": request},
        )
        if serializer.is_valid():
            updated = serializer.save()
            # Broadcast to any connected WS clients
            try:
                _broadcast_order_update(updated)
            except Exception:
                pass   # don't fail the HTTP response if Channels is unreachable

            return Response({
                "order_code": updated.order_code,
                "status":     updated.status,
                "updated_at": updated.updated_at,
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OrderDeleteView(APIView):
    """
    DELETE /api/orders/{id}/
    Admin-only permanent delete. Cascades OrderItem + OrderEvent rows.
    """

    permission_classes = [IsAuthenticated, IsAdminRole]

    def delete(self, request, pk):
        order = _fetch_order_or_404(pk)
        if order is None:
            return Response({"detail": "Order nahi mila."}, status=status.HTTP_404_NOT_FOUND)

        order_code = order.order_code
        order_id = order.id
        order.delete()
        return Response(
            {"detail": f"Order {order_code} deleted.", "id": order_id, "order_code": order_code},
            status=status.HTTP_200_OK,
        )


# ── Assign rider ───────────────────────────────────────────────────────────────

class AssignRiderView(APIView):
    """
    POST /api/orders/{id}/assign-rider/

    Admin-only. Body: {"rider_user_id": <int>}
    - Validates target user exists and has role=rider.
    - Sets order.rider_user and builds the display rider JSON blob from their Profile.
    """

    permission_classes = [IsAuthenticated, CanAssignRider]

    def post(self, request, pk):
        order = _fetch_order_or_404(pk)
        if order is None:
            return Response({"detail": "Order nahi mila."}, status=status.HTTP_404_NOT_FOUND)

        rider_user_id = request.data.get("rider_user_id")
        if not rider_user_id:
            return Response(
                {"detail": "rider_user_id required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            rider_user = User.objects.select_related("profile").get(pk=rider_user_id)
        except User.DoesNotExist:
            return Response({"detail": "Rider user nahi mila."}, status=status.HTTP_404_NOT_FOUND)

        try:
            rider_profile = rider_user.profile
        except Exception:
            return Response(
                {"detail": "Is user ka profile nahi hai."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if rider_profile.role != Role.RIDER:
            return Response(
                {
                    "detail": (
                        f"User '{rider_user.username}' ka role '{rider_profile.role}' hai, "
                        "'rider' nahi. Sirf rider role wala user assign ho sakta hai."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Build the display JSON blob from the rider's Profile
        order.rider_user = rider_user
        order.rider = {
            "name":  rider_profile.full_name or rider_user.username,
            "phone": rider_profile.phone,
            "bike":  request.data.get("bike", ""),    # optional override from request
        }
        order.save(update_fields=["rider_user", "rider", "updated_at"])

        # Record timeline OrderEvent with exact label "Assigned to rider"
        from .models import OrderEvent
        actor_name = getattr(getattr(request.user, "profile", None), "full_name", "") or request.user.username
        user_role  = getattr(getattr(request.user, "profile", None), "role", "admin")
        actor_label = f"{actor_name} ({user_role.capitalize()})" if user_role == Role.KITCHEN else (actor_name or "Owner")

        OrderEvent.objects.create(
            order=order,
            label="Assigned to rider",
            note=order.rider["name"],
            actor=actor_label,
            actor_user=request.user,
        )

        return Response({
            "detail":       "Rider assign ho gaya.",
            "order_code":   order.order_code,
            "rider":        order.rider,
            "rider_user_id": rider_user.id,
            "assigned_by":  actor_label,
        })


# ── Rider reject order ──────────────────────────────────────────────────────

class RiderRejectView(APIView):
    """
    POST /api/orders/{id}/reject/
    Rider-only. Unassigns the rider from the order.
    Body (optional): {"reason": "..."}
    Only the assigned rider may reject their own order.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        order = _fetch_order_or_404(pk)
        if order is None:
            return Response({"detail": "Order nahi mila."}, status=status.HTTP_404_NOT_FOUND)

        # Only the assigned rider can reject
        if order.rider_user_id != request.user.id:
            return Response(
                {"detail": "Sirf assigned rider order reject kar sakta hai."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Cannot reject already delivered/cancelled orders
        if order.status in (Order.STATUS_DELIVERED, Order.STATUS_CANCELLED):
            return Response(
                {"detail": f"Order already {order.status} — cannot reject."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reason = request.data.get("reason", "")

        with transaction.atomic():
            order.rider_user = None
            order.rider = None
            order.save(update_fields=["rider_user", "rider", "updated_at"])

            actor_name = getattr(
                getattr(request.user, "profile", None), "full_name", ""
            ) or request.user.username

            from .models import OrderEvent
            OrderEvent.objects.create(
                order=order,
                label="Rider rejected the order",
                note=reason or None,
                actor=f"Rider ({actor_name})",
                actor_user=request.user,
            )

        return Response({
            "detail": "Order reject ho gaya.",
            "order_code": order.order_code,
        })


# ── Rider location push ────────────────────────────────────────────────────────

class RiderLocationView(APIView):
    """
    GET  /api/orders/{id}/rider-location/
         Customer (order owner) or admin polls the last known rider position.
         Returns {lat, lng, status, eta_minutes, updated_at} or 204 if no data yet.

    POST /api/orders/{id}/rider-location/
         Only the assigned rider_user may POST.
         Only allowed when status == 'onway'.
         Body: {"lat": float, "lng": float, "eta_minutes": int (optional)}
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        order = _fetch_order_or_404(pk)
        if order is None:
            return Response({"detail": "Order nahi mila."}, status=status.HTTP_404_NOT_FOUND)

        is_owner = (order.user_id == request.user.id)
        is_admin_or_staff = request.user.is_staff or getattr(
            getattr(request.user, "profile", None), "role", ""
        ) == Role.ADMIN

        if not (is_owner or is_admin_or_staff):
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        lat = order.rider_lat
        lng = order.rider_lng

        if lat is None or lng is None:
            rp = getattr(order.rider_user, "rider_profile", None) if order.rider_user else None
            if rp and rp.lat is not None and rp.lng is not None:
                lat = rp.lat
                lng = rp.lng

        if lat is None or lng is None:
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response({
            "lat": lat,
            "lng": lng,
            "status": order.status,
            "eta_minutes": order.eta_minutes,
            "updated_at": order.updated_at,
        })

    def post(self, request, pk):
        # Only assigned rider may push location
        order = _fetch_order_or_404(pk)
        if order is None:
            return Response({"detail": "Order nahi mila."}, status=status.HTTP_404_NOT_FOUND)

        # Attach so IsAssignedRider can check
        request.order = order

        if not IsAssignedRider().has_permission(request, self):
            return Response(
                {"detail": IsAssignedRider.message},
                status=status.HTTP_403_FORBIDDEN,
            )

        if order.status != Order.STATUS_ONWAY:
            return Response(
                {
                    "detail": (
                        f"Location sirf 'onway' status par push ho sakti hai. "
                        f"Order abhi '{order.status}' hai."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        lat = request.data.get("lat")
        lng = request.data.get("lng")
        if lat is None or lng is None:
            return Response(
                {"detail": "lat aur lng dono required hain."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            lat = float(lat)
            lng = float(lng)
        except (TypeError, ValueError):
            return Response(
                {"detail": "lat aur lng numbers hone chahiye."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        update_fields = ["rider_lat", "rider_lng", "updated_at"]
        order.rider_lat = lat
        order.rider_lng = lng

        eta = request.data.get("eta_minutes")
        if eta is not None:
            try:
                order.eta_minutes = int(eta)
                update_fields.append("eta_minutes")
            except (TypeError, ValueError):
                pass   # ignore invalid eta silently

        order.save(update_fields=update_fields)

        # Broadcast to connected WS clients
        try:
            _broadcast_order_update(order)
        except Exception:
            pass

        return Response({
            "detail":      "Location update ho gai.",
            "rider_lat":   order.rider_lat,
            "rider_lng":   order.rider_lng,
            "eta_minutes": order.eta_minutes,
        })


# ── Customer rate order ───────────────────────────────────────────────────────

class OrderRateView(APIView):
    """
    POST /api/orders/{id}/rate/
    Customer only on their own delivered order. Body: {"rating": 1-5}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        order = _fetch_order_or_404(pk)
        if order is None:
            return Response({"detail": "Order nahi mila."}, status=status.HTTP_404_NOT_FOUND)

        if order.user_id != request.user.id and not request.user.is_staff:
            return Response({"detail": "Sirf apna order rate kar sakte hain."}, status=status.HTTP_403_FORBIDDEN)

        if order.status != Order.STATUS_DELIVERED:
            return Response({"detail": "Sirf delivered orders rate ho sakte hain."}, status=status.HTTP_400_BAD_REQUEST)

        if order.rating is not None:
            return Response({"detail": "Yeh order pehle se rate ho chuka hai."}, status=status.HTTP_400_BAD_REQUEST)

        from .serializers import OrderRatingSerializer
        serializer = OrderRatingSerializer(data=request.data, context={"order": order})
        if serializer.is_valid():
            order.rating = serializer.validated_data["rating"]
            order.save(update_fields=["rating", "updated_at"])

            from .models import OrderEvent
            OrderEvent.objects.create(
                order=order,
                label=f"Customer rated {order.rating}★",
                note="",
                actor=getattr(request.user.profile, "full_name", "") or request.user.username,
                actor_user=request.user,
            )

            return Response({
                "detail": "Rating save ho gai. Shukriya!",
                "order_code": order.order_code,
                "rating": order.rating,
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── Order controls ────────────────────────────────────────────────────────────

class OrderControlsView(APIView):
    """
    PATCH /api/orders/{id}/controls/
    Admin-only. Body: {"priority": "rush", "eta_minutes": 25, "internal_notes": "...", "discount": 100.00}
    """

    permission_classes = [IsAuthenticated, IsAdminRole]

    def patch(self, request, pk):
        order = _fetch_order_or_404(pk)
        if order is None:
            return Response({"detail": "Order nahi mila."}, status=status.HTTP_404_NOT_FOUND)

        from .serializers import OrderControlsSerializer
        serializer = OrderControlsSerializer(
            order,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        if serializer.is_valid():
            updated = serializer.save()
            return Response(OrderSerializer(updated).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── Admin endpoints ────────────────────────────────────────────────────────────

from datetime import timedelta
from django.db.models import Sum, Count, Avg
class AdminOrderListView(APIView):
    """
    GET /api/orders/all/?status=confirmed&q=zain
    Admin & Kitchen endpoint returning all orders across all customers.
    """
    permission_classes = [IsAuthenticated, CanViewAllOrders]

    def get(self, request):
        queryset = Order.objects.select_related("user", "rider_user", "user__profile").all()
        status_filter = request.query_params.get("status")
        if status_filter and status_filter != "all":
            queryset = queryset.filter(status=status_filter)

        q = request.query_params.get("q")
        if q:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(order_code__icontains=q) |
                Q(user__username__icontains=q) |
                Q(user__profile__full_name__icontains=q) |
                Q(dish_name__icontains=q)
            )

        limit = min(int(request.query_params.get("limit", 100)), 300)
        orders = queryset[:limit]
        return Response(OrderSerializer(orders, many=True).data)


class RiderJobsView(APIView):
    """
    GET /api/orders/rider-jobs/
    Returns all orders assigned to the authenticated rider (rider_user = request.user).
    Also returns unassigned 'pool' orders so riders can self-pick from the open pool.
    Sorted newest-first.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from accounts.models import Role
        # Only riders can call this
        role = getattr(getattr(request.user, "profile", None), "role", None)
        if not (role == Role.RIDER or request.user.is_superuser):
            return Response({"detail": "Only riders can access this endpoint."}, status=403)

        # Assigned to this rider (active + completed)
        assigned = Order.objects.filter(
            rider_user=request.user
        ).order_by("-created_at")

        return Response({
            "assigned": OrderSerializer(assigned, many=True).data,
        })


class AdminAnalyticsView(APIView):
    """
    GET /api/orders/analytics/
    Admin-only analytics endpoint returning aggregated stats & Recharts metrics.
    """
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Revenue
        total_revenue = Order.objects.filter(
            status=Order.STATUS_DELIVERED
        ).aggregate(sum=Sum("total"))["sum"] or Decimal("0.00")

        # Today orders
        today_orders = Order.objects.filter(created_at__gte=today_start).count()

        # Active riders
        from accounts.models import Profile, Role
        active_riders = Profile.objects.filter(role=Role.RIDER, user__is_active=True).count()

        # Avg delivery time (delivered orders)
        delivered_orders = Order.objects.filter(
            status=Order.STATUS_DELIVERED,
            delivered_at__isnull=False,
        )
        avg_delivery_time_min = 28
        if delivered_orders.exists():
            durations = [(o.delivered_at - o.created_at).total_seconds() / 60 for o in delivered_orders]
            if durations:
                avg_delivery_time_min = round(sum(durations) / len(durations))

        # Daily chart (last 7 days)
        daily_chart = []
        for i in range(6, -1, -1):
            day_date = (now - timedelta(days=i)).date()
            day_orders = Order.objects.filter(
                created_at__date=day_date
            )
            day_rev = day_orders.filter(status=Order.STATUS_DELIVERED).aggregate(sum=Sum("total"))["sum"] or Decimal("0.00")
            daily_chart.append({
                "date": day_date.strftime("%b %d"),
                "revenue": float(day_rev),
                "orders": day_orders.count(),
            })

        # Payment breakdown
        payment_tally = {
            "cod": Order.objects.filter(payment=Order.PAYMENT_COD).count(),
            "jazzcash": Order.objects.filter(payment=Order.PAYMENT_JAZZCASH).count(),
            "easypaisa": Order.objects.filter(payment=Order.PAYMENT_EASYPAISA).count(),
            "card": Order.objects.filter(payment=Order.PAYMENT_CARD).count(),
        }

        # Recent orders
        recent_orders = Order.objects.all()[:5]

        return Response({
            "total_revenue": float(total_revenue),
            "today_orders": today_orders,
            "active_riders": active_riders,
            "avg_delivery_time_min": avg_delivery_time_min,
            "daily_revenue_chart": daily_chart,
            "payment_method_breakdown": payment_tally,
            "recent_orders": OrderSerializer(recent_orders, many=True).data,
        })


class AdminPaymentsView(APIView):
    """
    GET /api/orders/payments/?payment_status=pending
    Admin-only payments ledger.
    """
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        queryset = Order.objects.select_related("user", "verified_by").all()
        pay_status = request.query_params.get("payment_status")
        if pay_status:
            queryset = queryset.filter(payment_status=pay_status)

        limit = min(int(request.query_params.get("limit", 50)), 200)
        orders = queryset[:limit]
        return Response(OrderSerializer(orders, many=True).data)


class AdminPaymentVerifyView(APIView):
    """
    POST /api/orders/{id}/verify-payment/
    Admin-only. Sets payment_status = 'verified', verified_by = request.user, paid_at = now().
    """
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, pk):
        order = _fetch_order_or_404(pk)
        if order is None:
            return Response({"detail": "Order nahi mila."}, status=status.HTTP_404_NOT_FOUND)

        reference = request.data.get("reference", "")
        amount = request.data.get("amount", str(order.total))

        order.payment_status = Order.PAY_STATUS_VERIFIED
        order.amount_paid = Decimal(str(amount))
        if reference:
            order.payment_reference = reference
        order.paid_at = timezone.now()
        order.verified_by = request.user
        order.save()

        from .models import OrderEvent
        OrderEvent.objects.create(
            order=order,
            label=f"Payment verified (Rs {order.amount_paid})",
            note=f"Ref: {order.payment_reference or 'N/A'}",
            actor="Owner",
            actor_user=request.user,
        )

        return Response(OrderSerializer(order).data)


class AdminPaymentStatusView(APIView):
    """
    PATCH /api/orders/{id}/payment-status/
    Admin-only. Sets payment_status to any valid value (verified, pending, failed, refunded).
    Body: {"payment_status": "verified", "reference": "optional", "amount": "optional"}
    """
    permission_classes = [IsAuthenticated, IsAdminRole]

    def patch(self, request, pk):
        order = _fetch_order_or_404(pk)
        if order is None:
            return Response({"detail": "Order nahi mila."}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get("payment_status")
        valid_statuses = [c[0] for c in Order.PAY_STATUS_CHOICES]
        if new_status not in valid_statuses:
            return Response(
                {"detail": f"Invalid payment_status. Must be one of: {', '.join(valid_statuses)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.payment_status = new_status

        if new_status == Order.PAY_STATUS_VERIFIED:
            reference = request.data.get("reference", "")
            amount = request.data.get("amount", str(order.total))
            order.amount_paid = Decimal(str(amount))
            if reference:
                order.payment_reference = reference
            order.paid_at = timezone.now()
            order.verified_by = request.user

        elif new_status == Order.PAY_STATUS_FAILED:
            order.amount_paid = Decimal("0.00")
            order.verified_by = request.user

        elif new_status == Order.PAY_STATUS_REFUNDED:
            order.amount_paid = Decimal("0.00")
            order.verified_by = request.user

        elif new_status == Order.PAY_STATUS_PENDING:
            order.amount_paid = Decimal("0.00")
            order.paid_at = None
            order.verified_by = None

        order.save()

        from .models import OrderEvent
        OrderEvent.objects.create(
            order=order,
            label=f"Payment → {order.get_payment_status_display()}",
            note=f"Ref: {order.payment_reference or 'N/A'}",
            actor="Owner",
            actor_user=request.user,
        )

        return Response(OrderSerializer(order).data)


class AdminCustomersView(APIView):
    """
    GET /api/orders/customers/
    Admin-only customer aggregation list.
    """
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        from accounts.models import Role
        customers = User.objects.filter(profile__role=Role.CUSTOMER).select_related("profile")

        result = []
        for user in customers:
            orders = Order.objects.filter(user=user)
            total_spent = orders.filter(status=Order.STATUS_DELIVERED).aggregate(sum=Sum("total"))["sum"] or Decimal("0.00")
            last_order = orders.first()
            default_addr = user.addresses.filter(is_default=True).first() or user.addresses.first()

            result.append({
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": getattr(user.profile, "full_name", "") or user.username,
                "phone": getattr(user.profile, "phone", "") or (default_addr.phone if default_addr else ""),
                "city": default_addr.city if default_addr else "",
                "total_orders": orders.count(),
                "total_spent": float(total_spent),
                "last_order_at": last_order.created_at if last_order else None,
            })

        return Response(result)


# ── Active rider for customer live tracking ───────────────────────────────────

class ActiveRiderView(APIView):
    """
    GET /api/orders/active-rider/

    Returns the assigned caddy's profile for the customer's most recent
    in-progress order (status in confirmed / kitchen / packed / onway).
    Returns 204 if no active order or no rider assigned yet.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        order = (
            Order.objects
            .filter(
                user=request.user,
                status__in=[
                    Order.STATUS_CONFIRMED,
                    Order.STATUS_KITCHEN,
                    Order.STATUS_PACKED,
                    Order.STATUS_ONWAY,
                ],
            )
            .select_related("rider_user__profile")
            .order_by("-created_at")
            .first()
        )

        if not order or not order.rider:
            return Response(None, status=status.HTTP_204_NO_CONTENT)

        rider_profile = None
        if order.rider_user:
            rider_profile = getattr(order.rider_user, "profile", None)

        return Response({
            "id": str(order.rider_user.id) if order.rider_user else "rider",
            "name": order.rider.get("name", rider_profile.full_name if rider_profile else "Assigned Rider"),
            "phone": order.rider.get("phone", rider_profile.phone if rider_profile else ""),
            "avatar_url": rider_profile.avatar_url if rider_profile else None,
            "vehicle": order.rider.get("bike", "Honda CD-70"),
            "rating": float(order.rating) if order.rating else 4.5,
            "deliveries": 0,
            "status": order.status,
            "eta_minutes": order.eta_minutes,
        })

