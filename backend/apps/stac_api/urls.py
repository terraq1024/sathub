from django.urls import path

from .views import CollectionItemsView, CollectionView, ItemView, RootView, SearchView


urlpatterns = [
    path("", RootView.as_view()),
    path("collections", CollectionView.as_view()),
    path("collections/sathub-imagery", CollectionView.as_view()),
    path("collections/sathub-imagery/items", CollectionItemsView.as_view()),
    path("collections/sathub-imagery/items/<str:item_id>", ItemView.as_view()),
    path("items/<str:item_id>", ItemView.as_view()),
    path("search", SearchView.as_view()),
]
