from django.contrib.auth.models import User
from rest_framework import serializers


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "is_staff", "is_superuser"]


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=128, write_only=True)
    email = serializers.EmailField(required=False, allow_blank=True, default="")

    def validate_username(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("用户名不能为空。")
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("用户名已被使用。")
        return value

    def validate_email(self, value):
        value = (value or "").strip()
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("邮箱已被使用。")
        return value

    def validate_password(self, value):
        from django.contrib.auth.password_validation import validate_password

        # Run against a transient user so similarity/attribute validators work.
        candidate = User(username=self.initial_data.get("username", ""))
        validate_password(value, user=candidate)
        return value

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
            email=validated_data.get("email") or "",
        )


class UserAdminSerializer(serializers.ModelSerializer):
    date_joined = serializers.DateTimeField(read_only=True)
    last_login = serializers.DateTimeField(read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "is_staff", "is_superuser", "is_active", "date_joined", "last_login"]
        read_only_fields = ["id", "username", "is_superuser", "date_joined", "last_login"]


class UserCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=128, write_only=True)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    is_staff = serializers.BooleanField(default=False)

    def validate_username(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("用户名不能为空。")
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("用户名已存在。")
        return value

    def validate_password(self, value):
        from django.contrib.auth.password_validation import validate_password

        candidate = User(username=self.initial_data.get("username", ""))
        validate_password(value, user=candidate)
        return value

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
            email=validated_data.get("email") or "",
            is_staff=validated_data.get("is_staff", False),
        )


class UserUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    is_staff = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)

    def validate_email(self, value):
        value = (value or "").strip()
        if value and User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("邮箱已被其他用户使用。")
        return value


class PasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(required=False, allow_blank=True, default="")
    new_password = serializers.CharField(max_length=128)

    def validate_new_password(self, value):
        from django.contrib.auth.password_validation import validate_password

        validate_password(value)
        return value


class AdminPasswordResetSerializer(serializers.Serializer):
    new_password = serializers.CharField(max_length=128)

    def validate_new_password(self, value):
        from django.contrib.auth.password_validation import validate_password

        validate_password(value)
        return value
