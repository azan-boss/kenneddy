from django.urls import path
from .views import (
    OrderListCreateView,
    VoiceOrderCreateView,
    VoiceOrderStatusView,
    OrderStatusView,
    OrderDeleteView,
    AssignRiderView,
    RiderRejectView,
    RiderLocationView,
    OrderRateView,
    OrderControlsView,
    AdminOrderListView,
    AdminAnalyticsView,
    AdminPaymentsView,
    AdminPaymentVerifyView,
    AdminPaymentStatusView,
    AdminCustomersView,
    ActiveRiderView,
    RiderJobsView,
)

urlpatterns = [
    path("",                      OrderListCreateView.as_view(),   name="order-list-create"),
    path("voice-order/",          VoiceOrderCreateView.as_view(),  name="order-voice-create"),
    path("voice-status/",         VoiceOrderStatusView.as_view(),  name="order-voice-status"),
    path("all/",                  AdminOrderListView.as_view(),    name="admin-order-list"),
    path("rider-jobs/",           RiderJobsView.as_view(),         name="rider-jobs"),
    path("analytics/",            AdminAnalyticsView.as_view(),    name="admin-analytics"),
    path("payments/",             AdminPaymentsView.as_view(),     name="admin-payments"),
    path("customers/",            AdminCustomersView.as_view(),    name="admin-customers"),
    path("active-rider/",         ActiveRiderView.as_view(),       name="order-active-rider"),
    path("<int:pk>/status/",      OrderStatusView.as_view(),       name="order-status"),
    path("<int:pk>/assign-rider/",AssignRiderView.as_view(),       name="order-assign-rider"),
    path("<int:pk>/reject/",      RiderRejectView.as_view(),       name="order-reject"),
    path("<int:pk>/rider-location/", RiderLocationView.as_view(),  name="order-rider-location"),
    path("<int:pk>/rate/",        OrderRateView.as_view(),         name="order-rate"),
    path("<int:pk>/controls/",    OrderControlsView.as_view(),     name="order-controls"),
    path("<int:pk>/verify-payment/", AdminPaymentVerifyView.as_view(), name="admin-payment-verify"),
    path("<int:pk>/payment-status/", AdminPaymentStatusView.as_view(), name="admin-payment-status"),
    path("<int:pk>/",             OrderDeleteView.as_view(),       name="order-delete"),
]


