from django.contrib.auth.models import User
from django.test import TestCase

from .models import Project, ProjectMembership
from .services import accessible_projects_for


class ProjectAccessTests(TestCase):
    def test_accessible_projects_include_created_and_memberships(self):
        owner = User.objects.create_user(username="owner")
        member = User.objects.create_user(username="member")
        outsider = User.objects.create_user(username="outsider")
        created = Project.objects.create(name="Created", code="created", created_by=owner)
        joined = Project.objects.create(name="Joined", code="joined", created_by=outsider)
        ProjectMembership.objects.create(project=joined, user=owner, role=ProjectMembership.ROLE_VIEWER)

        ids = set(accessible_projects_for(owner).values_list("id", flat=True))

        self.assertEqual(ids, {created.id, joined.id})
        self.assertFalse(accessible_projects_for(member).exists())
