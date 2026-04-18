from django.contrib.auth import get_user_model, password_validation
from rest_framework import serializers

User = get_user_model()


class RegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value: str) -> str:
        return User.objects.normalize_email(value)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    remember_me = serializers.BooleanField(required=False, default=False)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        password_validation.validate_password(attrs["new_password"], self.context["request"].user)
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        password_validation.validate_password(attrs["new_password"])
        return attrs


class AccountDeletionSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)


def serialize_user(user: User, *, include_presence: bool, include_created_at: bool) -> dict:
    payload = {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
    }
    if include_presence:
        payload["presence"] = user.presence_state
    if include_created_at:
        payload["created_at"] = user.created_at.isoformat().replace("+00:00", "Z")
    return payload


def serialize_public_user(user: User, *, include_presence: bool) -> dict:
    payload = {
        "id": str(user.id),
        "username": user.username,
    }
    if include_presence:
        payload["presence"] = user.presence_state
    return payload


def serialize_session(
    session,
    *,
    is_current: bool,
    include_last_seen: bool,
    include_expires_at: bool,
    include_client_meta: bool,
):
    payload = {
        "id": str(session.id),
        "created_at": session.created_at.isoformat().replace("+00:00", "Z"),
        "is_current": is_current,
    }
    if include_client_meta:
        payload["ip_address"] = session.ip_address
        payload["user_agent"] = session.user_agent
    if include_last_seen:
        payload["last_seen_at"] = session.last_seen_at.isoformat().replace("+00:00", "Z")
    if include_expires_at:
        payload["expires_at"] = session.expires_at.isoformat().replace("+00:00", "Z")
    return payload
