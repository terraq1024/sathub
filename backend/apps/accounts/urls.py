from django.urls import path

from .views import (
    AdminPasswordResetView,
    CapabilitiesView,
    ChangePasswordView,
    CsrfView,
    LoginView,
    LogoutView,
    MeView,
    RegisterView,
    UserDetailView,
    UserListView,
)


urlpatterns = [
    path("csrf", CsrfView.as_view()),
    path("login", LoginView.as_view()),
    path("logout", LogoutView.as_view()),
    path("me", MeView.as_view()),
    path("capabilities", CapabilitiesView.as_view()),
    path("register", RegisterView.as_view()),
    path("password", ChangePasswordView.as_view()),
    path("users", UserListView.as_view()),
    path("users/<int:user_id>", UserDetailView.as_view()),
    path("users/<int:user_id>/password", AdminPasswordResetView.as_view()),
]
