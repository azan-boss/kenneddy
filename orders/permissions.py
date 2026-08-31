"""
Role-based permission classes for order status transitions.

Role matrix (forward-only transitions still enforced by StatusSerializer):
  customer  → 403 always
  kitchen   → confirmed→kitchen, kitchen→packed only
  rider     → packed→onway, onway→delivered ONLY on orders assigned to them
  admin     → any valid forward transition
  superuser → same as admin
"""
from rest_framework.permissions import BasePermission

from accounts.models import Role


# Which transitions each role is allowed to initiate
_KITCHEN_ALLOWED = {"confirmed", "kitchen"}   # may move FROM these statuses
_RIDER_ALLOWED   = {"packed", "onway"}         # may move FROM these statuses


def _get_role(user):
    """Return the user's Profile role, or None if no profile exists."""
    try:
        return user.profile.role
    except Exception:
        return None


class CanAdvanceStatus(BasePermission):
    """
    Permission check for PATCH /api/orders/{id}/status/.

    Must be used AFTER the view has already fetched `order` and attached it
    to the request as `request.order` (set in OrderStatusView.patch before
    calling check_permissions — see views.py).
    """

    message = "Bu endpoint ke liye aapka role authorized nahi hai."

    def has_permission(self, request, view):
        # Superusers bypass everything
        if request.user.is_superuser:
            return True

        role = _get_role(request.user)

        if role == Role.ADMIN:
            return True

        if role == Role.KITCHEN:
            # Kitchen staff can only push orders they're responsible for:
            # confirmed→kitchen and kitchen→packed
            order = getattr(request, "order", None)
            if order is None:
                return True   # pre-fetch guard — actual check in view
            return order.status in _KITCHEN_ALLOWED

        if role == Role.RIDER:
            order = getattr(request, "order", None)
            if order is None:
                return True
            # Must be the assigned rider (or rider accepting an unassigned/offered order)
            is_assigned = (order.rider_user_id == request.user.id or order.rider_user_id is None)
            in_band     = (order.status in ["confirmed", "kitchen", "packed", "onway"])
            return is_assigned and in_band

        # customer (or unknown role) → 403
        return False


class IsAdminRole(BasePermission):
    """Allows access only to admin-role users or Django superusers."""

    message = "Sirf admin yeh kaam kar sakta hai."

    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        return _get_role(request.user) == Role.ADMIN


class CanAssignRider(BasePermission):
    """Allows admin or kitchen staff (or superuser) to assign riders to orders."""

    message = "Sirf admin ya kitchen staff rider assign kar sakte hain."

    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        role = _get_role(request.user)
        return role in (Role.ADMIN, Role.KITCHEN)


class CanViewAllOrders(BasePermission):
    """Allows admin or kitchen staff to view all orders."""

    message = "Sirf admin ya kitchen staff tamam orders dekh sakte hain."

    def has_permission(self, request, view):
        if request.user.is_superuser or request.user.is_staff:
            return True
        role = _get_role(request.user)
        return role in (Role.ADMIN, Role.KITCHEN)


class IsAssignedRider(BasePermission):
    """
    Rider-location endpoint: only the order's assigned rider_user may POST.
    Attach `request.order` in the view before calling check_permissions.
    """

    message = "Sirf assigned rider location push kar sakta hai."

    def has_permission(self, request, view):
        order = getattr(request, "order", None)
        if order is None:
            return True
        return order.rider_user_id == request.user.id
