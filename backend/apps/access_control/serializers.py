from rest_framework import serializers

from .models import ApiAccessToken


class ApiAccessTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiAccessToken
        fields = ["id", "name", "token_prefix", "scopes", "expires_at", "revoked_at", "last_used_at", "created_at"]


class TokenCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    scopes = serializers.ListField(
        child=serializers.ChoiceField(choices=["catalog/read", "assets/read"]),
        required=False,
        allow_empty=False,
        default=["catalog/read", "assets/read"],
    )
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class AssetSignSerializer(serializers.Serializer):
    image_id = serializers.CharField(max_length=64)
    role = serializers.CharField(max_length=20)
    expires_in = serializers.IntegerField(min_value=1, max_value=3600)
