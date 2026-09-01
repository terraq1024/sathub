import json
import tempfile
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import include, path
from rest_framework.test import APIClient

from apps.access_control.models import ApiAccessToken
from apps.imagery.models import ImageryAsset, ImageryRecord


urlpatterns = [
    path("api/stac/", include("apps.stac_api.urls")),
    path("api/access/", include("apps.access_control.urls")),
]


@override_settings(ROOT_URLCONF="apps.stac_api.tests", STAC_DIR=Path(tempfile.gettempdir()) / "airmap-stac-tests")
class StacApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="stac-user", password="pass")
        self.client.force_authenticate(self.user)
        self.asset_root = Path(tempfile.mkdtemp())
        self.data_override = override_settings(DATA_DIR=self.asset_root)
        self.data_override.enable()
        self.image = ImageryRecord.objects.create(
            id="image-1", scene_key="scene-1", identity_hash="hash-1", stac_id="scene-1", source_name="scene-1.tif",
            platform_code="AS05", satellite_name="AIRSAT-05", sensor="SAR", imaging_mode="STRIPMAP", polarization="HH",
            product_level="L2", acquisition_time=datetime(2024, 6, 1, tzinfo=dt_timezone.utc), bbox=[117, 31, 118, 32], geometry={"type": "Polygon", "coordinates": [[[117,31],[118,31],[118,32],[117,32],[117,31]]]},
            first_uploaded_by=self.user,
        )
        preview_path = self.asset_root / "scene.jpg"
        preview_path.write_bytes(b"preview-bytes")
        ImageryAsset.objects.create(imagery=self.image, role="preview", name="scene.jpg", path=str(preview_path), media_type="image/jpeg")

    def tearDown(self):
        self.data_override.disable()
        for path in self.asset_root.glob("**/*"):
            if path.is_file():
                path.unlink()
        self.asset_root.rmdir()

    def test_search_and_asset_href(self):
        response = self.client.get("/api/stac/search", {"bbox": "117.5,31.5,119,33", "query": json.dumps({"platform_code": {"eq": "AS05"}})})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["numberMatched"], 1)
        self.assertIn("/api/imagery/image-1/assets/preview", response.data["features"][0]["assets"]["preview"]["href"])
        self.assertNotIn("D:/private", response.content.decode())

    def test_collection_items_reuses_search_and_deduplicates_fallbacks(self):
        response = self.client.get("/api/stac/collections/airmap-imagery/items", {"datetime": "2024-01-01T00:00:00Z/2024-12-31T23:59:59Z"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["numberMatched"], 1)
        self.assertEqual(response.data["numberReturned"], 1)
        self.assertEqual(response.data["features"][0]["id"], "scene-1")

        fallback = ImageryRecord.objects.create(
            id="image-2", scene_key="scene-2", identity_hash="hash-2", stac_id="scene-2", source_name="scene-2.tif",
            acquisition_time=self.image.acquisition_time, first_uploaded_by=self.user,
        )
        response = self.client.get("/api/stac/search", {"datetime": "2024-01-01T00:00:00Z/2024-12-31T23:59:59Z"})
        self.assertEqual(response.data["numberMatched"], 2)
        self.assertEqual(len({feature["id"] for feature in response.data["features"]}), 2)

    def test_search_exposes_next_link_for_offset_pagination(self):
        for index in range(2, 5):
            ImageryRecord.objects.create(
                id=f"image-{index}", scene_key=f"scene-{index}", identity_hash=f"hash-{index}", stac_id=f"scene-{index}",
                source_name=f"scene-{index}.tif", acquisition_time=self.image.acquisition_time,
                first_uploaded_by=self.user,
            )
        response = self.client.get("/api/stac/search", {"limit": "2"})
        self.assertEqual(response.data["numberMatched"], 4)
        self.assertEqual(response.data["numberReturned"], 2)
        self.assertEqual(response.data["context"]["offset"], 0)
        next_link = next(link for link in response.data["links"] if link["rel"] == "next")
        next_response = self.client.get(next_link["href"])
        self.assertEqual(next_response.data["numberReturned"], 2)
        self.assertEqual(next_response.data["context"]["offset"], 2)

    def test_archived_excluded_and_invalid_parameters(self):
        self.image.is_archived = True
        self.image.save(update_fields=["is_archived"])
        self.assertEqual(self.client.get("/api/stac/search").data["numberMatched"], 0)
        self.assertEqual(self.client.get("/api/stac/search", {"limit": "0"}).status_code, 400)
        self.assertEqual(self.client.post("/api/stac/search", {"query": {"unknown": {"eq": "x"}}}, format="json").status_code, 400)

    def test_catalog_scope_does_not_return_signed_asset_url(self):
        _, raw = ApiAccessToken.issue(user=self.user, name="catalog-only", scopes=["catalog/read"])
        self.client.force_authenticate(None)
        response = self.client.get(
            "/api/stac/collections/airmap-imagery/items/scene-1",
            HTTP_AUTHORIZATION=f"Bearer {raw}",
        )

        self.assertEqual(response.status_code, 200)
        href = response.data["assets"]["preview"]["href"]
        self.assertNotIn("/api/access/signed-assets/", href)
        self.assertIn("/api/imagery/image-1/assets/preview", href)

    def test_assets_scope_returns_signed_url_with_range_support(self):
        _, raw = ApiAccessToken.issue(user=self.user, name="full-access", scopes=["catalog/read", "assets/read"])
        self.client.force_authenticate(None)
        response = self.client.get(
            "/api/stac/collections/airmap-imagery/items/scene-1",
            HTTP_AUTHORIZATION=f"Bearer {raw}",
        )

        self.assertEqual(response.status_code, 200)
        parsed = urlparse(response.data["assets"]["preview"]["href"])
        self.assertIn("/api/access/signed-assets/image-1/preview", parsed.path)
        query = parse_qs(parsed.query)
        signed_path = f"{parsed.path}?{parsed.query}"

        asset = self.client.get(signed_path, HTTP_RANGE="bytes=0-6")
        self.assertEqual(asset.status_code, 206)
        self.assertEqual(asset.content, b"preview")
        self.assertEqual(asset["Content-Range"], "bytes 0-6/13")

        head = self.client.head(signed_path, HTTP_RANGE="bytes=0-6")
        self.assertEqual(head.status_code, 206)
        self.assertEqual(head.content, b"")
        self.assertEqual(head["Content-Length"], "7")
        self.assertIn("signature", query)

    def test_catalog_collection_and_authentication(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get("/api/stac/").status_code, (401, 403))
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/stac/").data["id"], "airmap-catalog")
        self.assertEqual(self.client.get("/api/stac/collections").data["collections"][0]["id"], "airmap-imagery")
        self.assertEqual(self.client.get("/api/stac/collections/airmap-imagery").data["id"], "airmap-imagery")
        self.assertEqual(self.client.get("/api/stac/collections/airmap-imagery/items/scene-1").data["id"], "scene-1")
