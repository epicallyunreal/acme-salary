from rest_framework import serializers

from apps.accounts.models import User


class MeSerializer(serializers.ModelSerializer):
    """`GET /auth/me/`: the signed-in HR Manager, nothing a password hash could leak through."""

    class Meta:
        model = User
        fields = ("id", "email")
        read_only_fields = fields
