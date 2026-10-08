from rest_framework import serializers


class ResetSerializer(serializers.Serializer):
    """Shape only: the service checks the password and the confirmation (SPEC F9)."""

    password = serializers.CharField(max_length=256, trim_whitespace=False)
    confirm = serializers.CharField(max_length=16)
