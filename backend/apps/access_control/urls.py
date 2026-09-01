from django.urls import path

from .views import SignAssetView, SignedAssetView, TokenListCreateView, TokenRevokeView


urlpatterns = [
    path("tokens", TokenListCreateView.as_view()),
    path("tokens/<int:token_id>", TokenRevokeView.as_view()),
    path("assets/sign", SignAssetView.as_view()),
    path("signed-assets/<str:image_id>/<str:role>", SignedAssetView.as_view()),
]
