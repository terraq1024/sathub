import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from rest_framework.test import APIClient

from .services import derived_parent_code, geometry_bbox, normalize_gb_code, point_in_geometry


class CatalogGeometryTests(SimpleTestCase):
    geometry = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]]],
    }

    def test_geometry_helpers_and_code_normalization(self):
        self.assertEqual(geometry_bbox(self.geometry), [0.0, 0.0, 4.0, 4.0])
        self.assertTrue(point_in_geometry([2, 2], self.geometry))
        self.assertFalse(point_in_geometry([8, 8], self.geometry))
        self.assertEqual(normalize_gb_code("156110000"), "156110000")
        self.assertEqual(derived_parent_code("156110101", "county"), "156110100")
        self.assertEqual(derived_parent_code("156110100", "city"), "156110000")

    def test_multipolygon_bbox(self):
        geometry = {"type": "MultiPolygon", "coordinates": [[[[1, 2], [3, 2], [3, 4], [1, 2]]], [[[8, 9], [10, 9], [10, 11], [8, 9]]]]}
        self.assertEqual(geometry_bbox(geometry), [1.0, 2.0, 10.0, 11.0])


class AdminBoundaryCommandTests(TestCase):
    def test_import_command_filters_and_builds_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            feature = lambda name, gb, geometry: {"type": "Feature", "properties": {"name": name, "gb": gb}, "geometry": geometry}
            polygon = lambda x, y: {"type": "Polygon", "coordinates": [[[x, y], [x + 5, y], [x + 5, y + 5], [x, y], [x, y]]]}
            for filename, features in {
                "中国_省.geojson": [feature("安徽省", "110000", polygon(0, 0))],
                "中国_市.geojson": [feature("合肥市", "110100", polygon(1, 1))],
                "中国_县.geojson": [feature("肥东县", "110101", polygon(2, 2)), feature("境界线", "110199", polygon(2, 2)), {"type": "Feature", "properties": {"name": "河流"}, "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}],
            }.items():
                (root / filename).write_text(json.dumps({"type": "FeatureCollection", "crs": {"name": "EPSG:4490"}, "features": features}, ensure_ascii=False), encoding="utf-8")
            call_command("import_admin_boundaries", str(root), source_version="test-2026")
            from .models import AdministrativeUnit

            city = AdministrativeUnit.objects.get(level="city", name="合肥市")
            county = AdministrativeUnit.objects.get(level="county", name="肥东县")
            self.assertEqual(city.parent_id, AdministrativeUnit.objects.get(level="province", name="安徽省").pk)
            self.assertEqual(county.parent_id, city.pk)
            self.assertEqual(AdministrativeUnit.objects.count(), 3)


class CatalogGovernanceApiTests(TransactionTestCase):
    def setUp(self):
        self._ensure_current_imagery_columns_for_legacy_migrations()
        self.user = User.objects.create_user(username="catalog-admin", password="p", is_staff=True)
        self.imagery = self._create_imagery()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @staticmethod
    def _ensure_current_imagery_columns_for_legacy_migrations():
        """Keep this app's isolated tests compatible with the repository's old imagery migrations."""
        from apps.imagery.models import ImageryRecord

        existing = {column.name for column in connection.introspection.get_table_description(connection.cursor(), ImageryRecord._meta.db_table)}
        missing = [ImageryRecord._meta.get_field(name) for name in ("cog_status", "cog_path", "cog_error", "cog_updated_at") if name not in existing]
        if missing:
            with connection.schema_editor() as schema_editor:
                for field in missing:
                    schema_editor.add_field(ImageryRecord, field)

    def _create_imagery(self):
        from apps.imagery.models import ImageryRecord

        return ImageryRecord.objects.create(
            id="catalog-image",
            scene_key="catalog-scene",
            identity_hash="catalog-hash",
            stac_id="catalog-stac",
            source_name="catalog.tif",
            first_uploaded_by=self.user,
            acquisition_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            is_archived=False,
        )

    def test_crud_associate_and_query_imagery_ids(self):
        classification_response = self.client.post("/classifications", {"name": "研发数据", "code": "research"}, format="json")
        tag_response = self.client.post("/tags", {"name": "售前", "color": "#f00"}, format="json")
        self.assertEqual(classification_response.status_code, 201, classification_response.data)
        self.assertEqual(tag_response.status_code, 201, tag_response.data)
        classification_id = classification_response.data["id"]
        tag_id = tag_response.data["id"]

        association_response = self.client.post(
            "/associations",
            {"object_type": "imagery", "object_ids": [self.imagery.pk], "classification_ids": [classification_id], "tag_ids": [tag_id]},
            format="json",
        )
        self.assertEqual(association_response.status_code, 200)
        filtered = self.client.get(f"/imagery-ids?classification_ids={classification_id}&tag_ids={tag_id}")
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.data["imagery_ids"], [self.imagery.pk])
        detail = self.client.get(f"/imagery/{self.imagery.pk}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["tags"][0]["tag_name"], "售前")

    def test_non_staff_cannot_write_catalog(self):
        viewer = User.objects.create_user(username="catalog-viewer", password="p")
        self.client.force_authenticate(viewer)
        response = self.client.post("/tags", {"name": "forbidden"}, format="json")
        self.assertEqual(response.status_code, 403)
