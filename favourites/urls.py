from django.urls import path
from .views import FavouriteListCreateView, FavouriteDeleteView, FavouriteMergeView

urlpatterns = [
    path("",        FavouriteListCreateView.as_view(), name="favourite-list-create"),
    path("merge/",  FavouriteMergeView.as_view(),      name="favourite-merge"),
    path("<int:pk>/", FavouriteDeleteView.as_view(),   name="favourite-delete"),
]
