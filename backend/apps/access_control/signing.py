import base64
import hashlib
import hmac
from urllib.parse import urlencode

from django.conf import settings


def signature_payload(image_id, role, expiry):
    return f"{image_id}\n{role}\n{expiry}".encode()


def sign_asset(image_id, role, expiry):
    digest = hmac.new(settings.SECRET_KEY.encode(), signature_payload(image_id, role, expiry), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def build_signed_path(request, image_id, role, expiry):
    sig = sign_asset(image_id, role, expiry)
    path = f"/api/access/signed-assets/{image_id}/{role}?{urlencode({'expires': expiry, 'signature': sig})}"
    public_base = str(getattr(settings, "PUBLIC_SERVICE_BASE_URL", "")).rstrip("/")
    return f"{public_base}{path}" if public_base else request.build_absolute_uri(path)


def valid_signature(image_id, role, expiry, supplied):
    return hmac.compare_digest(sign_asset(image_id, role, expiry), supplied or "")
