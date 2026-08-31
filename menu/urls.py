from django.urls import path
from .views import CategoryListView, DishDetailView, DishListView, MenuBookView

urlpatterns = [
    path("book/", MenuBookView.as_view(), name="menu-book"),
    path("categories/", CategoryListView.as_view(), name="menu-categories"),
    path("dishes/", DishListView.as_view(), name="menu-dishes"),
    path("dishes/<slug:slug>/", DishDetailView.as_view(), name="menu-dish-detail"),
]
