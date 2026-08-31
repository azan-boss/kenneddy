from django.urls import path
from .views import (
    SignupView,
    ProfileView,
    AddressListCreateView,
    AddressDetailView,
    AddressSetDefaultView,
    PendingApprovalsView,
    ApproveRiderView,
    RejectRiderView,
    FleetVerifyRiderView,
    RiderProfileView,
    RiderDutyStatusView,
    RiderLocationShareView,
    AdminRidersView,
)

urlpatterns = [
    # Auth
    path("signup/", SignupView.as_view(), name="auth-signup"),

    # Profile
    path("profile/", ProfileView.as_view(), name="profile"),

    # Rider own profile
    path("rider/profile/", RiderProfileView.as_view(), name="rider-profile"),
    path("rider/duty-status/", RiderDutyStatusView.as_view(), name="rider-duty-status"),
    path("rider/location-share/", RiderLocationShareView.as_view(), name="rider-location-share"),

    # Addresses
    path("addresses/", AddressListCreateView.as_view(), name="address-list-create"),
    path("addresses/<int:pk>/", AddressDetailView.as_view(), name="address-detail"),
    path("addresses/<int:pk>/set-default/", AddressSetDefaultView.as_view(), name="address-set-default"),

    # Admin — Rider / Staff Management & Approvals
    path("admin/riders/", AdminRidersView.as_view(), name="admin-riders"),
    path("admin/pending-approvals/", PendingApprovalsView.as_view(), name="admin-pending-approvals"),
    path("admin/riders/<int:user_id>/approve/", ApproveRiderView.as_view(), name="admin-rider-approve"),
    path("admin/riders/<int:user_id>/reject/", RejectRiderView.as_view(), name="admin-rider-reject"),
    path("admin/riders/<int:user_id>/fleet-verify/", FleetVerifyRiderView.as_view(), name="admin-rider-fleet-verify"),
    path("admin/riders/<int:user_id>/verify/", FleetVerifyRiderView.as_view(), name="admin-rider-verify"),
]
