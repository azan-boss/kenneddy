"""
WebSocket consumer for live order tracking.

Connection URL: ws://<host>/ws/orders/<order_id>/?token=<jwt_access_token>

Auth:
  - JWT validated by JwtAuthMiddleware before reaching this consumer.
  - On connect: verifies scope["user"] is either the order's customer OR
    its assigned rider_user. Everyone else is rejected (close code 4003).

Data flow:
  - Rider POSTs location to /api/orders/{id}/rider-location/ (every ~7 s).
  - That view calls channel_layer.group_send("order_{id}", {...}).
  - This consumer receives the group message and forwards it to the WS client.
  - The WS client never sends any data — it's receive-only.

Message shape sent to client:
  {
    "status":      "onway",
    "rider_lat":   31.5204,
    "rider_lng":   74.3587,
    "eta_minutes": 18
  }
"""
import json

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _get_order(order_id):
    """Fetch Order with related user + rider_user in a single query."""
    from orders.models import Order
    try:
        return Order.objects.select_related("user", "rider_user").get(pk=order_id)
    except Order.DoesNotExist:
        return None


class OrderTrackingConsumer(AsyncJsonWebsocketConsumer):

    # ── connection ──────────────────────────────────────────────────────────

    async def connect(self):
        user = self.scope.get("user")

        # Reject anonymous / unauthenticated connections
        if user is None or isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close(code=4001)   # 4001 = Unauthorized
            return

        order_id = self.scope["url_route"]["kwargs"]["order_id"]
        order    = await _get_order(order_id)

        if order is None:
            await self.close(code=4004)   # 4004 = Not Found
            return

        # Only the customer who placed the order OR the assigned rider may connect
        is_customer = (order.user_id == user.id)
        is_rider    = (order.rider_user_id is not None and order.rider_user_id == user.id)

        # Admins / kitchen staff can also observe (is_staff covers Django admin users)
        is_staff    = user.is_staff or user.is_superuser

        if not (is_customer or is_rider or is_staff):
            await self.close(code=4003)   # 4003 = Forbidden
            return

        self.group_name = f"order_{order_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    # ── disconnect ──────────────────────────────────────────────────────────

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # ── receive (clients don't send — ignore silently) ──────────────────────

    async def receive_json(self, content, **kwargs):
        pass   # read-only stream; client messages are ignored

    # ── group message handler ───────────────────────────────────────────────

    async def order_update(self, event):
        """
        Called when channel_layer.group_send sends an "order.update" type message.
        Channels converts the dot to underscore when routing to the handler.
        Forwards only the fields the frontend map/ETA widget needs.
        """
        await self.send_json({
            "status":      event["status"],
            "rider_lat":   event["rider_lat"],
            "rider_lng":   event["rider_lng"],
            "eta_minutes": event["eta_minutes"],
        })
