import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

from .models import ApiAccessToken
from .range_response import ranged_file_response
from .signing import sign_asset, valid_signature
from .views import _safe_asset_path


class AccessControlUnitTests(SimpleTestCase):
    def test_token_hash_is_one_way_and_signature_detects_tampering(self):
        self.assertEqual(len(ApiAccessToken.hash_token("secret")), 64)
        signature = sign_asset("image", "preview", 2000)
        self.assertTrue(valid_signature("image", "preview", 2000, signature))
        self.assertFalse(valid_signature("image", "data", 2000, signature))
        self.assertFalse(valid_signature("image", "preview", 2001, signature))

    def test_range_response_supports_single_ranges_and_rejects_multiple(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "asset.bin"
            path.write_bytes(b"0123456789")
            request = APIRequestFactory().get("/", HTTP_RANGE="bytes=2-5")
            response = ranged_file_response(request, path)
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.content, b"2345")
            self.assertEqual(response["Content-Range"], "bytes 2-5/10")

            invalid = APIRequestFactory().get("/", HTTP_RANGE="bytes=0-1,3-4")
            response = ranged_file_response(invalid, path)
            self.assertEqual(response.status_code, 416)
            self.assertEqual(response["Content-Range"], "bytes */10")

            head = APIRequestFactory().head("/")
            response = ranged_file_response(head, path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"")
            self.assertEqual(response["Content-Length"], "10")
            self.assertEqual(response["Accept-Ranges"], "bytes")

            ranged_head = APIRequestFactory().head("/", HTTP_RANGE="bytes=2-5")
            response = ranged_file_response(ranged_head, path)
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.content, b"")
            self.assertEqual(response["Content-Length"], "4")
            self.assertEqual(response["Content-Range"], "bytes 2-5/10")


    @override_settings(ACCESS_MAX_RANGE_BYTES=4)
    def test_range_response_rejects_ranges_over_configured_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "asset.bin"
            path.write_bytes(b"0123456789")
            too_large = APIRequestFactory().get("/", HTTP_RANGE="bytes=0-999999999")
            response = ranged_file_response(too_large, path)
            self.assertEqual(response.status_code, 416)
            self.assertEqual(response["Content-Range"], "bytes */10")

    def test_asset_path_cannot_escape_data_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root.parent / "outside.bin"
            outside.write_bytes(b"private")
            with patch("apps.access_control.views.settings.DATA_DIR", root):
                asset = SimpleNamespace(path=str(outside))
                with self.assertRaises(Exception):
                    _safe_asset_path(asset)


class ApiAccessTokenModelTests(SimpleTestCase):
    def test_issue_never_stores_raw_token_and_expiry_state(self):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        token = ApiAccessToken(expires_at=now.replace(year=now.year + 1))
        raw = "opaque-secret"
        token.token_hash = ApiAccessToken.hash_token(raw)
        self.assertNotEqual(token.token_hash, raw)
        self.assertTrue(token.is_active(now))
        token.revoked_at = now
        self.assertFalse(token.is_active(now))
        token.revoked_at = None
        token.expires_at = now
        self.assertFalse(token.is_active(now))
