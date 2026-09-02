from django.urls import path
from rest_framework_simplejwt.views import TokenBlacklistView

from .views import (
    # Auth
    SignupView,
    LogoutView,
    SendEmailOTPView,
    VerifyEmailOTPView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    # Profile
    ProfileView,
    ChangePasswordView,
    # Addresses
    AddressListCreateView,
    AddressDetailView,
    AddressSetDefaultView,
    # Rider
    RiderProfileView,
    RiderDutyStatusView,
    RiderLocationShareView,
    # Admin — Rider / Staff Management & Approvals
    PendingApprovalsView,
    ApproveRiderView,
    RejectRiderView,
    FleetVerifyRiderView,
    AdminRidersView,
)

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────────────────
    path("signup/",                  SignupView.as_view(),               name="auth-signup"),
    path("logout/",                  LogoutView.as_view(),               name="auth-logout"),

    # Email OTP verification (signed-in user)
    path("send-otp/",               SendEmailOTPView.as_view(),          name="auth-send-otp"),
    path("verify-otp/",             VerifyEmailOTPView.as_view(),        name="auth-verify-otp"),

    # Forgot password (public, OTP-based)
    path("password-reset/",         PasswordResetRequestView.as_view(),  name="auth-password-reset"),
    path("password-reset-confirm/", PasswordResetConfirmView.as_view(),  name="auth-password-reset-confirm"),

    # ── Profile ───────────────────────────────────────────────────────────
    path("profile/",                ProfileView.as_view(),               name="profile"),
    path("profile/change-password/",ChangePasswordView.as_view(),        name="profile-change-password"),

    # ── Rider own profile ─────────────────────────────────────────────────
    path("rider/profile/",          RiderProfileView.as_view(),          name="rider-profile"),
    path("rider/duty-status/",      RiderDutyStatusView.as_view(),       name="rider-duty-status"),
    path("rider/location-share/",   RiderLocationShareView.as_view(),    name="rider-location-share"),

    # ── Addresses ─────────────────────────────────────────────────────────
    path("addresses/",              AddressListCreateView.as_view(),     name="address-list-create"),
    path("addresses/<int:pk>/",     AddressDetailView.as_view(),         name="address-detail"),
    path("addresses/<int:pk>/set-default/", AddressSetDefaultView.as_view(), name="address-set-default"),

    # ── Admin — Rider / Staff Management & Approvals ──────────────────────
    path("admin/riders/",                              AdminRidersView.as_view(),        name="admin-riders"),
    path("admin/pending-approvals/",                   PendingApprovalsView.as_view(),   name="admin-pending-approvals"),
    path("admin/riders/<int:user_id>/approve/",        ApproveRiderView.as_view(),       name="admin-rider-approve"),
    path("admin/riders/<int:user_id>/reject/",         RejectRiderView.as_view(),        name="admin-rider-reject"),
    path("admin/riders/<int:user_id>/fleet-verify/",   FleetVerifyRiderView.as_view(),   name="admin-rider-fleet-verify"),
    path("admin/riders/<int:user_id>/verify/",         FleetVerifyRiderView.as_view(),   name="admin-rider-verify"),
]
