import hashlib
import secrets

from django.conf import settings
from django.db import models


class ApiAccessToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_access_tokens")
    name = models.CharField(max_length=120)
    token_prefix = models.CharField(max_length=16, db_index=True)
    token_hash = models.CharField(max_length=64, unique=True)
    scopes = models.JSONField(default=list)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "access_control"
        ordering = ["-created_at"]

    @staticmethod
    def hash_token(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def issue(cls, *, user, name, scopes, expires_at=None):
        raw = secrets.token_urlsafe(32)
        token = cls.objects.create(user=user, name=name, token_prefix=raw[:8], token_hash=cls.hash_token(raw), scopes=scopes, expires_at=expires_at)
        return token, raw

    def is_active(self, now):
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > now)
