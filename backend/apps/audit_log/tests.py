from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import include, path
from rest_framework.test import APIClient

from .models import AuditEvent
from .services import record_event


urlpatterns = [
    path("audit/", include("apps.audit_log.urls")),
]


class RecordEventTests(TestCase):
    def test_record_event_persists_all_fields(self):
        user = get_user_model().objects.create_user(username="audited-user")

        event = record_event(
            actor=user,
            action="imagery.view",
            object_type="imagery",
            object_id=42,
            request_id="request-123",
            payload={"source": "catalog"},
            ip="2001:db8::1",
        )

        event.refresh_from_db()
        self.assertEqual(event.actor, user)
        self.assertEqual(event.object_id, "42")
        self.assertEqual(event.request_id, "request-123")
        self.assertEqual(event.payload, {"source": "catalog"})
        self.assertEqual(event.ip, "2001:db8::1")

    def test_record_event_accepts_anonymous_actor_and_isolates_default_payload(self):
        first = record_event(action="login.failed", object_type="session")
        second = record_event(action="login.failed", object_type="session")

        self.assertIsNone(first.actor)
        self.assertEqual(first.payload, {})
        self.assertEqual(second.payload, {})
        self.assertIsNot(first.payload, second.payload)


@override_settings(ROOT_URLCONF=__name__)
class AuditEventApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.user = user_model.objects.create_user(username="audit-user")
        cls.other_user = user_model.objects.create_user(username="other-user")
        cls.admin = user_model.objects.create_user(username="audit-admin", is_staff=True)
        cls.own_event = record_event(actor=cls.user, action="project.view", object_type="project", object_id="own")
        cls.other_event = record_event(actor=cls.other_user, action="project.view", object_type="project", object_id="other")
        cls.system_event = record_event(action="worker.run", object_type="worker", object_id="system")

    def setUp(self):
        self.client = APIClient()

    def test_unauthenticated_requests_are_rejected(self):
        self.assertIn(self.client.get("/audit/").status_code, (401, 403))

    def test_regular_user_only_lists_own_events(self):
        self.client.force_authenticate(self.user)

        response = self.client.get("/audit/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [self.own_event.id])

    def test_regular_user_cannot_retrieve_another_users_event(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(f"/audit/{self.other_event.id}")

        self.assertEqual(response.status_code, 404)

    def test_admin_lists_and_retrieves_all_events(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get("/audit/")
        detail = self.client.get(f"/audit/{self.other_event.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual({item["id"] for item in response.data}, {self.own_event.id, self.other_event.id, self.system_event.id})
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["id"], self.other_event.id)

    def test_api_is_read_only(self):
        self.client.force_authenticate(self.admin)

        self.assertEqual(self.client.post("/audit/", {}, format="json").status_code, 405)
        self.assertEqual(self.client.patch(f"/audit/{self.own_event.id}", {}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(f"/audit/{self.own_event.id}").status_code, 405)
