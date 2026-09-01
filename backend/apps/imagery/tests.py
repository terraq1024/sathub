import json
import tempfile
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import duckdb
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from apps.projects.models import Project

from .metadata import parse_product_group, scan_product_groups
from .models import ImageryDataset, ImageryDatasetMember, ImageryProjectTag, ImageryRecord, ImagerySavedSearch
from .services import refresh_on_ingestion_datasets, sync_imagery_projection


class MetadataParserTests(SimpleTestCase):
    def test_plain_geotiff_group_resolves_raster_metadata(self):
        import numpy as np
        import rasterio
        from rasterio.transform import from_bounds

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scene_dir = root / "demo-scene-001"
            scene_dir.mkdir()
            transform = from_bounds(117.0, 31.0, 117.5, 31.5, 32, 32)
            with rasterio.open(
                scene_dir / "demo-scene-001.tif", "w",
                driver="GTiff", width=32, height=32, count=1, dtype="uint8",
                crs="EPSG:4326", transform=transform,
            ) as dataset:
                dataset.write((np.indices((32, 32)).sum(axis=0) % 256).astype("uint8"), 1)

            groups = scan_product_groups(root)
            self.assertEqual(len(groups), 1)
            values = parse_product_group(groups[0])
            self.assertEqual(values["source_name"], "demo-scene-001")
            self.assertEqual(values["spatial_status"], "ready")
            self.assertEqual(values["bbox"], [117.0, 31.0, 117.5, 31.5])
            self.assertEqual(values["metadata_status"], "partial")


class ImageryApiTestBase(TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.settings_override = override_settings(
            DUCKDB_PATH=root / "imagery.duckdb",
            STAC_DIR=root / "stac",
        )
        self.settings_override.enable()
        self.owner = User.objects.create_user(username="owner", password="p")
        self.other = User.objects.create_user(username="other", password="p")
        self.staff = User.objects.create_user(username="staff", password="p", is_staff=True)
        self.project = Project.objects.create(name="Owner project", code="owner-project", created_by=self.owner)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def tearDown(self):
        self.settings_override.disable()
        self.temporary_directory.cleanup()

    def create_imagery(self, image_id, *, owner=None, acquired=None, bbox=None):
        acquired = acquired or datetime(2026, 4, 6, 2, 2, 32, tzinfo=timezone.utc)
        bbox = bbox or [117.0, 31.0, 117.5, 31.5]
        imagery = ImageryRecord.objects.create(
            id=image_id,
            scene_key=f"scene-{image_id}",
            identity_hash=(image_id * 64)[:64],
            stac_id=f"scene-{image_id}",
            source_name=f"source-{image_id}",
            platform_code="AS05",
            satellite_name="AIRSAT-05",
            sensor="SAR",
            imaging_mode="STRIPMAP",
            polarization="HH",
            polarizations=["HH"],
            product_level="L2",
            acquisition_time=acquired,
            geometry={
                "type": "Polygon",
                "coordinates": [[
                    [bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]],
                    [bbox[0], bbox[3]], [bbox[0], bbox[1]],
                ]],
            },
            bbox=bbox,
            first_uploaded_by=owner or self.owner,
            status=ImageryRecord.STATUS_READY,
        )
        sync_imagery_projection(imagery)
        return imagery


class ImageryApiTests(ImageryApiTestBase):

    def test_owner_can_edit_archive_find_and_restore_imagery(self):
        imagery = self.create_imagery("image-a")

        response = self.client.patch(
            f"/api/imagery/{imagery.pk}",
            {"display_name": "Hefei scene", "description": "Priority scene", "project_ids": [self.project.pk]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        imagery.refresh_from_db()
        self.assertEqual(imagery.display_name, "Hefei scene")
        self.assertTrue(ImageryProjectTag.objects.filter(imagery=imagery, project=self.project).exists())
        stac = json.loads(Path(imagery.stac_path).read_text(encoding="utf-8"))
        self.assertEqual(stac["properties"]["airmap:display_name"], "Hefei scene")
        self.assertEqual(stac["properties"]["airmap:project_ids"], [str(self.project.pk)])

        archived = self.client.delete(f"/api/imagery/{imagery.pk}")
        self.assertEqual(archived.status_code, 204)
        imagery.refresh_from_db()
        archived_stac = json.loads(Path(imagery.stac_path).read_text(encoding="utf-8"))
        self.assertTrue(archived_stac["properties"]["airmap:is_archived"])
        self.assertEqual(self.client.get("/api/imagery/").data["count"], 0)
        included = self.client.get("/api/imagery/", {"include_archived": "true"})
        self.assertEqual(included.data["count"], 1)
        self.assertEqual(
            self.client.get(f"/api/imagery/{imagery.pk}", {"include_archived": "true"}).status_code,
            200,
        )

        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get("/api/imagery/", {"include_archived": "true"}).data["count"], 0)
        self.client.force_authenticate(self.owner)
        restored = self.client.post(f"/api/imagery/{imagery.pk}/restore")
        self.assertEqual(restored.status_code, 200)
        self.assertFalse(ImageryRecord.objects.get(pk=imagery.pk).is_archived)
        self.assertEqual(self.client.get("/api/imagery/").data["count"], 1)

    def test_non_owner_cannot_edit_or_archive_imagery(self):
        imagery = self.create_imagery("image-a")
        self.client.force_authenticate(self.other)

        self.assertEqual(
            self.client.patch(f"/api/imagery/{imagery.pk}", {"display_name": "Denied"}, format="json").status_code,
            403,
        )
        self.assertEqual(self.client.delete(f"/api/imagery/{imagery.pk}").status_code, 403)

    def test_batch_permission_validation_is_atomic(self):
        first = self.create_imagery("image-a")
        second = self.create_imagery("image-b", owner=self.other)

        response = self.client.post(
            "/api/imagery/batch",
            {"action": "archive", "imagery_ids": [first.pk, second.pk]},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ImageryRecord.objects.get(pk=first.pk).is_archived)
        self.assertFalse(ImageryRecord.objects.get(pk=second.pk).is_archived)

    def test_batch_project_action_updates_projection(self):
        first = self.create_imagery("image-a")
        second = self.create_imagery("image-b")

        response = self.client.post(
            "/api/imagery/batch",
            {"action": "add_project", "imagery_ids": [first.pk, second.pk], "project_id": self.project.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["projection_synced"])
        self.assertEqual(ImageryProjectTag.objects.filter(project=self.project).count(), 2)
        filtered = self.client.get("/api/imagery/", {"project_id": self.project.pk})
        self.assertEqual(filtered.data["count"], 2)

    def test_staff_can_manage_any_imagery(self):
        imagery = self.create_imagery("image-a", owner=self.other)
        self.client.force_authenticate(self.staff)

        response = self.client.patch(
            f"/api/imagery/{imagery.pk}",
            {"display_name": "Staff edit"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ImageryRecord.objects.get(pk=imagery.pk).display_name, "Staff edit")

    def test_rebuild_command_regenerates_duckdb_and_stac(self):
        imagery = self.create_imagery("image-a")
        imagery.refresh_from_db()
        Path(imagery.stac_path).unlink()

        output = StringIO()
        call_command("rebuild_imagery_index", stdout=output)

        imagery.refresh_from_db()
        self.assertTrue(Path(imagery.stac_path).is_file())
        self.assertIn("Rebuilt 1 imagery projections", output.getvalue())

    def test_existing_duckdb_schema_is_extended_before_search(self):
        from django.conf import settings

        with duckdb.connect(str(settings.DUCKDB_PATH)) as connection:
            connection.execute(
                "CREATE TABLE imagery_index ("
                "image_id VARCHAR PRIMARY KEY, source_name VARCHAR, owner_id VARCHAR, "
                "acquisition_time TIMESTAMP, created_at TIMESTAMP)"
            )
            connection.execute(
                "INSERT INTO imagery_index VALUES (?, ?, ?, ?, ?)",
                ["legacy", "legacy-source", str(self.owner.pk), None, None],
            )

        response = self.client.get("/api/imagery/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["effective_display_name"], "legacy-source")

    def test_filters_radar_optical_and_source_vendor(self):
        radar = self.create_imagery("radar")
        radar.platform_code = "UMBRA-10"
        radar.satellite_name = "Umbra-10"
        radar.sensor = "SAR"
        radar.save()
        sync_imagery_projection(radar)

        optical = self.create_imagery("optical")
        optical.platform_code = "GF2"
        optical.satellite_name = "高分二号"
        optical.sensor = "PMS"
        optical.imaging_mode = ""
        optical.polarization = ""
        optical.save()
        sync_imagery_projection(optical)

        unknown = self.create_imagery("unknown")
        unknown.sensor = ""
        unknown.save()
        sync_imagery_projection(unknown)

        sar_response = self.client.get("/api/imagery/", {"sensor_type": "sar", "source_vendor": "Umbra"})
        self.assertEqual(sar_response.status_code, 200)
        self.assertEqual([item["image_id"] for item in sar_response.data["results"]], ["radar"])

        optical_response = self.client.get("/api/imagery/", {"sensor_type": "optical", "source_vendor": "高分"})
        self.assertEqual(optical_response.status_code, 200)
        self.assertEqual([item["image_id"] for item in optical_response.data["results"]], ["optical"])

    def test_imagery_facets_are_built_from_indexed_records(self):
        umbra = self.create_imagery("umbra-facet")
        umbra.platform_code = "UMBRA-10"
        umbra.satellite_name = "Umbra-10"
        umbra.save()
        sync_imagery_projection(umbra)

        response = self.client.get("/api/imagery/facets")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item["value"] == "Umbra-10" for item in response.data["satellites"]))
        self.assertTrue(any(item["value"] == "Umbra" for item in response.data["vendors"]))
        self.assertTrue(any(item["value"] == "SAR" for item in response.data["sensors"]))
        self.assertTrue(any(item["value"] == "STRIPMAP" for item in response.data["imaging_modes"]))
        self.assertTrue(any(item["value"] == "L2" for item in response.data["product_levels"]))
        self.assertTrue(any(item["value"] == "HH" for item in response.data["polarizations"]))


class ImageryDatasetApiTests(ImageryApiTestBase):
    def setUp(self):
        super().setUp()
        base_time = datetime(2026, 4, 1, tzinfo=timezone.utc)
        self.oldest = self.create_imagery("image-a", acquired=base_time)
        self.newest = self.create_imagery("image-b", acquired=base_time + timedelta(days=2), bbox=[118.0, 32.0, 119.0, 33.0])
        self.middle = self.create_imagery("image-c", acquired=base_time + timedelta(days=1))

    def test_create_dataset_orders_initial_members_and_updates_revision(self):
        response = self.client.post(
            "/api/imagery/datasets",
            {"name": "Three scenes", "imagery_ids": [self.oldest.pk, self.newest.pk, self.middle.pk]},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["revision"], 2)
        self.assertEqual(response.data["member_count"], 3)
        self.assertEqual(
            [member["imagery_id"] for member in response.data["members"]],
            [self.newest.pk, self.middle.pk, self.oldest.pk],
        )
        self.assertEqual(response.data["bbox"], [117.0, 31.0, 119.0, 33.0])

    def test_add_is_idempotent_and_member_patch_changes_revision(self):
        dataset = ImageryDataset.objects.create(name="Dataset", created_by=self.owner)
        add = self.client.post(
            f"/api/imagery/datasets/{dataset.pk}/members",
            {"imagery_ids": [self.oldest.pk, self.newest.pk]},
            format="json",
        )
        self.assertEqual(add.status_code, 200)
        self.assertEqual(add.data["revision"], 2)

        duplicate = self.client.post(
            f"/api/imagery/datasets/{dataset.pk}/members",
            {"imagery_ids": [self.oldest.pk]},
            format="json",
        )
        self.assertEqual(duplicate.data["revision"], 2)

        changed = self.client.patch(
            f"/api/imagery/datasets/{dataset.pk}/members/{self.oldest.pk}",
            {"enabled": False, "move": "top"},
            format="json",
        )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.data["revision"], 3)
        self.assertEqual(changed.data["members"][0]["imagery_id"], self.oldest.pk)
        self.assertFalse(changed.data["members"][0]["enabled"])

    def test_order_requires_every_member_and_can_set_enabled_snapshot(self):
        dataset = ImageryDataset.objects.create(name="Dataset", created_by=self.owner)
        for position, imagery in enumerate([self.oldest, self.newest, self.middle]):
            ImageryDatasetMember.objects.create(dataset=dataset, imagery=imagery, position=position, added_by=self.owner)

        invalid = self.client.put(
            f"/api/imagery/datasets/{dataset.pk}/members/order",
            {"imagery_ids": [self.oldest.pk]},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)

        valid = self.client.put(
            f"/api/imagery/datasets/{dataset.pk}/members/order",
            {
                "imagery_ids": [self.middle.pk, self.oldest.pk, self.newest.pk],
                "enabled_imagery_ids": [self.middle.pk, self.newest.pk],
            },
            format="json",
        )
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.data["revision"], 2)
        self.assertEqual([member["imagery_id"] for member in valid.data["members"]], [self.middle.pk, self.oldest.pk, self.newest.pk])
        self.assertEqual([member["enabled"] for member in valid.data["members"]], [True, False, True])

    def test_remove_member_normalizes_positions_and_updates_revision(self):
        dataset = ImageryDataset.objects.create(name="Dataset", created_by=self.owner)
        for position, imagery in enumerate([self.oldest, self.middle, self.newest]):
            ImageryDatasetMember.objects.create(dataset=dataset, imagery=imagery, position=position, added_by=self.owner)

        response = self.client.delete(
            f"/api/imagery/datasets/{dataset.pk}/members/{self.middle.pk}",
        )

        self.assertEqual(response.status_code, 204)
        dataset.refresh_from_db()
        self.assertEqual(dataset.revision, 2)
        self.assertEqual(
            list(dataset.members.values_list("imagery_id", "position")),
            [(self.oldest.pk, 0), (self.newest.pk, 1)],
        )

    def test_archived_imagery_cannot_be_added(self):
        dataset = ImageryDataset.objects.create(name="Dataset", created_by=self.owner)
        self.oldest.is_archived = True
        self.oldest.archived_at = datetime.now(timezone.utc)
        self.oldest.archived_by = self.owner
        self.oldest.save(update_fields=["is_archived", "archived_at", "archived_by", "updated_at"])

        response = self.client.post(
            f"/api/imagery/datasets/{dataset.pk}/members",
            {"imagery_ids": [self.oldest.pk]},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(dataset.members.count(), 0)

    @override_settings(IMAGERY_DATASET_MAX_MEMBERS=2)
    def test_dataset_member_limit_is_configurable(self):
        dataset = ImageryDataset.objects.create(name="Dataset", created_by=self.owner)

        response = self.client.post(
            f"/api/imagery/datasets/{dataset.pk}/members",
            {"imagery_ids": [self.oldest.pk, self.middle.pk, self.newest.pk]},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ImageryDatasetMember.objects.filter(dataset=dataset).count(), 0)

    def test_dataset_permissions_archive_and_include_archived(self):
        dataset = ImageryDataset.objects.create(name="Dataset", created_by=self.owner)
        self.client.force_authenticate(self.other)
        denied = self.client.patch(f"/api/imagery/datasets/{dataset.pk}", {"name": "Denied"}, format="json")
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.delete(f"/api/imagery/datasets/{dataset.pk}").status_code, 204)
        self.assertEqual(self.client.get("/api/imagery/datasets").data["count"], 0)
        included = self.client.get("/api/imagery/datasets", {"include_archived": "true"})
        self.assertEqual(included.data["count"], 1)

        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get("/api/imagery/datasets", {"include_archived": "true"}).data["count"], 0)

    def test_query_dataset_refresh_replaces_members_and_requires_manager(self):
        dataset_response = self.client.post(
            "/api/imagery/datasets",
            {"name": "Dynamic", "membership_type": "query", "query_definition": {"platform": "AS05"}},
            format="json",
        )
        self.assertEqual(dataset_response.status_code, 201)
        dataset = ImageryDataset.objects.get(pk=dataset_response.data["id"])
        self.assertEqual(dataset.membership_type, ImageryDataset.MEMBERSHIP_QUERY)
        refresh = self.client.post(f"/api/imagery/datasets/{dataset.pk}/refresh")
        self.assertEqual(refresh.status_code, 200)
        self.assertEqual(refresh.data["member_count"], 3)
        self.assertEqual(refresh.data["revision"], 2)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(f"/api/imagery/datasets/{dataset.pk}/refresh").status_code, 403)

    def test_query_dataset_on_ingestion_refreshes_automatically(self):
        dataset = ImageryDataset.objects.create(
            name="Automatic", created_by=self.owner, membership_type="query",
            query_definition={"platform": "AS05"}, refresh_mode="on_ingestion",
        )
        self.assertEqual(refresh_on_ingestion_datasets(), 1)
        dataset.refresh_from_db()
        self.assertEqual(dataset.members.count(), 3)
        self.assertEqual(dataset.revision, 2)

        self.assertEqual(refresh_on_ingestion_datasets(), 1)
        dataset.refresh_from_db()
        self.assertEqual(dataset.revision, 2)

    def test_static_dataset_refresh_is_rejected(self):
        dataset = ImageryDataset.objects.create(name="Static", created_by=self.owner)
        self.assertEqual(self.client.post(f"/api/imagery/datasets/{dataset.pk}/refresh").status_code, 400)


class ImageryV6ApiTests(ImageryApiTestBase):
    def test_saved_search_crud_permissions(self):
        response = self.client.post("/api/imagery/saved-searches", {"name": "SAR", "query_definition": {"platform": "AS05"}}, format="json")
        self.assertEqual(response.status_code, 201)
        search = ImagerySavedSearch.objects.get(pk=response.data["id"])
        self.assertEqual(self.client.get("/api/imagery/saved-searches").status_code, 200)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.patch(f"/api/imagery/saved-searches/{search.pk}", {"name": "No"}, format="json").status_code, 403)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.patch(f"/api/imagery/saved-searches/{search.pk}", {"name": "Updated"}, format="json").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/imagery/saved-searches/{search.pk}").status_code, 204)

    def test_saved_search_list_scoped_to_creator(self):
        self.client.post("/api/imagery/saved-searches", {"name": "Owner search", "query_definition": {}}, format="json")
        self.client.force_authenticate(self.other)
        self.client.post("/api/imagery/saved-searches", {"name": "Other search", "query_definition": {}}, format="json")
        listing = self.client.get("/api/imagery/saved-searches")
        self.assertEqual(listing.status_code, 200)
        names = [item["name"] for item in listing.data]
        self.assertEqual(names, ["Other search"])

    def test_dataset_list_search_and_pagination(self):
        ImageryDataset.objects.create(name="Alpha scenes", created_by=self.owner)
        ImageryDataset.objects.create(name="Beta block", created_by=self.owner)
        response = self.client.get("/api/imagery/datasets", {"q": "alpha"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Alpha scenes")
        paged = self.client.get("/api/imagery/datasets", {"page": 1, "page_size": 1})
        self.assertEqual(paged.data["count"], 2)
        self.assertEqual(len(paged.data["results"]), 1)

    def test_invalid_geometry_is_rejected(self):
        response = self.client.get("/api/imagery/", {"geometry": '{"type":"Point","coordinates":[1,2]}'})
        self.assertEqual(response.status_code, 400)

    def test_spatial_relations_and_exact_count(self):
        imagery = self.create_imagery("image-a", bbox=[0, 0, 2, 2])
        query = '{"type":"Polygon","coordinates":[[[0.5,0.5],[1.5,0.5],[1.5,1.5],[0.5,1.5],[0.5,0.5]]]}'
        self.assertEqual(self.client.get("/api/imagery/", {"geometry": query, "spatial_relation": "contains"}).data["count"], 1)
        self.assertEqual(self.client.get("/api/imagery/", {"geometry": query, "spatial_relation": "within"}).data["count"], 0)
        self.assertEqual(self.client.get("/api/imagery/", {"geometry": query, "spatial_relation": "intersects"}).data["count"], 1)
        larger = '{"type":"Polygon","coordinates":[[[-1,-1],[3,-1],[3,3],[-1,3],[-1,-1]]]}'
        self.assertEqual(self.client.get("/api/imagery/", {"geometry": larger, "spatial_relation": "within"}).data["count"], 1)
        outside = '{"type":"Polygon","coordinates":[[[5,5],[6,5],[6,6],[5,6],[5,5]]]}'
        result = self.client.get("/api/imagery/", {"geometry": outside, "page_size": 1}).data
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["results"], [])
