from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings

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
        try:
            refresh = self.token_class(attrs["refresh"])
        except TokenError:
            services.revoke_on_reuse(attrs["refresh"])
            raise
        user_id = refresh.payload.get(api_settings.USER_ID_CLAIM)
        user = (
            get_user_model().objects.filter(**{api_settings.USER_ID_FIELD: user_id}).first()
            if user_id
            else None
        )
        if user is None or not api_settings.USER_AUTHENTICATION_RULE(user):
            raise AuthenticationFailed(
                self.error_messages["no_active_account"], "no_active_account"
            )
        access, refresh = services.rotate(refresh)
        return {"access": str(access), "refresh": str(refresh)}
