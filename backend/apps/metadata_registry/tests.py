import json
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import include, path
from rest_framework.test import APIClient

from apps.imagery.metadata import ProductGroup, parse_product_group

from .engine import RuleValidationError, execute_rules, parse_product_group_with_registry
from .models import MetadataOverride, MetadataSchema, MetadataSchemaField, MetadataQualityIssue, ParserRun, ParserTemplate, ParserTemplateVersion


urlpatterns = [path("api/metadata/", include("apps.metadata_registry.urls"))]


def sample_rules():
    return {
        "match": {"filename_regex": "^AS05_", "asset_exists": ["metadata", "data"]},
        "fields": [
            {"key": "platform_code", "data_type": "string", "required": True, "sources": [{"type": "filename_regex", "pattern": "^(AS\\d+)_", "group": 1}], "transforms": ["upper"]},
            {"key": "satellite_name", "sources": [{"type": "xml_path", "asset": "metadata", "path": "satellite"}, {"type": "constant", "value": "fallback"}], "transforms": ["trim"]},
            {"key": "resolution_m", "data_type": "float", "sources": [{"type": "xml_path", "asset": "metadata", "path": "productinfo/NominalResolution"}], "transforms": ["to_number", {"op": "unit_convert", "from": "m", "to": "cm"}]},
            {"key": "width", "data_type": "integer", "sources": [{"type": "raster", "key": "width"}]},
        ],
    }


class RuleEngineTests(TestCase):
    def test_controlled_sources_and_transforms(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xml = root / "scene.meta.xml"
            xml.write_text("<root><satellite> AIRSAT-05 </satellite><productinfo><NominalResolution>2.5</NominalResolution></productinfo></root>", encoding="utf-8")
            group = ProductGroup(stem="AS05_TEST", files={"meta.xml": xml, ".tif": root / "missing.tif"})
            group.files[".tif"].write_bytes(b"not-raster")
            rules = sample_rules()
            rules["fields"] = rules["fields"][:3]
            result = execute_rules(group, rules)
            self.assertEqual(result["values"]["platform_code"], "AS05")
            self.assertEqual(result["values"]["satellite_name"], "AIRSAT-05")
            self.assertEqual(result["values"]["resolution_m"], 250.0)
            self.assertIn("platform_code", result["provenance"])

    def test_unsafe_rules_are_rejected(self):
        rules = sample_rules()
        rules["fields"][0]["sources"][0]["pattern"] = "(a+)+$"
        with self.assertRaises(RuleValidationError):
            execute_rules(ProductGroup(stem="AS05", files={}), rules)
        rules = sample_rules()
        rules["fields"][0]["sources"] = [{"type": "xml_path", "path": "../../etc/passwd"}]
        with self.assertRaises(RuleValidationError):
            execute_rules(ProductGroup(stem="AS05", files={}), rules)

    def test_unconfigured_registry_falls_back_to_legacy_parser(self):
        group = ProductGroup(stem="AS05_AR_TD_003485_E117.1_N31.3_20260406020232_L2_HH_05_001", files={})
        fallback = parse_product_group(group)
        result = parse_product_group_with_registry(group)
        self.assertEqual(result["source_name"], fallback["source_name"])


class RegistryApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="registry-user", password="password")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_non_admin_cannot_write_registry_configuration(self):
        response = self.client.post("/api/metadata/schemas", {"code": "sar", "name": "SAR"}, format="json")
        self.assertEqual(response.status_code, 403)

        response = self.client.post("/api/metadata/templates", {"schema": 1, "name": "AIRSAT"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_non_admin_can_read_registry_configuration(self):
        response = self.client.get("/api/metadata/schemas")
        self.assertEqual(response.status_code, 200)

    def test_admin_can_create_schema_and_template_version(self):
        admin = User.objects.create_user(username="registry-admin", password="password", is_staff=True)
        self.client.force_authenticate(admin)
        schema_response = self.client.post("/api/metadata/schemas", {"code": "sar-admin", "name": "SAR"}, format="json")
        self.assertEqual(schema_response.status_code, 201)
        schema_id = schema_response.data["id"]
        template_response = self.client.post("/api/metadata/templates", {"schema": schema_id, "name": "AIRSAT"}, format="json")
        self.assertEqual(template_response.status_code, 201)
        template_id = template_response.data["id"]
        version_response = self.client.post(f"/api/metadata/templates/{template_id}/versions", {"version": "1.0.0", "rules": sample_rules()}, format="json")
        self.assertEqual(version_response.status_code, 201)

    def test_admin_can_replace_schema_fields(self):
        admin = User.objects.create_user(username="schema-editor", password="password", is_staff=True)
        self.client.force_authenticate(admin)
        schema = MetadataSchema.objects.create(code="editable", name="Editable", created_by=admin)
        MetadataSchemaField.objects.create(schema=schema, key="old_field", label="Old")
        response = self.client.patch(
            f"/api/metadata/schemas/{schema.pk}",
            {"fields": [{"key": "platform_code", "label": "平台", "data_type": "string"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(schema.fields.values_list("key", flat=True)), ["platform_code"])

    def test_non_admin_cannot_publish_or_execute_parser(self):
        schema = MetadataSchema.objects.create(code="sar-read", name="SAR", created_by=self.user)
        template = ParserTemplate.objects.create(schema=schema, name="AIRSAT", matcher={}, created_by=self.user)
        version = ParserTemplateVersion.objects.create(template=template, version="1.0.0", rules=sample_rules(), created_by=self.user)
        self.assertEqual(self.client.post(f"/api/metadata/versions/{version.pk}/publish").status_code, 403)
        self.assertEqual(self.client.post("/api/metadata/runs/execute", {"imagery_id": "missing"}, format="json").status_code, 403)

    def test_non_admin_cannot_create_metadata_override(self):
        response = self.client.post("/api/metadata/overrides", {"imagery": "missing", "field_key": "satellite_name", "value": "manual"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_publish_and_immutable_version(self):
        admin = User.objects.create_user(username="publish-admin", password="password", is_staff=True)
        self.client.force_authenticate(admin)
        schema = MetadataSchema.objects.create(code="sar", name="SAR", created_by=self.user)
        template = ParserTemplate.objects.create(schema=schema, name="AIRSAT", matcher={"filename_regex": "^AS05_"}, created_by=self.user)
        response = self.client.post(f"/api/metadata/templates/{template.pk}/versions", {"version": "1.0.0", "rules": sample_rules()}, format="json")
        self.assertEqual(response.status_code, 201)
        version = ParserTemplateVersion.objects.get(pk=response.data["id"])
        self.assertEqual(self.client.post(f"/api/metadata/versions/{version.pk}/publish").status_code, 200)
        response = self.client.patch(f"/api/metadata/templates/{template.pk}/versions/{version.pk}", {"rules": sample_rules()}, format="json")
        self.assertIn(response.status_code, (404, 405))

    def test_invalid_rules_rejected_by_api(self):
        admin = User.objects.create_user(username="rules-admin", password="password", is_staff=True)
        self.client.force_authenticate(admin)
        schema = MetadataSchema.objects.create(code="optical", name="Optical", created_by=self.user)
        template = ParserTemplate.objects.create(schema=schema, name="Unsafe", created_by=self.user)
        bad = sample_rules()
        bad["fields"][0]["sources"][0]["pattern"] = "(a+)+$"
        response = self.client.post(f"/api/metadata/templates/{template.pk}/versions", {"version": "1.0.0", "rules": bad}, format="json")
        self.assertEqual(response.status_code, 400)
