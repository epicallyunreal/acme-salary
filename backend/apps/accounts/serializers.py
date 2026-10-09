from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from apps.accounts import services
from apps.accounts.models import User


class MeSerializer(serializers.ModelSerializer):
    """`GET /auth/me/`: the signed-in HR Manager, nothing a password hash could leak through."""

    class Meta:
        model = User
        fields = ("id", "email")
        read_only_fields = fields


class SessionRefreshSerializer(TokenRefreshSerializer):
    """`{refresh}` to `{access, refresh}` under the session rules in `accounts/services.py`:
    the session's end is kept across rotations, and a rotated-out or logged-out token presented
    again ends every session of its user before the 401."""

    def validate(self, attrs):
        access, refresh = services.refresh_session(attrs["refresh"])
        return {"access": str(access), "refresh": str(refresh)}
