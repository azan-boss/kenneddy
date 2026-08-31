from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from accounts.serializers import CustomTokenObtainPairSerializer

from django.db.models import Sum

# Django Admin Branding
admin.site.site_header = "🌙 Kennedy Moon Grill · Caddy Fleet 2.0"
admin.site.site_title = "Kennedy Caddy Admin"
admin.site.index_title = "Kitchen, Fleet & Order Operations Console"

_original_admin_index = admin.site.index

def caddy_admin_index(request, extra_context=None):
    extra = extra_context or {}
    try:
        from orders.models import Order
        from accounts.models import Profile, Role
        from django.contrib.auth.models import User
        from menu.models import Dish

        total_rev = Order.objects.filter(status=Order.STATUS_DELIVERED).aggregate(s=Sum("total"))["s"] or 0
        live_orders = Order.objects.filter(status__in=[
            Order.STATUS_CONFIRMED,
            Order.STATUS_KITCHEN,
            Order.STATUS_PACKED,
            Order.STATUS_ONWAY
        ]).count()
        pending_riders = User.objects.filter(profile__role=Role.RIDER, is_active=False).count()
        total_dishes = Dish.objects.filter(is_available=True).count()
        total_customers = Profile.objects.filter(role=Role.CUSTOMER).count()

        extra.update({
            "kpi_total_revenue": f"Rs {total_rev:,.0f}",
            "kpi_live_orders": live_orders,
            "kpi_pending_riders": pending_riders,
            "kpi_total_dishes": total_dishes,
            "kpi_total_customers": total_customers,
        })
    except Exception:
        pass
    return _original_admin_index(request, extra_context=extra)

admin.site.index = caddy_admin_index


urlpatterns = [
    # Django admin
    path("admin/", admin.site.urls),

    # JWT auth — login + refresh
    path("api/auth/login/", TokenObtainPairView.as_view(serializer_class=CustomTokenObtainPairSerializer), name="token-obtain"),
    path("auth/login/", TokenObtainPairView.as_view(serializer_class=CustomTokenObtainPairSerializer), name="token-obtain-alias"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token-refresh"),

    # Accounts app — signup + profile + addresses + admin rider approval
    path("api/auth/", include("accounts.urls")),      # → /api/auth/signup/
    path("api/",      include("accounts.urls")),      # → /api/profile/, /api/addresses/, /api/admin/riders/...

    # Menu app — categories + dishes
    path("api/menu/", include("menu.urls")),          # → /api/menu/categories/, /api/menu/dishes/

    # Orders app
    path("api/orders/", include("orders.urls")),      # → /api/orders/ + /api/orders/{id}/status/

    # Favourites app
    path("api/favourites/", include("favourites.urls")),  # → /api/favourites/ + merge/ + {id}/

    # ElevenLabs AI Voice Agent — signed URL for secure WebRTC sessions
    path("api/elevenlabs/signed-url/", __import__("elevenlabs_views", fromlist=["ElevenLabsSignedUrlView"]).ElevenLabsSignedUrlView.as_view(), name="elevenlabs-signed-url"),
]


from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns += [
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema")),
]