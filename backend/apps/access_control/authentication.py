from django.utils import timezone
from rest_framework import authentication, exceptions

from .models import ApiAccessToken


class BearerTokenAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        value = request.META.get("HTTP_AUTHORIZATION", "")
        parts = value.split()
        if not parts:
            return None
        if len(parts) != 2 or parts[0].lower() != self.keyword.lower():
            raise exceptions.AuthenticationFailed("Invalid bearer authorization")
        token = ApiAccessToken.objects.select_related("user").filter(token_hash=ApiAccessToken.hash_token(parts[1])).first()
        now = timezone.now()
        if not token or not token.is_active(now) or not token.user.is_active:
            raise exceptions.AuthenticationFailed("Invalid or expired token")
        token.last_used_at = now
        token.save(update_fields=["last_used_at"])
        return token.user, token

    def authenticate_header(self, request):
        return self.keyword


def has_scope(auth, scope):
    return bool(auth and scope in (auth.scopes or []))
