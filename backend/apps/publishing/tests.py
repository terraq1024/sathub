import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.imagery.models import ImageryDataset, ImageryDatasetMember, ImageryRecord

from .models import ImageryService, ServicePublishJob
from .services import (
    _commit_dataset_publication,
    _overview_minzoom,
    _probe_mosaic,
    _validate_cog_compatibility,
    _web_mercator_tile,
    create_publish_job,
    process_publish_job,
    titiler_tile_url,
)


class FakeHTTPResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return b"x"

    class Headers:
        def get_content_type(self):
            return "image/png"

    headers = Headers()


class ImageryServiceApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="publisher", password="test")
        self.other_user = get_user_model().objects.create_user(username="other", password="test")
        self.imagery = self._create_imagery(
            "image-1",
            "scene-1",
            "a" * 64,
            [110.0, 20.0, 111.0, 21.0],
        )
        self.imagery_two = self._create_imagery(
            "image-2",
            "scene-2",
            "b" * 64,
            [120.0, 30.0, 122.0, 32.0],
        )
        self.dataset = ImageryDataset.objects.create(name="Two scenes", created_by=self.user, revision=3)
        ImageryDatasetMember.objects.create(
            dataset=self.dataset,
            imagery=self.imagery_two,
            position=0,
            added_by=self.user,
        )
        ImageryDatasetMember.objects.create(
            dataset=self.dataset,
            imagery=self.imagery,
            position=1,
            added_by=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _create_imagery(self, image_id, scene_key, identity_hash, bbox):
        return ImageryRecord.objects.create(
            id=image_id,
            scene_key=scene_key,
            identity_hash=identity_hash,
            stac_id=scene_key,
            source_name=scene_key,
            first_uploaded_by=self.user,
            bbox=bbox,
            geometry={
                "type": "Polygon",
                "coordinates": [[
                    [bbox[0], bbox[1]], [bbox[2], bbox[1]],
                    [bbox[2], bbox[3]], [bbox[0], bbox[3]],
                    [bbox[0], bbox[1]],
                ]],
            },
        )

    def _create_dataset_service(self):
        response = self.client.post(
            "/api/services/",
            {"dataset_id": str(self.dataset.pk), "name": "Dataset service", "visibility": "public"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return ImageryService.objects.get(service_key=response.data["service_key"]), response

    def test_create_publish_and_offline_single_scene_service(self):
        response = self.client.post(
            "/api/services/",
            {"imagery_id": self.imagery.id, "name": "Scene service", "visibility": "public"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["source_type"], ImageryService.TYPE_SINGLE_SCENE)
        key = response.data["service_key"]

        publish = self.client.post(f"/api/services/{key}/publish")
        self.assertEqual(publish.status_code, 202)
        job = ServicePublishJob.objects.get()
        self.assertEqual(job.status, ServicePublishJob.STATUS_PENDING)
        self.assertEqual(job.source_snapshot, [self.imagery.pk])

        offline = self.client.post(f"/api/services/{key}/offline")
        self.assertEqual(offline.status_code, 204)
        self.assertEqual(ImageryService.objects.get(service_key=key).status, ImageryService.STATUS_OFFLINE)

    @override_settings(PUBLIC_SERVICE_BASE_URL="https://geo.example.test")
    def test_service_urls_use_configured_public_base(self):
        response = self.client.post(
            "/api/services/",
            {"imagery_id": self.imagery.id, "name": "External service", "visibility": "public"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        key = response.data["service_key"]
        self.assertEqual(response.data["tilejson_url"], f"https://geo.example.test/api/services/{key}/tilejson")
        self.assertEqual(response.data["xyz_url"], f"https://geo.example.test/api/services/{key}/tiles/{{z}}/{{x}}/{{y}}.png")
        self.assertEqual(response.data["ogcapi_url"], f"https://geo.example.test/api/services/{key}/ogcapi")

    def test_create_requires_exactly_one_source(self):
        missing = self.client.post("/api/services/", {}, format="json")
        self.assertEqual(missing.status_code, 400)
        both = self.client.post(
            "/api/services/",
            {"imagery_id": self.imagery.pk, "dataset_id": str(self.dataset.pk)},
            format="json",
        )
        self.assertEqual(both.status_code, 400)

    def test_archived_single_scene_cannot_create_service(self):
        self.imagery.is_archived = True
        self.imagery.save(update_fields=["is_archived", "updated_at"])
        response = self.client.post(
            "/api/services/",
            {"imagery_id": self.imagery.id, "name": "Archived service", "visibility": "public"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_only_dataset_creator_or_admin_can_create_dataset_service(self):
        other_client = APIClient()
        other_client.force_authenticate(self.other_user)
        forbidden = other_client.post(
            "/api/services/",
            {"dataset_id": str(self.dataset.pk)},
            format="json",
        )
        self.assertEqual(forbidden.status_code, 403)

        service, response = self._create_dataset_service()
        self.assertEqual(service.service_type, ImageryService.TYPE_DATASET_MOSAIC)
        self.assertEqual(response.data["dataset_id"], str(self.dataset.pk))
        self.assertEqual(response.data["dataset_name"], self.dataset.name)
        self.assertIn("source_revision", response.data)
        self.assertEqual(response.data["imagery_count"], 2)
        self.assertEqual(response.data["bbox"], [110.0, 20.0, 122.0, 32.0])
        self.assertTrue(response.data["needs_update"])

    def test_dataset_publish_job_freezes_enabled_member_order_and_revision(self):
        service, _ = self._create_dataset_service()
        job = create_publish_job(service, self.user)
        self.assertEqual(job.source_snapshot, [self.imagery_two.pk, self.imagery.pk])
        self.assertEqual(job.target_revision, 3)

        self.dataset.members.filter(imagery=self.imagery_two).update(enabled=False)
        self.dataset.revision = 4
        self.dataset.save(update_fields=["revision", "updated_at"])
        job.refresh_from_db()
        self.assertEqual(job.source_snapshot, [self.imagery_two.pk, self.imagery.pk])
        self.assertEqual(job.target_revision, 3)

    def test_dataset_commit_replaces_snapshot_and_revision(self):
        service, _ = self._create_dataset_service()
        with TemporaryDirectory() as tmp:
            mosaic_path = Path(tmp) / "service.json"
            mosaic_path.write_text("{}", encoding="utf-8")
            _commit_dataset_publication(
                service,
                [self.imagery_two, self.imagery],
                mosaic_path,
                "http://127.0.0.1:8081",
                {"rescale": "1,100"},
                3,
            )
        service.refresh_from_db()
        self.assertEqual(service.status, ImageryService.STATUS_ONLINE)
        self.assertEqual(service.source_revision, 3)
        self.assertEqual(
            list(service.service_assets.values_list("imagery_id", flat=True)),
            [self.imagery_two.pk, self.imagery.pk],
        )

    def test_dataset_tilejson_uses_successful_snapshot_bbox_union_when_degraded(self):
        service, _ = self._create_dataset_service()
        service.status = ImageryService.STATUS_DEGRADED
        service.save(update_fields=["status", "updated_at"])
        service.service_assets.create(imagery=self.imagery_two, order=0)
        service.service_assets.create(imagery=self.imagery, order=1)

        anonymous = APIClient()
        response = anonymous.get(f"/api/services/{service.service_key}/tilejson")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["bounds"], [110.0, 20.0, 122.0, 32.0])

    def test_public_single_scene_tilejson_remains_compatible(self):
        service = ImageryService.objects.create(
            name="Public service",
            service_key="public-service",
            visibility=ImageryService.VISIBILITY_PUBLIC,
            status=ImageryService.STATUS_ONLINE,
            created_by=self.user,
        )
        service.service_assets.create(imagery=self.imagery)
        response = APIClient().get("/api/services/public-service/tilejson")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["bounds"], self.imagery.bbox)
        self.assertIn("{z}", response.data["tiles"][0])

    def test_ogc_api_tiles_landing_and_tileset_metadata(self):
        service = ImageryService.objects.create(
            name="OGC service",
            service_key="ogc-service",
            visibility=ImageryService.VISIBILITY_PUBLIC,
            status=ImageryService.STATUS_ONLINE,
            created_by=self.user,
        )
        service.service_assets.create(imagery=self.imagery)

        landing = APIClient().get("/api/services/ogc-service/ogcapi")
        self.assertEqual(landing.status_code, 200)
        self.assertEqual(landing.data["links"][1]["rel"], "tilesets")
        self.assertIn("/ogcapi/tiles", landing.data["links"][1]["href"])

        tilesets = APIClient().get("/api/services/ogc-service/ogcapi/tiles")
        self.assertEqual(tilesets.status_code, 200)
        self.assertEqual(len(tilesets.data["tilesets"]), 1)
        self.assertIn("tileMatrix", tilesets.data["tilesets"][0]["links"][1]["href"])

        metadata = APIClient().get("/api/services/ogc-service/ogcapi/tiles/WebMercatorQuad")
        self.assertEqual(metadata.status_code, 200)
        self.assertEqual(metadata.data["tileMatrixSet"], "WebMercatorQuad")
        self.assertEqual(metadata.data["bounds"], self.imagery.bbox)

    @patch("apps.publishing.ogc_tiles.urlopen", return_value=FakeHTTPResponse())
    def test_ogc_tile_translates_row_col_to_existing_xyz_proxy(self, mocked_urlopen):
        service = ImageryService.objects.create(
            name="OGC tile service",
            service_key="ogc-tile-service",
            visibility=ImageryService.VISIBILITY_PUBLIC,
            status=ImageryService.STATUS_ONLINE,
            created_by=self.user,
            titiler_base_url="http://127.0.0.1:8081",
            cog_path=r"D:\data\scene.tif",
        )
        service.service_assets.create(imagery=self.imagery)
        response = APIClient().get(
            "/api/services/ogc-tile-service/ogcapi/tiles/WebMercatorQuad/5/11/10.png"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        requested = mocked_urlopen.call_args.args[0]
        self.assertIn("/cog/tiles/WebMercatorQuad/5/10/11.png", requested)

    def test_ogc_authenticated_service_matches_existing_access_policy(self):
        service = ImageryService.objects.create(
            name="Private OGC service",
            service_key="private-ogc-service",
            visibility=ImageryService.VISIBILITY_AUTHENTICATED,
            status=ImageryService.STATUS_ONLINE,
            created_by=self.user,
        )
        anonymous = APIClient().get("/api/services/private-ogc-service/ogcapi")
        self.assertEqual(anonymous.status_code, 401)
        authenticated = self.client.get("/api/services/private-ogc-service/ogcapi")
        self.assertEqual(authenticated.status_code, 200)

    def test_ogc_only_exposes_online_or_degraded_services(self):
        service = ImageryService.objects.create(
            name="Offline OGC service",
            service_key="offline-ogc-service",
            visibility=ImageryService.VISIBILITY_PUBLIC,
            status=ImageryService.STATUS_OFFLINE,
            created_by=self.user,
        )
        response = APIClient().get("/api/services/offline-ogc-service/ogcapi")
        self.assertEqual(response.status_code, 404)

    def test_tile_proxy_urls_select_cog_or_mosaic_routes(self):
        single = ImageryService(
            service_type=ImageryService.TYPE_SINGLE_SCENE,
            titiler_base_url="http://127.0.0.1:8081",
            cog_path=r"D:\data\single.tif",
        )
        single_url = titiler_tile_url(single, 5, 10, 11)
        self.assertIn("/cog/tiles/WebMercatorQuad/5/10/11.png", single_url)

        dataset = ImageryService(
            service_type=ImageryService.TYPE_DATASET_MOSAIC,
            titiler_base_url="http://127.0.0.1:8081",
            mosaic_path=r"D:\data\mosaics\dataset.json",
        )
        mosaic_url = titiler_tile_url(dataset, 5, 10, 11)
        parsed = urlparse(mosaic_url)
        self.assertIn("/mosaicjson/tiles/WebMercatorQuad/5/10/11.png", parsed.path)
        self.assertEqual(parse_qs(parsed.query)["pixel_selection"], ["first"])

    def test_mosaic_probe_uses_first_scene_center_instead_of_union_center(self):
        first_center = (110.5, 20.5)
        expected_x, expected_y = _web_mercator_tile(*first_center, 7)
        with TemporaryDirectory() as tmp:
            mosaic_path = Path(tmp) / "candidate.json"
            mosaic_path.write_text(json.dumps({
                "minzoom": 7,
                "bounds": [70.0, 10.0, 150.0, 50.0],
                "center": [110.0, 30.0, 7],
            }), encoding="utf-8")
            with patch(
                "apps.publishing.services.urlopen",
                side_effect=[FakeHTTPResponse(), FakeHTTPResponse()],
            ) as mocked_urlopen:
                _probe_mosaic(
                    mosaic_path,
                    "http://127.0.0.1:8081",
                    {},
                    [110.0, 20.0, 111.0, 21.0],
                )
        tile_url = mocked_urlopen.call_args_list[1].args[0]
        self.assertIn(f"/7/{expected_x}/{expected_y}.png", tile_url)

    def test_overview_minzoom_covers_the_dataset_union(self):
        metadata = [
            {"bounds": [109.9, 18.2, 110.2, 18.6]},
            {"bounds": [111.3, 24.8, 111.5, 25.0]},
        ]
        self.assertEqual(_overview_minzoom(metadata), 6)

    def test_failed_republish_keeps_old_mosaic_and_sets_degraded(self):
        service, _ = self._create_dataset_service()
        with TemporaryDirectory() as tmp:
            old_mosaic = Path(tmp) / "published.json"
            old_mosaic.write_text("{}", encoding="utf-8")
            service.mosaic_path = str(old_mosaic)
            service.status = ImageryService.STATUS_ONLINE
            service.save(update_fields=["mosaic_path", "status", "updated_at"])
            job = ServicePublishJob.objects.create(
                service=service,
                status=ServicePublishJob.STATUS_RUNNING,
                source_snapshot=[self.imagery.pk],
                target_revision=self.dataset.revision,
                created_by=self.user,
            )
            with patch("apps.publishing.services._publish_dataset", side_effect=ValueError("probe failed")):
                process_publish_job(job)
            self.assertTrue(old_mosaic.is_file())
        service.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(service.status, ImageryService.STATUS_DEGRADED)
        self.assertEqual(job.status, ServicePublishJob.STATUS_FAILED)
        self.assertIn("probe failed", service.error_message)

    def test_archived_snapshot_member_rejects_first_publication(self):
        service, _ = self._create_dataset_service()
        job = create_publish_job(service, self.user)
        job.status = ServicePublishJob.STATUS_RUNNING
        job.save(update_fields=["status", "updated_at"])
        self.imagery_two.is_archived = True
        self.imagery_two.save(update_fields=["is_archived", "updated_at"])

        process_publish_job(job)

        service.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(service.status, ImageryService.STATUS_FAILED)
        self.assertEqual(job.status, ServicePublishJob.STATUS_FAILED)
        self.assertIn("Archived imagery", job.error_message)

    def test_incompatible_cog_band_signatures_are_rejected(self):
        metadata = [
            {"count": 1, "dtypes": ["uint16"], "bounds": [110, 20, 111, 21]},
            {"count": 2, "dtypes": ["uint16", "uint16"], "bounds": [120, 30, 121, 31]},
        ]
        with patch("apps.publishing.services._inspect_cogs", return_value=metadata):
            with self.assertRaisesMessage(ValueError, "matching band counts and data types"):
                _validate_cog_compatibility([Path("one.tif"), Path("two.tif")])
