import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import include, path
from rest_framework.test import APIClient


urlpatterns = [
    path("api/auth/", include("apps.accounts.urls")),
]


@override_settings(
    ROOT_URLCONF="apps.accounts.tests",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class AuthFlowTests(TestCase):
    """Registration, user administration and password management."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user("admin", password="admin-pass-123", is_staff=True)
        self.user = User.objects.create_user("alice", password="alice-pass-123")

    # ---------- registration ----------

    def test_open_registration_creates_and_logs_in_regular_user(self):
        response = self.client.post(
            "/api/auth/register",
            {"username": "bob", "password": "a-strong-pass-1", "email": "bob@example.com"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["is_staff"])
        user = User.objects.get(username="bob")
        self.assertEqual(user.email, "bob@example.com")
        # Registered users are logged in immediately: /me reflects the session.
        self.assertEqual(self.client.get("/api/auth/me").data["username"], "bob")

    def test_registration_rejects_duplicate_username(self):
        response = self.client.post(
            "/api/auth/register",
            {"username": "Alice", "password": "a-strong-pass-1"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("用户名", str(response.data))

    def test_registration_rejects_weak_password(self):
        response = self.client.post(
            "/api/auth/register",
            {"username": "weak", "password": "123"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    # ---------- login guards ----------

    def test_login_rejects_disabled_account(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(
            "/api/auth/login",
            {"username": "alice", "password": "alice-pass-123"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    # ---------- user administration ----------

    def test_user_management_requires_staff(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/auth/users").status_code, 403)

    def test_admin_lists_creates_and_updates_users(self):
        self.client.force_authenticate(self.admin)

        listing = self.client.get("/api/auth/users")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.data), 2)

        created = self.client.post(
            "/api/auth/users",
            {"username": "carol", "password": "carol-pass-123", "is_staff": False},
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)

        promoted = self.client.patch(
            f"/api/auth/users/{created.data['id']}",
            {"is_staff": True},
            content_type="application/json",
        )
        self.assertEqual(promoted.status_code, 200)
        self.assertTrue(promoted.data["is_staff"])

        disabled = self.client.patch(
            f"/api/auth/users/{created.data['id']}",
            {"is_active": False},
            content_type="application/json",
        )
        self.assertEqual(disabled.status_code, 200)
        self.assertFalse(disabled.data["is_active"])

        removed = self.client.delete(f"/api/auth/users/{created.data['id']}")
        self.assertEqual(removed.status_code, 204)
        self.assertFalse(User.objects.filter(username="carol").exists())

    def test_admin_cannot_demote_disable_or_delete_self(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.patch(f"/api/auth/users/{self.admin.pk}", {"is_staff": False}, content_type="application/json").status_code,
            400,
        )
        self.assertEqual(
            self.client.patch(f"/api/auth/users/{self.admin.pk}", {"is_active": False}, content_type="application/json").status_code,
            400,
        )
        self.assertEqual(self.client.delete(f"/api/auth/users/{self.admin.pk}").status_code, 400)

    def test_admin_can_reset_user_password(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            f"/api/auth/users/{self.user.pk}/password",
            {"new_password": "reset-pass-123"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("reset-pass-123"))

    # ---------- self-service password ----------

    def test_user_changes_own_password_and_session_survives(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/auth/password",
            {"current_password": "alice-pass-123", "new_password": "new-pass-456"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-pass-456"))
        # Session survives the password change.
        self.assertEqual(self.client.get("/api/auth/me").data["username"], "alice")

    def test_password_change_rejects_wrong_current_password(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/auth/password",
            {"current_password": "wrong", "new_password": "new-pass-456"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
